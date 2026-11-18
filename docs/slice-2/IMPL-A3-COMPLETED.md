# Step A3 — Freeze digiKam XMP field mapping and preservation contract (IN PROGRESS)

**Status:** In progress; A3 is not complete. This is a partial execution record, not approval of a mapping or permission to start Phase B. Actual digiKam import/edit mapping has not been established and is a C3 acceptance obligation, not an A3 prerequisite. The Product Owner's later design review and the Phase A readiness gate are separate.

**Scope:** The Product Owner directed a targeted A3/A5 plan correction: use existing discovery and synthetic ExifTool evidence for preliminary design; require actual digiKam interoperability in C3. Product requirements are unchanged.

## Files created, updated, and removed

- **Created:** `docs/slice-2/IMPL-A3-COMPLETED.md` (this partial record).
- **Updated:** `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-A2-COMPLETED.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py`.
- **Removed:** None. Version-test edits follow the patch-version convention. No Slice 2 production code or public fixture was added.

## Evidence and boundary

The earlier discovery records actual digiKam-generated samples: `digiKam:TagsList` used slash-separated paths, `lr:hierarchicalSubject` used pipe-separated paths, and `dc:subject` contained flat leaf names. Title and description used `x-default`; `digiKam:CaptionsAuthorNames` was observed after a caption edit. Coexistence is not proof that each field is required or authorized for writing, nor that a generated sidecar can be imported or edited in digiKam. No cross-root taxonomy comparison is needed or authorized.

A reviewer downloaded ExifTool **13.64** to a temporary scratch directory and ran synthetic XMP sidecar tests only, without installing it system-wide. It wrote/read the listed hierarchy fields, `dc:title`, `dc:description`, and `digiKam:CaptionsAuthorNames`; it did not establish digiKam behavior. In a synthetic title update, unsuffixed `-XMP-dc:Title=Changed` removed the existing French language alternative; `-XMP-dc:Title-x-default=Changed` retained it. Independent readback of the resulting sidecars confirmed `Title-fr` was absent in the first and present in the second. A synthetic foreign property survived one update semantically although its XML serialization changed. A malformed sidecar write failed. These individual cases are not proof of complete preservation for arbitrary XMP.

An independent synthetic Exiv2 0.27.5 experiment represented description and caption authors as language alternatives, `TagsList` as an RDF sequence, and the Lightroom hierarchy and flat subjects as RDF bags. This is Exiv2 evidence, not ExifTool or digiKam interoperability proof. Caption authors are language-associated; author behavior cannot safely be assumed to be a single global scalar.

**Interoperability gap, assigned to C3:** digiKam was not available on PATH and no graphical display was available. There was no digiKam import, refresh, explicit parent/child assignment, title/caption/author display, or generated-tag edit/save test. Neither the minimum interoperable field set nor the full A2 segment character range is verified in digiKam. A3 may freeze preliminary, evidence-supported mappings without claiming actual interoperability; escalate a necessary representation crossing the parent REQ's optional/non-digiKam boundary to the Product Owner.

## Design work to carry forward, not yet frozen

- Use a private, uniquely created working XMP sidecar, never the source image, as the ExifTool write target. Check source, destination and backup alias risks, including symlinks and hard links. Validate the complete candidate before publishing through the existing artifact service; preserve its recovery, backup, permissions and lock-free concurrency contracts.
- A recovery validator must accept structurally valid old destination/backup data. Candidate preservation checks against the original snapshot are distinct from recovery validation and must not assume a concurrent read-back is necessarily the same writer's version. No conflict detection or crash-proof durability is promised.
- Compare semantic XMP values, including foreign namespaces and all protected language alternatives; XML byte identity is not necessary. Preserve all assignments outside a nonempty root and all existing assignments under an explicit empty root. An ambiguous flat keyword cannot be deleted merely because an in-root hierarchical assignment was removed. Do not infer explicit parent assignments from child paths. Fail safely if a required mapping cannot preserve these invariants.
- Where a selected localized field is updated, test the actual explicit-language ExifTool operation; an unsuffixed write can erase other languages. Unconfigured author must remain untouched. The exact author-language relationship remains a digiKam verification item.
- Future synthetic fixtures must cover absent and malformed sidecars; `ai` versus similarly prefixed roots; manual and `auto` tags; parent versus child; overlapping leaf names and ambiguous flat keywords; all empty-root modes; unchanged optional metadata; localized alternatives; foreign metadata; tool failure, timeout and path aliases. A4 owns final result and configuration semantics. C3 remains responsible for actual operator-observed refresh, edit, save and readback of generated metadata.

## A3 acceptance

- [ ] An explicit ExifTool field-read/write/validation contract and source-image protection strategy are documented, with observed and verified mappings distinguished.
- [ ] Preliminary mappings are grounded in available evidence, specify preservation of all unrelated metadata and never rely on cross-root taxonomy comparisons; unverified digiKam behavior is assigned to C3.
- [ ] Empty-root non-deletion and nonempty-root ownership have concrete positive/negative fixture cases, including flat-keyword ambiguity.
- [x] Preliminary mapping evidence and remaining interoperability uncertainty are recorded; no untested field-write assumption is promoted to fact.
- [ ] A3 completion record and plan checkoffs are synchronized.

The preliminary evidence row is satisfied; the A3 contract and synchronized completion checkoff are not yet complete. DigiKam access is not the blocker.
