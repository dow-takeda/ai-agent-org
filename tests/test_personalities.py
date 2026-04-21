from __future__ import annotations

import pytest

from src.personalities import (
    Personality,
    Tone,
    get_personality,
    get_tone,
    list_personality_ids,
    load_personalities,
    load_tones,
)

ROLES = ("pm", "engineer", "reviewer")
MIN_PERSONALITIES = 7
ALL_ROLES = ("pm", "engineer", "reviewer", "senior_engineer", "investigator")


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
            assert len(p.traits) >= 1
            assert p.system_prompt_extra

    @pytest.mark.parametrize("role", ROLES)
    def test_unique_ids(self, role):
        ids = [p.id for p in load_personalities(role)]
        assert len(ids) == len(set(ids)), f"Duplicate IDs in {role}: {ids}"

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            load_personalities("invalid")

    def test_investigator_role_loads(self):
        pers = load_personalities("investigator")
        assert len(pers) >= 3
        for p in pers:
            assert p.role == "investigator"
            assert p.focus
            assert p.system_prompt_extra


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


class TestTones:
    def test_load_tones(self):
        tones = load_tones()
        assert len(tones) >= 4
        for t in tones:
            assert isinstance(t, Tone)
            assert t.id
            assert t.name
            assert t.prompt_instruction

    def test_get_tone_existing(self):
        t = get_tone("onee")
        assert t.id == "onee"
        assert "おネエ" in t.name

    def test_get_tone_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            get_tone("nonexistent")

    def test_tone_prompts_are_enriched(self):
        """口調プロンプトが十分な長さと多様性指示を持つこと（Issue #28リグレッション防止）。"""
        for t in load_tones():
            assert len(t.prompt_instruction) >= 400, (
                f"Tone '{t.id}' prompt is too short ({len(t.prompt_instruction)} chars)"
            )
            assert "バリエーション" in t.prompt_instruction, (
                f"Tone '{t.id}' prompt lacks variation instruction"
            )


class TestAgentToneIntegration:
    def test_agent_with_tone(self):
        from src.agents.pm import PMAgent

        agent = PMAgent(tone_id="onee")
        assert agent.tone is not None
        assert "口調" in agent.system_prompt
        assert "おネエ" in agent.system_prompt

    def test_agent_with_personality_and_tone(self):
        from src.agents.engineer import EngineerAgent

        agent = EngineerAgent(personality_id="performance", tone_id="samurai")
        assert agent.personality is not None
        assert agent.tone is not None
        assert "パフォーマンス" in agent.system_prompt
        assert "でござる" in agent.system_prompt

    def test_agent_without_tone(self):
        from src.agents.pm import PMAgent

        agent = PMAgent()
        assert agent.tone is None
        assert "## 口調" not in agent.system_prompt


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
