"""Slice 3 configuration contracts with fictional inputs."""

import subprocess
import sys

import pytest

from image_clarus.config import ConfigurationError, resolve_config

JSON_SETUP = [
    "providers.p.base_url=http://fictional.example/v1",
    "models.m.provider=p",
    "models.m.model_id=fictional",
    "stages.json.model=m",
]


DESC_SETUP = [
    "providers.p.base_url=http://fictional.example/v1",
    "models.m.provider=p",
    "models.m.model_id=fictional",
    "stages.desc.model=m",
]


@pytest.mark.parametrize(
    ("assignment", "replacement", "field"),
    [
        (
            "stages.json.include_prompt_sha256={unknown: 1}",
            "stages.json.include_prompt_sha256=false",
            "stages.json.include_prompt_sha256",
        ),
        (
            "state.accumulate_categories={unknown: 1}",
            "state.accumulate_categories=true",
            "state.accumulate_categories",
        ),
        (
            'prompt_expansion.macros["state.categories.known"].max_depth={unknown: 1}',
            'prompt_expansion.macros["state.categories.known"].max_depth=1',
            "prompt_expansion.macros.<name>.max_depth",
        ),
        (
            "providers.p.timeout_seconds={unknown: 1}",
            "providers.p.timeout_seconds=60",
            "providers.<name>.timeout_seconds",
        ),
        (
            "providers.p.reasoning_effort_mapping.parameter={unknown: 1}",
            "providers.p.reasoning_effort_mapping={parameter: effort, values: {low: low}}",
            "providers.<name>.reasoning_effort_mapping.parameter",
        ),
        (
            "providers.p.reasoning_effort_mapping.values.off.omit={unknown: 1}",
            'providers.p.reasoning_effort_mapping={parameter: effort, values: {"off": {omit: true}}}',
            "providers.<name>.reasoning_effort_mapping.values",
        ),
    ],
)
def test_unknown_mapping_children_rejected_per_layer(assignment, replacement, field):
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=DESC_SETUP + [assignment, replacement],
        )
    assert field in str(exc.value)
    assert "unknown key" in str(exc.value)
    assert "unknown: 1" not in str(exc.value)


def test_unknown_mapping_child_in_unselected_stage_rejected():
    with pytest.raises(
        ConfigurationError, match=r"stages\.json\.include_prompt_sha256.*unknown key"
    ):
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=DESC_SETUP + ["stages.json.include_prompt_sha256={unknown: 1}"],
        )


def test_state_dir_repairs_scalar_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = resolve_config(
        discovery_paths=(), overrides=["state=bad"], state_dir="safe"
    )
    assert config["state"] == {
        "directory": tmp_path / "safe",
        "accumulate_categories": True,
    }


def test_yaml_leaf_mapping_cannot_be_hidden_by_override(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text("state: {accumulate_categories: {unknown: 1}}\n")
    with pytest.raises(
        ConfigurationError, match=r"state\.accumulate_categories.*unknown key"
    ):
        resolve_config(config_file=file, overrides=["state.accumulate_categories=true"])


def test_permitted_maps_and_replaceable_empty_leaf_mapping():
    config = resolve_config(
        discovery_paths=(),
        stages=("desc",),
        overrides=DESC_SETUP
        + [
            'providers.p.reasoning_effort_mapping={parameter: effort, values: {"off": {omit: true}, low: low}}',
            'prompt_expansion.macros={"state.categories.known": {delimiter: "/", max_depth: 2}}',
            "state.accumulate_categories={}",
            "state.accumulate_categories=false",
        ],
    )
    assert config["providers"]["p"]["reasoning_effort_mapping"]["values"]["off"] == {
        "omit": True
    }
    assert (
        config["prompt_expansion"]["macros"]["state.categories.known"]["max_depth"] == 2
    )
    assert config["state"]["accumulate_categories"] is False


def test_defaults():
    config = resolve_config(discovery_paths=())
    assert config["state"] == {"directory": None, "accumulate_categories": True}
    assert config["prompt_expansion"] == {"macros": {}}
    assert config["stages"]["json"]["include_prompt_sha256"] is False


def test_state_paths_precedence_and_null(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    file = source / "config.yaml"
    file.write_text("state: {directory: ./yaml, accumulate_categories: false}\n")
    assert resolve_config(config_file=file)["state"]["directory"] == source / "yaml"
    assert (
        resolve_config(config_file=file, overrides=["state.directory=./set"])["state"][
            "directory"
        ]
        == cwd / "set"
    )
    assert (
        resolve_config(config_file=file, overrides=["state.directory=null"])["state"][
            "directory"
        ]
        is None
    )
    config = resolve_config(
        config_file=file,
        overrides=["state.directory=./set", "state.accumulate_categories=true"],
        state_dir="./flag",
    )
    assert config["state"] == {"directory": cwd / "flag", "accumulate_categories": True}


def test_macro_override_order_and_distinct_keys(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text(
        'prompt_expansion:\n  macros:\n    state.categories.known: {delimiter: ":", max_depth: 4}\n'
    )
    key = 'prompt_expansion.macros["state.categories.known"]'
    other = 'prompt_expansion.macros["config.example.values"]'
    config = resolve_config(
        config_file=file,
        overrides=[
            key + ".max_depth=1",
            key + '={delimiter: "|"}',
            key + ".max_depth=0",
            other + ".max_depth=null",
            other + '.delimiter="/"',
        ],
    )
    assert config["prompt_expansion"]["macros"] == {
        "state.categories.known": {"delimiter": "|", "max_depth": 0},
        "config.example.values": {"delimiter": "/", "max_depth": None},
    }


@pytest.mark.parametrize(
    "assignment",
    [
        'prompt_expansion.macros["state.categories.known"].max_depth=-1',
        'prompt_expansion.macros["state.categories.known"].max_depth=true',
        'prompt_expansion.macros["state.categories.known"].delimiter=""',
        'prompt_expansion.macros["state.categories.known"].delimiter="\\uD800"',
        "prompt_expansion.macros.state.categories.known.max_depth=2",
        'prompt_expansion.macros["state.private_sentinel"].unknown=2',
        'prompt_expansion.macros["state.private_sentinel].max_depth=2',
        'prompt_expansion.macros["private_sentinel"].max_depth=2',
        "state.accumulate_categories=1",
        'state.directory=""',
    ],
)
def test_invalid_global_settings_are_sanitized(assignment):
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), overrides=[assignment])
    assert "private_sentinel" not in str(exc.value)
    assert "state" in str(exc.value) or "prompt_expansion.macros" in str(exc.value)


def test_invalid_macro_key_is_rejected_even_when_later_replaced(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text(
        'prompt_expansion: {macros: {"state.categories.known": {secret_field: 1}}}\n'
    )
    with pytest.raises(ConfigurationError, match="prompt_expansion.macros"):
        resolve_config(config_file=file, overrides=["prompt_expansion.macros={}"])


def test_category_paths_and_json_stage_isolation():
    config = resolve_config(
        discovery_paths=(),
        stages=("json",),
        overrides=JSON_SETUP
        + [
            "stages.json.preferred_categories=[food, food/desserts/cookies]",
            "stages.json.include_prompt_sha256=true",
        ],
    )
    assert config["stages"]["json"]["preferred_categories"] == [
        "food",
        "food/desserts/cookies",
    ]
    assert config["stages"]["json"]["include_prompt_sha256"] is True
    assert (
        resolve_config(
            discovery_paths=(), overrides=["stages.json.include_prompt_sha256=7"]
        )["stages"]["json"]["include_prompt_sha256"]
        == 7
    )
    with pytest.raises(ConfigurationError, match="include_prompt_sha256"):
        resolve_config(
            discovery_paths=(),
            stages=("json",),
            overrides=JSON_SETUP + ["stages.json.include_prompt_sha256=7"],
        )


@pytest.mark.parametrize(
    "category", ["food//cake", "/food", "food/", "food/ bad", "food/a|b"]
)
def test_invalid_category_path(category):
    with pytest.raises(ConfigurationError, match="preferred_categories"):
        resolve_config(
            discovery_paths=(),
            stages=("json",),
            overrides=JSON_SETUP + [f'stages.json.preferred_categories=["{category}"]'],
        )


def test_macro_parent_child_order_and_duplicate_leaf():
    key = 'prompt_expansion.macros["state.categories.known"]'
    config = resolve_config(
        discovery_paths=(),
        overrides=[
            key + ".max_depth=8",
            'prompt_expansion.macros={"state.categories.known": {delimiter: "|"}}',
            key + ".max_depth=2",
            key + ".max_depth=3",
        ],
    )
    assert config["prompt_expansion"]["macros"]["state.categories.known"] == {
        "delimiter": "|",
        "max_depth": 3,
    }


def test_global_values_can_be_repaired_by_higher_priority(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text(
        'state: {directory: "", accumulate_categories: 12}\n'
        'prompt_expansion: {macros: {"state.categories.known": {max_depth: -1}}}\n'
    )
    config = resolve_config(
        config_file=file,
        overrides=[
            "state.directory=null",
            "state.accumulate_categories=false",
            'prompt_expansion.macros["state.categories.known"].max_depth=0',
        ],
    )
    assert config["state"] == {"directory": None, "accumulate_categories": False}
    assert (
        config["prompt_expansion"]["macros"]["state.categories.known"]["max_depth"] == 0
    )


def test_process_cli_accepts_state_flag_and_rejects_duplicate(tmp_path):
    image = tmp_path / "fictional.jpg"
    image.write_bytes(b"fictional")
    config = tmp_path / "config.yaml"
    config.write_text(
        'providers: {p: {base_url: "http://fictional.example/v1"}}\nmodels: {m: {provider: p, model_id: fictional}}\nstages: {desc: {model: m}}\n'
    )
    # A pre-existing description prevents network activity.
    (tmp_path / "fictional.jpg.desc.txt").write_text("fictional")
    command = [
        sys.executable,
        "-m",
        "image_clarus",
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        "desc",
        "--state-dir",
        "./missing",
    ]
    result = subprocess.run(
        command, cwd=tmp_path, text=True, capture_output=True, timeout=20, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "desc: skipped" in result.stdout
    result = subprocess.run(
        command + ["--set", "state=bad"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "desc: skipped" in result.stdout
    result = subprocess.run(
        command + ["--set", "stages.json.include_prompt_sha256={unknown: 1}"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "stages.json.include_prompt_sha256" in result.stderr
    assert "unknown key" in result.stderr
    assert "unknown: 1" not in result.stderr
    result = subprocess.run(
        command + ["--state-dir", "./other"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "may only be specified once" in result.stderr
    result = subprocess.run(
        command
        + ["--set", 'prompt_expansion.macros["state.categories.known"].max_depth=-1'],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "prompt_expansion.macros.<name>.max_depth" in result.stderr
    assert "state.categories.known" not in result.stderr
