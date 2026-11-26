# Step C1 - Verify batch behavior through the CLI [TEST]

**Status:** Complete and ready for review; review acceptance is separate. C2–C4 have not been started by this step.

**Version:** 0.3.54. Verification environment: Linux, Python 3.13.15, ExifTool 13.10.

## Evidence

- `tests/integration/test_slice4_c1_selection.py` exercises CLI selection, default extension candidates, depth, literal and pattern paths, overlaps, explicit/discovered symlinks, contextual prerequisites, admission and invalid-selection boundaries. Discovery eligibility does not establish decoding support for every extension.
- `tests/integration/test_c1_plan_parity.py` compares exact ordered admission identities and the allowance boundary across two roots in both modes. The CLI does not print the execution plan: test-only child instrumentation snapshots the immutable initial plan at runner entry and compares it with dry-run output.
- `tests/integration/test_slice4_c1_overlap.py` and `test_stage_lifetimes.py` use loopback inference and barriers to observe concurrent stage activity, actor ownership, per-image ordering and sequential behavior; the latter includes real ExifTool XMP publication. A preliminary probe incorrectly counted a parked inference and a nested confirmation on the same actor as concurrent execution; the corrected instrumentation separates them. This is evidence for the exercised paths, not a platform-wide scheduling proof.
- `tests/integration/test_slice4_c1_budget.py`, `test_slice4_c1_corrections.py` and `test_slice4_c1_progressive*.py` cover regeneration, no refill after failure, initially excluded images, actual corrections beyond N and 2N, and actual XMP evaluations. The successful 10,000-image in-process fixture records 6,000 no-work, 1,000 admitted and 3,000 excluded; initial routes 1,000/0/9,000; 1,000 successful controlled description and 1,000 structured requests; 10,000 XMP evaluation entries and 30,000 stage dispositions. Real stages validate and publish generated description and JSON; disabled XMP policies produce no XMP writes. Separate real CLI tests exercise XMP publication; 10,000 evaluations do not mean 10,000 writes.
- `tests/integration/test_slice4_c1_state.py`, `test_c1_state_config_selection.py` and `test_c1_memory_fallback_batch.py` exercise image/CWD/explicit/YAML/generic state selection in both modes, generated and valid-skipped accumulation, sequential visibility, memory and selected corrupt-store fallback without substitution. Concurrent memory selection is exercised but deterministic cross-image memory visibility under concurrent timing is not independently established.
- `tests/integration/test_c1_dry_run_safety_matrix.py` and `test_c1_e19_boundaries.py` guard CLI content access, mutation, network, processes, ExifTool lookup and file logging in applicable dry-run/startup cases; independently probe guards; check empty real execution, static validation and missing runtime dependency. The old-state fixture is unsupported version 0, not proven migratable. Estimates are labeled estimates, not peak bounds.
- E01–E12 and E17–E19 are supported by these tests together with the previously implemented discovery, planner, execution, reporter, state and XMP suites. E10, E12 and E18 include failure/continuation work also assigned to C2; this record does not assert that C2's complete matrix has run. E02 also has C3 packaging/regression ownership.

## Verification

- With ExifTool available on PATH, `.venv/bin/python -m pytest -q -p no:cacheprovider` — **1,944 passed in 873.98s**. Tests use synthetic data and controlled providers; no live provider was contacted.
- Focused final additions: `.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_stage_lifetimes.py tests/integration/test_c1_plan_parity.py` — **4 passed** with ExifTool available.
- `uv lock --check`, `uv run --no-sync --locked ruff check .`, `uv run --no-sync --locked ruff format --check .`, and CLI version check passed. ExifTool was supplied in an isolated temporary tool directory.
- An earlier full attempt reported 1,921 passed, 2 skipped and 4 failed because its background PATH lacked the package tool and its isolated child could not load the temporary ExifTool's Perl libraries. All four passed in a corrected focused rerun; the full result above is the subsequent corrected run.

## Acceptance

- [x] Real CLI evidence establishes native selection/planning/execution, actual overlap/sequential behavior and stage subsets.
- [x] Budget/correction/routing examples reconcile distinct image and stage counts without treating XMP evaluation as guaranteed publication.
- [x] State identity, accumulation timing, dry-run boundaries, verbose output and estimates have observable evidence.
- [x] Every covered acceptance row identifies commands, assertions, versions and limitations rather than inferring success from unit mocks.

## Limits

No Windows runtime, live provider, physical storage fault, or 10,000 ExifTool writes were tested. Full failure-policy/signal/resume verification belongs to C2; the fresh multi-version packaging gates belong to C3. Nothing here claims review acceptance or Slice 4 closeout.
