from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="AIエージェント組織: PM → Engineer → Reviewer パイプライン",
    )
    parser.add_argument(
        "--request",
        required=True,
        help="改修要求（日本語テキスト）",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="対象ソースコードのディレクトリパス",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="使用するClaudeモデル (デフォルト: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="出力ディレクトリ (デフォルト: outputs/)",
    )
    args = parser.parse_args()

    from src.pipeline import run_pipeline

    output_dir = Path(args.output_dir) if args.output_dir else None
    run_pipeline(
        request=args.request,
        source_path=args.source,
        model=args.model,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
