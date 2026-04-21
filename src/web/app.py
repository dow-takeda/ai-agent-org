from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.events import PipelineEvent
from src.pipeline import run_pipeline
from src.schemas import ApprovalRequest, ApprovalResult

app = FastAPI(title="AI Agent Org - Demo")

STATIC_DIR = Path(__file__).parent / "static"

# In-memory run queue store (demo tool, single user)
_runs: dict[str, Queue[PipelineEvent | None]] = {}

# In-memory approval store: run_id -> {event, request, result}
_approval_requests: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/talk", response_class=HTMLResponse)
async def talk_page() -> HTMLResponse:
    html = (STATIC_DIR / "talk.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/api/config")
async def get_config() -> dict:
    """パイプライン設定を返す。"""
    from src.config import load_config

    config = load_config()
    is_container = Path("/.dockerenv").exists()
    return {
        "engineer_count": config.engineer_count,
        "reviewer_count": config.reviewer_count,
        "is_container": is_container,
        "default_source": "/workspace/source" if is_container else "",
    }


@app.get("/api/browse")
async def browse_directory(path: str = "") -> dict:
    """ディレクトリの内容を返す（ファイルツリーブラウザ用）。"""
    from src.context import SKIP_DIRS

    target = Path(path) if path else None
    if not target or not target.is_dir():
        return {"error": "invalid path", "entries": []}

    entries = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith(".") or item.name in SKIP_DIRS:
                continue
            entries.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                }
            )
    except PermissionError:
        return {"error": "permission denied", "entries": []}
    return {"path": str(target), "entries": entries}


@app.get("/api/personalities")
async def list_personalities() -> dict:
    """役職別のパーソナリティ一覧を返す。"""
    from src.personalities import load_personalities

    result = {}
    for role in ("senior_engineer", "pm", "engineer", "reviewer"):
        personalities = load_personalities(role)
        result[role] = [
            {"id": p.id, "name": p.name, "focus": p.focus, "description": p.description}
            for p in personalities
        ]
    return result


@app.get("/api/tones")
async def list_tones() -> list[dict]:
    """口調一覧を返す。"""
    from src.personalities import load_tones

    tones = load_tones()
    return [{"id": t.id, "name": t.name, "description": t.description} for t in tones]


@app.post("/api/run")
async def start_run(request: Request) -> dict:
    form = await request.form()

    request_text = form.get("request_text", "")
    source_path = form.get("source_path", "")
    model = form.get("model", "claude-sonnet-4-6")

    run_id = uuid.uuid4().hex[:8]
    queue: Queue[PipelineEvent | None] = Queue()
    _runs[run_id] = queue

    req_text = str(request_text)

    # Personality/tone: 動的にフォームから収集
    def _get(key: str) -> str:
        return str(form.get(key, "") or "")

    se_personality = _get("senior_engineer_personality")
    pm_personality = _get("pm_personality")
    se_tone = _get("senior_engineer_tone")
    pm_tone = _get("pm_tone")

    eng_pids = [_get(f"engineer{i}_personality") for i in range(1, 10)]
    eng_pids = [p for p in eng_pids if p]
    rev_pids = [_get(f"reviewer{i}_personality") for i in range(1, 10)]
    rev_pids = [p for p in rev_pids if p]
    eng_tone = _get("engineer1_tone")
    rev_tone = _get("reviewer1_tone")

    def on_event(event: PipelineEvent) -> None:
        queue.put(event)

    def web_approval(req: ApprovalRequest) -> ApprovalResult:
        """Web用の承認コールバック。Eventでパイプラインスレッドをブロックする。"""
        approval_event = Event()
        _approval_requests[run_id] = {
            "event": approval_event,
            "request": req.model_dump(),
            "result": None,
        }
        approval_event.wait()
        result_data = _approval_requests.pop(run_id)["result"]
        return ApprovalResult(**result_data)

    def run_in_thread() -> None:
        try:
            run_pipeline(
                request=req_text,
                source_path=str(source_path),
                model=str(model),
                on_event=on_event,
                on_approval=web_approval,
                senior_engineer_personality_id=se_personality or None,
                pm_personality_id=pm_personality or None,
                engineer_personality_ids=eng_pids or None,
                reviewer_personality_ids=rev_pids or None,
                senior_engineer_tone_id=se_tone or None,
                pm_tone_id=pm_tone or None,
                engineer_tone_id=eng_tone or None,
                reviewer_tone_id=rev_tone or None,
            )
        except Exception as e:
            queue.put(PipelineEvent(type="pipeline_error", data={"error": str(e)}))
        finally:
            queue.put(None)  # sentinel

    thread = Thread(target=run_in_thread, daemon=True)
    thread.start()

    return {"run_id": run_id}


@app.post("/api/talk")
async def talk(request: Request) -> dict:
    """談話室の単発リクエスト。会話履歴と選択情報を受け取り、応答を返す。"""
    from src.schemas import TalkMessage
    from src.talk import ROLE_DISPLAY_NAMES, TalkAgent

    body = await request.json()
    role = str(body.get("role", ""))
    personality_id = body.get("personality_id") or None
    tone_id = body.get("tone_id") or None
    model = str(body.get("model", "claude-sonnet-4-6"))
    raw_messages = body.get("messages", [])

    if role not in ROLE_DISPLAY_NAMES:
        return {"error": f"invalid role: {role}"}
    if not raw_messages:
        return {"error": "messages is required"}

    try:
        messages = [TalkMessage(**m) for m in raw_messages]
    except Exception as e:  # noqa: BLE001
        return {"error": f"invalid messages: {e}"}

    try:
        agent = TalkAgent(
            role=role,
            model=model,
            personality_id=personality_id,
            tone_id=tone_id,
        )
        result, _usage = agent.chat(messages)
    except ValueError as e:
        return {"error": str(e)}

    return {"reply": result.reply}


@app.post("/api/run/{run_id}/approve")
async def approve_request(
    run_id: str,
    approved: bool = Form(...),
    feedback: str = Form(default=""),
    terminate: bool = Form(default=False),
) -> dict:
    """ユーザー承認/却下/終了を受け付ける。"""
    if run_id not in _approval_requests:
        return {"error": "no pending approval request"}
    _approval_requests[run_id]["result"] = {
        "approved": approved,
        "feedback": feedback,
        "terminate": terminate,
    }
    _approval_requests[run_id]["event"].set()
    return {"ok": True}


@app.get("/api/run/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    queue = _runs.get(run_id)
    if not queue:
        return StreamingResponse(
            iter(['data: {"type": "error", "data": {"error": "run not found"}}\n\n']),
            media_type="text/event-stream",
        )

    async def event_generator():  # type: ignore[no-untyped-def]
        try:
            while True:
                try:
                    event = queue.get_nowait()
                except Empty:
                    await asyncio.sleep(0.05)
                    continue
                if event is None:
                    yield 'data: {"type": "done"}\n\n'
                    break
                yield event.to_sse()
        finally:
            _runs.pop(run_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
