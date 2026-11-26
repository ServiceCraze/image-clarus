"""Black-box selection and initial-plan acceptance with synthetic inputs."""

import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cli(tmp_path):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers["Content-Length"])))
            body = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Synthetic description.",
                            },
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  sample:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
        "models:\n  sample:\n    provider: sample\n    model_id: fictional\n"
        "stages:\n  desc:\n    model: sample\n  json:\n    model: sample\n"
    )
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(HOME=str(home), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*")

    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    (audit_dir / "sitecustomize.py").write_text(
        "import os, sys\n"
        'root = os.environ.get("SELECTION_GUARD")\n'
        "def guard(event, args):\n"
        '    if event == "open" and root and isinstance(args[0], (str, bytes, os.PathLike)):\n'
        "        p = os.path.abspath(os.fsdecode(args[0]))\n"
        "        if os.path.commonpath((root, p)) == root:\n"
        '            raise SystemExit("guard: image tree content opened")\n'
        "sys.addaudithook(guard)\n"
    )

    def run(*selections, options=(), dry=True, guard=None):
        child_env = env.copy()
        if guard is not None:
            child_env["SELECTION_GUARD"] = str(guard)
            child_env["PYTHONPATH"] = os.pathsep.join(
                (str(audit_dir), str(ROOT / "src"))
            )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                *map(str, selections),
                "--config",
                str(config),
                *options,
                *(["--dry-run"] if dry else []),
            ],
            check=False,
            cwd=tmp_path,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    yield run, calls
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def create(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic image bytes")
    return path


def rows(result):
    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("plan provisional ")
    ]
    return [
        (json.loads(re.search(r'image=("(?:[^"\\]|\\.)*")', line).group(1)), line)
        for line in lines
    ]


def snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def test_directory_six_extensions_depth_and_literal_first(tmp_path, cli):
    run, calls = cli
    root = tmp_path / "images"
    names = [
        "a.JPG",
        "b.jpeg",
        "c.png",
        "d.webp",
        "e.tif",
        "f.TIFF",
        "ignore.raw",
        "nest/g.jpg",
        "nest/deep/h.png",
        "[a].jpg",
        "a.jpg",
    ]
    for name in names:
        create(root, name)
    before = snapshot(root)
    result = run(root, options=("--stages", "desc", "--max-depth", "1"))
    assert [Path(p).relative_to(root).as_posix() for p, _ in rows(result)] == [
        "[a].jpg",
        "a.JPG",
        "a.jpg",
        "b.jpeg",
        "c.png",
        "d.webp",
        "e.tif",
        "f.TIFF",
        "nest/g.jpg",
    ]
    literal = rows(run(root / "[a].jpg", options=("--stages", "desc")))
    assert [Path(p).name for p, _ in literal] == ["[a].jpg"]
    assert snapshot(root) == before and calls == []


@pytest.mark.parametrize(
    ("depth_options", "expected"),
    [
        (("--max-depth", "0"), ["a.jpg", "z.png"]),
        (
            ("--max-depth-unlimited",),
            ["a.jpg", "z.png", "nest/b.jpg", "nest/deep/c.png"],
        ),
    ],
)
def test_cli_depth_overrides_restrictive_configuration(
    tmp_path, cli, depth_options, expected
):
    run, calls = cli
    root = tmp_path / "images"
    for name in ("z.png", "nest/deep/c.png", "a.jpg", "nest/b.jpg"):
        create(root, name)
    config = tmp_path / "config.yaml"
    with config.open("a") as stream:
        configured_depth = 2 if depth_options[0] == "--max-depth" else 0
        stream.write(f"selection:\n  max_depth: {configured_depth}\n")
    before = snapshot(root)
    planned = rows(run(root, options=("--stages", "desc", *depth_options)))
    assert [Path(p).relative_to(root).as_posix() for p, _ in planned] == expected
    assert snapshot(root) == before and calls == []


def test_cli_extensions_replace_default_allowlist(tmp_path, cli):
    run, calls = cli
    root = tmp_path / "images"
    for name in ("a.jpg", "b.RAW", "nested/c.png", "nested/d.raw", "e.webp"):
        create(root, name)
    before = snapshot(root)
    planned = rows(run(root, options=("--stages", "desc", "--extensions", "raw,png")))
    assert [Path(p).relative_to(root).as_posix() for p, _ in planned] == [
        "b.RAW",
        "nested/c.png",
        "nested/d.raw",
    ]
    assert snapshot(root) == before and calls == []


def test_pattern_overlap_symlinks_and_depth(tmp_path, cli):
    run, calls = cli
    root = tmp_path / "images"
    a = create(root, "a.jpg")
    b = create(root, "nested/b.jpg")
    create(root, "nested/deep/c.jpg")
    try:
        (root / "link.jpg").symlink_to(a)
        (root / "dirlink").symlink_to(root / "nested", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    before = snapshot(root)
    result = run(
        b, root / "**/*.jpg", root, options=("--stages", "desc", "--max-depth", "1")
    )
    paths = [Path(p) for p, _ in rows(result)]
    assert paths == [b.resolve(), a.resolve()]
    explicit = rows(
        run(root / "link.jpg", root / "a.jpg", options=("--stages", "desc"))
    )
    assert [Path(p) for p, _ in explicit] == [a.resolve()]
    assert snapshot(root) == before and calls == []


def test_initial_admission_order_boundary_matches_execution(tmp_path, cli):
    run, calls = cli
    root = tmp_path / "images"
    for name in ("a.jpg", "b.jpg", "c.jpg", "d.jpg"):
        create(root, name)
    (root / "a.jpg.desc.txt").write_text("already present")
    options = ("--stages", "desc", "--max-work-files", "2", "--verbose")
    before = snapshot(root)
    planned = rows(run(root, options=options))
    assert [Path(p).name for p, _ in planned] == ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
    for (_, line), expected in zip(
        planned, ("NO_LLM_WORK", "ADMITTED", "ADMITTED", "KNOWN_EXCLUDED")
    ):
        assert f"class={expected}" in line
    assert "admission=1 budget=not_reached" in planned[1][1]
    assert "admission=2 budget=reached" in planned[2][1]
    assert snapshot(root) == before and calls == []
    actual = run(root, options=options, dry=False)
    assert actual.returncode == 0, (actual.stdout, actual.stderr)
    assert "summary images=4 admitted=2 no_work=1 excluded=1" in actual.stdout
    assert len(calls) == 2
    assert (root / "b.jpg.desc.txt").exists() and (root / "c.jpg.desc.txt").exists()
    assert not (root / "d.jpg.desc.txt").exists()
    assert (root / "a.jpg.desc.txt").read_text() == "already present"


@pytest.mark.parametrize("kind", ["literal", "directory", "pattern"])
def test_contextual_missing_prerequisite_default(tmp_path, cli, kind):
    run, calls = cli
    root = tmp_path / "images"
    image = create(root, "one.jpg")
    selection = {"literal": image, "directory": root, "pattern": root / "*.jpg"}[kind]
    before = snapshot(root)
    result = run(selection, options=("--stages", "json"), dry=False)
    if kind == "literal":
        assert result.returncode != 0, (result.stdout, result.stderr)
        assert "prerequisite" in (result.stdout + result.stderr).lower()
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert "skip stage=json reason=missing_prerequisite count=1" in result.stdout
    assert snapshot(root) == before and calls == []


@pytest.mark.parametrize("dry", [True, False])
def test_invalid_later_selection_fails_atomically(tmp_path, cli, dry):
    run, calls = cli
    root = tmp_path / "images"
    image = create(root, "one.jpg")
    before = snapshot(root)
    result = run(
        image, root / "missing.jpg", options=("--stages", "desc"), dry=dry, guard=root
    )
    assert result.returncode != 0
    assert "selection error" in result.stderr
    assert (
        "plan complete" not in result.stdout and "summary images=" not in result.stdout
    )
    assert snapshot(root) == before and calls == []
