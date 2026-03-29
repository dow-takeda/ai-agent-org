from __future__ import annotations

from unittest.mock import patch

import pytest

from src.config import PipelineConfig
from src.schemas import (
    ApprovalRequest,
    ApprovalResult,
    CodePatch,
    EngineerOutput,
    PMOutput,
    PMRollbackDecision,
    ReviewerOutput,
    RollbackProposal,
    SeniorEngineerOutput,
)


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("# app", encoding="utf-8")
    return str(src)


@pytest.fixture
def config():
    cfg = PipelineConfig.__new__(PipelineConfig)
    cfg.max_rollback_attempts = 3
    cfg.max_discussion_rounds = 2
    cfg.pm_count = 1
    cfg.engineer_count = 1
    cfg.reviewer_count = 1
    cfg.default_pm_personality = None
    cfg.default_engineer_personality = None
    cfg.default_reviewer_personality = None
    cfg.default_pm_tone = "onee"
    cfg.default_engineer_tone = "onee"
    cfg.default_reviewer_tone = "onee"
    return cfg


def _senior_eng_output():
    return SeniorEngineerOutput(
        summary="影響範囲を調べたわよ〜",
        impact_files=["app.py"],
        analysis="app.pyが直接の改修対象",
    )


def _pm_output():
    return PMOutput(
        summary="要件をまとめたわよ〜",
        requirements=["要件1"],
        tasks=["タスク1"],
        acceptance_criteria=["条件1"],
        referenced_files=["app.py"],
    )


def _eng_output(rollback=None):
    return EngineerOutput(
        summary="実装してみたわよ〜",
        design_notes="設計メモ",
        code_patches=[CodePatch(file_path="app.py", patch="print('hi')", description="追加")],
        assumptions=["前提1"],
        rollback_proposal=rollback,
    )


def _rev_output(result="PASS", rollback=None):
    return ReviewerOutput(
        summary="レビューしたわよ〜",
        review_result=result,
        issues=[] if result == "PASS" else ["問題1"],
        fix_instructions=[] if result == "PASS" else ["修正1"],
        rollback_proposal=rollback,
    )


def _approval_yes(req: ApprovalRequest) -> ApprovalResult:
    return ApprovalResult(approved=True)


def _approval_no(req: ApprovalRequest) -> ApprovalResult:
    return ApprovalResult(approved=False, feedback="改善してください")


def _approval_terminate(req: ApprovalRequest) -> ApprovalResult:
    return ApprovalResult(approved=False, terminate=True)


class TestHappyPath:
    def test_pass_pipeline(self, source_dir, config):
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),
                (_eng_output(), {}),
                (_rev_output("PASS"), {}),
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=_approval_yes,
                config=config,
            )
            assert result.exists()
            assert mock_llm.call_count == 4


class TestPMApproval:
    def test_pm_approval_rejected_then_approved(self, source_dir, config):
        call_count = [0]

        def approval_fn(req: ApprovalRequest) -> ApprovalResult:
            call_count[0] += 1
            if req.approval_type == "pm_output" and call_count[0] == 1:
                return ApprovalResult(approved=False, feedback="要件を明確にして")
            return ApprovalResult(approved=True)

        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),  # first PM
                (_pm_output(), {}),  # PM re-run after rejection
                (_eng_output(), {}),
                (_rev_output("PASS"), {}),
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=approval_fn,
                config=config,
            )
            assert result.exists()
            assert mock_llm.call_count == 5


class TestRollback:
    def test_engineer_rollback_approved_by_pm(self, source_dir, config):
        rollback_proposal = RollbackProposal(
            source_agent="engineer",
            target_agent="pm",
            reason="要件に矛盾がある",
            details=["要件1と要件2が矛盾"],
        )
        pm_decision = PMRollbackDecision(
            approved=True,
            reason="確かに矛盾がある",
            instructions=["要件を再整理すること"],
        )

        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),  # first PM
                (_eng_output(rollback=rollback_proposal), {}),  # engineer with rollback
                (pm_decision, {}),  # PM rollback review
                (_pm_output(), {}),  # PM re-run
                (_eng_output(), {}),  # engineer retry
                (_rev_output("PASS"), {}),
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=_approval_yes,
                config=config,
            )
            assert result.exists()

    def test_reviewer_rollback_pm_rejects_user_overrides(self, source_dir, config):
        rollback_proposal = RollbackProposal(
            source_agent="reviewer",
            target_agent="engineer",
            reason="設計に根本的な問題",
            details=["パフォーマンスの考慮なし"],
        )
        pm_decision = PMRollbackDecision(
            approved=False,
            reason="軽微な問題",
            instructions=[],
        )

        override_count = [0]

        def approval_fn(req: ApprovalRequest) -> ApprovalResult:
            if req.approval_type == "rollback_override":
                override_count[0] += 1
                return ApprovalResult(approved=True, feedback="差し戻してください")
            return ApprovalResult(approved=True)

        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),
                (_eng_output(), {}),
                (_rev_output("FAIL", rollback=rollback_proposal), {}),
                (pm_decision, {}),  # PM rejects rollback
                # user overrides → engineer re-runs
                (_eng_output(), {}),
                (_rev_output("PASS"), {}),
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=approval_fn,
                config=config,
            )
            assert result.exists()
            assert override_count[0] == 1


class TestRollbackLimit:
    def test_rollback_limit_reached(self, source_dir, config):
        config.max_rollback_attempts = 2

        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),
                (_eng_output(), {}),
                (_rev_output("FAIL"), {}),  # FAIL → retry 1
                (_eng_output(), {}),
                (_rev_output("FAIL"), {}),  # FAIL → retry 2 (limit)
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=_approval_yes,
                config=config,
            )
            assert result.exists()


class TestTerminate:
    def test_terminate_at_pm_approval(self, source_dir, config):
        """ユーザーが終了を指示した場合、PM出力までで終了する。"""
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=_approval_terminate,
                config=config,
            )
            assert result.exists()
            assert mock_llm.call_count == 2  # Senior Eng + PM only


class TestReviewFailRetry:
    def test_review_fail_then_pass(self, source_dir, config):
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),
                (_eng_output(), {}),
                (_rev_output("FAIL"), {}),  # first review: FAIL
                (_eng_output(), {}),  # engineer retry
                (_rev_output("PASS"), {}),  # second review: PASS
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=_approval_yes,
                config=config,
            )
            assert result.exists()
            assert mock_llm.call_count == 6


class TestNoApprovalCallback:
    def test_pipeline_without_approval(self, source_dir, config):
        """on_approval=Noneの場合、承認ステップがスキップされる。"""
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.side_effect = [
                (_senior_eng_output(), {}),  # senior engineer
                (_pm_output(), {}),
                (_eng_output(), {}),
                (_rev_output("PASS"), {}),
            ]
            from src.pipeline import run_pipeline

            result = run_pipeline(
                request="テスト要求",
                source_path=source_dir,
                on_approval=None,
                config=config,
            )
            assert result.exists()
            assert mock_llm.call_count == 4
