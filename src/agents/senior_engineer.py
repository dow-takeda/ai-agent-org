from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import SeniorEngineerOutput


class SeniorEngineerAgent(BaseAgent):
    prompt_file = "senior_engineer.md"
    output_model = SeniorEngineerOutput
    role = "senior_engineer"

    def _build_user_message(self, **kwargs: str) -> list[dict]:
        request = kwargs["request"]
        source_skeleton = kwargs["source_skeleton"]
        return [
            {"type": "text", "text": f"[改修要求]\n{request}"},
            {
                "type": "text",
                "text": f"[ソースコード構造]\n{source_skeleton}",
                "cache_control": {"type": "ephemeral"},
            },
        ]
