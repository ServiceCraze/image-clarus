"""Slice 4 state identity and accumulation through the real batch CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_single_image_pipeline import METADATA, ROOT, png, rig  # noqa: F401

from image_clarus.state.storage import SQLiteStorage, initialize


def run(cwd, *args):
    env = os.environ.copy()
    env.update(HOME=str(cwd), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*")
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", *map(str, args)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def store(root, seed):
    root.mkdir(parents=True, exist_ok=True)
    state = root / ".image-clarus"
    initialize(state)
    SQLiteStorage(state).add_categories([seed])
    return state


def categories(state):
    return SQLiteStorage(state).snapshot_categories()


def sidecar(image, path):
    payload = {
        "format_version": 1,
        "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
        "schema_version": "2.0.0",
        "provenance": {
            "provider_alias": "fictional",
            "model_alias": "fictional",
            "model_id": "fictional",
            "prompt_id": "fictional",
            "description_sha256": "a" * 64,
        },
        "metadata": {"tag_candidates": [path.split("/")]},
    }
    output = Path(str(image) + ".desc.json")
    data = json.dumps(payload).encode()
    output.write_bytes(data)
    return output, data


@pytest.mark.parametrize(
    "mode", ["--inter-stage-concurrency", "--no-inter-stage-concurrency"]
)
@pytest.mark.parametrize("selection", ["image", "cwd", "explicit"])
@pytest.mark.parametrize("enabled", [True, False])
def test_batch_state_selection_generated_and_skipped(
    rig,  # noqa: F811
    tmp_path,
    mode,
    selection,
    enabled,
):
    cwd = tmp_path / "working"
    cwd.mkdir()
    a, b = tmp_path / "collection-a", tmp_path / "collection-b"
    sa, sb = store(a, "seed/a"), store(b, "seed/b")
    sc = store(cwd, "seed/cwd") if selection != "image" else None
    se = (
        store(tmp_path / "chosen", "seed/explicit") if selection == "explicit" else None
    )
    first, second = a / "first.png", b / "second.png"
    for image in (first, second):
        image.write_bytes(png())
        Path(str(image) + ".desc.txt").write_text("fictional description")
    artifact, before = sidecar(first, "skipped/first")
    prompt = tmp_path / "json-prompt.txt"
    prompt.write_text("Transform the supplied description into JSON.")
    args = [
        "process",
        first,
        second,
        "--config",
        rig.config("identity"),
        "--stages",
        "json",
        "--json-prompt",
        prompt,
        mode,
        "--set",
        f"state.accumulate_categories={str(enabled).lower()}",
    ]
    if se:
        args += ["--state-dir", se]
    result = run(cwd, *args)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert artifact.read_bytes() == before
    assert (
        json.loads(Path(str(second) + ".desc.json").read_text())["metadata"] == METADATA
    )
    assert [r[0] for r in rig.requests] == ["json"]
    states = {sa: {"seed/a"}, sb: {"seed/b"}}
    if sc:
        states[sc] = {"seed/cwd"}
    if se:
        states[se] = {"seed/explicit"}
    target_first = se or sc or sa
    target_second = se or sc or sb
    if enabled:
        states[target_first].add("skipped/first")
        states[target_second].update({"color/blue", "shape/square"})
    for state, expected in states.items():
        assert set(categories(state)) == expected


@pytest.mark.parametrize("enabled", [True, False])
def test_sequential_visibility_after_skipped_json(rig, tmp_path, enabled):  # noqa: F811
    cwd = tmp_path / "shared"
    state = store(cwd, "seed/start")
    a, b = cwd / "a.png", cwd / "b.png"
    for image in (a, b):
        image.write_bytes(png())
    Path(str(a) + ".desc.txt").write_text("existing description")
    artifact, before = sidecar(a, "first/seen")
    second_artifact, second_before = sidecar(b, "second/seen")
    prompt = tmp_path / "desc-prompt.txt"
    prompt.write_text("Known categories: {{state.categories.known}}")
    result = run(
        cwd,
        "process",
        a,
        b,
        "--config",
        rig.config("visibility"),
        "--stages",
        "desc,json",
        "--desc-prompt",
        prompt,
        "--no-inter-stage-concurrency",
        "--set",
        f"state.accumulate_categories={str(enabled).lower()}",
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (
        artifact.read_bytes() == before
        and second_artifact.read_bytes() == second_before
    )
    assert [r[0] for r in rig.requests] == ["desc"]
    request = json.dumps(rig.requests[0][1])
    assert "seed/start" in request
    assert ("first/seen" in request) is enabled
    assert "second/seen" not in request
    assert set(categories(state)) == (
        {"seed/start", "first/seen", "second/seen"} if enabled else {"seed/start"}
    )
