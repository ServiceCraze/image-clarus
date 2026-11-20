"""CLI orchestration tests using injected stage results and state failures."""

import json
import signal
import sys
from pathlib import Path

import pytest

from image_clarus import cli
from image_clarus.results import PipelineResult, StageResult
from image_clarus.state.service import StateService
from image_clarus.state.storage import MemoryStorage, StateError


class ObservedStorage(MemoryStorage):
    def close(self):
        self.final = self.snapshot_categories()
        super().close()


def payload():
    return json.dumps(
        {
            "format_version": 1,
            "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
            "schema_version": "2.0.0",
            "provenance": {
                "provider_alias": "demo",
                "model_alias": "demo",
                "model_id": "demo",
                "prompt_id": "demo",
                "description_sha256": "a" * 64,
            },
            "metadata": {"tag_candidates": [["ai-tools", "leaf"], ["one"]]},
        }
    ).encode()


@pytest.mark.parametrize("root,limit,depth", [("ai", 1, 0), ("other", 10, 2)])
@pytest.mark.parametrize("status", ["completed", "skipped"])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("later_failure", [True, False])
def test_cli_post_pipeline_and_policy_independent(
    tmp_path, monkeypatch, capsys, status, enabled, later_failure, root, limit, depth
):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"synthetic")
    artifact = Path(str(image) + ".desc.json")
    artifact.write_bytes(payload())
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: fictional\nstages:\n  json:\n    model: m\n"
    )
    storage = ObservedStorage()
    service = StateService(storage)
    monkeypatch.setattr(StateService, "select", lambda *a, **kw: service)

    def pipeline(image_path, config, services, stages, **kwargs):
        assert (
            services.state.snapshot_categories() == []
        )  # later stage sees pre-update state
        j = StageResult(
            "json",
            status,
            output_path=artifact,
            reason_code="output_exists" if status == "skipped" else None,
        )
        x = (
            StageResult("xmp", "failed", error_category="synthetic", message="failure")
            if later_failure
            else StageResult("xmp", "completed", output_path=image)
        )
        return PipelineResult(image_path, (j, x))

    monkeypatch.setattr("image_clarus.pipeline.run_pipeline", pipeline)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "json",
            "--set",
            f"state.accumulate_categories={str(enabled).lower()}",
            "--set",
            f"stages.xmp.tag_root={root}",
            "--set",
            f"stages.xmp.tag_limit={limit}",
            "--set",
            f'prompt_expansion.macros["state.categories.known"].max_depth={depth}',
        ],
    )
    assert cli.main() == (1 if later_failure else 0)
    assert storage.final == (["ai-tools/leaf", "one"] if enabled else [])
    assert artifact.read_bytes() == payload()
    assert f"json: {status}" in capsys.readouterr().out


def test_state_failure_preserves_result(tmp_path, monkeypatch, capsys):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"synthetic")
    artifact = Path(str(image) + ".desc.json")
    artifact.write_bytes(payload())
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: fictional\nstages:\n  json:\n    model: m\n"
    )

    class Broken(MemoryStorage):
        def add_categories(self, paths):
            raise StateError("secret sentinel")

    monkeypatch.setattr(StateService, "select", lambda *a, **kw: StateService(Broken()))
    monkeypatch.setattr(
        "image_clarus.pipeline.run_pipeline",
        lambda image, *a, **kw: PipelineResult(
            image, (StageResult("json", "completed", output_path=artifact),)
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "json",
        ],
    )
    assert cli.main() == 0
    output = capsys.readouterr()
    assert "json: completed" in output.out and "state error" in output.err
    assert "secret sentinel" not in output.err
    assert artifact.read_bytes() == payload()


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_after_pipeline_prevents_write_and_controls_exit(
    tmp_path, monkeypatch, signum
):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"synthetic")
    Path(str(image) + ".desc.json").write_bytes(payload())
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: fictional\nstages:\n  json:\n    model: m\n"
    )
    storage = ObservedStorage()
    monkeypatch.setattr(StateService, "select", lambda *a, **kw: StateService(storage))

    def pipeline(image, config, services, stages, **kwargs):
        services.stop.request(signum)
        return PipelineResult(
            image,
            (
                StageResult(
                    "json", "completed", output_path=Path(str(image) + ".desc.json")
                ),
            ),
        )

    monkeypatch.setattr("image_clarus.pipeline.run_pipeline", pipeline)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "json",
        ],
    )
    assert cli.main() == 128 + signum
    assert storage.final == []
