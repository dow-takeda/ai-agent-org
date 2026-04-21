from __future__ import annotations

from src.agents.base import BaseAgent
from src.personalities import VALID_ROLES
from src.schemas import TalkMessage, TalkResponse

ROLE_DISPLAY_NAMES: dict[str, str] = {
    "pm": "PM",
    "engineer": "エンジニア",
    "reviewer": "レビュアー",
    "senior_engineer": "シニアエンジニア",
}


class TalkAgent(BaseAgent):
    """談話室用の軽量エージェント。パイプラインとは独立した自由対話を行う。"""

    prompt_file = "talk.md"
    output_model = TalkResponse

    def __init__(
        self,
        role: str,
        model: str = "claude-sonnet-4-6",
        personality_id: str | None = None,
        tone_id: str | None = None,
    ) -> None:
        if role not in VALID_ROLES:
            msg = f"Invalid role: {role}. Must be one of {VALID_ROLES}"
            raise ValueError(msg)
        self.role = role
        super().__init__(
            model=model,
            personality_id=personality_id,
            tone_id=tone_id,
        )

    def _build_user_message(self, **kwargs: str) -> str:
        return kwargs["user_message"]

    def chat(self, messages: list[TalkMessage]) -> tuple[TalkResponse, dict]:
        """会話履歴を渡して応答を得る。

        履歴最後の発言（user）に対するassistant応答を生成する。
        それ以前のやり取りはコンテキストとして整形して渡す。
        """
        if not messages or messages[-1].role != "user":
            msg = "Last message must be from 'user'"
            raise ValueError(msg)

        if len(messages) == 1:
            user_message = messages[0].content
        else:
            history_text = "\n\n".join(
                f"[{'あなた' if m.role == 'assistant' else 'ユーザー'}の発言]\n{m.content}"
                for m in messages[:-1]
            )
            latest = messages[-1].content
            user_message = (
                f"これまでの会話:\n\n{history_text}\n\n"
                f"[ユーザーの最新発言]\n{latest}\n\n"
                f"上記の文脈を踏まえ、あなたとして応答してください。"
            )

        result, usage = self.run(user_message=user_message)
        if not isinstance(result, TalkResponse):  # pragma: no cover
            msg = f"Expected TalkResponse, got {type(result).__name__}"
            raise TypeError(msg)
        return result, usage
