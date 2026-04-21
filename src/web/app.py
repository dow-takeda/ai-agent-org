from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.events import PipelineEvent
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


@app.get("/api/themes")
async def api_list_themes() -> list[dict]:
    """要望テーマ一覧を返す。UIのテーマ選択に使用。"""
    from src.themes import list_themes

    return [t.to_dict() for t in list_themes()]


@app.get("/api/themes/{theme_id}/prompts")
async def api_theme_prompts(theme_id: str) -> dict:
    """指定テーマの役職ごとのデフォルトプロンプト内容を返す（UIのtextarea初期値）。"""
    from src.themes import get_theme

    try:
        theme = get_theme(theme_id)
    except ValueError as e:
        return {"error": str(e)}
    return {role.role_id: role.load_prompt() for role in theme.roles}


@app.post("/api/run")
async def start_run(request: Request) -> dict:
    """テーマ対応の実行エンドポイント。JSON body または legacy form data を受け付ける。"""
    from src.config import load_config
    from src.themes import get_theme
    from src.themes.base import ThemeRoleOverride, ThemeRunContext

    content_type = request.headers.get("content-type", "")
    is_json = "application/json" in content_type

    if is_json:
        body = await request.json()
    else:
        # Legacy form data (改修要望テーマのみ対応、後方互換)
        form = await request.form()
        body = {
            "theme_id": "modification",
            "request_text": str(form.get("request_text", "")),
            "source_path": str(form.get("source_path", "")),
            "model": str(form.get("model", "claude-sonnet-4-6")),
            "roles": _legacy_form_to_roles(form),
        }

    theme_id = body.get("theme_id") or "modification"
    try:
        theme = get_theme(theme_id)
    except ValueError as e:
        return {"error": str(e)}

    run_id = uuid.uuid4().hex[:8]
    queue: Queue[PipelineEvent | None] = Queue()
    _runs[run_id] = queue

    req_text = str(body.get("request_text", ""))
    source_path = str(body.get("source_path", ""))
    model = str(body.get("model", "claude-sonnet-4-6"))
    raw_roles = body.get("roles") or []
    role_overrides = [
        ThemeRoleOverride(
            role_id=str(r["role_id"]),
            index=int(r.get("index", 1)),
            personality_id=r.get("personality_id") or None,
            tone_id=r.get("tone_id") or None,
            prompt_override=r.get("prompt_override") or None,
        )
        for r in raw_roles
        if r.get("role_id")
    ]

    # role_counts: roles[]の role_id 出現回数から算出
    role_counts: dict[str, int] = {}
    for ov in role_overrides:
        role_counts[ov.role_id] = role_counts.get(ov.role_id, 0) + 1

    ctx = ThemeRunContext(
        request=req_text,
        source_path=source_path,
        model=model,
        output_dir=None,
        role_overrides=role_overrides,
        role_counts=role_counts,
    )

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

    config = load_config()

    def run_in_thread() -> None:
        try:
            theme.run(ctx, config=config, on_event=on_event, on_approval=web_approval)
        except Exception as e:
            queue.put(PipelineEvent(type="pipeline_error", data={"error": str(e)}))
        finally:
            queue.put(None)  # sentinel

    thread = Thread(target=run_in_thread, daemon=True)
    thread.start()

    return {"run_id": run_id, "theme_id": theme_id}


def _legacy_form_to_roles(form) -> list[dict]:  # type: ignore[no-untyped-def]
    """旧 form 形式を roles[] に変換する（modification theme 専用互換）。"""

    def _get(key: str) -> str:
        return str(form.get(key, "") or "")

    roles: list[dict] = []
    se_p = _get("senior_engineer_personality")
    se_t = _get("senior_engineer_tone")
    if se_p or se_t:
        roles.append(
            {
                "role_id": "senior_engineer",
                "index": 1,
                "personality_id": se_p or None,
                "tone_id": se_t or None,
            }
        )
    pm_p = _get("pm_personality")
    pm_t = _get("pm_tone")
    if pm_p or pm_t:
        roles.append(
            {"role_id": "pm", "index": 1, "personality_id": pm_p or None, "tone_id": pm_t or None}
        )
    eng_tone = _get("engineer1_tone") or None
    for i in range(1, 10):
        eng_p = _get(f"engineer{i}_personality")
        if eng_p:
            roles.append(
                {"role_id": "engineer", "index": i, "personality_id": eng_p, "tone_id": eng_tone}
            )
    rev_tone = _get("reviewer1_tone") or None
    for i in range(1, 10):
        rev_p = _get(f"reviewer{i}_personality")
        if rev_p:
            roles.append(
                {"role_id": "reviewer", "index": i, "personality_id": rev_p, "tone_id": rev_tone}
            )
    return roles


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
