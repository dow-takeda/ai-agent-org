FROM python:3.12-slim

WORKDIR /app

# 依存関係インストール
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# アプリケーションコード
COPY src/ src/
COPY prompts/ prompts/
COPY personalities/ personalities/
COPY sandbox/ sandbox/

# 出力ディレクトリ
RUN mkdir -p /workspace/outputs

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "src.main"]
