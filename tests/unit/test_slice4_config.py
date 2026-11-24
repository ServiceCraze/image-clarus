import sys

import pytest

from image_clarus import cli
from image_clarus.config import ConfigurationError, resolve_config


def resolve(**kwargs):
    return resolve_config(discovery_paths=(), **kwargs)


def test_process_help_describes_contextual_prerequisite_defaults(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["image-clarus", "process", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    output = " ".join(capsys.readouterr().out.split())
    assert "fail for a single literal file; skip for batch selections" in output


def test_controls_layer_and_repair(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "selection:\n  max_depth: 8\n  extensions: []\npipeline:\n  max_work_files: 7\n  inter_stage_concurrency: true\ncategory_rebuild:\n  max_depth: 4\n"
    )
    c = resolve(
        config_file=path,
        overrides=["selection.max_depth=3", "pipeline.max_work_files=5"],
        max_depth=1,
        extensions="JPG,jpg,png",
        no_max_work_files=True,
        inter_stage_concurrency=False,
    )
    assert c["selection"] == {"max_depth": 1, "extensions": ["jpg", "png"]}
    assert c["pipeline"]["max_work_files"] is None
    assert c["pipeline"]["inter_stage_concurrency"] is False
    assert c["category_rebuild"]["max_depth"] == 4


@pytest.mark.parametrize(
    "override",
    [
        "selection.max_depth=-1",
        "selection.max_depth=true",
        "category_rebuild.max_depth=1.5",
        "pipeline.max_work_files=0",
        "pipeline.max_work_files=false",
        "pipeline.inter_stage_concurrency=1",
        "selection.extensions=[]",
        "selection.extensions=[.jpg]",
        "selection.extensions=['jpg ']",
    ],
)
def test_invalid_controls(override):
    with pytest.raises(ConfigurationError):
        resolve(overrides=[override])


def test_contextual_provenance_and_replacement(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("pipeline:\n  missing_prerequisite: fail\n")
    assert resolve(batch_context=True)["pipeline"]["missing_prerequisite"] == "skip"
    assert resolve()["pipeline"]["missing_prerequisite"] == "fail"
    assert (
        resolve(config_file=path, batch_context=True)["pipeline"][
            "missing_prerequisite"
        ]
        == "fail"
    )
    assert (
        resolve(config_file=path, batch_context=True, overrides=["pipeline={}"])[
            "pipeline"
        ]["missing_prerequisite"]
        == "skip"
    )
    assert (
        resolve(
            config_file=path,
            batch_context=True,
            overrides=["pipeline={}", "pipeline.missing_prerequisite=fail"],
        )["pipeline"]["missing_prerequisite"]
        == "fail"
    )
    assert (
        resolve(
            batch_context=True,
            overrides=["pipeline.missing_prerequisite=skip"],
            missing_prerequisite="fail",
        )["pipeline"]["missing_prerequisite"]
        == "fail"
    )


def test_rebuild_depth_and_macro_are_independent():
    c = resolve(
        overrides=[
            "selection.max_depth=3",
            "category_rebuild.max_depth=5",
            'prompt_expansion.macros["state.categories"].max_depth=2',
        ],
        max_depth=0,
        rebuild=True,
    )
    assert c["selection"]["max_depth"] == 3
    assert c["category_rebuild"]["max_depth"] == 0
    assert c["prompt_expansion"]["macros"]["state.categories"]["max_depth"] == 2


def test_static_xmp_does_not_probe(monkeypatch):
    from image_clarus import config

    monkeypatch.setattr(config.shutil, "which", lambda _: pytest.fail("runtime probe"))
    resolve(stages=("xmp",), runtime_preflight=False)


def test_management_ignores_unselected_invalid_values(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "providers:\n  fictional:\n    timeout_seconds: broken\nstages:\n  xmp:\n    tag_limit: wrong\n"
    )
    resolve(config_file=path, management=True, rebuild=True)


@pytest.mark.parametrize(
    "args",
    [
        ["process", "x", "--dry-run", "--dry-run"],
        ["process", "x", "--max-depth", "1", "--max-depth-unlimited"],
        ["state", "categories", "rebuild", "x", "-i", "--ignore-case"],
    ],
)
def test_repeated_or_conflicting_flags_are_usage_errors(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["image-clarus", *args])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_management_is_not_reported_as_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["image-clarus", "state", "categories", "list"])
    assert cli.main() == 2
    assert "not implemented" in capsys.readouterr().err


def test_dry_run_does_not_open_state_or_probe_xmp(tmp_path, monkeypatch, capsys):
    from image_clarus import config
    from image_clarus.state.service import StateService

    image = tmp_path / "fictional.jpg"
    image.write_bytes(b"fictional")
    settings = tmp_path / "settings.yaml"
    settings.write_text("{}")
    monkeypatch.setattr(config.shutil, "which", lambda _: pytest.fail("runtime probe"))
    monkeypatch.setattr(
        StateService, "select", lambda *a, **k: pytest.fail("state opened")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--stages",
            "xmp",
            "--config",
            str(settings),
            "--dry-run",
        ],
    )
    assert cli.main() == 2
    assert "not implemented" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["process", "a", "--verbose", "b"],
        ["process", "a", "--", "b"],
        ["process", ""],
        ["process", "a", "--regenerate", "--regenerate"],
        ["process", "a", "--no-inter-stage-concurrency", "--inter-stage-concurrency"],
        ["state", "categories", "rebuild", "a", "--", "b"],
        ["state", "categories", "rebuild", ""],
    ],
)
def test_selection_grammar_rejections(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["image-clarus", *args])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["process", "--stages", "xmp", "--dry-run", "a", "b", "--verbose"],
        ["process", "--stages", "xmp", "--dry-run", "--", "-a", "b"],
        ["state", "categories", "rebuild", "--max-depth", "1", "a", "b"],
        ["state", "categories", "rebuild", "--", "-a", "b"],
    ],
)
def test_contiguous_selections_reach_stub(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["image-clarus", *args])
    monkeypatch.setattr("image_clarus.config.discovery_locations", lambda: ())
    assert cli.main() == 2
    assert "not implemented" in capsys.readouterr().err


@pytest.mark.parametrize("rebuild", [False, True])
def test_management_isolates_processing_values_but_validates_state(tmp_path, rebuild):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "state:\n  directory: target\n  accumulate_categories: broken\n"
        "selection:\n  extensions: []\npipeline:\n  max_work_files: 0\n"
        "providers:\n  test:\n    timeout_seconds: broken\n"
        "stages:\n  xmp:\n    tag_limit: wrong\n"
    )
    config = resolve(config_file=path, management=True, rebuild=rebuild)
    assert config["state"]["directory"] == tmp_path / "target"
    with pytest.raises(ConfigurationError, match="state.directory"):
        resolve(config_file=path, overrides=["state.directory=42"], management=True)
    with pytest.raises(ConfigurationError, match="unknown"):
        resolve(config_file=path, overrides=["pipeline.fictional=1"], management=True)
    if rebuild:
        with pytest.raises(ConfigurationError, match="category_rebuild.max_depth"):
            resolve(
                overrides=["category_rebuild.max_depth=-1"],
                management=True,
                rebuild=True,
            )


@pytest.mark.parametrize("bad_config", [False, True])
def test_dry_run_stub_never_reads_input_or_runs_services(
    tmp_path, monkeypatch, capsys, bad_config
):
    from pathlib import Path

    from image_clarus import config, pipeline
    from image_clarus.artifacts import ArtifactService
    from image_clarus.state.service import StateService

    image = tmp_path / "input.jpg"
    sidecar = tmp_path / "input.desc.json"
    image.write_bytes(b"input sentinel")
    sidecar.write_bytes(b"sidecar sentinel")
    settings = tmp_path / "settings.yaml"
    settings.write_text("selection:\n  max_depth: -1\n" if bad_config else "{}")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path in (image, sidecar):
            pytest.fail("input content opened")
        return original_open(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("execution service or preflight invoked")

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(config.shutil, "which", forbidden)
    monkeypatch.setattr(config, "_probe_exiftool", forbidden)
    monkeypatch.setattr(StateService, "select", forbidden)
    monkeypatch.setattr(ArtifactService, "write", forbidden)
    monkeypatch.setattr(pipeline, "run_pipeline", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--stages",
            "xmp",
            "--config",
            str(settings),
            "--dry-run",
        ],
    )
    assert cli.main() == 2
    assert (
        "selection.max_depth" if bad_config else "not implemented"
    ) in capsys.readouterr().err
    monkeypatch.setattr(Path, "open", original_open)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
