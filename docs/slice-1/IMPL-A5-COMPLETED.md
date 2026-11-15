# Step A5 — Freeze safe-write, recovery, and concurrency details

**Status:** Complete as a `[DESIGN]` step.

**Scope deviations:** None.

## Files Created/Updated/Removed

- **Created:** `docs/slice-1/IMPL-A5-COMPLETED.md` (this contract and test matrix).
- **Updated:** `docs/slice-1/IMPL-PLAN-slice-1.md` (A5 decisions, acceptance, B2/B5/C2 test obligations, and status).
- **Updated:** `docs/slice-1/IMPL-A2-COMPLETED.md` (the A5-owned backup-retention configuration leaf and subsequent-progress note).
- **Updated:** `docs/slice-1/IMPL-A3-COMPLETED.md` and `docs/slice-1/IMPL-A4-COMPLETED.md` (historical closeout status reconciled with subsequent A5 completion).
- **Updated:** `docs/HLD-image-clarus.md` §10.3 (Phase A design handoff and implementation ownership).
- **Removed:** None.

## Summary and boundary

A5 freezes a shared safe-write contract for the Slice 1 `.desc.txt` and `.desc.json` artifacts: how complete bytes are staged and validated, how an existing output is backed up and replaced, how a missing destination is recovered, what retention means, and which failures may be reported as successful. It also specifies the lock-free concurrency limit and a deterministic test matrix for B5/C2.

This record is design-only. No production code, tests, package resources, or configuration examples were created; no application tests, builds, typechecks, or provider requests were run. The artifact-service contract is reusable for later XMP work, but A5 does not add an XMP stage or authorize implementation. Erik's A3 Product Owner review remains pending, A6 remains the Phase A readiness gate, and Phase B/C implementation remains unauthorized until that gate passes.

The safe-write service owns filesystem mechanics only. The owning stage continues to decide whether an artifact is needed, whether an existing artifact is valid, whether explicit regeneration is required, and which stage-specific validator/category applies. A generation, parse, or schema-validation failure before safe-write begins must not modify the destination or its backup.

## Configuration contract

A5 adds exactly one leaf under A2's existing `pipeline` map:

| Key | Type / default | Contract |
| --- | --- | --- |
| `pipeline.backup_retention` | Enum: `remove` or `retain`; default `remove` | After the owning stage has verified the current destination, `remove` removes the `.bak` file; `retain` keeps it. Any failed write, failed recovery, or failed destination verification preserves an available backup regardless of this setting. |

The key adds no configuration root and no dedicated CLI option. It follows A2's file/default/`--set` precedence and can be overridden with `--set pipeline.backup_retention=retain`. Unknown values fail configuration validation. The A2 record and B2 tests now include this leaf; A5 owns the transaction semantics.

## Safe-write transaction

The owning stage supplies a complete byte payload and its stage-specific validator. The service must not stream partial model output directly to the target. It operates only on the stage-owned sidecar path, never on the source image path. The service treats payload bytes as opaque: it does not parse, merge, scrub, or normalize sidecar metadata. A later XMP stage must preserve unrelated metadata before supplying its bytes to this service.

1. **Recover before deciding whether output exists.** The selected stage invokes recovery before applying its normal existing-output/skip/regeneration policy. Recovery never reads or writes the source image.
2. **Prepare a unique sibling temporary file.** Create it exclusively in the destination's parent directory using an unpredictable unique name, for example `.<destination-name>.image-clarus-<random>.tmp`. A backup staging file uses a distinct sibling prefix such as `.<destination-name>.bak.image-clarus-<random>.tmp`. Never use a fixed shared `.tmp` name or a temporary file on another filesystem.
3. **Write, set mode, and verify staged bytes.** Write the entire payload and apply the final mode specified in step 4 before flushing/fsyncing and closing the file. Reopen it; require byte equality with the supplied payload, the required mode bits, and successful stage-specific validation before replacing either the destination or its backup. A failure here leaves the destination and prior backup unchanged.
4. **Apply permission behavior before publication.** Create every temporary file with mode `0600`; before flush/fsync/close, set its final mode for the operation. A new destination remains `0600`, intentionally keeping generated descriptions/metadata private by default. For replacement, set the output temp to the existing destination's POSIX mode bits. For backup refresh, capture the original destination's mode with `stat.S_IMODE(os.fstat(source_fd).st_mode)` from the same open descriptor used to copy its bytes, and set the backup temp to exactly those bits. For recovery, capture the `.bak` mode with `stat.S_IMODE(os.fstat(backup_fd).st_mode)` from the descriptor used to read its bytes, and set the restored temp to exactly those bits. Verify staged and published mode bits alongside byte validation. A mode-setting failure aborts before replacing the destination or `.bak`; retain any prior `.bak`. Owner, ACLs, extended attributes, and other filesystem-specific metadata are not guaranteed to be preserved.
5. **Refresh the backup before replacing an existing destination.** If a destination currently exists, copy its exact bytes from an open file descriptor to a separate backup temporary file, apply the mode bits captured from that same descriptor, flush/fsync/close it, and verify both byte equality and mode before atomically replacing `<destination>.bak` with that completed copy. The refreshed `.bak` therefore has the original destination's mode bits, not the temporary file's initial `0600` mode. This refreshes any older `.bak` from the current original rather than promoting a stale backup. If backup preparation fails, do not replace the destination; retain any prior `.bak` and report `file_io`.
6. **Replace through the filesystem operation.** Publish the fully staged output with same-directory `os.replace`; never truncate/write the destination in place. A new destination has no `.bak` unless one already existed from recovery. Same-directory replacement is the selected mechanism, not a promise that every filesystem provides identical atomicity or power-loss durability.
7. **Verify the actual destination.** Read the destination back, verify its required mode bits in the uncontended case, and apply the owning stage's validator. Do not report an unverified or invalid destination as completed. With a single writer, tests require the destination bytes and mode to equal the staged payload and mode. During concurrent lock-free writes, another complete valid payload may already be present at read-back; accept the valid destination without a winner claim or rollback. No conflict detection or compare-and-swap is introduced.
8. **Apply retention only after verification.** With `remove`, remove `<destination>.bak` only after the current destination has passed the owning stage's validation; with `retain`, keep the backup. If the target was new and no backup exists, neither policy creates one. A backup-removal error is a `file_io` failure even though the destination may already be valid: preserve the destination and any remaining backup, do not roll back, and do not report the stage as fully completed.
9. **Clean up only owned temporary files.** On success or failure, the current operation makes a best-effort cleanup of temporary files it created. A cleanup error is reported without deleting the destination or backup. Pre-existing temporary files are not assumed stale and are not deleted automatically; they are never recovery sources.

Filesystem operations and errors use A2's result/exit contract. Storage failures use `file_io`; stage validation failures use the owning stage's established category. Return sanitized messages and do not expose raw provider data, credentials, or raw exception text. Preserve A2's intentional internal resolved-image-path and CLI sidecar-path reporting.

## Recovery state table

Recovery examines only the destination and its `.bak`; it never promotes a temporary file.

| Destination | `.bak` | Required action | Required preservation |
| --- | --- | --- | --- |
| Missing | Missing | No recovery; let the stage apply its missing-output policy. | Do not create a backup. |
| Missing | Present/readable | Capture `.bak` mode bits from the same open descriptor used to read it; copy its bytes through a unique same-directory temporary file, apply the captured mode before flush/fsync/close, verify exact bytes and mode, then replace the missing destination. The restored destination therefore receives the backup's mode bits. The stage validates the restored destination and mode before normal skip/regenerate decisions. | Keep `.bak` until stage validation succeeds. If restore, mode-setting, or stage validation fails, preserve the backup. Apply `backup_retention` only after successful stage validation. |
| Present | Present | Destination is authoritative. Do not restore over it, even if the destination later fails stage validation; existing A2 invalid-artifact and explicit-regeneration rules apply. | Preserve `.bak` until the destination has been validated. Then apply `backup_retention`. |
| Present | Missing | Destination is authoritative; the stage validates/skips/regenerates under A2/A3 rules. | No recovery action. |
| Any | One or more pre-existing temporary files | Ignore them for recovery and do not infer staleness from age or naming alone. | Do not delete them automatically. A later maintenance process may remove them only with independent proof that no writer owns them. |

If destination replacement fails after a backup has been refreshed and the destination is now missing, the operation may use the same verified restore procedure before returning its original `file_io` failure. If the destination still exists, it remains authoritative; do not overwrite it with a backup as rollback. A backup is never discarded on a failed write merely because the configured retention is `remove`.

## Failure and interruption outcomes

| Failure point | Destination / backup outcome | Result |
| --- | --- | --- |
| Generation, decoding, or stage validation before safe-write | No filesystem changes by safe-write. | Owning stage reports its established failure category. |
| Temporary creation, write, flush/fsync, read-back, mode-setting, or validation before backup refresh | Existing destination and `.bak` unchanged; clean only the operation's temporary file. | Failed; never completed. |
| Backup copy/mode-setting/flush/fsync/verification fails | Existing destination unchanged; a prior `.bak` remains. No destination replacement starts. | `file_io`; never completed. |
| Backup refresh succeeds, destination replacement fails | Keep the refreshed backup. Keep an extant destination authoritative; if it is absent, attempt verified restoration. | `file_io`; never completed. |
| Destination replacement succeeds but read-back/validation fails | Leave the destination and keep any backup. Never roll back over an extant destination. | `file_io` or the owning validation category; never completed. |
| Backup or owned-temporary cleanup fails | Leave the verified destination and any remaining backup/temp in place; do not roll back. | `file_io`; operation is not fully completed. The remaining temp is ignored by future recovery. |
| `SIGINT`/`SIGTERM` before safe-write starts | Do not start a write. | Follow A2 signal status (`130`/`143`). |
| `SIGINT`/`SIGTERM` after safe-write starts | Defer cancellation until the transaction reaches a terminal safe boundary (verified completion or a reported failure); then exit using A2's signal status. A safely completed write remains completed. | Follow A2 signal status; no later selected stage starts. |
| Uncatchable process death (for example, `SIGKILL`) | No cleanup guarantee. On the next invocation, apply the recovery state table; an orphan temp is ignored. | No claim of graceful completion or crash-proof durability. |

A failed operation may leave a valid destination if failure occurred after replacement (for example, retention cleanup failed). The result remains failed because the requested transaction did not finish; the valid destination is not deleted or rolled back. On a subsequent run, normal stage validity and explicit-regeneration rules apply.

## Concurrency and filesystem limits

- No application lock, queue, compare-and-swap, or conflict-detection mechanism is added. Concurrent operations use unique temporary names and same-directory replacements; the last successful replacement that remains on disk wins. Concurrent edits can be lost.
- Separate-process tests assert only that the final destination is one complete valid payload from the competing writes, never truncated/interleaved. They do not assert a particular winner or that every process observes its own payload after a race.
- Backup refresh and backup cleanup can race with another process. These races are accepted by the HLD's lock-free, last-successful-replacement-wins decision; the implementation must not claim stronger protection.
- B5/C2 must run fault cases under temporary test directories on the actual Linux test filesystem and record its type (for example, with `stat -f -c %T <test-dir>`). If a distinct writable filesystem such as `/dev/shm` is available, run a scoped smoke test and record it; otherwise document the skip. Do not mount filesystems, alter system/user data, or require an exhaustive filesystem matrix.
- The design flushes/fsyncs file contents before replacement and verifies the published artifact. Filesystem-specific rename, directory-entry, power-loss, and network-filesystem guarantees remain outside the contract; do not claim crash-proof writes or add speculative OS/filesystem branches.

## Deterministic B5/C2 fault-test matrix

These are planned implementation tests, not tests executed by this design closeout. Use `tmp_path`, controlled fault injection around the filesystem-operation seam, synthetic payloads, and disposable child processes only. Every failure test asserts the exact destination, `.bak`, owned-temp, and result-category state; assert that the source-image fixture remains byte-for-byte unchanged.

| ID | Scenario | Required assertions |
| --- | --- | --- |
| SW-01 | Create a new `.desc.txt` or `.desc.json` | Complete validated bytes at destination; mode `0600`; no backup created. |
| SW-02 | Replace an existing artifact | Before publication, `.bak` is a byte-exact copy of the previous destination and has the same POSIX mode bits; replacement is complete and stage-valid with the previous destination's mode bits. |
| SW-03 | Refresh an older backup | The refreshed `.bak` matches the current destination, not the older `.bak`; after verification, `remove` deletes it and `retain` keeps it. |
| SW-04 | Recover missing destination with backup | Restore exact backup bytes and POSIX mode bits through a unique temporary file; verify both on the restored destination before applying retention; preserve backup if mode-setting, restoration, or validation fails. |
| SW-05 | Destination and backup both exist | Never restore over destination. A valid destination follows skip/regeneration policy; an invalid one fails under A2/A3 rules and leaves the backup available. |
| SW-06 | Orphan/pre-existing temp file | It is not a recovery source and is not deleted; the current operation removes only the temp it created. |
| SW-07 | Fail temporary create/write/fsync/read-back/validation/mode-setting | Destination and prior backup remain byte-identical; result is not completed; only owned temp cleanup is attempted. |
| SW-08 | Fail backup copy/mode-setting/fsync/verification/replace | Destination remains unchanged; prior backup remains if refresh did not commit; no target replacement occurs. |
| SW-09 | Fail destination replace | Keep backup; preserve an extant destination, or attempt verified restore only if destination is missing; report `file_io`. |
| SW-10 | Fail destination read-back or stage validation after replacement | Keep destination and backup; no rollback over destination; do not report completed. |
| SW-11 | Fail backup removal or owned-temp cleanup | Leave destination and remaining recoverable files; report `file_io`; future recovery ignores the temp. |
| SW-12 | Graceful signal and forced process death at transaction checkpoints | `SIGINT`/`SIGTERM` wait for a safe terminal boundary and return A2 statuses; restart after forced death follows the recovery table without using temp files. |
| SW-13 | Overlapping separate-process writers | With a barrier, final target is exactly one complete valid payload; no particular writer is selected and no locking/conflict-detection guarantee is asserted. |
| SW-14 | Source-image integrity and path boundaries | Source fixture is unchanged; only the owned sidecar destination is passed to the artifact writer. |
| SW-15 | Mode behavior | New output is `0600`; replacement preserves the previous destination mode, backup refresh preserves that same original mode, and recovery gives the destination the backup's mode; unsupported owner/ACL/xattr preservation is not asserted. |

B5 follows RED → GREEN → REFACTOR and records the expected failing test before implementation. C2 runs the named signal, process-death, filesystem-state, and separate-process scenarios; C3 records the interpreter and actual filesystem evidence. No real provider, credential, user photo, or destructive filesystem operation is needed.

## Acceptance

- [x] Every HLD backup/recovery invariant is represented in the state table and deterministic B5/C2 test cases.
- [x] Failure paths preserve the destination or available backup; incomplete/unverified output is never reported as completed, and no rollback overwrites a destination after a failed verification.
- [x] Backup retention is configurable through `pipeline.backup_retention` (`remove` or `retain`, default `remove`) under the existing config root; failure paths preserve backups regardless of policy.
- [x] Pre-existing temporary files are never recovery sources and are not deleted unless proven stale; each operation cleans only its own temporary files.
- [x] Lock-free, last-successful-replacement-wins behavior and accepted backup/cleanup races remain explicit; tests use separate processes without asserting a winner.
- [x] Permission behavior—including mode preservation for backup refresh and recovery—representative Linux filesystem evidence, fault injection, and durability limitations are specified without promising crash-proof writes.
- [x] [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md) is complete and linked.

## Verification and environment notes

- This closeout records design and test obligations only; no application code or tests were run.
- The implementation plan and A2 config record were updated to match the new retention leaf and the safe-write contract. A3/A4 records preserve their historical closeout states and now distinguish subsequent A5 progress.
- Documentation structure, local links, acceptance-check synchronization, and whitespace are verified after the final cross-file edits; application test/build evidence remains for B5/C2/C3.

## References

- [REQ-image-clarus.md](../REQ-image-clarus.md) — safe-write and recovery requirements.
- [HLD-image-clarus.md](../HLD-image-clarus.md) §§7.1, 7.2, 10.3 — safe-write architecture, backup recovery, and lock-free concurrency.
- [IMPL-PLAN-slice-1.md](IMPL-PLAN-slice-1.md) — A5 decisions and B2/B5/C2 implementation/test ownership.
- [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md) — configuration, stage result, existing-output, and signal contracts.
- [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md) — JSON artifact validity and explicit-regeneration rules.
- [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md) — provider and diagnostic boundaries; A5 does not alter provider behavior.
