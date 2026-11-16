"""Regression tests for offline schema reference handling."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from referencing.exceptions import Unresolvable

from image_clarus import schema_worker


@pytest.fixture
def endpoint():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"type":"string"}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/private-sentinel", requests
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_preflight_rejects_nested_dialect_remote_reference(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "dependencies": {"a": {"$ref": url}},
            }
        },
    }
    result = schema_worker.preflight(json.dumps(schema), timeout=10)
    assert result == {"status": "invalid_schema"}
    assert requests == []
    assert "private-sentinel" not in repr(result)


@pytest.mark.parametrize(
    "dialect,container",
    [
        ("07", lambda ref: {"definitions": {"old": {"$ref": ref}}}),
        ("07", lambda ref: {"dependencies": {"old": {"$ref": ref}}}),
        ("07", lambda ref: {"additionalItems": {"$ref": ref}}),
        ("03", lambda ref: {"extends": [{"$ref": ref}]}),
    ],
)
def test_legacy_schema_containers_are_scanned(endpoint, dialect, container):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": f"http://json-schema.org/draft-{dialect}/schema#",
                **container(url),
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_runtime_validator_never_retrieves_remote_reference(endpoint):
    url, requests = endpoint
    schema = {"type": "object", "properties": {"x": {"$ref": url}}}
    with pytest.raises(Unresolvable):
        schema_worker._validation_errors(schema, {"x": "value"})
    assert requests == []


def test_202012_inactive_dependencies_is_annotation(endpoint):
    url, requests = endpoint
    schema = {"type": "object", "dependencies": {"x": {"$ref": url}}}
    encoded = json.dumps(schema)
    assert schema_worker.preflight(encoded, timeout=10) == {"status": "ok"}
    assert schema_worker.validate(encoded, {"x": 1}, timeout=10) == {"status": "ok"}
    assert requests == []


def test_selected_config_rejects_before_provider_request(endpoint, tmp_path, caplog):
    from image_clarus.config import ConfigurationError, resolve_config

    url, requests = endpoint
    secret = "sensitive-payload-sentinel"
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "dependencies": {"a": {"$ref": url}},
                "description": secret,
            }
        },
    }
    schema_path = tmp_path / "private-schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ConfigurationError) as error:
        resolve_config(
            stages=("json",),
            discovery_paths=(),
            overrides=[
                f'providers.p.base_url="{url}"',
                'models.m.provider="p"',
                'models.m.model_id="m"',
                'stages.json.model="m"',
                f'stages.json.schema_file="{schema_path}"',
            ],
        )
    assert requests == []
    assert all(
        item not in str(error.value) + caplog.text
        for item in (secret, url, str(schema_path))
    )


def test_annotations_and_keyword_shaped_property_names_are_data(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "$ref": {"type": "string"},
            "$schema": {"type": "string"},
            "dependencies": {"type": "string"},
        },
        "examples": [{"$ref": url}],
        "default": {"$ref": url},
    }
    encoded = json.dumps(schema)
    assert schema_worker.preflight(encoded, timeout=10) == {"status": "ok"}
    assert schema_worker.validate(encoded, {"$ref": "ok"}, timeout=10) == {
        "status": "ok"
    }
    assert requests == []


@pytest.mark.parametrize(
    "keyword", ["$defs", "properties", "patternProperties", "dependentSchemas"]
)
def test_modern_schema_maps_reject_remote_refs(endpoint, keyword):
    url, requests = endpoint
    schema = {"type": "object", keyword: {"x": {"$ref": url}}}
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_local_reference_still_works():
    schema = {
        "type": "object",
        "$defs": {"s": {"type": "string"}},
        "properties": {"x": {"$ref": "#/$defs/s"}},
    }
    encoded = json.dumps(schema)
    assert schema_worker.preflight(encoded, timeout=10) == {"status": "ok"}
    assert schema_worker.validate(encoded, {"x": "ok"}, timeout=10) == {"status": "ok"}
    assert (
        schema_worker.validate(encoded, {"x": 1}, timeout=10)["status"]
        == "invalid_instance"
    )


@pytest.mark.parametrize("dialect", [None, "http://json-schema.org/draft-07/schema#"])
def test_invalid_schema_activated_from_annotation_fails_preflight(dialect):
    ref = {"$ref": "#/examples/0"}
    if dialect:
        ref["$schema"] = dialect
    schema = {"type": "object", "examples": [{"type": 123}], "properties": {"x": ref}}
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }


def test_legacy_nested_id_with_remote_reference_fails_closed(endpoint):
    url, requests = endpoint
    for child in (
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "properties": {"x": {"id": url, "$ref": "#/missing"}},
        },
    ):
        schema = {"type": "object", "properties": {"nested": child}}
        assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
            "status": "invalid_schema"
        }
    assert requests == []


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("additionalItems", {"$ref": "https://invalid.example/schema"}),
        ("extends", [{"$ref": "https://invalid.example/schema"}]),
        ("$recursiveRef", "https://invalid.example/schema"),
    ],
)
def test_inactive_modern_keywords_are_data(keyword, value):
    schema = {"type": "object", keyword: value}
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {"status": "ok"}


def test_unknown_nested_dialect_inherits_caller():
    schema = {
        "type": "object",
        "properties": {"x": {"$schema": "urn:unknown", "type": "string"}},
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {"status": "ok"}


def test_draft4_id_without_reference_is_safe():
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "id": "https://invalid.example/base",
                "type": "string",
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {"status": "ok"}


def test_draft7_reference_into_annotation_inherits_dialect(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "examples": [{"dependencies": {"x": ["y"], "y": {"$ref": url}}}],
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "$ref": "#/examples/0",
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_reference_to_same_target_under_different_dialects(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "examples": [{"dependencies": {"x": {"$ref": url}}}],
        "properties": {
            "modern": {"$ref": "#/examples/0"},
            "legacy": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "$ref": "#/examples/0",
            },
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_draft7_mixed_dependencies_scans_schema_after_array(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "dependencies": {"first": ["other"], "second": {"$ref": url}},
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_draft4_id_scope_does_not_escape_offline_registry(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "properties": {
                    "inner": {
                        "id": url,
                        "properties": {"deep": {"$ref": "#/properties/x"}},
                    }
                },
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_referenced_annotation_is_scanned(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "examples": [{"$dynamicRef": url}],
        "properties": {"x": {"$ref": "#/examples/0"}},
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_active_recursive_ref_must_resolve():
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "https://json-schema.org/draft/2019-09/schema",
                "$recursiveRef": "#/missing",
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }


def test_unknown_nested_dialect_inherits_legacy_for_dependencies(endpoint):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "properties": {
                    "y": {
                        "$schema": "urn:unknown",
                        "dependencies": {"z": {"$ref": url}},
                    }
                },
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []


def test_active_recursive_ref_local_root_is_accepted():
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "https://json-schema.org/draft/2019-09/schema",
                "$recursiveRef": "#",
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {"status": "ok"}


@pytest.mark.parametrize("keyword", ["type", "disallow"])
def test_draft3_type_schemas_reject_remote_refs(endpoint, keyword):
    url, requests = endpoint
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "$schema": "http://json-schema.org/draft-03/schema#",
                keyword: [{"$ref": url}],
            }
        },
    }
    assert schema_worker.preflight(json.dumps(schema), timeout=10) == {
        "status": "invalid_schema"
    }
    assert requests == []
