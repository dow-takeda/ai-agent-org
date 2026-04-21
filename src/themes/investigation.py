from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.agents.investigator import InvestigatorAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.senior_engineer import SeniorEngineerAgent
from src.context import load_files_content, load_source_skeleton
from src.logger import RunLogger
from src.schemas import (
    ApprovalRequest,
    InvestigationReport,
    InvestigationReviewerOutput,
)
from src.themes.base import RoleSlot, SourcePathMode, Theme, ThemeRunContext
from src.themes.phases import (
    build_source_root_note,
    emit,
    extract_role_override,
    print_usage,
    resolve_personality_ids,
    run_senior_engineer_phase,
    tprint,
)

if TYPE_CHECKING:
    from src.config import PipelineConfig
    from src.events import OnEvent


ApprovalCallback = "Callable[[ApprovalRequest], ApprovalResult] | None"

PROMPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "prompts"
INVESTIGATION_PROMPTS = PROMPTS_ROOT / "themes" / "investigation"


def build_investigation_theme() -> Theme:
    """障害調査テーマ定義を構築する。"""
    roles = [
        RoleSlot(
            role_id="senior_engineer",
            display_name="シニアエンジニア",
            agent_class=SeniorEngineerAgent,
            default_count=1,
            min_count=1,
            max_count=1,
            prompt_path=INVESTIGATION_PROMPTS / "senior_engineer.md",
        ),
        RoleSlot(
            role_id="investigator",
            display_name="調査員",
            agent_class=InvestigatorAgent,
            default_count=2,
            min_count=1,
            max_count=4,
            prompt_path=INVESTIGATION_PROMPTS / "investigator.md",
        ),
        RoleSlot(
            role_id="reviewer",
            display_name="レビュアー",
            agent_class=ReviewerAgent,
            default_count=1,
            min_count=1,
            max_count=3,
            prompt_path=INVESTIGATION_PROMPTS / "reviewer.md",
        ),
    ]

    return Theme(
        id="investigation",
        name="障害調査",
        description="障害・不具合の根本原因特定と推奨アクション提示。修正実装は行わない",
        source_path_mode=SourcePathMode.REQUIRED,
        request_label="障害の詳細",
        request_placeholder="再現手順や観察された事象を具体的に記述してください（関連ファイルは相対パス推奨）",
        roles=roles,
        run=_run,
    )


def _run(
    ctx: ThemeRunContext,
    config: PipelineConfig,
    on_event: OnEvent = None,
    on_approval: ApprovalCallback = None,
) -> Path:
    """障害調査テーマの実行。Senior → Investigator(N人議論) → Reviewer の流れ。"""
    logger = RunLogger(ctx.output_dir)
    logger.log_input(ctx.request, ctx.source_path)

    emit(on_event, "pipeline_start", request=ctx.request)

    request_with_root = build_source_root_note(ctx.source_path) + ctx.request
    step_counter = [0]

    # --- Senior Engineer: 影響範囲分析 ---
    se_pid, se_tid, se_prompt = extract_role_override(ctx, "senior_engineer", 1)
    source_skeleton = load_source_skeleton(ctx.source_path)
    senior_output = run_senior_engineer_phase(
        request_with_root,
        source_skeleton,
        ctx.model,
        on_event,
        logger,
        step_counter,
        personality_id=se_pid,
        tone_id=se_tid,
        prompt_override=se_prompt,
    )
    senior_output_text = senior_output.model_dump_json(indent=2)

    files_content = load_files_content(ctx.source_path, senior_output.impact_files)

    # --- Investigator: 調査（N人議論） ---
    investigator_count = ctx.role_counts.get("investigator", 2)
    investigator_count = max(1, min(investigator_count, 4))

    investigator_output = _run_investigator_phase(
        ctx,
        request_with_root,
        senior_output_text,
        files_content,
        investigator_count,
        config,
        on_event,
        logger,
        step_counter,
    )

    # --- ユーザー承認ポイント ---
    if on_approval is not None:
        approval_summary = "Investigator の調査結果が完了しました。承認しますか？"
        approval_details = investigator_output.model_dump()
        emit(
            on_event,
            "approval_request",
            approval_type="investigator_output",
            summary=approval_summary,
            details=approval_details,
        )
        approval = on_approval(
            ApprovalRequest(
                approval_type="investigator_output",
                summary=approval_summary,
                details=approval_details,
            )
        )
        emit(on_event, "approval_result", approved=approval.approved)
        if approval.terminate:
            tprint("  ユーザーの指示によりパイプラインを終了します。")
            emit(on_event, "pipeline_terminated")
            logger.write_summary()
            emit(on_event, "pipeline_complete")
            return logger.run_dir

    # --- Reviewer: 調査結果の妥当性検証 ---
    reviewer_count = ctx.role_counts.get("reviewer", 1)
    reviewer_count = max(1, min(reviewer_count, 3))

    reviewer_output = _run_investigation_reviewer_phase(
        ctx,
        request_with_root,
        senior_output_text,
        investigator_output,
        files_content,
        reviewer_count,
        config,
        on_event,
        logger,
        step_counter,
    )

    # --- FAIL なら Investigator 再実行（rollback 上限まで） ---
    rollback_count = 0
    while reviewer_output.review_result == "FAIL" and rollback_count < config.max_rollback_attempts:
        rollback_count += 1
        emit(on_event, "review_fail_retry", attempt=rollback_count)
        limit = config.max_rollback_attempts
        tprint(f"  レビューFAIL → Investigator 再実行 ({rollback_count}/{limit})")

        feedback_text = "[レビュアーからのフィードバック]\n"
        feedback_text += "\n".join(f"- {c}" for c in reviewer_output.concerns)
        if reviewer_output.missing_investigations:
            feedback_text += "\n\n[追加調査すべき観点]\n"
            missing = reviewer_output.missing_investigations
            feedback_text += "\n".join(f"- {m}" for m in missing)

        investigator_output = _run_investigator_phase(
            ctx,
            request_with_root + "\n\n" + feedback_text,
            senior_output_text,
            files_content,
            investigator_count,
            config,
            on_event,
            logger,
            step_counter,
        )

        reviewer_output = _run_investigation_reviewer_phase(
            ctx,
            request_with_root,
            senior_output_text,
            investigator_output,
            files_content,
            reviewer_count,
            config,
            on_event,
            logger,
            step_counter,
        )

    hit_limit = rollback_count >= config.max_rollback_attempts
    if hit_limit and reviewer_output.review_result == "FAIL":
        emit(on_event, "rollback_limit_reached", count=rollback_count)
        limit = config.max_rollback_attempts
        tprint(f"\n⚠️ 差し戻し上限 ({limit}) に到達。最終結果で出力します。")

    logger.write_summary()

    summary_data: dict = {
        "steps": step_counter[0],
        "output_dir": str(logger.run_dir),
        "review_result": reviewer_output.review_result,
        "concerns": reviewer_output.concerns,
    }
    emit(on_event, "pipeline_complete", **summary_data)

    result_label = "✅ PASS" if reviewer_output.review_result == "PASS" else "❌ FAIL"
    tprint(f"\n結果: {result_label}")
    tprint(f"詳細: {logger.run_dir}")
    return logger.run_dir


def _run_single_investigator(
    request_with_root: str,
    senior_output_text: str,
    files_content: str,
    model: str,
    personality_id: str | None,
    tone_id: str | None,
    prompt_override: str | None,
    agent_label: str,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> tuple[InvestigationReport, dict]:
    emit(on_event, "agent_start", agent=agent_label)
    agent = InvestigatorAgent(
        model=model,
        personality_id=personality_id,
        tone_id=tone_id,
        prompt_override=prompt_override,
    )
    output, usage = agent.run(
        request=request_with_root,
        senior_engineer_output=senior_output_text,
        files_content=files_content,
    )
    step_counter[0] += 1
    logger.log_step(f"{agent_label}_output", step_counter[0], output, usage)
    print_usage("完了", usage)
    emit(
        on_event,
        "agent_complete",
        agent=agent_label,
        output=output.model_dump(),
        usage=usage,
        personality_name=agent.personality.name if agent.personality else None,
    )
    return output, usage


def _run_investigator_phase(
    ctx: ThemeRunContext,
    request_with_root: str,
    senior_output_text: str,
    files_content: str,
    n: int,
    config: PipelineConfig,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> InvestigationReport:
    tprint(f"🔹 Investigator フェーズ実行中 ({n}人)...")
    # 役職ごとの personality / tone / prompt を収集
    pids: list[str | None] = []
    tones: list[str | None] = []
    prompts: list[str | None] = []
    for i in range(1, n + 1):
        pid, tid, po = extract_role_override(ctx, "investigator", i)
        pids.append(pid)
        tones.append(tid)
        prompts.append(po)
    # None の場合はパーソナリティを YAML から補完
    filled_pids = resolve_personality_ids([p for p in pids if p], "investigator", n)
    # override があるところは override を優先
    final_pids: list[str | None] = []
    fill_iter = iter(filled_pids)
    for p in pids:
        final_pids.append(p if p else next(fill_iter))

    # 単独実行
    if n == 1:
        output, _ = _run_single_investigator(
            request_with_root,
            senior_output_text,
            files_content,
            ctx.model,
            final_pids[0],
            tones[0],
            prompts[0],
            "investigator",
            on_event,
            logger,
            step_counter,
        )
        return output

    # 複数人: 独立実行 → 議論 → 収束 or Senior 裁定
    outputs: list[InvestigationReport] = []
    for i in range(n):
        out, _ = _run_single_investigator(
            request_with_root,
            senior_output_text,
            files_content,
            ctx.model,
            final_pids[i],
            tones[i],
            prompts[i],
            f"investigator_{i + 1}",
            on_event,
            logger,
            step_counter,
        )
        outputs.append(out)

    # 議論ラウンド
    for round_num in range(config.max_discussion_rounds):
        emit(
            on_event,
            "discussion_round",
            agent="investigator",
            round=round_num + 1,
            total_rounds=config.max_discussion_rounds,
            agent_count=n,
        )
        tprint(
            f"  Investigator 議論ラウンド {round_num + 1}/{config.max_discussion_rounds} ({n}人)..."
        )
        new_outputs: list[InvestigationReport] = []
        for i in range(n):
            others = "\n---\n".join(
                outputs[j].model_dump_json(indent=2) for j in range(n) if j != i
            )
            agent = InvestigatorAgent(
                model=ctx.model,
                personality_id=final_pids[i],
                tone_id=tones[i],
                prompt_override=prompts[i],
            )
            out, _ = agent.run_discussion(
                own_output=outputs[i].model_dump_json(indent=2),
                other_output=others,
                request=request_with_root,
                senior_engineer_output=senior_output_text,
                files_content=files_content,
            )
            new_outputs.append(out)
        outputs = new_outputs

    # 収束チェック: root_cause が一致すれば収束（シンプルな判定）
    causes = {out.root_cause for out in outputs}
    if len(causes) == 1:
        emit(on_event, "discussion_converged", agent="investigator")
        # 複数人の知見を統合した最終出力を1人分に集約
        merged_hypotheses: list[str] = []
        merged_evidence: list[str] = []
        merged_files: list[str] = []
        merged_repro: list[str] = []
        merged_actions: list[str] = []
        for out in outputs:
            for h in out.hypotheses:
                if h not in merged_hypotheses:
                    merged_hypotheses.append(h)
            for e in out.evidence:
                if e not in merged_evidence:
                    merged_evidence.append(e)
            for f in out.affected_files:
                if f not in merged_files:
                    merged_files.append(f)
            for r in out.reproduction_steps:
                if r not in merged_repro:
                    merged_repro.append(r)
            for a in out.recommended_actions:
                if a not in merged_actions:
                    merged_actions.append(a)
        return InvestigationReport(
            summary=outputs[0].summary,
            root_cause=outputs[0].root_cause,
            hypotheses=merged_hypotheses,
            evidence=merged_evidence,
            affected_files=merged_files,
            reproduction_steps=merged_repro,
            severity=outputs[0].severity,
            recommended_actions=merged_actions,
            rollback_proposal=next(
                (o.rollback_proposal for o in outputs if o.rollback_proposal),
                None,
            ),
        )

    # 収束せず → Senior が裁定
    emit(on_event, "senior_tiebreak", agent="senior_engineer")
    tprint("  Investigator間の議論が収束しませんでした。Senior Engineer が裁定します...")
    return _senior_tiebreak_investigator(outputs, ctx.model, on_event, logger, step_counter)


def _senior_tiebreak_investigator(
    outputs: list[InvestigationReport],
    model: str,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> InvestigationReport:
    from src.client import call_llm

    outputs_text = "\n\n".join(
        f"[Investigator {i + 1} の出力]\n{out.model_dump_json(indent=2)}"
        for i, out in enumerate(outputs)
    )
    tiebreak_request = (
        f"[裁定依頼]\n"
        f"{len(outputs)}人のInvestigatorが議論しましたが合意に至りませんでした。\n"
        f"以下の調査結果を比較検討し、最終的な統合調査報告を生成してください。\n\n"
        f"{outputs_text}"
    )
    system_prompt = (INVESTIGATION_PROMPTS / "senior_tiebreak.md").read_text(encoding="utf-8")
    result, usage = call_llm(
        system_prompt=system_prompt,
        user_message=tiebreak_request,
        output_model=InvestigationReport,
        model=model,
    )
    step_counter[0] += 1
    logger.log_step("senior_tiebreak_investigator", step_counter[0], result, usage)
    print_usage("裁定完了", usage)
    emit(
        on_event,
        "agent_complete",
        agent="senior_tiebreak",
        output=result.model_dump(),
        usage=usage,
    )
    return result


def _run_single_investigation_reviewer(
    request_with_root: str,
    senior_output_text: str,
    investigator_output_text: str,
    files_content: str,
    model: str,
    personality_id: str | None,
    tone_id: str | None,
    prompt_override: str | None,
    agent_label: str,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> tuple[InvestigationReviewerOutput, dict]:
    from src.client import call_llm

    emit(on_event, "agent_start", agent=agent_label)

    # ReviewerAgent を使うが output_model だけ差し替えたいので call_llm を直接呼ぶ
    # system_prompt はテーマ専用の reviewer.md を読む
    if prompt_override is not None:
        base_prompt = prompt_override
    else:
        base_prompt = (INVESTIGATION_PROMPTS / "reviewer.md").read_text(encoding="utf-8")

    # personality / tone の追記（BaseAgent の挙動を簡易再現）
    system_prompt = base_prompt
    if personality_id:
        from src.personalities import get_personality

        personality = get_personality("reviewer", personality_id)
        traits_text = "\n".join(f"- {t}" for t in personality.traits)
        system_prompt += (
            f"\n\n## あなたのパーソナリティ\n"
            f"名前: {personality.name}\n"
            f"こだわり: {personality.focus}\n"
            f"特徴:\n{traits_text}\n\n"
            f"{personality.system_prompt_extra}"
        )
    if tone_id:
        from src.personalities import get_tone

        tone = get_tone(tone_id)
        system_prompt += f"\n\n## 口調\n{tone.prompt_instruction}"

    user_message = (
        f"[障害の詳細]\n{request_with_root}\n\n"
        f"[シニアエンジニアの影響分析]\n{senior_output_text}\n\n"
        f"[Investigator の調査報告]\n{investigator_output_text}\n\n"
    )
    if files_content:
        user_message += f"[関連ソースコード]\n{files_content}\n"

    output, usage = call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        output_model=InvestigationReviewerOutput,
        model=model,
    )
    step_counter[0] += 1
    logger.log_step(f"{agent_label}_output", step_counter[0], output, usage)
    print_usage("完了", usage)
    emit(
        on_event,
        "agent_complete",
        agent=agent_label,
        output=output.model_dump(),
        usage=usage,
        personality_name=personality.name if personality_id else None,
    )
    return output, usage


def _run_investigation_reviewer_phase(
    ctx: ThemeRunContext,
    request_with_root: str,
    senior_output_text: str,
    investigator_output: InvestigationReport,
    files_content: str,
    n: int,
    config: PipelineConfig,
    on_event: OnEvent,
    logger: RunLogger,
    step_counter: list[int],
) -> InvestigationReviewerOutput:
    tprint(f"🔹 Reviewer フェーズ実行中 ({n}人)...")
    investigator_output_text = investigator_output.model_dump_json(indent=2)

    # 役職ごとの override を収集
    pids: list[str | None] = []
    tones: list[str | None] = []
    prompts: list[str | None] = []
    for i in range(1, n + 1):
        pid, tid, po = extract_role_override(ctx, "reviewer", i)
        pids.append(pid)
        tones.append(tid)
        prompts.append(po)
    filled_pids = resolve_personality_ids([p for p in pids if p], "reviewer", n)
    final_pids: list[str | None] = []
    fill_iter = iter(filled_pids)
    for p in pids:
        final_pids.append(p if p else next(fill_iter))

    if n == 1:
        output, _ = _run_single_investigation_reviewer(
            request_with_root,
            senior_output_text,
            investigator_output_text,
            files_content,
            ctx.model,
            final_pids[0],
            tones[0],
            prompts[0],
            "reviewer",
            on_event,
            logger,
            step_counter,
        )
        return output

    # 複数人: 独立実行のみ（議論はシンプル化のため省略。PASS/FAIL多数決で統合）
    outputs: list[InvestigationReviewerOutput] = []
    for i in range(n):
        out, _ = _run_single_investigation_reviewer(
            request_with_root,
            senior_output_text,
            investigator_output_text,
            files_content,
            ctx.model,
            final_pids[i],
            tones[i],
            prompts[i],
            f"reviewer_{i + 1}",
            on_event,
            logger,
            step_counter,
        )
        outputs.append(out)

    # 統合: 一人でもFAILならFAIL、指摘は統合
    any_fail = any(o.review_result == "FAIL" for o in outputs)
    merged_concerns: list[str] = []
    merged_missing: list[str] = []
    rollback = None
    for out in outputs:
        for c in out.concerns:
            if c not in merged_concerns:
                merged_concerns.append(c)
        for m in out.missing_investigations:
            if m not in merged_missing:
                merged_missing.append(m)
        if out.rollback_proposal and not rollback:
            rollback = out.rollback_proposal
    return InvestigationReviewerOutput(
        summary=outputs[0].summary,
        review_result="FAIL" if any_fail else "PASS",
        concerns=merged_concerns,
        missing_investigations=merged_missing,
        rollback_proposal=rollback,
    )
