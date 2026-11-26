# Step M1 - Implement strict category list and clear [CODE]

**Status:** Implementation complete and ready for review. This status does not indicate review acceptance; M2 and later steps have not been started.

**Version:** 0.3.49

**Scope deviations:** None.

**Files:** Created `src/image_clarus/state/management.py`, `src/image_clarus/state/readonly.py`, `tests/unit/test_state_management.py`, `tests/unit/test_state_readonly.py`, `tests/integration/test_state_management_cli.py`, and this record. Updated `src/image_clarus/cli.py`, `tests/unit/test_slice4_config.py`, `docs/slice-4/IMPL-PLAN-slice-4.md`, `pyproject.toml`, and `uv.lock`. No files deleted.

## Implementation

- Added strict persistent target selection using explicit/configured selection or CWD ancestry; missing or invalid selections fail rather than falling back to invocation-local memory. Retained target identity is checked when available, without asserting race-free pathname pinning.
- Added `state/readonly.py`: a standard-library SQLite `mode=ro` connection establishes a snapshot before authoritative repository recognition and category enumeration. It does not initialize or migrate the store. Normal SQLite and operating-system read-related filesystem effects remain allowed.
- Added `state/management.py`: clear revalidates the selected target under `BEGIN IMMEDIATE`, applies a registered migration and category deletion in the same transaction, checks interruption before commit, and reports uncertain commits without claiming deletion. Other domains remain intact.
- Wired list and clear into the actual CLI. List emits one JSON-quoted category per line; clear reports target origin before mutation and a count after confirmed commit. Strict state errors use sanitized stderr and nonzero status; rebuild remains a stub for M2.

## Verification

- `uv run --no-sync --locked pytest tests/unit/test_state_management.py tests/unit/test_state_readonly.py tests/integration/test_state_management_cli.py tests/unit/test_slice4_config.py tests/integration/test_state_cli.py -q` — **69 passed**.
- `uv run --no-sync --locked pytest -q -p no:cacheprovider` — **1,759 passed, 67 skipped**.
- `uv lock --check`, `ruff check .`, and `ruff format --check .` — passed; 194 files formatted.
- `image-clarus --version` under the locked environment — `image-clarus 0.3.49`.
- Built the wheel, installed it with dependencies into a separate environment, and ran its CLI outside the checkout with `PYTHONPATH` unset against a synthetic store: list returned the expected JSON-quoted category. The wheel was a pure-Python wheel; no custom SQLite package was built.
- Tests cover data/schema preservation, migration-required and corrupt stores, rollback-journal and WAL reads, concurrent writer snapshots, exclusive-lock failure, strict target failure, category-only clear, empty clear, migration and rollback, precommit stop, injected begin/delete/commit failures, target replacement and unavailable identity capability. Permission denial is an injected failure, not an OS permissions test.
- Existing ordinary-processing state CLI tests passed in the focused run; they exercise its separate nonblocking state behavior. No live provider or personal data was used.

## Acceptance

- [x] List is logically data/schema read-only throughout opening/validation/reporting, including migration-needed and inaccessible-store cases; normal SQLite and OS read effects are allowed.
- [x] Missing or invalid persistent state cannot appear as an empty successful persistent listing.
- [x] Clear removes categories only, with any registered migration in the same transaction, and reports transaction/access failures accurately without another persistent destination or memory substitution.
- [x] Dedicated command behavior and ordinary optional-processing state behavior remain distinct and tested.

## Evidence limits

WAL and rollback-journal tests used independent SQLite connections in the test process; independent-process category command concurrency belongs to M3. Transaction failures and permission denial were injected, not physical storage failures. No Windows runtime test was performed. Target identity checks cannot eliminate all external replacement races. Commit errors are conservatively reported as unknown rather than automatically retried.
