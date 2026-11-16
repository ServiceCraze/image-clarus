import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from image_clarus import resources

ROOT = Path(__file__).resolve().parents[2]
ASSETS = (
    (
        "structure_prompt",
        "prompts/image-structure.txt",
        "15b5dd95690fbaf9dae7f485628a80eff2ac7a12945e7c19281456359f30a683",
    ),
    (
        "structure_schema",
        "schemas/image-structure.schema.json",
        "9d90dd0aa3722535fe4f79eb1770b50900dcfe61ce376e4ce54fee03b43877f0",
    ),
)


@pytest.mark.parametrize("name,path,digest", ASSETS)
def test_source_resource_has_exact_a3_bytes(name, path, digest):
    lookup = getattr(resources, name, None)
    assert callable(lookup), f"{name} resource lookup is missing"
    data = lookup().read_bytes()
    assert data == (ROOT / path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    assert not data.startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("name,path,digest", ASSETS)
def test_installed_wheel_resource_matches_source(name, path, digest, tmp_path):
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    env = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(env)],
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
            str(env / "bin/python"),
            str(next(dist.glob("*.whl"))),
        ],
        check=True,
        capture_output=True,
    )
    env_os = os.environ.copy()
    env_os.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(env / "bin/python"),
            "-c",
            f"from image_clarus import resources; import sys; sys.stdout.buffer.write(getattr(resources, '{name}')().read_bytes())",
        ],
        cwd=tmp_path,
        env=env_os,
        capture_output=True,
        check=True,
    )
    assert result.stdout == (ROOT / path).read_bytes()
    assert hashlib.sha256(result.stdout).hexdigest() == digest
