"""Supplementary contract tests for the single-pass macro boundary."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from image_clarus.config import ConfigurationError
from image_clarus.prompt_expansion import expand_prompt, safe_config_snapshot
from image_clarus.state.service import StateService
from image_clarus.state.storage import MemoryStorage, StateError, StateStopped


def expand(source, config=None, options=None, state=None):
    return expand_prompt(
        source,
        safe_config_snapshot(config or {}, {}),
        state if state is not None else StateService(MemoryStorage()),
        options or {},
    )


@pytest.mark.parametrize(
    "source",
    [
        "{{config}}",
        "{{config.1bad}}",
        "{{config.a b}}",
        "{{ config.a}}",
        "{{config.a()}}",
        "{{config.a[0]}}",
        "{{config.a|upper}}",
        "{{config.a",
        "{{config.a{{config.a}}",
        "{{other.a}}",
        "{{state.categories.missing}}",
    ],
)
def test_invalid_scanner_candidates_fail_without_echoing_input(source):
    with pytest.raises(ConfigurationError) as exc:
        expand(source, {"a": "value"})
    assert source not in str(exc.value)


def test_scanner_escapes_once_and_accepts_valid_segments():
    source = r"{single} \{{config.a}} {{config._a-b9}} {{config.a}}{{config.a}}"
    assert expand(source, {"_a-b9": "é", "a": "{{config._a-b9}}"}) == (
        "{single} {{config.a}} é {{config._a-b9}}{{config._a-b9}}"
    )


def test_nested_unicode_json_is_compact_and_deterministic():
    first = {"z": [{"β": "雪", "a": None}], "a": {"y": False, "x": 1.5}}
    second = {"a": {"x": 1.5, "y": False}, "z": [{"a": None, "β": "雪"}]}
    expected = '{"a":{"x":1.5,"y":false},"z":[{"a":null,"β":"雪"}]}'
    assert expand("{{config.obj}}", {"obj": first}) == expected
    assert expand("{{config.obj}}", {"obj": second}) == expected


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), object(), "\ud800"]
)
def test_invalid_nested_values_have_sanitized_errors(value):
    marker = "fictional-sensitive-value"
    with pytest.raises(ConfigurationError) as exc:
        expand(
            "{{config.secret_alias}}",
            {"secret_alias": {"marker": marker, "value": value}},
        )
    assert marker not in str(exc.value)
    assert "secret_alias" not in str(exc.value)


def test_exact_namespace_options_literal_delimiters_and_immutability():
    config = {
        "categories": {"known": ["a.b.c", "a.b.d", "x.y"]},
        "other": ["a::b::c", "a::b::d", "z"],
    }
    state = StateService(MemoryStorage())
    state.add_categories(["a/b/c", "a/b/d", "z/y"])
    source = "{{config.categories.known}} {{state.categories.known}} {{config.other}}"
    options = {
        "config.categories.known": {"delimiter": ".", "max_depth": 2},
        "state.categories.known": {"max_depth": 1},
        "config.other": {"delimiter": "::", "max_depth": 2},
    }
    before_config, before_options = deepcopy(config), deepcopy(options)
    before_state = state.snapshot_categories()
    snapshot = safe_config_snapshot(config, {})
    before_snapshot = deepcopy(snapshot)
    result = expand_prompt(source, snapshot, state, options)
    assert result == '["a.b","x.y"] ["a","z"] ["a::b","z"]'
    assert config == before_config and options == before_options
    assert snapshot == before_snapshot and state.snapshot_categories() == before_state
    assert (
        source
        == "{{config.categories.known}} {{state.categories.known}} {{config.other}}"
    )


@pytest.mark.parametrize("depth", [None, 0, 1])
def test_mixed_arrays_rejected_for_every_configured_depth(depth):
    with pytest.raises(ConfigurationError):
        expand(
            "{{config.items}}",
            {"items": ["path/a", 4]},
            {"config.items": {"max_depth": depth}},
        )
    assert expand("{{config.items}}", {"items": ["path/a", 4]}) == '["path/a",4]'


def test_real_failed_state_read_falls_back_once_without_leaking(capsys):
    class Broken(MemoryStorage):
        def snapshot_categories(self):
            raise StateError("fictional-private-read-error")

    state = StateService(Broken())
    assert (
        expand("{{state.categories.known}}/{{state.categories.known}}", state=state)
        == "[]/[]"
    )
    error = capsys.readouterr().err
    assert error.count("category read failed") == 1
    assert "fictional-private-read-error" not in error
    state.add_categories(["new/path"])
    assert state.snapshot_categories() == ["new/path"]


def test_stopped_state_read_propagates_without_fallback_or_diagnostic(capsys):
    stop = SimpleNamespace(signum=2)
    storage = MemoryStorage(stop=stop)
    state = StateService(storage, stop=stop)
    with pytest.raises(StateStopped):
        expand("{{state.categories.known}}", state=state)
    assert state.storage is storage
    assert capsys.readouterr().err == ""
