from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import PMOutput


class PMAgent(BaseAgent):
    prompt_file = "pm.md"
    output_model = PMOutput

    def _build_user_message(self, **kwargs: str) -> str:
        request = kwargs["request"]
        source_context = kwargs["source_context"]
        return f"[改修要求]\n{request}\n\n[対象ソースコード]\n{source_context}"
