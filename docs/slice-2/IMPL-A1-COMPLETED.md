# Step A1 — Reconcile Slice 2 requirements and the existing HLD (COMPLETED)

**Status:** Complete — reconciliation and baseline verification performed; the Product Owner accepted the Slice 2 REQ on 2026-11-17. A1's detailed and summary checkoffs are synchronized. Approval of remaining Phase A decisions and readiness is separate.

**Scope deviations:** None. No Slice 2 implementation or later Phase A step was started.

## Files created, updated, and removed

- **Created:** `docs/slice-2/IMPL-A1-COMPLETED.md` (this record).
- **Updated:** `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, `docs/slice-2/REQ-slice-2.md`, `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/DISCOVERY-slice-2.md`, `README.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py`.
- **Removed:** None.

The A1 reconciliation was checked at package version `0.1.12`; recording REQ acceptance and closeout bumps the application to `0.1.13` under the patch-increment convention. The planning inspection at `0.1.10` and Slice 1's `0.1.7` closeout remain historical. Production source code was not changed; the two test edits update version assertions only.

## Scope, authority and disposition

- The Product Owner explicitly decided that an omitted XMP tag root defaults to `ai`; a root explicitly set to `""` means no added prefix, with `disabled` unchanged and `add`/`new`/`overwrite` all behaving as non-destructive `add`. The parent REQ and HLD now record this decision; it is not reopened as a design question.
- The Slice 2 REQ was initially proposed when A1 began. The Product Owner explicitly accepted it on 2026-11-17; requesting A1 alone had not been treated as acceptance. Approval of A2–A5 design/readiness decisions remains separate.
- HLD describes the accepted JSON-stage inference/ranking/category guidance and deterministic, model-free XMP publication boundary. Exact schema, mapping, configuration, selected-field and compatibility behavior remains for A2–A4 and the A5 gate. No working XMP implementation is claimed.
- The parent REQ's independently optional non-digiKam representations remain end-state requirements; the HLD's initial XMP release remains limited to digiKam-compatible representations. An observed field is not automatically an authorized write target. A3 must verify mappings and escalate to the Product Owner if a required write crosses the parent REQ's representation boundary. No such necessity has been established in A1.
- The proposed Slice 2 REQ's S2-02 preservation wording now explicitly distinguishes manual tags outside a non-empty generated root from assignments inside it, which follow S2-12; the empty-root policy protects all existing tags. This removes inconsistent wording without changing the selected policy.
- Directory/pattern traversal, batches, functional search and other deferred capabilities remain outside this slice; no later numbered slice or Release 1 commitment is inferred.

## Requirement comparison

The following comparison was prepared when the Slice 2 REQ was proposed, against the parent REQ and HLD. The Product Owner subsequently accepted the REQ; this comparison is not evidence that any Slice 2 feature works.

| Slice 2 requirement | Reconciliation and disposition | Owning design/verification |
| --- | --- | --- |
| S2-01 | Inherits persisted independent stages and ordering; proposed XMP is a third stage, not yet implemented. | A4, B5, C1 |
| S2-02 | Inherits source integrity and unrelated metadata protection; clarifies policy ownership within a non-empty root and all-tag protection for an empty root. | A3, B5, C2 |
| S2-03 | Proposes additive built-in JSON information, preserving the six existing descriptive fields and provenance. | A2, B2, C1 |
| S2-04 | Proposes supported, independently addressable title generation. | A2, B2, C3 |
| S2-05 | Proposes a concise supported caption separate from the comprehensive description. | A2, B2, C3 |
| S2-06 | Refines searchable metadata into ranked human-search-oriented recommendations without a fixed count. | A2, B2/B4, C3 |
| S2-07 | Proposes meaningful non-exclusive category paths without the XMP root; preserves explicit-parent distinction. | A2–A3, B2–B4, C3 |
| S2-08 | Proposes configurable category guidance, not a hard-coded personal taxonomy. | A2/A4, B1–B2, C3 |
| S2-09 | Places semantic work in JSON and deterministic mapping in XMP; HLD now records the proposed boundary. | A2–A3, B2–B5, C1 |
| S2-10 | Inherits custom schemas and create-only/explicit-regeneration rules; proposes explicit optional-field, compatibility and future evolution contracts. | A2/A4, B2/B4, C1 |
| S2-11 | Inherits the HLD's replaceable backend and initial ExifTool/digiKam boundary; field mappings remain unverified. | A3, B3–B5, C3 |
| S2-12 | Inherits non-empty-root policies and records the Product Owner's explicit empty-root override in parent REQ/HLD. | A3–A4, B1/B4, C2–C3 |
| S2-13 | Proposes ranked deterministic top-N selection; count/default and duplicate handling remain design decisions. | A2/A4, B1/B4, C1 |
| S2-14 | Inherits independent title/caption policies and defaults; proposes supported-empty input as a no-op and localized-value preservation. | A3–A4, B3–B4, C3 |
| S2-15 | Proposes optional config-only caption author with independent policies; mapping and interoperability remain open. | A3–A4, B1/B3–B4, C3 |
| S2-16 | Inherits shared recoverable writes, existing permission limitations and lock-free behavior; XMP-specific validation remains open. | A3–A4, B3–B5, C2 |
| S2-17 | Inherits CLI/YAML/default precedence and selected-stage isolation; proposes stage-specific settings. | A4, B1, C1/C4 |
| S2-18 | Requires actual automated and operator-observed interoperability/quality evidence, with privacy and blockers recorded honestly. | A2–A5, C1–C5 |

## Baseline checks and limitations

- Read the parent and Slice 2 REQs, HLD, Slice 2 plan/discovery, Slice 1 A3/A5/C5 and safe-write correction, and inspected the relevant current source/config/resource touchpoints. The registry in `src/image_clarus/pipeline.py` is currently `desc,json`; `ArtifactService.write` and `ArtifactService.recover` exist in `src/image_clarus/artifacts.py`.
- A path check confirmed all 16 selected CLI/config/pipeline/artifact/provider/stage/resource/example/test/lock touchpoints exist. `schemas/image-structure.schema.json` reports built-in ID `urn:image-clarus:metadata-schema:1.0.0`; the fixed envelope contract is documented in Slice 1 A3.
- `uv --version`: `uv 0.12.6`; `uv run --locked --python 3.13 python --version`: Python `3.13.15`; the corresponding Python 3.12 check: `3.12.14`. The Python selection checks recreated the local `.venv`; it was restored to Python 3.13 by subsequent commands.
- Before the documentation/version changes, `uv lock --locked`, `uv run --locked image-clarus --version`, and top-level, `process`, and `search` help succeeded; the CLI reported `0.1.11`. Existing installation commands were inspected in `README.md`; a new isolated install was not performed in A1.
- After the patch bump: `uv lock --locked` passed; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py::test_version_uses_installed_metadata tests/unit/test_resources.py` returned **3 passed**; `uv run --locked --python 3.13 image-clarus --version` reported `image-clarus 0.1.12`; Ruff check and format check for the two version-test files passed.
- After recording Product Owner acceptance and bumping to `0.1.13`, `uv lock --locked` passed, the same targeted pytest selection returned **3 passed**, and `uv run --locked image-clarus --version` reported `image-clarus 0.1.13`. Documentation links and whitespace checks passed, and all four A1 acceptance rows matched between this record and the plan.
- These are baseline and version checks, not Slice 2 behavior tests. No live provider request, ExifTool/digiKam interoperability test, or full application suite was run in A1. No Git commands were run and repository commit state was not inspected.

## A1 acceptance

- [x] Slice 2 REQ status/acceptance is explicitly recorded; no unresolved REQ contradiction is silently bypassed.
- [x] Parent REQ and HLD reflect the actual JSON/XMP separation and already-decided empty-root product behavior without weakening preservation or reopening that decision.
- [x] Current paths, executable toolchain and inherited contracts are verified; necessary changes are distinguished from deferred capabilities.
- [x] A1 completion record lists files created, updated and removed, decisions, evidence and deviations; its link and plan checkoffs are synchronized.

At A1 closeout, A2–A5 and all implementation and verification phases remained unstarted. **Subsequent progress:** A2–A5 are complete as design/readiness work; implementation and verification phases remain unstarted. See [A5](IMPL-A5-COMPLETED.md).
