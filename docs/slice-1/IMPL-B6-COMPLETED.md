# Step B6 — Implement the description stage (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. CLI integration, JSON-stage work and end-to-end signal handling remain B7–B8/C1–C2.

**Files created:** `src/image_clarus/stages/__init__.py`, `src/image_clarus/stages/description.py`, `tests/unit/test_description_stage.py`, and this record.

**Files updated:** `src/image_clarus/artifacts.py`, `src/image_clarus/config.py`, `tests/unit/test_config.py`, `docs/slice-1/IMPL-B2-COMPLETED.md`, `docs/slice-1/IMPL-B5-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.

**Files removed:** None.

## Summary

Implemented the B4-compatible description stage. It uses the full image filename plus `.desc.txt`, validates existing descriptions as nonblank UTF-8, performs recovery before deciding whether to skip, and writes generated UTF-8 only through the shared artifact service. Explicit regeneration permits replacement of invalid or valid existing descriptions; failed generation does not publish a completed output. It uses the selected provider/model and reasoning, and reads the canonical or overridden prompt without trimming or appended instructions. Its shared services must provide the configured artifact service and a `provider_factory(provider, model)`; B8 owns constructing those services and invoking preflight.

An independent audit identified two integration issues corrected in this step. Environment-backed credentials containing only whitespace now fail selected-stage authentication preflight, consistent with the provider. During explicit regeneration, recovery retains an existing backup until the write succeeds; otherwise a provider failure could remove a backup before generation. The artifact recovery API now permits deferring retention, and the normal configured retention is applied on successful write. The audit also observed that the HTTP adapter accepts a UTF-16 JSON response envelope; A4 requires JSON media and valid JSON but does not explicitly freeze envelope encoding. This observation is not presented as a UTF-8 response-enforcement test or changed as part of B6.

## Verification and test-first evidence

- Behavioral RED → GREEN was observed for creation through the coordinator, valid existing skip, invalid existing failure, explicit regeneration, exact built-in/custom prompt selection, selected model/provider/effort, provider failure, blank provider content, safe-write failure, unreadable image, and sanitized prompt read failure. The creation RED exercised an intentionally failing stage stub. Recovery, unsupported suffix, reasoning inheritance, and invalid UTF-8 existing-artifact tests were supplemental first-run GREEN coverage, not historical RED.
- The whitespace-only environment credential regression failed because no `ConfigurationError` was raised before the B2 correction and passed afterward. The existing-backup/provider-failure regression failed because the backup was removed before the retention correction and passed afterward; successful `remove` and `retain` cases are supplemental GREEN tests.
- `uv run --locked --extra dev pytest tests/unit/test_description_stage.py -q` — **21 passed**. Tests use synthetic image bytes, the real provider adapter with `httpx.MockTransport`, and the real artifact service, including a B4 `desc`-only coordinator invocation. They do not call a live provider or use real credentials.
- `uv run --locked --extra dev pytest -q` — **183 passed**. Ruff lint and format, `uv lock --check`, and `uv build --python 3.13` passed.
- The test checks original synthetic image bytes remain unchanged and the sidecar path uses the complete filename. CLI input resolution, public CLI behavior and broader source-integrity scenarios remain B8/C1–C2. Signal and process-death behavior remain C2; Python 3.12 runtime verification remains C3.

## Acceptance

- [x] `desc` works alone and writes exactly `<image>.desc.txt` beside the input.
- [x] The default prompt is byte-for-byte consistent with the existing resource; prompt override works independently.
- [x] Existing output is skipped by default and replaced only on explicit regeneration.
- [x] Empty/whitespace-only responses and other failures are reported and leave no falsely completed output.
- [x] RED/GREEN and regression evidence is recorded; [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md) is linked.

## Follow-up

B7 and later steps have not started. This does not claim the `process` CLI is wired or that a real provider has been contacted.

**Subsequent progress:** B7 is complete; see [IMPL-B7-COMPLETED.md](IMPL-B7-COMPLETED.md). B8 and later work remain open.
