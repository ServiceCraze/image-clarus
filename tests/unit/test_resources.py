import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "image-description.txt"


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
    assert cli.stdout == b"image-clarus 0.3.4\n"
