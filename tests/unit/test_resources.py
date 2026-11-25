import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "image-description.txt"

# These tests exercise the distribution channels, so they need the project
# checkout (packaging metadata, prompt file) and the `uv` launcher. When the
# suite is run from something that is not that checkout - for example an
# installed wheel's tests placed in a scratch directory - there is nothing to
# package and the channel tests are skipped rather than failing.
REQUIRES_CHECKOUT = pytest.mark.skipif(
    not (ROOT / "pyproject.toml").is_file() or not PROMPT.is_file(),
    reason="distribution checks require the project checkout and its prompt file",
)
REQUIRES_UV = pytest.mark.skipif(
    subprocess.run(
        ["sh", "-c", "command -v uv"], check=False, capture_output=True
    ).returncode
    != 0,
    reason="distribution checks require the uv launcher",
)


@REQUIRES_CHECKOUT
@REQUIRES_UV
def test_description_prompt_from_source_checkout():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from image_clarus.resources import description_prompt; import sys; sys.stdout.buffer.write(description_prompt().read_bytes())",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=True,
    )
    assert result.stdout == PROMPT.read_bytes()


@REQUIRES_CHECKOUT
@REQUIRES_UV
def test_description_prompt_from_installed_wheel(tmp_path):
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    environment = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(environment)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--no-deps",
            "--python",
            str(environment / "bin/python"),
            str(next(dist.glob("*.whl"))),
        ],
        check=True,
        capture_output=True,
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(environment / "bin/python"),
            "-c",
            "from image_clarus.resources import description_prompt; import sys; sys.stdout.buffer.write(description_prompt().read_bytes())",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    assert result.stdout == PROMPT.read_bytes()
    cli = subprocess.run(
        [str(environment / "bin/image-clarus"), "--version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    from importlib.metadata import version

    assert cli.stdout == f"image-clarus {version('image-clarus')}\n".encode()
