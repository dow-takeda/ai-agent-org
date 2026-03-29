from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.schemas import ApprovalRequest, ApprovalResult

DOCKER_IMAGE = "ai-agent-org"
DEFAULT_SOURCE_DIR = Path(__file__).resolve().parent.parent / "sandbox" / "default_source"

# sandbox モードでコンテナに渡す環境変数キー
_SANDBOX_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "MAX_ROLLBACK_ATTEMPTS",
    "MAX_DISCUSSION_ROUNDS",
    "ENGINEER_COUNT",
    "REVIEWER_COUNT",
    "THINKING_BUDGET_TOKENS",
    "DEFAULT_PM_PERSONALITY",
    "DEFAULT_ENGINEER_PERSONALITY",
    "DEFAULT_REVIEWER_PERSONALITY",
    "DEFAULT_PM_TONE",
    "DEFAULT_ENGINEER_TONE",
    "DEFAULT_REVIEWER_TONE",
]


def cli_approval(request: ApprovalRequest) -> ApprovalResult:
    """CLI用の承認コールバック。ユーザーにinput()で承認/却下/終了を求める。"""
    print(f"\n{'=' * 60}")
    print(f"承認リクエスト: {request.summary}")
    print(json.dumps(request.details, ensure_ascii=False, indent=2))
    print(f"{'=' * 60}")
    response = input("承認(y) / 却下して再実行(n) / 終了(q): ").strip().lower()
    if response == "q":
        return ApprovalResult(approved=False, terminate=True)
    feedback = ""
    if response != "y":
        feedback = input("フィードバック（任意）: ").strip()
    return ApprovalResult(approved=(response == "y"), feedback=feedback)


def _build_docker_image() -> None:
    """Docker イメージをビルドする（キャッシュ利用で変更なしなら高速）。"""
    print(f"🐳 Docker イメージ '{DOCKER_IMAGE}' をビルド中...")
    subprocess.run(
        ["docker", "build", "-t", DOCKER_IMAGE, "."],
        check=True,
    )


def _run_sandbox(args: argparse.Namespace) -> None:
    """Docker コンテナ内でアプリを実行する。"""
    _build_docker_image()

    source_path = args.source or str(DEFAULT_SOURCE_DIR)
    output_dir = Path(args.output_dir or "outputs").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["docker", "run", "--rm"]

    # 対話モード（CLIモード時）
    if not args.web:
        cmd += ["-it"]

    # ポートマッピング（Webモード時）
    if args.web:
        cmd += ["-p", f"{args.port}:{args.port}"]

    # 環境変数
    for key in _SANDBOX_ENV_KEYS:
        val = os.getenv(key)
        if val:
            cmd += ["-e", f"{key}={val}"]

    # ボリュームマウント
    cmd += ["-v", f"{output_dir}:/workspace/outputs"]

    # ソースディレクトリ（読取専用）
    source = Path(source_path).resolve()
    cmd += ["-v", f"{source}:/workspace/source:ro"]

    # イメージ
    cmd += [DOCKER_IMAGE]

    # アプリ引数
    if args.web:
        cmd += ["--web", "--port", str(args.port)]
    cmd += ["--source", "/workspace/source"]
    if args.request:
        cmd += ["--request", args.request]
    if args.request_file:
        cmd += ["--request-file", args.request_file]
    cmd += ["--output-dir", "/workspace/outputs"]
    cmd += ["--model", args.model]

    print("🐳 サンドボックスモードで起動します（Docker）")
    sys.exit(subprocess.call(cmd))


def _is_inside_container() -> bool:
    """Docker コンテナ内で実行中かを判定する。"""
    return Path("/.dockerenv").exists()


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="AIエージェント組織: PM → Engineer → Reviewer パイプライン",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="サンドボックスモード（Docker隔離環境で実行）",
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
        help=f"対象ソースコードのディレクトリパス (デフォルト: {DEFAULT_SOURCE_DIR})",
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

    # サンドボックスモード: Docker コンテナに委譲
    if args.sandbox:
        _run_sandbox(args)
        return

    if args.web:
        import uvicorn

        from src.web.app import app

        # コンテナ内では 0.0.0.0 にバインド
        host = "0.0.0.0" if _is_inside_container() else "127.0.0.1"  # noqa: S104
        mode = "🐳 サンドボックス" if _is_inside_container() else "🌐 ホスト"
        print(f"{mode} Web UI を起動します: http://localhost:{args.port}")
        uvicorn.run(app, host=host, port=args.port)
        return

    # CLI mode: --request or --request-file and --source are required
    if not args.request and not args.request_file:
        parser.error(
            "--request または --request-file のいずれかを指定してください（--web モード以外）"
        )
    if not args.source:
        args.source = str(DEFAULT_SOURCE_DIR)

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
