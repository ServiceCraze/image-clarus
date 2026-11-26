# Step M2 - Implement additive category rebuild [CODE]

**Status:** Implementation complete and ready for review. Review acceptance is separate; M3 and later steps have not been started.

**Version:** 0.3.51

**Subsequent progress:** [M3](IMPL-M3-COMPLETED.md) adds independent-process concurrency and POSIX signal evidence; the M2 verification below remains tied to its original version.

**Scope deviations:** None.

## Implementation and decisions

- Rebuild uses strict M1 target selection and read-only recognition, independent of source location; it discovers all sidecars before mutation using B2's deterministic selection, deduplication, independent depth and case option.
- Shared extraction reads one sidecar byte snapshot and uses the existing injected envelope reader and category extraction rules; it never imports stage implementations into the state domain. Valid empty inputs do not open a writable state transaction.
- Nonempty inputs each use a short SQLite transaction. Any registered migration and the first union commit or roll back together. Existing categories are retained. Per-input failures continue; storage failure, interruption, uncertain commit or a close failure stops further updates without retrying uncertain work.
- Reports distinguish inspected and not-attempted inputs, success, skip, input failure, storage failure, unknown commit, interruption, category-bearing inputs, eligible paths, attempted and confirmed transactions, and confirmed inserts. An unknown commit marks the insert count incomplete. Target origin is printed before mutation; fixed diagnostics omit source paths and category data.
- Files created: `src/image_clarus/state/rebuild.py`, `tests/unit/test_state_rebuild.py`, `tests/integration/test_state_rebuild_cli.py`, `tests/integration/test_state_rebuild_cases.py`, and this record. Updated: `src/image_clarus/state/accumulation.py`, `src/image_clarus/state/management.py`, `src/image_clarus/state/readonly.py`, `src/image_clarus/cli.py`, related unit tests, `tests/unit/test_slice4_config.py`, `pyproject.toml`, `uv.lock`, and this slice's implementation plan. No files deleted.

## Verification

- `uv run --no-sync --locked pytest tests/unit/test_state_rebuild.py tests/unit/test_state_management.py tests/unit/test_state_readonly.py tests/unit/test_state_accumulation.py tests/unit/test_slice4_config.py tests/integration/test_state_rebuild_cli.py tests/integration/test_state_rebuild_cases.py -q` — **128 passed**.
- `uv run --no-sync --locked pytest -q -p no:cacheprovider` — **1,800 passed, 67 skipped**.
- `uv lock --check`, Ruff check and format check passed; 199 files already formatted. CLI version: `image-clarus 0.3.51`.
- Actual CLI tests include 997 valid plus three invalid sidecars, continued processing, exact inserted counts, source preservation, no-category cases, explicit versus discovered symlinks, selection deduplication, target selection, case-insensitive native pattern and depth. Earlier CLI tests observed the stub fail before integration.
- Unit tests cover recognition and migration without unintended mutation, migration plus union commit/rollback, injected transaction/close and interruption outcomes, category counts, unknown commit, and ordinary accumulation extraction. The 997-input run uses fictional local data and no live provider.

## Acceptance

- [x] Rebuild retains existing categories and adds recognized full paths under current extraction rules, with no XMP/model/artifact mutation.
- [x] Independent traversal and deduplication behave as A1/A3 specify; an empty result makes no changes.
- [x] Invalid/unreadable inputs do not prevent eligible later inputs; valid partial additions remain and failures are visible.
- [x] Interrupted/failed storage operations and counts are truthful; ordinary accumulation semantics and dependency direction remain intact.

## Evidence limits

Transaction and interruption fault tests use controlled injection; they are not physical disk failures or OS-signal tests. M3 owns independent-process category concurrency and signal acceptance. Windows runtime was not tested. Retained path identity checks detect supported replacements but do not eliminate every external replacement race.
