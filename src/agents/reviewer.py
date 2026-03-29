from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import ReviewerOutput


class ReviewerAgent(BaseAgent):
    prompt_file = "reviewer.md"
    output_model = ReviewerOutput
    role = "reviewer"

    def _build_user_message(self, **kwargs: str) -> list[dict]:
        request = kwargs["request"]
        pm_output = kwargs["pm_output"]
        engineer_output = kwargs["engineer_output"]
        files_content = kwargs["files_content"]
        return [
            {
                "type": "text",
                "text": (
                    f"[改修要求]\n{request}\n\n"
                    f"[PMの出力]\n{pm_output}\n\n"
                    f"[エンジニアの出力]\n{engineer_output}"
                ),
            },
            {
                "type": "text",
                "text": f"[対象ソースコード]\n{files_content}",
                "cache_control": {"type": "ephemeral"},
            },
        ]
