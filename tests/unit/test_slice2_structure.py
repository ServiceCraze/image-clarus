"""Slice 2 B2: Extended JSON generation and packaged resources — focused tests."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from image_clarus import resources
from image_clarus.artifacts import ArtifactService
from image_clarus.providers.openai_compatible import OpenAICompatible


@pytest.fixture
def slice2_context(tmp_path):
    """Context with Slice 2 built-in resources and synthetic provider."""
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic")
    desc = tmp_path / "synthetic.png.desc.txt"
    desc.write_bytes(b"A red bell pepper rests on a white plate.")
    requests = []
    replies = []
    on_request = []

    def handler(request):
        requests.append(json.loads(request.content))
        for callback in on_request:
            callback()
        content = (
            replies.pop(0)
            if replies
            else '{"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[],"title":"","caption":"","tag_candidates":[]}'
        )
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

    import httpx

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
                "prompt_file": None,
                "schema_file": None,
                "reasoning_effort": None,
                "regenerate": False,
                "validation_retries": 0,
                "preferred_categories": [],
            }
        },
        "pipeline": {"missing_prerequisite": "fail"},
    }
    return SimpleNamespace(
        image=image,
        desc=desc,
        requests=requests,
        replies=replies,
        on_request=on_request,
        services=services,
        config=config,
        output=tmp_path / "synthetic.png.desc.json",
    )


def run_structure(c):
    import importlib

    try:
        stage = importlib.import_module("image_clarus.stages.structure").run_structure
    except ModuleNotFoundError as exc:
        if exc.name != "image_clarus.stages.structure":
            raise
        return None
    return stage(c.image, c.config, c.services)


# ─── Schema packaging tests ──────────────────────────────────────────────────


def test_builtin_schema_v1_resource_exists():
    """The v1 historical schema resource is available and matches A2's recorded hash."""
    data = resources.structure_schema_v1().read_bytes()
    assert (
        data
        == (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "image-structure-v1.schema.json"
        ).read_bytes()
    )
    assert (
        hashlib.sha256(data).hexdigest()
        == "9d90dd0aa3722535fe4f79eb1770b50900dcfe61ce376e4ce54fee03b43877f0"
    )
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    assert not data.startswith(b"\xef\xbb\xbf")


def test_builtin_schema_v1_installed_wheel_matches_source(tmp_path):
    """The v1 schema is correctly packaged in the installed wheel."""
    import os
    import subprocess
    import sys

    ROOT = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    env = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(env)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--no-deps",
            "--python",
            str(env / "bin/python"),
            str(next(dist.glob("*.whl"))),
        ],
        check=True,
        capture_output=True,
    )
    env_os = os.environ.copy()
    env_os.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(env / "bin/python"),
            "-c",
            "from image_clarus import resources; import sys; sys.stdout.buffer.write(resources.structure_schema_v1().read_bytes())",
        ],
        cwd=tmp_path,
        env=env_os,
        capture_output=True,
        check=True,
    )
    assert (
        result.stdout
        == (ROOT / "schemas" / "image-structure-v1.schema.json").read_bytes()
    )
    assert (
        hashlib.sha256(result.stdout).hexdigest()
        == "9d90dd0aa3722535fe4f79eb1770b50900dcfe61ce376e4ce54fee03b43877f0"
    )


def test_canonical_schema_is_2_0_0():
    """The canonical schema resource has been evolved to 2.0.0."""
    data = resources.structure_schema().read_bytes()
    schema = json.loads(data)
    assert schema["$id"] == "urn:image-clarus:metadata-schema:2.0.0"
    assert "title" in schema["required"]
    assert "caption" in schema["required"]
    assert "tag_candidates" in schema["required"]


def test_canonical_prompt_is_valid_utf8_text():
    """The built-in prompt is usable without freezing its wording."""
    assert resources.structure_prompt().read_bytes().decode("utf-8").strip()


# ─── New schema field validation tests ───────────────────────────────────────


def test_new_builtin_payload_requires_title_caption_tag_candidates():
    """Built-in 2.0.0 payload requires the three new fields."""
    schema_bytes = resources.structure_schema().read_bytes()
    schema = json.loads(schema_bytes)
    validator = Draft202012Validator(schema)

    valid_payload = {
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
        "title": "Red bell pepper on a plate",
        "caption": "A red bell pepper rests on a white plate.",
        "tag_candidates": [
            ["food", "bell pepper"],
            ["food", "pepper"],
            ["color", "red"],
            ["plate"],
        ],
    }
    assert validator.is_valid(valid_payload)

    # Missing title
    missing_title = {k: v for k, v in valid_payload.items() if k != "title"}
    assert not validator.is_valid(missing_title)

    # Missing caption
    missing_caption = {k: v for k, v in valid_payload.items() if k != "caption"}
    assert not validator.is_valid(missing_caption)

    # Missing tag_candidates
    missing_candidates = {
        k: v for k, v in valid_payload.items() if k != "tag_candidates"
    }
    assert not validator.is_valid(missing_candidates)


def test_new_fields_accept_empty_values():
    """Empty string and empty array are valid for new fields when unsupported."""
    schema_bytes = resources.structure_schema().read_bytes()
    schema = json.loads(schema_bytes)
    validator = Draft202012Validator(schema)

    payload = {
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
    assert validator.is_valid(payload)


def test_tag_candidate_segment_validation():
    """Tag segments reject leading/trailing whitespace, slash, pipe, C0/C1 controls."""
    schema_bytes = resources.structure_schema().read_bytes()
    schema = json.loads(schema_bytes)
    validator = Draft202012Validator(schema)

    base = {
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
        "title": "t",
        "caption": "c",
    }

    # Valid segment
    valid = {**base, "tag_candidates": [["food", "bell pepper"]]}
    assert validator.is_valid(valid)

    # Leading whitespace
    invalid_ws = {**base, "tag_candidates": [[" food", "bell pepper"]]}
    assert not validator.is_valid(invalid_ws)

    # Trailing whitespace
    invalid_ws2 = {**base, "tag_candidates": [["food", "bell pepper "]]}
    assert not validator.is_valid(invalid_ws2)

    # Slash in segment
    invalid_slash = {**base, "tag_candidates": [["food/bell", "pepper"]]}
    assert not validator.is_valid(invalid_slash)

    # Pipe in segment
    invalid_pipe = {**base, "tag_candidates": [["food|bell", "pepper"]]}
    assert not validator.is_valid(invalid_pipe)

    # C0 control
    invalid_c0 = {**base, "tag_candidates": [["food\x00bell", "pepper"]]}
    assert not validator.is_valid(invalid_c0)

    # C1 control
    invalid_c1 = {**base, "tag_candidates": [["food\x80bell", "pepper"]]}
    assert not validator.is_valid(invalid_c1)

    # DEL
    invalid_del = {**base, "tag_candidates": [["food\x7fbell", "pepper"]]}
    assert not validator.is_valid(invalid_del)


def test_tag_candidate_duplicate_paths_rejected():
    """Exact duplicate paths are rejected by uniqueItems."""
    schema_bytes = resources.structure_schema().read_bytes()
    schema = json.loads(schema_bytes)
    validator = Draft202012Validator(schema)

    payload = {
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
        "title": "t",
        "caption": "c",
        "tag_candidates": [["food", "bell pepper"], ["food", "bell pepper"]],
    }
    assert not validator.is_valid(payload)

    # Case variants are distinct
    case_variant = {
        **payload,
        "tag_candidates": [["food", "bell pepper"], ["food", "Bell Pepper"]],
    }
    assert validator.is_valid(case_variant)


# ─── Category guidance tests ─────────────────────────────────────────────────


def test_category_guidance_added_as_third_user_part(slice2_context):
    """Non-empty preferred categories are added as third user message part."""
    c = slice2_context
    c.config["stages"]["json"]["preferred_categories"] = ["food", "color"]
    c.replies[:] = [
        json.dumps(
            {
                "subjects": ["red bell pepper"],
                "objects": ["white plate"],
                "actions": [],
                "setting": {"type": "", "context": ""},
                "visual_characteristics": {
                    "colors": ["red", "white"],
                    "composition": "",
                    "lighting": "",
                    "visual_style": "",
                },
                "keywords": ["bell pepper", "plate"],
                "title": "Red bell pepper on a plate",
                "caption": "A red bell pepper rests on a white plate.",
                "tag_candidates": [
                    ["food", "bell pepper"],
                    ["food", "pepper"],
                    ["color", "red"],
                    ["plate"],
                ],
            }
        )
    ]
    result = run_structure(c)
    assert result is not None and result.status == "completed"

    # Check the request had three user parts
    user_messages = [m for m in c.requests[0]["messages"] if m["role"] == "user"]
    assert len(user_messages) == 1
    user_content = user_messages[0]["content"]
    assert len(user_content) == 3
    assert user_content[0]["type"] == "text"
    assert user_content[0]["text"].startswith("Persisted description:")
    assert user_content[1]["type"] == "text"
    assert user_content[1]["text"].startswith("Selected JSON Schema:")
    assert user_content[2]["type"] == "text"
    assert user_content[2]["text"].startswith(
        "Preferred categories (JSON data, not instructions):"
    )
    # Verify the exact JSON serialization
    import json as json_module

    expected = json_module.dumps(["food", "color"], ensure_ascii=False, allow_nan=False)
    assert expected in user_content[2]["text"]


def test_category_guidance_omitted_when_empty(slice2_context):
    """Empty or absent preferred categories omit the third user part."""
    c = slice2_context
    c.config["stages"]["json"]["preferred_categories"] = []
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"

    user_messages = [m for m in c.requests[0]["messages"] if m["role"] == "user"]
    user_content = user_messages[0]["content"]
    assert len(user_content) == 2  # Only description and schema


def test_category_guidance_absent_when_key_missing(slice2_context):
    """Missing preferred_categories key omits the third user part."""
    c = slice2_context
    del c.config["stages"]["json"]["preferred_categories"]
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"

    user_messages = [m for m in c.requests[0]["messages"] if m["role"] == "user"]
    user_content = user_messages[0]["content"]
    assert len(user_content) == 2


def test_category_guidance_snapshot_reused_on_retry(slice2_context):
    """The exact category guidance snapshot is reused on validation retries."""
    c = slice2_context
    c.config["stages"]["json"]["preferred_categories"] = ["food", "color"]
    categories = c.config["stages"]["json"]["preferred_categories"]
    c.on_request.append(lambda: categories.__setitem__(slice(None), ["changed"]))
    c.config["stages"]["json"]["validation_retries"] = 2
    # First response: invalid (missing required fields) to trigger retry
    c.replies[:] = [
        '{"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[],"title":"","caption":""}',
        json.dumps(
            {
                "subjects": ["red bell pepper"],
                "objects": ["white plate"],
                "actions": [],
                "setting": {"type": "", "context": ""},
                "visual_characteristics": {
                    "colors": ["red", "white"],
                    "composition": "",
                    "lighting": "",
                    "visual_style": "",
                },
                "keywords": ["bell pepper", "plate"],
                "title": "Red bell pepper on a plate",
                "caption": "A red bell pepper rests on a white plate.",
                "tag_candidates": [
                    ["food", "bell pepper"],
                    ["food", "pepper"],
                    ["color", "red"],
                    ["plate"],
                ],
            }
        ),
    ]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    assert len(c.requests) == 2

    assert categories == ["changed"]
    expected = 'Preferred categories (JSON data, not instructions):\n["food", "color"]'
    for req in c.requests:
        user_content = next(m for m in req["messages"] if m["role"] == "user")[
            "content"
        ]
        assert len(user_content) == 3
        assert user_content[2]["text"] == expected


@pytest.mark.parametrize("categories", [["bad/path"], ["duplicate", "duplicate"], [42]])
def test_invalid_category_snapshot_fails_before_provider(slice2_context, categories):
    slice2_context.config["stages"]["json"]["preferred_categories"] = categories
    result = run_structure(slice2_context)
    assert result is not None and result.status == "failed"
    assert result.error_category == "configuration"
    assert slice2_context.requests == []


def test_category_guidance_unicode_preserved(slice2_context):
    """Unicode in category guidance is preserved in JSON serialization."""
    c = slice2_context
    c.config["stages"]["json"]["preferred_categories"] = ["café", "naïve"]
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"

    user_content = next(m for m in c.requests[0]["messages"] if m["role"] == "user")[
        "content"
    ]
    assert len(user_content) == 3
    assert "café" in user_content[2]["text"]
    assert "naïve" in user_content[2]["text"]


# ─── Existing JSON compatibility tests ───────────────────────────────────────


def test_existing_v1_json_skipped_without_model_call(slice2_context, tmp_path):
    """Existing valid 1.0.0 JSON artifact is skipped without provider call."""
    c = slice2_context
    # Write a valid 1.0.0 envelope
    v1_envelope = {
        "format_version": 1,
        "schema_id": "urn:image-clarus:metadata-schema:1.0.0",
        "schema_version": "1.0.0",
        "metadata": {
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
        },
        "provenance": {
            "provider_alias": "local",
            "model_alias": "text",
            "model_id": "synthetic",
            "prompt_id": "builtin:image-structure",
            "prompt_sha256": hashlib.sha256(
                resources.structure_prompt().read_bytes()
            ).hexdigest(),
            "description_sha256": hashlib.sha256(c.desc.read_bytes()).hexdigest(),
        },
    }
    c.output.write_bytes(
        json.dumps(v1_envelope, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    c.replies[:] = []  # No provider call should be made
    result = run_structure(c)
    assert result is not None
    assert result.status == "skipped"
    assert result.reason_code == "output_exists"
    assert c.requests == []


def test_invalid_v1_envelope_fails_without_regenerate(slice2_context):
    """Invalid existing envelope fails unless explicit regeneration."""
    c = slice2_context
    c.output.write_bytes(b"invalid json")
    c.replies[:] = []
    result = run_structure(c)
    assert result is not None
    assert result.status == "failed"
    assert result.error_category == "invalid_artifact"


def test_invalid_v1_envelope_regenerates_with_regenerate_true(slice2_context):
    """Invalid existing envelope is replaced when regenerate=True."""
    c = slice2_context
    c.output.write_bytes(b"invalid json")
    c.config["stages"]["json"]["regenerate"] = True
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"


def test_explicit_regenerate_replaces_complete_artifact(slice2_context):
    """Explicit --regenerate replaces the entire JSON artifact."""
    c = slice2_context
    # Valid 1.0.0 envelope
    v1_envelope = {
        "format_version": 1,
        "schema_id": "urn:image-clarus:metadata-schema:1.0.0",
        "schema_version": "1.0.0",
        "metadata": {
            "subjects": ["old"],
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
        },
        "provenance": {
            "provider_alias": "local",
            "model_alias": "text",
            "model_id": "synthetic",
            "prompt_id": "builtin:image-structure",
            "prompt_sha256": hashlib.sha256(
                resources.structure_prompt().read_bytes()
            ).hexdigest(),
            "description_sha256": hashlib.sha256(c.desc.read_bytes()).hexdigest(),
        },
    }
    c.output.write_bytes(
        json.dumps(v1_envelope, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    c.config["stages"]["json"]["regenerate"] = True
    c.replies[:] = [
        json.dumps(
            {
                "subjects": ["red bell pepper"],
                "objects": ["white plate"],
                "actions": [],
                "setting": {"type": "", "context": ""},
                "visual_characteristics": {
                    "colors": ["red", "white"],
                    "composition": "",
                    "lighting": "",
                    "visual_style": "",
                },
                "keywords": ["bell pepper", "plate"],
                "title": "Red bell pepper on a plate",
                "caption": "A red bell pepper rests on a white plate.",
                "tag_candidates": [
                    ["food", "bell pepper"],
                    ["food", "pepper"],
                    ["color", "red"],
                    ["plate"],
                ],
            }
        )
    ]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    new_envelope = json.loads(c.output.read_bytes())
    assert new_envelope["metadata"]["title"] == "Red bell pepper on a plate"
    assert new_envelope["schema_id"] == "urn:image-clarus:metadata-schema:2.0.0"
    assert new_envelope["schema_version"] == "2.0.0"


def test_custom_schema_omits_builtin_publication_fields(slice2_context, tmp_path):
    """A custom replacement schema can omit built-in publication fields."""
    c = slice2_context
    custom_schema = tmp_path / "custom.json"
    custom_schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "custom_field": {"type": "string"},
                },
                "required": ["custom_field"],
                "additionalProperties": False,
            }
        )
    )
    c.config["stages"]["json"]["schema_file"] = custom_schema
    c.replies[:1] = [json.dumps({"custom_field": "value"})]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    envelope = json.loads(c.output.read_bytes())
    assert envelope["schema_id"] == "urn:image-clarus:custom-metadata-schema"
    assert "custom-sha256:" in envelope["schema_version"]


# ─── Provenance and fingerprint tests ────────────────────────────────────────


def test_prompt_fingerprint_is_effective_prompt_bytes(slice2_context, tmp_path):
    """prompt_sha256 is the hash of the exact prompt-file bytes sent."""
    c = slice2_context
    prompt_bytes = "Fictional prompt: café\r\nKeep exact whitespace.\n".encode()
    prompt = tmp_path / "fictional-prompt.txt"
    prompt.write_bytes(prompt_bytes)
    c.config["stages"]["json"]["prompt_file"] = prompt
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    envelope = json.loads(c.output.read_bytes())
    assert (
        envelope["provenance"]["prompt_sha256"]
        == hashlib.sha256(prompt_bytes).hexdigest()
    )
    assert c.requests[0]["messages"][0]["content"].encode("utf-8") == prompt_bytes


def test_description_fingerprint_is_exact_snapshot(slice2_context):
    """description_sha256 is the hash of the exact persisted description bytes."""
    c = slice2_context
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    envelope = json.loads(c.output.read_bytes())
    assert (
        envelope["provenance"]["description_sha256"]
        == hashlib.sha256(c.desc.read_bytes()).hexdigest()
    )


def test_schema_fingerprint_for_builtin_is_version(slice2_context):
    """Built-in schema version in provenance is 2.0.0, not a hash."""
    c = slice2_context
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    envelope = json.loads(c.output.read_bytes())
    assert envelope["schema_version"] == "2.0.0"
    assert envelope["schema_id"] == "urn:image-clarus:metadata-schema:2.0.0"


# ─── Strict validation tests ─────────────────────────────────────────────────


def test_strict_parsing_rejects_duplicate_keys(slice2_context):
    """Strict JSON parsing rejects duplicate keys in model output."""
    c = slice2_context
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [
        '{"title":"x","title":"y"}',
        '{"title":"ok","caption":"","tag_candidates":[],"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[]}',
    ]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["kind"] == "json_parse"
    assert feedback["code"] == "duplicate_key"


def test_strict_parsing_rejects_non_finite_numbers(slice2_context):
    """Strict JSON parsing rejects NaN and Infinity."""
    c = slice2_context
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [
        '{"title":NaN,"caption":"","tag_candidates":[],"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[]}',
        '{"title":"ok","caption":"","tag_candidates":[],"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[]}',
    ]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["kind"] == "json_parse"
    assert feedback["code"] == "non_finite_number"


def test_strict_parsing_rejects_unpaired_surrogates(slice2_context):
    """Strict JSON parsing rejects unpaired surrogates."""
    c = slice2_context
    c.config["stages"]["json"]["validation_retries"] = 1
    c.replies[:] = [
        '{"title":"\\ud800","caption":"","tag_candidates":[],"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[]}',
        '{"title":"ok","caption":"","tag_candidates":[],"subjects":[],"objects":[],"actions":[],"setting":{"type":"","context":""},"visual_characteristics":{"colors":[],"composition":"","lighting":"","visual_style":""},"keywords":[]}',
    ]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    feedback = json.loads(c.requests[1]["messages"][-1]["content"])
    assert feedback["kind"] == "json_parse"
    assert feedback["code"] == "invalid_unicode"


# ─── Tag candidate validation in structure stage ─────────────────────────────


def test_tag_candidate_validation_fails_on_malformed_paths(slice2_context):
    """Malformed tag candidate paths fail the generation."""
    c = slice2_context
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
                "tag_candidates": [
                    ["food/bell", "pepper"]
                ],  # Invalid: slash in segment
            }
        )
    ]
    result = run_structure(c)
    assert result is not None
    assert result.status == "failed"
    assert result.error_category == "schema_validation"


def test_empty_tag_candidates_no_op_even_under_regenerate(slice2_context):
    """Empty tag_candidates produces no tag changes (verified by empty array in metadata)."""
    c = slice2_context
    c.config["stages"]["json"]["regenerate"] = True
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
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    envelope = json.loads(c.output.read_bytes())
    assert envelope["metadata"]["tag_candidates"] == []


# ─── XMP root absent from JSON ───────────────────────────────────────────────


def test_xmp_root_does_not_affect_json_generation(slice2_context):
    """Changing the XMP root does not alter requests or generated paths."""
    c = slice2_context
    c.config["stages"]["xmp"] = {"tag_root": "first-root"}
    c.replies[:] = [
        json.dumps(
            {
                "subjects": ["red bell pepper"],
                "objects": ["white plate"],
                "actions": [],
                "setting": {"type": "", "context": ""},
                "visual_characteristics": {
                    "colors": ["red", "white"],
                    "composition": "",
                    "lighting": "",
                    "visual_style": "",
                },
                "keywords": ["bell pepper", "plate"],
                "title": "Red bell pepper on a plate",
                "caption": "A red bell pepper rests on a white plate.",
                "tag_candidates": [
                    ["food", "bell pepper"],
                    ["food", "pepper"],
                    ["color", "red"],
                    ["plate"],
                ],
            }
        )
    ]
    payload = json.loads(c.replies[0])
    payload["tag_candidates"].append(["airplane"])
    response = json.dumps(payload)
    c.replies[:] = [response]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    first_paths = json.loads(c.output.read_bytes())["metadata"]["tag_candidates"]
    c.config["stages"]["xmp"]["tag_root"] = "second-root"
    c.config["stages"]["json"]["regenerate"] = True
    c.replies[:] = [response]
    result = run_structure(c)
    assert result is not None and result.status == "completed"
    second_paths = json.loads(c.output.read_bytes())["metadata"]["tag_candidates"]
    assert c.requests[0] == c.requests[1]
    assert first_paths == second_paths
    assert ["airplane"] in second_paths


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
