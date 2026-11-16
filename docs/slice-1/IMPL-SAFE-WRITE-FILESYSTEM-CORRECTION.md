# Slice 1 — Safe-write filesystem compatibility correction

**Status:** Implementation and automated verification complete; Product Owner disposition of the test-order evidence gap is pending. The reported mount's compatibility and the cause of the original failure remain unverified. C4 and C5 remain open.

**Scope:** The Product Owner approved capability-dependent permission handling without filesystem-name exceptions, while retaining artifact integrity, replacement, recovery, cleanup and the documented lock-free concurrency boundary. This corrects the unconditional POSIX-mode requirement previously introduced in A5; it does not revise the history of the original design or its verification.

**Files created:** `tests/unit/test_artifacts_compat.py`, `tests/unit/test_partial_modes.py`, `tests/unit/test_recovery_invalid_backup.py`, and this record.

**Files updated:** `src/image_clarus/artifacts.py`, `src/image_clarus/stages/description.py`, `src/image_clarus/stages/structure.py`, `README.md`, `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, `docs/slice-1/IMPL-A5-COMPLETED.md`, `docs/slice-1/IMPL-B5-COMPLETED.md`, `docs/slice-1/IMPL-C2-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.

**Files removed:** None. No version increment or provider request was made.

## Behavior

- Probe permission behavior using a unique empty sibling before writing output or backup bytes. When POSIX modes cannot be represented, issue a privacy warning and continue without a filesystem-name allowlist. Where modes are supported, continue verifying the requested staged mode. Actual access-denied and I/O errors remain failures. Neither POSIX mode read-back nor the probe establishes privacy against ACLs or other access mechanisms.
- Content bytes are still validated before replacement; fsync, backups, read-back, recovery, cleanup and the accepted lock-free race limitations remain. Recovery now validates a backup before publishing it; an invalid backup remains available and does not become the destination.
- Sanitized failure details can include the operation checkpoint and numeric errno, without raw paths, payload or OS exception text. Both stage consumers surface the diagnostic.

## Evidence and limitations

- Full automated tests: **514 passed** on Linux CPython 3.12.14 and **514 passed** on Linux CPython 3.13.15. Ruff lint and format, lockfile check and build passed.
- **75 focused tests passed** with temporary paths on a `fuseblk` repository mount. A separate disposable mode check on that mount showed that it accepted `0600` and `0644`; this is not evidence that a mode-ignoring mount works. Ignored, unsupported and partially represented modes and permission-denied/I/O conditions were simulated in automated tests.
- An isolated normal `uv tool` installation reported application version `0.1.2` and successfully wrote synthetic bytes under a simulated ignored-mode condition while emitting a privacy warning. Since this correction does not increment the version, an explicit reinstall and behavior check are required to distinguish it from an earlier installation.
- Tests for the originally reported user mount were not run; the mount was not accessible in the development environment. The actual reported failure and native Windows execution remain unverified. No private photos, credentials, real model calls or mount changes were used.
- RED→GREEN was observed for initial ignored/unsupported-mode handling, diagnostics, cleanup, partial-mode handling, invalid-backup publication and sanitized malformed mode-operation errors. **Test-order evidence gap:** the initial test for a mode-capable probe followed by an ignored actual mode was corrected only after the implementation, so its corrected version lacks an observed pre-fix RED. It passes as supplemental regression coverage; no historical RED is claimed. This requires the Product Owner's explicit disposition under the project's TDD policy.
- The historical lock-free design can accept another writer's valid destination at read-back and cannot guarantee a deterministic winner. Backup/cleanup races and filesystem-specific crash durability remain documented limitations.
