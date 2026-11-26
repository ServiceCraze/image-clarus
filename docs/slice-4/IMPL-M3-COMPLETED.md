# Step M3 - Verify category command boundaries and concurrency [TEST]

**Status:** Complete and ready for review; review acceptance is separate. M4 and Phase C have not been started.

**Version:** 0.3.52

**Scope deviations:** None.

## Evidence and scope

- Real CLI list/clear/rebuild tests exercise CWD, configured and explicit target selection, missing and corrupt stores, clear-then-rebuild, unrelated-domain preservation and unchanged sidecars. M2's actual-CLI 997-valid/3-invalid, no-category, duplicate and source/target cases were rerun.
- Independent CLI processes overlap rebuild/rebuild between committed contributions and exercise clear/rebuild transaction orders. Listing during an uncommitted clear or rebuild sees the preceding committed snapshot. A held SQLite write transaction causes bounded rebuild failure without a claimed commit. Test-only child barriers pause real transaction/scan boundaries; they do not turn the scan into a single atomic operation.
- Real POSIX SIGINT and SIGTERM were delivered and acknowledged at pre-commit and post-commit trace barriers in separate CLI processes. Tests inspect exit, counts, persisted categories, sidecars and process cleanup. The post-commit barrier is after `commit()` returns, not inside the SQLite commit syscall.
- An actual processing CLI was held at a synthetic loopback provider while independent management CLI processes listed, cleared and rebuilt state; processing then completed and accumulated its own categories. A separate real SQLite writer lock demonstrated strict clear failure while ordinary processing published its primary artifact and emitted nonblocking state diagnostics. No live provider was used.
- Existing state fault and post-primary tests remain part of the applicable regression suite. Permission/migration fault injections are simulations; contention and OS signals above use real processes. Windows runtime and physical disk failure were not tested.

**Files:** Created `tests/integration/test_m3_cli.py`, `tests/integration/test_m3_concurrency.py`, `tests/integration/test_m3_signals.py`, `tests/integration/test_m3_processing.py`, and this record. Updated `pyproject.toml`, `uv.lock`, the Slice 4 plan and the M2 subsequent-progress note. No production code changed or files deleted.

## Verification

- `uv run --no-sync --locked pytest tests/integration/test_m3_cli.py tests/integration/test_m3_concurrency.py tests/integration/test_m3_signals.py tests/integration/test_m3_processing.py tests/integration/test_state_management_cli.py tests/integration/test_state_rebuild_cases.py tests/integration/test_state_rebuild_cli.py tests/integration/test_c1_state_inference.py tests/integration/test_c1_state_faults.py -q` — **46 passed**.
- `uv run --no-sync --locked pytest -q -p no:cacheprovider` — **1,814 passed, 67 skipped**.
- `uv lock --check`, Ruff check and Ruff format check passed; **204 files** already formatted. Locked CLI reported `image-clarus 0.3.52`.
- Signals are POSIX-specific; no Windows behavior is inferred. Test barriers and injected fault cases are not physical storage failures, power-loss tests or general latency guarantees. The final contents of a concurrent clear/rebuild depend on transaction order.

## Acceptance

- [x] Actual CLI evidence covers list read-only/open failures, category-only clear, additive/empty/partial rebuild and selection contexts.
- [x] Independent-process tests establish required sharing/transaction behavior and interruption retention without stronger whole-run guarantees.
- [x] Command counts/exits and persistence match observable outcomes; failed state access never masquerades as success.
- [x] Ordinary processing's nonblocking state and post-primary timing contracts remain covered.
