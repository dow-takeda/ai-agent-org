from __future__ import annotations

import json
from queue import Queue
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.events import PipelineEvent
from src.web.app import _runs, app

client = TestClient(app)


class TestIndexPage:
    def test_get_index(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "AI改修チーム" in response.text
        assert "text/html" in response.headers["content-type"]


class TestStartRun:
    def test_start_run_returns_run_id(self):
        with patch("src.web.app.run_pipeline"):
            response = client.post(
                "/api/run",
                data={"request_text": "テスト要求", "source_path": "/var/src"},  # noqa: S108
            )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 8


class TestSSEStream:
    def test_stream_events(self):
        run_id = "test1234"
        queue: Queue[PipelineEvent | None] = Queue()
        _runs[run_id] = queue

        queue.put(PipelineEvent(type="pipeline_start", data={"request": "テスト"}))
        queue.put(PipelineEvent(type="agent_start", agent="pm"))
        queue.put(None)  # sentinel

        with client.stream("GET", f"/api/run/{run_id}/events") as response:
            assert response.status_code == 200
            lines = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    lines.append(json.loads(line.removeprefix("data: ")))

        assert lines[0]["type"] == "pipeline_start"
        assert lines[1]["type"] == "agent_start"
        assert lines[1]["agent"] == "pm"
        assert lines[2]["type"] == "done"

    def test_stream_unknown_run_id(self):
        with client.stream("GET", "/api/run/nonexistent/events") as response:
            assert response.status_code == 200
            lines = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    lines.append(json.loads(line.removeprefix("data: ")))
            assert lines[0]["type"] == "error"
