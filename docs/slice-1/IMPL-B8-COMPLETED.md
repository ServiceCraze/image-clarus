# Step B8 — Wire the single-image `process` command (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. Detailed interruption, process-death, independent-process overlap and filesystem fault acceptance remain assigned to [C1](IMPL-PLAN-slice-1.md#step-c1--verify-independent-stage-execution-and-persisted-handoff-test) and [C2](IMPL-PLAN-slice-1.md#step-c2--verify-failure-recovery-source-integrity-and-credential-hygiene-test).

**Files created:** `tests/unit/test_cli_acceptance.py`, `tests/unit/test_cli_b8_contract.py`, `tests/unit/test_cli_artifact_acceptance.py`, `tests/unit/test_cli_config_acceptance.py`, and this record.

**Files updated:** `src/image_clarus/cli.py`, `src/image_clarus/schema_worker.py`, `tests/unit/test_cli.py`, `tests/unit/test_schema_worker.py`, `docs/slice-1/IMPL-B7-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.

**Files removed:** None.

## Summary

Wired one-image processing to selected-stage config preflight, the ordered coordinator, real stage and shared artifact/provider services, and A2's stdout/stderr and exit contracts. Stage selection remains explicit, outputs are create-only unless regenerated, and JSON reads the persisted description. Help, version and the help-only search stub remain available without executing a pipeline. Single-use flags and unknown options are checked; `--set` is repeatable and dedicated overrides take precedence. Logging level is applied to console diagnostics. Configured credentials are redacted from displayed results, including when they appear in an output path.

SIGINT/SIGTERM are captured with signal-priority exit codes. Tests cover cancelling stalled provider calls, interruption of schema preflight with worker cleanup, no subsequent publication before a write, and completion of an already-started write. Worker startup masks signals until cleanup owns the child on platforms with `pthread_sigmask`. Schema validation after preflight can remain blocked until its bounded worker timeout; provider cancellation cannot guarantee that a remote server stops processing. Signal delivery during native operations, the pre-write boundary, and broader process-level fault scenarios are not exhaustively proven here; C2 owns the full interruption acceptance matrix. Linux is the required test platform.

## Verification and TDD evidence

- `uv run --locked --extra dev pytest -q` — **385 passed** after the Patch 025 correction. `ruff check .`, `ruff format --check .`, `uv lock --locked`, and `uv build` passed.
- A fresh Python 3.13 environment installed the built wheel with normal dependencies. From outside the checkout with `PYTHONPATH` cleared, installed `image-clarus --version`, `process --help`, and the exact search stub message/status passed.
- Synthetic localhost HTTP stubs exercised default and reversed combined selection, persisted description handoff, desc-only and json-only operation, path/config precedence, dedicated prompt/schema overrides, regeneration, failure policies, credential handling and unchanged source image. No live provider was contacted.
- Behavioral RED then GREEN was observed for the missing-image error, existing-output skip, JSON missing prerequisite, combined persisted handoff, dedicated missing-prerequisite override, duplicate stage selection and singleton options, missing configuration, regeneration, selected prompt validation, signal-before-publication, stalled-provider cancellation, signal during schema preflight/worker spawn/path validation/summary, credential redaction, unknown option abbreviation and configured logging. The five singleton-option parameter cases and the two signal parameter cases were run as batches. The first glob-path test passed for the wrong reason; after correcting the test setup, it failed on the intended behavior and passed after the fix.
- Supplemental tests added after implementation, including the independent black-box A2 matrix, successful custom JSON-prompt override and safe-write checkpoint checks, first ran GREEN; they are not historical RED evidence. Following a coverage crosswalk, subprocess tests also exercised two-output regeneration, invalid artifact preservation, JSON skip ordering, typed overrides and discovery precedence. Discovery tests redirect user/system paths with `sitecustomize`; platform path construction is separately covered by config tests. Provider failure redaction uses a real synthetic HTTP failure, while injected stage-message redaction is exercised in-process. The description-prompt RED test attempted a connection to a local `127.0.0.1` endpoint; it did not use a live provider.
- Patch 025 review reproduced an interrupted stage reporting an ordinary failure. The in-process stage-double regression, using real SIGINT/SIGTERM for both `desc` and `json`, failed all four cases with `failed / file_io` before the fix and passed all four afterward as `skipped / interrupted`. Two existing real-signal safe-write tests also passed, preserving completed results after a write reaches its safe boundary.

## Acceptance

- [x] Every accepted CLI option and behavior from A2 has a black-box test.
- [x] Stage selection, config precedence, result display, and exit behavior match their contracts.
- [x] The CLI does not modify the source image and does not silently invoke unselected stages.
- [x] Top-level, `process`, and `search` help work; executing `search` reports not implemented, with no Slice 1 search matching.
- [x] RED/GREEN and regression evidence is recorded; [IMPL-B8-COMPLETED.md](IMPL-B8-COMPLETED.md) is linked.

B9 and Phase C have not been started as part of B8.
