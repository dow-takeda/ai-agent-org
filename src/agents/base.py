from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from src.client import call_llm

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class BaseAgent:
    """エージェントの基底クラス。"""

    prompt_file: str  # サブクラスで定義
    output_model: type[BaseModel]  # サブクラスで定義

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            path = PROMPTS_DIR / self.prompt_file
            self._system_prompt = path.read_text(encoding="utf-8")
        return self._system_prompt

    def _build_user_message(self, **kwargs: str) -> str:
        raise NotImplementedError

    def run(self, **kwargs: str) -> tuple[BaseModel, dict]:
        user_message = self._build_user_message(**kwargs)
        return call_llm(
            system_prompt=self.system_prompt,
            user_message=user_message,
            output_model=self.output_model,
            model=self.model,
        )
