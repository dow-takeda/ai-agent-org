from __future__ import annotations

from pathlib import Path

from src.agents.engineer import EngineerAgent
from src.agents.pm import PMAgent
from src.agents.reviewer import ReviewerAgent
from src.context import load_source_context
from src.logger import RunLogger


def _print_usage(label: str, usage: dict) -> None:
    in_tok = usage.get("input_tokens", "?")
    out_tok = usage.get("output_tokens", "?")
    print(f"  {label} (入力: {in_tok}, 出力: {out_tok} トークン)")


def run_pipeline(
    request: str,
    source_path: str,
    model: str = "claude-sonnet-4-6",
    output_dir: Path | None = None,
) -> Path:
    """PM → Engineer → Reviewer のパイプラインを実行し、ログディレクトリのパスを返す。"""
    source_context = load_source_context(source_path)
    logger = RunLogger(output_dir)
    logger.log_input(request, source_path)

    print("🔹 PM エージェント実行中...")
    pm_agent = PMAgent(model=model)
    pm_output, pm_usage = pm_agent.run(request=request, source_context=source_context)
    logger.log_step("pm_output", 1, pm_output, pm_usage)
    _print_usage("完了", pm_usage)

    pm_output_text = pm_output.model_dump_json(indent=2)

    print("🔹 Engineer エージェント実行中...")
    eng_agent = EngineerAgent(model=model)
    eng_output, eng_usage = eng_agent.run(
        pm_output=pm_output_text,
        source_context=source_context,
    )
    logger.log_step("engineer_output", 2, eng_output, eng_usage)
    _print_usage("完了", eng_usage)

    eng_output_text = eng_output.model_dump_json(indent=2)

    print("🔹 Reviewer エージェント実行中...")
    rev_agent = ReviewerAgent(model=model)
    rev_output, rev_usage = rev_agent.run(
        request=request,
        pm_output=pm_output_text,
        engineer_output=eng_output_text,
        source_context=source_context,
    )
    logger.log_step("reviewer_output", 3, rev_output, rev_usage)
    _print_usage("完了", rev_usage)

    logger.write_summary()

    result_label = "✅ PASS" if rev_output.review_result == "PASS" else "❌ FAIL"
    print(f"\n結果: {result_label}")
    if rev_output.issues:
        print("指摘事項:")
        for issue in rev_output.issues:
            print(f"  - {issue}")

    print(f"\n詳細: {logger.run_dir}")
    return logger.run_dir
