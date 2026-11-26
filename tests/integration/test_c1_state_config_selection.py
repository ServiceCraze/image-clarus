"""C1 CLI state selection precedence and shared persistent accumulation."""

import json
from pathlib import Path

import pytest
from test_single_image_pipeline import png, rig  # noqa: F401
from test_slice4_c1_state import categories, run, sidecar, store


@pytest.mark.parametrize(
    "mode", ["--inter-stage-concurrency", "--no-inter-stage-concurrency"]
)
@pytest.mark.parametrize("selection", ["yaml", "generic", "dedicated", "cleared"])
def test_batch_configured_state_selection(rig, tmp_path, mode, selection):  # noqa: F811
    cwd = tmp_path / "work"
    cwd.mkdir()
    yaml_store = store(tmp_path / "configured", "seed/yaml")
    generic_store = store(cwd / "generic", "seed/generic")
    dedicated_store = store(cwd / "dedicated", "seed/dedicated")
    cwd_store = store(cwd, "seed/cwd")
    image_store = store(tmp_path / "images", "seed/image")
    config = rig.config("config-selection")
    with config.open("a", encoding="utf-8") as stream:
        stream.write("state:\n  directory: configured/.image-clarus\n")
    images = [tmp_path / "images" / "first.png", tmp_path / "images" / "second.png"]
    artifacts = []
    for index, image in enumerate(images):
        image.write_bytes(png())
        artifacts.append(sidecar(image, f"batch/item{index}"))
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Known: {{state.categories.known}}", encoding="utf-8")
    args = [
        "process",
        *images,
        "--config",
        config,
        "--stages",
        "desc,json",
        "--desc-prompt",
        prompt,
        mode,
    ]
    if selection in {"generic", "dedicated"}:
        args += ["--set", "state.directory=generic/.image-clarus"]
    if selection == "dedicated":
        # Dedicated override wins even when the generic assignment appears later.
        args += [
            "--state-dir",
            "dedicated/.image-clarus",
            "--set",
            "state.directory=generic/.image-clarus",
        ]
    if selection == "cleared":
        args += ["--set", "state.directory=null"]
    result = run(cwd, *args)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "state error" not in result.stderr
    target, seed = {
        "yaml": (yaml_store, "seed/yaml"),
        "generic": (generic_store, "seed/generic"),
        "dedicated": (dedicated_store, "seed/dedicated"),
        "cleared": (cwd_store, "seed/cwd"),
    }[selection]
    assert len(rig.requests) == 2
    for stage, body, _ in rig.requests:
        assert stage == "desc"
        request = json.dumps(body)
        assert seed in request
        for other in {
            "seed/yaml",
            "seed/generic",
            "seed/dedicated",
            "seed/cwd",
            "seed/image",
        } - {seed}:
            assert other not in request
    for image, (artifact, original) in zip(images, artifacts):
        assert image.read_bytes() == png()
        assert artifact.read_bytes() == original
        assert Path(str(image) + ".desc.txt").exists()
    for state, original_seed in [
        (yaml_store, "seed/yaml"),
        (generic_store, "seed/generic"),
        (dedicated_store, "seed/dedicated"),
        (cwd_store, "seed/cwd"),
        (image_store, "seed/image"),
    ]:
        expected = {original_seed}
        if state == target:
            expected.update({"batch/item0", "batch/item1"})
        assert set(categories(state)) == expected
