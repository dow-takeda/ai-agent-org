from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.base import BaseAgent


class SourcePathMode(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    UNUSED = "unused"


@dataclass
class RoleSlot:
    """テーマで使う1つの役職スロット定義。"""

    role_id: str
    display_name: str
    agent_class: type[BaseAgent]
    default_count: int
    min_count: int
    max_count: int
    prompt_path: Path  # prompt ファイルへの絶対パス
    default_personality_id: str | None = None

    def load_prompt(self) -> str:
        """prompt ファイルを読み込む。"""
        return self.prompt_path.read_text(encoding="utf-8")


@dataclass
class ThemeRoleOverride:
    """1 実行分の役職ごとのユーザ上書き設定。"""

    role_id: str
    index: int  # 1-based（同一役職で複数いる場合の識別）
    personality_id: str | None = None
    tone_id: str | None = None
    prompt_override: str | None = None


@dataclass
class ThemeRunContext:
    """テーマ実行時に渡されるコンテキスト。"""

    request: str
    source_path: str  # unused テーマでは空文字列可
    model: str
    output_dir: Path | None
    role_overrides: list[ThemeRoleOverride] = field(default_factory=list)
    # 個別役職人数の上書き（role_id -> count）。未指定の場合 default_count を使う
    role_counts: dict[str, int] = field(default_factory=dict)

    def override_for(self, role_id: str, index: int) -> ThemeRoleOverride | None:
        """指定 role_id / index の override を返す。無ければ None。"""
        for ov in self.role_overrides:
            if ov.role_id == role_id and ov.index == index:
                return ov
        return None


@dataclass
class Theme:
    """テーマ定義。UIへの提示情報と実行関数を持つ。"""

    id: str
    name: str
    description: str
    source_path_mode: SourcePathMode
    request_label: str
    request_placeholder: str
    roles: list[RoleSlot]
    # run(ctx, on_event, on_approval) -> Path
    run: Callable[..., Path]

    def get_role(self, role_id: str) -> RoleSlot:
        """role_id に一致する RoleSlot を返す。"""
        for r in self.roles:
            if r.role_id == role_id:
                return r
        msg = f"Role {role_id!r} not defined in theme {self.id!r}"
        raise ValueError(msg)

    def to_dict(self) -> dict:
        """UI へ渡すための辞書化。agent_class や callable は除外。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source_path_mode": self.source_path_mode.value,
            "request_label": self.request_label,
            "request_placeholder": self.request_placeholder,
            "roles": [
                {
                    "role_id": r.role_id,
                    "display_name": r.display_name,
                    "default_count": r.default_count,
                    "min_count": r.min_count,
                    "max_count": r.max_count,
                    "default_personality_id": r.default_personality_id,
                }
                for r in self.roles
            ],
        }
