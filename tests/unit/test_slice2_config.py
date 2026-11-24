"""Slice 2 configuration preflight (all values synthetic)."""

import pytest

from image_clarus.config import ConfigurationError, resolve_config


def test_slice2_defaults_and_typed_root_precedence(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('stages: {xmp: {tag_root: "file"}}\n')
    defaults = resolve_config(discovery_paths=())
    assert defaults["stages"]["xmp"]["tag_root"] == "ai"
    config = resolve_config(config_file=path, overrides=['stages.xmp.tag_root=""'])
    assert config["stages"]["xmp"]["tag_root"] == ""
    assert config["stages"]["json"]["preferred_categories"] == []


def test_xmp_preflight_ignores_unused_stage_shapes_and_needs_no_model(
    tmp_path, monkeypatch
):
    tool = tmp_path / "exiftool"
    tool.write_text('#!/bin/sh\nprintf "13.00\\n"\n')
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    path = tmp_path / "config.yaml"
    path.write_text(
        "stages: {desc: 42, json: {preferred_categories: bad, schema_file: missing}}\n"
    )
    config = resolve_config(config_file=path, stages=("xmp",), regenerate=True)
    assert config["stages"]["xmp"]["tag_root"] == "ai"
    assert "regenerate" not in config["stages"]["xmp"]


@pytest.mark.parametrize(
    "assignment",
    [
        'tag_root=" bad"',
        "tag_root=null",
        'tag_root="bad/path"',
        "tag_limit=-1",
        "tag_limit=true",
        "tag_limit=1.5",
        "tag_policy=wrong",
        "title_policy=add",
        "caption_policy=add",
        "caption_author_policy=add",
        "caption_author=12",
        'custom_title_property=""',
        "custom_caption_property=42",
        'custom_tags_property="\\uD800"',
    ],
)
def test_xmp_invalid_values_fail_before_tool_discovery(assignment, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(), stages=("xmp",), overrides=["stages.xmp." + assignment]
        )
    assert "stages.xmp." + assignment.split("=")[0] in str(exc.value)
    assert "ExifTool" not in str(exc.value)


@pytest.mark.parametrize(
    "categories", ["[one, one]", '[" bad"]', '["bad|value"]', "[42]", "invalid"]
)
def test_selected_json_rejects_invalid_categories(categories):
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("json",),
            overrides=[
                "providers.p.base_url=http://fictional.example/v1",
                "models.m.provider=p",
                "models.m.model_id=fictional",
                "stages.json.model=m",
                "stages.json.preferred_categories=" + categories,
            ],
        )
    assert "stages.json.preferred_categories" in str(exc.value)


@pytest.fixture
def fake_exiftool(tmp_path, monkeypatch):
    tool = tmp_path / "exiftool"
    tool.write_text('#!/bin/sh\nprintf "13.00\\n"\n')
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    return tool


def test_selected_xmp_preserves_yaml_empty_root(fake_exiftool, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('stages: {xmp: {tag_root: ""}}\n')
    config = resolve_config(config_file=path, stages=("xmp",))
    assert config["stages"]["xmp"]["tag_root"] == ""


def test_json_preflight_does_not_probe_exiftool(monkeypatch):
    import image_clarus.config as config_module

    def no_probe(_):
        raise AssertionError("unused XMP dependency was probed")

    monkeypatch.setattr(config_module.shutil, "which", no_probe)
    config = resolve_config(
        discovery_paths=(),
        stages=("json",),
        overrides=[
            "providers.p.base_url=http://fictional.example/v1",
            "models.m.provider=p",
            "models.m.model_id=fictional",
            "stages.json.model=m",
            "stages.json.preferred_categories=[wildlife]",
        ],
    )
    assert config["stages"]["json"]["preferred_categories"] == ["wildlife"]


@pytest.mark.parametrize("policy", ["add", "new", "overwrite", "disabled"])
def test_tag_policy_valid_with_empty_root(fake_exiftool, policy):
    result = resolve_config(
        discovery_paths=(),
        stages=("xmp",),
        overrides=[
            'stages.xmp.tag_root=""',
            f"stages.xmp.tag_policy={policy}",
            "stages.xmp.tag_limit=0",
            'stages.xmp.caption_author=" fictional "',
            'stages.xmp.custom_title_property="title.key"',
        ],
    )
    assert result["stages"]["xmp"]["tag_policy"] == policy
    assert result["stages"]["xmp"]["caption_author"] == " fictional "
    assert result["stages"]["xmp"]["custom_title_property"] == "title.key"


@pytest.mark.parametrize("policy", ["new", "overwrite", "disabled"])
def test_independent_field_policies(fake_exiftool, policy):
    result = resolve_config(
        discovery_paths=(),
        stages=("xmp",),
        overrides=[
            f"stages.xmp.{field}={policy}"
            for field in ("title_policy", "caption_policy", "caption_author_policy")
        ],
    )
    assert all(
        result["stages"]["xmp"][field] == policy
        for field in ("title_policy", "caption_policy", "caption_author_policy")
    )


def test_missing_and_failing_exiftool_are_sanitized(fake_exiftool):
    fake_exiftool.write_text(
        '#!/bin/sh\nprintf "fictional-private-output" >&2\nexit 1\n'
    )
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), stages=("xmp",))
    assert "ExifTool" in str(exc.value)
    assert "fictional-private-output" not in str(exc.value)
    fake_exiftool.unlink()
    with pytest.raises(ConfigurationError, match="ExifTool"):
        resolve_config(discovery_paths=(), stages=("xmp",))


def test_unselected_xmp_shape_is_isolated_but_unknown_keys_are_not(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("stages: {xmp: 42}\n")
    resolve_config(
        config_file=path,
        stages=("desc",),
        overrides=[
            "providers.p.base_url=http://fictional.example/v1",
            "models.m.provider=p",
            "models.m.model_id=fictional",
            "stages.desc.model=m",
        ],
    )
    path.write_text("stages: {xmp: {fictional_unknown: 1}}\n")
    with pytest.raises(ConfigurationError, match="unknown key"):
        resolve_config(config_file=path, stages=("desc",))


def test_json_categories_override_preserves_order_and_case():
    config = resolve_config(
        discovery_paths=(),
        stages=("json",),
        overrides=[
            "providers.p.base_url=http://fictional.example/v1",
            "models.m.provider=p",
            "models.m.model_id=fictional",
            "stages.json.model=m",
            'stages.json.preferred_categories=[" bad"]',
            'stages.json.preferred_categories=["Bird", "bird"]',
        ],
    )
    assert config["stages"]["json"]["preferred_categories"] == ["Bird", "bird"]


def test_timeout_is_sanitized_and_uses_bounded_shell_free_probe(
    fake_exiftool, monkeypatch
):
    import image_clarus.config as config_module

    fake_exiftool.write_text(
        '#!/bin/sh\nprintf "fictional-private-output" >&2\nexec /bin/sleep 5\n'
    )
    monkeypatch.setattr(config_module, "_EXIFTOOL_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), stages=("xmp",))
    assert "ExifTool" in str(exc.value)
    assert "fictional-private-output" not in str(exc.value)


@pytest.mark.parametrize(
    "overrides",
    [
        ["stages.xmp.tag_root.private_nested=1"],
        ["stages.xmp.tag_root.private_nested=1", "stages.xmp.tag_root=ai"],
        [
            "pipeline.backup_retention.private_nested=1",
            "pipeline.backup_retention=remove",
        ],
    ],
)
def test_unknown_nested_override_is_rejected_in_each_layer(overrides):
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), overrides=overrides)
    assert "private_nested" not in str(exc.value)


def test_dedicated_missing_prerequisite_repairs_lower_priority_global_shape():
    config = resolve_config(
        discovery_paths=(), overrides=["pipeline=42"], missing_prerequisite="skip"
    )
    assert config["pipeline"]["missing_prerequisite"] == "skip"


def test_exiftool_probe_rejects_executable_with_no_version(tmp_path, monkeypatch):
    tool = tmp_path / "exiftool"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ConfigurationError, match="ExifTool"):
        resolve_config(discovery_paths=(), stages=("xmp",))


def test_exiftool_probe_rejects_oversized_output_without_disclosing_it(
    fake_exiftool,
):
    fake_exiftool.write_text(
        '#!/bin/sh\ni=0\nwhile [ "$i" -lt 200 ]; do printf "x"; i=$((i+1)); done\n'
    )
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), stages=("xmp",))
    assert "ExifTool" in str(exc.value)
    assert "xxxxxxxxxx" not in str(exc.value)


def test_exiftool_preflight_does_not_require_selectable_pipes(
    fake_exiftool, monkeypatch
):
    import selectors

    def unsupported():
        raise OSError("pipe selection unavailable")

    monkeypatch.setattr(selectors, "DefaultSelector", unsupported)
    resolve_config(discovery_paths=(), stages=("xmp",))


@pytest.mark.parametrize(
    ("body", "timeout"),
    [
        ('printf "fictional-private-output"; exec /bin/sleep 5', 0.2),
        ('printf "%0130d" 0; exec /bin/sleep 5', 2),
        ('printf "12.34"; exec /bin/sleep 5', 0.2),
    ],
)
def test_probe_reaps_child_on_timeout_or_oversize(
    fake_exiftool, monkeypatch, body, timeout
):
    import subprocess
    import time

    import image_clarus.config as config_module

    fake_exiftool.write_text(f"#!/bin/sh\n{body}\n")
    monkeypatch.setattr(config_module, "_EXIFTOOL_TIMEOUT_SECONDS", timeout)
    original_popen = subprocess.Popen
    children = []

    def record_child(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(config_module.subprocess, "Popen", record_child)
    start = time.monotonic()
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), stages=("xmp",))
    assert time.monotonic() - start < 3
    assert "fictional-private-output" not in str(exc.value)
    assert len(children) == 1 and children[0].poll() is not None
