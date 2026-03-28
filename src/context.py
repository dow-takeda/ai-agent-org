from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".txt",
}

MAX_FILE_SIZE = 100_000  # bytes
TOKEN_WARNING_THRESHOLD = 150_000


def _estimate_tokens(text: str) -> int:
    """トークン数の概算（日本語混在テキスト向け）。"""
    return len(text) // 3


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def _is_source_file(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_EXTENSIONS


def load_source_context(source_path: str) -> str:
    """対象ディレクトリを走査し、ファイルツリーとソースコードを結合したテキストを返す。"""
    root = Path(source_path).resolve()
    if not root.is_dir():
        raise ValueError(f"指定されたパスはディレクトリではありません: {source_path}")

    file_paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        dirnames.sort()
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if _is_source_file(fpath) and fpath.stat().st_size <= MAX_FILE_SIZE:
                file_paths.append(fpath)

    # ファイルツリー
    tree_lines = ["=== ファイルツリー ==="]
    for fpath in file_paths:
        tree_lines.append(str(fpath.relative_to(root)))

    # ファイル内容
    content_parts = ["\n".join(tree_lines), ""]
    for fpath in file_paths:
        rel = fpath.relative_to(root)
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: S112
            continue
        content_parts.append(f"=== {rel} ===")
        content_parts.append(text)
        content_parts.append("")

    full_context = "\n".join(content_parts)

    estimated_tokens = _estimate_tokens(full_context)
    if estimated_tokens > TOKEN_WARNING_THRESHOLD:
        print(
            f"⚠ ソースコンテキストが大きすぎる可能性があります "
            f"(推定 {estimated_tokens:,} トークン)。"
            f"--source で対象ディレクトリを絞ることを検討してください。",
        )

    return full_context
