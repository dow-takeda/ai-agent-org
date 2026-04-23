from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

PERSONALITIES_DIR = Path(__file__).resolve().parent.parent / "personalities"

VALID_ROLES = ("pm", "engineer", "reviewer", "senior_engineer", "investigator", "analyst")


class Personality(BaseModel):
    id: str
    name: str
    role: str
    focus: str
    description: str
    traits: list[str]
    system_prompt_extra: str


class Tone(BaseModel):
    id: str
    name: str
    description: str
    prompt_instruction: str


def load_tones() -> list[Tone]:
    """口調一覧をYAMLから読み込む。"""
    path = PERSONALITIES_DIR / "tones.yaml"
    if not path.exists():
        msg = f"Tones file not found: {path}"
        raise FileNotFoundError(msg)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Tone(**item) for item in data]


def get_tone(tone_id: str) -> Tone:
    """指定されたIDに一致する口調を返す。"""
    tones = load_tones()
    for t in tones:
        if t.id == tone_id:
            return t
    available = [t.id for t in tones]
    msg = f"Tone '{tone_id}' not found. Available: {available}"
    raise ValueError(msg)


def load_personalities(role: str) -> list[Personality]:
    """指定された役職のパーソナリティ一覧をYAMLから読み込む。"""
    if role not in VALID_ROLES:
        msg = f"Invalid role: {role}. Must be one of {VALID_ROLES}"
        raise ValueError(msg)

    path = PERSONALITIES_DIR / f"{role}.yaml"
    if not path.exists():
        msg = f"Personality file not found: {path}"
        raise FileNotFoundError(msg)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Personality(**item) for item in data]


def get_personality(role: str, personality_id: str) -> Personality:
    """指定された役職とIDに一致するパーソナリティを返す。"""
    personalities = load_personalities(role)
    for p in personalities:
        if p.id == personality_id:
            return p
    available = [p.id for p in personalities]
    msg = f"Personality '{personality_id}' not found for role '{role}'. Available: {available}"
    raise ValueError(msg)


def list_personality_ids(role: str) -> list[str]:
    """指定された役職の利用可能なパーソナリティIDの一覧を返す。"""
    return [p.id for p in load_personalities(role)]
