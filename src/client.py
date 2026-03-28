from __future__ import annotations

import json
from typing import TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_client: Anthropic | None = None


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


def call_llm(
    system_prompt: str,
    user_message: str,
    output_model: type[T],
    model: str = "claude-sonnet-4-6",
) -> tuple[T, dict]:
    """LLMを呼び出し、構造化された出力とusage情報を返す。"""
    client = get_client()
    schema = _add_additional_properties_false(output_model.model_json_schema())

    with client.messages.stream(
        model=model,
        max_tokens=64000,
        thinking={"type": "enabled", "budget_tokens": 10000},
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema,
            },
        },
    ) as stream:
        response = stream.get_final_message()

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
