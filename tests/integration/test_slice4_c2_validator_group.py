"""Group signals during an admitted write with a real validator subprocess.

Instrumentation adds schema validation to the real description validator because
that built-in validator does not itself launch a subprocess. The worker performs
real jsonschema validation after the test barrier; no validator result is faked.
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
    "c2_signal_helpers", Path(__file__).with_name("test_c2_signal_safety.py")
)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)


def _wait(predicate, process, message, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if process.poll() is not None:
            break
        time.sleep(0.01)
    pytest.fail(message)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_repeated_group_signals_drain_real_protected_validator(tmp_path, signum):
    marker = tmp_path / "validator-entered"
    received = tmp_path / "received"
    release = tmp_path / "release"
    injection = f"""\
import os, signal, time
from pathlib import Path
from image_clarus import schema_worker
from image_clarus.artifacts import ArtifactService
real_signal = signal.signal
def install(sig, handler):
    if callable(handler) and handler.__name__ == "request":
        def observed(signum, frame):
            handler(signum, frame)
            with Path({str(received)!r}).open("a") as stream:
                stream.write(str(signum) + "\\n")
        return real_signal(sig, observed)
    return real_signal(sig, handler)
signal.signal = install
original_validate = ArtifactService._validate
def validate(self, validator, data, category):
    if self._last_point.get() == "output_validate":
        def with_child(value):
            result = schema_worker.validate('{{"type":"object","title":"protected-validator-test"}}', {{}}, timeout=10)
            return result == {{"status": "ok"}} and validator(value)
        return original_validate(self, with_child, data, category)
    return original_validate(self, validator, data, category)
ArtifactService._validate = validate
from jsonschema import Draft202012Validator
original_errors = Draft202012Validator.iter_errors
def errors(self, instance, *args, **kwargs):
    if self.schema == {{"type": "object", "title": "protected-validator-test"}} and instance == {{}}:
        Path({str(marker)!r}).write_text(str(os.getpid()) + " " + str(os.getpgrp()))
        deadline = time.monotonic() + 9
        while not Path({str(release)!r}).exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("validator barrier timed out")
            time.sleep(.01)
    return original_errors(self, instance, *args, **kwargs)
Draft202012Validator.iter_errors = errors
"""
    (tmp_path / "sitecustomize.py").write_text(injection)
    image = tmp_path / "image.png"
    image.write_bytes(_helpers.SOURCE)
    target = Path(str(image) + ".desc.txt")
    target.write_bytes(b"old description")
    with _helpers.provider() as (port, entered, _, requests):
        config = tmp_path / "config.yaml"
        config.write_text(
            f"providers:\n  local:\n    base_url: http://127.0.0.1:{port}/v1\n"
            "models:\n  m:\n    provider: local\n    model_id: synthetic\n"
            "stages:\n  desc:\n    model: m\npipeline:\n  backup_retention: retain\n"
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
        child_pid = None
        try:
            assert entered.wait(15)
            _wait(marker.exists, process, "validator did not enter")
            child_pid, child_group = map(int, marker.read_text().split())
            assert child_pid != process.pid
            assert os.getpgid(child_pid) == child_group
            for count in (1, 2):
                os.killpg(process.pid, signum)
                _wait(
                    lambda count=count: (
                        received.exists()
                        and len(received.read_text().splitlines()) >= count
                    ),
                    process,
                    "CLI did not handle repeated group signal",
                    timeout=5,
                )
                assert process.poll() is None
                os.kill(child_pid, 0)
            release.touch()
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 128 + signum, (stdout, stderr)
            assert f"desc: completed — output={json.dumps(str(target))}" in stdout
            assert target.read_bytes() == _helpers.NEW_DESCRIPTION.encode()
            assert Path(str(target) + ".bak").read_bytes() == b"old description"
            assert image.read_bytes() == _helpers.SOURCE
            assert len(requests) == 1
            assert not list(tmp_path.glob(".*.image-clarus-*.tmp"))
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
            child_pid = None
            assert child_group != process.pid, (
                "protected validator inherited CLI process group"
            )
        finally:
            release.touch()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
