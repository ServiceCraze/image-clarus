"""Independent CLI invocations sharing a synthetic repository."""

import json
import sqlite3
import subprocess
import sys

import pytest
from test_single_image_pipeline import rig  # noqa: F401


def run(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", *map(str, args)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=25,
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_independent_skipped_invocations_share_repository(tmp_path, enabled):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert run(repo, "init").returncode == 0
    state = repo / ".image-clarus"
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  text:\n    provider: local\n    model_id: fictional\nstages:\n  json:\n    model: text\n"
    )
    for index in range(2):
        directory = tmp_path / f"collection-{index}"
        directory.mkdir()
        image = directory / "sample.jpg"
        image.write_bytes(b"synthetic")
        artifact = directory / "sample.jpg.desc.json"
        data = json.dumps(
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
                "metadata": {"tag_candidates": [["shared", str(index)]]},
            }
        ).encode()
        artifact.write_bytes(data)
        result = run(
            directory,
            "process",
            image,
            "--stages",
            "json",
            "--config",
            config,
            "--state-dir",
            state,
            "--set",
            f"state.accumulate_categories={str(enabled).lower()}",
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert "json: skipped" in result.stdout
        assert artifact.read_bytes() == data
    with sqlite3.connect(state / "state.sqlite3") as connection:
        assert connection.execute(
            "select path from known_categories order by path"
        ).fetchall() == ([("shared/0",), ("shared/1",)] if enabled else [])


@pytest.mark.parametrize("enabled", [True, False])
def test_generated_then_independent_macro_request(rig, tmp_path, enabled):  # noqa: F811
    repo = tmp_path / "shared"
    repo.mkdir()
    assert run(repo, "init").returncode == 0
    state = repo / ".image-clarus"
    config = rig.config("shared-config")
    rig.desc.write_text("synthetic description")
    rig.finish(
        rig.start(
            config,
            "--stages",
            "json",
            "--state-dir",
            str(state),
            "--set",
            f"state.accumulate_categories={str(enabled).lower()}",
        )
    )
    with sqlite3.connect(state / "state.sqlite3") as connection:
        assert connection.execute(
            "select path from known_categories order by path"
        ).fetchall() == ([("color/blue",), ("shape/square",)] if enabled else [])
    other = tmp_path / "unrelated"
    other.mkdir()
    image = other / "other.png"
    image.write_bytes(rig.original)
    prompt = other / "prompt.txt"
    prompt.write_text("Known: {{state.categories.known}}")
    result = run(
        other,
        "process",
        image,
        "--stages",
        "desc",
        "--config",
        config,
        "--state-dir",
        state,
        "--desc-prompt",
        prompt,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert [stage for stage, _, _ in rig.requests] == ["json", "desc"]
    request = json.dumps(rig.requests[-1][1])
    assert ("color/blue" in request) is enabled
    assert ("shape/square" in request) is enabled
