from copy import deepcopy
from pathlib import Path

import pytest

from image_clarus.config import ConfigurationError
from image_clarus.prompt_expansion import expand_prompt, safe_config_snapshot
from image_clarus.state.service import StateService
from image_clarus.state.storage import MemoryStorage, StateError


def expand(text, config, options=None, state=None):
    return expand_prompt(
        text,
        safe_config_snapshot(config),
        state or StateService(MemoryStorage()),
        options or {},
    )


def test_expands_namespaced_values_and_transforms():
    config = {"paths": ["a/b/c", "a/b/d", "z"]}
    state = StateService(MemoryStorage())
    state.add_categories(["food/cake", "food/pie"])
    options = {
        "config.paths": {"max_depth": 2},
        "state.categories.known": {"max_depth": 1},
    }
    assert (
        expand("{{config.paths}} {{state.categories.known}}", config, options, state)
        == '["a/b","z"] ["food"]'
    )


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, '["a::b::c","a::b::d","z"]'),
        ({"max_depth": None}, '["a::b::c","a::b::d","z"]'),
        ({"delimiter": "::", "max_depth": 2}, '["a::b","z"]'),
        ({"max_depth": 0}, "[]"),
    ],
)
def test_depth_and_delimiter(options, expected):
    assert (
        expand(
            "{{config.paths}}",
            {"paths": ["a::b::c", "a::b::d", "z"]},
            {"config.paths": options},
        )
        == expected
    )


def test_safe_snapshot_filters_credentials_everywhere_without_mutation():
    config = {
        "providers": {
            "one": {"api_key": "fictional-inline"},
            "two": {"api_key_env": "FICTIONAL_TOKEN"},
        },
        "nested": {
            "fictional-inline-key": "x",
            "text": "prefix fictional-env suffix",
            "ok": "safe",
            "list": ["fictional-inline", "yes"],
        },
    }
    original = deepcopy(config)
    snapshot = safe_config_snapshot(config, {"FICTIONAL_TOKEN": "fictional-env"})
    text = expand_prompt(
        "{{config.providers}} {{config.nested}}",
        snapshot,
        StateService(MemoryStorage()),
        {},
    )
    assert "fictional-inline" not in text and "fictional-env" not in text
    assert text == '{"one":{},"two":{}} {"list":["yes"],"ok":"safe"}'
    assert config == original
    for ref in (
        "config.providers.one.api_key",
        "config.providers.two.api_key_env",
        "config.nested.text",
    ):
        with pytest.raises(ConfigurationError) as exc:
            expand_prompt(
                "{{" + ref + "}}", snapshot, StateService(MemoryStorage()), {}
            )
        assert "fictional" not in str(exc.value)


def test_serialization_escaping_nonrecursive_and_paths():
    config = {
        "object": {"z": True, "a": [None, "é"]},
        "value": "{{config.object}}",
        "path": Path("/fictional/path"),
    }
    assert (
        expand(
            r"\{{config.object}} {{config.value}} {{config.object}} {{config.path}} {x}",
            config,
        )
        == '{{config.object}} {{config.object}} {"a":[null,"é"],"z":true} /fictional/path {x}'
    )


@pytest.mark.parametrize(
    "text",
    [
        "{{state.unknown}}",
        "{{config.missing}}",
        "{{unknown.x}}",
        "{{config.x[0]}}",
        "{{config.x",
        "{{config..x}}",
    ],
)
def test_invalid_refs_are_sanitized(text):
    with pytest.raises(ConfigurationError) as exc:
        expand(text, {"x": 1})
    assert text not in str(exc.value)


@pytest.mark.parametrize("value", [["a", 1], 12, [None]])
def test_configured_non_string_array_is_rejected(value):
    with pytest.raises(ConfigurationError):
        expand("{{config.x}}", {"x": value}, {"config.x": {"max_depth": 0}})


def test_unconfigured_mixed_array_serializes_and_invalid_values_fail():
    assert expand("{{config.x}}", {"x": [1, "a", None]}) == '[1,"a",null]'
    for value in (float("nan"), object()):
        with pytest.raises(ConfigurationError):
            expand("{{config.x}}", {"x": value})


@pytest.mark.parametrize(
    "options", [{"max_depth": -1}, {"max_depth": True}, {"delimiter": ""}]
)
def test_invalid_options_rejected(options):
    with pytest.raises(ConfigurationError):
        expand("{{config.x}}", {"x": []}, {"config.x": options})


def test_sources_and_state_unchanged_for_zero():
    config = {"x": ["a/b", "c/d"]}
    original = deepcopy(config)
    state = StateService(MemoryStorage())
    state.add_categories(["a/b", "c/d"])
    before = state.snapshot_categories()
    source = "{{config.x}} {{state.categories.known}}"
    assert (
        expand(
            source,
            config,
            {"config.x": {"max_depth": 0}, "state.categories.known": {"max_depth": 0}},
            state,
        )
        == "[] []"
    )
    assert config == original and state.snapshot_categories() == before
    assert source == "{{config.x}} {{state.categories.known}}"


def test_real_service_read_failure_falls_back_and_reports(capsys):
    class Broken(MemoryStorage):
        def snapshot_categories(self):
            raise StateError("fictional secret exception")

    state = StateService(Broken())
    assert (
        expand("before {{state.categories.known}} after", {}, state=state)
        == "before [] after"
    )
    diagnostic = capsys.readouterr().err
    assert "category read failed" in diagnostic and "fictional secret" not in diagnostic
    state.add_categories(["new/path"])
    assert state.snapshot_categories() == ["new/path"]
