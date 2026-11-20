"""Separate-process ordering at a real later XMP stage, with fictional inputs."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_xmp_cli_b5 import envelope, png

ROOT = Path(__file__).resolve().parents[2]


def _categories(database):
    with sqlite3.connect(database, timeout=5) as connection:
        return [
            row[0]
            for row in connection.execute(
                "select path from known_categories order by path"
            )
        ]


def _wait(path, process):
    deadline = time.monotonic() + 25
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), "child did not reach the actual XMP planning barrier"


@pytest.mark.skipif(
    shutil.which("exiftool") is None, reason="real ExifTool unavailable"
)
@pytest.mark.parametrize("enabled", [True, False])
def test_later_real_xmp_stage_finishes_before_category_accumulation(tmp_path, enabled):
    init = subprocess.run(
        [sys.executable, "-m", "image_clarus", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert init.returncode == 0, (init.stdout, init.stderr)
    state = tmp_path / ".image-clarus"
    database = state / "state.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "insert into known_categories(path) values (?)", ("existing/item",)
        )
    image = tmp_path / "fictional.png"
    source = png()
    image.write_bytes(source)
    artifact = Path(str(image) + ".desc.json")
    original = json.dumps(envelope()).encode()
    artifact.write_bytes(original)
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  text:\n    provider: local\n    model_id: fictional\n"
        "stages:\n  json:\n    model: text\n"
    )
    marker = tmp_path / "entered"
    release = tmp_path / "release"
    # Wrap a genuine later-stage operation, not the pipeline or the stage result.
    # The original planner invokes the real ExifTool before this barrier.
    (tmp_path / "sitecustomize.py").write_text(
        "import time\nfrom pathlib import Path\n"
        "from image_clarus.stages import xmp\n"
        "original = xmp.prepare_updates\n"
        "def observe(*args, **kwargs):\n"
        "    result = original(*args, **kwargs)\n"
        f"    Path({str(marker)!r}).touch()\n"
        "    deadline = time.monotonic() + 25\n"
        f"    while not Path({str(release)!r}).exists():\n"
        "        if time.monotonic() >= deadline: raise RuntimeError('barrier timed out')\n"
        "        time.sleep(0.01)\n"
        "    return result\n"
        "xmp.prepare_updates = observe\n"
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
            "--stages",
            "json,xmp",
            "--config",
            str(config),
            "--state-dir",
            str(state),
            "--set",
            f"state.accumulate_categories={str(enabled).lower()}",
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait(marker, process)
        assert process.poll() is None
        assert _categories(database) == ["existing/item"]
        release.touch()
        stdout, stderr = process.communicate(timeout=25)
        assert process.returncode == 0, (stdout, stderr)
        assert "json: skipped" in stdout
        assert "xmp: completed" in stdout
        expected = ["existing/item"]
        if enabled:
            expected = ["color/blue", "existing/item", "shape/square"]
        assert _categories(database) == expected
        assert image.read_bytes() == source
        assert artifact.read_bytes() == original
        assert Path(str(image) + ".xmp").exists()
    finally:
        release.touch()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
