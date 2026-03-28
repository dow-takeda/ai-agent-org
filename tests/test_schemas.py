from src.schemas import (
    ApprovalRequest,
    ApprovalResult,
    CodePatch,
    EngineerOutput,
    PMOutput,
    PMRollbackDecision,
    ReviewerOutput,
    RollbackProposal,
)


def test_pm_output_roundtrip():
    data = {
        "requirements": ["要件1"],
        "tasks": ["タスク1"],
        "acceptance_criteria": ["条件1"],
    }
    output = PMOutput.model_validate(data)
    assert output.requirements == ["要件1"]
    assert output.model_dump() == data


def test_engineer_output_roundtrip():
    data = {
        "design_notes": "設計メモ",
        "code_patches": [
            {"file_path": "app.py", "patch": "print('hello')", "description": "追加"},
        ],
        "assumptions": ["前提1"],
    }
    output = EngineerOutput.model_validate(data)
    assert len(output.code_patches) == 1
    assert isinstance(output.code_patches[0], CodePatch)


def test_reviewer_output_pass():
    output = ReviewerOutput(review_result="PASS", issues=[], fix_instructions=[])
    assert output.review_result == "PASS"


def test_reviewer_output_fail():
    output = ReviewerOutput(
        review_result="FAIL",
        issues=["問題1"],
        fix_instructions=["修正1"],
    )
    assert output.review_result == "FAIL"
    assert len(output.issues) == 1


def test_pm_output_json_schema_has_required_fields():
    schema = PMOutput.model_json_schema()
    assert "requirements" in schema["properties"]
    assert "tasks" in schema["properties"]
    assert "acceptance_criteria" in schema["properties"]


def test_rollback_proposal_roundtrip():
    data = {
        "source_agent": "engineer",
        "target_agent": "pm",
        "reason": "要件に矛盾がある",
        "details": ["要件1と要件2が矛盾"],
    }
    proposal = RollbackProposal.model_validate(data)
    assert proposal.source_agent == "engineer"
    assert proposal.model_dump() == data


def test_pm_rollback_decision():
    decision = PMRollbackDecision(
        approved=True,
        reason="差し戻し承認",
        instructions=["要件を再整理"],
    )
    assert decision.approved is True
    assert len(decision.instructions) == 1


def test_approval_request_and_result():
    req = ApprovalRequest(
        approval_type="pm_output",
        summary="PM出力の承認",
        details={"requirements": ["要件1"]},
    )
    assert req.approval_type == "pm_output"

    result = ApprovalResult(approved=True)
    assert result.approved is True
    assert result.feedback == ""

    result_with_feedback = ApprovalResult(approved=False, feedback="修正して")
    assert result_with_feedback.feedback == "修正して"

    result_terminate = ApprovalResult(approved=False, terminate=True)
    assert result_terminate.terminate is True


def test_engineer_output_with_rollback_proposal():
    output = EngineerOutput(
        design_notes="設計",
        code_patches=[],
        assumptions=[],
        rollback_proposal=RollbackProposal(
            source_agent="engineer",
            target_agent="pm",
            reason="矛盾",
            details=["詳細"],
        ),
    )
    assert output.rollback_proposal is not None
    assert output.rollback_proposal.target_agent == "pm"


def test_engineer_output_without_rollback_proposal():
    output = EngineerOutput(
        design_notes="設計",
        code_patches=[],
        assumptions=[],
    )
    assert output.rollback_proposal is None


def test_reviewer_output_with_rollback_proposal():
    output = ReviewerOutput(
        review_result="FAIL",
        issues=["問題"],
        fix_instructions=["修正"],
        rollback_proposal=RollbackProposal(
            source_agent="reviewer",
            target_agent="engineer",
            reason="設計ミス",
            details=["詳細"],
        ),
    )
    assert output.rollback_proposal is not None
    assert output.rollback_proposal.source_agent == "reviewer"
