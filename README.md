# ai-agent-org

Multi-agent AI system that processes code modification requests through a PM → Engineer → Reviewer pipeline using Claude API.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create `.env` with your API key:

```
ANTHROPIC_API_KEY=your-api-key-here
```

## Usage

```bash
python -m src.main \
  --request "改修要求をここに記述" \
  --source /path/to/target/source/code
```

Options:

| Flag | Description | Default |
|------|-------------|---------|
| `--request` | Modification request | - |
| `--request-file` | Path to request file or directory | - |
| `--source` | Path to target source code directory | - |
| `--model` | Claude model to use | `claude-sonnet-4-6` |
| `--output-dir` | Output directory | `outputs/` |
| `--web` | Start Web UI mode | - |
| `--port` | Web server port | `8000` |

Results are saved to `outputs/run_<timestamp>/`.

## Web UI (Demo Mode)

非エンジニア向けのデモ用に、ブラウザ上でパイプラインの実行結果を確認できるWeb UIを提供しています。

```bash
# Web UIを起動
python -m src.main --web

# ポートを変更する場合
python -m src.main --web --port 3000
```

ブラウザで `http://localhost:8000` にアクセスすると、LINE風のチャットUIが表示されます。

1. **ソースパス**に対象ソースコードのディレクトリパスを入力
2. **改修要求**をテキスト入力、またはファイルをアップロード
3. **▶ ボタン**でパイプラインを実行
4. PM → Engineer → Reviewer の各エージェントの出力がチャット形式で表示されます

## Development

```bash
# Run tests
pytest

# Lint
ruff check src/ tests/

# Security scan
bandit -r src/ -c pyproject.toml

# Set up pre-commit hooks
pre-commit install
```

## Development Flow (with Claude Code)

本プロジェクトでは Claude Code を使った開発フローを採用しています。

```
1. 要求          ユーザーが改修要求を伝える（文字列 or 指示書ファイルパス）
2. 計画          Claude が Plan モードで実装計画を作成 → ユーザー承認
3. Issue 作成    承認後、GitHub Issue を作成
4. ブランチ作成   feature/{issue番号}-{snake_case要約} でブランチを切る
5. 実装          コード修正 + unittest の追加・確認
6. ローカル検証   pytest / ruff / bandit をローカル実行し全パス確認
7. コミット       メッセージ冒頭に #{issue番号} を付与してコミット
8. Push & PR     GitHub へ push し、PR を作成してユーザーに報告
9. レビュー       ユーザーが PR を確認
   - 否認 → Issue にコメントし、5 から再作業
   - 承認 → Issue に総括コメントを追加し close
```

## License

MIT
