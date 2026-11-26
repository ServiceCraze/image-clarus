"""Bounded real CLI startup probes with executable dry-run safety guards."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# This runs before the application imports, inside the actual CLI child. Raising
# SystemExit makes forbidden operations observable even if application code catches
# ordinary exceptions. Config/import reads are allowed; input and state reads are not.
GUARD = """\
import logging, os, shutil, sys
root = os.path.abspath(os.environ["DRY_GUARD_ROOT"])
original_which = shutil.which
def which(name, *a, **kw):
    if "exiftool" in str(name).lower():
        raise SystemExit("GUARD: exiftool lookup")
    return original_which(name, *a, **kw)
shutil.which = which
class ForbiddenFileHandler(logging.Handler):
    def __init__(self, *a, **kw):
        raise SystemExit("GUARD: file logger")
logging.FileHandler = ForbiddenFileHandler

def guard(event, args):
    if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "socket.connect"):
        raise SystemExit("GUARD: process or provider " + event)
    if event in ("os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.chmod", "os.link", "os.symlink", "os.truncate"):
        raise SystemExit("GUARD: filesystem mutation " + event)
    if event == "open":
        path, mode, flags = args
        if isinstance(path, (str, bytes, os.PathLike)):
            path = os.path.abspath(os.fsdecode(path))
            if os.path.commonpath((root, path)) == root:
                raise SystemExit("GUARD: input or state content open")
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise SystemExit("GUARD: writable open")
sys.addaudithook(guard)
"""


def snapshot(root):
    return {
        str(path.relative_to(root)): ("dir" if path.is_dir() else path.read_bytes())
        for path in root.rglob("*")
    }


@pytest.mark.parametrize(
    "case", ["success", "empty", "bad_config", "unavailable", "late_selection"]
)
def test_cli_dry_run_safety_matrix(tmp_path, case):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    if case != "empty":
        (inputs / "a.jpg").write_bytes(b"fictional image")
        (inputs / "a.jpg.desc.txt").write_bytes(b"existing description")
        (inputs / "b.jpg").write_bytes(b"another image")
    # State path lives in the protected tree, including an existing sentinel.
    state = inputs / "state"
    state.mkdir()
    (state / "state.db").write_bytes(b"state sentinel")
    config = tmp_path / "config.yaml"
    config.write_text(
        "selection:\n  max_depth: -1\n"
        if case == "bad_config"
        else "providers:\n  sample:\n    base_url: http://127.0.0.1:1/v1\n"
        "models:\n  sample:\n    provider: sample\n    model_id: fictional\n"
        "stages:\n  desc:\n    model: sample\n  json:\n    model: sample\n"
    )
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "sitecustomize.py").write_text(GUARD)
    home = tmp_path / "home"
    home.mkdir()
    before = snapshot(tmp_path)
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        PYTHONPATH=os.pathsep.join((str(audit), str(ROOT / "src"))),
        PYTHONDONTWRITEBYTECODE="1",
        DRY_GUARD_ROOT=str(inputs),
        PATH=str(tmp_path / "missing-bin"),
    )
    selections = [str(inputs)]
    if case == "late_selection":
        selections = [str(inputs / "a.jpg"), str(inputs / "missing.jpg")]
    stages = "xmp" if case == "unavailable" else "desc"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            *selections,
            "--config",
            str(config),
            "--state-dir",
            str(state),
            "--stages",
            stages,
            "--dry-run",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert snapshot(tmp_path) == before
    assert "GUARD:" not in result.stdout + result.stderr, (result.stdout, result.stderr)
    if case in ("bad_config", "late_selection"):
        assert result.returncode == 2, (result.stdout, result.stderr)
        assert (
            "selection.max_depth" if case == "bad_config" else "selection error"
        ) in result.stderr
        assert "plan incomplete" in result.stderr
        assert "estimate unavailable: incomplete plan" in result.stderr
        assert "plan complete" not in result.stdout
        assert "estimated initial plan/queue memory:" not in result.stdout
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)
        count = 0 if case == "empty" else 2
        assert f"plan complete images={count} " in result.stdout
        assert "runtime_dependencies=not_checked" in result.stdout
        assert re.search(
            r"estimated initial plan/queue memory: \d+ bytes \(estimate, not peak or bound\)",
            result.stdout,
        )
        assert (
            len(
                [
                    line
                    for line in result.stdout.splitlines()
                    if line.startswith("plan provisional ")
                ]
            )
            == count
        )
        assert result.stderr == ""
        if case == "success":
            assert "admitted=1 no_work=1 excluded=0" in result.stdout
        if case == "empty":
            assert "admitted=0 no_work=0 excluded=0" in result.stdout


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "open(os.environ['DRY_GUARD_ROOT'] + '/image.jpg').read()",
            "input or state content",
        ),
        ("open('forbidden', 'w')", "writable open"),
        ("os.mkdir('forbidden')", "filesystem mutation"),
        ("subprocess.run(['true'])", "process or provider"),
        ("socket.socket().connect(('127.0.0.1', 1))", "process or provider"),
        ("shutil.which('exiftool')", "exiftool lookup"),
        ("logging.FileHandler('forbidden')", "file logger"),
    ],
)
def test_child_guard_rejects_forbidden_operations(tmp_path, code, expected):
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "sitecustomize.py").write_text(GUARD)
    root = tmp_path / "inputs"
    root.mkdir()
    (root / "image.jpg").write_bytes(b"sentinel")
    before = snapshot(tmp_path)
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(audit), PYTHONDONTWRITEBYTECODE="1", DRY_GUARD_ROOT=str(root)
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, subprocess, socket, shutil, logging; " + code,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert f"GUARD: {expected}" in result.stderr
    assert snapshot(tmp_path) == before
