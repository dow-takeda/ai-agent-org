from __future__ import annotations

import json
import time
from typing import TypeVar

from anthropic import Anthropic, RateLimitError
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_client: Anthropic | None = None

MAX_RETRIES = 5
INITIAL_RETRY_WAIT = 10  # seconds
MAX_RETRY_WAIT = 120  # seconds


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def _add_additional_properties_false(schema: dict) -> dict:
    """JSON Schemaの全objectに additionalProperties: false を再帰的に付与する。"""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        for prop in schema.get("properties", {}).values():
            _add_additional_properties_false(prop)
    if "items" in schema:
        _add_additional_properties_false(schema["items"])
    for def_schema in schema.get("$defs", {}).values():
        _add_additional_properties_false(def_schema)
    return schema


def _build_system_blocks(system_prompt: str) -> list[dict]:
    """システムプロンプトをcache_control付きのブロックリストに変換する。"""
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _build_message_content(user_message: str | list[dict]) -> str | list[dict]:
    """ユーザーメッセージをAPI送信用の形式に変換する。

    文字列の場合はそのまま返す。
    list[dict]の場合はcontent blocks形式としてそのまま返す。
    """
    return user_message


def call_llm(
    system_prompt: str,
    user_message: str | list[dict],
    output_model: type[T],
    model: str = "claude-sonnet-4-6",
    thinking_budget: int = 10000,
) -> tuple[T, dict]:
    """LLMを呼び出し、構造化された出力とusage情報を返す。

    Prompt Caching: システムプロンプトとcache_control付きcontent blocksをキャッシュ。
    リトライ: RateLimitError時にexponential backoffで最大5回リトライ。
    """
    client = get_client()
    schema = _add_additional_properties_false(output_model.model_json_schema())

    system_blocks = _build_system_blocks(system_prompt)
    content = _build_message_content(user_message)

    for attempt in range(MAX_RETRIES):
        try:
            with client.messages.stream(
                model=model,
                max_tokens=64000,
                thinking={"type": "enabled", "budget_tokens": thinking_budget},
                system=system_blocks,
                messages=[{"role": "user", "content": content}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": schema,
                    },
                },
            ) as stream:
                response = stream.get_final_message()
            break
        except RateLimitError:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = min(INITIAL_RETRY_WAIT * (2**attempt), MAX_RETRY_WAIT)
            print(f"  ⏳ レートリミット到達。{wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"応答が max_tokens に達して切り詰められました "
            f"(出力: {response.usage.output_tokens} トークン)。",
        )

    # テキストブロックからJSONを抽出
    text_block = next(b for b in response.content if b.type == "text")
    parsed = output_model.model_validate(json.loads(text_block.text))

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    if hasattr(response.usage, "cache_creation_input_tokens"):
        usage["cache_creation_input_tokens"] = response.usage.cache_creation_input_tokens
    if hasattr(response.usage, "cache_read_input_tokens"):
        usage["cache_read_input_tokens"] = response.usage.cache_read_input_tokens

    return parsed, usage
