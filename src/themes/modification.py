from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.agents.engineer import EngineerAgent
from src.agents.pm import PMAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.senior_engineer import SeniorEngineerAgent
from src.pipeline import run_pipeline
from src.themes.base import RoleSlot, SourcePathMode, Theme, ThemeRunContext

if TYPE_CHECKING:
    from src.config import PipelineConfig
    from src.events import OnEvent

PROMPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "prompts"


def build_modification_theme() -> Theme:
    """改修要望テーマ定義を構築する。"""
    roles = [
        RoleSlot(
            role_id="senior_engineer",
            display_name="シニアエンジニア",
            agent_class=SeniorEngineerAgent,
            default_count=1,
            min_count=1,
            max_count=1,
            prompt_path=PROMPTS_ROOT / "senior_engineer.md",
        ),
        RoleSlot(
            role_id="pm",
            display_name="PM",
            agent_class=PMAgent,
            default_count=1,
            min_count=1,
            max_count=1,
            prompt_path=PROMPTS_ROOT / "pm.md",
        ),
        RoleSlot(
            role_id="engineer",
            display_name="エンジニア",
            agent_class=EngineerAgent,
            default_count=1,
            min_count=1,
            max_count=5,
            prompt_path=PROMPTS_ROOT / "engineer.md",
        ),
        RoleSlot(
            role_id="reviewer",
            display_name="レビュアー",
            agent_class=ReviewerAgent,
            default_count=1,
            min_count=1,
            max_count=5,
            prompt_path=PROMPTS_ROOT / "reviewer.md",
        ),
    ]

    return Theme(
        id="modification",
        name="改修要望",
        description="既存ソースコードに対する改修案件。影響分析→要件定義→実装→レビューの双方向パイプライン",
        source_path_mode=SourcePathMode.REQUIRED,
        request_label="改修要求",
        request_placeholder=(
            "改修要求を入力してください（ファイルは相対パスで指定: 例 src/context.py）"
        ),
        roles=roles,
        run=_run,
    )


def _run(
    ctx: ThemeRunContext,
    config: PipelineConfig,
    on_event: OnEvent = None,
    on_approval: object | None = None,
) -> Path:
    """改修要望テーマの実行。既存 run_pipeline() に委譲する。"""

    # ctx.role_overrides を既存 run_pipeline の引数に分解
    def _collect_overrides(role_id: str) -> tuple[list[str | None], list[str | None], str | None]:
        """指定 role_id の全 index の (personality_ids, prompt_overrides, tone_id) を返す。"""
        overrides = [o for o in ctx.role_overrides if o.role_id == role_id]
        overrides.sort(key=lambda o: o.index)
        pids: list[str | None] = [o.personality_id for o in overrides]
        prompts: list[str | None] = [o.prompt_override for o in overrides]
        # tone は先頭要素のものを代表値として使う（全員同じテーマ口調を想定）
        tone_id = overrides[0].tone_id if overrides else None
        return pids, prompts, tone_id

    se_pids, se_prompts, se_tone = _collect_overrides("senior_engineer")
    pm_pids, pm_prompts, pm_tone = _collect_overrides("pm")
    eng_pids, eng_prompts, eng_tone = _collect_overrides("engineer")
    rev_pids, rev_prompts, rev_tone = _collect_overrides("reviewer")

    # 単一ロールは最初の要素のみ使用
    se_pid = se_pids[0] if se_pids else None
    se_prompt = se_prompts[0] if se_prompts else None
    pm_pid = pm_pids[0] if pm_pids else None
    pm_prompt = pm_prompts[0] if pm_prompts else None

    # None-only list は省略して run_pipeline のデフォルト解決に任せる
    def _strip_none_only(lst: list[str | None]) -> list[str] | None:
        filtered = [x for x in lst if x]
        return filtered if filtered else None

    engineer_count = ctx.role_counts.get("engineer")
    reviewer_count = ctx.role_counts.get("reviewer")

    return run_pipeline(
        request=ctx.request,
        source_path=ctx.source_path,
        model=ctx.model,
        output_dir=ctx.output_dir,
        on_event=on_event,
        on_approval=on_approval,  # type: ignore[arg-type]
        config=config,
        pm_personality_id=pm_pid,
        engineer_personality_ids=_strip_none_only(eng_pids),
        reviewer_personality_ids=_strip_none_only(rev_pids),
        senior_engineer_personality_id=se_pid,
        pm_tone_id=pm_tone,
        engineer_tone_id=eng_tone,
        reviewer_tone_id=rev_tone,
        senior_engineer_tone_id=se_tone,
        senior_engineer_prompt_override=se_prompt,
        pm_prompt_override=pm_prompt,
        engineer_prompt_overrides=eng_prompts or None,
        reviewer_prompt_overrides=rev_prompts or None,
        engineer_count_override=engineer_count,
        reviewer_count_override=reviewer_count,
    )
