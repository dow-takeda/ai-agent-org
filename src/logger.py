from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"


class RunLogger:
    """パイプラインの各ステップの出力をファイルに保存する。"""

    def __init__(self, output_dir: Path | None = None) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = output_dir or DEFAULT_OUTPUT_DIR
        self.run_dir = base / f"run_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._steps: list[dict] = []

    def log_input(self, request: str, source_path: str) -> None:
        data = {"request": request, "source_path": source_path}
        self._write("00_input.json", data)

    def log_step(self, step_name: str, index: int, output: BaseModel, usage: dict) -> None:
        data = {
            "step": step_name,
            "output": output.model_dump(),
            "usage": usage,
        }
        self._write(f"{index:02d}_{step_name}.json", data)
        self._steps.append(data)

    def write_summary(self) -> None:
        lines = ["# パイプライン実行結果\n"]
        for step_data in self._steps:
            name = step_data["step"]
            output = step_data["output"]
            usage = step_data["usage"]
            lines.append(f"## {name}\n")
            in_tok = usage.get("input_tokens", "?")
            out_tok = usage.get("output_tokens", "?")
            lines.append(f"トークン使用量: 入力={in_tok}, 出力={out_tok}\n")
            for key, value in output.items():
                lines.append(f"### {key}\n")
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            lines.append(f"- {json.dumps(item, ensure_ascii=False, indent=2)}\n")
                        else:
                            lines.append(f"- {item}\n")
                else:
                    lines.append(f"{value}\n")
            lines.append("")
        (self.run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    def _write(self, filename: str, data: dict) -> None:
        path = self.run_dir / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
