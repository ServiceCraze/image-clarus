import pytest
from test_structure_stage import context, run  # noqa: F401

from image_clarus.stages.structure import _parse, _ParseError


def test_large_json_integer_is_sanitized_parse_failure():
    with pytest.raises(_ParseError, match="invalid_json"):
        _parse('{"n":' + "9" * 5000 + "}")


def test_nonprogressing_schema_recursion_returns_configuration(request):
    _context = request.getfixturevalue("context")
    _context.schema.write_text('{"type": "object", "$ref": "#"}')
    _context.replies[:] = ["{}"]
    result = run(_context)
    assert (result.status, result.error_category) == ("failed", "configuration")
    assert not _context.output.exists()


def test_recursion_in_property_ref_is_reported_without_exception(request):
    c = request.getfixturevalue("context")
    c.schema.write_text(
        '{"type":"object","properties":{"x":{"$ref":"#/$defs/loop"}},"$defs":{"loop":{"$ref":"#/$defs/loop"}}}'
    )
    c.replies[:] = ['{"x":1}']
    result = run(c)
    assert (result.status, result.error_category) == ("failed", "configuration")
    assert not c.output.exists()


def test_recovered_description_obeys_backup_removal_policy(request):
    c = request.getfixturevalue("context")
    backup = c.desc.with_name(c.desc.name + ".bak")
    c.desc.rename(backup)
    assert run(c).status == "completed"
    assert not backup.exists()


def test_numeric_validation_overflow_returns_safe_failure(request):
    c = request.getfixturevalue("context")
    c.schema.write_text('{"type":"object","properties":{"x":{"multipleOf":0.1}}}')
    c.replies[:] = ['{"x":' + "9" * 401 + "}"]
    result = run(c)
    assert result.status == "failed"
    assert result.error_category in {"configuration", "schema_validation"}
    assert not c.output.exists()


def test_validation_timeout_is_not_retried_or_published(request, monkeypatch):
    from image_clarus import schema_worker

    c = request.getfixturevalue("context")
    c.config["stages"]["json"]["validation_retries"] = 2
    monkeypatch.setattr(
        schema_worker, "validate", lambda *args, **kwargs: {"status": "timeout"}
    )
    result = run(c)
    assert result.status == "failed"
    assert result.error_category == "configuration"
    assert len(c.requests) == 1
    assert not c.output.exists()
