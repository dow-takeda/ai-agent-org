from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path

from src.agents.engineer import EngineerAgent
from src.agents.pm import PMAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.senior_engineer import SeniorEngineerAgent
from src.config import PipelineConfig, load_config
from src.context import load_files_content, load_source_skeleton
from src.events import OnEvent, PipelineEvent
from src.logger import RunLogger
from src.schemas import (
    ApprovalRequest,
    ApprovalResult,
    EngineerOutput,
    PMOutput,
    ReviewerOutput,
    SeniorEngineerOutput,
)

ApprovalCallback = Callable[[ApprovalRequest], ApprovalResult] | None


def _tprint(*args: object, **kwargs: object) -> None:
    """タイムスタンプ付きprint。"""
    ts = datetime.datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005
    print(f"[{ts}]", *args, **kwargs)


def _print_usage(label: str, usage: dict) -> None:
    in_tok = usage.get("input_tokens", "?")
    out_tok = usage.get("output_tokens", "?")
    _tprint(f"  {label} (入力: {in_tok}, 出力: {out_tok} トークン)")


def _emit(on_event: OnEvent, event_type: str, agent: str | None = None, **data: object) -> None:
    if on_event:
        on_event(PipelineEvent(type=event_type, agent=agent, data=data))


def _run_senior_engineer_phase(
    request: str,
    source_skeleton: str,
    model: str,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
    personality_id: str | None = None,
    tone_id: str | None = None,
    prompt_override: str | None = None,
) -> SeniorEngineerOutput:
    _tprint("🔹 シニアエンジニア 影響範囲分析中...")
    _emit(on_event, "agent_start", agent="senior_engineer")
    agent = SeniorEngineerAgent(
        model=model,
        personality_id=personality_id,
        tone_id=tone_id,
        prompt_override=prompt_override,
    )

    output, usage = agent.run(
        request=request,
        source_skeleton=source_skeleton,
    )
    step_counter[0] += 1
    logger.log_step("senior_engineer_output", step_counter[0], output, usage)
    _print_usage("完了", usage)
    _emit(
        on_event,
        "agent_complete",
        agent="senior_engineer",
        output=output.model_dump(),
        usage=usage,
        personality_name=agent.personality.name if agent.personality else None,
    )
    return output


def _run_pm_phase(
    request: str,
    senior_engineer_output: str,
    model: str,
    rollback_history: list[dict],
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
    personality_id: str | None = None,
    tone_id: str | None = None,
    prompt_override: str | None = None,
) -> PMOutput:
    _tprint("🔹 PM エージェント実行中...")
    _emit(on_event, "agent_start", agent="pm")
    pm_agent = PMAgent(
        model=model,
        personality_id=personality_id,
        tone_id=tone_id,
        prompt_override=prompt_override,
    )

    extra_context = ""
    if rollback_history:
        history_text = "\n".join(
            f"- {h.get('from', '?')}: {h.get('reason', '')}" for h in rollback_history
        )
        extra_context = f"\n\n[過去の差し戻し履歴]\n{history_text}"

    pm_output, pm_usage = pm_agent.run(
        request=request + extra_context,
        senior_engineer_output=senior_engineer_output,
    )
    step_counter[0] += 1
    logger.log_step("pm_output", step_counter[0], pm_output, pm_usage)
    _print_usage("完了", pm_usage)
    _emit(
        on_event,
        "agent_complete",
        agent="pm",
        output=pm_output.model_dump(),
        usage=pm_usage,
        personality_name=pm_agent.personality.name if pm_agent.personality else None,
    )
    return pm_output


def _handle_pm_approval(
    pm_output: PMOutput,
    request: str,
    senior_engineer_output: str,
    model: str,
    rollback_history: list[dict],
    on_event: OnEvent,
    on_approval: ApprovalCallback,
    logger: RunLogger,
    config: PipelineConfig,
    step_counter: list[int],
    personality_id: str | None = None,
    tone_id: str | None = None,
    prompt_override: str | None = None,
) -> PMOutput | None:
    """PM出力のユーザー承認。Noneを返した場合はパイプライン終了。"""
    if on_approval is None:
        return pm_output

    attempts = 0
    while attempts < config.max_rollback_attempts:
        approval_summary = "PMの要件定義が完了しました。承認しますか？"
        approval_details = pm_output.model_dump()
        _emit(
            on_event,
            "approval_request",
            approval_type="pm_output",
            summary=approval_summary,
            details=approval_details,
        )
        approval = on_approval(
            ApprovalRequest(
                approval_type="pm_output",
                summary=approval_summary,
                details=approval_details,
            )
        )
        _emit(on_event, "approval_result", approved=approval.approved)

        if approval.approved:
            return pm_output

        if approval.terminate:
            _tprint("  ユーザーの指示によりパイプラインを終了します。")
            _emit(on_event, "pipeline_terminated")
            return None

        attempts += 1
        _tprint(f"  PM出力が却下されました。再実行します... (試行 {attempts})")
        rollback_history.append({"from": "user", "reason": approval.feedback})
        pm_output = _run_pm_phase(
            request + f"\n\n[ユーザーフィードバック]\n{approval.feedback}",
            senior_engineer_output,
            model,
            rollback_history,
            on_event,
            logger,
            step_counter,
            personality_id=personality_id,
            tone_id=tone_id,
            prompt_override=prompt_override,
        )

    _tprint("  PM承認の再試行上限に到達しました。最新の出力で続行します。")
    return pm_output


def _run_single_engineer(
    pm_output_text: str,
    files_content: str,
    model: str,
    rollback_history: list[dict],
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
    personality_id: str | None = None,
    tone_id: str | None = None,
    agent_label: str = "engineer",
    prompt_override: str | None = None,
) -> tuple[EngineerOutput, dict]:
    _emit(on_event, "agent_start", agent=agent_label)
    eng_agent = EngineerAgent(
        model=model,
        personality_id=personality_id,
        tone_id=tone_id,
        prompt_override=prompt_override,
    )

    extra_context = ""
    if rollback_history:
        history_items = [h for h in rollback_history if h.get("from") in ("reviewer", "user")]
        if history_items:
            history_text = "\n".join(f"- {h.get('reason', '')}" for h in history_items)
            extra_context = f"\n\n[過去のフィードバック]\n{history_text}"

    eng_output, eng_usage = eng_agent.run(
        pm_output=pm_output_text + extra_context,
        files_content=files_content,
    )
    step_counter[0] += 1
    logger.log_step(f"{agent_label}_output", step_counter[0], eng_output, eng_usage)
    _print_usage("完了", eng_usage)
    _emit(
        on_event,
        "agent_complete",
        agent=agent_label,
        output=eng_output.model_dump(),
        usage=eng_usage,
        personality_name=eng_agent.personality.name if eng_agent.personality else None,
    )
    return eng_output, eng_usage


def _resolve_personality_ids(pids: list[str], role: str, count: int) -> list[str | None]:
    """パーソナリティIDリストをcount分に解決する。不足分はYAMLから補完。"""
    if len(pids) >= count:
        return list(pids[:count])

    from src.personalities import list_personality_ids

    all_ids = list_personality_ids(role)
    result: list[str | None] = list(pids)
    used = set(pids)
    for aid in all_ids:
        if len(result) >= count:
            break
        if aid not in used:
            result.append(aid)
            used.add(aid)
    while len(result) < count:
        result.append(None)
    return result


def _run_engineer_phase(
    pm_output: PMOutput,
    files_content: str,
    model: str,
    config: PipelineConfig,
    rollback_history: list[dict],
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
    engineer_personality_ids: list[str] | None = None,
    tone_id: str | None = None,
    engineer_count_override: int | None = None,
    engineer_prompt_overrides: list[str | None] | None = None,
) -> EngineerOutput:
    pm_output_text = pm_output.model_dump_json(indent=2)
    n = engineer_count_override if engineer_count_override is not None else config.engineer_count
    pids = _resolve_personality_ids(engineer_personality_ids or [], "engineer", n)
    prompt_overrides = list(engineer_prompt_overrides or [])
    while len(prompt_overrides) < n:
        prompt_overrides.append(None)

    if n == 1:
        eng_output, _ = _run_single_engineer(
            pm_output_text,
            files_content,
            model,
            rollback_history,
            on_event,
            logger,
            step_counter,
            personality_id=pids[0],
            tone_id=tone_id,
            prompt_override=prompt_overrides[0],
        )
        return eng_output

    # N人体制: 独立実行 → 議論 → 収束 or PM裁定
    outputs: list[EngineerOutput] = []
    for i in range(n):
        label = f"engineer_{i + 1}"
        out, _ = _run_single_engineer(
            pm_output_text,
            files_content,
            model,
            rollback_history,
            on_event,
            logger,
            step_counter,
            personality_id=pids[i],
            tone_id=tone_id,
            agent_label=label,
            prompt_override=prompt_overrides[i],
        )
        outputs.append(out)

    # 議論ラウンド
    for round_num in range(config.max_discussion_rounds):
        _emit(
            on_event,
            "discussion_round",
            agent="engineer",
            round=round_num + 1,
            total_rounds=config.max_discussion_rounds,
            agent_count=n,
        )
        _tprint(
            f"  Engineer 議論ラウンド {round_num + 1}/{config.max_discussion_rounds} ({n}人)..."
        )

        new_outputs: list[EngineerOutput] = []
        for i in range(n):
            others = "\n---\n".join(
                outputs[j].model_dump_json(indent=2) for j in range(n) if j != i
            )
            agent = EngineerAgent(
                model=model,
                personality_id=pids[i],
                tone_id=tone_id,
                prompt_override=prompt_overrides[i],
            )
            out, _ = agent.run_discussion(
                own_output=outputs[i].model_dump_json(indent=2),
                other_output=others,
                pm_output=pm_output_text,
                files_content=files_content,
            )
            new_outputs.append(out)
        outputs = new_outputs

    # 収束チェック: 全員のcode_patchesのfile_pathが一致すれば収束
    all_paths = [{p.file_path for p in out.code_patches} for out in outputs]
    if len({frozenset(s) for s in all_paths}) == 1:
        _emit(on_event, "discussion_converged", agent="engineer")
        return outputs[0]

    # PM裁定
    _emit(on_event, "pm_tiebreak", agent="pm")
    _tprint("  Engineer間の議論が収束しませんでした。PMが裁定します...")
    return _pm_tiebreak_engineer(pm_output, outputs, model, on_event, logger, step_counter)


def _pm_tiebreak_engineer(
    pm_output: PMOutput,
    outputs: list[EngineerOutput],
    model: str,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> EngineerOutput:
    outputs_text = "\n\n".join(
        f"[エンジニア{i + 1}の出力]\n{out.model_dump_json(indent=2)}"
        for i, out in enumerate(outputs)
    )
    tiebreak_request = (
        f"[PM裁定依頼]\n"
        f"{len(outputs)}人のエンジニアが議論しましたが合意に至りませんでした。\n"
        f"以下の実装案から最適なものを選択し、"
        f"エンジニアとして最終的な統合出力を生成してください。\n\n"
        f"{outputs_text}\n\n"
        f"[PMの要件]\n{pm_output.model_dump_json(indent=2)}"
    )
    from src.agents.base import PROMPTS_DIR, call_llm

    system_prompt = (PROMPTS_DIR / "pm_tiebreak.md").read_text(encoding="utf-8")
    result, usage = call_llm(
        system_prompt=system_prompt,
        user_message=tiebreak_request,
        output_model=EngineerOutput,
        model=model,
    )
    step_counter[0] += 1
    logger.log_step("pm_tiebreak_engineer", step_counter[0], result, usage)
    _print_usage("PM裁定完了", usage)
    _emit(on_event, "agent_complete", agent="pm_tiebreak", output=result.model_dump(), usage=usage)
    return result


def _run_single_reviewer(
    request: str,
    pm_output_text: str,
    eng_output_text: str,
    files_content: str,
    model: str,
    rollback_history: list[dict],
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
    personality_id: str | None = None,
    tone_id: str | None = None,
    agent_label: str = "reviewer",
    prompt_override: str | None = None,
) -> tuple[ReviewerOutput, dict]:
    _emit(on_event, "agent_start", agent=agent_label)
    rev_agent = ReviewerAgent(
        model=model,
        personality_id=personality_id,
        tone_id=tone_id,
        prompt_override=prompt_override,
    )

    rev_output, rev_usage = rev_agent.run(
        request=request,
        pm_output=pm_output_text,
        engineer_output=eng_output_text,
        files_content=files_content,
    )
    step_counter[0] += 1
    logger.log_step(f"{agent_label}_output", step_counter[0], rev_output, rev_usage)
    _print_usage("完了", rev_usage)
    _emit(
        on_event,
        "agent_complete",
        agent=agent_label,
        output=rev_output.model_dump(),
        usage=rev_usage,
        personality_name=rev_agent.personality.name if rev_agent.personality else None,
    )
    return rev_output, rev_usage


def _run_reviewer_phase(
    request: str,
    pm_output: PMOutput,
    eng_output: EngineerOutput,
    files_content: str,
    model: str,
    config: PipelineConfig,
    rollback_history: list[dict],
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
    reviewer_personality_ids: list[str] | None = None,
    tone_id: str | None = None,
    reviewer_count_override: int | None = None,
    reviewer_prompt_overrides: list[str | None] | None = None,
) -> ReviewerOutput:
    pm_output_text = pm_output.model_dump_json(indent=2)
    eng_output_text = eng_output.model_dump_json(indent=2)
    n = reviewer_count_override if reviewer_count_override is not None else config.reviewer_count
    pids = _resolve_personality_ids(reviewer_personality_ids or [], "reviewer", n)
    prompt_overrides = list(reviewer_prompt_overrides or [])
    while len(prompt_overrides) < n:
        prompt_overrides.append(None)

    if n == 1:
        rev_output, _ = _run_single_reviewer(
            request,
            pm_output_text,
            eng_output_text,
            files_content,
            model,
            rollback_history,
            on_event,
            logger,
            step_counter,
            personality_id=pids[0],
            tone_id=tone_id,
            prompt_override=prompt_overrides[0],
        )
        return rev_output

    # N人体制: 独立実行 → 議論 → 収束 or PM裁定
    outputs: list[ReviewerOutput] = []
    for i in range(n):
        label = f"reviewer_{i + 1}"
        out, _ = _run_single_reviewer(
            request,
            pm_output_text,
            eng_output_text,
            files_content,
            model,
            rollback_history,
            on_event,
            logger,
            step_counter,
            personality_id=pids[i],
            tone_id=tone_id,
            agent_label=label,
            prompt_override=prompt_overrides[i],
        )
        outputs.append(out)

    # 議論ラウンド
    for round_num in range(config.max_discussion_rounds):
        _emit(
            on_event,
            "discussion_round",
            agent="reviewer",
            round=round_num + 1,
            total_rounds=config.max_discussion_rounds,
            agent_count=n,
        )
        _tprint(
            f"  Reviewer 議論ラウンド {round_num + 1}/{config.max_discussion_rounds} ({n}人)..."
        )

        new_outputs: list[ReviewerOutput] = []
        for i in range(n):
            others = "\n---\n".join(
                outputs[j].model_dump_json(indent=2) for j in range(n) if j != i
            )
            agent = ReviewerAgent(
                model=model,
                personality_id=pids[i],
                tone_id=tone_id,
                prompt_override=prompt_overrides[i],
            )
            out, _ = agent.run_discussion(
                own_output=outputs[i].model_dump_json(indent=2),
                other_output=others,
                request=request,
                pm_output=pm_output_text,
                engineer_output=eng_output_text,
                files_content=files_content,
            )
            new_outputs.append(out)
        outputs = new_outputs

    # 収束チェック: 全員のreview_resultが一致すれば収束
    results = {out.review_result for out in outputs}
    if len(results) == 1:
        _emit(on_event, "discussion_converged", agent="reviewer")
        merged_issues: list[str] = []
        merged_fix: list[str] = []
        rollback = None
        for out in outputs:
            merged_issues.extend(i for i in out.issues if i not in merged_issues)
            merged_fix.extend(f for f in out.fix_instructions if f not in merged_fix)
            if out.rollback_proposal and not rollback:
                rollback = out.rollback_proposal
        return ReviewerOutput(
            summary=outputs[0].summary,
            review_result=outputs[0].review_result,
            issues=merged_issues,
            fix_instructions=merged_fix,
            rollback_proposal=rollback,
        )

    # PM裁定
    _emit(on_event, "pm_tiebreak", agent="pm")
    _tprint("  Reviewer間の議論が収束しませんでした。PMが裁定します...")
    return _pm_tiebreak_reviewer(pm_output, outputs, model, on_event, logger, step_counter)


def _pm_tiebreak_reviewer(
    pm_output: PMOutput,
    outputs: list[ReviewerOutput],
    model: str,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> ReviewerOutput:
    from src.agents.base import PROMPTS_DIR, call_llm

    outputs_text = "\n\n".join(
        f"[レビュワー{i + 1}の出力]\n{out.model_dump_json(indent=2)}"
        for i, out in enumerate(outputs)
    )
    tiebreak_request = (
        f"[PM裁定依頼]\n"
        f"{len(outputs)}人のレビュワーが議論しましたが合意に至りませんでした。\n"
        f"以下のレビュー結果から最適なものを選択し、"
        f"レビュワーとして最終的な統合出力を生成してください。\n\n"
        f"{outputs_text}\n\n"
        f"[PMの要件]\n{pm_output.model_dump_json(indent=2)}"
    )
    system_prompt = (PROMPTS_DIR / "pm_tiebreak.md").read_text(encoding="utf-8")
    result, usage = call_llm(
        system_prompt=system_prompt,
        user_message=tiebreak_request,
        output_model=ReviewerOutput,
        model=model,
    )
    step_counter[0] += 1
    logger.log_step("pm_tiebreak_reviewer", step_counter[0], result, usage)
    _print_usage("PM裁定完了", usage)
    _emit(on_event, "agent_complete", agent="pm_tiebreak", output=result.model_dump(), usage=usage)
    return result


def _handle_rollback(
    proposal,
    model: str,
    on_event: OnEvent,
    on_approval: ApprovalCallback,
    logger: RunLogger,
    step_counter: list[int],
) -> tuple[bool, list[str]]:
    """差し戻し提案をPMが精査し、必要に応じてユーザーに最終確認する。"""
    proposal_data = proposal.model_dump()
    _emit(on_event, "rollback_proposed", agent=proposal.source_agent, proposal=proposal_data)
    _tprint(f"  差し戻し提案: {proposal.source_agent} → {proposal.target_agent}")
    _tprint(f"  理由: {proposal.reason}")

    # PM精査
    _emit(on_event, "rollback_review_start", agent="pm")
    pm_agent = PMAgent(model=model)
    pm_decision, pm_usage = pm_agent.run_rollback_review(proposal)
    step_counter[0] += 1
    logger.log_step("pm_rollback_decision", step_counter[0], pm_decision, pm_usage)
    _print_usage("PM差し戻し精査完了", pm_usage)
    _emit(
        on_event,
        "rollback_review_complete",
        agent="pm",
        decision=pm_decision.model_dump(),
    )

    if pm_decision.approved:
        _tprint(f"  PMが差し戻しを承認しました: {pm_decision.reason}")
        return True, pm_decision.instructions

    # PM棄却 → ユーザーに最終確認
    _tprint(f"  PMが差し戻しを棄却しました: {pm_decision.reason}")
    if on_approval is not None:
        rb_summary = f"PMが差し戻しを棄却しました: {pm_decision.reason}"
        rb_details = {
            "proposal": proposal.model_dump(),
            "pm_decision": pm_decision.model_dump(),
        }
        _emit(
            on_event,
            "approval_request",
            approval_type="rollback_override",
            summary=rb_summary,
            details=rb_details,
        )
        approval = on_approval(
            ApprovalRequest(
                approval_type="rollback_override",
                summary=rb_summary,
                details=rb_details,
            )
        )
        _emit(on_event, "approval_result", approved=approval.approved)
        if approval.approved:
            _tprint("  ユーザーが差し戻しを承認しました（PMの判断を覆しました）")
            return True, [approval.feedback] if approval.feedback else []

    _tprint("  差し戻しは棄却されました。パイプラインを続行します。")
    return False, []


def run_pipeline(
    request: str,
    source_path: str,
    model: str = "claude-sonnet-4-6",
    output_dir: Path | None = None,
    on_event: OnEvent = None,
    on_approval: ApprovalCallback = None,
    config: PipelineConfig | None = None,
    pm_personality_id: str | None = None,
    engineer_personality_ids: list[str] | None = None,
    reviewer_personality_ids: list[str] | None = None,
    senior_engineer_personality_id: str | None = None,
    pm_tone_id: str | None = None,
    engineer_tone_id: str | None = None,
    reviewer_tone_id: str | None = None,
    senior_engineer_tone_id: str | None = None,
    senior_engineer_prompt_override: str | None = None,
    pm_prompt_override: str | None = None,
    engineer_prompt_overrides: list[str | None] | None = None,
    reviewer_prompt_overrides: list[str | None] | None = None,
    engineer_count_override: int | None = None,
    reviewer_count_override: int | None = None,
) -> Path:
    """Senior Engineer → PM → Engineer → Reviewer のパイプラインを実行する。

    シニアエンジニアがスケルトンから影響範囲を特定し、
    PMが要件整理、Engineer/Reviewerは対象ファイルのみ参照する。
    差し戻し・複数人議論・ユーザー承認を含む双方向フロー。
    """
    config = config or load_config()
    logger = RunLogger(output_dir)
    logger.log_input(request, source_path)

    # Resolve personality/tone defaults from config
    pm_pid = pm_personality_id or config.default_pm_personality
    eng_pids = engineer_personality_ids
    if eng_pids is None and config.default_engineer_personality:
        eng_pids = [config.default_engineer_personality]
    rev_pids = reviewer_personality_ids
    if rev_pids is None and config.default_reviewer_personality:
        rev_pids = [config.default_reviewer_personality]
    pm_tid = pm_tone_id or config.default_pm_tone
    eng_tid = engineer_tone_id or config.default_engineer_tone
    rev_tid = reviewer_tone_id or config.default_reviewer_tone
    se_pid = senior_engineer_personality_id
    se_tid = senior_engineer_tone_id or config.default_pm_tone  # fallback to PM tone

    _emit(on_event, "pipeline_start", request=request)

    # ソースルート情報をリクエストに付与（パス正規化）
    source_root_note = (
        f"[ソースコードのルートパス]\n"
        f"ユーザーが指定したソースコードのルートは「{source_path}」です。\n"
        f"ユーザーがこのパス配下のファイルを絶対パスで言及する場合は、"
        f"ルートからの相対パスとして解釈してください。\n\n"
    )
    request_with_root = source_root_note + request

    rollback_count = 0
    rollback_history: list[dict] = []
    step_counter = [0]

    # --- Phase 0: シニアエンジニア（スケルトンで影響範囲分析）---
    source_skeleton = load_source_skeleton(source_path)
    senior_output = _run_senior_engineer_phase(
        request_with_root,
        source_skeleton,
        model,
        on_event,
        logger,
        step_counter,
        personality_id=se_pid,
        tone_id=se_tid,
        prompt_override=senior_engineer_prompt_override,
    )
    senior_output_text = senior_output.model_dump_json(indent=2)

    # --- Phase 1: PM（シニアエンジニアの報告を元に要件整理）---
    pm_output = _run_pm_phase(
        request_with_root,
        senior_output_text,
        model,
        rollback_history,
        on_event,
        logger,
        step_counter,
        personality_id=pm_pid,
        tone_id=pm_tid,
        prompt_override=pm_prompt_override,
    )

    # --- ユーザー承認 ---
    pm_output = _handle_pm_approval(
        pm_output,
        request_with_root,
        senior_output_text,
        model,
        rollback_history,
        on_event,
        on_approval,
        logger,
        config,
        step_counter,
        personality_id=pm_pid,
        tone_id=pm_tid,
        prompt_override=pm_prompt_override,
    )

    if pm_output is None:
        logger.write_summary()
        _emit(on_event, "pipeline_complete")
        _tprint(f"\n詳細: {logger.run_dir}")
        return logger.run_dir

    # --- 対象ファイルのみの全文を生成 ---
    files_content = load_files_content(source_path, pm_output.referenced_files)

    # --- メインループ: Engineer → Reviewer（差し戻しあり） ---
    rev_output = None
    while rollback_count < config.max_rollback_attempts:
        # --- Phase 2: Engineer ---
        eng_output = _run_engineer_phase(
            pm_output,
            files_content,
            model,
            config,
            rollback_history,
            on_event,
            logger,
            step_counter,
            engineer_personality_ids=eng_pids,
            tone_id=eng_tid,
            engineer_count_override=engineer_count_override,
            engineer_prompt_overrides=engineer_prompt_overrides,
        )

        # Engineer差し戻し提案チェック
        if eng_output.rollback_proposal:
            should_rollback, instructions = _handle_rollback(
                eng_output.rollback_proposal,
                model,
                on_event,
                on_approval,
                logger,
                step_counter,
            )
            if should_rollback:
                rollback_count += 1
                rollback_history.append(
                    {
                        "from": "engineer",
                        "reason": eng_output.rollback_proposal.reason,
                        "instructions": instructions,
                    }
                )
                _emit(
                    on_event,
                    "rollback",
                    source="engineer",
                    target="pm",
                    attempt=rollback_count,
                )
                _tprint(f"  差し戻し実行 ({rollback_count}/{config.max_rollback_attempts})")
                pm_output = _run_pm_phase(
                    request_with_root,
                    senior_output_text,
                    model,
                    rollback_history,
                    on_event,
                    logger,
                    step_counter,
                    personality_id=pm_pid,
                    tone_id=pm_tid,
                    prompt_override=pm_prompt_override,
                )
                pm_output = _handle_pm_approval(
                    pm_output,
                    request_with_root,
                    senior_output_text,
                    model,
                    rollback_history,
                    on_event,
                    on_approval,
                    logger,
                    config,
                    step_counter,
                    personality_id=pm_pid,
                    tone_id=pm_tid,
                    prompt_override=pm_prompt_override,
                )
                if pm_output is None:
                    break
                # PM再実行時にreferenced_filesが変わる可能性があるので再生成
                files_content = load_files_content(source_path, pm_output.referenced_files)
                continue

        if pm_output is None:
            break

        # --- Phase 3: Reviewer ---
        rev_output = _run_reviewer_phase(
            request_with_root,
            pm_output,
            eng_output,
            files_content,
            model,
            config,
            rollback_history,
            on_event,
            logger,
            step_counter,
            reviewer_personality_ids=rev_pids,
            tone_id=rev_tid,
            reviewer_count_override=reviewer_count_override,
            reviewer_prompt_overrides=reviewer_prompt_overrides,
        )

        # Reviewer差し戻し提案チェック
        if rev_output.rollback_proposal:
            should_rollback, instructions = _handle_rollback(
                rev_output.rollback_proposal,
                model,
                on_event,
                on_approval,
                logger,
                step_counter,
            )
            if should_rollback:
                rollback_count += 1
                target = rev_output.rollback_proposal.target_agent
                rollback_history.append(
                    {
                        "from": "reviewer",
                        "target": target,
                        "reason": rev_output.rollback_proposal.reason,
                        "instructions": instructions,
                    }
                )
                _emit(
                    on_event,
                    "rollback",
                    source="reviewer",
                    target=target,
                    attempt=rollback_count,
                )
                _tprint(f"  差し戻し実行 ({rollback_count}/{config.max_rollback_attempts})")
                if target == "pm":
                    pm_output = _run_pm_phase(
                        request_with_root,
                        senior_output_text,
                        model,
                        rollback_history,
                        on_event,
                        logger,
                        step_counter,
                        personality_id=pm_pid,
                        tone_id=pm_tid,
                        prompt_override=pm_prompt_override,
                    )
                    pm_output = _handle_pm_approval(
                        pm_output,
                        request_with_root,
                        senior_output_text,
                        model,
                        rollback_history,
                        on_event,
                        on_approval,
                        logger,
                        config,
                        step_counter,
                        personality_id=pm_pid,
                        tone_id=pm_tid,
                        prompt_override=pm_prompt_override,
                    )
                    if pm_output is None:
                        break
                    files_content = load_files_content(source_path, pm_output.referenced_files)
                continue

        # PASS → 完了
        if rev_output.review_result == "PASS":
            break

        # FAIL（差し戻し提案なし）→ fix_instructionsでEngineer再実行
        rollback_count += 1
        rollback_history.append(
            {
                "from": "reviewer",
                "reason": "FAIL: " + "; ".join(rev_output.fix_instructions),
            }
        )
        _emit(on_event, "review_fail_retry", attempt=rollback_count)
        max_attempts = config.max_rollback_attempts
        _tprint(f"  レビューFAIL → Engineer再実行 ({rollback_count}/{max_attempts})")
        continue

    if pm_output is None:
        logger.write_summary()
        _emit(on_event, "pipeline_complete")
        _tprint(f"\n詳細: {logger.run_dir}")
        return logger.run_dir

    if rollback_count >= config.max_rollback_attempts:
        _emit(on_event, "rollback_limit_reached", count=rollback_count)
        max_att = config.max_rollback_attempts
        _tprint(f"\n⚠️ 差し戻し上限 ({max_att}) に到達。最終結果で出力します。")

    logger.write_summary()

    # パイプライン完了サマリを構築
    summary_data: dict = {
        "steps": step_counter[0],
        "output_dir": str(logger.run_dir),
    }
    if rev_output:
        summary_data["review_result"] = rev_output.review_result
        summary_data["issues"] = rev_output.issues
    _emit(on_event, "pipeline_complete", **summary_data)

    if rev_output:
        result_label = "✅ PASS" if rev_output.review_result == "PASS" else "❌ FAIL"
        _tprint(f"\n結果: {result_label}")
        if rev_output.issues:
            _tprint("指摘事項:")
            for issue in rev_output.issues:
                _tprint(f"  - {issue}")

    _tprint(f"\n詳細: {logger.run_dir}")
    return logger.run_dir
