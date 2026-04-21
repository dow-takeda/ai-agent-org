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
        assert "AI エージェント組織" in response.text
        assert "text/html" in response.headers["content-type"]

    def test_index_has_talk_link(self):
        response = client.get("/")
        assert "/talk" in response.text
        assert "談話室" in response.text


class TestTalkPage:
    def test_get_talk(self):
        response = client.get("/talk")
        assert response.status_code == 200
        assert "談話室" in response.text
        assert "text/html" in response.headers["content-type"]


class TestTalkAPI:
    def test_talk_missing_role(self):
        response = client.post(
            "/api/talk",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 200
        assert "error" in response.json()

    def test_talk_missing_messages(self):
        response = client.post(
            "/api/talk",
            json={"role": "pm", "messages": []},
        )
        assert response.json().get("error") == "messages is required"

    def test_talk_success(self):
        from src.schemas import TalkResponse

        with patch("src.talk.TalkAgent.chat") as mock_chat:
            mock_chat.return_value = (
                TalkResponse(reply="あら、こんにちは！"),
                {"input_tokens": 10, "output_tokens": 5},
            )
            response = client.post(
                "/api/talk",
                json={
                    "role": "pm",
                    "personality_id": "visionary",
                    "tone_id": "onee",
                    "messages": [{"role": "user", "content": "やあ"}],
                },
            )
        assert response.status_code == 200
        assert response.json() == {"reply": "あら、こんにちは！"}


class TestStartRun:
    def test_start_run_legacy_form_returns_run_id(self):
        """旧 form 形式（modification theme）の下位互換。"""
        with patch("src.themes.modification.run_pipeline"):
            response = client.post(
                "/api/run",
                data={"request_text": "テスト要求", "source_path": "/var/src"},  # noqa: S108
            )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 8
        assert data.get("theme_id") == "modification"

    def test_start_run_json_theme_modification(self):
        with patch("src.themes.modification.run_pipeline"):
            response = client.post(
                "/api/run",
                json={
                    "theme_id": "modification",
                    "request_text": "テスト",
                    "source_path": "/var/src",  # noqa: S108
                    "roles": [{"role_id": "pm", "index": 1}],
                },
            )
        assert response.status_code == 200
        assert response.json().get("theme_id") == "modification"

    def test_start_run_invalid_theme(self):
        response = client.post(
            "/api/run",
            json={"theme_id": "nonexistent", "request_text": "x", "source_path": "/x"},
        )
        assert response.status_code == 200
        assert "error" in response.json()


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
