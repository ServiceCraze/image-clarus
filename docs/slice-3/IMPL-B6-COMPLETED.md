# Step B6 - Integrate category accumulation after processing [CODE] (COMPLETED)

**Status:** Complete for post-image category accumulation. B7 documentation and Phase C cross-step verification remain open.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `src/image_clarus/state/accumulation.py`, `tests/unit/test_state_accumulation.py`, `tests/unit/test_cli_state_accumulation.py`, `tests/integration/test_state_accumulation_cli.py`, `tests/integration/test_state_accumulation_timing.py`, `tests/integration/test_state_accumulation_signals.py`, and this record.
- Updated: `src/image_clarus/cli.py`, `src/image_clarus/state/storage.py`, `tests/unit/test_state_storage.py`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, `pyproject.toml`, `uv.lock`, the Slice 3 plan and predecessor progress notes.
- Removed: None.

## Behavior and acceptance evidence

1. After the selected pipeline returns and before the invocation-local state service closes, the CLI invokes optional accumulation once. Only selected JSON results completed or skipped as `output_exists` qualify; other results and interrupted work do not. A later-stage failure does not undo eligible JSON or alter its result. The coordinator remains free of category policy.
2. Extraction reads one persisted snapshot and applies the existing envelope validity contract. Exact built-in v1/v2 and custom identities are distinguished; v1 contributes no candidates. For recognized v2/custom envelopes, missing or empty candidates contribute nothing, valid complete paths are deduplicated, and a malformed entry rejects the entire optional contribution. It does not require unrelated payload fields or the current custom schema and does not alter the source sidecar.
3. Accumulation defaults on and can be disabled for generated and existing JSON. Independent CLI processes shared an initialized SQLite repository across unrelated image directories: a later process expanded accumulated categories in a synthetic-provider request. An existing valid JSON skip contributed without regeneration or a model request and retained identical artifact bytes.
4. A separate-process barrier test held the actual later XMP stage after its real ExifTool-backed planner, observed the unchanged repository while that stage was in progress, then released it and observed the completed update; the disabled case remained unchanged. Injected orchestration tests separately cover later-stage failure and the influence of prompt depth, XMP root and limit. Stored category paths remain complete.
5. Optional read and state update failures emit sanitized visible diagnostics and preserve primary results, exit behavior and artifacts. The storage service retains its existing nonpersistent fallback and does not retry a failed union in memory. No external provider or private data was used.
6. An independent audit reproduced a stop during the final busy-timeout setup before commit still allowing a write. Stop checks now occur immediately after that setup and before commit for initialization, migration and category union. Six injected stop-token regression cases first failed, then passed with rollback checked from a separate connection.

## Verification and limitations

- Initial direct-component RED was a missing-module collection failure, not behavioral evidence. Before CLI wiring, an independent skipped-JSON invocation failed behaviorally because state remained empty; the focused accumulation and state suite subsequently passed **72 tests**. The original ordering test used an injected pipeline; the later real XMP-stage barrier test provides separate stronger timing evidence.
- The pre-commit correction produced **6 observed failures** before the fix and **6 passes** after it. Independent CLI processes also received actual SIGINT and SIGTERM at controlled pre-BEGIN, pre-COMMIT-check, and immediately-after-COMMIT checkpoints; all six cases passed, preserving signal exit and sidecar bytes. The after-COMMIT checkpoint proves a committed result at that boundary, not a signal delivered inside SQLite's commit syscall. Atomic coupling between state and sidecars is not claimed.
- The first full suite found **8 failures** from a stage-selection test double that omitted the now-consumed resolved setting. Updating that double to match resolved configuration yielded **8 focused passes**. The final full suite, with temporary ExifTool 13.55 on `PATH`, passed **1,163 tests**, no skips. Ruff check and format check passed; **143 files** formatted. `uv lock --locked` resolved **21 packages** and the CLI reported **0.2.13**.
- Separate-process and failure-injection tests use fictional images, state and a local synthetic provider. They do not establish live-provider behavior, power-loss durability, or a deterministic winner for concurrent sidecar writers.

## B6 acceptance

- [x] An observer confirms accumulation occurs after selected stages finish, not between JSON and another selected stage.
- [x] Default-enabled successful JSON contributes complete paths; a later independent CLI invocation can expand them.
- [x] Existing valid selected JSON contributes without a request or changed artifact bytes; disabling accumulation prevents updates in both generated and skipped cases.
- [x] State-read/update failure emits a visible error while preserving primary results, exit behavior, and sidecars.
- [x] Eligibility tests distinguish `output_exists` from other skips/failures and retain the established JSON validation/skip contract.
- [x] Extraction is independent of prompt depth, XMP selection, XMP ownership root, and publication limit.
