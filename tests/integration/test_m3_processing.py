"""M3: real process/management overlap and optional state failure boundaries."""

import os
import sqlite3
import subprocess
import sys

from test_c1_state_faults import stop_holder, wait_for_holder
from test_single_image_pipeline import ROOT, check_envelope, rig  # noqa: F401
from test_state_rebuild_cli import sidecar

from image_clarus.state.storage import SQLiteStorage, initialize


def management(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", "state", "categories", *map(str, args)],
        cwd=cwd,
        env=dict(os.environ, HOME=str(cwd / "home"), PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )


def test_management_read_clear_rebuild_during_held_inference(rig, tmp_path):  # noqa: F811
    state = tmp_path / ".image-clarus"
    initialize(state)
    SQLiteStorage(state).add_categories(["seed/item"])
    with sqlite3.connect(state / "state.sqlite3") as db:
        db.execute("CREATE TABLE unrelated (value TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('retained')")
    source = tmp_path / "fixture.desc.json"
    sidecar(source, [["management", "item"]])
    source_bytes = source.read_bytes()
    rig.desc.write_text("fictional description", encoding="utf-8")
    rig.hold.add("json")
    process = rig.start(
        rig.config("overlap"), "--stages", "json", "--state-dir", str(state)
    )
    try:
        assert rig.arrived["json"].wait(15), "inference did not reach the provider"
        assert process.poll() is None and not rig.structured.exists()
        listing = management(tmp_path, "list", "--state-dir", state)
        assert (listing.returncode, listing.stdout, listing.stderr) == (
            0,
            '"seed/item"\n',
            "",
        )
        clear = management(tmp_path, "clear", "--state-dir", state)
        assert (clear.returncode, clear.stdout, clear.stderr) == (
            0,
            "clear target=configured\nclear deleted=1\n",
            "",
        )
        rebuild = management(tmp_path, "rebuild", source, "--state-dir", state)
        assert rebuild.returncode == 0, (rebuild.stdout, rebuild.stderr)
        assert (
            "success=1" in rebuild.stdout and "confirmed_inserted=1" in rebuild.stdout
        )
        listing = management(tmp_path, "list", "--state-dir", state)
        assert (listing.returncode, listing.stdout, listing.stderr) == (
            0,
            '"management/item"\n',
            "",
        )
        assert process.poll() is None and not rig.release["json"].is_set()
        assert not rig.structured.exists()
        rig.release["json"].set()
        assert "json: completed" in rig.finish(process)
        check_envelope(rig, "fictional description")
        assert SQLiteStorage(state).snapshot_categories() == [
            "color/blue",
            "management/item",
            "shape/square",
        ]
        with sqlite3.connect(state / "state.sqlite3") as db:
            assert db.execute("SELECT value FROM unrelated").fetchall() == [
                ("retained",)
            ]
        assert source.read_bytes() == source_bytes
        assert rig.image.read_bytes() == rig.original
        assert [request[0] for request in rig.requests] == ["json"]
    finally:
        rig.release["json"].set()


def test_real_writer_lock_is_nonblocking_for_primary_but_strict_for_clear(
    rig,  # noqa: F811
    tmp_path,
):
    state = tmp_path / ".image-clarus"
    initialize(state)
    SQLiteStorage(state).add_categories(["seed/item"])
    rig.desc.write_text("fictional description", encoding="utf-8")
    code = (
        "import os, sqlite3, sys\n"
        "db = sqlite3.connect(sys.argv[1])\n"
        "db.execute('BEGIN IMMEDIATE')\n"
        "os.write(1, b'L')\n"
        "sys.stdin.readline()\n"
        "db.rollback()\n"
        "db.close()\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", code, str(state / "state.sqlite3")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_holder(holder)
        clear = management(tmp_path, "clear", "--state-dir", state)
        assert clear.returncode == 1, (clear.stdout, clear.stderr)
        assert (
            "state operation failed" in clear.stderr and "deleted=" not in clear.stdout
        )
        process = rig.start(
            rig.config("locked"), "--stages", "json", "--state-dir", str(state)
        )
        stdout, stderr = process.communicate(timeout=25)
        assert process.returncode == 0, (stdout, stderr)
        assert "json: completed" in stdout
        assert (
            "state error: category update failed" in stderr
            and "temporary state" in stderr
        )
        assert holder.poll() is None
        check_envelope(rig, "fictional description")
        assert rig.image.read_bytes() == rig.original
    finally:
        stop_holder(holder)
    assert holder.returncode == 0
    assert SQLiteStorage(state).snapshot_categories() == ["seed/item"]
