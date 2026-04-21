from __future__ import annotations

from src.themes.base import RoleSlot, SourcePathMode, Theme
from src.themes.investigation import build_investigation_theme
from src.themes.modification import build_modification_theme

_THEMES: dict[str, Theme] = {
    "modification": build_modification_theme(),
    "investigation": build_investigation_theme(),
}


def get_theme(theme_id: str) -> Theme:
    """テーマIDからTheme定義を返す。"""
    if theme_id not in _THEMES:
        available = list(_THEMES.keys())
        msg = f"Unknown theme: {theme_id!r}. Available: {available}"
        raise ValueError(msg)
    return _THEMES[theme_id]


def list_themes() -> list[Theme]:
    """登録済みテーマ一覧を返す（表示順）。"""
    return list(_THEMES.values())


__all__ = [
    "RoleSlot",
    "SourcePathMode",
    "Theme",
    "get_theme",
    "list_themes",
]
