from __future__ import annotations

from src.agents.base import BaseAgent
from src.schemas import InvestigationReport


class InvestigatorAgent(BaseAgent):
    """障害調査テーマの調査員エージェント。仮説立案・根本原因特定を行う。"""

    prompt_file = "themes/investigation/investigator.md"
    output_model = InvestigationReport
    role = "investigator"

    def _build_user_message(self, **kwargs: str) -> list[dict]:
        request = kwargs["request"]
        senior_output = kwargs["senior_engineer_output"]
        files_content = kwargs.get("files_content", "")
        blocks: list[dict] = [
            {"type": "text", "text": f"[障害の詳細]\n{request}"},
            {
                "type": "text",
                "text": f"[シニアエンジニアの影響分析]\n{senior_output}",
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
