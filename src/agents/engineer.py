from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import EngineerOutput


class EngineerAgent(BaseAgent):
    prompt_file = "engineer.md"
    output_model = EngineerOutput
    role = "engineer"

    def _build_user_message(self, **kwargs: str) -> str:
        pm_output = kwargs["pm_output"]
        source_context = kwargs["source_context"]
        return f"[PMの出力]\n{pm_output}\n\n[対象ソースコード]\n{source_context}"
