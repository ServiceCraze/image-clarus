"""Import isolation and compatibility for configuration errors."""

import subprocess
import sys
import textwrap

import pytest


def _run_fresh(source):
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_prompt_expansion_import_does_not_import_config():
    _run_fresh(
        """
        import importlib.abc
        import sys

        class BlockConfig(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "image_clarus.config":
                    raise AssertionError("config import forbidden")
                return None

        assert "image_clarus.config" not in sys.modules
        sys.meta_path.insert(0, BlockConfig())
        import image_clarus.prompt_expansion
        assert "image_clarus.config" not in sys.modules
        """
    )


def test_configuration_error_import_identity_in_fresh_process():
    _run_fresh(
        """
        from image_clarus.config_errors import ConfigurationError as canonical
        from image_clarus.config import ConfigurationError as legacy
        from image_clarus.prompt_expansion import ConfigurationError as expansion
        assert canonical is legacy is expansion
        assert issubclass(canonical, ValueError)
        """
    )


@pytest.mark.parametrize(
    ("message", "category", "expected"),
    [
        ("bad value", "configuration", "Invalid configuration: bad value"),
        ("Invalid configuration", "configuration", "Invalid configuration"),
        (
            "Cannot load configuration file",
            "configuration",
            "Cannot load configuration file",
        ),
        ("bad value", "schema", "bad value"),
    ],
)
def test_configuration_error_preserves_message_and_category(
    message, category, expected
):
    from image_clarus.config import ConfigurationError

    error = ConfigurationError(message, category)
    assert str(error) == expected
    assert error.category == category
    assert ConfigurationError("bad value").category == "configuration"
