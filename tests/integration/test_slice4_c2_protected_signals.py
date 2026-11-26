"""POSIX CLI signal delivery during an admitted sidecar publication.

The barrier is injected at ArtifactService checkpoints, not inside a syscall.
The local provider is synthetic; actual CLI, signal handlers and file writes run.
"""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "c2_helpers", Path(__file__).with_name("test_c2_signal_safety.py")
)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("delivery", ["process", "group"])
@pytest.mark.parametrize(
    "checkpoint", ["output_validate", "backup_replace", "destination_replace"]
)
def test_repeated_signals_drain_admitted_publication(
    tmp_path, signum, delivery, checkpoint
):
    image = tmp_path / "fictional.png"
    image.write_bytes(_helpers.SOURCE)
    target = Path(str(image) + ".desc.txt")
    target.write_bytes(b"old description")
    marker, received, release = (
        tmp_path / name for name in ("entered", "received", "release")
    )
    injection = f"""\
import signal, time
from pathlib import Path
from image_clarus.artifacts import ArtifactService
real_signal = signal.signal
def install(sig, handler):
    if callable(handler) and handler.__name__ == "request":
        def observed(signum, frame):
            handler(signum, frame)
            with Path({str(received)!r}).open("a") as f:
                f.write(str(signum) + "\\n")
        return real_signal(sig, observed)
    return real_signal(sig, handler)
signal.signal = install
original = ArtifactService._point
def point(self, name):
    if name == {checkpoint!r}:
        Path({str(marker)!r}).touch()
        deadline = time.monotonic() + 20
        while not Path({str(release)!r}).exists():
            if time.monotonic() > deadline:
                raise RuntimeError("barrier timed out")
            time.sleep(.01)
    return original(self, name)
ArtifactService._point = point
"""
    (tmp_path / "sitecustomize.py").write_text(injection)
    with _helpers.provider() as (port, entered, _, requests):
        config = tmp_path / "config.yaml"
        config.write_text(
            f"providers:\n  local:\n    base_url: http://127.0.0.1:{port}/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\npipeline:\n  backup_retention: retain\n"
        )
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
                "--stages=desc",
                "--regenerate",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            assert entered.wait(15)
            _helpers.wait_for_marker(marker, process)
            for count in (1, 2):
                if delivery == "group":
                    os.killpg(process.pid, signum)
                else:
                    process.send_signal(signum)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and process.poll() is None:
                    if (
                        received.exists()
                        and len(received.read_text().splitlines()) >= count
                    ):
                        break
                    time.sleep(0.01)
                assert (
                    received.exists()
                    and len(received.read_text().splitlines()) >= count
                )
            assert process.poll() is None
            release.touch()
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 128 + signum, (stdout, stderr)
            assert f"desc: completed — output={json.dumps(str(target))}" in stdout
            assert target.read_bytes() == _helpers.NEW_DESCRIPTION.encode()
            assert Path(str(target) + ".bak").read_bytes() == b"old description"
            assert image.read_bytes() == _helpers.SOURCE
            assert len(requests) == 1
            assert not list(tmp_path.glob(".*.image-clarus-*.tmp"))
        finally:
            release.touch()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
            # Detect and clean up any surviving member before reporting failure.
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                os.killpg(process.pid, signal.SIGKILL)
                pytest.fail("a member of the CLI process group survived")
