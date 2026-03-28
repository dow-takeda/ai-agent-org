from __future__ import annotations

import json

from src.events import PipelineEvent


class TestPipelineEvent:
    def test_create_event(self):
        event = PipelineEvent(type="agent_start", agent="pm")
        assert event.type == "agent_start"
        assert event.agent == "pm"
        assert event.data == {}
        assert event.timestamp > 0

    def test_create_event_with_data(self):
        event = PipelineEvent(
            type="agent_complete",
            agent="reviewer",
            data={"output": {"review_result": "PASS"}},
        )
        assert event.data["output"]["review_result"] == "PASS"

    def test_to_sse_format(self):
        event = PipelineEvent(type="pipeline_start", data={"request": "テスト要求"})
        sse = event.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        payload = json.loads(sse.removeprefix("data: ").strip())
        assert payload["type"] == "pipeline_start"
        assert payload["data"]["request"] == "テスト要求"

    def test_to_sse_ensure_ascii_false(self):
        event = PipelineEvent(type="pipeline_start", data={"request": "日本語テスト"})
        sse = event.to_sse()
        assert "日本語テスト" in sse
