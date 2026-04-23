from src.schemas import (
    ApprovalRequest,
    ApprovalResult,
    AuditFinding,
    AuditReviewerOutput,
    AuditStatistics,
    CodebaseAuditReport,
    CodePatch,
    EngineerOutput,
    InvestigationReport,
    InvestigationReviewerOutput,
    PMOutput,
    PMRollbackDecision,
    ReviewerOutput,
    RollbackProposal,
)


def test_investigation_report_roundtrip():
    data = {
        "summary": "調査してみたわよ〜",
        "root_cause": "ログイン処理のセッショントークン初期化漏れ",
        "hypotheses": ["仮説A", "仮説B（棄却）"],
        "evidence": ["login.pyの42行目でトークン未設定"],
        "affected_files": ["src/login.py", "src/session.py"],
        "reproduction_steps": ["ログインする"],
        "severity": "high",
        "recommended_actions": ["追加調査: セッション期限切れ処理"],
        "rollback_proposal": None,
    }
    report = InvestigationReport.model_validate(data)
    assert report.root_cause.startswith("ログイン")
    assert report.severity == "high"
    assert report.model_dump() == data


def test_investigation_reviewer_output_roundtrip():
    data = {
        "summary": "レビューしたわよ〜",
        "review_result": "PASS",
        "concerns": [],
        "missing_investigations": [],
        "rollback_proposal": None,
    }
    result = InvestigationReviewerOutput.model_validate(data)
    assert result.review_result == "PASS"
    assert result.model_dump() == data


def test_investigation_reviewer_output_fail():
    data = {
        "summary": "これは甘いわ",
        "review_result": "FAIL",
        "concerns": ["根拠が薄い"],
        "missing_investigations": ["関連モジュールの調査"],
        "rollback_proposal": None,
    }
    result = InvestigationReviewerOutput.model_validate(data)
    assert result.review_result == "FAIL"
    assert "関連モジュールの調査" in result.missing_investigations


def test_pm_output_roundtrip():
    data = {
        "summary": "まとめたわよ〜",
        "requirements": ["要件1"],
        "tasks": ["タスク1"],
        "acceptance_criteria": ["条件1"],
        "referenced_files": ["app.py"],
    }
    output = PMOutput.model_validate(data)
    assert output.requirements == ["要件1"]
    assert output.summary == "まとめたわよ〜"
    assert output.referenced_files == ["app.py"]
    assert output.model_dump() == data


def test_engineer_output_roundtrip():
    data = {
        "summary": "実装したわよ〜",
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
    output = ReviewerOutput(
        summary="問題なしよ〜", review_result="PASS", issues=[], fix_instructions=[]
    )
    assert output.review_result == "PASS"


def test_reviewer_output_fail():
    output = ReviewerOutput(
        summary="問題あるわよ〜",
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
        summary="差し戻し提案あるわよ",
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
        summary="実装したわよ〜",
        design_notes="設計",
        code_patches=[],
        assumptions=[],
    )
    assert output.rollback_proposal is None


def test_reviewer_output_with_rollback_proposal():
    output = ReviewerOutput(
        summary="差し戻すわよ",
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


def test_codebase_audit_report_roundtrip():
    data = {
        "summary": "調査したわよ〜",
        "scope": "依存ライブラリのEOLとライセンス互換性",
        "findings": [
            {
                "category": "dependency",
                "severity": "high",
                "location": "requirements.txt: numpy==1.18",
                "description": "numpy 1.18 は EOL",
                "recommendation": "numpy>=1.26 に更新",
            },
            {
                "category": "license",
                "severity": "medium",
                "location": "node_modules/foo",
                "description": "GPL-3.0 と MIT 互換性懸念",
                "recommendation": "代替ライブラリ検討",
            },
        ],
        "statistics": {
            "lines_of_code": 12000,
            "module_count": 32,
            "dependency_count": 48,
            "notes": [],
        },
        "recommended_actions": ["EOL 依存の更新", "ライセンス棚卸し"],
        "rollback_proposal": None,
    }
    report = CodebaseAuditReport.model_validate(data)
    assert report.scope.startswith("依存")
    assert len(report.findings) == 2
    assert isinstance(report.findings[0], AuditFinding)
    assert isinstance(report.statistics, AuditStatistics)
    assert report.model_dump() == data


def test_codebase_audit_report_minimal():
    """statistics 省略でも妥当なこと（任意フィールド）。"""
    report = CodebaseAuditReport(
        summary="サマリ",
        scope="スコープ",
        findings=[],
        recommended_actions=[],
    )
    assert report.statistics is None
    assert report.rollback_proposal is None


def test_audit_reviewer_output_pass():
    data = {
        "summary": "レビュー完了",
        "review_result": "PASS",
        "concerns": [],
        "missing_checks": [],
        "rollback_proposal": None,
    }
    result = AuditReviewerOutput.model_validate(data)
    assert result.review_result == "PASS"
    assert result.model_dump() == data


def test_audit_reviewer_output_fail():
    data = {
        "summary": "観点漏れあり",
        "review_result": "FAIL",
        "concerns": ["severity の付与根拠が薄い"],
        "missing_checks": ["フロント依存のCVE未確認", "LICENSE整合性未検証"],
        "rollback_proposal": None,
    }
    result = AuditReviewerOutput.model_validate(data)
    assert result.review_result == "FAIL"
    assert "LICENSE整合性未検証" in result.missing_checks


def test_audit_finding_categories():
    """category は dependency / license / security / quality のいずれか。"""
    for cat in ("dependency", "license", "security", "quality"):
        f = AuditFinding(
            category=cat,
            severity="low",
            location="x",
            description="y",
            recommendation="z",
        )
        assert f.category == cat
