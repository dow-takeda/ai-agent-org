# ai-agent-org

Multi-agent AI system that processes code modification requests through a PM → Engineer → Reviewer pipeline using Claude API.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install   # ← 必須: commit/push時のチェックフックを自動インストール
```

`pre-commit install` は一度実行すれば済みます。これにより `.git/hooks/pre-commit` と `.git/hooks/pre-push` が設置され、以降のコミット・プッシュ時にチェックが自動で走ります。

> 📁 **venv は `.venv/` に作成してください**。push 時の pytest フックは `.venv/bin/pytest` を直接参照するため、この位置に venv がないと `git push` が失敗します。

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

1. **テーマタブ**で依頼の種類を選択（改修要望 / 障害調査）
2. **ソースパス**に対象ソースコードのディレクトリパスを入力（テーマが required の場合）
3. **⚙ エージェント設定** で役職の人数・パーソナリティ・口調を調整。必要なら各役職の**プロンプト textarea** を編集（この実行のみ有効）
4. **依頼内容**をテキスト入力
5. **▶ ボタン**で実行
6. 各エージェントの出力がチャット形式で表示されます

**`/talk`**（談話室）: エージェントと対話形式で雑談できるテスト画面。テーマ機構とは独立。

## Development

### 自動チェック（pre-commit フック）

セットアップ時に `pre-commit install` を実行済みなら、以下が **自動で強制** されます。意識的に `ruff` や `bandit` を叩く必要はありません。

| タイミング | 走るチェック | 失敗時の挙動 |
|---|---|---|
| `git commit` | ruff lint + format / bandit / detect-private-key / large-files / merge-conflict / EOF / trailing-whitespace | commit が中断される |
| `git push`   | pytest (全テスト) | push が中断される |

> ⚠ **`--no-verify` でのバイパスは禁止** です。フックが失敗する場合は原因を修正してください。

### 手動で個別に実行したい場合

```bash
# 全フックを全ファイルに対して実行
pre-commit run --all-files

# 個別コマンド（通常は不要）
pytest
ruff check src/ tests/
ruff format --check src/ tests/
bandit -r src/ -c pyproject.toml
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
