from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.schemas import ApprovalRequest, ApprovalResult


def cli_approval(request: ApprovalRequest) -> ApprovalResult:
    """CLI用の承認コールバック。ユーザーにinput()で承認/却下を求める。"""
    print(f"\n{'=' * 60}")
    print(f"承認リクエスト: {request.summary}")
    print(json.dumps(request.details, ensure_ascii=False, indent=2))
    print(f"{'=' * 60}")
    response = input("承認しますか？ (y/n): ").strip().lower()
    feedback = ""
    if response != "y":
        feedback = input("フィードバック（任意）: ").strip()
    return ApprovalResult(approved=(response == "y"), feedback=feedback)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="AIエージェント組織: PM → Engineer → Reviewer パイプライン",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Web UIモードでサーバーを起動",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Webサーバーのポート番号 (デフォルト: 8000)",
    )
    request_group = parser.add_mutually_exclusive_group(required=False)
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
        default=None,
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

    if args.web:
        import uvicorn

        from src.web.app import app

        print(f"🌐 Web UI を起動します: http://localhost:{args.port}")
        uvicorn.run(app, host="127.0.0.1", port=args.port)  # noqa: S104
        return

    # CLI mode: --request or --request-file and --source are required
    if not args.request and not args.request_file:
        parser.error(
            "--request または --request-file のいずれかを指定してください（--web モード以外）"
        )
    if not args.source:
        parser.error("--source を指定してください（--web モード以外）")

    if args.request_file:
        request_path = Path(args.request_file)
        if not request_path.exists():
            parser.error(f"指定されたパスが見つかりません: {args.request_file}")
        if request_path.is_file():
            request = request_path.read_text(encoding="utf-8")
        else:
            files = sorted(p for p in request_path.iterdir() if p.is_file())
            if not files:
                parser.error(f"ディレクトリにファイルがありません: {args.request_file}")
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
        on_approval=cli_approval,
    )


if __name__ == "__main__":
    main()
