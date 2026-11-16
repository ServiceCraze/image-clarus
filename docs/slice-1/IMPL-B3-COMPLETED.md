# Step B3 — Implement the OpenAI-compatible provider adapter (COMPLETED)

**Status:** Complete.
**Scope deviations:** None. B3 implements the provider boundary, not stage/coordinator or CLI wiring.
**Files created:** `src/image_clarus/providers/__init__.py`, `src/image_clarus/providers/openai_compatible.py`, `tests/unit/test_openai_compatible.py`, and this record.
**Files updated:** `src/image_clarus/config.py`, `tests/unit/test_config.py` (the selected-stage URL preflight correction described below), `docs/slice-1/IMPL-B2-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.
**Files removed:** None.

## Summary

Implemented the synchronous Chat Completions boundary for independent description and structured requests, including model/reasoning selection, image data URLs, JSON mode and validation-feedback history, authentication, response/error classification, and fixed sanitized provider errors. Tests use synthetic bytes, text, dummy credentials and `httpx.MockTransport`; no live provider requests or real credentials were used. Integration with stages remains B6/B7 work.

An audit found an HTTPX-invalid URL accepted by both the B2 preflight and B3 endpoint checker, which could escape with its hostname in an exception. Both boundaries now validate with HTTPX and report sanitized configuration failures before transport. This is a correction to the existing B2 validation path, not a new configuration policy.

## Verification and TDD evidence

- Initial focused image-request test failed because the adapter module was missing, then passed after implementation. An initial broader provider-behavior batch reported 33 failing and one passing test before its implementation; additional tests were added during development and some passed immediately on first execution. Not every individual supplemental case has an independently observed RED; no retrospective RED is claimed.
- For the HTTPX-invalid URL defect, `uv run --locked --extra dev pytest tests/unit/test_openai_compatible.py::test_invalid_httpx_url_is_sanitized_before_transport -q` failed with an unsanitized `httpx.InvalidURL` before the fix. The corresponding B2 preflight regression also failed before the fix. Both passed after the correction, including sanitized traceback/context assertions and zero transport calls.
- Patch 018 regressions: `uv run --locked --extra dev pytest tests/unit/test_openai_compatible.py::test_nonstring_endpoint_is_sanitized_without_transport tests/unit/test_openai_compatible.py::test_missing_tls_ca_file_is_sanitized_before_network -q` initially failed with `AttributeError` and `FileNotFoundError`, respectively; both passed after the fix. The missing-CA test uses an isolated synthetic `SSL_CERT_FILE` and blocks socket connections, checking the `provider_unavailable` category and sanitized traceback/logs. Non-string endpoints now fail as `configuration` before transport.
- The provider tests exercise request construction and MIME mappings, JSON request parts and retry history, reasoning selection, error categories, authentication, no automatic retry, malformed responses, and redaction. The supplemental logging test invokes httpcore's trace machinery inside `MockTransport`, verifying filtering during the provider call and normal logging outside it; it is not a real-network transport test.
- After Patch 018, `uv run --locked --extra dev pytest -q` — **104 passed**. `ruff check .`, `ruff format --check .`, `uv lock --check`, and `uv build --python 3.13` passed. Python 3.12 compatibility remains C3 work.

## Acceptance

- [x] Both model-driven stages can call the adapter through the contract fixed in A4.
- [x] Test coverage proves request construction, success parsing, error handling, capability handling, and secret redaction.
- [x] Automated tests use no external service or real credentials.
- [x] RED/GREEN and regression evidence is recorded; [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md) is linked.

## Follow-up

At B3 closeout, B4 and later steps remained unstarted. B4 has since completed; B5 and later steps remain unstarted. B6/B7 own stage integration and C3 owns the Python 3.12 compatibility matrix.
