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
