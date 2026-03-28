# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent AI system: PM → Engineer → Reviewer の直列パイプラインで、既存ソースコードに対する改修を自動実行する。フレームワークなし、素のPython + Claude API。

## Commands

```bash
# セットアップ
python3 -m venv .venv && source .venv/bin/activate && pip install anthropic python-dotenv

# 実行
python -m src.main --request "改修要求" --source /path/to/target/src

# オプション
python -m src.main --request "..." --source /path --model claude-opus-4-6 --output-dir ./my-output
```

## Architecture

- `src/main.py` — CLIエントリポイント (argparse)
- `src/pipeline.py` — 3エージェントの直列実行オーケストレーション
- `src/client.py` — Anthropic API呼び出し (structured output + streaming + extended thinking)
- `src/schemas.py` — Pydantic models: `PMOutput`, `EngineerOutput`, `ReviewerOutput`
- `src/context.py` — 対象ディレクトリを走査しソースコードを結合テキスト化
- `src/logger.py` — 実行結果を `outputs/run_<timestamp>/` にJSON + summary.md保存
- `src/agents/base.py` — ベースエージェント（プロンプト読み込み + LLM呼び出し）
- `src/agents/{pm,engineer,reviewer}.py` — 各ロールのエージェント
- `prompts/{pm,engineer,reviewer}.md` — 日本語システムプロンプト（コードと分離）

## Key Design Decisions

- **Structured output**: Anthropic APIの `output_config` + Pydantic `model_json_schema()` でJSON応答を型保証
- **プロンプト分離**: `prompts/*.md` に日本語プロンプトを外出し。コード変更なしで反復改善可能
- **ログ**: 各ステップ後に即座にファイル出力。途中で失敗しても部分的な結果が残る

## Language

プロンプト・エージェント出力は日本語。コード・変数名・コミットメッセージは英語。
