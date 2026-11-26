"""CLI batch memory sharing versus selected broken-store isolation."""

import json
import time
from pathlib import Path

import pytest
from test_single_image_pipeline import png, rig  # noqa: F401
from test_slice4_c1_state import categories, run, sidecar, store


@pytest.mark.parametrize(
    "mode", ["--inter-stage-concurrency", "--no-inter-stage-concurrency"]
)
@pytest.mark.parametrize("selection", ["memory", "broken"])
def test_batch_memory_and_broken_store(rig, tmp_path, mode, selection):  # noqa: F811
    work = tmp_path / "work"
    work.mkdir()
    images = tmp_path / "batch-images"
    images.mkdir()
    first, second = images / "first.png", images / "second.png"
    for image in (first, second):
        image.write_bytes(png())
    Path(str(first) + ".desc.txt").write_text("existing fictional description")
    first_artifact, first_bytes = sidecar(first, "first/seen")
    # A skipped second JSON artifact lets the description snapshot reveal whether
    # the first image's post-stage accumulation is visible to this image.
    second_artifact, second_bytes = sidecar(second, "second/seen")
    prompt = tmp_path / "authored-prompt.txt"
    prompt.write_text("Fictional known: {{state.categories.known}}", encoding="utf-8")
    args = [
        "process",
        first,
        second,
        "--config",
        rig.config("batch-memory"),
        "--stages",
        "desc,json",
        "--desc-prompt",
        prompt,
        mode,
    ]
    if selection == "broken":
        alternate = store(work, "seed/alternate")
        before = (alternate / "state.sqlite3").read_bytes()
        selected = tmp_path / "fictional-private-selected"
        selected.mkdir()
        (selected / "state.sqlite3").write_bytes(b"fictional-corrupt-sentinel")
        args += ["--state-dir", selected]
    start = time.monotonic()
    result = run(work, *args)
    elapsed = time.monotonic() - start
    assert elapsed < 45
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert first_artifact.read_bytes() == first_bytes
    assert second_artifact.read_bytes() == second_bytes
    assert first.read_bytes() == png() and second.read_bytes() == png()
    assert Path(str(second) + ".desc.txt").exists()
    assert not Path(str(first) + ".xmp").exists()
    assert not Path(str(second) + ".xmp").exists()
    assert [request[0] for request in rig.requests] == ["desc"]
    request = json.dumps(rig.requests[0][1])
    assert "Fictional known:" in request and "second/seen" not in request
    if selection == "memory":
        assert not (work / ".image-clarus").exists()
        assert not (images / ".image-clarus").exists()
        assert "state error" not in result.stderr
        if mode == "--no-inter-stage-concurrency":
            assert "first/seen" in request
    else:
        assert "first/seen" not in request and "seed/alternate" not in request
        assert "Fictional known: []" in request
        assert "state error: repository unavailable" in result.stderr
        assert "temporary state" in result.stderr
        for sentinel in (
            "fictional-private-selected",
            "fictional-corrupt-sentinel",
            "Traceback",
        ):
            assert sentinel not in result.stdout + result.stderr
        assert categories(alternate) == ["seed/alternate"]
        assert (alternate / "state.sqlite3").read_bytes() == before
        assert (
            selected / "state.sqlite3"
        ).read_bytes() == b"fictional-corrupt-sentinel"
