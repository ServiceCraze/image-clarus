# Slice 2 Implementation Plan

> **For implementers and reviewers:** Phase A readiness is complete and Phase B is in progress. Complete steps in order unless an approved plan revision changes dependencies. Every CODE/TEST step requires observed RED → GREEN → REFACTOR evidence. Create the linked `IMPL-<StepId>-COMPLETED.md` only when that step is actually executed, and synchronize its evidence and checkboxes with this plan. Review the completion record first; a record alone is not proof that acceptance passed.

**Status:** In progress — Phase A (A1–A5) and B1–B3 are complete. The Product Owner accepted B2's documented historical RED-evidence gap; B4–B6 and Phase C remain open. XMP stage integration and digiKam interoperability are not claimed.

**Goal:** Extend the single-image `json` output with useful title, caption, and ranked hierarchical tag recommendations, then implement a deterministic `xmp` stage that publishes configured metadata to digiKam-compatible XMP sidecars while preserving source images and unrelated XMP metadata.

**Governing requirements:** [Overall REQ](../REQ-image-clarus.md), [Slice 2 REQ](REQ-slice-2.md) (accepted), [HLD](../HLD-image-clarus.md). [Slice 2 discovery](DISCOVERY-slice-2.md) is supporting evidence, not a competing specification. [Slice 1 implementation plan](../slice-1/IMPL-PLAN-slice-1.md) and its completion records establish the working implementation and execution conventions.

**Repository baseline inspected:** The current repository already contains the Python 3.12+ package, two registered stages (`desc`, `json`), a single-image `process` CLI, an OpenAI-compatible provider, configuration resolution, structured JSON generation, and a shared artifact service. At planning inspection, `pyproject.toml` reported version `0.1.10`; this is a snapshot, **not** a prescribed Slice 2 version or a claim that tests were run for this plan. The existing payload schema is `1.0.0` with envelope `format_version: 1`. Phase A must recheck paths and behavior against the then-current checkout before editing.

**Planning rule:** Carry forward the project-specific checklist discipline from Slice 1—ordered phases, searchable exact-match step headings, decisions and readiness, test-first implementation, recorded evidence, and Product Owner scope control. Do not import unrelated Service Craze frontend/backend, tenant, COMMS, UI, or JavaScript gates. Do not impose a step-count target.

---

## Purpose, scope, and authority

The delivery unit is **Slice 2**; Phases A, B, C and their step IDs are internal to this slice. The process is **REQ → HLD → Slice implementation plan → implementation**. The parent REQ's end-state requirements remain authoritative unless a Product Owner-approved Slice 2 refinement explicitly changes them. A design decision may specify how to satisfy a requirement, but must not silently change product behavior or scope.

### Included

- Single-image `json` enhancement: preserve its current descriptive metadata, application-owned envelope and provenance while adding publication-oriented title, caption, ranked search-useful tags, and meaningful category paths.
- Configurable preferred-category guidance for JSON inference, independent of the XMP publication root; full replacement of the JSON payload schema and prompt remains supported.
- Independent single-image `xmp` stage: persisted JSON input, deterministic ranked top-N selection, ExifTool backend, digiKam-compatible sidecar output, tag/title/caption/optional-author policies, and verified preservation.
- Extend existing configuration, CLI stage selection, stage results, and shared recoverable artifact writing only as needed for that functionality.
- Synthetic/sanitized automated testing, ExifTool round trips, operator-observed digiKam read/edit verification, metadata-quality review, package and documentation checks.

### Excluded and carried forward

| End-state capability | Slice 2 disposition | Carry-forward ownership |
| --- | --- | --- |
| Directory/glob/pattern input, recursion, multi-image traversal and batch controls/summaries | Excluded; single source-image path only | Later selection/operations plan; no numbered slice or release promised |
| Functional `search` matching, structured filters, machine-readable search results | Excluded; retain existing help-visible search stub | Later search plan |
| Embeddings/semantic search | Excluded | Future goal; not required in Release 1 |
| Non-digiKam vendor tag/keyword synchronization, other XMP backends | Excluded except a representation empirically required for digiKam interoperability | Later optional mapping/backend extension; retain parent REQ capability |
| Existing manual-tag taxonomy reconciliation across roots, historic deleted-tag reconciliation beyond the selected generated-root policy | Excluded | No inferred future commitment |
| Internal scheduler, database, queue, additional provider protocols, generalized batch logging/retries | Excluded | Existing end-state/future boundaries unchanged |
| General filesystem portability certification, crash-proof writes, native Windows matrix | Excluded | Preserve Slice 1 documented limits |
| Destructive top-level tag update force option | Excluded; **not** a Slice 2 requirement | Possible future Product Owner decision only |

### Locked product behavior and inherited constraints

1. Stages operate on adjacent persisted sidecars: `<image>.desc.txt`, `<image>.desc.json`, `<image>.xmp`. No image-byte changes. Selected stages run in `desc`, `json`, `xmp` registry order; absent selection means all registered stages. Explicit single-stage selection never auto-runs missing prerequisites or invokes a model on behalf of XMP.
2. Existing valid `.desc.json` is skipped by default after the Slice 1 structural envelope check, even if its metadata schema differs. Explicit JSON regeneration replaces the entire JSON sidecar; no field-by-field JSON merge, automatic migration, or provenance-based freshness regeneration is required. Invalid existing artifacts follow the established failure rules.
3. The JSON payload keeps `subjects`, `objects`, `actions`, `setting`, `visual_characteristics`, and `keywords`; its new ranked candidates contain **no XMP ownership prefix**. Preferred categories guide JSON inference; the XMP stage applies a publication root only when writing XMP.
4. Omitted XMP tag-root configuration uses `ai`. An explicitly configured `""` means no prefix. **With `""`: `disabled` performs no tag writes; `add`, `new`, and `overwrite` all behave as `add`, without deleting any existing tags.** With a non-empty root, the configured policy applies within that root only, including to manually assigned tags under that root. Default tag policy is `add`. No cross-root deduplication or reconciliation.
5. XMP title and caption independently support `new` (**default**), `overwrite`, and `disabled`. A missing or supported empty source title/caption/tag list never clears XMP, including when `overwrite` is configured. Caption author comes **only from optional configuration**, never model inference. When unconfigured, do not modify author metadata; when provided, the author independently supports `new` (default), `overwrite`, and `disabled`.
6. A missing required `.desc.json` file uses the inherited configurable missing-prerequisite policy (single-file default `fail`). Optional fields absent from otherwise compatible JSON are not missing-file failures. Invalid/incompatible structured inputs must not be reported as successful publication. XMP cannot silently regenerate JSON.
7. XMP writes must preserve all unrelated XML properties and tag assignments outside a nonempty generated root; an empty root preserves **all** existing tag assignments. A flat keyword representation that loses hierarchy must not lead to destructive changes. ExifTool is required **only** when XMP is selected. A3 selects evidence-supported digiKam mapping candidates; actual digiKam interoperability must be verified in C3 before Slice 2 acceptance.
8. Retain the Slice 1 artifact transaction, current-original backup refresh, validation before publication and backup recovery, filesystem-capability-dependent permission handling, no application locks, and last-successful-replacement-wins limitations. `pipeline.backup_retention` remains the existing policy. Concurrency can lose edits; do not claim conflict detection or crash durability.
9. Runtime, selected-stage configuration validation, credentials/redaction, CLI > selected YAML > built-ins, source-prompt overrides, application SemVer, independent metadata-schema SemVer, custom-schema replacement, fixed envelope provenance, and Linux test platform are inherited unless explicitly refined in the approved design.

**Canonical reconciliation progress:** A1 aligned the parent REQ and HLD §6.3 with the explicitly approved empty-root decision and documented the JSON/XMP separation without weakening preservation. The Product Owner accepted the Slice 2 REQ on 2026-11-17. The HLD's initial digiKam-only scope and parent REQ's later optional non-digiKam mappings are a **delivery allocation**, not permission to implement other mappings now. A field's presence in digiKam output alone does not authorize writing it; escalate any mapping that would cross the parent REQ's default/optional representation boundary for Product Owner reconciliation.

## Verified repository layout and implementation touchpoints

These paths were inspected as existing in the repository at planning time. They are implementation **candidates**, not authorization to replace a file wholesale. Confirm current content and reuse existing patterns at each step.

| Concern | Existing location | Slice 2 anticipated work |
| --- | --- | --- |
| CLI, stage selection, help, exit codes | `src/image_clarus/cli.py` | Register and route XMP; preserve existing CLI semantics |
| Registry/coordinator and stage results | `src/image_clarus/pipeline.py`, `src/image_clarus/results.py` | Add `xmp` in fixed order; no XMP policy in coordinator |
| Configuration, defaults, selected-stage preflight | `src/image_clarus/config.py` | Add JSON category guidance and XMP policy keys; keep config precedence |
| Existing JSON stage | `src/image_clarus/stages/structure.py` | Consume new prompt/schema; preserve envelope, existing-output rules |
| Existing description stage | `src/image_clarus/stages/description.py` | Regression only; do not change canonical description prompt |
| Artifact transactions | `src/image_clarus/artifacts.py` | Reuse for XMP, extend only on demonstrated need |
| Provider and packaged resources | `src/image_clarus/providers/openai_compatible.py`, `src/image_clarus/resources.py` | Reuse; JSON model-driven, XMP deterministic |
| Default JSON prompt/schema | `prompts/image-structure.txt`, `schemas/image-structure.schema.json` | Evolve and package through existing resource mapping |
| Example config, package, docs | `examples/config.yaml`, `pyproject.toml`, `uv.lock`, `README.md` | Update for approved Slice 2 behavior |
| Existing automated tests | `tests/unit/`, `tests/integration/` | Extend relevant suites; add focused XMP tests where appropriate |
| Existing Slice 1 evidence | `docs/slice-1/IMPL-A3-COMPLETED.md`, `IMPL-A5-COMPLETED.md`, `IMPL-B5-COMPLETED.md`, `IMPL-B7-COMPLETED.md`, `IMPL-C2-COMPLETED.md`, `IMPL-C4-COMPLETED.md`, `IMPL-C5-COMPLETED.md`, `IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md` | Inherit limits and implementation contracts, not historical test results |

**A3-selected additions, not existing files at inspection:** `src/image_clarus/stages/xmp.py` and `src/image_clarus/xmp_backend.py`; focused tests and sanitized fixtures under `tests/`. The A3 record defines the backend interface. Do not add a framework or separate service merely for extensibility.

## Implementer and reviewer protocol

1. The Product Owner alone accepts the Slice 2 REQ, authorizes scope revisions, and approves any required design gate or process exception. An unapproved scope/architecture conflict is a **stop condition**, not an implied new issue or deferral.
2. Phase A is design/contract freeze; the readiness gate must pass before modifying production code. Record alternatives, decisions, rationale, fixture evidence and tests needed for each unresolved contract. Do not reopen the locked decisions above without Product Owner direction.
3. Every CODE/TEST step: write focused test → execute and capture expected **RED** → implement minimum behavior → demonstrate **GREEN** → refactor where needed and run relevant regression. If RED cannot be demonstrated, record that honestly and seek explicit Product Owner approval for a deviation; never claim retroactive RED.
4. For each executed step, create `docs/slice-2/IMPL-<StepId>-COMPLETED.md`. Include step title/status, `Scope deviations: None` or a specific approved deviation/reference/carry-forward, exact **files created, updated, removed**, work summary, decisions and rationale, test commands and actual outcomes, limitations and unchecked items. Reviewers read the completion record first.
5. Each step's linked completion record and checked detailed acceptance items must agree with the matching summary checkoff and plan status. Do not check off unexecuted or blocked tests; creating a record is insufficient evidence. Do **not** create completion records during planning.
6. Automated tests use synthetic descriptions/photos and local controlled provider stubs. Public fixtures must be synthetic or sanitized; never publish original XMP samples, GPS/location, owner/camera/lens/serial/device metadata, credentials, personal photos, private endpoints or provider infrastructure identifiers. Normal user XMP handling **preserves** existing metadata; sanitization applies to public test materials only.
7. Real images, external models or provider calls require operator authorization of endpoint, model, data transfer and cost. digiKam GUI observations and human quality ratings are recorded as **manual evidence**, not automated test passes. If a required verification environment is unavailable, record the blocker and keep acceptance unchecked.
8. If changed functionality supersedes existing code, audit production call sites, remaining consumers, tests, resources and fixtures; remove genuinely orphaned code and obsolete references. Retention of orphaned production code requires Product Owner approval and documented rationale. Do not introduce dependency cycles or break legitimate consumers.
9. Keep repository commit/push/history state under Product Owner control; commits, pushes and history edits are not acceptance gates. Update application patch version for delivered changes according to the project convention, including its authoritative `pyproject.toml`, lockfile and version tests; do not rewrite historical Slice 1 version evidence or tie metadata-schema version to application version.

## Phase summary checklist

### Phase A — Discovery and contract freeze

- [x] Step A1 — Reconcile Slice 2 requirements and the existing HLD [DESIGN]
- [x] Step A2 — Freeze enhanced JSON, ranking, and schema evolution contracts [DESIGN]
- [x] Step A3 — Freeze digiKam XMP field mapping and preservation contract [DESIGN]
- [x] Step A4 — Freeze configuration, update policies, compatibility, and stage outcomes [DESIGN]
- [x] Step A5 — Pass the Phase A readiness gate [DESIGN]

### Phase B — Implementation

- [x] Step B1 — Extend configuration and selected-stage validation [CODE/TEST]
- [x] Step B2 — Extend structured JSON generation and packaged resources [CODE/TEST]
- [x] Step B3 — Implement the ExifTool XMP backend and mapping [CODE/TEST]
- [ ] Step B4 — Implement deterministic XMP selection and field policies [CODE/TEST]
- [ ] Step B5 — Integrate the XMP stage, registry, and single-image CLI [CODE/TEST]
- [ ] Step B6 — Document Slice 2 configuration, behavior, and compatibility [DOCS/TEST]

### Phase C — Verification and closeout

- [ ] Step C1 — Verify the single-image persisted JSON-to-XMP pipeline [TEST]
- [ ] Step C2 — Verify metadata preservation, write recovery, and failure boundaries [TEST]
- [ ] Step C3 — Perform digiKam interoperability and metadata-quality reviews [MANUAL/TEST]
- [ ] Step C4 — Run Linux package, compatibility, and quality gates [TEST]
- [ ] Step C5 — Reconcile Slice 2 evidence and close acceptance [DOCS/TEST]

---

# Detailed steps

## Phase A — Discovery and contract freeze

**Entry:** The Product Owner accepted the governing Slice 2 REQ on 2026-11-17. No production-code changes in Phase A. Small non-production ExifTool/digiKam fixture experiments are permitted when necessary to freeze a mapping; record what actually ran and sanitize any publishable results.

### Step A1 — Reconcile Slice 2 requirements and the existing HLD [DESIGN]

**Goal:** Establish one consistent Slice 2 scope and durable architectural baseline without silently revising existing Product Owner decisions.

**Inputs:** `docs/REQ-image-clarus.md`; `docs/HLD-image-clarus.md`; `docs/slice-2/REQ-slice-2.md`; `docs/slice-2/DISCOVERY-slice-2.md`; Slice 1 plan, A3/A5/C5 and safe-write correction records; repository modules and `README.md` listed above.

**Actions:**
1. Compare every S2-01–S2-18 requirement with the parent REQ and HLD. Record inherited behavior, true Slice 2 refinements, exclusions and any actual conflict. Obtain Product Owner acceptance of the proposed Slice 2 REQ; leave the gate pending if not obtained.
2. Reconcile the parent REQ and HLD §§3–4, 6, 8–10 for the additive JSON information product, JSON inference versus deterministic XMP publishing, the default `ai` root and the **explicit empty-root effective-policy override**. Record the existing Product Owner decision as authoritative, not a reopened decision. Preserve the root-independent JSON paths, field defaults and ownership invariants.
3. Preserve the HLD's original ExifTool/digiKam-only initial backend scope and parent REQ's later optional vendor mappings; avoid a second competing Slice 2 HLD. If an empirically necessary mapping would cross the parent REQ's representation boundary, escalate for Product Owner reconciliation; observation alone is not authorization.
4. Confirm the current repository layout, tests, CLI/config behavior, artifact API, installation commands, application version and published asset paths. Identify actual design gaps rather than assuming the Slice 1 environment is unchanged.
5. Record any genuine conflict and its Product Owner disposition; do not use implementation convenience to narrow or split the authorized slice.

**Outputs:** Reconciled `docs/REQ-image-clarus.md` and `docs/HLD-image-clarus.md` reflecting the approved exception; baseline/conflict/decision evidence and [IMPL-A1-COMPLETED.md](IMPL-A1-COMPLETED.md); plan references updated to confirmed paths.

**A1 progress:** Reconciliation and baseline checks are recorded in the linked completion record. The Product Owner accepted the Slice 2 REQ on 2026-11-17; A1–A5 are complete as design/readiness work.

**Acceptance:**
- [x] Slice 2 REQ status/acceptance is explicitly recorded; no unresolved REQ contradiction is silently bypassed.
- [x] Parent REQ and HLD reflect the actual JSON/XMP separation and already-decided empty-root product behavior without weakening preservation or reopening that decision.
- [x] Current paths, executable toolchain and inherited contracts are verified; necessary changes are distinguished from deferred capabilities.
- [x] A1 completion record lists files created, updated and removed, decisions, evidence and deviations; its link and plan checkoffs are synchronized.

### Step A2 — Freeze enhanced JSON, ranking, and schema evolution contracts [DESIGN]

**Goal:** Decide the complete model-facing JSON payload, configurable category guidance, ranking semantics and versioned compatibility rules before modifying its schema or prompt.

**Inputs:** S2-03–S2-10, S2-13 and S2-18; `schemas/image-structure.schema.json`, `prompts/image-structure.txt`; `src/image_clarus/stages/structure.py`; Slice 1 A3 and B7 records; A1 reconciliation.

**Actions:**
1. Freeze precise field names, schema types/requiredness and empty/absent semantics for title, caption and rank-ordered hierarchical tag candidates. Preserve the six existing descriptive field meanings and the application-owned envelope/provenance. Decide how independent ranked paths represent uncategorized tags and one concept in multiple categories; no XMP root in JSON.
2. Freeze JSON prompt wording and inputs for supported inferences, search-useful ranking, specificity versus useful broader concepts, non-fabrication, meaningful category placement and no fixed candidate count. Define how preferred-category guidance reaches the JSON model without changing the canonical `.desc.txt` prompt.
3. Decide default preferred categories (if any), absent/empty preference behavior, unlisted category recommendations, string/path validity, separators, normalization, duplicates, ties and rank/order serialization. Determine the top-N unit (candidate/path/concept), duplicate handling and default limit for deterministic XMP selection. Leave no hidden semantic judgment to XMP.
4. Apply the existing independent metadata-schema SemVer rule from Slice 1 A3: compatible optional additions may be minor; new required fields that invalidate previously valid payloads require major; patch for annotation-only changes. Freeze actual new schema identity/version and how known built-in versions, unknown versions and fully replacing custom schemas are handled. Keep `format_version: 1` unless its envelope itself changes for a justified reason.
5. Preserve structural-only create-if-missing skip, explicit whole-artifact JSON regeneration, strict validation, custom-schema replacement, model/prompt provenance and safe writing. Define how a consumer recognizes available fields without treating every older payload as invalid.
6. Produce small **fictitious/sanitized** description-to-expected-metadata examples spanning distinct images, optional/empty values, multiple categories and ranking. Specify a human review rubric for supported factual content, useful title/caption, retrieval-oriented ranking and non-forced categorization; separate model-quality judgments from schema validity.

**Outputs:** JSON contract and version decision, prompt requirements, ranked-path/top-N examples, future schema-evolution process and human-review rubric in [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md); plan updated with frozen schema and resource contracts, pending Product Owner review.

**A2 frozen design:** Built-in metadata schema `urn:image-clarus:metadata-schema:2.0.0` adds required `title`, `caption`, and ranked `tag_candidates` path arrays while retaining the six existing fields and envelope format 1. Each distinct path counts once toward configurable top-N (default 10); unsupported fields are empty/no-op. Preferred categories default to an empty list and, when non-empty, are a separate provider request data part, not part of the prompt/description hashes. Recognize explicit built-in 1.0.0/2.0.0 readers; custom payload publication uses an explicit mapping, with exact config and result details assigned to A4. Existing create-only skip and full regeneration remain unchanged. The linked record freezes the complete schema, exact prompt bytes, compatibility and examples; this is design completion, not Product Owner approval or implemented behavior. A3 must verify path representability.

**Acceptance:**
- [x] Every new payload field and category/ranking rule is testable with concrete sanitized examples, with unchanged existing metadata meanings and no XMP root in JSON.
- [x] SemVer choice, schema ID, envelope compatibility, historical/custom payload reader policy and explicit regeneration behavior are stated without introducing automatic migration.
- [x] Top-N limit and multi-hierarchy counting have deterministic definitions, including invalid/duplicate entries and absent/empty fields.
- [x] A small human-review rubric and illustrative evaluation set exist; no real-model execution or observed quality result is claimed.
- [x] A2 completion record, decisions/evidence and plan checkoffs are synchronized.

### Step A3 — Freeze digiKam XMP field mapping and preservation contract [DESIGN]

**Goal:** Freeze evidence-supported preliminary ExifTool write targets and a non-destructive XMP merge/validation contract, with actual digiKam interoperability verified in C3.

**Inputs:** S2-11–S2-16 and S2-18; HLD §6 and §7; discovery §§4–5; Slice 1 A5/B5/C2 and filesystem correction; sanitized or synthetic XMP fixture candidates; A2 JSON contract.

**Actions:**
1. Using synthetic/sanitized fixtures, inspect digiKam-compatible representations for hierarchical leaf assignments, title, caption and optional caption author. Record the distinction between **observed** fields (`digiKam:TagsList`, `lr:hierarchicalSubject`, `dc:subject`, `dc:title`, `dc:description`, `digiKam:CaptionsAuthorNames`, etc.) and fields actually needed/writable. Do not assume vendor duplicates must be synchronized.
2. Test ExifTool sidecar create/read/update with synthetic fixtures where available, including hierarchy serialization, XML language alternatives (`x-default`), author handling and field availability. Record exact evidence and distinguish ExifTool results, observed digiKam output and unverified assumptions. Use this evidence to select preliminary mappings; actual digiKam import/edit and the minimum interoperable field set are mandatory C3 checks, not A3 prerequisites.
3. Freeze read/transform/validate/write interface shape for an optional ExifTool backend, subprocess timeout/error/sanitization boundary, path handling, dependency detection, and the staging arrangement that **never sends the source image as a write target**. Select the exact XMP module paths during this step.
4. Freeze preservation assertions for unrelated camera/vendor/namespace data, manual and `auto` tags, root-scoped overwrite, empty-root additive-only operations, shared flat keyword values with ambiguous ownership, and existing language alternatives. No change to a shared flat field is allowed to delete ambiguous unrelated data.
5. Decide which representations to leave untouched based on the available evidence; how to report a mapping that cannot satisfy preservation; whether a no-change result is `skipped` or `completed`; and how to validate entire candidate XMP before publication and read-back after publication. C3 may require a mapping correction without expanding vendor scope.
6. Define sanitized positive/negative fixture matrix including existing XMP, absent sidecar, malformed sidecar, duplicate/overlapping names, no title/caption/author, hierarchy parent/child, explicit empty root, and preserved foreign metadata. Record the digiKam refresh/import steps to validate later in C3 rather than asserting immediate database refresh.

**Outputs:** Exact XMP mapping and backend contract, synthetic/sanitized fixture requirements and evidence, preservation/round-trip assertions and [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md); HLD mapping clarifications where durable.

**A3 frozen design:** Use `XMP-digiKam:TagsList` for slash-separated explicitly assigned paths and `x-default` alternatives of `XMP-dc:Title`, `XMP-dc:Description` and `XMP-digiKam:CaptionsAuthorNames`; leave shared flat keywords and other observed vendor fields unchanged. `src/image_clarus/xmp_backend.py` owns ExifTool mechanics and `src/image_clarus/stages/xmp.py` owns stage/policy orchestration. The linked record defines source-image protection, preservation, validation, fixtures and failure boundaries. These are preliminary interoperability mappings tested with synthetic ExifTool, not a digiKam verification claim; C3 retains import/edit/save verification.

**Acceptance:**
- [x] An explicit ExifTool field-read/write/validation contract and source-image protection strategy are documented, with observed and verified mappings distinguished.
- [x] Preliminary mappings are grounded in available evidence, specify preservation of all unrelated metadata and never rely on cross-root taxonomy comparisons; unverified digiKam behavior is assigned to C3.
- [x] Empty-root non-deletion and nonempty-root ownership have concrete positive/negative fixture cases, including flat-keyword ambiguity.
- [x] Preliminary mapping evidence and remaining interoperability uncertainty are recorded; no untested field-write assumption is promoted to fact.
- [x] A3 completion record and plan checkoffs are synchronized.

### Step A4 — Freeze configuration, update policies, compatibility, and stage outcomes [DESIGN]

**Goal:** Make selected-stage configuration and every XMP operation deterministic, including older/custom JSON, optional fields, and update-mode interactions.

**Inputs:** S2-01, S2-10, S2-12–S2-17; `src/image_clarus/config.py`, `cli.py`, `pipeline.py`, `results.py`; `examples/config.yaml`; Slice 1 A2/A3/A5; A1–A3 decisions.

**Actions:**
1. Freeze exact YAML keys/defaults and `--set` or dedicated CLI override forms for preferred categories (used by JSON), XMP root, tag top-N/policy, title/caption policies, optional caption author and author policy. Keep omitted root distinguishable from explicit `""` throughout load/merge/override/type validation; preserve CLI > one selected YAML > built-ins.
2. Define a complete root/policy truth table. With omitted root use `ai`; with nonempty root apply `add`/`overwrite`/`new`/`disabled` within the root; with explicitly empty root use effective `add` for `add`/`new`/`overwrite` and effective `disabled` for `disabled`, regardless of other tags. No invalid-combination error or destructive top-level force mode is introduced.
3. Freeze independent `new`/`overwrite`/`disabled` behavior for title, caption, and optional config-supplied author, with absent/supported-empty source values as no-ops. Define what counts as empty existing XMP fields and how existing localized alternatives survive. Do not infer author from model output.
4. Freeze how XMP recognizes compatible built-in historical and custom-schema payloads and maps known available fields. Missing `.desc.json` invokes existing configurable missing-prerequisite handling; missing optional publication fields are no-ops; malformed/incompatible payloads fail with actionable nonsecret diagnostics. A selected stage never auto-regenerates JSON or calls a model.
5. Freeze XMP no-change result code, stage-specific preflight, missing ExifTool behavior, `--regenerate` interaction (it must not silently turn XMP policies destructive), selected-stage options/help and the existing `process` exit/continuation semantics. Determine whether configuration is validated globally or only for the selected stage, without requiring unused XMP/ExifTool settings for `desc`/`json`.
6. Record exact synthetic test matrix across config precedence, empty versus omitted root, policy tables, optional inputs, schema compatibility, unknown keys, `--stages` subsets and default all-stage selection. Mark Phase A contract changes that require review or HLD reconciliation.

**Outputs:** Exact config/CLI/compatibility/policy/result contracts and test matrix in [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md); plan and HLD updated where appropriate.

**A4 frozen design:** `stages.json.preferred_categories` defaults to `[]`; `stages.xmp` defines tag root `ai`, top-N `10`, tag policy `add`, independent `new` title/caption/author policies, null author and explicit custom metadata property mappings. Existing YAML-valued `--set` controls them; an explicit empty root uses `--set 'stages.xmp.tag_root=""'`. Only selected-stage values and ExifTool requirements are validated; unknown keys remain globally rejected. Built-in versions use exact paired validators; custom publication uses explicit literal property mapping. No-change is `skipped/no_change`; `--regenerate` affects only desc/json. The linked record contains full policies, compatibility, diagnostics and tests.

**Acceptance:**
- [x] Config defaults, override parsing, key-level validation and policy truth tables are exact and match the Slice 2 REQ without reopening product choices.
- [x] Missing artifact, absent/empty optional fields and malformed/incompatible JSON have distinct specified outcomes; old/custom JSON mapping is safe and explicit.
- [x] Stage `xmp` has no model dependency; unused XMP configuration/ExifTool cannot block unrelated selected stages.
- [x] Title/caption/author updates and `--regenerate` interactions are defined without accidental deletion or inferred identity.
- [x] A4 completion record and plan checkoffs are synchronized.

### Step A5 — Pass the Phase A readiness gate [DESIGN]

**Goal:** Confirm Slice 2 requirements, HLD, data and XMP contracts, module ownership, executable steps and required Product Owner decisions are ready for implementation.

**Inputs:** A1–A4 completion records; updated HLD; accepted Slice 2 REQ; this plan; relevant Slice 1 baseline evidence.

**Actions:**
1. Audit all A1–A4 contracts for contradictions, incomplete mappings or unfrozen options. Ensure JSON schema version/field shape, top-N semantics, config keys, ExifTool field writes and preservation, results, fixtures and commands are explicit.
2. Treat the orchestrator-assigned scope and governing requirements as ready; resolve normal design details and escalate only genuine scope/requirement conflicts. Review the evidence-supported preliminary mapping as a design, not as verified interoperability. DigiKam import/edit/save verification remains mandatory in C3 and is not an A5 prerequisite.
3. Recheck every Phase B candidate path/test command against the repository; update them to the actual approved design. Preserve all 18 S2 requirements in the traceability matrix and the original REQ's later-slice allocations.
4. Confirm no Phase B production code was introduced before gate approval. Record any blocker and leave this step unchecked until resolved.

**Outputs:** Gate decision, remaining-item register and implementation contracts in [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md); updated plan paths and readiness state.

**Acceptance:**
- [x] A1–A4 design evidence and HLD reconciliation are complete and internally consistent.
- [x] The accepted Slice 2 REQ and readiness contracts are reconciled; no required mapping/contract is left for implementers to guess.
- [x] Exact candidate modules, assets, fixture ownership, commands and test assertions are reconciled against current source.
- [x] No production implementation has begun prematurely; A5 completion record and summary/detailed checkoffs agree.

## Phase B — Implementation

**Entry:** A5 readiness complete; execution begins when the orchestrator assigns a Phase B step. Use the frozen contracts; work is bounded to existing services and the new stage/backend. Escalate genuine scope or requirement conflicts. Every CODE/TEST step documents observed RED, GREEN, refactor and applicable regression evidence.

**A5 implementation handoff:** Existing focused tests are `tests/unit/test_config.py`, `tests/unit/test_cli_config_acceptance.py`, `tests/unit/test_config_diagnostics.py`, `tests/unit/test_structure_stage.py`, `tests/unit/test_structure_resources.py`, `tests/unit/test_schema_worker.py`, `tests/unit/test_openai_compatible.py`, `tests/unit/test_artifacts.py`, and `tests/integration/test_single_image_pipeline.py`. Create `tests/unit/test_xmp_backend.py` and `tests/unit/test_xmp_stage.py` for B3/B4 and synthetic fixtures under `tests/fixtures/xmp/`; B5 adds XMP coverage to the existing pipeline integration tests. The B2 historical source and packaged schema paths are named in A2 and B2. For each test-first step run `uv run --locked --extra dev --python 3.13 pytest -q <step test paths>` before and after implementation; for example B1 uses the first three config test files above. Run B2's structure/resource/schema/provider tests, B3's backend test, B4's stage test, and B5's pipeline integration test plus affected regressions. These are execution instructions, not claims those future tests exist or passed. C4 owns full-suite and packaging evidence.

### Step B1 — Extend configuration and selected-stage validation [CODE/TEST]

**Goal:** Support every approved Slice 2 configuration value with correct precedence, type validation, selected-stage isolation and no model requirement for XMP.

**Inputs:** A4 key/default/CLI contract; `src/image_clarus/config.py`; `tests/unit/test_config.py`, `test_cli_config_acceptance.py`, `test_config_diagnostics.py`; existing `examples/config.yaml` as a reference only.

**Actions:**
1. Add focused config tests and demonstrate RED for omitted versus explicitly empty root, all tag/title/caption/author policies, optional author, top-N, category guidance, unknown keys, typed `--set`, CLI-over-YAML precedence and malformed selected settings.
2. Extend existing configuration resolution/validation where appropriate. Reuse existing defaults, merge rules, key/path normalization and redaction. Validate selected stage values/shapes before execution, including malformed unused shapes being isolated; reject unknown keys globally, including in unselected stages. Do not require an XMP model or ExifTool for JSON-only/description-only selection.
3. Test that JSON-only selects/validates its own category guidance and model independently, whereas XMP-only needs no model credentials, provider endpoint or JSON schema file preflight unless the frozen consumer contract explicitly requires it. Exercise the XMP configuration/preflight boundary in isolation; executable XMP stage integration belongs to B5.
4. Keep old `--regenerate` semantics for the JSON/description stages; do not translate it to an unconditional destructive XMP update.
5. Achieve GREEN and run current config, CLI and regression suites.

**Outputs:** Configuration extension and tests; [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md).

**B1 result:** Configuration resolution and isolated selected-XMP ExifTool preflight are implemented and tested; JSON generation, XMP policy execution and CLI stage integration remain B2–B5. The completion record distinguishes observed RED/GREEN from supplemental cases and records the full regression result.

**Acceptance:**
- [x] Configuration precedence and omitted/explicit-empty root values and policy settings pass resolution/validation examples.
- [x] `desc`/`json` do not depend on XMP-specific preflight or ExifTool; isolated XMP preflight does not require model/provider selection.
- [x] Optional author and policy settings resolve without inventing destructive overrides; B4/B5 verify actual XMP behavior.
- [x] Observed RED/GREEN, regression and completion record evidence are linked.

### Step B2 — Extend structured JSON generation and packaged resources [CODE/TEST]

**Goal:** Make newly generated built-in JSON provide validated title, caption and ranked hierarchy candidates without changing the existing descriptive or provenance contracts.

**Inputs:** A2/A4 frozen JSON and configuration contracts; B1 resolved category configuration; `prompts/image-structure.txt`, `schemas/image-structure.schema.json`, `src/image_clarus/stages/structure.py`, `src/image_clarus/providers/openai_compatible.py`, `src/image_clarus/resources.py`, `pyproject.toml`; existing `tests/unit/test_structure_stage.py`, `tests/unit/test_structure_resources.py`, `tests/unit/test_schema_worker.py`.

**Actions:**
1. Add focused tests first for new schema fields, valid supported/empty outputs, rank order, uncategorized and multi-category recommendations, absence of XMP root, candidate validity, configured category guidance in the JSON request, strict validation and packaging. Run them and record observed RED.
2. Before evolving the built-in schema, copy its exact 1.0.0 bytes to `schemas/image-structure-v1.schema.json`; add the packaged `image_clarus/resources/schemas/image-structure-v1.schema.json` wheel mapping and `structure_schema_v1()` lookup. Verify source and installed-wheel assets and A2's recorded hash. Evolve the canonical schema to A2's 2.0.0 and update the prompt, preserving the six descriptive fields, envelope/provenance, strict parsing, custom schema replacement and exact fingerprints.
3. Update `stages/structure.py` and `providers/openai_compatible.py` to pass B1's resolved category guidance as A2's optional third user data part. Test exact framing, empty omission, retry snapshots and custom overrides; prompt/description fingerprints retain their meanings. Do not add XMP semantics to the provider or JSON artifact.
4. Test structural-only skip of an existing old-version JSON artifact, invalid existing envelope failure, explicit entire-artifact regeneration, failure preservation, and a custom replacement schema that omits built-in publication fields.
5. Achieve GREEN, refactor if needed, run appropriate current unit/integration regressions and check installed resource lookup where the frozen contract requires it.

**Outputs:** Enhanced schema/prompt/JSON generation and focused tests; [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md).

**Acceptance:**
- [x] New built-in outputs validate and contain the approved publication-oriented metadata while existing descriptive fields and provenance remain intact.
- [x] Model inference/category guidance is independent of the XMP root and custom schema/prompt replacement still works.
- [x] Existing JSON skip, explicit replacement, strict validation, schema identity and safe publication behavior pass.
- [x] Observed RED/GREEN and relevant regression evidence, changed-file inventory and completion record are linked.

### Step B3 — Implement the ExifTool XMP backend and mapping [CODE/TEST]

**Goal:** Add the minimal ExifTool-backed sidecar transformation/read/validation interface defined in A3 without embedding selection, inference or policy decisions in the backend.

**Inputs:** A3 mapping/backend/fixture contract; approved sanitized fixtures; `src/image_clarus/artifacts.py`; current package layout; existing artifact and CLI tests.

**Actions:**
1. Add focused tests using synthetic/sanitized XMP and, for process-boundary tests, a controlled fake ExifTool executable or equivalent boundary. Observe RED for absent backend, sidecar creation/read, verified writable fields, unchanged unrelated properties, malformed output, missing executable, nonzero exit, timeout and safe error redaction.
2. Implement or extend the A3-approved XMP backend interface with ExifTool as its sole initial implementation. Keep ExifTool optional for unrelated stages and do not invoke it on the source image as a write target.
3. Implement the evidence-supported preliminary field mapping for hierarchical assignments, title/caption and optional author. Preserve any observed but unnecessary vendor representations; handle XML language alternatives and flat keyword values according to the frozen non-destructive field contract. C3 verifies actual digiKam interoperability.
4. Test ExifTool round-trip behavior where executable availability permits; keep real-tool results distinct from stubbed subprocess tests. Validate transformed XMP before handing complete candidate bytes to the artifact service.
5. Achieve GREEN and run current relevant regressions. If a real required mapping fails its fixture test, stop and revise A3 with the Product Owner rather than adopting an unsafe write.

**Outputs:** Approved XMP backend module(s), sanitized fixtures and tests; [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md).

**B3 result:** The standalone backend and mapping passed synthetic ExifTool and hermetic tests. Unsupported RDF structures fail closed; sidecar recovery, source/destination alias guards and publication belong to stage integration. Actual digiKam interoperability remains in C3.

**Acceptance:**
- [x] Backend operates on XMP sidecars and never writes image bytes; actual read/write targets match the preliminary A3 mapping. Actual digiKam interoperability remains a separate C3 obligation.
- [x] Subprocess failures, tool absence, malformed XMP and unexpected field mutation fail with actionable, nonsecret outcomes.
- [x] Required real-ExifTool mapping checks and hermetic backend tests have recorded results; unmet required mapping remains unchecked.
- [x] Observed RED/GREEN, changed-file inventory and completion record are linked.

### Step B4 — Implement deterministic XMP selection and field policies [CODE/TEST]

**Goal:** Transform recognized persisted JSON and existing XMP metadata into an exact, validated set of policy-governed updates without any model call.

**Inputs:** A2 ranked-candidate contract; A3 field ownership; A4 policy/compatibility contract; `docs/slice-2/REQ-slice-2.md`; B3 backend; test fixtures.

**Actions:**
1. Write and run failing tests for top-N rank preservation, exact-path deduplication and invalid-path rejection without text normalization, unprefixed JSON paths, omitted-root `ai`, explicit-empty no-prefix, and `add`/`overwrite`/`new`/`disabled` under a nonempty root.
2. Test **all empty-root policy combinations**: `disabled` no-op, `add`/`new`/`overwrite` equivalent to non-deleting `add`, including foreign/manual/auto/rootless existing tags and repeated invocations. With a nonempty root, replacing only its assignments is permitted; unrelated roots are untouched.
3. Test title and caption `new`/`overwrite`/`disabled` independently, existing and localized values, absent/supported-empty optional source no-op even under `overwrite`, and config-only optional author with separate policies. No inference of author or clearing on unavailable JSON values.
4. Test recognized historical/custom JSON, missing optional fields, missing required artifact versus incompatible/malformed payload, exact policy/no-change results and rejection of unknown path shapes. Never infer arbitrary custom fields or trigger `json`/provider calls.
5. Implement minimum deterministic selection, mapping inputs and field-policy logic in the appropriate approved layer; delegate ExifTool mechanics to B3 and file publication to the existing artifact service. Document the effective policy in results/diagnostics where A4 requires it.
6. Verify GREEN and run focused and relevant regression tests.

**Outputs:** Deterministic XMP selection and field-policy implementation/tests; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md).

**Acceptance:**
- [ ] Top-N selection is reproducible and follows persisted order without semantic reranking.
- [ ] Empty-root and nonempty-root policy truth tables pass, with verified no-deletion guarantees.
- [ ] Title, caption and author fields follow independent policies; unavailable source data never deletes XMP values.
- [ ] Older/custom JSON behavior, malformed input and no-op results match A4; XMP logic makes no model call.
- [ ] Observed RED/GREEN, regression and completion record evidence are linked.

### Step B5 — Integrate the XMP stage, registry, and single-image CLI [CODE/TEST]

**Goal:** Make the `xmp` stage independently usable and composable with `desc` and `json`, publishing complete XMP through the existing recoverable artifact service.

**Inputs:** B1–B4; `src/image_clarus/cli.py`, `pipeline.py`, `results.py`, `artifacts.py`, `stages/`; current CLI/registry/integration tests; A4 stage-result contract.

**Actions:**
1. Add failing tests for `--stages=xmp`, `json,xmp`, `desc,json,xmp`, default full registry, `desc`/`json` only, missing artifact `fail`/`skip`, no model call from XMP, ExifTool absence selected versus unselected, stage order, CLI output, exit codes and interruption behavior.
2. Add `xmp` as the third registry stage and integrate a stage-owned read/validate/policy/transform/publish flow. Extend CLI wiring and help without moving stage-specific ownership into `run_pipeline`. Preserve single-image path restrictions and existing `search` stub behavior.
3. Reuse `ArtifactService.recover` and `.write` with an XMP-specific validator; preserve correct `.bak` handling, backup-retention config, corrected filesystem mode semantics, operation-owned temp cleanup, source image hash and lock-free behavior. Do not invent stronger concurrent-merge guarantees.
4. Exercise existing output/no-change, brand-new XMP, malformed existing XMP, failure during transformation or safe publication, and graceful cancellation at existing safe boundaries. A failed update must not report completion or delete the only recoverable original.
5. Verify GREEN, run current CLI, pipeline, artifact and single-image integration regressions and check production reachability/orphaned-code references after wiring.

**Outputs:** Integrated XMP stage, registry/CLI updates and tests; [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md).

**Acceptance:**
- [ ] Default and explicit stage combinations follow `desc,json,xmp` order and require no automatic prerequisite expansion.
- [ ] XMP stage works alone with persisted JSON and requires ExifTool only when selected; source image bytes remain unchanged.
- [ ] Recoverable sidecar publishing, stage outcomes, exit codes, interruption and config precedence match the frozen contracts.
- [ ] Existing `desc`/`json`, search stub and artifact behavior regressions pass; obsolete code/fixtures are reviewed.
- [ ] Observed RED/GREEN, regression and completion record evidence are linked.

### Step B6 — Document Slice 2 configuration, behavior, and compatibility [DOCS/TEST]

**Goal:** Document exactly what users can do with Slice 2 and what is intentionally not supported, without implying unfinished work is available.

**Inputs:** Approved A2–A4 contracts, implemented B1–B5 behavior, `README.md`, `examples/config.yaml`, schema/prompt assets and CLI help.

**Actions:**
1. Update README and sanitized config example for XMP optional ExifTool installation, the single-image `xmp` stage, `desc/json/xmp` combinations, YAML and CLI precedence, category guidance, top-N, optional author and title/caption/tag policies.
2. Explain omitted root default `ai` versus expressly `""`; state the **effective** `add`/`disabled` override for empty root and the nonempty-root update-policy semantics. Do not suggest a current destructive top-level force option.
3. Explain additive changes to newly generated JSON, schema-version identity and evolution, valid-old-file skip, explicit full regeneration, custom schemas, absent/empty optional publication values and invalid/incompatible consumer input.
4. Document digiKam sidecar refresh/import behavior only as observed in C3 or label it as requiring manual verification until that step; state no cross-root reconciliation or vendor-specific synchronization. Warn that lock-free concurrent XMP edits can be lost.
5. Verify non-provider documentation examples against actual CLI help/config parsing, packaging and installed resources; inspect all public examples/fixtures for identifying metadata or secrets. Update docs links as appropriate, not code outside scope.

**Outputs:** Updated user documentation/configuration examples, compatibility notes and [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md).

**Acceptance:**
- [ ] Documented commands and configuration keys match the implemented surface or are explicitly marked pending manual validation.
- [ ] Scope, safety defaults, optional author and schema evolution/regeneration behavior are explained accurately.
- [ ] Examples contain no private identifiers or unverified interoperability promises.
- [ ] Documentation check evidence and completion record are linked.

## Phase C — Verification and closeout

**Entry:** B1–B6 delivered with reviewed completion evidence. Planned tests below have **not** been run by this plan. A failing gate requires a bounded in-scope correction with genuine test evidence or a Product Owner decision; do not silently waive criteria.

### Step C1 — Verify the single-image persisted JSON-to-XMP pipeline [TEST]

**Goal:** Verify the complete single-image CLI behavior and persisted handoffs, including default stage selection, independent invocation and schema evolution.

**Inputs:** B1–B6 outputs; `tests/integration/test_single_image_pipeline.py`; local provider stub; sanitized ExifTool fixture set; S2 acceptance crosswalk.

**Actions:**
1. Run black-box CLI tests using a synthetic image and local provider transport. Verify `desc` creates persisted `.desc.txt`, `json` consumes that file and persists `.desc.json`, and `xmp` consumes **persisted** JSON, not prior in-memory results.
2. Exercise default `desc,json,xmp`, selected `desc`, `json`, `xmp`, `json,xmp`, and all three; verify selected order and that a single selected stage never auto-generates prerequisites or requires other stages' unused credentials/config.
3. Cover existing JSON create-only skip across schema-version changes and explicit full regeneration; run XMP on a supported historical/custom JSON artifact with only some optional fields, and on a malformed/incompatible payload; verify different outcomes.
4. Confirm ranking/top-N, tag-root construction, title/caption/optional author and field-specific policies with actual persisted XMP; source image SHA-256 remains identical.
5. Run the isolated integration suite and record commands, versions, fixtures, true results and any unexercised cases. Do not call an external provider or publish private test data.

**Outputs:** CLI/stage integration matrix, test results and [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md).

**Acceptance:**
- [ ] All selected-stage and default single-image flows follow persisted-file contracts and expected results.
- [ ] Historical/custom JSON, missing artifact and optional-source versus invalid-input cases are distinguished correctly.
- [ ] Published XMP field values, source-image integrity and policy/rank behavior match the design.
- [ ] Executed test logs and completion record substantiate the verified cases.

### Step C2 — Verify metadata preservation, write recovery, and failure boundaries [TEST]

**Goal:** Prove destructive-update boundaries and shared artifact safety using real XMP/ExifTool where required and deterministic fault injection elsewhere.

**Inputs:** B3–B5 tests/backend/stage; Slice 1 A5/B5/C2 and approved mode-correction evidence; sanitized XMP snapshots; `tests/unit/test_artifacts.py` and existing integration fault tests.

**Actions:**
1. Compare complete before/after XMP data for nonempty-root tag policies, empty-root every policy, manual/auto tags, hierarchy ancestors, shared flat keyword overlap, unrelated namespaces/camera/vendor fields and localized title/caption data. Verify `overwrite` never escapes a nonempty root and empty root never deletes an existing tag.
2. Exercise `new`, `overwrite`, `disabled` on populated and empty title/caption/author, unconfigured author preservation, absent JSON optional fields and repeated no-change publication. Confirm other valid field updates still proceed independently.
3. Inject ExifTool missing/timeout/nonzero/malformed output; invalid existing XMP; invalid JSON; temporary-output, backup-refresh, publication, read-back and cleanup failures. Reuse the existing artifact service's genuine permission/I/O and simulated unsupported-mode tests; verify preserved recoverable original/backups, proper category/exit and no false completion.
4. Test recovery when `.xmp` is absent but `.bak` exists, destination-plus-backup authority and invalid backup rejection. Run a barrier-controlled overlap of separate OS processes performing XMP read–merge–write against the same sidecar; assert complete valid output rather than a deterministic winner. Document lost-update and backup/cleanup race risks without claiming serialized merges.
5. Record actual scratch filesystem and any ExifTool availability/permission limitations. Do not claim full crash/OS durability or conflict detection.

**Outputs:** Preservation diff/test matrix, failure/recovery evidence and [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md).

**Acceptance:**
- [ ] Tag preservation invariant passes for nonempty and empty roots, including ambiguous shared fields.
- [ ] Existing unrelated XMP metadata and language alternatives are preserved to the frozen A3 contract; all configured field policies pass.
- [ ] Invalid/failing writes do not report success and retain recoverable artifacts, with existing filesystem mode limitations respected.
- [ ] Separate OS processes overlap XMP read–merge–write; resulting artifacts are complete and valid, with no deterministic winner asserted and lost-update risk documented.
- [ ] Actual tested environments and lock-free limitations are documented; record and plan checkoffs align.

### Step C3 — Perform digiKam interoperability and metadata-quality reviews [MANUAL/TEST]

**Goal:** Confirm actual digiKam usability and human value of metadata, not merely syntactically valid XMP and JSON.

**Owner:** Product Owner or explicitly authorized operator performs/observes GUI tests and authorizes any real-model processing, input data and data transfer/cost.

**Inputs:** A2 sanitized quality rubric/examples; A3 XMP mapping/fixtures; B1–B6 implemented behavior; installed digiKam and ExifTool where available.

**Actions:**
1. With a safe synthetic/sanitized image/XMP sample, publish under `ai`, import/refresh XMP in digiKam, confirm hierarchical leaf assignment, ancestor-based filtering without redundant parent assignment, title/caption visibility and editing, and optional caption author. Record **exact UI version, metadata-read/refresh steps, operator observations** and actual resulting XMP changes.
2. Edit a generated hierarchical tag in digiKam, save the change, read back the persisted XMP and refresh/reload in digiKam to verify the edit and preservation of unrelated manual tags. Separately add or edit manual tags/title/caption, rerun Image Clarus under `new`/`overwrite`/`disabled` as relevant, and confirm unrelated metadata remains. Repeat a top-level additive example with explicit empty root, no tag deletions. Do not use unsanitized samples in public evidence.
3. Review a small, varied synthetic/sanitized description set using the A2 rubric, checking generated title/caption factual support/usefulness, tag retrieval relevance, ranking and category appropriateness including uncategorized/multiple categories. Record examples, outcome per criterion and limitations; distinguish human judgment from hard validation.
4. Where real model inference is required, use only an explicitly operator-approved endpoint, model and inputs/cost. If no authorized provider or digiKam is available, record the exact blocker and leave the affected acceptance unchecked; never claim manual verification occurred from schema inspection alone.
5. Report any interoperability gap as an in-scope blocker for mapping correction, not as grounds to broaden the XMP vendor scope.

**Outputs:** Sanitized operator findings, digiKam UI/round-trip procedure, metadata-quality rubric results and [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md).

**Acceptance:**
- [ ] A real digiKam read/edit/refresh path is observed and recorded; a generated tag is edited and saved, its XMP is read back and refreshed, and hierarchy, title, caption, optional author and preservation meet S2-18.
- [ ] Human-reviewed metadata examples and outcomes are recorded with limitations; no unsupported claims pass as evidence.
- [ ] External provider/data/cost permission is documented if used; manual evidence is not represented as automated testing.
- [ ] Blockers remain unchecked rather than silently converted to success; completion record links to evidence.

### Step C4 — Run Linux package, compatibility, and quality gates [TEST]

**Goal:** Verify a reproducible installed Slice 2 CLI, Python compatibility, ExifTool optionality, resource packaging and regression suite.

**Inputs:** Updated `pyproject.toml`, `uv.lock`, `README.md`, resources, all tests; Slice 1 C3/C5 commands; B1–B6 and C1–C3 evidence.

**Actions:**
1. On Linux, verify locked dependencies and run the established commands against the then-current checkout: `uv lock --locked`; `uv run --locked --extra dev --python 3.13 pytest`; `uv run --locked --extra dev --python 3.13 ruff check .`; `uv run --locked --extra dev --python 3.13 ruff format --check .`; `uv build --python 3.13`. Record actual tool/Python versions and exit codes.
2. Test the supported Python 3.12 minimum with `uv run --locked --extra dev --python 3.12 pytest`. A missing interpreter/tool is a recorded blocker, not a passing gate. Do not require native Windows or exhaustive filesystem tests.
3. Install the built wheel in an isolated environment and run `image-clarus --version`, top-level and `process`/`search` help, JSON/description resource lookup and the XMP stage's optional-ExifTool diagnostics; run from outside the checkout to catch packaging errors.
4. Verify `--version` reflects authoritative `[project].version` and synchronized version tests/lock according to the project's patch-version convention. Confirm old search-stub behavior and `desc`/`json` without ExifTool remain valid.
5. Reconcile new dependencies and code with the current package/test layout. Audit changed/replaced code for reachable production consumers, obsolete functions/fixtures and dependency cycles; remove genuine orphans only under the project protocol and record any retention approval.

**Outputs:** Linux test/quality/build/installed-CLI transcript, compatibility and reachability audit, [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md).

**Acceptance:**
- [ ] Full tests, Ruff, locked dependency check and build pass on Python 3.13 Linux, with actual commands/outcomes recorded.
- [ ] Python 3.12 compatibility is executed and passes or remains explicitly blocked/unchecked.
- [ ] Built/installed package exposes required commands and resources; ExifTool is optional outside XMP, version/lock are coherent.
- [ ] Production reachability, unused artifacts and no-unapproved-dependency expansion are reviewed; record and checkoffs agree.

### Step C5 — Reconcile Slice 2 evidence and close acceptance [DOCS/TEST]

**Goal:** Close Slice 2 only when all 18 requirements and the S2-18 acceptance outcomes are supported by actual evidence.

**Inputs:** A1–A5, B1–B6, C1–C4 completion records; accepted Slice 2 REQ and reconciled HLD; acceptance crosswalk below; current repo docs/tests.

**Actions:**
1. Reconcile every S2-01–S2-18 requirement and each acceptance row against executed automated and manual evidence. Confirm safety/preservation checks, model-quality review, digiKam interoperability, versioning and installed-CLI validation.
2. Keep plan status, phase summary, detailed step checks and completion records synchronized; a record may be complete for what was done without implying an unmet acceptance condition passed.
3. Record unmet criteria, accepted deviations and Product Owner approvals. Do not close on merely plausible or planned results; defer only with explicit Product Owner decision, with a visible carry-forward and scope impact.
4. Confirm no batch/traversal/search/vendor expansion was added without approval and that no public fixture or doc contains unsanitized private metadata. Preserve historical Slice 1 evidence.
5. Set status to **Complete** only after required acceptance is verified and Product Owner closure is recorded. Otherwise use **Partial/Blocked** with exact remaining obligations.

**Outputs:** Final crosswalk, closeout disposition and [IMPL-C5-COMPLETED.md](IMPL-C5-COMPLETED.md); synced plan and README status after acceptance.

**Acceptance:**
- [ ] All S2 requirements and acceptance outcomes map to executed, reviewable evidence or explicitly remain open with an authorized disposition.
- [ ] All required tests, digiKam and quality/manual gates are actually satisfied before marking complete.
- [ ] Plan, summary/detail checkboxes, completion records, HLD and public documentation agree.
- [ ] Product Owner closeout decision and deviations/carry-forward are recorded; C5 record linked.

## Parent requirements-to-slice allocation

This matrix carries forward all end-state areas from the Slice 1 allocation. Slice 1 evidence remains historical; Slice 2 work and checks are pending. Later capabilities are candidates, not commitments to a numbered slice or Release 1.

| Parent REQ area | Slice 1 baseline | Slice 2 allocation | Later candidates and goals | Prerequisites and verification |
| --- | --- | --- | --- | --- |
| Purpose, platform, runtime, packaging, license and delivery approach (Purpose; Guiding requirements; Runtime and external dependencies; Delivery approach and scope; Known non-goals) | Python 3.12+, 3.13 baseline, Linux, `uv`, package, version CLI and license | Preserve and verify the installed CLI, package, locked dependencies and application version | Publication timing uncommitted; non-Linux portability desirable, exhaustive OS CI not required | Slice 1 A1/B1/C3; Slice 2 A1, C4–C5 |
| Stage artifacts, source integrity, create-only and regeneration (Guiding requirements; Processing stages and artifacts) | Single-image `desc`/`json`, adjacent sidecars, explicit regeneration | Preserve contracts and add policy-governed XMP | Broader selection remains later | Slice 1 A2/B6–B8; Slice 2 A1/A4, B2/B5, C1–C2 |
| Input selection and traversal (Input selection and traversal) | One image path | Remain single-image | Directory, patterns, recursion, allowlist and batch candidates; exclusions and expanded formats later goals | Slice 2 C1 verifies single input; future selection plan owns traversal and input tests |
| Stage prerequisites and composition (Stage dependencies) | Persisted `.desc.txt`; independent JSON; single-image prerequisite policy | Independently selectable XMP consumes persisted JSON, respects missing-artifact policy and optional fields | Directory/pattern skip-and-continue with later selection/batch work | Slice 1 A2/C1; Slice 2 A4, B5, C1 |
| Providers, prompts, model selection, reasoning and validation retry (Model providers and prompts) | OpenAI-compatible adapter, named per-stage models, prompt/schema overrides, reasoning and bounded opt-in validation retry | Preserve model behavior; evolve JSON prompt/category guidance; XMP makes no model call | Additional providers are future candidates | Slice 1 A3–A4/B3/B6–B7; Slice 2 A2/A4, B1–B2, C1/C3 |
| Structured metadata and provenance (Structured metadata expectations) | Default descriptive payload, replaceable schema, envelope/provenance and independent schema version | Add title, caption, ranked category recommendations and future schema-evolution policy | Further schema evolution subject to its own version/compatibility policy | Slice 1 A3/B7; Slice 2 A2/A4, B2, C1/C3 |
| XMP and preservation (XMP metadata integration) | Not implemented | ExifTool, digiKam mappings, root and field policies, source/XMP preservation, real interoperability | Other representations independently optional in later work; no release commitment | Slice 2 A1/A3–A4, B1/B3–B5, C1–C3/C5 |
| Search (Search) | Help-visible search stub | Preserve stub without functional search | Deterministic text/JSON search and outputs are candidates; embeddings a later goal, not Release 1 requirement | Slice 1 B1/B8; Slice 2 B5/C4; future search plan owns matching tests |
| Configuration and precedence (Configuration and precedence) | Single selected YAML, CLI precedence, stage validation and prompt/schema overrides | Add category and XMP settings, explicit-empty root and selected-stage isolation | Later selection/search settings belong to owning plans | Slice 1 A2/B2; Slice 2 A4, B1, C1/C4 |
| Failure policies, retries, logging and summaries (Failure policies, retries and logging) | Single-image results, zero default request retry, bounded schema retry, redacted diagnostics | Preserve defaults and add XMP-specific failures and results | General category actions/retries, batch continuation/summaries and configurable log destinations remain later | Slice 1 A2/A4; Slice 2 A4, B1/B5, C1–C2/C4 |
| External scheduling, stop, resume and concurrency (External scheduling, stop and resume) | Independent processes, no scheduler, lock-free contract | Preserve CLI composition and test overlapping XMP writes; document lost edits | Multi-image rescan, batch stop and external run bounds remain later candidates | Slice 1 C1–C2; Slice 2 B5, C1–C2; later operational plan owns batch checks |
| Safe writes and recovery (Safe-write requirements) | Shared sidecar service, backup/recovery and filesystem-capability handling | Reuse for validated XMP, including failures, recovery and overlapping processes | Additional filesystem/OS evidence as warranted; no crash-proof promise | Slice 1 A5/B5/C2 and correction; Slice 2 A3, B3/B5, C2/C4 |
| Requirements-to-design handoff (Requirements-to-design handoff) | Slice 1 Phase A froze relevant CLI/config/provider/schema/write decisions | Reconcile parent REQ/HLD and freeze JSON, XMP mapping, configuration and safety contracts before implementation | Selection/search and batch contracts belong to later plans | Slice 1 A1–A6; Slice 2 A1–A5 readiness and requirement/evidence matrices |

## Slice 2 requirements-to-steps traceability

The matrix covers each numbered Slice 2 requirement. Phase A owns contract decisions, Phase B implements them, Phase C verifies them. A step assignment does not imply the step has been executed.

| Requirement | Contract/design | Implementation | Verification/closeout |
| --- | --- | --- | --- |
| S2-01 Persisted handoffs, independent stages | A1, A4 | B2, B5 | C1, C4, C5 |
| S2-02 Artifacts and source integrity | A1, A3 | B3, B5 | C1, C2, C5 |
| S2-03 Additive JSON information | A2 | B2 | C1, C3, C5 |
| S2-04 Useful supported title | A2 | B2, B4 | C3, C5 |
| S2-05 Useful supported caption | A2 | B2, B4 | C3, C5 |
| S2-06 Human-search-oriented ranked candidates | A2 | B2, B4 | C1, C3, C5 |
| S2-07 Hierarchical categorization | A2, A3 | B2, B3–B4 | C1–C3, C5 |
| S2-08 Preferred category guidance | A2, A4 | B1–B2 | C1, C3, C5 |
| S2-09 Inference versus publication | A1–A3 | B2, B3–B5 | C1, C5 |
| S2-10 Schema, prompt and historical JSON compatibility | A2, A4 | B2, B4, B6 | C1–C2, C4–C5 |
| S2-11 Deterministic digiKam publication | A3 | B3–B5 | C1–C3, C5 |
| S2-12 Tag ownership and policies incl. empty root | A1, A3–A4 | B1, B4–B5 | C1–C3, C5 |
| S2-13 Ranked top-N XMP selection | A2, A4 | B1, B4 | C1, C3, C5 |
| S2-14 Independent title/caption policies | A3–A4 | B3–B4 | C1–C3, C5 |
| S2-15 Optional config-only caption author | A3–A4 | B1, B3–B4 | C1–C3, C5 |
| S2-16 Existing XMP, write safety and failure | A1, A3–A4 | B3–B5 | C2, C4–C5 |
| S2-17 Config precedence and stage-specific behavior | A1, A4 | B1–B2, B5–B6 | C1, C4–C5 |
| S2-18 Required acceptance evidence | A1–A5 | B1–B6 | C1–C5 |

## S2-18 acceptance-outcome crosswalk

Each row is an **unverified obligation** until cited completion records demonstrate execution and results.

| Outcome | Required evidence owner | Status |
| --- | --- | --- |
| JSON output extension, old descriptive fields and provenance | B2, C1, C5 | Pending |
| Evidence-bound title/caption/tag claims | A2 rubric, C3, C5 | Pending |
| Ranking, preferred/multiple/uncategorized paths, top-N | A2, B4, C1/C3, C5 | Pending |
| Human-reviewed metadata quality | A2, C3, C5 | Pending |
| Standalone stages and persisted handoffs | B5, C1, C5 | Pending |
| digiKam hierarchy recognition, generated-tag edit/readback and ancestor filtering | A3, C3, C5 | Pending |
| Nonempty/empty root policy and idempotence | B4, C1–C2, C5 | Pending |
| Editable title/caption, independent policies | B3–B4, C3, C5 | Pending |
| Optional author, no-author preservation, all policies | B1, B3–B4, C2–C3, C5 | Pending |
| Existing XMP preservation including flat keywords | A3, C2–C3, C5 | Pending |
| Safe writes, failures, ExifTool optionality, no image edits | B3–B5, C1–C2/C4, C5 | Pending |
| Historical/custom JSON handling, schema/version evolution | A2/A4, B2/B4/B6, C1, C5 | Pending |
| CLI-over-YAML precedence, selected-stage isolation | A4, B1, C1/C4, C5 | Pending |
| Public synthetic/sanitized fixtures | A3, B3, B6, C2–C5 | Pending |

## Consolidated Phase A decisions and gates

The Phase A design decisions are complete. These contracts do not change locked product requirements; implementation and evidence remain assigned to later steps.

| Contract | Design disposition | Implementation / verification |
| --- | --- | --- |
| Parent REQ/HLD reconciliation and accepted Slice 2 requirements | A1 complete | Carry through B1–B6 and C1–C5 |
| JSON, ranking, categories, top-N and versioned schemas | A2 complete; A5 names the historical asset | B1/B2/B4 and C1/C3 |
| Preliminary ExifTool fields, language alternatives, hierarchy and flat-field preservation | A3 complete as design; actual minimum field set unverified | B3/B4; mandatory digiKam verification and correction in C3 |
| Backend subprocess, artifact validation and recovery | A3 complete; A5 clarifies recovery before no-change | B3/B5, C2/C3 |
| Config keys, optional fields, no-op, CLI and stage outcomes | A4 complete | B1/B4/B5 and C1/C4 |

**Already decided, not an open design question:** `ai` when omitted; explicitly `""` means rootless, `disabled` is no-op, all other tag policies behave as additive `add`; nonempty-root policies retain their normal meanings; no namespace prefix in JSON; XMP optional fields never clear data merely because absent/empty; caption author only from optional config; JSON default skip/explicit whole-file regeneration; deterministic XMP with no model calls.

## Deviation, deferral, and escalation ledger

**Approved Slice 2 deviations:** None recorded at planning time.

**Open Slice 2 work:** B2–B6 implementation and Phase C verification remain pending. Actual digiKam import/edit and the minimum interoperable mapping remain C3 obligations; do not portray preliminary ExifTool tests as proving them. Escalate genuine scope or requirements conflicts, not ordinary implementation decisions.

**Carry-forward:** Only the explicitly excluded end-state features in the scope table; no later slice number or Release 1 promise is assigned. Do not narrow current Slice 2 acceptance by marking a hard requirement as deferred without Product Owner authorization.

**Inherited historical exceptions:** Slice 1's accepted test-order and safe-write mode capability corrections remain accurately recorded in its own files. They do not waive new Slice 2 tests or create permission to skip RED evidence.

## Plan validation and source basis

**Plan validation is structural only.** Creation of this proposed plan does **not** mean code was implemented, ExifTool/digiKam ran, model quality was demonstrated, or any test passed.

- [x] The accepted Slice 2 REQ and completed Phase A contracts are recorded; the orchestrator owns subsequent step assignment.
- [ ] Actual implementation and verification results support every detailed acceptance row before it is checked.
- [ ] Completion records and deviations remain aligned as work proceeds.

**Source documents and implementation baseline:**

- [Parent requirements](../REQ-image-clarus.md)
- [Existing HLD](../HLD-image-clarus.md)
- [Slice 2 requirements](REQ-slice-2.md)
- [Slice 2 discovery](DISCOVERY-slice-2.md)
- [Slice 1 implementation plan](../slice-1/IMPL-PLAN-slice-1.md)
- [Slice 1 A3 JSON contract](../slice-1/IMPL-A3-COMPLETED.md)
- [Slice 1 A5 safe-write contract](../slice-1/IMPL-A5-COMPLETED.md)
- [Slice 1 B5 artifact implementation](../slice-1/IMPL-B5-COMPLETED.md)
- [Slice 1 B7 JSON implementation](../slice-1/IMPL-B7-COMPLETED.md)
- [Slice 1 C2 failure testing](../slice-1/IMPL-C2-COMPLETED.md)
- [Slice 1 C4 manual provider evaluation](../slice-1/IMPL-C4-COMPLETED.md)
- [Slice 1 C5 closeout](../slice-1/IMPL-C5-COMPLETED.md)
- [Slice 1 filesystem mode correction](../slice-1/IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md)
- [Root JSON prompt](../../prompts/image-structure.txt) and [schema](../../schemas/image-structure.schema.json)
- [Example config](../../examples/config.yaml), [README](../../README.md), [package manifest](../../pyproject.toml)
