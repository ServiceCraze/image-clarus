def test_selected_stage_resolves_model_and_provider(tmp_path):
    from image_clarus.config import resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  local:\n    base_url: http://localhost:1234/v1\n"
        "models:\n  vision:\n    provider: local\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: vision\n"
    )
    config = resolve_config(stages=("desc",), config_file=path)
    assert config["stages"]["desc"]["model"] == "vision"
    assert config["models"]["vision"]["provider"] == "local"
    assert config["providers"]["local"]["timeout_seconds"] == 60


def test_http_provider_requires_loopback_or_private_address(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    for host, allowed in (
        ("localhost", True),
        ("127.0.0.1", True),
        ("[::1]", True),
        ("10.1.2.3", True),
        ("172.16.2.3", True),
        ("192.168.2.3", True),
        ("[fd00::1]", True),
        ("provider.example", False),
        ("169.254.1.1", False),
        ("203.0.113.1", False),
    ):
        path.write_text(
            f'providers:\n  p: {{base_url: "http://{host}/v1"}}\n'
            "models:\n  m: {provider: p, model_id: m}\n"
            "stages:\n  desc: {model: m}\n"
        )
        if allowed:
            resolve_config(config_file=path, stages=("desc",))
        else:
            with pytest.raises(ConfigurationError):
                resolve_config(config_file=path, stages=("desc",))


def test_defaults_are_available_without_a_selected_stage(tmp_path):
    from image_clarus.config import resolve_config

    config = resolve_config(stages=(), discovery_paths=(tmp_path / "missing",))
    assert config["pipeline"] == {
        "missing_prerequisite": "fail",
        "on_stage_failure": "stop",
        "backup_retention": "remove",
    }


def test_discovery_selects_first_file_without_merging(tmp_path):
    from image_clarus.config import resolve_config

    user = tmp_path / "user.yaml"
    system = tmp_path / "system.yaml"
    user.write_text("pipeline:\n  backup_retention: retain\n")
    system.write_text("pipeline:\n  missing_prerequisite: skip\n")
    config = resolve_config(stages=(), discovery_paths=(user, system))
    assert config["pipeline"]["backup_retention"] == "retain"
    assert config["pipeline"]["missing_prerequisite"] == "fail"


def test_invalid_retention_is_configuration_error(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text("pipeline:\n  backup_retention: forever\n")
    with pytest.raises(ConfigurationError):
        resolve_config(stages=(), discovery_paths=(path,))


def test_explicit_config_suppresses_discovery(tmp_path):
    from image_clarus.config import resolve_config

    explicit = tmp_path / "explicit.yaml"
    discovered = tmp_path / "discovered.yaml"
    explicit.write_text("pipeline:\n  on_stage_failure: continue\n")
    discovered.write_text("pipeline:\n  backup_retention: retain\n")
    config = resolve_config(
        config_file=explicit, stages=(), discovery_paths=(discovered,)
    )
    assert config["pipeline"]["on_stage_failure"] == "continue"
    assert config["pipeline"]["backup_retention"] == "remove"


def test_duplicate_yaml_keys_fail_without_disclosing_values(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "pipeline:\n  backup_retention: secret-sentinel\n  backup_retention: retain\n"
    )
    with pytest.raises(ConfigurationError) as error:
        resolve_config(stages=(), discovery_paths=(path,))
    assert "secret-sentinel" not in str(error.value)


def test_set_override_uses_yaml_and_last_value_wins(tmp_path):
    from image_clarus.config import resolve_config

    path = tmp_path / "config.yaml"
    path.write_text("pipeline:\n  backup_retention: remove\n")
    config = resolve_config(
        stages=(),
        discovery_paths=(path,),
        overrides=[
            "pipeline.backup_retention=remove",
            "pipeline.backup_retention=retain",
        ],
    )
    assert config["pipeline"]["backup_retention"] == "retain"


def test_malformed_yaml_is_a_sanitized_configuration_error(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "bad.yaml"
    path.write_text("api_key: sentinel-secret\nbad: [\n")
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(stages=(), discovery_paths=(path,))
    assert "sentinel-secret" not in str(exc.value)


def test_unknown_global_keys_are_rejected(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "bad.yaml"
    path.write_text("unexpected: 123\n")
    with pytest.raises(ConfigurationError):
        resolve_config(stages=(), config_file=path)


def test_selected_stage_without_model_fails_preflight(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError):
        resolve_config(stages=("desc",), discovery_paths=(tmp_path / "missing",))


def test_layers_and_path_origins(tmp_path, monkeypatch):
    from image_clarus.config import resolve_config

    source = tmp_path / "source"
    source.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    path = source / "config.yaml"
    path.write_text(
        "providers:\n  p:\n    base_url: http://localhost\n"
        "models:\n  m:\n    provider: p\n    model_id: m\n"
        "stages:\n  desc:\n    model: m\n    prompt_file: from-file\n"
        "  json:\n    model: m\n    schema_file: schema\n"
    )
    (cwd / "from-flag").write_text("prompt")
    (cwd / "json-prompt").write_text("prompt")
    (source / "schema").write_text('{"type":"object"}')
    config = resolve_config(
        config_file=path,
        stages=("desc", "json"),
        overrides=["stages.desc.prompt_file=from-set"],
        desc_prompt="from-flag",
        json_prompt="json-prompt",
    )
    assert config["stages"]["desc"]["prompt_file"] == cwd / "from-flag"
    assert config["stages"]["json"]["prompt_file"] == cwd / "json-prompt"
    assert config["stages"]["json"]["schema_file"] == source / "schema"


def test_invalid_global_schema_is_rejected(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    for text in (
        "pipeline: []",
        "pipeline:\n  unknown: x",
        "logging:\n  level: TRACE",
        "stages:\n  desc:\n    regenerate: 3",
        "providers:\n  bad.alias: {}",
    ):
        path.write_text(text)
        with pytest.raises(ConfigurationError):
            resolve_config(config_file=path)


def test_selected_stage_isolation_and_authentication(tmp_path, monkeypatch):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  p:\n    base_url: http://localhost\n    api_key_env: SYNTHETIC_TEST_KEY\n"
        "models:\n  m:\n    provider: p\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\n  json:\n    model: absent\n"
    )
    monkeypatch.delenv("SYNTHETIC_TEST_KEY", raising=False)
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(config_file=path, stages=("desc",))
    assert exc.value.category == "authentication"
    monkeypatch.setenv("SYNTHETIC_TEST_KEY", "secret-sentinel")
    config = resolve_config(config_file=path, stages=("desc",))
    assert "secret-sentinel" not in repr(config)
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path, stages=("json",))


def test_mapping_and_retry_validation(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    base = (
        "providers:\n  p:\n    base_url: http://localhost\n"
        "    reasoning_effort_mapping:\n      parameter: thinking\n      values:\n        low: concise\n"
        "models:\n  m:\n    provider: p\n    model_id: m\n"
        "stages:\n  json:\n    model: m\n    reasoning_effort: high\n    validation_retries: 3\n"
    )
    path.write_text(base)
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path, stages=("json",))
    path.write_text(base.replace("validation_retries: 3", "validation_retries: 2"))
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path, stages=("json",))
    path.write_text(
        base.replace("validation_retries: 3", "validation_retries: 2").replace(
            "effort: high", "effort: low"
        )
    )
    assert (
        resolve_config(config_file=path, stages=("json",))["stages"]["json"][
            "validation_retries"
        ]
        == 2
    )


def test_override_can_create_aliases_but_not_credentials(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    common = [
        "providers.p.base_url=http://localhost",
        "models.m.provider=p",
        "models.m.model_id=m",
        "stages.desc.model=m",
    ]
    config = resolve_config(discovery_paths=(), stages=("desc",), overrides=common)
    assert config["models"]["m"]["model_id"] == "m"
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(), overrides=["providers.p.api_key=secret-sentinel"]
        )
    assert "secret-sentinel" not in str(exc.value)


def test_credential_in_mapping_override_is_forbidden():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError):
        resolve_config(discovery_paths=(), overrides=["providers.p={api_key: secret}"])


def test_empty_stage_effort_is_not_inheritance(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        'providers:\n  p: {base_url: "http://localhost"}\nmodels:\n  m: {provider: p, model_id: m}\nstages:\n  desc: {model: m, reasoning_effort: ""}\n'
    )
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path, stages=("desc",))


def test_unselected_mapping_still_rejects_unknown_fields(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  p:\n    reasoning_effort_mapping:\n      values: {low: [bad]}\n"
    )
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path)


def test_invalid_url_delimiters_rejected_even_when_empty(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    for url in (
        "http://localhost?",
        "http://localhost#",
        "http://user@localhost",
        "http://localhost/chat/completions",
    ):
        path.write_text(
            f'providers:\n  p: {{base_url: "{url}"}}\nmodels:\n  m: {{provider: p, model_id: m}}\nstages:\n  desc: {{model: m}}\n'
        )
        with pytest.raises(ConfigurationError):
            resolve_config(config_file=path, stages=("desc",))


def test_discovery_platform_paths_are_deterministic(tmp_path):
    from image_clarus.config import discovery_locations

    user, system = discovery_locations("linux", {}, tmp_path)
    assert user == tmp_path / ".config/image-clarus/config.yaml"
    assert str(system) == "/etc/image-clarus/config.yaml"
    user, system = discovery_locations("darwin", {}, tmp_path)
    assert user == tmp_path / "Library/Application Support/image-clarus/config.yaml"
    assert str(system) == "/Library/Application Support/image-clarus/config.yaml"
    assert discovery_locations(
        "win32", {"APPDATA": "user", "PROGRAMDATA": "system"}, tmp_path
    ) == (
        __import__("pathlib").Path("user/image-clarus/config.yaml"),
        __import__("pathlib").Path("system/image-clarus/config.yaml"),
    )


def test_set_mapping_replaces_target_mapping(tmp_path):
    from image_clarus.config import resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  p:\n    base_url: http://localhost\n    reasoning_effort_mapping:\n      parameter: thinking\n      values: {low: low, high: high}\n"
    )
    config = resolve_config(
        config_file=path,
        overrides=[
            "providers.p.reasoning_effort_mapping={parameter: thinking, values: {low: concise}}"
        ],
    )
    assert config["providers"]["p"]["reasoning_effort_mapping"]["values"] == {
        "low": "concise"
    }


def test_recursive_yaml_is_a_sanitized_configuration_error(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text("providers:\n  p: &cycle {reasoning_effort_mapping: *cycle}\n")
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path)


def test_public_ip_http_endpoint_is_rejected():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError):
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=[
                "providers.p.base_url=http://8.8.8.8/v1",
                "models.m.provider=p",
                "models.m.model_id=m",
                "stages.desc.model=m",
            ],
        )


def test_schema_property_names_and_examples_are_not_schema_keywords(tmp_path):
    import json

    from image_clarus.config import resolve_config

    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "$ref": {"type": "string"},
                    "$dynamicRef": {"type": "string"},
                },
                "examples": [
                    {"$ref": "https://example.invalid", "$dynamicRef": "data"}
                ],
            }
        )
    )
    resolve_config(
        discovery_paths=(),
        stages=("json",),
        json_schema=schema,
        overrides=[
            "providers.p.base_url=http://localhost",
            "models.m.provider=p",
            "models.m.model_id=m",
            "stages.json.model=m",
        ],
    )


def test_huge_timeout_is_sanitized_configuration_error():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=[
                "providers.p.base_url=http://localhost",
                "providers.p.timeout_seconds=" + "9" * 400,
                "models.m.provider=p",
                "models.m.model_id=m",
                "stages.desc.model=m",
            ],
        )
    assert "999999" not in str(exc.value)


def test_deep_override_is_sanitized_configuration_error():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            overrides=["logging.level=" + "[" * 1200 + "secret" + "]" * 1200],
        )
    assert "secret" not in str(exc.value)


def test_empty_unselected_prompt_does_not_block_selected_stage(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    path.write_text(
        'providers:\n  p: {base_url: "http://localhost"}\nmodels:\n  m: {provider: p, model_id: m}\nstages:\n  desc: {model: m}\n  json: {model: m, prompt_file: ""}\n'
    )
    resolve_config(config_file=path, stages=("desc",))
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path, stages=("json",))


def test_custom_schema_references_are_checked_only_in_subschemas(tmp_path):
    import json

    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    schema_path = tmp_path / "schema.json"
    opts = {
        "discovery_paths": (),
        "stages": ("json",),
        "json_schema": schema_path,
        "overrides": [
            "providers.p.base_url=http://localhost",
            "models.m.provider=p",
            "models.m.model_id=m",
            "stages.json.model=m",
        ],
    }
    schema = {
        "type": "object",
        "$defs": {"thing": {"type": "string"}},
        "properties": {"item": {"$ref": "#/$defs/thing"}},
    }
    schema_path.write_text(json.dumps(schema))
    resolve_config(**opts)
    for reference in (
        {"$ref": "https://example.invalid/schema"},
        {"$ref": "file:///tmp/schema"},
        {"$dynamicRef": "#thing"},
    ):
        schema["properties"]["item"] = reference
        schema_path.write_text(json.dumps(schema))
        with pytest.raises(ConfigurationError):
            resolve_config(**opts)


def test_first_invalid_discovery_file_never_falls_back(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    first, second = tmp_path / "first", tmp_path / "second"
    first.write_text("pipeline: [")
    second.write_text("pipeline: {backup_retention: retain}")
    with pytest.raises(ConfigurationError):
        resolve_config(discovery_paths=(first, second))


def test_set_path_origin_and_dedicated_path_precedence(tmp_path, monkeypatch):
    from image_clarus.config import resolve_config

    cwd, source = tmp_path / "cwd", tmp_path / "source"
    cwd.mkdir()
    source.mkdir()
    monkeypatch.chdir(cwd)
    file = source / "config.yaml"
    file.write_text("stages:\n  desc: {prompt_file: file.txt}\n")
    (cwd / "set.txt").write_text("set")
    (cwd / "flag.txt").write_text("flag")
    opts = {"config_file": file, "overrides": ["stages.desc.prompt_file=set.txt"]}
    assert resolve_config(**opts)["stages"]["desc"]["prompt_file"] == cwd / "set.txt"
    common = [
        "providers.p.base_url=http://localhost",
        "models.m.provider=p",
        "models.m.model_id=m",
        "stages.desc.model=m",
    ]
    opts["overrides"] += common
    assert (
        resolve_config(**opts, stages=("desc",), desc_prompt="flag.txt")["stages"][
            "desc"
        ]["prompt_file"]
        == cwd / "flag.txt"
    )


def test_higher_precedence_repairs_invalid_file_and_prior_override(tmp_path):
    from image_clarus.config import resolve_config

    path = tmp_path / "config.yaml"
    path.write_text("pipeline: {missing_prerequisite: 12}\n")
    config = resolve_config(
        config_file=path,
        overrides=["pipeline.missing_prerequisite=17"],
        missing_prerequisite="skip",
    )
    assert config["pipeline"]["missing_prerequisite"] == "skip"


def test_schema_unresolved_fragment_and_nested_id_are_rejected(tmp_path):
    import json

    import pytest

    from image_clarus.config import ConfigurationError, _check_schema

    path = tmp_path / "schema.json"
    for subschema in (
        {"$ref": "#missing"},
        {"$id": "https://example.invalid/nested", "$ref": "#"},
    ):
        path.write_text(json.dumps({"type": "object", "properties": {"x": subschema}}))
        with pytest.raises(ConfigurationError):
            _check_schema(path)


def test_deep_selected_schema_failure_is_sanitized(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, _check_schema

    path = tmp_path / "schema.json"
    path.write_text(
        '{"type":"object","properties":{"x":'
        + '{"not":' * 450
        + "true"
        + "}" * 450
        + "}}"
    )
    with pytest.raises(ConfigurationError):
        _check_schema(path)


def test_invalid_override_reports_safe_path_without_values_or_aliases():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(), overrides=["pipeline.backup_retention=[secret-sentinel"]
        )
    assert "pipeline.backup_retention" in str(exc.value)
    assert "secret-sentinel" not in str(exc.value)
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(discovery_paths=(), overrides=["pipeline.backup_retention=123"])
    assert "pipeline.backup_retention" in str(exc.value)
    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            overrides=["providers.secret-sentinel.api_key=other-secret"],
        )
    assert "secret-sentinel" not in str(exc.value)
    assert "other-secret" not in str(exc.value)


def test_referenced_annotation_schema_cannot_hide_external_ref(tmp_path):
    import json

    import pytest

    from image_clarus.config import ConfigurationError, _check_schema

    schema = {
        "type": "object",
        "examples": [{"$ref": "https://example.invalid/schema"}],
        "properties": {"x": {"$ref": "#/examples/0"}},
    }
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema))
    with pytest.raises(ConfigurationError):
        _check_schema(path)


def test_dedicated_override_repairs_wrong_parent_type(tmp_path):
    from image_clarus.config import resolve_config

    path = tmp_path / "config.yaml"
    path.write_text("pipeline: 42\n")
    assert (
        resolve_config(config_file=path, missing_prerequisite="skip")["pipeline"][
            "missing_prerequisite"
        ]
        == "skip"
    )


def test_invalid_override_enum_reports_path():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(), overrides=["pipeline.backup_retention=not-valid"]
        )
    assert "pipeline.backup_retention" in str(exc.value)
    assert "not-valid" not in str(exc.value)


def test_schema_fragment_anchors_pointers_and_network_isolation(tmp_path, monkeypatch):
    import json
    import socket

    import pytest

    from image_clarus.config import ConfigurationError, _check_schema

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    path = tmp_path / "schema.json"
    schema = {
        "type": "object",
        "$defs": {"a/b": {"$anchor": "target", "type": "string"}},
        "properties": {"a": {"$ref": "#target"}, "b": {"$ref": "#/$defs/a~1b"}},
    }
    path.write_text(json.dumps(schema))
    _check_schema(path)
    for ref in ("#missing", "#/$defs/missing", "https://example.invalid/schema"):
        schema["properties"]["a"]["$ref"] = ref
        path.write_text(json.dumps(schema))
        with pytest.raises(ConfigurationError):
            _check_schema(path)


def test_invalid_layers_retain_unknown_and_duplicate_key_safety(tmp_path):
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    path = tmp_path / "config.yaml"
    for text in (
        "pipeline: {unknown: secret}\n",
        "pipeline: {backup_retention: secret, backup_retention: retain}\n",
    ):
        path.write_text(text)
        with pytest.raises(ConfigurationError) as exc:
            resolve_config(
                config_file=path, overrides=["pipeline={backup_retention: retain}"]
            )
        assert "secret" not in str(exc.value)


def test_last_override_repairs_type_from_earlier_override():
    from image_clarus.config import resolve_config

    config = resolve_config(
        discovery_paths=(), overrides=["logging.level=123", "logging.level=INFO"]
    )
    assert config["logging"]["level"] == "INFO"


def test_invalid_selected_override_reports_redacted_path():
    import pytest

    from image_clarus.config import ConfigurationError, resolve_config

    with pytest.raises(ConfigurationError) as exc:
        resolve_config(
            discovery_paths=(),
            stages=("desc",),
            overrides=[
                "providers.secret_alias.base_url=http://public.example",
                "models.m.provider=secret_alias",
                "models.m.model_id=m",
                "stages.desc.model=m",
            ],
        )
    assert "providers.<name>.base_url" in str(exc.value)
    assert "secret_alias" not in str(exc.value)
    assert "public.example" not in str(exc.value)
