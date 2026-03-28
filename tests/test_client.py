from src.client import _add_additional_properties_false


def test_add_additional_properties_to_simple_object():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    result = _add_additional_properties_false(schema)
    assert result["additionalProperties"] is False


def test_add_additional_properties_to_nested_object():
    schema = {
        "type": "object",
        "properties": {
            "inner": {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
            },
        },
    }
    result = _add_additional_properties_false(schema)
    assert result["additionalProperties"] is False
    assert result["properties"]["inner"]["additionalProperties"] is False


def test_add_additional_properties_to_defs():
    schema = {
        "type": "object",
        "properties": {},
        "$defs": {
            "Item": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            },
        },
    }
    result = _add_additional_properties_false(schema)
    assert result["$defs"]["Item"]["additionalProperties"] is False


def test_add_additional_properties_to_array_items():
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"val": {"type": "string"}},
                },
            },
        },
    }
    result = _add_additional_properties_false(schema)
    assert result["properties"]["items"]["items"]["additionalProperties"] is False
