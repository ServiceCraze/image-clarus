import json

import pytest
from jsonschema import Draft202012Validator

from image_clarus.schema_worker import validate


def test_worker_reports_independent_boolean_property_locations():
    schema = {"type": "object", "properties": {"a/b": False, "c~d": False}}
    result = validate(json.dumps(schema), {"a/b": 1, "c~d": 2}, timeout=5)
    assert result["status"] == "invalid_instance"
    assert result["feedback"]["errors"] == [
        {
            "instance_path": "/a~1b",
            "schema_path": "/properties/a~1b",
            "keyword": "None",
        },
        {
            "instance_path": "/c~0d",
            "schema_path": "/properties/c~0d",
            "keyword": "None",
        },
    ]


@pytest.mark.parametrize(
    "schema,instance",
    [
        ({"properties": {"x": {"anyOf": [False, {"type": "integer"}]}}}, {"x": 1}),
        ({"properties": {"x": {"anyOf": [False, {"type": "integer"}]}}}, {"x": "bad"}),
        ({"properties": {"x": {"oneOf": [False, True]}}}, {"x": 1}),
        ({"properties": {"x": {"not": False}}}, {"x": 1}),
        ({"properties": {"x": {"if": False, "then": False, "else": True}}}, {"x": 1}),
        ({"properties": {"x": {"contains": False}}}, {"x": [1, 2]}),
        ({"properties": {"x": {"items": False}}}, {"x": [1]}),
        ({"properties": {"x": {"allOf": [True, False]}}}, {"x": 1}),
    ],
)
def test_worker_preserves_draft202012_branch_validity(schema, instance):
    schema.update(
        {"type": "object", "$schema": "https://json-schema.org/draft/2020-12/schema"}
    )
    expected = Draft202012Validator(schema).is_valid(instance)
    result = validate(json.dumps(schema), instance, timeout=5)
    assert result["status"] == ("ok" if expected else "invalid_instance")


def test_allof_boolean_location_and_reference_sibling_remain_distinct():
    schema = {
        "type": "object",
        "$defs": {
            "target": False,
            "anchor": {"$anchor": "flag", "$ref": "#/%24defs/target"},
        },
        "properties": {
            "x": {"allOf": [False, {"$ref": "#flag", "type": "string"}]},
        },
    }
    result = validate(json.dumps(schema), {"x": 2}, timeout=5)
    assert result["status"] == "invalid_instance"
    assert result["feedback"]["errors"] == [
        {"instance_path": "/x", "schema_path": "/$defs/target", "keyword": "None"},
        {
            "instance_path": "/x",
            "schema_path": "/properties/x/allOf/0",
            "keyword": "None",
        },
        {
            "instance_path": "/x",
            "schema_path": "/properties/x/allOf/1/type",
            "keyword": "type",
        },
    ]


def test_boolean_location_with_nested_dialect():
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "properties": {"bad": False},
            }
        },
    }
    result = validate(json.dumps(schema), {"x": {"bad": 1}}, timeout=5)
    assert result["status"] == "invalid_instance"
    assert result["feedback"]["errors"] == [
        {
            "instance_path": "/x/bad",
            "schema_path": "/properties/x/properties/bad",
            "keyword": "None",
        },
    ]


@pytest.mark.parametrize("condition,branch", [(True, "then"), (False, "else")])
def test_conditional_false_branch_location(condition, branch):
    schema = {"type": "object", "properties": {"x": {"if": condition, branch: False}}}
    result = validate(json.dumps(schema), {"x": 1}, timeout=5)
    assert result["status"] == "invalid_instance"
    assert result["feedback"]["errors"] == [
        {
            "instance_path": "/x",
            "schema_path": f"/properties/x/{branch}",
            "keyword": "None",
        },
    ]


@pytest.mark.parametrize(
    "keyword,limit,instance", [("minContains", 2, [1]), ("maxContains", 1, [1, 2])]
)
def test_contains_count_feedback_points_to_the_actual_keyword(keyword, limit, instance):
    schema = {
        "type": "object",
        "properties": {"a": {"contains": {"type": "integer"}, keyword: limit}},
    }
    result = validate(json.dumps(schema), {"a": instance}, timeout=5)
    assert result["feedback"]["errors"] == [
        {
            "instance_path": "/a",
            "schema_path": f"/properties/a/{keyword}",
            "keyword": keyword,
        }
    ]
