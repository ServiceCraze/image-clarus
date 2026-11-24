import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_signal_during_path_validation_takes_precedence_over_config_error(
    tmp_path, monkeypatch
):
    import signal

    from image_clarus import cli

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    resolve = Path.resolve

    def interrupted_resolve(path, *args, **kwargs):
        if path == image:
            os.kill(os.getpid(), signal.SIGTERM)
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", interrupted_resolve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(tmp_path / "missing"),
            "--stages",
            "desc",
        ],
    )
    assert cli.main() == 143


def test_signal_during_summary_changes_exit_status(tmp_path, monkeypatch, capsys):
    import builtins
    import signal

    from image_clarus import cli

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    Path(str(image) + ".desc.txt").write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    real_print = builtins.print

    def interrupt_summary(*args, **kwargs):
        if args and str(args[0]).startswith("desc: "):
            os.kill(os.getpid(), signal.SIGTERM)
        return real_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", interrupt_summary)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
    )
    assert cli.main() == 143
    assert capsys.readouterr().out == "desc: skipped — reason=output_exists\n"


def test_top_level_help_lists_subcommands():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "process" in result.stdout and "search" in result.stdout


def test_process_help_describes_frozen_options():
    result = run_cli("process", "--help")
    assert result.returncode == 0
    for expected in (
        "IMAGE",
        "--config",
        "--stages",
        "--set",
        "--desc-prompt",
        "--json-prompt",
        "--json-schema",
        "--regenerate",
        "--missing-prerequisite",
        "desc,json,xmp",
        "fail",
        "create-only",
        "search",
    ):
        assert expected in result.stdout


def test_search_help_works():
    assert run_cli("search", "--help").returncode == 0


def test_search_stub_and_unknown_arguments():
    result = run_cli("search")
    assert (result.returncode, result.stdout, result.stderr) == (
        3,
        "",
        "search is not implemented in Slice 1\n",
    )
    assert run_cli("search", "unexpected").returncode == 2


def test_version_uses_installed_metadata():
    result = run_cli("--version")
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "image-clarus 0.3.10\n",
        "",
    )


def test_version_missing_metadata_is_configuration_error(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-S", "-m", "image_clarus", "--version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert (
        result.stderr
        == "image-clarus: installation error: version metadata unavailable\n"
    )


def test_process_rejects_missing_image(tmp_path):
    result = run_cli("process", str(tmp_path / "missing.png"))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "image" in result.stderr.lower()


def test_process_desc_skips_existing_output(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    sidecar = tmp_path / "image.png.desc.txt"
    sidecar.write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  vision:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: vision\n"
    )
    result = run_cli("process", str(image), "--config", str(config), "--stages", "desc")
    assert result.returncode == 0
    assert result.stdout == "desc: skipped — reason=output_exists\n"
    assert image.read_bytes() == b"synthetic"


def test_json_only_missing_prerequisite_is_failure(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  text:\n    provider: local\n    model_id: synthetic\nstages:\n  json:\n    model: text\n"
    )
    result = run_cli("process", str(image), "--config", str(config), "--stages", "json")
    assert result.returncode == 1
    assert result.stdout == "json: failed — category=missing_prerequisite; message=\n"
    assert not (tmp_path / "image.png.desc.txt").exists()


def test_combined_execution_persists_and_rereads_description(tmp_path):
    import hashlib
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            content = (
                "persisted description" if len(requests) == 1 else '{"caption":"ok"}'
            )
            data = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": content},
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        image = tmp_path / "image.png"
        image.write_bytes(b"synthetic")
        schema = tmp_path / "schema.json"
        schema.write_text('{"type":"object","required":["caption"]}')
        config = tmp_path / "config.yaml"
        config.write_text(
            f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n  json:\n    model: m\n"
        )
        result = run_cli(
            "process",
            str(image),
            "--config",
            str(config),
            "--json-schema",
            str(schema),
            "--stages",
            "desc,json",
        )
        assert result.returncode == 0, result.stderr
        assert (
            result.stdout
            == f"desc: completed — output={json.dumps(str(image) + '.desc.txt')}\njson: completed — output={json.dumps(str(image) + '.desc.json')}\n"
        )
        parts = requests[1]["messages"][1]["content"]
        assert len(parts) == 1
        assert json.loads(parts[0]["text"]) == {
            "description": "persisted description",
            "schema": json.loads(schema.read_text()),
        }
        data = json.loads(Path(str(image) + ".desc.json").read_text())
        assert (
            data["provenance"]["description_sha256"]
            == hashlib.sha256(b"persisted description").hexdigest()
        )
        assert image.read_bytes() == b"synthetic"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_missing_prerequisite_flag_overrides_set(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  text:\n    provider: local\n    model_id: synthetic\nstages:\n  json:\n    model: text\n"
    )
    result = run_cli(
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        "json",
        "--set",
        "pipeline.missing_prerequisite=fail",
        "--missing-prerequisite",
        "skip",
    )
    assert result.returncode == 0
    assert result.stdout == "json: skipped — reason=missing_prerequisite\n"


def test_duplicate_stage_selection_is_usage_error(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    result = run_cli("process", str(image), "--stages", "desc,desc")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "stage" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_missing_config_is_sanitized_preflight_error(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    result = run_cli(
        "process", str(image), "--config", str(tmp_path / "absent"), "--stages", "desc"
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "configuration" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_duplicate_singleton_option_is_usage_error(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    Path(str(image) + ".desc.txt").write_text("existing")
    result = run_cli(
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        "desc",
        "--stages",
        "desc",
    )
    assert result.returncode == 2
    assert result.stdout == ""


def test_regenerate_overrides_create_only(tmp_path):
    image = tmp_path / "image.xyz"
    image.write_bytes(b"synthetic")
    Path(str(image) + ".desc.txt").write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    result = run_cli(
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        "desc",
        "--regenerate",
    )
    assert result.returncode == 1
    assert "category=unsupported_image" in result.stdout
    assert Path(str(image) + ".desc.txt").read_text() == "existing"


import pytest


@pytest.mark.parametrize(
    "selection,expected",
    [
        (None, ("desc", "json", "xmp")),
        ("xmp", ("xmp",)),
        ("xmp,json", ("json", "xmp")),
        ("xmp,desc", ("desc", "xmp")),
        ("xmp,json,desc", ("desc", "json", "xmp")),
        ("desc,json", ("desc", "json")),
        ("desc", ("desc",)),
        ("json", ("json",)),
    ],
)
def test_cli_selects_only_requested_stages_and_preflights_them(
    tmp_path, monkeypatch, capsys, selection, expected
):
    from image_clarus import cli, config
    from image_clarus.results import StageResult
    from image_clarus.stages import description, structure, xmp

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    calls = []
    preflight = []

    def resolve(**kwargs):
        preflight.append(kwargs["stages"])
        return {
            "logging": {"level": "WARNING"},
            "pipeline": {"backup_retention": "remove"},
            "state": {"directory": None, "accumulate_categories": True},
        }

    def fake(name):
        def run(image, config, services):
            calls.append(name)
            return StageResult(name, "skipped", reason_code="no_change")

        return run

    monkeypatch.setattr(config, "resolve_config", resolve)
    monkeypatch.setattr(description, "run_description", fake("desc"))
    monkeypatch.setattr(structure, "run_structure", fake("json"))
    monkeypatch.setattr(xmp, "run_xmp", fake("xmp"), raising=False)
    args = ["image-clarus", "process", str(image)]
    if selection is not None:
        args += ["--stages", selection]
    monkeypatch.setattr(sys, "argv", args)

    assert cli.main() == 0
    assert preflight == [expected]
    assert calls == list(expected)
    output = capsys.readouterr()
    assert output.out == "".join(
        f"{stage}: skipped — reason=no_change\n" for stage in expected
    )
    assert output.err == ""


@pytest.mark.parametrize(
    ("stage", "option"), [("desc", "--desc-prompt"), ("json", "--json-prompt")]
)
def test_selected_prompt_override_is_preflight_validated(tmp_path, stage, option):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  {stage}:\n    model: m\n"
    )
    result = run_cli(
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        stage,
        option,
        str(tmp_path / "absent"),
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_sigterm_during_request_does_not_publish(tmp_path):
    import json
    import signal
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    entered = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            entered.set()
            release.wait(10)
            data = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "not published",
                            },
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert entered.wait(10)
        proc.send_signal(signal.SIGTERM)
        release.set()
        stdout, stderr = proc.communicate(timeout=15)
        assert proc.returncode == 143, stderr
        assert stdout == "desc: skipped — reason=interrupted\n"
        assert not Path(str(image) + ".desc.txt").exists()
    finally:
        release.set()
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize(
    "option,value",
    [
        ("--config", "f"),
        ("--desc-prompt", "f"),
        ("--json-prompt", "f"),
        ("--json-schema", "f"),
        ("--missing-prerequisite", "skip"),
    ],
)
def test_other_singleton_options_reject_duplicates(tmp_path, option, value):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    result = run_cli("process", str(image), option, value, option, value)
    assert result.returncode == 2
    assert "may only be specified once" in result.stderr


def test_glob_characters_are_rejected_even_if_file_exists(tmp_path):
    image = tmp_path / "im*.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    Path(str(image) + ".desc.txt").write_text("existing")
    result = run_cli("process", str(image), "--config", str(config), "--stages", "desc")
    assert result.returncode == 2
    assert "image" in result.stderr.lower()


def test_failure_message_is_single_line(tmp_path, monkeypatch, capsys):
    from image_clarus import cli
    from image_clarus.results import StageResult
    from image_clarus.stages import description

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    monkeypatch.setattr(
        description,
        "run_description",
        lambda *args: StageResult(
            "desc", "failed", error_category="file_io", message="first\nsecond\rthird"
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
    )
    assert cli.main() == 1
    assert (
        capsys.readouterr().out
        == "desc: failed — category=file_io; message=first second third\n"
    )


def test_authentication_preflight_exits_one_without_summary(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n    api_key_env: IMAGE_CLARUS_TEST_UNSET_7291\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    result = run_cli("process", str(image), "--config", str(config), "--stages", "desc")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("selection", ["", "desc,", "unknown", "DESC"])
def test_invalid_stage_lists_are_rejected(tmp_path, selection):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    result = run_cli("process", str(image), "--stages", selection)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "stage" in result.stderr.lower()


def test_exiftool_preflight_is_required_only_for_selected_xmp(tmp_path, monkeypatch):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    Path(str(image) + ".desc.txt").write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  m:\n    provider: local\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\n"
    )
    monkeypatch.setenv("PATH", str(tmp_path))
    desc = run_cli("process", str(image), "--config", str(config), "--stages", "desc")
    assert (desc.returncode, desc.stdout, desc.stderr) == (
        0,
        "desc: skipped — reason=output_exists\n",
        "",
    )
    selected = run_cli(
        "process", str(image), "--config", str(config), "--stages", "xmp"
    )
    assert selected.returncode == 2
    assert selected.stdout == ""
    assert "ExifTool" in selected.stderr
    assert "Traceback" not in selected.stderr


@pytest.mark.parametrize(
    "policy,code,line",
    [
        ("fail", 1, "xmp: failed — category=missing_prerequisite; message=\n"),
        ("skip", 0, "xmp: skipped — reason=missing_prerequisite\n"),
    ],
)
def test_xmp_only_missing_json_uses_policy_without_model_or_auto_expansion(
    tmp_path, monkeypatch, policy, code, line
):
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text("{}\n")
    executable = tmp_path / "exiftool"
    executable.write_text("#!/bin/sh\nprintf '12.34\\n'\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    result = run_cli(
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        "xmp",
        "--missing-prerequisite",
        policy,
        "--regenerate",
    )
    assert (result.returncode, result.stdout, result.stderr) == (code, line, "")
    assert image.read_bytes() == b"synthetic"
    assert not Path(str(image) + ".desc.txt").exists()
    assert not Path(str(image) + ".desc.json").exists()
    assert not Path(str(image) + ".xmp").exists()


@pytest.mark.parametrize("signum", [2, 15])
@pytest.mark.parametrize("stage", ["desc", "json", "xmp"])
def test_interrupted_stage_failure_is_reported_as_skipped(
    tmp_path, monkeypatch, capsys, signum, stage
):
    from image_clarus import cli
    from image_clarus.results import StageResult
    from image_clarus.stages import description, structure, xmp

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  m:\n    provider: local\n    model_id: synthetic\n"
        + (f"stages:\n  {stage}:\n    model: m\n" if stage != "xmp" else "")
    )
    if stage == "xmp":
        executable = tmp_path / "exiftool"
        executable.write_text("#!/bin/sh\nprintf '12.34\\n'\n")
        executable.chmod(0o755)
        monkeypatch.setenv("PATH", str(tmp_path))

    def interrupted_stage(image_path, settings, services):
        os.kill(os.getpid(), signum)
        assert services.stop.signum == signum
        return StageResult(stage, "failed", error_category="file_io")

    module, name = {
        "desc": (description, "run_description"),
        "json": (structure, "run_structure"),
        "xmp": (xmp, "run_xmp"),
    }[stage]
    monkeypatch.setattr(module, name, interrupted_stage, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            stage,
        ],
    )
    assert cli.main() == 128 + signum
    assert capsys.readouterr().out == f"{stage}: skipped — reason=interrupted\n"


def test_signal_before_artifact_write_prevents_publication(
    tmp_path, monkeypatch, capsys
):
    import signal

    from image_clarus import cli
    from image_clarus.artifacts import ArtifactError
    from image_clarus.results import StageResult
    from image_clarus.stages import description

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )

    def fake_stage(image, config, services):
        os.kill(os.getpid(), signal.SIGTERM)
        try:
            services.artifacts.write(
                Path(str(image) + ".desc.txt"), b"data", lambda data: True
            )
        except ArtifactError as error:
            return StageResult("desc", "failed", error_category=error.category)
        return StageResult(
            "desc", "completed", output_path=Path(str(image) + ".desc.txt")
        )

    monkeypatch.setattr(description, "run_description", fake_stage)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
    )
    assert cli.main() == 143
    assert capsys.readouterr().out == "desc: skipped — reason=interrupted\n"
    assert not Path(str(image) + ".desc.txt").exists()


@pytest.mark.parametrize("signum", [2, 15])
def test_signal_interrupts_stalled_provider_without_publication(tmp_path, signum):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            entered.set()
            release.wait(20)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n  json:\n    model: m\n"
    )
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc,json",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert entered.wait(15)
        proc.send_signal(signum)
        try:
            stdout, stderr = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            pytest.fail("CLI remained blocked while provider stalled")
        assert proc.returncode == 128 + signum, stderr
        assert (
            stdout
            == "desc: skipped — reason=interrupted\njson: skipped — reason=interrupted\n"
        )
        assert not Path(str(image) + ".desc.txt").exists()
        assert not Path(str(image) + ".desc.json").exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        release.set()
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize("signum", [2, 15])
def test_signal_during_preflight_reaps_worker(tmp_path, signum):
    import time

    marker = tmp_path / "worker.pid"
    worker_code = f"import os,time;open({str(marker)!r},'w').write(str(os.getpid()));time.sleep(60)"
    (tmp_path / "sitecustomize.py").write_text(
        "import subprocess, sys\n"
        "old = subprocess.Popen\n"
        "def spawn(args, *a, **kw):\n"
        "    if isinstance(args, list) and 'image_clarus.schema_worker' in args:\n"
        f"        args = [sys.executable, '-c', {worker_code!r}]\n"
        "    return old(args, *a, **kw)\n"
        "subprocess.Popen = spawn\n"
    )
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  json:\n    model: m\n"
    )
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}')
    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join((str(tmp_path), str(ROOT / "src")))
    )
    proc = subprocess.Popen(
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
            "--json-schema",
            str(schema),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    worker = None
    try:
        deadline = time.monotonic() + 15
        while (
            not marker.exists() and proc.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert marker.exists()
        worker = int(marker.read_text())
        proc.send_signal(signum)
        stdout, stderr = proc.communicate(timeout=3)
        assert proc.returncode == 128 + signum, stderr
        assert stdout == ""
        with pytest.raises(ProcessLookupError):
            os.kill(worker, 0)
        assert not Path(str(image) + ".desc.json").exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        if worker is not None:
            try:
                os.kill(worker, 9)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("credential_kind", ["inline", "environment"])
def test_summary_redacts_credentials_in_failure_message(
    tmp_path, monkeypatch, capsys, credential_kind
):
    from image_clarus import cli
    from image_clarus.results import StageResult
    from image_clarus.stages import description

    secret = "synthetic-secret-for-redaction"
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    key = (
        f"api_key: {secret}"
        if credential_kind == "inline"
        else "api_key_env: B8_TEST_SECRET"
    )
    monkeypatch.setenv("B8_TEST_SECRET", secret)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n    {key}\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    monkeypatch.setattr(
        description,
        "run_description",
        lambda *args: StageResult(
            "desc", "failed", error_category="file_io", message="error " + secret
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
    )
    assert cli.main() == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert "[REDACTED]" in output.out


@pytest.mark.parametrize("signum", [2, 15])
def test_signal_during_write_finishes_transaction_safely(tmp_path, signum):
    import time

    marker = tmp_path / "write-entered"
    release = tmp_path / "write-release"
    (tmp_path / "sitecustomize.py").write_text(
        "import time\nfrom pathlib import Path\n"
        "from image_clarus.artifacts import ArtifactService\n"
        "old = ArtifactService._point\n"
        "def point(self, name):\n"
        "    if name == 'destination_replace':\n"
        f"        Path({str(marker)!r}).touch()\n"
        f"        while not Path({str(release)!r}).exists(): time.sleep(0.01)\n"
        "    return old(self, name)\n"
        "ArtifactService._point = point\n"
    )
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    destination = Path(str(image) + ".desc.txt")
    destination.write_text("original")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    script = (
        "import sys; from pathlib import Path; from image_clarus import cli; "
        "from image_clarus.results import StageResult; from image_clarus.stages import description; "
        + "defn = "
        + repr(
            'def stage(image, config, services):\n path = Path(str(image) + ".desc.txt")\n services.artifacts.write(path, b"new", lambda data: True)\n return StageResult("desc", "completed", output_path=path)'
        )
        + "; "
        "exec(defn); description.run_description = stage; "
        f"sys.argv = {['image-clarus', 'process', str(image), '--config', str(config), '--stages', 'desc', '--regenerate']!r}; "
        "raise SystemExit(cli.main())"
    )
    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join((str(tmp_path), str(ROOT / "src")))
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not marker.exists() and proc.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert marker.exists()
        proc.send_signal(signum)
        time.sleep(0.1)
        assert proc.poll() is None
        assert destination.read_text() == "original"
        release.touch()
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 128 + signum, stderr
        assert "desc: completed" in stdout
        assert destination.read_text() == "new"
        assert not list(tmp_path.glob("*.tmp"))
    finally:
        release.touch()
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
