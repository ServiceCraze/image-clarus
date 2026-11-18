"""Real process signals at XMP transformation and publication boundaries."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from image_clarus.xmp_backend import EMPTY, ExifToolBackend

ROOT = Path(__file__).resolve().parents[2]
SOURCE = b"fictional image bytes\x00\xff"


def _wait(marker, process):
    deadline = time.monotonic() + 20
    while (
        not marker.exists() and process.poll() is None and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert marker.exists(), "process did not reach the checkpoint"


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="ExifTool unavailable")
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize(
    "checkpoint",
    ["after_transform", "output_write", "backup_replace", "destination_replace"],
)
def test_real_signal_before_or_during_xmp_publication(tmp_path, signum, checkpoint):
    image = tmp_path / "fictional.jpg"
    image.write_bytes(SOURCE)
    target = Path(str(image) + ".xmp")
    target.write_bytes(EMPTY)
    backup = Path(str(target) + ".bak")
    metadata = {
        "format_version": 1,
        "schema_id": "urn:image-clarus:custom-metadata-schema",
        "schema_version": "custom-sha256:" + "a" * 64,
        "metadata": {},
        "provenance": {
            "provider_alias": "fictional",
            "model_alias": "fictional",
            "model_id": "fictional",
            "prompt_id": "fictional",
            "prompt_sha256": "a" * 64,
            "description_sha256": "b" * 64,
        },
    }
    Path(str(image) + ".desc.json").write_text(json.dumps(metadata))
    config = tmp_path / "config.yaml"
    config.write_text(
        'stages:\n  xmp:\n    caption_author: "Fictional Author"\n    caption_author_policy: overwrite\npipeline:\n  backup_retention: retain\n'
    )
    marker, received, release = [
        tmp_path / name for name in ("entered", "received", "release")
    ]
    injection = f"""\
import signal
import time
from pathlib import Path
from image_clarus.artifacts import ArtifactService
from image_clarus.xmp_backend import ExifToolBackend
real_signal = signal.signal
def install(sig, handler):
    if callable(handler) and handler.__name__ == "request":
        def observed(signum, frame):
            handler(signum, frame)
            Path({str(received)!r}).touch()
        return real_signal(sig, observed)
    return real_signal(sig, handler)
signal.signal = install
def barrier():
    Path({str(marker)!r}).touch()
    deadline = time.monotonic() + 20
    while not Path({str(release)!r}).exists():
        if time.monotonic() > deadline:
            raise RuntimeError("barrier timed out")
        time.sleep(0.01)
original_run = ExifToolBackend._run
def run(self, args):
    result = original_run(self, args)
    if {checkpoint!r} == "after_transform":
        barrier()
    return result
ExifToolBackend._run = run
original_point = ArtifactService._point
def point(self, name):
    if name == {checkpoint!r}:
        barrier()
    return original_point(self, name)
ArtifactService._point = point
"""
    (tmp_path / "sitecustomize.py").write_text(injection)
    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join((str(tmp_path), str(ROOT / "src")))
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages=xmp",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait(marker, process)
        process.send_signal(signum)
        _wait(received, process)
        assert process.poll() is None
        release.touch()
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 128 + signum, stderr
        assert image.read_bytes() == SOURCE
        if checkpoint == "after_transform":
            assert "xmp: skipped — reason=interrupted" in stdout
            assert target.read_bytes() == EMPTY
            assert not backup.exists()
        else:
            assert "xmp: completed" in stdout
            assert backup.read_bytes() == EMPTY
            assert (
                ExifToolBackend(tmp_path).read(target.read_bytes())["author"]
                == "Fictional Author"
            )
        assert not list(tmp_path.glob(".*.image-clarus-*.tmp"))
        assert not list(tmp_path.glob(".image-clarus-*.xmp"))
    finally:
        release.touch()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
