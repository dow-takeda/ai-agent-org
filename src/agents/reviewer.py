from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import ReviewerOutput


class ReviewerAgent(BaseAgent):
    prompt_file = "reviewer.md"
    output_model = ReviewerOutput
    role = "reviewer"

    def _build_user_message(self, **kwargs: str) -> str:
        request = kwargs["request"]
        pm_output = kwargs["pm_output"]
        engineer_output = kwargs["engineer_output"]
        source_context = kwargs["source_context"]
        return (
            f"[改修要求]\n{request}\n\n"
            f"[PMの出力]\n{pm_output}\n\n"
            f"[エンジニアの出力]\n{engineer_output}\n\n"
            f"[対象ソースコード]\n{source_context}"
        )
