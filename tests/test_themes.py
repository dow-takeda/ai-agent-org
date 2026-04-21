from __future__ import annotations

import pytest

from src.themes import get_theme, list_themes
from src.themes.base import RoleSlot, SourcePathMode, Theme, ThemeRoleOverride, ThemeRunContext


class TestRegistry:
    def test_list_themes_returns_known_themes(self):
        ids = {t.id for t in list_themes()}
        assert "modification" in ids
        assert "investigation" in ids

    def test_get_theme_returns_theme(self):
        t = get_theme("modification")
        assert isinstance(t, Theme)
        assert t.id == "modification"

    def test_get_theme_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown theme"):
            get_theme("nonexistent")


class TestModificationTheme:
    def test_fields(self):
        t = get_theme("modification")
        assert t.name == "改修要望"
        assert t.source_path_mode == SourcePathMode.REQUIRED
        role_ids = [r.role_id for r in t.roles]
        assert role_ids == ["senior_engineer", "pm", "engineer", "reviewer"]

    def test_prompts_exist(self):
        t = get_theme("modification")
        for role in t.roles:
            content = role.load_prompt()
            assert len(content) > 20


class TestInvestigationTheme:
    def test_fields(self):
        t = get_theme("investigation")
        assert t.name == "障害調査"
        assert t.source_path_mode == SourcePathMode.REQUIRED
        role_ids = [r.role_id for r in t.roles]
        assert role_ids == ["senior_engineer", "investigator", "reviewer"]
        investigator_role = t.get_role("investigator")
        assert investigator_role.default_count == 2
        assert investigator_role.min_count == 1
        assert investigator_role.max_count >= 2

    def test_prompts_exist(self):
        t = get_theme("investigation")
        for role in t.roles:
            content = role.load_prompt()
            assert len(content) > 30


class TestThemeSerialization:
    def test_to_dict_excludes_callable(self):
        t = get_theme("modification")
        d = t.to_dict()
        assert "run" not in d
        assert d["id"] == "modification"
        assert "source_path_mode" in d
        assert isinstance(d["roles"], list)
        assert all("role_id" in r for r in d["roles"])

    def test_to_dict_includes_max_count(self):
        t = get_theme("investigation")
        d = t.to_dict()
        inv = next(r for r in d["roles"] if r["role_id"] == "investigator")
        assert inv["max_count"] >= 2
        assert inv["min_count"] == 1


class TestThemeRunContext:
    def test_override_lookup(self):
        ctx = ThemeRunContext(
            request="x",
            source_path="/tmp",  # noqa: S108
            model="claude-sonnet-4-6",
            output_dir=None,
            role_overrides=[
                ThemeRoleOverride(role_id="pm", index=1, personality_id="visionary"),
                ThemeRoleOverride(role_id="engineer", index=2, tone_id="onee"),
            ],
        )
        pm_ov = ctx.override_for("pm", 1)
        assert pm_ov is not None
        assert pm_ov.personality_id == "visionary"
        assert ctx.override_for("pm", 2) is None
        eng_ov = ctx.override_for("engineer", 2)
        assert eng_ov is not None
        assert eng_ov.tone_id == "onee"


class TestRoleSlot:
    def test_role_slot_load_prompt(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("hello prompt", encoding="utf-8")
        from src.agents.pm import PMAgent

        slot = RoleSlot(
            role_id="pm",
            display_name="PM",
            agent_class=PMAgent,
            default_count=1,
            min_count=1,
            max_count=1,
            prompt_path=p,
        )
        assert slot.load_prompt() == "hello prompt"
