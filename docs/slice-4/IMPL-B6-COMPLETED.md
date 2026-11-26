# Step B6 - Integrate dry-run progress and actual metrics [CODE]

**Status:** Complete. B6 integrates discovery, metadata-only planning, batch execution,
and A4 reporting at the `process` CLI boundary. B6 is implementation-complete and
ready for review; this does not start any later plan step.

**Version:** 0.3.48

**Scope deviations:** None.

## Files created/updated

- Created: `src/image_clarus/batch_reporting.py`,
  `tests/unit/test_b6_cli_reporting.py`.
- Updated: `src/image_clarus/cli.py`, `tests/unit/test_slice4_config.py`,
  `pyproject.toml`, `uv.lock`, `docs/slice-4/IMPL-PLAN-slice-4.md`, this record.
- Removed: None.

## What is implemented

- `process --dry-run` uses deterministic discovery and the shared planner without
  constructing state, artifact, provider, or XMP execution services. It streams
  JSON-quoted provisional file rows, then emits immutable admission totals and
  the A4-labeled initial plan/queue memory estimate after planning completes.
  Incomplete plans report the estimate as unavailable on stderr.
- Directory/pattern and multi-selection execution uses the completed planner and
  selects B5 concurrent execution from the resolved default; a disabled
  concurrency setting selects the sequential executor.
- `BatchReporter` reduces serialized coordinator events into bounded summaries:
  planned bypasses, actual evaluation/transformation/outcome counts, skip reasons,
  request/retry and distinct LLM/corrective-image counts, XMP evaluation/write
  counters, accounted progress, and monotonic elapsed time. Verbose execution
  renders escaped per-stage start/end rows.
- Single-token directories and native patterns use batch defaults even when they
  resolve to one image. State diagnostics retain their existing direct stderr
  rendering without duplicate summary output. The reducer reconciles complete
  provider identities and terminal events against executor results and immutable
  plan generation/admission classifications; incomplete or conflicting accounting
  produces a sanitized failure instead of a successful result, including on the
  concise explicit-file path. Dry-run config
  and stage-selection failures render the required incomplete-plan/estimate-
  unavailable diagnostics, and configured secrets are redacted before every
  displayed path is quoted.
- Explicit-file compatibility now routes configuration- and override-resolved
  `on_stage_failure: abort` through the B6 executor path. Recognized dry-run
  argument errors also emit the incomplete-plan and unavailable-estimate
  diagnostics before argparse exits.
- Existing explicit-file, nonverbose concise stage lines remain on their
  established compatibility path. Batch output is a bounded summary rather than
  an unbounded path listing.

## Verification performed

- `uv run --no-sync --locked pytest tests/unit/test_b6_cli_routing.py tests/unit/test_b6_cli_reporting.py tests/unit/test_slice4_config.py tests/unit/test_cli.py -q` — **109 passed**.
- `uv run --no-sync --locked pytest -q -p no:cacheprovider` — **1,731 passed, 67 skipped**.
- `uv lock --check` — passed.
- `uv run --no-sync --locked ruff check .` — passed.
- `uv run --no-sync --locked ruff format --check .` — passed after the correction.
- `uv run --no-sync --locked image-clarus --version` — `image-clarus 0.3.48`.
- Direct CLI smoke: two synthetic images with existing fictional description
  sidecars produced a concurrent batch summary with two authoritative
  `output_exists` skips and no provider requests.

## Acceptance disposition

- [x] Single-image compatibility and default concurrent batch behavior are reachable through the actual CLI.
- [x] Dry-run maintains the metadata-only execution boundary, prints the completed-plan estimate, and marks an incomplete estimate unavailable.
- [x] CLI dry-run emits deterministic file-level no-work, admitted, and known-excluded rows and marks the Nth admitted row as `budget=reached`.
- [x] Reporter metrics distinguish immutable plan classes from actual event-derived evaluation, transformation, requests, skips, outcomes, and corrective work.
- [x] Progress uses terminal accounting pairs, including zero-work rendering, rather than successful-operation percentages.
- [x] Required output is channel-separated; paths are JSON-quoted; concise explicit-file output remains compatible.
- [x] Follow-up reporting corrections cover single-token batch defaults, nonduplicated state diagnostics, complete event/result identity reconciliation (including immutable terminal generation/admission), concise-path reconciliation, incomplete dry-run diagnostics, and path-secret redaction.
- [x] Follow-up CLI routing corrections apply resolved abort policy to explicit-file execution and emit incomplete dry-run diagnostics for recognized argument errors.

## Evidence limits

- No live provider was called. Provider-boundary, correction, failure, abort, and
  signal behavior remain covered with synthetic/injected executor tests; C1/C2
  own further integrated CLI acceptance scenarios.
- Windows runtime behavior was not exercised. The existing platform limitation
  remains unchanged.
