"""Direct contracts for extracted schema utilities."""

import json

import pytest
from jsonschema import Draft202012Validator

from image_clarus.config_errors import ConfigurationError
from image_clarus.schema_feedback import _feedback
from image_clarus.schema_validation import _check_schema, _strict_json


def test_schema_validation_accepts_local_reference_and_rejects_remote(tmp_path):
    path = tmp_path / "schema.json"
    schema = {
        "type": "object",
        "$defs": {"value": {"type": "string"}},
        "properties": {"x": {"$ref": "#/$defs/value"}},
    }
    path.write_text(json.dumps(schema), encoding="utf-8")
    _check_schema(path)
    schema["properties"]["x"]["$ref"] = "https://example.invalid/schema"
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid configuration"):
        _check_schema(path)


def test_strict_json_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "schema.json"
    path.write_text('{"type":"object","type":"object"}', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid selected schema"):
        _strict_json(path)


def test_feedback_reports_referenced_constraint_pointer():
    schema = {
        "$defs": {"label": {"type": "string"}},
        "properties": {"x": {"$ref": "#/$defs/label"}},
    }
    errors = list(Draft202012Validator(schema).iter_errors({"x": 42}))
    assert _feedback(schema, errors) == {
        "kind": "schema_validation",
        "total_errors": 1,
        "truncated": False,
        "errors": [
            {
                "instance_path": "/x",
                "schema_path": "/$defs/label/type",
                "keyword": "type",
            }
        ],
    }
