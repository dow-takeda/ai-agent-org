from __future__ import annotations

from pydantic import BaseModel, Field


class SeniorEngineerOutput(BaseModel):
    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    impact_files: list[str] = Field(
        description="影響範囲のファイルパス一覧（ファイルツリーに存在する相対パス）"
    )
    analysis: str = Field(description="構造分析の説明（依存関係、影響範囲の根拠）")


class PMOutput(BaseModel):
    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    requirements: list[str] = Field(description="要件一覧")
    tasks: list[str] = Field(description="実装タスク一覧")
    acceptance_criteria: list[str] = Field(description="完了条件一覧")
    referenced_files: list[str] = Field(description="Engineer/Reviewerが参照すべきファイルパス一覧")


class CodePatch(BaseModel):
    file_path: str = Field(description="対象ファイルパス")
    patch: str = Field(description="変更内容（コード）")
    description: str = Field(description="この変更の説明")


class RollbackProposal(BaseModel):
    source_agent: str = Field(description="提案元エージェント (engineer/reviewer)")
    target_agent: str = Field(description="差し戻し先エージェント (pm/engineer)")
    reason: str = Field(description="差し戻し理由")
    details: list[str] = Field(description="具体的な問題点")


class PMRollbackDecision(BaseModel):
    approved: bool = Field(description="差し戻しを承認するか")
    reason: str = Field(description="判断理由")
    instructions: list[str] = Field(description="再実行時の指示（承認時のみ）")


class ApprovalRequest(BaseModel):
    approval_type: str = Field(description="承認タイプ: pm_output / rollback_override")
    summary: str = Field(description="承認対象の要約")
    details: dict = Field(description="承認対象の詳細データ")


class ApprovalResult(BaseModel):
    approved: bool = Field(description="承認されたか")
    feedback: str = Field(default="", description="ユーザーからのフィードバック")
    terminate: bool = Field(default=False, description="パイプラインを終了するか")


class EngineerOutput(BaseModel):
    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    design_notes: str = Field(description="設計メモ")
    code_patches: list[CodePatch] = Field(description="コード変更一覧")
    assumptions: list[str] = Field(description="前提事項一覧")
    rollback_proposal: RollbackProposal | None = Field(
        default=None, description="PMへの差し戻し提案（根本的な問題がある場合のみ）"
    )


class ReviewerOutput(BaseModel):
    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    review_result: str = Field(description="PASS または FAIL")
    issues: list[str] = Field(description="指摘事項一覧")
    fix_instructions: list[str] = Field(description="修正指示一覧")
    rollback_proposal: RollbackProposal | None = Field(
        default=None, description="上流への差し戻し提案（根本的な問題がある場合のみ）"
    )


class TalkMessage(BaseModel):
    role: str = Field(description="発言者: 'user' か 'assistant'")
    content: str = Field(description="発言内容")


class TalkResponse(BaseModel):
    reply: str = Field(description="エージェントの応答文（指定された口調・パーソナリティで）")


class InvestigationReport(BaseModel):
    """障害調査テーマで Investigator が出力する調査報告書。"""

    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    root_cause: str = Field(description="推定される根本原因")
    hypotheses: list[str] = Field(description="検討した仮説と採用/棄却の理由")
    evidence: list[str] = Field(description="根拠となるコード箇所や挙動")
    affected_files: list[str] = Field(description="関連するファイルパス一覧")
    reproduction_steps: list[str] = Field(description="再現手順")
    severity: str = Field(description="深刻度: critical / high / medium / low")
    recommended_actions: list[str] = Field(
        description="次に取るべき推奨アクション（修正実装は含めない）"
    )
    rollback_proposal: RollbackProposal | None = Field(
        default=None, description="シニアエンジニアへの差し戻し提案（調査範囲の見直しが必要な場合）"
    )


class InvestigationReviewerOutput(BaseModel):
    """障害調査テーマで Reviewer が出力するレビュー結果。"""

    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    review_result: str = Field(description="PASS または FAIL")
    concerns: list[str] = Field(description="指摘事項（仮説の飛躍・根拠不足など）")
    missing_investigations: list[str] = Field(description="追加で調査すべき観点")
    rollback_proposal: RollbackProposal | None = Field(
        default=None, description="上流（Investigator または Senior）への差し戻し提案"
    )


class AuditFinding(BaseModel):
    """コードベース調査テーマで Analyst が個別に挙げる指摘事項。"""

    category: str = Field(description="観点カテゴリ: dependency / license / security / quality")
    severity: str = Field(description="深刻度: critical / high / medium / low")
    location: str = Field(description="該当箇所（ファイルパス、設定キー、依存名など）")
    description: str = Field(description="指摘内容の説明")
    recommendation: str = Field(description="推奨対応（具体的なアクション）")


class AuditStatistics(BaseModel):
    """コードベース調査テーマの参考統計値（任意）。"""

    lines_of_code: int | None = Field(default=None, description="概算LOC")
    module_count: int | None = Field(default=None, description="モジュール（ディレクトリ）数")
    dependency_count: int | None = Field(default=None, description="依存関係の総数")
    notes: list[str] = Field(default_factory=list, description="その他の参考メトリクス・補足")


class CodebaseAuditReport(BaseModel):
    """コードベース調査テーマで Analyst が出力する調査報告書。"""

    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    scope: str = Field(description="今回の調査対象スコープ（観点・範囲・除外）")
    findings: list[AuditFinding] = Field(
        description="観点別の指摘事項一覧（依存・ライセンス・セキュリティ・品質）"
    )
    statistics: AuditStatistics | None = Field(
        default=None, description="コードベースに関する参考統計（任意）"
    )
    recommended_actions: list[str] = Field(
        description="優先順位付き推奨アクション一覧（修正実装は含めない）"
    )
    rollback_proposal: RollbackProposal | None = Field(
        default=None,
        description="シニアエンジニアへの差し戻し提案（調査範囲の見直しが必要な場合）",
    )


class AuditReviewerOutput(BaseModel):
    """コードベース調査テーマで Reviewer が出力するレビュー結果。"""

    summary: str = Field(description="サマリ発言（指定された口調で簡潔に1〜3文）")
    review_result: str = Field(description="PASS または FAIL")
    concerns: list[str] = Field(description="指摘事項（根拠不足・観点漏れなど）")
    missing_checks: list[str] = Field(
        description="追加で確認すべき観点・カテゴリ・対象（EOL確認漏れ、ライセンス未確認など）"
    )
    rollback_proposal: RollbackProposal | None = Field(
        default=None, description="上流（Analyst または Senior）への差し戻し提案"
    )
