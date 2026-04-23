from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.analyst import AnalystAgent
from src.personalities import get_personality, load_personalities
from src.schemas import AuditFinding, CodebaseAuditReport


class TestAnalystPersonalities:
    def test_all_three_loaded(self):
        pers = load_personalities("analyst")
        ids = {p.id for p in pers}
        assert {"dependency_focused", "license_compliance", "security_minded"}.issubset(ids)

    def test_personality_fields(self):
        for pid in ("dependency_focused", "license_compliance", "security_minded"):
            p = get_personality("analyst", pid)
            assert p.role == "analyst"
            assert p.focus
            assert p.description
            assert len(p.traits) >= 2
            assert p.system_prompt_extra


class TestAnalystAgent:
    def test_init_bare(self):
        agent = AnalystAgent()
        assert agent.role == "analyst"
        assert agent.personality is None
        assert agent.tone is None

    def test_init_with_personality(self):
        agent = AnalystAgent(personality_id="dependency_focused")
        assert agent.personality.id == "dependency_focused"
        assert "依存" in agent.system_prompt

    def test_init_with_tone(self):
        agent = AnalystAgent(tone_id="polite")
        assert agent.tone.id == "polite"
        assert "## 口調" in agent.system_prompt

    def test_init_with_invalid_personality(self):
        with pytest.raises(ValueError, match="not found"):
            AnalystAgent(personality_id="nonexistent")

    def test_prompt_override(self):
        override_text = "あなたは独自のテスト用調査員です。"
        agent = AnalystAgent(prompt_override=override_text)
        assert override_text in agent.system_prompt

    def test_build_user_message_structure(self):
        agent = AnalystAgent()
        blocks = agent._build_user_message(
            request="EOL 依存の洗い出し",
            senior_engineer_output="調査スコープ...",
            files_content="ファイル内容...",
        )
        assert isinstance(blocks, list)
        assert len(blocks) == 3
        assert "調査依頼" in blocks[0]["text"]
        assert "調査スコープ" in blocks[1]["text"]
        assert "関連ソースコード" in blocks[2]["text"]

    def test_build_user_message_without_files(self):
        agent = AnalystAgent()
        blocks = agent._build_user_message(
            request="x",
            senior_engineer_output="y",
        )
        assert len(blocks) == 2

    def test_run_calls_llm_with_audit_schema(self):
        agent = AnalystAgent()
        fake_report = CodebaseAuditReport(
            summary="調査完了",
            scope="依存ライブラリの EOL 確認",
            findings=[
                AuditFinding(
                    category="dependency",
                    severity="high",
                    location="requirements.txt",
                    description="numpy==1.18 は EOL",
                    recommendation="numpy>=1.26 に更新",
                ),
            ],
            recommended_actions=["EOL 依存の更新"],
        )
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.return_value = (fake_report, {"input_tokens": 10, "output_tokens": 5})
            result, _ = agent.run(
                request="x",
                senior_engineer_output="y",
                files_content="",
            )
        assert result.scope.startswith("依存ライブラリ")
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["output_model"] == CodebaseAuditReport
