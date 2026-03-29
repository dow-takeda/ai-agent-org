from __future__ import annotations

from src.agents.base import PROMPTS_DIR, BaseAgent
from src.schemas import PMOutput, PMRollbackDecision, RollbackProposal


class PMAgent(BaseAgent):
    prompt_file = "pm.md"
    output_model = PMOutput
    role = "pm"

    def _build_user_message(self, **kwargs: str) -> list[dict]:
        request = kwargs["request"]
        senior_engineer_output = kwargs["senior_engineer_output"]
        return [
            {"type": "text", "text": f"[改修要求]\n{request}"},
            {
                "type": "text",
                "text": f"[シニアエンジニアの調査報告]\n{senior_engineer_output}",
            },
        ]

    def run_rollback_review(self, proposal: RollbackProposal) -> tuple[PMRollbackDecision, dict]:
        """差し戻し提案を精査し、承認/棄却を判断する。"""
        from src.agents.base import call_llm

        system_prompt = (PROMPTS_DIR / "pm_rollback.md").read_text(encoding="utf-8")
        user_message = f"[差し戻し提案]\n{proposal.model_dump_json(indent=2)}"
        return call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            output_model=PMRollbackDecision,
            model=self.model,
        )
