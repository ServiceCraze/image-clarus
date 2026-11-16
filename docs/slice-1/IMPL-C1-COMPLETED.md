# Step C1 — Verify independent stage execution and persisted handoff (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. Filesystem fault injection, signal boundaries, and concurrent writers remain assigned to [C2](IMPL-PLAN-slice-1.md#step-c2--verify-failure-recovery-source-integrity-and-credential-hygiene-test); environment compatibility remains C3.

**Files created:** `tests/integration/test_single_image_pipeline.py` and this record.

**Files updated:** `docs/slice-1/IMPL-PLAN-slice-1.md` and `docs/slice-1/IMPL-B9-COMPLETED.md`.

**Files removed:** None.

## Verification and acceptance matrix

All integration tests invoke the public CLI in subprocesses with generated, non-identifying PNG bytes and a controlled local HTTP stub; no live provider, real credential or personal image was used. They validate JSON metadata against the built-in Draft 2020-12 schema and assert the expected envelope fields and identifiers.

| Scenario | Observed evidence |
| --- | --- |
| `desc` only | One description request, exact `.desc.txt` output, no JSON or unrelated output. |
| `json` only with persisted description | One JSON request, exact persisted text including CRLF and Unicode in the request, built-in schema identity and exact-byte SHA-256 in the output, no description request. |
| `json` only without description | Missing-prerequisite failure, exit 1, no provider request or output. |
| Explicit `desc,json` and default selection | Both cases complete in registry order; the JSON request contains the exact persisted description and selected schema; output validates and has A3 version and provenance. |
| Existing output and explicit regeneration | Existing valid outputs skip without new requests or modifications; explicit regeneration executes both stages and validates the new output. |
| Overlapping independent processes | Two different CLI OS processes use different configs and model IDs. The stub holds the desc regeneration of `v1` to `v2`; JSON reads and sends exact `v1` while desc remains held. After holding JSON, desc is released and completes `v2`; only then is JSON released. The JSON artifact validates, fingerprints `v1` rather than final `v2`, and both processes exit successfully. |
| Source and output integrity | Every scenario checks the source bytes/hash unchanged and the image directory contains only the exact expected image and sidecar names, excluding XMP and unrelated files. |

- `uv run --locked --extra dev pytest -q tests/integration/test_single_image_pipeline.py` — **7 passed**. The synchronized two-process case was independently rerun three additional times, each **1 passed**.
- Full suite: `uv run --locked --extra dev pytest -q` — **392 passed**. Ruff lint, formatting check, `uv lock --locked`, and `uv build` passed.
- Tests were added to verify already implemented behavior; they are supplemental acceptance evidence, not historical RED evidence. No production behavior was changed in C1.

## Acceptance

- [x] All required Slice 1 stage combinations and prerequisite behaviors pass.
- [x] `json` reads the persisted handoff and never triggers `desc` when explicitly omitted.
- [x] Generated `.desc.json` identifies the schema version according to A3, independently of the application version.
- [x] Generated `.desc.json` fingerprints the exact persisted description snapshot consumed by the JSON request.
- [x] Two separate CLI processes execute `desc` and `json` concurrently with their independently selected models; JSON consumes a complete persisted description and neither completed sidecar is corrupted.
- [x] Source image remains unchanged; outputs use the exact sidecar names.
- [x] [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md) is complete and linked.

C2 and later steps have not been started as part of C1.

**Subsequent progress:** C2 is complete; see [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md). C3 and later steps remain open.
