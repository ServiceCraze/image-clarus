import json


def test_signal_during_worker_spawn_reaps_child(monkeypatch):
    import os
    import signal
    import subprocess

    import pytest

    from image_clarus import schema_worker

    class Interrupted(BaseException):
        pass

    children = []
    real_popen = subprocess.Popen
    previous = signal.signal(
        signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Interrupted())
    )

    def spawn(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        children.append(process)
        os.kill(os.getpid(), signal.SIGTERM)
        return process

    monkeypatch.setattr(schema_worker.subprocess, "Popen", spawn)
    try:
        with pytest.raises(Interrupted):
            schema_worker.preflight("{}", timeout=5)
        assert children[0].poll() is not None
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
        signal.signal(signal.SIGTERM, previous)


def test_preflight_accepts_valid_schema():
    from image_clarus.schema_worker import preflight

    result = preflight(json.dumps({"type": "object"}), timeout=5)
    assert result == {"status": "ok"}


def test_validation_returns_normalized_feedback():
    from image_clarus.schema_worker import validate

    schema = json.dumps({"type": "object", "properties": {"age": {"type": "integer"}}})
    assert validate(schema, {"age": "bad"}, timeout=5) == {
        "status": "invalid_instance",
        "feedback": {
            "kind": "schema_validation",
            "total_errors": 1,
            "truncated": False,
            "errors": [
                {
                    "instance_path": "/age",
                    "schema_path": "/properties/age/type",
                    "keyword": "type",
                }
            ],
        },
    }


def test_worker_is_reaped_if_communication_fails(monkeypatch):
    import subprocess

    from image_clarus import schema_worker

    created = []
    real_popen = subprocess.Popen

    def start(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)

        def fail(*args, **kwargs):
            raise OSError("private sentinel")

        monkeypatch.setattr(process, "communicate", fail)
        return process

    monkeypatch.setattr(schema_worker.subprocess, "Popen", start)
    assert schema_worker.preflight('{"type":"object"}', timeout=5) == {
        "status": "worker_error"
    }
    assert created[0].poll() is not None


def test_catastrophic_regex_times_out_and_child_is_reaped(monkeypatch):
    import subprocess
    import time

    from image_clarus import schema_worker

    created = []
    real_popen = subprocess.Popen

    def start(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(schema_worker.subprocess, "Popen", start)
    schema = json.dumps(
        {"type": "object", "properties": {"value": {"pattern": "^(a+)+$"}}}
    )
    started = time.monotonic()
    result = schema_worker.validate(schema, {"value": "a" * 10000 + "!"}, timeout=1)
    assert result == {"status": "timeout"}
    assert time.monotonic() - started < 4
    assert created[0].poll() is not None


def test_crash_and_invalid_schema_are_sanitized(monkeypatch):
    import subprocess

    from image_clarus import schema_worker

    created = []
    real_popen = subprocess.Popen

    def start(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(schema_worker.subprocess, "Popen", start)
    assert schema_worker._run(
        {"operation": "bad", "schema": '{"type":"object"}'}, 5
    ) == {"status": "worker_error"}
    assert created[-1].poll() is not None
    assert schema_worker.preflight('{"type":"private sentinel"}', timeout=5) == {
        "status": "invalid_schema"
    }


def test_results_after_deadline_are_not_accepted(monkeypatch):
    from image_clarus import schema_worker

    real_clock = schema_worker.time.monotonic
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return real_clock() + (10 if calls >= 4 else 0)

    monkeypatch.setattr(schema_worker.time, "monotonic", clock)
    assert schema_worker.preflight('{"type":"object"}', timeout=5) == {
        "status": "timeout"
    }


def test_valid_instance_and_large_input():
    from image_clarus.schema_worker import validate

    schema = '{"type":"object"}'
    assert validate(schema, {"text": "x" * 200000}, timeout=5) == {"status": "ok"}


def test_nonprogressing_reference_is_sanitized():
    from image_clarus.schema_worker import validate

    schema = '{"type":"object","properties":{"x":{"$ref":"#/$defs/cycle"}},"$defs":{"cycle":{"$ref":"#/$defs/cycle"}}}'
    assert validate(schema, {"x": 1}, timeout=5) == {"status": "worker_error"}
