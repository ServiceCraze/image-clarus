# Step A3 — Freeze digiKam XMP field mapping and preservation contract (COMPLETED)

**Status:** Design complete. Actual digiKam interoperability remains a C3 acceptance obligation. No implementation or successful digiKam interoperability is claimed.

**Subsequent progress:** A4 has frozen configuration, localized-field policy and no-change outcomes; see [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md). A5 clarified that required recovery and retention cleanup precede an otherwise no-change result; see [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md).

**Scope deviations:** None. The Product Owner directed the A3/A5 plan correction: use discovery and synthetic ExifTool evidence for preliminary design and require actual digiKam interoperability in C3; product requirements are unchanged.

## Files created, updated, and removed

- **Created:** `docs/slice-2/IMPL-A3-COMPLETED.md` (this record).
- **Updated:** `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-A2-COMPLETED.md`, `docs/HLD-image-clarus.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py`.
- **Removed:** None. Version-test edits follow the patch-version convention. No Slice 2 production code or public fixture was added.

## Evidence and boundary

The earlier discovery records actual digiKam-generated samples: `digiKam:TagsList` used slash-separated paths, `lr:hierarchicalSubject` used pipe-separated paths, and `dc:subject` contained flat leaf names. Title and description used `x-default`; `digiKam:CaptionsAuthorNames` was observed after a caption edit. Coexistence is not proof that each field is required or authorized for writing, nor that a generated sidecar can be imported or edited in digiKam. No cross-root taxonomy comparison is needed or authorized.

A reviewer downloaded ExifTool **13.64** to a temporary scratch directory and ran synthetic XMP sidecar tests only, without installing it system-wide. It wrote/read the listed hierarchy fields, `dc:title`, `dc:description`, and `digiKam:CaptionsAuthorNames`; it did not establish digiKam behavior. In a synthetic title update, unsuffixed `-XMP-dc:Title=Changed` removed the existing French language alternative; `-XMP-dc:Title-x-default=Changed` retained it. Independent readback of the resulting sidecars confirmed `Title-fr` was absent in the first and present in the second. A synthetic foreign property survived one update semantically although its XML serialization changed. A malformed sidecar write failed. These individual cases are not proof of complete preservation for arbitrary XMP.

An independent synthetic Exiv2 0.27.5 experiment represented description and caption authors as language alternatives, `TagsList` as an RDF sequence, and the Lightroom hierarchy and flat subjects as RDF bags. This is Exiv2 evidence, not ExifTool or digiKam interoperability proof. Caption authors are language-associated; author behavior cannot safely be assumed to be a single global scalar.

**Interoperability gap, assigned to C3:** digiKam was not available on PATH and no graphical display was available. There was no digiKam import, refresh, explicit parent/child assignment, title/caption/author display, or generated-tag edit/save test. Neither the minimum interoperable field set nor the full A2 segment character range is verified in digiKam. A3 may freeze preliminary, evidence-supported mappings without claiming actual interoperability; escalate a necessary representation crossing the parent REQ's optional/non-digiKam boundary to the Product Owner.

## Preliminary mapping and ownership

The first implementation uses the following deliberately limited targets, based on the observed digiKam output and synthetic ExifTool reads and writes. This is a design choice, not proof of the minimum interoperable set; C3 checks actual behavior and drives corrections if necessary.

| JSON/config input | ExifTool read/write target | Contract |
| --- | --- | --- |
| Ranked selected tag paths | `XMP-digiKam:TagsList` | RDF sequence of explicitly assigned paths. Encode segments with `/`; prepend nonempty root as one segment. A child does not create a separate parent assignment. Compare complete segment sequences, case-sensitively; no prefix matching such as `ai` versus `aisle`. |
| `title` | `XMP-dc:Title-x-default` | Update only the `x-default` language alternative; preserve all other alternatives. |
| `caption` | `XMP-dc:Description-x-default` | Update only the `x-default` language alternative; preserve all other alternatives. |
| Configured caption author | `XMP-digiKam:CaptionsAuthorNames-x-default` | Update only the `x-default` author alternative under its independent policy. If no author is configured, do not change any author value. Do not infer creator identity. |

Read each affected property, including language alternatives, and the complete original XMP information model for preservation validation. `lr:hierarchicalSubject`, `dc:subject`, other vendor-specific fields and camera metadata are **not** write targets in this initial mapping, even if present. In particular, leave flat keywords unchanged: a leaf cannot prove hierarchical ownership. Do not pretend these fields were synchronized; if C3 shows another representation necessary, correct the mapping with preservation and applicable scope authorization. No cross-root taxonomy matching or semantic reconciliation is performed. Do not convert arbitrary malformed hierarchy entries into apparently valid ones: fail safely if necessary to preserve them.

The existing A2 contract validates every candidate before top-N; each path counts once. A zero limit, empty candidate list or disabled policy never clears tags. For nonempty root, `add` unions exact assignments; `new` adds only if no assignment begins with that root segment; `overwrite` removes only assignments under that root and adds selected paths. For empty root, `add`, `new`, and `overwrite` all perform an additive union and `disabled` makes no change. If generated and existing assignment are identical, retain one; preserve unrelated assignments and their order. The title, caption and author policies and absent values remain independent; A4 specifies exact config and stage result details. Select `skipped` for a fully unchanged XMP stage, subject to A4's complete result contract.

## Backend interface, staging and validation

Select `src/image_clarus/xmp_backend.py` for ExifTool mechanics and `src/image_clarus/stages/xmp.py` for stage orchestration and policies; neither exists yet. B3 implements an `ExifToolBackend` with `read(snapshot: bytes | None)`, `transform(snapshot: bytes | None, updates) -> bytes`, and `validate(candidate: bytes)` operations. `read` returns the complete representation required for semantic preservation checks and typed values for the selected fields; `updates` contains explicit final field values, not model data or policy decisions. The stage validates input, computes policy and compares before/after semantics; the backend handles tool invocation, XMP parsing/serialization and explicit per-field updates. Concrete Python types are implementation details constrained by this interface and the tests.

ExifTool writes **only** an exclusively created private working `.xmp` in the destination directory. For an absent sidecar seed it with a minimal valid empty XMP/RDF packet; never use the image as a template or write target. Copy a byte snapshot of an existing sidecar to the working file. Invoke ExifTool without a shell, passing arguments as separate values, with a fixed executable resolved via PATH only for selected XMP operations; suppress implicit user ExifTool configuration. Reject NUL and unrepresentable arguments; use an end-of-options boundary for paths and test spaces, Unicode and leading hyphens. Bound each subprocess to 30 seconds, kill and reap on timeout, bound output, and return sanitized category-level errors without raw XMP, paths, arguments, stdout or stderr. Missing executable, timeout, nonzero exit, malformed input or output and preservation violations fail the stage. Clean up only this invocation's working files, including ExifTool-generated backups.

Before touching sidecars, guard source image versus destination, backup and temporary targets against lexical/resolved path collisions and existing same-file aliases, including symlinks and hard links; reject unsafe paths rather than writing. Read/recover the sidecar using the existing artifact service. Validate that the original is parseable and structurally safe; never silently replace malformed existing metadata. Transform the snapshot; parse the whole resulting XMP and compare semantic namespace-expanded properties, structures, values, ordered lists and language alternatives with the original, allowing only the explicit, policy-authorized changes. XML byte identity, prefix choice and serialization form do not need to match. If unsupported structures cannot be reliably compared or preserved, fail closed rather than remove them.

Publish complete candidate bytes through `ArtifactService.write` using a structural XMP validator for staged bytes and readback. Candidate-specific authorized-change and preservation assertions happen before publication, not as the recovery validator: valid older backup/destination content must remain recoverable. Readback validates the observed complete artifact, but under the inherited lock-free last-replacement-wins contract a different writer may have replaced it; do not claim conflict detection, serializable merges, or universal crash durability. Existing backup/retention and filesystem permission-capability semantics apply.

## Synthetic fixture matrix and C3 handoff

| Input and policy | Required design assertion |
| --- | --- |
| `auto/plate`, `food/pepper`, `ai/food/pepper`; flat `pepper` | `overwrite` under `ai` changes only `ai` assignments; manual/auto assignments and the ambiguous flat `pepper` remain. |
| `aisle/lamp`, no `ai` assignment; nonempty root `ai`, `new` | Add `ai/food/pepper`; similar prefix and other roots do not suppress it. Existing `ai/other` instead suppresses `new`. |
| Existing `food/pepper` and `auto/plate`; empty root | Each enabled policy adds selected `food/pizza`, retains all existing tags and is idempotent; `disabled` is unchanged. An attempted removal is rejected. |
| Existing `ai/food/pizza`; selected `ai/food` | Paths are independent assignments; do not infer or remove a parent solely from a child. Duplicates are not appended. |
| `x-default` and French title/caption/author alternatives | Explicit default update changes only its language; unconfigured author and non-default languages survive. Unsuffixed write that removes a French alternative fails preservation. |
| Existing foreign property, camera data, opaque vendor list, absent title/caption, or empty source | Preserve unrelated content and do not clear missing/empty fields even under `overwrite`. Reject a candidate that changes a foreign value. |
| No sidecar; malformed XMP; unsafe image/sidecar alias; timeout or failing ExifTool | Create from an empty packet only when safe; otherwise fail without modifying the image or valid original and preserve recoverable backup. |

Use only synthetic/sanitized fixtures. B3–B5 implement and test this contract. In C3 the operator imports/rereads the generated sidecar in digiKam, checks hierarchy and ancestor filtering, title, caption and author, edits a generated descendant and the generated title/caption, saves, reads the persisted XMP and refreshes again; record exact settings and observed outcome. No immediate database refresh is presumed. A mapping failure is corrected and retested without claiming earlier tool serialization demonstrated digiKam compatibility.

## A3 acceptance

- [x] An explicit ExifTool field-read/write/validation contract and source-image protection strategy are documented, with observed and verified mappings distinguished.
- [x] Preliminary mappings are grounded in available evidence, specify preservation of all unrelated metadata and never rely on cross-root taxonomy comparisons; unverified digiKam behavior is assigned to C3.
- [x] Empty-root non-deletion and nonempty-root ownership have concrete positive/negative fixture cases, including flat-keyword ambiguity.
- [x] Preliminary mapping evidence and remaining interoperability uncertainty are recorded; no untested field-write assumption is promoted to fact.
- [x] A3 completion record and plan checkoffs are synchronized.

## Verification and limits

- ExifTool 13.64 synthetic tests wrote/read the preliminary targets; independent readback confirmed that an explicit `x-default` title update preserves the French alternative while an unsuffixed update removes it. Another synthetic round trip exercised hierarchy changes and author language alternatives. These are ExifTool results, not application or digiKam tests.
- Application patch version advanced to `0.1.17`. No actual digiKam operation, model call, Slice 2 implementation, or full application suite is claimed. C3 verifies actual interoperability; A4 finalizes configuration and field-policy details. No Git commands were run.
