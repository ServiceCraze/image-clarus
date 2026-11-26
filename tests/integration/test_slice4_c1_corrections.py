"""C1 CLI budget and runtime correction tests with synthetic fixtures."""

import os
import subprocess
import sys
from pathlib import Path

from test_single_image_pipeline import ROOT, rig  # noqa: F401


def start_batch(fixture, tmp_path, config):
    env = os.environ.copy()
    env.update(
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(fixture.image.parent),
            "--config",
            str(config),
            "--stages",
            "desc",
            "--max-work-files",
            "1",
            "--no-inter-stage-concurrency",
            "--verbose",
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish(process):
    try:
        return process.communicate(timeout=40)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_corrections_exceed_twice_budget_after_real_sidecar_removal(rig, tmp_path):  # noqa: F811
    # The first request proves the complete immutable plan already exists. Hold it
    # while three predicted-existing sidecars are actually removed.
    rig.image.rename(rig.image.parent / "a.png")
    images = [rig.image.parent / f"{name}.png" for name in ("a", "b", "c", "d", "z")]
    for image in images[1:]:
        image.write_bytes(rig.original)
    sidecars = [Path(str(image) + ".desc.txt") for image in images]
    for sidecar in sidecars[1:4]:
        sidecar.write_text("synthetic existing description")
    config = rig.config("correction")
    rig.hold.add("desc")
    process = start_batch(rig, tmp_path, config)
    try:
        assert rig.arrived["desc"].wait(20), "first provider request not reached"
        assert process.poll() is None
        for sidecar in sidecars[1:4]:
            sidecar.unlink()
        # The known-excluded image is changed too, but remains excluded.
        sidecars[4].write_text("created after planning")
        rig.release["desc"].set()
        stdout, stderr = finish(process)
    finally:
        rig.release["desc"].set()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    assert process.returncode == 0, (stdout, stderr)
    assert "summary images=5 admitted=1 no_work=3 excluded=1" in stdout
    assert (
        "work llm_images=4 corrective_images=3 requests=4 first_requests=4 retries=0"
        in stdout
    )
    assert len(rig.requests) == 4
    assert all(p.exists() for p in sidecars[:4])
    assert sidecars[4].read_text() == "created after planning"
    assert all(image.read_bytes() == rig.original for image in images)


def test_failed_admitted_image_does_not_replenish_budget(rig, tmp_path):  # noqa: F811
    first = rig.image.parent / "a.png"
    rig.image.rename(first)
    second = rig.image.parent / "b.png"
    second.write_bytes(rig.original)
    config = rig.config("failure")
    rig.hold.add("desc")
    process = start_batch(rig, tmp_path, config)
    try:
        assert rig.arrived["desc"].wait(20), "first provider request not reached"
        assert process.poll() is None
        # Introduce an unpublishable target only after planning and request entry.
        Path(str(first) + ".desc.txt").mkdir()
        rig.release["desc"].set()
        stdout, stderr = finish(process)
    finally:
        rig.release["desc"].set()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    assert process.returncode == 1, (stdout, stderr)
    assert "summary images=2 admitted=1 no_work=0 excluded=1" in stdout
    assert "skip stage=desc reason=budget_excluded count=1" in stdout
    assert not Path(str(second) + ".desc.txt").exists()
    assert len(rig.requests) == 1
    assert "failed=1" in stdout
    assert first.read_bytes() == second.read_bytes() == rig.original
