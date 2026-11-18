import hashlib
import importlib
import json
from types import SimpleNamespace

import httpx
import pytest

from image_clarus.artifacts import ArtifactService
from image_clarus.providers.openai_compatible import OpenAICompatible


@pytest.fixture
def context(tmp_path):
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic")
    desc = tmp_path / "synthetic.png.desc.txt"
    desc.write_bytes("é\r\n".encode())
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes(b"Extract.\n")
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"caption": {"type": "string"}},
                "required": ["caption"],
                "additionalProperties": False,
            }
        )
    )
    requests = []
    replies = ['{"caption":"café"}']

    def handler(request):
        requests.append(json.loads(request.content))
        content = replies.pop(0)
        if isinstance(content, int):
            return httpx.Response(content, json={"error": {}})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    services = SimpleNamespace(
        artifacts=ArtifactService(),
        provider_factory=lambda p, m: OpenAICompatible(p, m, transport=transport),
    )
    config = {
        "providers": {"local": {"base_url": "http://localhost/v1"}},
        "models": {"text": {"provider": "local", "model_id": "synthetic"}},
        "stages": {
            "json": {
                "model": "text",
                "prompt_file": prompt,
                "schema_file": schema,
                "reasoning_effort": None,
                "regenerate": False,
                "validation_retries": 0,
            }
        },
        "pipeline": {"missing_prerequisite": "fail"},
    }
    return SimpleNamespace(
        image=image,
        desc=desc,
        prompt=prompt,
        schema=schema,
        requests=requests,
        replies=replies,
        services=services,
        config=config,
        output=tmp_path / "synthetic.png.desc.json",
    )


def run(c):
    try:
        stage = importlib.import_module("image_clarus.stages.structure").run_structure
    except ModuleNotFoundError as exc:
        if exc.name != "image_clarus.stages.structure":
            raise
        return None
    return stage(c.image, c.config, c.services)


def test_generation_uses_exact_snapshots_and_provenance(context):
    c = context
    result = run(c)
    assert result is not None and result.status == "completed"
    value = json.loads(c.output.read_bytes())
    assert value["metadata"] == {"caption": "café"}
    assert value["format_version"] == 1
    assert value["schema_id"] == "urn:image-clarus:custom-metadata-schema"
    assert (
        value["schema_version"]
        == "custom-sha256:" + hashlib.sha256(c.schema.read_bytes()).hexdigest()
    )
    assert value["provenance"] == {
        "provider_alias": "local",
        "model_alias": "text",
        "model_id": "synthetic",
        "prompt_id": "custom",
        "prompt_sha256": hashlib.sha256(c.prompt.read_bytes()).hexdigest(),
        "description_sha256": hashlib.sha256(c.desc.read_bytes()).hexdigest(),
    }
    assert (
        c.requests[0]["messages"][1]["content"][0]["text"]
        == "Persisted description:\né\r\n"
    )
    assert c.output.read_bytes().endswith(b"\n")


def test_generation_reads_existing_description_once(context, monkeypatch):
    from pathlib import Path

    c = context
    original_open = Path.open
    reads = []

    def counting_open(path, *args, **kwargs):
        if path == c.desc:
            reads.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    assert run(c).status == "completed"
    assert len(reads) == 1


def test_missing_description_is_recovered_from_backup(context):
    c = context
    c.services.artifacts = ArtifactService("retain")
    original = c.desc.read_bytes()
    backup = c.desc.with_name(c.desc.name + ".bak")
    c.desc.rename(backup)
    assert run(c).status == "completed"
    assert c.desc.read_bytes() == original
    assert backup.read_bytes() == original


def test_existing_envelope_skips_before_inputs(context):
    c = context
    assert run(c).status == "completed"
    original = c.output.read_bytes()
    c.desc.unlink()
    c.schema.write_text("invalid")
    result = run(c)
    assert (result.status, result.reason_code) == ("skipped", "output_exists")
    assert c.output.read_bytes() == original
    assert len(c.requests) == 1


def test_retry_parse_and_schema_feedback(context):
    c = context
    c.config["stages"]["json"]["validation_retries"] = 2
    c.replies[:] = [
        '{"caption":1,"other":2}',
        '{"caption":"x","caption":"y"}',
        '{"caption":"ok"}',
    ]
    result = run(c)
    assert result.status == "completed"
    assert len(c.requests) == 3
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback == {
        "kind": "schema_validation",
        "total_errors": 2,
        "truncated": False,
        "errors": [
            {
                "instance_path": "",
                "schema_path": "/additionalProperties",
                "keyword": "additionalProperties",
            },
            {
                "instance_path": "/caption",
                "schema_path": "/properties/caption/type",
                "keyword": "type",
            },
        ],
    }
    assert json.loads(c.requests[2]["messages"][-1]["content"]) == {
        "kind": "json_parse",
        "code": "duplicate_key",
    }


@pytest.mark.parametrize(
    "policy,status,code",
    [
        ("fail", "failed", "missing_prerequisite"),
        ("skip", "skipped", "missing_prerequisite"),
    ],
)
def test_missing_description_policy(context, policy, status, code):
    c = context
    c.desc.unlink()
    c.config["pipeline"]["missing_prerequisite"] = policy
    result = run(c)
    assert result.status == status
    assert (result.error_category if status == "failed" else result.reason_code) == code
    assert not c.requests


def test_generated_envelope_is_validated_before_publish(context):
    c = context
    c.config["providers"][""] = c.config["providers"]["local"]
    c.config["models"]["text"]["provider"] = ""
    result = run(c)
    assert (result.status, result.error_category) == ("failed", "configuration")
    assert not c.output.exists()
    assert len(c.requests) == 1


@pytest.mark.parametrize(
    "payload,code",
    [
        ("```json\n{}\n```", "invalid_json"),
        ('{"caption":"x","caption":"y"}', "duplicate_key"),
        ('{"caption":NaN}', "non_finite_number"),
        ('{"caption":1e9999}', "non_finite_number"),
        ('{"caption":"\\ud800"}', "invalid_unicode"),
    ],
)
def test_parse_errors_retry_with_safe_codes(context, payload, code):
    c = context
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [payload, '{"caption":"ok"}']
    assert run(c).status == "completed"
    assert json.loads(c.requests[1]["messages"][-1]["content"]) == {
        "kind": "json_parse",
        "code": code,
    }


@pytest.mark.parametrize(
    "schema",
    [
        '{"type":"object","type":"object"}',
        '{"type":"object","$ref":"https://example.test/a"}',
        '{"type":"object","$ref":"#/$defs/missing"}',
        '{"type":"object","$dynamicRef":"#foo"}',
        '{"type":"object","properties":{"x":{"$id":"urn:nested"}}}',
        '{"type":"array"}',
        '{"type":"object","default":1e9999}',
    ],
)
def test_invalid_schemas_are_rejected_before_request(context, schema):
    context.schema.write_text(schema)
    result = run(context)
    assert (result.status, result.error_category) == ("failed", "configuration")
    assert context.requests == []


def test_local_anchor_schema_works(context):
    context.schema.write_text(
        json.dumps(
            {
                "type": "object",
                "$defs": {"entry": {"$anchor": "entry", "type": "string"}},
                "properties": {"caption": {"$ref": "#entry"}},
            }
        )
    )
    assert run(context).status == "completed"


@pytest.mark.parametrize(
    "body",
    [b"bad", b'{"format_version":1,"format_version":1}', b'{"format_version":NaN}'],
)
def test_invalid_existing_artifact_not_overwritten(context, body):
    context.output.write_bytes(body)
    result = run(context)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert context.output.read_bytes() == body
    assert not context.requests


def test_provider_failure_preserves_destination_and_backup(context):
    c = context
    c.output.write_bytes(b"old")
    backup = c.output.with_name(c.output.name + ".bak")
    backup.write_bytes(b"older")
    c.config["stages"]["json"].update(regenerate=True, validation_retries=2)
    c.replies[:] = [503]
    result = run(c)
    assert (result.status, result.error_category) == ("failed", "provider_unavailable")
    assert c.output.read_bytes() == b"old"
    assert backup.read_bytes() == b"older"
    assert len(c.requests) == 1


@pytest.mark.parametrize("retention", ["remove", "retain"])
def test_regeneration_backup_retention(context, retention):
    c = context
    c.output.write_bytes(b"old")
    backup = c.output.with_name(c.output.name + ".bak")
    backup.write_bytes(b"older")
    c.config["stages"]["json"]["regenerate"] = True
    c.services.artifacts = ArtifactService(retention)
    assert run(c).status == "completed"
    assert (
        (backup.read_bytes() == b"old")
        if retention == "retain"
        else not backup.exists()
    )


@pytest.mark.parametrize("data", [b"", b"  \n", b"\xff"])
def test_invalid_description_fails_without_provider(context, data):
    context.desc.write_bytes(data)
    result = run(context)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert not context.requests


@pytest.mark.parametrize("retries", [True, -1, 3, 1.0])
def test_invalid_retry_counts(context, retries):
    context.config["stages"]["json"]["validation_retries"] = retries
    result = run(context)
    assert (result.status, result.error_category) == ("failed", "configuration")
    assert not context.requests


def test_validation_retry_exhaustion_preserves_output(context):
    c = context
    c.output.write_bytes(b"prior")
    c.config["stages"]["json"].update(regenerate=True, validation_retries=1)
    c.replies[:] = ["{}", "{}"]
    result = run(c)
    assert (result.status, result.error_category) == ("failed", "schema_validation")
    assert c.output.read_bytes() == b"prior"
    assert len(c.requests) == 2


def test_feedback_resolves_local_refs_to_actual_escaped_schema_pointers(context):
    c = context
    schema = {
        "type": "object",
        "$defs": {
            "a/b~c": {"$anchor": "target", "type": "string"},
            "chain": {"$ref": "#target"},
        },
        "properties": {
            "z/last": {"$ref": "#/$defs/chain"},
            "a~first": {"$ref": "#/$defs/a~1b~0c"},
            "direct": {"type": "string"},
        },
    }
    c.schema.write_text(json.dumps(schema))
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({"z/last": 1, "a~first": 2, "direct": 3}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback == {
        "kind": "schema_validation",
        "total_errors": 3,
        "truncated": False,
        "errors": [
            {
                "instance_path": "/a~0first",
                "schema_path": "/$defs/a~1b~0c/type",
                "keyword": "type",
            },
            {
                "instance_path": "/direct",
                "schema_path": "/properties/direct/type",
                "keyword": "type",
            },
            {
                "instance_path": "/z~1last",
                "schema_path": "/$defs/a~1b~0c/type",
                "keyword": "type",
            },
        ],
    }
    for error in feedback["errors"]:
        node = schema
        for token in error["schema_path"].split("/")[1:]:
            node = node[token.replace("~1", "/").replace("~0", "~")]
        assert node == "string"


def test_builtin_resources(context):
    from image_clarus import resources

    c = context
    c.config["stages"]["json"].update(prompt_file=None, schema_file=None)
    c.replies[:] = [
        json.dumps(
            {
                "subjects": [],
                "objects": [],
                "actions": [],
                "setting": {"type": "", "context": ""},
                "visual_characteristics": {
                    "colors": [],
                    "composition": "",
                    "lighting": "",
                    "visual_style": "",
                },
                "keywords": [],
                "title": "",
                "caption": "",
                "tag_candidates": [],
            }
        )
    ]
    assert run(c).status == "completed"
    result = json.loads(c.output.read_bytes())
    assert result["schema_version"] == "2.0.0"
    assert result["provenance"]["prompt_id"] == "builtin:image-structure"
    assert (
        result["provenance"]["prompt_sha256"]
        == hashlib.sha256(resources.structure_prompt().read_bytes()).hexdigest()
    )
    assert (
        c.requests[0]["messages"][0]["content"].encode()
        == resources.structure_prompt().read_bytes()
    )


def test_feedback_sorted_deduplicated_and_truncated(context):
    c = context
    c.schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {f"k{i:02}": {"type": "string"} for i in range(25)},
            }
        )
    )
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({f"k{i:02}": 1 for i in reversed(range(25))}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["total_errors"] == 25
    assert feedback["truncated"] is True
    assert [e["instance_path"] for e in feedback["errors"]] == [
        f"/k{i:02}" for i in range(20)
    ]


def test_recover_existing_json_backup_and_skip(context):
    c = context
    assert run(c).status == "completed"
    original = c.output.read_bytes()
    backup = c.output.with_name(c.output.name + ".bak")
    c.output.rename(backup)
    c.desc.unlink()
    result = run(c)
    assert (result.status, result.reason_code) == ("skipped", "output_exists")
    assert c.output.read_bytes() == original
    assert not backup.exists()
    assert len(c.requests) == 1


def test_safe_write_failure_preserves_existing_json(context):
    c = context
    c.output.write_bytes(b"old")
    c.config["stages"]["json"]["regenerate"] = True

    def checkpoint(point):
        if point == "destination_replace":
            raise OSError("private path sentinel")

    c.services.artifacts = ArtifactService(checkpoint=checkpoint)
    result = run(c)
    assert (result.status, result.error_category) == ("failed", "file_io")
    assert "private path sentinel" not in result.message
    assert c.output.read_bytes() == b"old"


def test_feedback_points_inside_referenced_subschemas(context):
    c = context
    schema = {
        "type": "object",
        "$defs": {
            "entry": {
                "type": "object",
                "properties": {"inner": {"type": "string"}},
                "required": ["inner"],
            }
        },
        "properties": {"wrap": {"$ref": "#/$defs/entry"}},
    }
    c.schema.write_text(json.dumps(schema))
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({"wrap": {"inner": 3}}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback == {
        "kind": "schema_validation",
        "total_errors": 1,
        "truncated": False,
        "errors": [
            {
                "instance_path": "/wrap/inner",
                "schema_path": "/$defs/entry/properties/inner/type",
                "keyword": "type",
            }
        ],
    }


def test_feedback_resolves_direct_anchor_ref_property(context):
    c = context
    schema = {
        "type": "object",
        "$defs": {"entry": {"$anchor": "entry", "type": "string"}},
        "properties": {"caption": {"$ref": "#entry"}},
    }
    c.schema.write_text(json.dumps(schema))
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({"caption": 1}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback == {
        "kind": "schema_validation",
        "total_errors": 1,
        "truncated": False,
        "errors": [
            {
                "instance_path": "/caption",
                "schema_path": "/$defs/entry/type",
                "keyword": "type",
            }
        ],
    }


def test_feedback_distinguishes_ref_target_from_sibling_keywords(context):
    c = context
    schema = {
        "type": "object",
        "$defs": {"x": {"type": "integer"}},
        "properties": {"n": {"$ref": "#/$defs/x", "type": "string"}},
    }
    c.schema.write_text(json.dumps(schema))
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({"n": 1.5}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback == {
        "kind": "schema_validation",
        "total_errors": 2,
        "truncated": False,
        "errors": [
            {
                "instance_path": "/n",
                "schema_path": "/$defs/x/type",
                "keyword": "type",
            },
            {
                "instance_path": "/n",
                "schema_path": "/properties/n/type",
                "keyword": "type",
            },
        ],
    }


@pytest.mark.parametrize("key", ["x", "y"])
def test_feedback_identifies_direct_false_property(context, key):
    c = context
    c.schema.write_text(
        json.dumps({"type": "object", "properties": {"x": False, "y": False}})
    )
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({key: 1}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["errors"] == [
        {
            "instance_path": f"/{key}",
            "schema_path": f"/properties/{key}",
            "keyword": "None",
        }
    ]


def test_feedback_identifies_false_prefix_item(context):
    c = context
    c.schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"items": {"prefixItems": [True, False]}},
            }
        )
    )
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = ['{"items":[0,1]}', "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["errors"] == [
        {
            "instance_path": "/items/1",
            "schema_path": "/properties/items/prefixItems/1",
            "keyword": "None",
        }
    ]


def test_feedback_identifies_nested_false_in_percent_encoded_ref_target(context):
    c = context
    schema = {
        "type": "object",
        "$defs": {
            "a/b~c": {"properties": {"inner": False}},
            "via": {"$ref": "#/$defs/a~1b~0c"},
        },
        "properties": {
            "outer": {"$ref": "#/%24defs/via", "type": "object"},
        },
    }
    c.schema.write_text(json.dumps(schema))
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = ['{"outer":{"inner":1}}', "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["errors"] == [
        {
            "instance_path": "/outer/inner",
            "schema_path": "/$defs/a~1b~0c/properties/inner",
            "keyword": "None",
        }
    ]


def test_feedback_resolves_boolean_subschema_targets_behind_refs(context):
    c = context
    schema = {
        "type": "object",
        "$defs": {
            "x": False,
            "via": {"$ref": "#/$defs/x"},
            "flag": {"$anchor": "flag", "$ref": "#/$defs/x"},
        },
        "properties": {
            "a": {"$ref": "#/$defs/x"},
            "b": {"$ref": "#/$defs/via"},
            "c": {"$ref": "#flag"},
        },
    }
    c.schema.write_text(json.dumps(schema))
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [json.dumps({"a": 1, "b": 2, "c": 3}), "{}"]
    assert run(c).status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["total_errors"] == 3
    assert feedback["truncated"] is False
    assert [
        (entry["instance_path"], entry["schema_path"]) for entry in feedback["errors"]
    ] == [("/a", "/$defs/x"), ("/b", "/$defs/x"), ("/c", "/$defs/x")]
    for entry in feedback["errors"]:
        node = schema
        for token in entry["schema_path"].split("/")[1:]:
            node = node[token.replace("~1", "/").replace("~0", "~")]
        assert node is False
