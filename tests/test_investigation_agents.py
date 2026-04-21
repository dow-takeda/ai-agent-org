from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.investigator import InvestigatorAgent
from src.personalities import get_personality, load_personalities
from src.schemas import InvestigationReport


class TestInvestigatorPersonalities:
    def test_all_three_loaded(self):
        pers = load_personalities("investigator")
        ids = {p.id for p in pers}
        assert {"forensic", "hypothesis_driven", "systemic"}.issubset(ids)

    def test_personality_fields(self):
        for pid in ("forensic", "hypothesis_driven", "systemic"):
            p = get_personality("investigator", pid)
            assert p.role == "investigator"
            assert p.focus
            assert p.description
            assert len(p.traits) >= 2
            assert p.system_prompt_extra


class TestInvestigatorAgent:
    def test_init_bare(self):
        agent = InvestigatorAgent()
        assert agent.role == "investigator"
        assert agent.personality is None
        assert agent.tone is None

    def test_init_with_personality(self):
        agent = InvestigatorAgent(personality_id="forensic")
        assert agent.personality.id == "forensic"
        assert "フォレンジック" in agent.system_prompt

    def test_init_with_tone(self):
        agent = InvestigatorAgent(tone_id="polite")
        assert agent.tone.id == "polite"
        assert "## 口調" in agent.system_prompt

    def test_init_with_invalid_personality(self):
        with pytest.raises(ValueError, match="not found"):
            InvestigatorAgent(personality_id="nonexistent")

    def test_prompt_override(self):
        override_text = "あなたは独自のテスト用調査員です。"
        agent = InvestigatorAgent(prompt_override=override_text)
        assert override_text in agent.system_prompt

    def test_build_user_message_structure(self):
        agent = InvestigatorAgent()
        blocks = agent._build_user_message(
            request="障害: ログイン時にクラッシュ",
            senior_engineer_output="影響分析...",
            files_content="ファイル内容...",
        )
        assert isinstance(blocks, list)
        assert len(blocks) == 3
        assert "障害" in blocks[0]["text"]
        assert "影響分析" in blocks[1]["text"]

    def test_run_calls_llm_with_report_schema(self):
        agent = InvestigatorAgent()
        fake_report = InvestigationReport(
            summary="調査完了",
            root_cause="セッション管理のバグ",
            hypotheses=["仮説1"],
            evidence=["証拠1"],
            affected_files=["app.py"],
            reproduction_steps=["ログインする"],
            severity="high",
            recommended_actions=["追加調査"],
        )
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.return_value = (fake_report, {"input_tokens": 10, "output_tokens": 5})
            result, _ = agent.run(
                request="x",
                senior_engineer_output="y",
                files_content="",
            )
        assert result.root_cause == "セッション管理のバグ"
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["output_model"] == InvestigationReport
