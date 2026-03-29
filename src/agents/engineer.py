from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import EngineerOutput


class EngineerAgent(BaseAgent):
    prompt_file = "engineer.md"
    output_model = EngineerOutput
    role = "engineer"

    def _build_user_message(self, **kwargs: str) -> list[dict]:
        pm_output = kwargs["pm_output"]
        files_content = kwargs["files_content"]
        return [
            {"type": "text", "text": f"[PMの出力]\n{pm_output}"},
            {
                "type": "text",
                "text": f"[対象ソースコード]\n{files_content}",
                "cache_control": {"type": "ephemeral"},
            },
        ]
