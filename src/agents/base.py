from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from src.client import call_llm
from src.personalities import Personality, get_personality

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# サブクラスのroleマッピング用
_ROLE_MAP: dict[str, str] = {}


class BaseAgent:
    """エージェントの基底クラス。"""

    prompt_file: str  # サブクラスで定義
    output_model: type[BaseModel]  # サブクラスで定義
    role: str  # サブクラスで定義 ("pm", "engineer", "reviewer")

    def __init__(self, model: str = "claude-sonnet-4-6", personality_id: str | None = None) -> None:
        self.model = model
        self._system_prompt: str | None = None
        self.personality: Personality | None = None
        if personality_id:
            self.personality = get_personality(self.role, personality_id)

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            path = PROMPTS_DIR / self.prompt_file
            base_prompt = path.read_text(encoding="utf-8")
            if self.personality:
                traits_text = "\n".join(f"- {t}" for t in self.personality.traits)
                personality_section = (
                    f"\n\n## あなたのパーソナリティ\n"
                    f"名前: {self.personality.name}\n"
                    f"こだわり: {self.personality.focus}\n"
                    f"特徴:\n{traits_text}\n\n"
                    f"{self.personality.system_prompt_extra}"
                )
                self._system_prompt = base_prompt + personality_section
            else:
                self._system_prompt = base_prompt
        return self._system_prompt

    def _build_user_message(self, **kwargs: str) -> str | list[dict]:
        raise NotImplementedError

    def run(self, **kwargs: str) -> tuple[BaseModel, dict]:
        user_message = self._build_user_message(**kwargs)
        return call_llm(
            system_prompt=self.system_prompt,
            user_message=user_message,
            output_model=self.output_model,
            model=self.model,
        )

    def run_discussion(self, **kwargs: str) -> tuple[BaseModel, dict]:
        """他のエージェントの出力を踏まえて再検討し、統合出力を生成する。"""
        own_output = kwargs["own_output"]
        other_output = kwargs["other_output"]
        remaining = {k: v for k, v in kwargs.items() if k not in ("own_output", "other_output")}
        base_blocks = self._build_user_message(**remaining)

        discussion_text = (
            f"[自分の前回の出力]\n{own_output}\n\n"
            f"[相手エージェントの出力]\n{other_output}\n\n"
            f"上記を踏まえ、最終的な出力を再検討してください。"
            f"相手の指摘で妥当な点は取り入れ、"
            f"自分の主張で重要な点は維持してください。"
            f"最終的な統合出力を生成してください。"
        )

        # base_blocks がcontent blocks (list[dict]) の場合、議論テキストを先頭に追加
        if isinstance(base_blocks, list):
            content = [{"type": "text", "text": discussion_text}, *base_blocks]
        else:
            content = f"{base_blocks}\n\n{discussion_text}"

        return call_llm(
            system_prompt=self.system_prompt,
            user_message=content,
            output_model=self.output_model,
            model=self.model,
        )
