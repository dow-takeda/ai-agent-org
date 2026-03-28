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
| `--request` | Modification request (required) | - |
| `--source` | Path to target source code directory (required) | - |
| `--model` | Claude model to use | `claude-sonnet-4-6` |
| `--output-dir` | Output directory | `outputs/` |

Results are saved to `outputs/run_<timestamp>/`.

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

## License

MIT
