import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from image_clarus.artifacts import ArtifactService
from image_clarus.pipeline import run_pipeline
from image_clarus.providers.openai_compatible import OpenAICompatible
from image_clarus.stages.description import run_description

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
)


@pytest.fixture
def context(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(PNG)
    requests = []
    response = {"content": "A synthetic scene."}

    def handler(request):
        requests.append(json.loads(request.content))
        if response.get("status"):
            return httpx.Response(
                response["status"], json={"error": {"message": "private sentinel"}}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": response["content"],
                        },
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    services = SimpleNamespace(
        artifacts=ArtifactService(),
        provider_factory=lambda provider, model: OpenAICompatible(
            provider, model, transport=transport
        ),
    )
    config = {
        "providers": {"local": {"base_url": "http://localhost/v1"}},
        "models": {"vision": {"provider": "local", "model_id": "vision-one"}},
        "stages": {
            "desc": {
                "model": "vision",
                "prompt_file": None,
                "reasoning_effort": None,
                "regenerate": False,
            }
        },
        "pipeline": {"backup_retention": "remove"},
    }
    return image, config, services, requests, response


def test_creation_via_pipeline(context):
    image, config, services, requests, _ = context
    result = run_pipeline(
        image, config, services, {"desc": run_description}, selected=("desc",)
    )
    output = image.with_name(image.name + ".desc.txt")
    assert result.stages[0].status == "completed"
    assert result.stages[0].output_path == output
    assert output.read_bytes() == b"A synthetic scene."
    assert image.read_bytes() == PNG
    assert len(requests) == 1


def test_valid_existing_is_skipped(context):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    output.write_text("original", encoding="utf-8")
    result = run_description(image, config, services)
    assert (result.status, result.reason_code) == ("skipped", "output_exists")
    assert output.read_text() == "original"
    assert requests == []


def test_invalid_existing_fails_without_overwrite(context):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    output.write_bytes(b"  \n")
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert output.read_bytes() == b"  \n"
    assert requests == []


@pytest.mark.parametrize("original", [b"valid", b"  \n"])
def test_explicit_regeneration_replaces_existing(context, original):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    output.write_bytes(original)
    config["stages"]["desc"]["regenerate"] = True
    result = run_description(image, config, services)
    assert result.status == "completed"
    assert output.read_bytes() == b"A synthetic scene."
    assert len(requests) == 1


@pytest.mark.parametrize("override", [False, True])
def test_prompt_selection_is_exact(context, tmp_path, override):
    image, config, services, requests, _ = context
    expected = "Fully describe and explain everything about this image."
    if override:
        prompt = tmp_path / "prompt.txt"
        expected = "Custom instructions.\nSecond line.\n"
        prompt.write_text(expected, encoding="utf-8")
        config["stages"]["desc"]["prompt_file"] = prompt
    result = run_description(image, config, services)
    assert result.status == "completed"
    assert requests[0]["messages"][0]["content"] == expected


def test_selected_model_provider_and_effort(context):
    image, config, services, requests, _ = context
    config["providers"]["second"] = {"base_url": "http://127.0.0.1/v1"}
    config["models"]["chosen"] = {
        "provider": "second",
        "model_id": "selected-vision",
        "reasoning_effort": "low",
    }
    config["stages"]["desc"].update(model="chosen", reasoning_effort="high")
    result = run_description(image, config, services)
    assert result.status == "completed"
    assert requests[0]["model"] == "selected-vision"
    assert requests[0]["reasoning_effort"] == "high"


def test_provider_failure_preserves_original(context):
    image, config, services, requests, response = context
    output = image.with_name(image.name + ".desc.txt")
    output.write_bytes(b"original")
    config["stages"]["desc"]["regenerate"] = True
    response["status"] = 503
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "provider_unavailable")
    assert "private sentinel" not in result.message
    assert output.read_bytes() == b"original"
    assert len(requests) == 1


@pytest.mark.parametrize("retention", ["remove", "retain"])
def test_regeneration_success_applies_backup_retention(context, retention):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    backup = output.with_name(output.name + ".bak")
    output.write_bytes(b"original")
    backup.write_bytes(b"older")
    config["stages"]["desc"]["regenerate"] = True
    services.artifacts = ArtifactService(retention)
    assert run_description(image, config, services).status == "completed"
    assert output.read_bytes() == b"A synthetic scene."
    assert (
        backup.read_bytes() == b"original"
        if retention == "retain"
        else not backup.exists()
    )
    assert len(requests) == 1


def test_regeneration_provider_failure_preserves_existing_backup(context):
    image, config, services, requests, response = context
    output = image.with_name(image.name + ".desc.txt")
    backup = output.with_name(output.name + ".bak")
    output.write_bytes(b"original")
    backup.write_bytes(b"older")
    config["stages"]["desc"]["regenerate"] = True
    response["status"] = 503
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "provider_unavailable")
    assert output.read_bytes() == b"original"
    assert backup.read_bytes() == b"older"
    assert len(requests) == 1


@pytest.mark.parametrize("content", ["", "  \n\t"])
def test_empty_provider_output_is_failure_without_artifact(context, content):
    image, config, services, requests, response = context
    response["content"] = content
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "provider_unavailable")
    assert not image.with_name(image.name + ".desc.txt").exists()
    assert len(requests) == 1


def test_safe_write_failure_preserves_original(context):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    output.write_bytes(b"original")
    config["stages"]["desc"]["regenerate"] = True

    def fail(point):
        if point == "destination_replace":
            raise OSError("private path sentinel")

    services.artifacts = ArtifactService(checkpoint=fail)
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "file_io")
    assert "private path sentinel" not in result.message
    assert output.read_bytes() == b"original"
    assert len(requests) == 1


def test_unreadable_image_fails_safely(context):
    image, config, services, requests, _ = context
    image.unlink()
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "file_io")
    assert requests == []
    assert not image.with_name(image.name + ".desc.txt").exists()


def test_prompt_read_failure_is_sanitized(context, tmp_path):
    image, config, services, requests, _ = context
    config["stages"]["desc"]["prompt_file"] = tmp_path / "sensitive-prompt"
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "configuration")
    assert "sensitive-prompt" not in result.message
    assert requests == []


def test_recovery_of_valid_backup_skips_before_provider(context):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    backup = output.with_name(output.name + ".bak")
    backup.write_bytes(b"recovered description")
    result = run_description(image, config, services)
    assert (result.status, result.reason_code) == ("skipped", "output_exists")
    assert output.read_bytes() == b"recovered description"
    assert not backup.exists()
    assert requests == []


def test_unsupported_image_suffix_is_reported(context):
    image, config, services, requests, _ = context
    renamed = image.with_suffix(".xyz")
    image.rename(renamed)
    result = run_description(renamed, config, services)
    assert (result.status, result.error_category) == ("failed", "unsupported_image")
    assert requests == []
    assert not renamed.with_name(renamed.name + ".desc.txt").exists()


def test_model_effort_inherits_when_stage_unspecified(context):
    image, config, services, requests, _ = context
    config["models"]["vision"]["reasoning_effort"] = "low"
    assert run_description(image, config, services).status == "completed"
    assert requests[0]["reasoning_effort"] == "low"


def test_invalid_utf8_existing_is_not_replaced(context):
    image, config, services, requests, _ = context
    output = image.with_name(image.name + ".desc.txt")
    output.write_bytes(b"\xff")
    result = run_description(image, config, services)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert output.read_bytes() == b"\xff"
    assert requests == []
