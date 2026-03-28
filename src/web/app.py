from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from fastapi import FastAPI, Form, UploadFile
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


@app.post("/api/run")
async def start_run(
    request_text: str = Form(default=""),
    request_file: UploadFile | None = None,
    source_path: str = Form(...),
    model: str = Form(default="claude-sonnet-4-6"),
) -> dict:
    run_id = uuid.uuid4().hex[:8]
    queue: Queue[PipelineEvent | None] = Queue()
    _runs[run_id] = queue

    # Resolve request content
    if request_file and request_file.filename:
        content = await request_file.read()
        request = content.decode("utf-8")
    else:
        request = request_text

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
        # 承認待ちイベントはon_event経由で既にキューに入っている
        approval_event.wait()
        result_data = _approval_requests.pop(run_id)["result"]
        return ApprovalResult(**result_data)

    def run_in_thread() -> None:
        try:
            run_pipeline(
                request=request,
                source_path=source_path,
                model=model,
                on_event=on_event,
                on_approval=web_approval,
            )
        except Exception as e:
            queue.put(PipelineEvent(type="pipeline_error", data={"error": str(e)}))
        finally:
            queue.put(None)  # sentinel

    thread = Thread(target=run_in_thread, daemon=True)
    thread.start()

    return {"run_id": run_id}


@app.post("/api/run/{run_id}/approve")
async def approve_request(
    run_id: str,
    approved: bool = Form(...),
    feedback: str = Form(default=""),
) -> dict:
    """ユーザー承認/却下を受け付ける。"""
    if run_id not in _approval_requests:
        return {"error": "no pending approval request"}
    _approval_requests[run_id]["result"] = {"approved": approved, "feedback": feedback}
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
