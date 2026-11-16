"""Run selected-schema operations in a disposable, time-limited process.

Only JSON data crosses the process boundary. Never put credentials in a request.
The timeout includes serialization and child startup; OS process creation and the
final kill/reap are not themselves interruptible. This is not a memory sandbox.
"""

import json
import math
import signal
import subprocess
import sys
import time

SCHEMA_TIMEOUT_SECONDS = 10


class _Snapshot:
    def __init__(self, text):
        self.text = text

    def read_text(self, encoding):
        return self.text


def _run(request, timeout):
    start = time.monotonic()
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be a positive finite number")
    try:
        payload = json.dumps(request, allow_nan=False).encode("utf-8")
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            return {"status": "timeout"}
        # Defer CLI interrupts until the child is registered for cleanup.
        process = None
        old_mask = None
        try:
            if hasattr(signal, "pthread_sigmask"):
                old_mask = signal.pthread_sigmask(
                    signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM}
                )
            process = subprocess.Popen(
                [sys.executable, "-m", "image_clarus.schema_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if old_mask is not None:
                mask, old_mask = old_mask, None
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            output, _ = process.communicate(
                payload, timeout=max(0, timeout - (time.monotonic() - start))
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}
        finally:
            try:
                if old_mask is not None:
                    signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    if process.stdin:
                        process.stdin.close()
                    if process.stdout:
                        process.stdout.close()
        if time.monotonic() - start >= timeout:
            return {"status": "timeout"}
        if process.returncode != 0:
            return {"status": "worker_error"}
        result = json.loads(output)
        if not isinstance(result, dict):
            return {"status": "worker_error"}
        return result
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return {"status": "worker_error"}


def preflight(schema_json, *, timeout):
    """Check a JSON schema snapshot; return a sanitized status dictionary."""
    return _run({"operation": "preflight", "schema": schema_json}, timeout)


def validate(schema_json, instance, *, timeout):
    """Validate an instance, returning normalized feedback on failure."""
    return _run(
        {"operation": "validate", "schema": schema_json, "instance": instance}, timeout
    )


def _validation_errors(schema, instance):
    """Capture boolean locations at descent, before jsonschema loses them.

    This instrumentation is confined to the disposable validation process.
    All keyword implementations and non-boolean descent remain jsonschema's.
    """
    from jsonschema import Draft202012Validator
    from jsonschema.validators import _META_SCHEMAS
    from referencing import Registry

    from image_clarus.stages.structure import _resolve_ref, _schema_nodes

    nodes = _schema_nodes(schema)
    active = []
    classes = set(_META_SCHEMAS.values()) | {Draft202012Validator}
    originals = {cls: (cls.descend, cls.VALIDATORS.copy()) for cls in classes}

    def wrap(keyword, function):
        def run(validator, value, instance, parent):
            active.append((keyword, value, parent))
            try:
                yield from function(validator, value, instance, parent) or ()
            finally:
                active.pop()

        return run

    root_schema = schema

    def wrap_descend(original_descend):
        def descend(
            validator, instance, schema, path=None, schema_path=None, resolver=None
        ):
            for error in original_descend(
                validator, instance, schema, path, schema_path, resolver
            ):
                if schema is False and active:
                    keyword, value, parent = active[-1]
                    parent_path = nodes.get(id(parent))
                    if keyword == "$ref":
                        resolved = _resolve_ref(root_schema, value)
                        location = resolved[0] if resolved is not None else None
                    elif (
                        keyword == "if"
                        and schema_path in ("then", "else")
                        and parent_path is not None
                    ):
                        location = parent_path + (schema_path,)
                    elif parent_path is not None:
                        location = parent_path + (keyword,)
                        if schema_path is not None:
                            location += (schema_path,)
                    else:
                        location = None
                    if location is not None:
                        error._actual_boolean_schema_path = location
                    if path is not None:
                        error.path.appendleft(path)
                    if schema_path is not None:
                        error.schema_path.appendleft(schema_path)
                yield error

        return descend

    try:
        for cls, (original_descend, validators) in originals.items():
            cls.descend = wrap_descend(original_descend)
            cls.VALIDATORS.update(
                {key: wrap(key, function) for key, function in validators.items()}
            )
        return list(
            Draft202012Validator(schema, registry=Registry()).iter_errors(instance)
        )
    finally:
        for cls, (original_descend, validators) in originals.items():
            cls.descend = original_descend
            cls.VALIDATORS.clear()
            cls.VALIDATORS.update(validators)


def _main():
    try:
        request = json.load(sys.stdin)
        from image_clarus.config import ConfigurationError, _check_schema

        try:
            _check_schema(_Snapshot(request["schema"]))
        except ConfigurationError:
            result = {"status": "invalid_schema"}
        else:
            if request["operation"] == "preflight":
                result = {"status": "ok"}
            elif request["operation"] == "validate":
                from image_clarus.stages.structure import _feedback

                schema = json.loads(request["schema"])
                errors = _validation_errors(schema, request["instance"])
                result = (
                    {
                        "status": "invalid_instance",
                        "feedback": _feedback(schema, errors),
                    }
                    if errors
                    else {"status": "ok"}
                )
            else:
                return 1
        json.dump(result, sys.stdout, allow_nan=False)
    except Exception:  # noqa: BLE001 - never disclose worker exceptions
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
