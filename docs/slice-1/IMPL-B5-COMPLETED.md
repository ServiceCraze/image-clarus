# Step B5 — Implement the recoverable sidecar artifact service (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. The artifact service supplies filesystem mechanics; stage-owned policy and stage/CLI integration remain B6–B8.

**Files created:** `src/image_clarus/artifacts.py`, `tests/unit/test_artifacts.py`, `tests/unit/test_artifacts_tracer.py`, and this record.

**Files updated:** `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-B4-COMPLETED.md` (subsequent progress note).

**Files removed:** None.

## Summary

Implemented staged sidecar writes, same-directory replacement, current-original backup refresh, destination-authoritative recovery, byte/mode checks, caller-supplied stage validation, configurable `remove`/`retain` backup handling, sanitized error categories and best-effort cleanup of operation-owned temporary files. Failed destination replacement attempts verified recovery when the destination is missing and preserves the backup; it does not roll back an existing destination. No application-level lock or crash-proof guarantee is introduced. The service requires callers to supply a sidecar, never the source image; actual stage path construction remains B6/B7 and its integrated source-image verification remains C1/C2.

The read-back check verifies exact bytes and mode if the published inode is the staged inode; when another inode is observed, it accepts stage-valid content to honor A5's lock-free concurrent-writer rule. A synthetic faulty replacement that substitutes a different valid inode is observationally indistinguishable from another writer's replacement at that point and may therefore be accepted; the test suite does not establish fault detection for that case. The service does not claim conflict detection, serialized backups, directory-fsync durability, or a particular concurrent winner.

**Subsequent approved correction:** B5's original unconditional mode equality conflicts with the REQ's expected filesystems. The current contract requires best-effort private creation and mode preservation, with exact checks where supported, while tolerating demonstrated inability to represent or enforce POSIX modes; genuine permission and I/O failures still fail. Transaction, validation, backup, replacement, recovery and concurrency safeguards remain; backup validation now precedes recovery publication. See the [correction record](IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md) for implementation and automated evidence. The Product Owner accepted the documented test-order exception. The operator later reported successful artifact publication and a synthetic create-only probe on Linux NTFS/FUSE; neither this nor the historical B5 tests establish native Windows support or exhaustive recovery behavior on NTFS/FUSE.

## Verification and test-first evidence

- The first implementation was discarded because its observed RED evidence covered only a missing module. The replacement was implemented after focused RED tests: creation (`NotImplementedError`), backup refresh (stale backup), recovery (`NotImplementedError`), injected create fault, post-publication validation failure, and recovery read fault. A broader fault batch produced 28 failures and 9 passes before fault handling was completed; staged-byte mismatch, published-byte mismatch and validator-exception tracers produced 3 failures and 1 pass before their correction. Some cases were grouped and supplemental tests passed on first execution; they are not represented as individually observed RED.
- A further targeted test reproduced a missing-destination failure after a failed destination replacement; it failed with `FileNotFoundError` before the restore correction and passed afterward. An audit-driven cleanup test observed only one unlink attempt when two owned files existed; it failed before the best-effort cleanup correction and passed afterward.
- `uv run --locked --extra dev pytest tests/unit/test_artifacts.py tests/unit/test_artifacts_tracer.py -q` — **43 passed**, including synthetic fault injection, retained backup and mode checks, orphan-temp preservation, and two separate processes synchronized immediately before publication. Final output must be one complete submitted payload; no winner is asserted.
- `uv run --locked --extra dev pytest -q` — **162 passed**. Ruff lint and format checks, `uv lock --check`, and `uv build --python 3.13` passed.
- The test scratch filesystem was XFS. Three scoped create/replace/recovery cases also passed using a disposable directory on `/dev/shm` tmpfs, which was removed afterward. No real image or provider was used.
- Cooperative/OS signal handling and forced-process-death verification belong to C2; actual stage and CLI integration belong to B6–B8. Python 3.12 runtime verification remains C3 work.

## Acceptance

- [x] HLD §7.1 recovery rules are all covered.
- [x] Failed writes preserve recoverable originals and cannot produce a success result.
- [x] No application-level lock or false crash-proof promise is introduced.
- [x] Source image paths are never passed as write destinations.
- [x] Backup retention follows `pipeline.backup_retention`; failure paths preserve backups independently of retention policy.
- [x] Only operation-owned temporary files are cleaned automatically; concurrent tests run as separate OS processes and leave a complete artifact.
- [x] SW-02/SW-04/SW-15 verify POSIX mode preservation on backup refresh and recovery.
- [x] RED/GREEN and fault-test evidence is recorded; [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md) is linked.

## Follow-up

At B5 closeout, B6 and later steps had not started. B6 subsequently implemented the description stage and extended recovery to defer backup retention during regeneration; see [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md). Broader source-path safety and signal behavior were assigned to the later integration steps.

**Subsequent progress:** B6–B9 and C1–C5 are complete. The safe-write correction and its accepted test-order exception are in the [correction record](IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md); final acceptance is in [IMPL-C5-COMPLETED.md](IMPL-C5-COMPLETED.md).
