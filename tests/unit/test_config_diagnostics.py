"""Actionable configuration errors must never echo untrusted content."""

import pytest

from image_clarus.config import ConfigurationError, resolve_config


def test_unknown_key_has_safe_location_reason_and_fix(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("pipeline:\n  private_key_sentinel: private_value_sentinel\n")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path)
    message = str(exc.value)
    assert "pipeline" in message
    assert "unknown" in message.lower()
    assert "remove" in message.lower()
    assert "private_key_sentinel" not in message
    assert "private_value_sentinel" not in message


def test_http_hostname_passes_selected_preflight():
    config = resolve_config(
        discovery_paths=(),
        stages=("desc",),
        overrides=[
            "providers.p.base_url=http://fictional.example/v1",
            "models.m.provider=p",
            "models.m.model_id=synthetic",
            "stages.desc.model=m",
        ],
    )
    assert config["providers"]["p"]["base_url"] == "http://fictional.example/v1"


@pytest.mark.parametrize(
    ("text", "field", "reason", "fix"),
    [
        ("pipeline: []", "pipeline", "mapping", "replace"),
        ("logging: {level: 4}", "logging.level", "string", "set"),
        ("stages: {desc: {regenerate: 9}}", "stages.desc.regenerate", "boolean", "set"),
        (
            "pipeline: {backup_retention: private_value_sentinel}",
            "pipeline.backup_retention",
            "invalid",
            "set",
        ),
        (
            "providers: {private_alias_sentinel: {unknown_private: x}}",
            "providers.<name>",
            "unknown",
            "remove",
        ),
        (
            "pipeline: {backup_retention: remove, backup_retention: retain}",
            "configuration",
            "duplicate",
            "remove",
        ),
        ("pipeline: [private_value_sentinel", "configuration", "yaml", "correct"),
    ],
)
def test_safe_diagnostics_for_file_errors(tmp_path, text, field, reason, fix):
    path = tmp_path / "private_path_sentinel"
    path.write_text(text)
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            config_file=path,
            stages=("desc",) if field.startswith("stages.desc.") else (),
        )
    message = str(exc.value).lower()
    assert field.lower() in message
    assert reason in message
    assert fix in message
    for secret in (
        "private_value_sentinel",
        "private_alias_sentinel",
        "unknown_private",
        "private_path_sentinel",
    ):
        assert secret not in message


@pytest.mark.parametrize(
    ("extra", "field", "reason", "fix", "category"),
    [
        (
            ["stages.desc.model=missing_private"],
            "stages.desc.model",
            "model",
            "set",
            "configuration",
        ),
        (
            ["models.m.provider=missing_private"],
            "models.<name>.provider",
            "provider",
            "set",
            "configuration",
        ),
        (
            ["providers.p.base_url=http://user:secret@private-host.invalid/path"],
            "providers.<name>.base_url",
            "url",
            "set",
            "configuration",
        ),
        (
            ["providers.p.timeout_seconds=0"],
            "providers.<name>.timeout_seconds",
            "positive",
            "set",
            "configuration",
        ),
        (
            ["providers.p.api_key_env=PRIVATE_ENV_SENTINEL"],
            "providers.<name>.api_key_env",
            "credential",
            "set",
            "authentication",
        ),
        (
            ["stages.desc.prompt_file=private_path_sentinel"],
            "stages.desc.prompt_file",
            "file",
            "set",
            "configuration",
        ),
    ],
)
def test_safe_selected_diagnostics(extra, field, reason, fix, category, monkeypatch):
    monkeypatch.delenv("PRIVATE_ENV_SENTINEL", raising=False)
    options = [
        "providers.p.base_url=http://localhost",
        "models.m.provider=p",
        "models.m.model_id=x",
        "stages.desc.model=m",
    ] + extra
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), stages=("desc",), overrides=options)
    message = str(exc.value).lower()
    assert field.lower() in message
    assert reason in message
    assert fix in message
    assert exc.value.category == category
    for secret in (
        "missing_private",
        "private-host",
        "secret",
        "private_env_sentinel",
        "private_path_sentinel",
    ):
        assert secret not in message


def test_yaml_parse_error_reports_location_without_yaml(tmp_path):
    path = tmp_path / "config"
    path.write_text("logging:\n  level: [private_value_sentinel\n")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path)
    assert "line" in str(exc.value).lower()
    assert "column" in str(exc.value).lower()
    assert "private_value_sentinel" not in str(exc.value)


def test_invalid_override_has_reason_and_fix():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            overrides=["pipeline.backup_retention=[private_value_sentinel"],
        )
    text = str(exc.value).lower()
    assert "pipeline.backup_retention" in text and "yaml" in text and "correct" in text
    assert "private_value_sentinel" not in text


@pytest.mark.parametrize(
    ("stage", "extra", "field", "reason"),
    [
        (
            "desc",
            "stages.desc.reasoning_effort=not_valid",
            "stages.desc.reasoning_effort",
            "effort",
        ),
        (
            "json",
            "stages.json.validation_retries=9",
            "stages.json.validation_retries",
            "retry",
        ),
        (
            "desc",
            "providers.p.reasoning_effort_mapping={parameter: effort, values: {}}",
            "providers.<name>.reasoning_effort_mapping",
            "mapping",
        ),
    ],
)
def test_other_selected_fields_are_actionable(stage, extra, field, reason):
    options = [
        "providers.p.base_url=http://localhost",
        "models.m.provider=p",
        "models.m.model_id=x",
        f"stages.{stage}.model=m",
        extra,
    ]
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), stages=(stage,), overrides=options)
    message = str(exc.value).lower()
    assert field.lower() in message and reason in message and "set" in message


def test_invalid_schema_diagnostic_uses_safe_stage_path(tmp_path):
    schema = tmp_path / "private_schema_path_sentinel"
    schema.write_text("not json private_schema_value_sentinel")
    options = [
        "providers.p.base_url=http://localhost",
        "models.m.provider=p",
        "models.m.model_id=x",
        "stages.json.model=m",
    ]
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(), stages=("json",), json_schema=schema, overrides=options
        )
    message = str(exc.value).lower()
    assert (
        "stages.json.schema_file" in message
        and "schema" in message
        and "set" in message
    )
    assert "private_schema" not in message


@pytest.mark.parametrize(
    ("text", "field", "reason"),
    [
        ("providers: {private.alias: {}}", "providers.<name>", "alias"),
        (
            "providers: {p: {reasoning_effort_mapping: {parameter: 2}}}",
            "providers.<name>.reasoning_effort_mapping.parameter",
            "string",
        ),
        (
            "models: {m: {reasoning_effort_mapping: {values: []}}}",
            "models.<name>.reasoning_effort_mapping.values",
            "mapping",
        ),
        (
            "models: {m: {reasoning_effort_mapping: {unknown_private: 1}}}",
            "models.<name>.reasoning_effort_mapping",
            "unknown",
        ),
    ],
)
def test_nested_diagnostics_include_safe_field(tmp_path, text, field, reason):
    path = tmp_path / "config"
    path.write_text(text)
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path)
    message = str(exc.value).lower()
    assert field.lower() in message and reason in message
    assert "set" in message or "remove" in message or "replace" in message
    assert "private.alias" not in message and "unknown_private" not in message


def test_override_duplicate_yaml_key_reports_duplicate():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            overrides=[
                "pipeline={backup_retention: private_sentinel, backup_retention: remove}"
            ],
        )
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "pipeline" in text and "duplicate" in text and "remove" in text
    assert "private_sentinel" not in text


def test_unhashable_yaml_key_reports_location_and_fix(tmp_path):
    path = tmp_path / "config"
    path.write_text("pipeline:\n  ? [private_sentinel]\n  : value\n")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path)
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "mapping key" in text and "line 2" in text and "replace" in text
    assert "private_sentinel" not in text


def test_invalid_yaml_timestamp_is_not_unreadable_file(tmp_path):
    path = tmp_path / "private_path_sentinel"
    path.write_text("logging: {level: 2025-99-99}\n")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path)
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "yaml" in text and "value" in text and "correct" in text
    assert "readable" not in text and "private_path_sentinel" not in text


def test_reserved_reasoning_parameter_identifies_field():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=[
                "providers.p.base_url=http://localhost",
                "models.m.provider=p",
                "models.m.model_id=x",
                "stages.desc.model=m",
                "providers.p.reasoning_effort_mapping={parameter: messages, values: {low: private_sentinel}}",
            ],
        )
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "providers.<name>.reasoning_effort_mapping.parameter" in text
    assert "reserved" in text and "set" in text
    assert "private_sentinel" not in text


def test_unknown_override_key_is_not_reported_as_forbidden_credential():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(), overrides=["pipeline.private_sentinel=value"]
        )
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "pipeline" in text and "unknown key" in text and "remove" in text
    assert "forbidden" not in text and "private_sentinel" not in text


def test_explicit_prompt_bad_expansion_has_field_and_correction():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            desc_prompt="~private_unlikely_user_sentinel/prompt",
        )
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "stages.desc.prompt_file" in text and "path" in text and "set" in text
    assert "private_unlikely_user_sentinel" not in text


def test_unrelated_override_is_not_blame_for_file_error(tmp_path):
    path = tmp_path / "config"
    path.write_text("logging: {level: 42}\n")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path, overrides=["pipeline.backup_retention=retain"])
    text = str(exc.value).lower()
    assert "logging.level" in text and "string" in text
    assert "pipeline.backup_retention" not in text


def test_relevant_override_path_retained_for_nested_error():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), overrides=["logging={level: 42}"])
    text = str(exc.value).lower()
    assert "logging.level" in text and "override paths: logging" in text


def test_different_provider_override_is_not_blame_for_selected_provider(tmp_path):
    path = tmp_path / "config"
    path.write_text(
        "providers: {p: {base_url: http://localhost, timeout_seconds: 0}}\nmodels: {m: {provider: p, model_id: x}}\nstages: {desc: {model: m}}\n"
    )
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            config_file=path,
            stages=("desc",),
            overrides=["providers.q.timeout_seconds=10"],
        )
    text = str(exc.value).lower()
    assert "providers.<name>.timeout_seconds" in text and "positive" in text
    assert "override paths:" not in text


def test_direct_api_key_control_characters_are_actionable(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  p:\n    base_url: http://localhost\n"
        '    api_key: "SYNTHETIC_KEY_SENTINEL\\r\\nX-Probe: 1"\n'
        "models:\n  m:\n    provider: p\n    model_id: sample-model\n"
        "stages:\n  desc:\n    model: m\n"
    )
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path, stages=("desc",))
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "providers.<name>.api_key" in text
    assert "header" in text and "set" in text
    assert "synthetic_key_sentinel" not in text and "x-probe" not in text


def test_environment_api_key_control_characters_are_actionable(monkeypatch):
    monkeypatch.setenv(
        "SYNTHETIC_PROVIDER_KEY",
        "SYNTHETIC_KEY_SENTINEL\r\nX-Probe: 1",
    )
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=[
                "providers.p.base_url=http://localhost",
                "providers.p.api_key_env=SYNTHETIC_PROVIDER_KEY",
                "models.m.provider=p",
                "models.m.model_id=sample-model",
                "stages.desc.model=m",
            ],
        )
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "providers.<name>.api_key_env" in text
    assert "header" in text and "set" in text
    assert "synthetic_key_sentinel" not in text and "x-probe" not in text


@pytest.mark.parametrize("source", ["direct", "environment"])
def test_non_ascii_api_key_is_rejected_during_preflight(tmp_path, monkeypatch, source):
    key = "SYNTHETIC_KEY_é"
    if source == "direct":
        path = tmp_path / "config.yaml"
        path.write_text(
            "providers:\n  p:\n    base_url: http://localhost\n"
            f'    api_key: "{key}"\n'
            "models:\n  m:\n    provider: p\n    model_id: sample-model\n"
            "stages:\n  desc:\n    model: m\n"
        )
        options = {"config_file": path, "stages": ("desc",)}
        field = "providers.<name>.api_key"
    else:
        monkeypatch.setenv("SYNTHETIC_PROVIDER_KEY", key)
        options = {
            "discovery_paths": (),
            "stages": ("desc",),
            "overrides": [
                "providers.p.base_url=http://localhost",
                "providers.p.api_key_env=SYNTHETIC_PROVIDER_KEY",
                "models.m.provider=p",
                "models.m.model_id=sample-model",
                "stages.desc.model=m",
            ],
        }
        field = "providers.<name>.api_key_env"

    with pytest.raises(ConfigurationError) as exc:
        resolve_config(**options)
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert field in text
    assert "ascii" in text and "header" in text and "set" in text
    assert key.lower() not in text


def test_unpaired_surrogate_model_id_is_actionable():
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=[
                "providers.p.base_url=http://localhost",
                "models.m.provider=p",
                'models.m.model_id="\\uD800"',
                "stages.desc.model=m",
            ],
        )
    text = str(exc.value).lower()
    assert exc.value.category == "configuration"
    assert "models.<name>.model_id" in text
    assert "utf-8" in text and "set" in text
    assert "d800" not in text
