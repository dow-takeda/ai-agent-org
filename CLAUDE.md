# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent AI system: PM → Engineer → Reviewer の双方向パイプラインで、既存ソースコードに対する改修を自動実行する。差し戻し機構・複数人議論・ユーザー承認を備える。フレームワークなし、素のPython + Claude API。

## Commands

```bash
# セットアップ
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pre-commit install    # commit/push時のチェックフック（必須・初回のみ）

# 実行
python -m src.main --request "改修要求" --source /path/to/target/src

# オプション
python -m src.main --request "..." --source /path --model claude-opus-4-6 --output-dir ./my-output
```

## Architecture

- `src/main.py` — CLIエントリポイント (argparse + CLI承認コールバック)
- `src/pipeline.py` — 改修要望パイプライン（差し戻しループ・複数人議論・ユーザー承認）
- `src/themes/` — **要望テーマのフレームワーク**。`Theme` / `RoleSlot` / `ThemeRunContext` + テーマ別実装
  - `src/themes/base.py` — データクラス定義
  - `src/themes/phases.py` — 共通フェーズヘルパ（Senior Engineer など）
  - `src/themes/modification.py` — 改修要望テーマ（既存 `pipeline.run_pipeline` に委譲）
  - `src/themes/investigation.py` — 障害調査テーマ（Senior → Investigator×2 → Reviewer）
- `src/config.py` — パイプライン設定ローダー（.envから読み込み）
- `src/client.py` — Anthropic API呼び出し (structured output + streaming + extended thinking)
- `src/schemas.py` — Pydantic models: `PMOutput`, `EngineerOutput`, `ReviewerOutput`, `InvestigationReport`, `InvestigationReviewerOutput`, `RollbackProposal`, `PMRollbackDecision`, `ApprovalRequest`, `ApprovalResult` など
- `src/personalities.py` — パーソナリティ（YAML読み込み）+ 口調（`Tone`モデル、`tones.yaml`読み込み）
- `src/context.py` — 対象ディレクトリを走査しソースコードを結合テキスト化
- `src/logger.py` — 実行結果を `outputs/run_<timestamp>/` にJSON + summary.md保存
- `src/agents/base.py` — ベースエージェント（プロンプト読み込み + LLM呼び出し + 議論メソッド + `prompt_override`）
- `src/agents/{pm,engineer,reviewer,senior_engineer,investigator}.py` — 各ロールのエージェント
- `prompts/{pm,engineer,reviewer,senior_engineer}.md` — 改修要望テーマの日本語システムプロンプト
- `prompts/pm_rollback.md` / `prompts/pm_tiebreak.md` — 差し戻し・裁定プロンプト
- `prompts/themes/investigation/*.md` — 障害調査テーマ用プロンプト
- `personalities/{pm,engineer,reviewer,senior_engineer,investigator}.yaml` — 各ロールのパーソナリティ定義
- `personalities/tones.yaml` — 口調定義（おネエ言葉、丁寧な敬語、カジュアル、武士語）
- `src/web/app.py` — FastAPI Web UI（SSEストリーミング、テーマ/パーソナリティ/口調API）
- `src/web/static/index.html` — LINE風チャットUI（テーマタブ、動的設定パネル、プロンプト編集）

## Key Design Decisions

- **Structured output**: Anthropic APIの `output_config` + Pydantic `model_json_schema()` でJSON応答を型保証
- **プロンプト分離**: `prompts/*.md` に日本語プロンプトを外出し。コード変更なしで反復改善可能
- **ログ**: 各ステップ後に即座にファイル出力。途中で失敗しても部分的な結果が残る
- **差し戻し機構**: 後工程→PM精査→承認/棄却。PM棄却時はユーザーに最終確認。ループ上限は `.env` の `MAX_ROLLBACK_ATTEMPTS`
- **複数人体制**: Engineer/Reviewer最大2人。ラウンド制議論で収束、膠着時はPMが裁定。上限は `MAX_DISCUSSION_ROUNDS`
- **ユーザー承認**: PM出力後とPM差し戻し棄却時に承認ポイント。CLIは`input()`、Webは`threading.Event`でブロック
- **承認コールバック**: `ApprovalCallback`プロトコルでCLI/Web統一。`on_approval=None`で承認スキップ
- **パーソナリティと口調の分離**: パーソナリティ（専門性・思考傾向）と口調（話し方のスタイル）は独立した概念。自由に組み合わせ可能
- **サマリ発言**: 各エージェント出力に口調付きの短いサマリを含む。チャットUIではサマリをメイン表示、詳細は折りたたみ
- **デフォルト口調**: `.env` の `DEFAULT_PM_TONE`, `DEFAULT_ENGINEER_TONE`, `DEFAULT_REVIEWER_TONE` で設定（デフォルト: `onee`）
- **デフォルトパーソナリティ**: `.env` の `DEFAULT_PM_PERSONALITY`, `DEFAULT_ENGINEER_PERSONALITY`, `DEFAULT_REVIEWER_PERSONALITY` で設定（デフォルト: なし）
- **要望テーマ**: `src/themes/` に Theme 定義を追加することで新規テーマを増やせる。第1次は「改修要望」「障害調査」の2テーマを提供。各テーマは登場役職・パイプラインフロー・出力スキーマ・ソースパス要否（`required` / `optional` / `unused`）を個別に定義する
- **プロンプト編集（UI 実行時）**: Web UI の各役職に展開される textarea で prompt を編集可能。編集結果は当該実行のみ有効で、ファイルは書き換わらない（`BaseAgent(prompt_override=...)` で注入）
- **CLI は改修要望のみ**: `--theme` フラグは提供しない。CLI 実行は従来互換

## Development Flow

ユーザーからの改修要求を受けてからマージまでの開発フローは以下の通り。**このフローを厳守すること。**

1. **要求受領**: ユーザーから要求を受け取る（文字列 or 指示書ファイルパス）。指示書の場合はファイルを読み込む。
2. **計画作成**: Planモードに入り、実装計画を作成してユーザーに承認を求める。
3. **Issue作成**: ユーザーが計画を承認したら、GitHub Issueを作成する。
4. **ブランチ作成**: featureブランチを作成する。命名規則: `feature/{issue番号}-{要約2~5単語のsnake_case}`
5. **実装**: 修正を実施する。修正後、unittestが十全であることを確認する（不足があれば追加）。
6. **ローカル検証**: unittest・リント・脆弱性チェックなど、GitHub Actionsで行うステージをローカルで実行する。問題があれば修正し再チェック。`pre-commit install` 済みなら `git commit` 時に ruff / bandit / detect-private-key 等、`git push` 時に pytest が **自動で走って失敗時は中断** されるので、これに従う。`--no-verify` によるバイパスは禁止。
7. **コミット**: 全ステージ正常終了後にコミット。コミットメッセージの冒頭に `#{issue番号}` を付与する。
8. **Push & PR作成**: GitHubへpushし、プルリクエストを作成してユーザーに報告する。
9. **レビュー対応**:
   - ユーザーがPRを**否認**した場合 → 否認内容をIssueにコメントし、ステップ5から再開。
   - ユーザーがPRを**承認**した場合 → 作業内容を総括してIssueにコメントを追加し、Issueをcloseする。

## Language

プロンプト・エージェント出力は日本語。コード・変数名・コミットメッセージは英語。
