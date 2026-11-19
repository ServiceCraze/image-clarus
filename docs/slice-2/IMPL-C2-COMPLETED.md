# Step C2 — Verify metadata preservation, write recovery, and failure boundaries (COMPLETED)

**Status at C2 closeout:** Complete for C2's synthetic XMP preservation, safe-write/recovery, and lock-free process-overlap acceptance. C3–C5 remained open at that time. ExifTool evidence is not digiKam interoperability evidence.

**Subsequent progress:** C3 is complete based on Product Owner-reported digiKam testing; see [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md). C4–C5 remain open.

**Scope deviations:** None. This is a TEST step; no production source changed. New tests add supplemental GREEN acceptance coverage to the existing B3–B5 behavior. The first focused run had four failures in the newly written test helper, which incorrectly compared the intentionally changed `TagsList` as an unchanged field; that assertion was corrected and the focused rerun passed. No product RED or historical test-first result is claimed.

## Files created, updated, and removed

- **Created:** `tests/integration/test_c2_xmp_safety.py` and this completion record.
- **Updated:** `tests/unit/test_artifacts.py` (valid destination versus distinct valid backup authority), `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-C1-COMPLETED.md` and `docs/slice-2/IMPL-B6-COMPLETED.md` (subsequent progress), `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py` and `tests/unit/test_resources.py`. Application patch version advanced from `0.1.30` to `0.1.32`.
- **Removed:** None. No production files changed and no Git command was run.

## Preservation, failure, and recovery matrix

All image content and metadata values in these tests are synthetic and fictional. XMP writes and independent field reads used local ExifTool **13.64**; no provider, real image, or digiKam was used.

| C2 contract | Executed evidence |
| --- | --- |
| Nonempty-root ownership and ambiguous shared fields | `test_nonempty_overwrite_preserves_ambiguous_tags_and_unrelated_xmp` performs an actual ExifTool-backed `overwrite` from root `ai`. It confirms paths under `ai` are replaced while `manual/`, `auto/`, and the prefix-near-match `aisle/` assignments remain. Full semantic properties are compared before/after: `dc:subject` flat keywords, Lightroom hierarchy, camera/exposure properties, and a foreign property are unchanged. Title/caption `x-default` values change; French alternatives remain. Unconfigured author data and both author language values remain unchanged. ExifTool independently reads back the published fields. |
| Explicit empty root and tag policies | `test_explicit_empty_root_never_deletes_existing_tag_assignments` runs real ExifTool publication for each of `add`, `new`, `overwrite`, and `disabled` with `tag_root=""`. The first three add missing top-level paths without deleting or duplicating any existing assignment; `disabled` makes no change. Other semantic properties and the source-image SHA-256 remain unchanged. |
| Configured fields and locales | The nonempty-root test verifies independent title/caption overwrite and no-author preservation. `test_configured_author_overwrite_changes_only_x_default` changes only the configured author's `x-default`, preserving its French alternative and all other properties. `test_new_policy_respects_nondefault_only_language_alternative` confirms a French-only title is not overwritten under `new`. Existing `test_independent_field_policies_on_existing_sidecar` exercises three independent real-ExifTool title/caption/author policy combinations; `tests/unit/test_xmp_stage.py::test_field_policies_use_all_language_alternatives` covers `new`, `overwrite`, and `disabled` for all three fields across populated, empty, localized-only and whitespace alternatives. |
| Recovery, authority and invalid artifacts | `test_absent_xmp_recovers_valid_backup_before_no_change` restores a valid `.xmp.bak`, verifies it with ExifTool, and checks retention removal and unchanged source hash. `test_valid_destination_remains_authoritative_over_valid_backup` verifies distinct valid destination/backup authority in the XMP CLI path; the shared-service unit regression retains both exact payloads. Existing stage/backend tests verify invalid/malformed XMP, invalid JSON, structurally valid but untransformable foreign backup, invalid backup retention, and backup-only recovery. |
| Failure boundaries and filesystem capability | Existing `tests/unit/test_artifacts.py` fault-injects temporary-output, validation, backup-refresh, publication, read-back and cleanup checkpoints, checking error categories and recoverable bytes. `tests/unit/test_artifacts_compat.py` covers supported, ignored, partial and unsupported mode semantics, privacy warnings, and genuine permission/I/O errors. `tests/unit/test_xmp_backend.py` covers missing executable, actual bounded timeout/process reaping, nonzero and oversized output, malformed tool output, and preservation rejection. `tests/unit/test_xmp_integration.py` checks stage result categories, malformed inputs, actual timeout/reaping and a real-ExifTool publication failure. These are synthetic faults, not physical disk-failure claims. |
| Separate-process XMP overlap | `test_xmp_writers_overlap_in_separate_processes_without_corrupting_sidecar` starts two OS processes with different roots. A test-only file barrier holds both at `destination_replace`, after both have read/merged from the initial sidecar and staged candidates. The final XMP and backup are parsed and independently read; the final tags match either complete candidate, with no winner asserted. The scenario passed **10 consecutive repetitions**. It demonstrates overlap and valid output, not serialization: one update may be lost. |

## Verification

- Focused C2 command, run with pytest temporary files on XFS and ExifTool 13.64 prepended to `PATH`:
  `uv run --locked --extra dev --python 3.13 pytest -q tests/integration/test_c2_xmp_safety.py tests/unit/test_artifacts.py tests/unit/test_artifacts_compat.py tests/unit/test_xmp_backend.py tests/unit/test_xmp_integration.py` — **115 passed**.
- `tests/integration` on Python 3.13.15 with the same ExifTool and scratch-filesystem setup: **100 passed**, no skips on the final standalone rerun. An earlier run while two full suites were also running hit one 10-second test-harness timeout in the inherited held-provider SIGTERM test; the process was cleaned up, the cause is unknown, and the standalone rerun passed. No timing guarantee or root-cause fix is claimed.
- Full suite with ExifTool 13.64 on `PATH` and pytest temporary files on XFS: **853 passed** on Python **3.13.15** and **853 passed** on Python **3.12.14**. One combined invocation of integration and both interpreter suites exceeded the terminal's 420-second foreground limit before returning test output; it is not counted as a suite result. The three suites were then run separately and passed as recorded above.
- The two-process overlap test was run ten times; each repetition passed. `uv lock --locked`, Ruff check and format check across `src/image_clarus` and `tests` passed. CLI reported `image-clarus 0.1.32`.
- `df -T` confirmed the test temporary directory is on **XFS** and the checkout is on **virtiofs**. The C2 temporary-file scenarios ran on XFS. No separate NTFS/ACL mount was exercised; mode limitations were covered through the existing capability and fault simulations. ExifTool 13.64 was available locally; no system install was performed. Absolute environment-specific paths and private mount labels are omitted.
- The lock-free design still permits lost updates and backup/cleanup races. This is not evidence of conflict detection, crash/power-loss durability, universal filesystem behavior, or digiKam compatibility. At C2 closeout, real digiKam import/edit/read-back remained C3; see subsequent progress above.

## Acceptance

- [x] Tag preservation invariant passes for nonempty and empty roots, including ambiguous shared fields.
- [x] Existing unrelated XMP metadata and language alternatives are preserved to the frozen A3 contract; all configured field policies pass.
- [x] Invalid/failing writes do not report success and retain recoverable artifacts, with existing filesystem mode limitations respected.
- [x] Separate OS processes overlap XMP read–merge–write; resulting artifacts are complete and valid, with no deterministic winner asserted and lost-update risk documented.
- [x] Actual tested environments and lock-free limitations are documented; record and plan checkoffs align.
