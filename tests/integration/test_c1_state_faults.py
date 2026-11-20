"""C1 subprocess fault probes; all providers and injected errors are fictional."""

import json
import os
import selectors
import sqlite3
import subprocess
import sys

import pytest
from test_state_b3_primary import initialize, tree_bytes
from test_xmp_cli_b5 import DESCRIPTION, ROOT, envelope, rig, validate_json  # noqa: F401


@pytest.mark.parametrize(
    "fault", ["open", "permission", "read-desc", "read-json", "update", "migration"]
)
def test_injected_state_failures_preserve_primary_and_do_not_substitute(
    rig,  # noqa: F811
    tmp_path,
    fault,
):
    """Inject at the storage boundary in the actual CLI subprocess, not the provider."""
    home = tmp_path / "home"
    initialize(tmp_path, home)
    alternate = tmp_path / ".image-clarus"
    selected_parent = tmp_path / "selected-parent"
    selected_parent.mkdir()
    initialize(selected_parent, home)
    selected = selected_parent / ".image-clarus"
    with sqlite3.connect(selected / "state.sqlite3") as conn:
        conn.execute("INSERT INTO known_categories(path) VALUES ('seed/selected')")
    with sqlite3.connect(alternate / "state.sqlite3") as conn:
        conn.execute("INSERT INTO known_categories(path) VALUES ('seed/alternate')")
    before_selected = tree_bytes(selected)
    before_alternate = tree_bytes(alternate)
    marker = tmp_path / "injection-reached"
    hook = tmp_path / "hook"
    hook.mkdir()
    # _connect permission simulates access denial independent of the test user's privileges.
    # The migration fixture and injected callback are synthetic, not a production migration.
    (hook / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "from image_clarus.state import storage\n"
        f"marker = Path({str(marker)!r})\n"
        f"fault = {fault!r}\n"
        "def fail(*args, **kwargs):\n"
        "    marker.touch()\n"
        "    if fault == 'permission': raise PermissionError('fictional-private-sentinel')\n"
        "    raise storage.StateError('fictional-private-sentinel')\n"
        "if fault in ('open', 'permission'): storage._connect = fail\n"
        "elif fault.startswith('read-'): storage.SQLiteStorage.snapshot_categories = fail\n"
        "elif fault == 'update': storage.SQLiteStorage.add_categories = fail\n"
        "elif fault == 'migration':\n"
        "    storage.FORMAT_VERSION = 2\n"
        "    storage.DOMAIN_VERSION = 2\n"
        "    storage._validate_or_migrate = fail\n"
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Fictional categories: {{state.categories.known}}")
    args = ["--stages", "desc,json", "--state-dir", str(selected)]
    if fault == "read-desc":
        args += ["--desc-prompt", str(prompt)]
    if fault == "read-json":
        args += ["--json-prompt", str(prompt)]
    env = dict(
        os.environ,
        HOME=str(home),
        PYTHONPATH=os.pathsep.join((str(hook), str(ROOT / "src"))),
        NO_PROXY="*",
        no_proxy="*",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(rig.image),
            "--config",
            str(tmp_path / "config.yaml"),
            *args,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert marker.exists(), (fault, result.stdout, result.stderr)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "desc: completed" in result.stdout and "json: completed" in result.stdout
    expected = (
        "category read failed"
        if fault.startswith("read-")
        else "category update failed"
        if fault == "update"
        else "repository unavailable"
    )
    assert (
        "state error" in result.stderr
        and expected in result.stderr
        and "temporary state" in result.stderr
    )
    assert (
        "fictional-private-sentinel" not in result.stderr
        and "Traceback" not in result.stderr
    )
    assert rig.desc.read_bytes() == DESCRIPTION.encode()
    validate_json(rig)
    assert [stage for stage, _ in rig.requests] == ["desc", "json"]
    if fault.startswith("read-"):
        request = json.dumps(rig.requests[0 if fault == "read-desc" else 1][1])
        assert "Fictional categories: []" in request
        assert "seed/selected" not in request and "seed/alternate" not in request
    assert rig.image.read_bytes() == rig.original
    assert not rig.xmp.exists()
    assert tree_bytes(selected) == before_selected
    assert tree_bytes(alternate) == before_alternate


def wait_for_holder(holder, timeout: float = 10):
    """Wait for the single-byte signal sent only after acquiring the write lock."""
    with selectors.DefaultSelector() as selector:
        selector.register(holder.stdout, selectors.EVENT_READ)
        assert selector.select(timeout), "SQLite lock holder readiness timed out"
        assert os.read(holder.stdout.fileno(), 1) == b"L", (
            "SQLite lock holder exited or sent an invalid readiness signal"
        )


def stop_holder(holder, timeout: float = 10):
    """Release the holder, force-stop it if necessary, and always reap it."""
    try:
        holder.communicate(input="release\n", timeout=timeout)
    except BaseException:
        holder.kill()
        holder.communicate()
        raise


@pytest.mark.parametrize("code", ["import time; time.sleep(30)", "pass"])
def test_holder_readiness_failure_is_bounded_and_reaped(code):
    holder = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with pytest.raises(AssertionError, match="SQLite lock holder"):
            wait_for_holder(holder, timeout=0.2)
    finally:
        if "sleep" in code:
            with pytest.raises(subprocess.TimeoutExpired):
                stop_holder(holder, timeout=0.2)
        else:
            stop_holder(holder, timeout=2)
    assert holder.returncode is not None


def test_real_writer_contention_preserves_artifacts_and_alternate(rig, tmp_path):  # noqa: F811
    home = tmp_path / "home"
    initialize(tmp_path, home)
    alternate = tmp_path / ".image-clarus"
    parent = tmp_path / "selected"
    parent.mkdir()
    initialize(parent, home)
    selected = parent / ".image-clarus"
    before_selected = tree_bytes(selected)
    before_alternate = tree_bytes(alternate)
    code = (
        "import os,sqlite3,sys\n"
        "c=sqlite3.connect(sys.argv[1])\n"
        "c.execute('BEGIN IMMEDIATE')\n"
        "os.write(1, b'L')\n"
        "sys.stdin.readline()\n"
        "c.rollback()\n"
        "c.close()\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", code, str(selected / "state.sqlite3")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_holder(holder)
        out, err = rig.finish(
            rig.start("--stages", "desc,json", "--state-dir", str(selected))
        )
        assert "desc: completed" in out and "json: completed" in out
        assert "state error: category update failed" in err and "temporary state" in err
        assert rig.desc.read_bytes() == DESCRIPTION.encode()
        validate_json(rig)
        assert [stage for stage, _ in rig.requests] == ["desc", "json"]
        assert rig.image.read_bytes() == rig.original and not rig.xmp.exists()
    finally:
        stop_holder(holder)
    assert holder.returncode == 0
    assert tree_bytes(selected) == before_selected
    assert tree_bytes(alternate) == before_alternate


@pytest.mark.parametrize(
    "winner", ["flag", "override", "yaml", "cwd", "image", "memory"]
)
def test_cli_state_precedence_and_no_creation(tmp_path, winner):
    from image_clarus.state.storage import initialize as create_store

    work = tmp_path / "work"
    images = tmp_path / "images"
    configs = tmp_path / "configs"
    home = tmp_path / "home"
    for directory in (work, images, configs, home):
        directory.mkdir()
    paths = {
        "flag": work / "flag-state",
        "override": work / "set-state",
        "yaml": configs / "yaml-state",
        "cwd": work / ".image-clarus",
        "image": images / ".image-clarus",
    }
    active = {"flag", "override", "yaml"}
    if winner in {"flag", "override", "yaml", "cwd"}:
        active.add("cwd")
    if winner != "memory":
        active.add("image")
    for name in active:
        create_store(paths[name])
    image = images / "fictional.png"
    image.write_bytes(b"fictional image")
    sidecar = images / "fictional.png.desc.json"
    content = json.dumps(envelope()).encode()
    sidecar.write_bytes(content)
    config = configs / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  text:\n    provider: local\n    model_id: fictional\n"
        "stages:\n  json:\n    model: text\n"
        + (
            "state:\n  directory: yaml-state\n"
            if winner in {"flag", "override", "yaml"}
            else ""
        )
    )
    args = []
    if winner in {"flag", "override"}:
        args += ["--set", "state.directory=set-state"]
    if winner == "flag":
        args += ["--state-dir", "flag-state"]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "json",
            *args,
        ],
        cwd=work,
        env=dict(os.environ, HOME=str(home), PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "json: skipped" in result.stdout and not result.stderr
    assert sidecar.read_bytes() == content and image.read_bytes() == b"fictional image"
    for name in active:
        with sqlite3.connect(paths[name] / "state.sqlite3") as conn:
            rows = conn.execute(
                "SELECT path FROM known_categories ORDER BY path"
            ).fetchall()
        assert rows == ([("color/blue",), ("shape/square",)] if winner == name else [])
    if winner == "memory":
        assert not paths["cwd"].exists() and not paths["image"].exists()


def category_rows(directory):
    with sqlite3.connect(directory / "state.sqlite3") as conn:
        return [
            row[0]
            for row in conn.execute("SELECT path FROM known_categories ORDER BY path")
        ]


@pytest.mark.parametrize(
    "case", ["cwd-nearest", "cwd-ancestor", "image-nearest", "memory"]
)
def test_nested_discovery_real_cli_provider(rig, tmp_path, case):  # noqa: F811
    from image_clarus.state.storage import initialize as create_store

    cwd_root = tmp_path / "cwd-root"
    work = cwd_root / "nested" / "work"
    image_root = tmp_path / "image-root"
    images = image_root / "nested" / "images"
    work.mkdir(parents=True)
    images.mkdir(parents=True)
    image = images / "fictional.png"
    image.write_bytes(rig.original)
    repos = {
        "cwd-near": work.parent / ".image-clarus",
        "cwd-far": cwd_root / ".image-clarus",
        "image-near": images / ".image-clarus",
        "image-far": image_root / ".image-clarus",
    }
    active = {
        "cwd-nearest": {"cwd-near", "cwd-far", "image-near", "image-far"},
        "cwd-ancestor": {"cwd-far", "image-near", "image-far"},
        "image-nearest": {"image-near", "image-far"},
        "memory": set(),
    }[case]
    selected = {
        "cwd-nearest": "cwd-near",
        "cwd-ancestor": "cwd-far",
        "image-nearest": "image-near",
        "memory": None,
    }[case]
    for name in active:
        create_store(repos[name])
        with sqlite3.connect(repos[name] / "state.sqlite3") as conn:
            conn.execute(
                "INSERT INTO known_categories(path) VALUES (?)", (f"seed/{name}",)
            )
    # A nearer uninitialized directory must not be created into a repository.
    if case in {"cwd-ancestor", "image-nearest", "memory"}:
        repos["cwd-near"].mkdir()
        (repos["cwd-near"] / "fictional-marker").write_bytes(b"unchanged")
    before = {name: tree_bytes(path) for name, path in repos.items() if path.exists()}
    prompt = tmp_path / "state-prompt.txt"
    prompt.write_text("Fictional categories: {{state.categories.known}}")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(tmp_path / "config.yaml"),
            "--stages",
            "desc,json",
            "--desc-prompt",
            str(prompt),
            "--json-prompt",
            str(prompt),
        ],
        cwd=work,
        env=dict(
            os.environ,
            HOME=str(tmp_path / "home"),
            PYTHONPATH=str(ROOT / "src"),
            NO_PROXY="*",
            no_proxy="*",
        ),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "desc: completed" in result.stdout and "json: completed" in result.stdout
    assert "state error" not in result.stderr
    assert [stage for stage, _ in rig.requests] == ["desc", "json"]
    expected = f"seed/{selected}" if selected else None
    for _, request in rig.requests:
        text = json.dumps(request)
        assert "Fictional categories:" in text
        if expected:
            assert expected in text
        else:
            assert "Fictional categories: []" in text
        for name in active - ({selected} if selected else set()):
            assert f"seed/{name}" not in text
    for name in active:
        if name == selected:
            assert category_rows(repos[name]) == [
                "color/blue",
                f"seed/{name}",
                "shape/square",
            ]
        else:
            assert tree_bytes(repos[name]) == before[name]
            assert category_rows(repos[name]) == [f"seed/{name}"]
    if case in {"cwd-ancestor", "image-nearest", "memory"}:
        assert tree_bytes(repos["cwd-near"]) == before["cwd-near"]
        assert not (repos["cwd-near"] / "state.sqlite3").exists()
    assert image.read_bytes() == rig.original
    assert (images / "fictional.png.desc.txt").read_bytes() == DESCRIPTION.encode()
    generated = json.loads((images / "fictional.png.desc.json").read_text())
    assert generated["metadata"]["tag_candidates"] == [
        ["shape", "square"],
        ["color", "blue"],
    ]
    assert not (images / "fictional.png.xmp").exists()


@pytest.mark.parametrize("kind", ["missing", "corrupt"])
def test_yaml_explicit_failure_does_not_use_discovered_store(rig, tmp_path, kind):  # noqa: F811
    home = tmp_path / "home"
    initialize(tmp_path, home)
    alternate = tmp_path / ".image-clarus"
    with sqlite3.connect(alternate / "state.sqlite3") as conn:
        conn.execute("INSERT INTO known_categories(path) VALUES ('seed/alternate')")
    before = tree_bytes(alternate)
    selected = tmp_path / "yaml-selected"
    if kind == "corrupt":
        selected.mkdir()
        (selected / "state.sqlite3").write_bytes(b"fictional-corrupt-data")
    selected_before = tree_bytes(selected) if selected.exists() else None
    with (tmp_path / "config.yaml").open("a") as config:
        config.write("state:\n  directory: yaml-selected\n")
    prompt = tmp_path / "state-prompt.txt"
    prompt.write_text("Fictional categories: {{state.categories.known}}")
    out, err = rig.finish(
        rig.start(
            "--stages",
            "desc,json",
            "--desc-prompt",
            str(prompt),
            "--json-prompt",
            str(prompt),
        )
    )
    assert "desc: completed" in out and "json: completed" in out
    assert (
        "state error" in err
        and "repository unavailable" in err
        and "temporary state" in err
    )
    assert (
        "yaml-selected" not in err
        and "fictional-corrupt-data" not in err
        and "Traceback" not in err
    )
    assert [stage for stage, _ in rig.requests] == ["desc", "json"]
    for _, request in rig.requests:
        text = json.dumps(request)
        assert "Fictional categories: []" in text and "seed/alternate" not in text
    assert tree_bytes(alternate) == before
    assert category_rows(alternate) == ["seed/alternate"]
    if selected_before is None:
        assert not selected.exists()
    else:
        assert tree_bytes(selected) == selected_before
    assert rig.desc.read_bytes() == DESCRIPTION.encode()
    validate_json(rig)
    assert rig.image.read_bytes() == rig.original and not rig.xmp.exists()
