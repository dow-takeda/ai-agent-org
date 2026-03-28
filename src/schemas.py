from __future__ import annotations

from pydantic import BaseModel, Field


class PMOutput(BaseModel):
    requirements: list[str] = Field(description="要件一覧")
    tasks: list[str] = Field(description="実装タスク一覧")
    acceptance_criteria: list[str] = Field(description="完了条件一覧")


class CodePatch(BaseModel):
    file_path: str = Field(description="対象ファイルパス")
    patch: str = Field(description="変更内容（コード）")
    description: str = Field(description="この変更の説明")


class EngineerOutput(BaseModel):
    design_notes: str = Field(description="設計メモ")
    code_patches: list[CodePatch] = Field(description="コード変更一覧")
    assumptions: list[str] = Field(description="前提事項一覧")


class ReviewerOutput(BaseModel):
    review_result: str = Field(description="PASS または FAIL")
    issues: list[str] = Field(description="指摘事項一覧")
    fix_instructions: list[str] = Field(description="修正指示一覧")
