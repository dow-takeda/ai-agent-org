from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from src.agents.senior_engineer import SeniorEngineerAgent
from src.events import OnEvent, PipelineEvent
from src.schemas import (
    SeniorEngineerOutput,
)

if TYPE_CHECKING:
    from src.logger import RunLogger
    from src.themes.base import ThemeRunContext


ApprovalCallback = "Callable[[ApprovalRequest], ApprovalResult] | None"


def tprint(*args: object, **kwargs: object) -> None:
    """タイムスタンプ付きprint。"""
    ts = datetime.datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005
    print(f"[{ts}]", *args, **kwargs)


def print_usage(label: str, usage: dict) -> None:
    in_tok = usage.get("input_tokens", "?")
    out_tok = usage.get("output_tokens", "?")
    tprint(f"  {label} (入力: {in_tok}, 出力: {out_tok} トークン)")


def emit(on_event: OnEvent, event_type: str, agent: str | None = None, **data: object) -> None:
    if on_event:
        on_event(PipelineEvent(type=event_type, agent=agent, data=data))


def resolve_personality_ids(pids: list[str], role: str, count: int) -> list[str | None]:
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


def run_senior_engineer_phase(
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
    """Senior Engineer フェーズ: スケルトンから影響範囲を分析する。"""
    tprint("🔹 シニアエンジニア 影響範囲分析中...")
    emit(on_event, "agent_start", agent="senior_engineer")
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
    print_usage("完了", usage)
    emit(
        on_event,
        "agent_complete",
        agent="senior_engineer",
        output=output.model_dump(),
        usage=usage,
        personality_name=agent.personality.name if agent.personality else None,
    )
    return output


def build_source_root_note(source_path: str) -> str:
    """ソースルート情報（パス正規化ノート）を生成する。source_pathが空なら空文字列。"""
    if not source_path:
        return ""
    return (
        f"[ソースコードのルートパス]\n"
        f"ユーザーが指定したソースコードのルートは「{source_path}」です。\n"
        f"ユーザーがこのパス配下のファイルを絶対パスで言及する場合は、"
        f"ルートからの相対パスとして解釈してください。\n\n"
    )


def extract_role_override(
    ctx: ThemeRunContext,
    role_id: str,
    index: int,
) -> tuple[str | None, str | None, str | None]:
    """指定 role_id/index の override を (personality_id, tone_id, prompt_override) で返す。"""
    ov = ctx.override_for(role_id, index)
    if ov is None:
        return None, None, None
    return ov.personality_id, ov.tone_id, ov.prompt_override
