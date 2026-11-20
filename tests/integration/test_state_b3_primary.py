"""B3 fallback at the real CLI boundary with a loopback-only provider."""

import json
import os
import sqlite3
import subprocess
import sys

import pytest
from test_xmp_cli_b5 import (  # noqa: F401
    DESCRIPTION,
    ROOT,
    assert_xmp,
    envelope,
    real_exiftool,
    rig,
    validate_json,
)


def initialize(directory, home):
    env = os.environ.copy()
    env.update(HOME=str(home), PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "image_clarus", "init"],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def tree_bytes(directory):
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
@pytest.mark.parametrize("kind", ["missing", "corrupt", "incompatible"])
def test_invalid_explicit_state_preserves_primary_and_discoverable_store(
    rig,  # noqa: F811
    tmp_path,
    level,
    kind,
):
    home = tmp_path / "home"
    initialize(tmp_path, home)
    discovered = tmp_path / ".image-clarus"
    database = discovered / "state.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO known_categories(path) VALUES (?)", ("existing/category",)
        )
    before = tree_bytes(discovered)

    explicit = tmp_path / "private-state-sentinel"
    if kind == "corrupt":
        explicit.mkdir()
        (explicit / "state.sqlite3").write_bytes(b"corrupt-private-content-sentinel")
    elif kind == "incompatible":
        other = tmp_path / "other"
        other.mkdir()
        initialize(other, home)
        (other / ".image-clarus").rename(explicit)
        with sqlite3.connect(explicit / "state.sqlite3") as connection:
            connection.execute("PRAGMA user_version = 999")
    explicit_before = tree_bytes(explicit) if explicit.exists() else None

    config = tmp_path / "config.yaml"
    with config.open("a") as stream:
        stream.write(f"logging:\n  level: {level}\n")
    assert not rig.desc.exists() and not rig.structured.exists()
    stdout, stderr = rig.finish(
        rig.start("--stages", "desc,json", "--state-dir", str(explicit))
    )
    assert "desc: completed" in stdout and "json: completed" in stdout
    assert "state error" in stderr and "temporary state" in stderr
    assert "private-state-sentinel" not in stderr
    assert "corrupt-private-content-sentinel" not in stderr
    assert "Traceback" not in stderr
    assert rig.desc.read_bytes() == DESCRIPTION.encode()
    validate_json(rig)
    assert [stage for stage, _ in rig.requests] == ["desc", "json"]
    assert rig.image.read_bytes() == rig.original
    assert tree_bytes(discovered) == before
    if explicit_before is None:
        assert not explicit.exists()
    else:
        assert tree_bytes(explicit) == explicit_before


def test_unavailable_state_does_not_block_xmp_publication(rig, tmp_path, real_exiftool):  # noqa: F811
    rig.desc.write_text(DESCRIPTION, encoding="utf-8")
    rig.structured.write_text(json.dumps(envelope()), encoding="utf-8")
    stdout, stderr = rig.finish(
        rig.start("--stages", "xmp", "--state-dir", str(tmp_path / "missing-state"))
    )
    assert "xmp: completed" in stdout
    assert "state error" in stderr
    assert "missing-state" not in stderr
    assert_xmp(rig)
    assert rig.image.read_bytes() == rig.original
    assert rig.requests == []
    assert not (tmp_path / "missing-state").exists()
