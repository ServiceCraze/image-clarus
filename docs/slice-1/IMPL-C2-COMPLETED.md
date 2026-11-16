# Step C2 — Verify failure recovery, source integrity, and credential hygiene (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. Package/environment gates remain [C3](IMPL-PLAN-slice-1.md#step-c3--run-linux-package-and-quality-gates-test).

**Files created:** `tests/integration/test_c2_write_safety.py`, `tests/integration/test_c2_signal_safety.py`, and this record.

**Files updated:** `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-C1-COMPLETED.md`.

**Files removed:** None.

**Subsequent approved correction:** The original unconditional POSIX-mode checks conflict with expected filesystem coverage. The corrected contract tolerates demonstrably unsupported mode semantics, preserves exact modes where supported, and still fails genuine permission and I/O errors; other safety invariants remain. The [correction record](IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md) reports later tests and the pending test-order disposition. C2's XFS/tmpfs evidence and checked acceptance below are historical; its suite did not run on the `fuseblk` repository. Native Windows is not proven.

## Safety evidence

All payloads, image bytes and credentials were synthetic. Provider traffic used controlled loopback HTTP stubs; no live provider or personal image was used. Existing artifact and provider tests were rerun alongside new integration tests.

| Scenario | Executed evidence |
| --- | --- |
| Injected failures | Existing checkpoint tests cover output staging/write/mode/fsync/read/validation, backup refresh, target replacement/read-back/validation, retention and cleanup; recovery tests cover restore failures and backup preservation. New tests inject actual `os.replace`, `os.fchmod` and backup unlink failures and check exact contents, modes, temp cleanup and sanitized `file_io` results. A syscall fault is injected at its boundary, not an actual disk failure. |
| Recovery | Missing destination with backup restores the backup; destination plus backup leaves destination authoritative. Existing orphan temps are neither promoted nor deleted. Invalid destination/validation failures preserve available backups and never report a completed transaction. |
| Separate writers | Two spawned OS processes synchronize immediately before publishing distinct 200,000-byte payloads to the same sidecar. The result is exactly one complete payload; neither winner nor conflict detection is asserted. Backup and source bytes are checked. |
| Forced process death | Disposable writers receive SIGKILL at staged-output read, backup verification, pre-target replacement and post-replacement read-back. A separate recovery process checks authoritative destination, backup, orphan temp bytes and modes. A killed recovery is restarted with a deliberately altered orphan and restores from the backup instead. SIGKILL is not graceful shutdown. |
| Graceful signal before response | Real CLI processes receive SIGINT and SIGTERM while a local provider holds its response. Each exits 130 or 143 **before** provider release; desc and json are reported interrupted, no second request or output occurs, and source bytes are unchanged. |
| Graceful signal during write | Real CLI/stage execution uses a process-local injected checkpoint barrier at output write, backup replacement and destination replacement. Both signals wait for the started write to reach its safe boundary; the complete description and old backup remain, JSON is skipped/interrupted, and source bytes are unchanged. |
| Credentials | Provider logging/error tests use dummy credentials and check logs, exceptions and traceback text for disclosure. CLI synthetic-provider failure and output redaction tests cover streams. |

## Filesystem and verification

- The Linux test scratch directory was **XFS** (`stat -f -c %T "$TMPDIR"`); the repository itself was `fuseblk`. The complete fault and signal suite uses scratch paths, not the repository filesystem. A separate writable **tmpfs** (`/dev/shm`) ran all 10 new write-safety tests successfully; a separate create/replace/retain/recover smoke also passed and its temporary directory was removed.
- `uv run --locked --extra dev pytest -q tests/integration/test_c2_write_safety.py tests/integration/test_c2_signal_safety.py tests/unit/test_artifacts.py tests/unit/test_artifacts_tracer.py tests/unit/test_openai_compatible.py` — **112 passed**. Full suite — **410 passed**. Ruff lint and format checks, `uv lock --locked`, and `uv build` passed.
- New tests verify existing behavior and are supplemental evidence, not historical RED evidence. No production code changed in C2.
- No application locks, serialized writes or deterministic winner are claimed. Concurrent backup/cleanup races and lost updates remain possible. This evidence does not establish atomic rename or durability on all filesystems, directory-entry persistence, power-loss safety or network-filesystem behavior; it is not a crash-proof guarantee.

## Acceptance

- [x] Recoverable originals are preserved across injected failures.
- [x] No incomplete/invalid artifact is reported as complete.
- [x] Separate-process overlapping writes leave a complete valid sidecar; the test does not claim conflict detection or a deterministic winner.
- [x] SIGINT/SIGTERM return `130`/`143`, stop before the next stage, cancel requests when safe, and finish any write already in progress before exit.
- [x] Secret redaction and lock-free limitations are verified.
- [x] Evidence states actual tested filesystem and does not overclaim.
- [x] [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md) is complete and linked.

C3 and later steps have not been started as part of C2.

**Subsequent progress:** C3 is complete; see [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md). C4 and later steps remain open.
