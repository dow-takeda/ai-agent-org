from __future__ import annotations

import pytest

from src.personalities import (
    Personality,
    get_personality,
    list_personality_ids,
    load_personalities,
)

ROLES = ("pm", "engineer", "reviewer")
MIN_PERSONALITIES = 7


class TestLoadPersonalities:
    @pytest.mark.parametrize("role", ROLES)
    def test_load_all_roles(self, role):
        personalities = load_personalities(role)
        assert len(personalities) >= MIN_PERSONALITIES
        for p in personalities:
            assert p.role == role

    @pytest.mark.parametrize("role", ROLES)
    def test_all_fields_populated(self, role):
        for p in load_personalities(role):
            assert p.id
            assert p.name
            assert p.role == role
            assert p.focus
            assert p.description
            assert p.tone
            assert len(p.traits) >= 1
            assert p.system_prompt_extra

    @pytest.mark.parametrize("role", ROLES)
    def test_unique_ids(self, role):
        ids = [p.id for p in load_personalities(role)]
        assert len(ids) == len(set(ids)), f"Duplicate IDs in {role}: {ids}"

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            load_personalities("invalid")


class TestGetPersonality:
    def test_get_existing(self):
        p = get_personality("pm", "visionary")
        assert isinstance(p, Personality)
        assert p.id == "visionary"
        assert p.role == "pm"

    def test_get_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            get_personality("pm", "nonexistent")


class TestListPersonalityIds:
    @pytest.mark.parametrize("role", ROLES)
    def test_list_ids(self, role):
        ids = list_personality_ids(role)
        assert len(ids) >= MIN_PERSONALITIES
        assert all(isinstance(i, str) for i in ids)


class TestAgentPersonalityIntegration:
    def test_pm_agent_with_personality(self):
        from src.agents.pm import PMAgent

        agent = PMAgent(personality_id="visionary")
        assert agent.personality is not None
        assert "パーソナリティ" in agent.system_prompt
        assert "ビジョナリー" in agent.system_prompt

    def test_engineer_agent_with_personality(self):
        from src.agents.engineer import EngineerAgent

        agent = EngineerAgent(personality_id="performance")
        assert agent.personality is not None
        assert "パフォーマンス" in agent.system_prompt

    def test_reviewer_agent_with_personality(self):
        from src.agents.reviewer import ReviewerAgent

        agent = ReviewerAgent(personality_id="correctness")
        assert agent.personality is not None
        assert "正確性" in agent.system_prompt

    def test_agent_without_personality(self):
        from src.agents.pm import PMAgent

        agent = PMAgent()
        assert agent.personality is None
        assert "パーソナリティ" not in agent.system_prompt

    def test_agent_invalid_personality_raises(self):
        from src.agents.pm import PMAgent

        with pytest.raises(ValueError, match="not found"):
            PMAgent(personality_id="nonexistent")
