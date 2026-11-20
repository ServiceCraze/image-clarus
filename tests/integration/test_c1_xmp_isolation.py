"""C1 stage isolation and accumulation with real CLI and ExifTool."""

import json
import os
import sqlite3
import subprocess
import sys

from test_c1_publication import read_fields
from test_state_b3_primary import initialize, tree_bytes
from test_xmp_cli_b5 import ROOT, envelope

pytest_plugins = ("test_xmp_cli_b5",)


def test_xmp_only_invalid_selected_state_never_expands_or_accesses_provider(
    rig, real_exiftool, tmp_path
):
    initialize(tmp_path, tmp_path / "home")
    alternate = tmp_path / ".image-clarus"
    before = tree_bytes(alternate)
    selected = tmp_path / "fictional-private-selected-state"
    selected.mkdir()
    artifact = json.dumps(envelope()).encode()
    rig.structured.write_bytes(artifact)
    hook = tmp_path / "hook"
    hook.mkdir()
    loaded = hook / "loaded"
    invoked = hook / "invoked"
    (hook / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "import socket\n"
        "from image_clarus import prompt_expansion\n"
        f"Path({str(loaded)!r}).touch()\n"
        "def forbidden(*args, **kwargs):\n"
        f"    Path({str(invoked)!r}).touch()\n"
        "    raise RuntimeError('fictional forbidden access')\n"
        "prompt_expansion.expand_prompt = forbidden\n"
        "prompt_expansion.safe_config_snapshot = forbidden\n"
        "socket.socket.connect = forbidden\n"
        "socket.socket.connect_ex = forbidden\n"
        "socket.create_connection = forbidden\n"
    )
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.pathsep.join((str(hook), str(ROOT / "src"))),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(rig.image),
            "--stages",
            "xmp",
            "--config",
            str(rig.no_model_cfg),
            "--state-dir",
            str(selected),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert loaded.exists() and not invoked.exists()
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "xmp: completed" in result.stdout
    assert "state error" in result.stderr and "repository unavailable" in result.stderr
    assert "temporary state" in result.stderr
    assert str(selected) not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert not rig.requests and rig.image.read_bytes() == rig.original
    assert rig.structured.read_bytes() == artifact
    assert tree_bytes(alternate) == before and list(selected.iterdir()) == []
    fields = read_fields(real_exiftool, rig.xmp)
    assert fields["XMP-dc:Title"] == "Blue square"
    assert fields["XMP-digiKam:TagsList"] == ["ai/shape/square", "ai/color/blue"]


def test_later_real_xmp_failure_still_accumulates_skipped_json(
    rig, real_exiftool, tmp_path
):
    initialize(tmp_path, tmp_path / "home")
    state = tmp_path / ".image-clarus"
    artifact = json.dumps(envelope()).encode()
    rig.structured.write_bytes(artifact)
    broken = b"<fictional-invalid-xmp"
    rig.xmp.write_bytes(broken)
    out, err = rig.finish(
        rig.start("--stages", "json,xmp", "--state-dir", str(state)), 1
    )
    assert "json: skipped" in out
    assert "xmp: failed — category=invalid_artifact" in out
    assert not err and not rig.requests
    assert rig.image.read_bytes() == rig.original
    assert rig.structured.read_bytes() == artifact and rig.xmp.read_bytes() == broken
    with sqlite3.connect(state / "state.sqlite3") as connection:
        assert connection.execute(
            "select path from known_categories order by path"
        ).fetchall() == [("color/blue",), ("shape/square",)]


def test_invalid_optional_categories_leave_skipped_json_and_state_unchanged(
    rig, tmp_path
):
    initialize(tmp_path, tmp_path / "home")
    state = tmp_path / ".image-clarus"
    data = envelope()
    data["metadata"] = dict(
        data["metadata"], tag_candidates=[["valid"], ["bad/segment"]]
    )
    artifact = json.dumps(data).encode()
    rig.structured.write_bytes(artifact)
    before = tree_bytes(state)
    out, err = rig.finish(rig.start("--stages", "json", "--state-dir", str(state)))
    assert "json: skipped" in out
    assert "state error: category accumulation failed" in err
    assert not rig.requests and rig.structured.read_bytes() == artifact
    assert rig.image.read_bytes() == rig.original and tree_bytes(state) == before
