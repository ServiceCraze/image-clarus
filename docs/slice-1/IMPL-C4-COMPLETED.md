# Step C4 — Perform an authorized real-provider quality smoke test (COMPLETED)

**Status:** Complete. This is operator-reported manual evidence, not an automated test or a claim that Hermes independently observed the provider runs.

**Scope deviation approved by the Product Owner:** The original plan required exclusively synthetic, non-identifying images. The Product Owner explicitly superseded that input criterion with operator-authorized test images and accepted the completed tests using real, user-selected images. No additional inference run was requested. Source-derived sensitive information may appear in generated metadata; the operator controls input selection, data transfer, costs and handling of outputs.

**Files created:** `docs/slice-1/IMPL-C4-COMPLETED.md` (this record).

**Files updated:** `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`.

**Files removed:** None. The patch version was incremented from `0.1.3` to `0.1.4` for this documentation closeout; the operator's observed probe was on `0.1.3`, not `0.1.4`.

## Operator-reported manual results

- The operator authorized and exercised a real compatible provider with selected real images. The provider, endpoint, model names, image contents and credentials are intentionally omitted from this public record.
- Both description and structured JSON generation succeeded. Descriptions provided sufficient information for the structured stage. The operator reported schema validation and provenance in generated JSON; no field-by-field inventory of metadata categories was supplied.
- Independent stage execution and skipping existing outputs were successful. Artifact publication succeeded on Linux and Linux-mounted NTFS/FUSE, including the corrected permission handling. Earlier transient provider failures did not recur in the final tests.
- Separately, the operator ran a synthetic create-only artifact probe with installed version `0.1.3` on the affected NTFS/FUSE mount. It emitted the expected privacy warning, reported mode `0777`, and verified the published bytes. It did not exercise replacement or recovery on that mount; native Windows execution is not established.
- The operator reported that inspected generated artifacts contained no API credentials. A screenshot's metadata contained contact information visible in its source; those details are not reproduced here. Logs were **not independently checked for sensitive information**, so no conclusion about their contents is claimed. The observed privacy warning also means access to artifacts depends on filesystem and mount controls, including ACLs.
- The original write failure's precise cause was not independently established. Ranked tag candidates are a separate schema-design consideration, not a C4 blocker. The Product Owner subsequently accepted the separate safe-write test-order exception; see the [correction record](IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md) and the completed [C5 closeout](IMPL-C5-COMPLETED.md). This later disposition does not change what was known at C4 closeout.

## Acceptance

- [x] The approved provider completes both stages with the agreed contract, or the row remains unchecked with `NOT SAFELY AVAILABLE` and a precise blocker.
- [x] Operator-authorized test images are used; no secret is copied into the record.
- [x] Manual result is not represented as automated test evidence.
- [x] [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md) is complete and linked.
