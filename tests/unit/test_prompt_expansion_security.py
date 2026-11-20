"""Adversarial snapshot and state boundary regression tests."""

import traceback
from copy import deepcopy

import pytest

from image_clarus.config import ConfigurationError
from image_clarus.prompt_expansion import expand_prompt, safe_config_snapshot
from image_clarus.state.storage import StateStopped


def test_tuple_snapshot_recursively_filters_credentials_without_mutation():
    config = {
        "providers": {
            "a": {"api_key": "fake-inline-key"},
            "b": {"api_key_env": "FAKE_ENV"},
        },
        "items": (
            "safe",
            "fake-inline-key",
            ["fake-env-key", {"api_key": "hidden", "ok": "yes"}],
            {"api_key_env": "hidden", "fake-inline-key-alias": 1},
        ),
    }
    original = deepcopy(config)
    snapshot = safe_config_snapshot(config, {"FAKE_ENV": "fake-env-key"})
    output = expand_prompt("{{config.items}}", snapshot, None, {})
    assert output == '["safe",[{"ok":"yes"}],{}]'
    assert config == original


def test_unknown_state_reference_never_reads_state():
    class State:
        def snapshot_categories(self):
            pytest.fail("unknown reference triggered state read")

    with pytest.raises(ConfigurationError):
        expand_prompt("{{state.unknown}}", {}, State(), {})


@pytest.mark.parametrize("where", ["snapshot", "state"])
@pytest.mark.parametrize("error_type", [RuntimeError, ConfigurationError])
def test_unexpected_exceptions_have_sanitized_traceback(where, error_type):
    sensitive = "fictional-private-prompt-secret-path"

    class BrokenConfig(dict):
        def get(self, key, default=None):
            raise error_type(sensitive)

    class BrokenState:
        def snapshot_categories(self):
            raise error_type(sensitive)

    with pytest.raises(ConfigurationError) as exc:
        if where == "snapshot":
            safe_config_snapshot(BrokenConfig(), {})
        else:
            expand_prompt("{{state.categories.known}}", {}, BrokenState(), {})
    assert sensitive not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit, StateStopped])
def test_state_interrupts_propagate(error_type):
    class State:
        def snapshot_categories(self):
            raise error_type("stopped")

    with pytest.raises(error_type):
        expand_prompt("{{state.categories.known}}", {}, State(), {})


def test_unsupported_nested_structure_is_rejected():
    with pytest.raises(ConfigurationError):
        safe_config_snapshot({"items": ({"unsafe": object()},)}, {})
