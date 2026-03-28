from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="AIエージェント組織: PM → Engineer → Reviewer パイプライン",
    )
    request_group = parser.add_mutually_exclusive_group(required=True)
    request_group.add_argument(
        "--request",
        help="改修要求（日本語テキスト）",
    )
    request_group.add_argument(
        "--request-file",
        help="改修要求を記載したファイルまたはディレクトリのパス",
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

    if args.request_file:
        request_path = Path(args.request_file)
        if not request_path.exists():
            parser.error(f"指定されたパスが見つかりません: {args.request_file}")
        if request_path.is_file():
            request = request_path.read_text(encoding="utf-8")
        else:
            files = sorted(p for p in request_path.iterdir() if p.is_file())
            if not files:
                parser.error(
                    f"ディレクトリにファイルがありません: {args.request_file}"
                )
            parts = []
            for f in files:
                parts.append(f"# {f.name}\n{f.read_text(encoding='utf-8')}")
            request = "\n\n".join(parts)
    else:
        request = args.request

    from src.pipeline import run_pipeline

    output_dir = Path(args.output_dir) if args.output_dir else None
    run_pipeline(
        request=request,
        source_path=args.source,
        model=args.model,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
