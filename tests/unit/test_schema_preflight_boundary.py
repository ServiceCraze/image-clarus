import pytest


def test_selected_schema_preflight_timeout_is_configuration_error(
    tmp_path, monkeypatch
):
    from image_clarus import schema_worker
    from image_clarus.config import ConfigurationError, resolve_config

    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}')
    seen = []

    def timeout(schema_json, *, timeout):
        seen.append(schema_json)
        return {"status": "timeout"}

    monkeypatch.setattr(schema_worker, "preflight", timeout)
    with pytest.raises(ConfigurationError):
        resolve_config(
            stages=("json",),
            discovery_paths=(),
            overrides=[
                'providers.p.base_url="http://localhost/v1"',
                'models.m.provider="p"',
                'models.m.model_id="m"',
                'stages.json.model="m"',
                f'stages.json.schema_file="{schema}"',
            ],
        )
    assert seen == ['{"type":"object"}']
