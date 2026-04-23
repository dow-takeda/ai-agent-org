from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import CodebaseAuditReport


class AnalystAgent(BaseAgent):
    """コードベース調査テーマの調査員（Analyst）エージェント。

    依存・ライセンス・セキュリティ・品質といった観点別に、
    コードベース全体の健全性を調査して報告書を作成する。
    """

    prompt_file = "themes/codebase_audit/analyst.md"
    output_model = CodebaseAuditReport
    role = "analyst"

    def _build_user_message(self, **kwargs: str) -> list[dict]:
        request = kwargs["request"]
        senior_output = kwargs["senior_engineer_output"]
        files_content = kwargs.get("files_content", "")
        blocks: list[dict] = [
            {"type": "text", "text": f"[調査依頼]\n{request}"},
            {
                "type": "text",
                "text": f"[シニアエンジニアの調査スコープ]\n{senior_output}",
            },
        ]
        if files_content:
            blocks.append(
                {
                    "type": "text",
                    "text": f"[関連ソースコード]\n{files_content}",
                }
            )
        return blocks
