# Slice 4 Implementation Plan

**Date:** 2026-11-23

**Status:** In progress. A1–A4 design are complete; A5 is in progress, and all implementation and verification steps remain open. No Slice 4 feature implementation or acceptance test is claimed by A1–A5.

**Goal:** Deliver native unattended batch processing with metadata-only planning, an initial LLM-work image allowance, optional inter-stage concurrency, dry-run and useful progress reporting, plus separate category-state management commands, while preserving accepted single-image behavior.

**Intended repository path:** `docs/slice-4/IMPL-PLAN-slice-4.md`

**Governing inputs:** [Parent REQ](../REQ-image-clarus.md), [parent HLD](../HLD-image-clarus.md), and [Slice 4 REQ](REQ-slice-4.md). The [Slice 3 plan](../slice-3/IMPL-PLAN-slice-3.md) and [closeout](../slice-3/IMPL-C3-COMPLETED.md) establish inherited behavior, development conventions, and historical evidence limits.

**Inspected baseline:** Public `ServiceCraze/image-clarus`, `main` at [03aab049b0a77fe41e327d298d509c2d1b49e79c](https://github.com/ServiceCraze/image-clarus/commit/03aab049b0a77fe41e327d298d509c2d1b49e79c), package version `0.3.3` in `pyproject.toml` and `uv.lock`. Inspection covered the current repository tree, governing documents, Slice 3 plan and design/closeout evidence, CLI/configuration, pipeline/results, stages, artifact services, provider/schema boundaries, state and prompt services, resources, and relevant tests. This is source inspection, not fresh application-test or packaging evidence.

**Authority and orchestration:** Follow REQ → HLD → implementation plan → implementation. The Slice 4 REQ is still labeled draft at the inspected revision. The orchestrator's assignment establishes requirements readiness for the assigned work; this plan adds no separate REQ acceptance gate. Phase A completion is a mandatory prerequisite to both implementation phases. Newly arising product-behavior decisions require Product Owner approval before Phase A closes; already decided behavior and routine implementation mechanics do not require renewed approval.

## Implementer and reviewer protocol

1. Execute only the assigned step after its dependencies are satisfied. Resolve ordinary mechanics within the approved scope. Raise actual conflicts, behavior changes, scope expansion, or proposed deferrals instead of silently narrowing requirements.
2. Create `docs/slice-4/IMPL-<StepId>-COMPLETED.md` when the corresponding step is executed, and link it in that step's Outputs. The links in this proposed plan name future records; do not create them merely to make the links resolve during drafting.
3. Every completion record includes the exact step heading, status, decisions and rationale, files created/changed/deleted, actual commands and results, tested package/runtime versions, blockers and limitations, unchecked acceptance criteria, and `Scope deviations: None` or the approval reference, reason, owner, and carry-forward.
4. Review the completion record first, then verify its implementation and evidence. A record's existence, a commit, or an orchestration advancement is not proof that an unexecuted test passed. Keep overall/phase status, summary checkboxes, detailed acceptance, crosswalks, and completion records consistent.
5. Use focused unit tests as the primary development execution harness. Tests and implementation evolve together to investigate behavior and resolve uncertainty. An initial test pass or failure is acceptable; mandatory RED-before-implementation sequencing is rejected. Record observed results and never invent historical RED evidence.
6. Preserve existing patterns and supported consumers. Audit callers, imports, resources, exports, tests, and fixtures when replacing a production path. Remove confirmed orphaned production code and obsolete tests. Retaining a true orphan requires an explicit Product Owner exception, documented purpose, and adjacent code comment; tests or unsupported exports alone do not justify retention.
7. Use synthetic images, sanitized sidecars, independent prompt fixtures, local provider stubs, and fictitious models, providers, hosts, paths, and credentials in publishable artifacts. No live provider call is authorized by this plan. A new manual digiKam exercise is not a Slice 4 acceptance condition.
8. Each delivering step owns the project's patch-version increment and synchronization at its delivery boundary, including documentation deliveries where applicable. Update the authoritative `pyproject.toml`, synchronize `uv.lock`, and update affected exact-version assertions, including `tests/unit/test_cli.py` and `tests/unit/test_resources.py` where needed. Record the actual version and checks. Respect an explicitly narrower assignment; do not preselect future release numbers or bump versions merely while drafting this proposed plan.
9. Design steps produce documented contracts and acceptance scenarios, not feature implementation. No significant design choice may pass through the Phase A gate as TBD. Record the outcome, rationale, acceptance scenario, and applicable Product Owner decision for each significant choice.
10. Commits, pushes, releases, history changes, and implementation of other steps are not authorized merely by this plan. Preserve accepted Slice 1–3 documents and historical evidence; reconcile current parent documentation forward.

## 1. Scope and fixed contracts

### 1.1 Included

- Native file, directory, and supported-pattern selection; deterministic discovery, default unlimited recursion, independent process/rebuild depth, extension controls, and the approved symlink boundary.
- Generic stage capabilities, a completed metadata-only initial plan, initial queue routing, and an allowance for distinct initially admitted LLM-work images.
- Authoritative execution rechecks, allowed corrective inference, progressive routing, one active worker per selected stage, default inter-stage concurrency, and sequential image-first execution when disabled.
- Per-image state resolution and eligible category accumulation, ordinary nonblocking state failures, failure continuation, interruption, and rescan-based resume.
- Dry-run, its required labeled memory estimate, verbose single/batch output, plan-relative progress, final actual metrics, and script-compatible result/exit behavior.
- A separate implementation phase for category list, clear, and additive best-effort rebuild.
- Behavioral verification, regression and package checks, documentation, and evidence reconciliation.

### 1.2 Excluded

Native search, content-aware planning Option B, multiple workers within one stage, model-aware scheduling, built-in scheduling, a persistent queue/job database, new provider protocols or image decoders, new LLM stages, prompt/schema changes, XMP-derived rebuild, additional XMP mappings, taxonomy inference/reconciliation, discovered-symlink following, advanced exclusion rules, and a digiKam plugin are outside this slice. Metadata-only Option A remains available if Option B is introduced later. No fixed later slice number, delivery order, or Release 1 commitment is assigned here.

### 1.3 Accepted behavior

| Contract | Required treatment |
| --- | --- |
| Discovery | Files in a directory precede descent into its subdirectories. Selection/admission order is deterministic for an unchanged collection. Recursion is unlimited by default; depth 0 means starting directory only, 1 includes its direct subdirectories. Process and rebuild settings are independent of each other and of category-macro depth. |
| Symlinks | Do not follow discovered image or directory symlinks. Preserve explicit image-target resolution; an explicitly supplied directory symlink may designate a root. Apply the same boundary to rebuild. |
| Capabilities | `usesLLM` and `skipIfValidOutputExists` are generic stage concepts. Both are true for `desc`/`json`, false for `xmp`. Respect regeneration. XMP's runtime `no_change` is an outcome, not an existence-based planning bypass. |
| Planning | Read directory/existence metadata and configuration only as needed. No image/sidecar-content reads, recovery, ExifTool, inference, category accumulation, or persistent-state/artifact mutation. Finish the execution plan before workers begin. Predictions are provisional. |
| Initial admission | `--max-work-files N` is an optional positive-integer allowance for the first N distinct images predicted to need any selected LLM stage. One image can run multiple LLM stages for one slot. No runtime replenishment or retroactive reclassification. |
| Known exclusions | Images initially known to need LLM work but excluded by the allowance remain excluded from all selected LLM inference. They still reach selected non-LLM stages under ordinary prerequisite/continuation policies. Discovery must not simply stop at the Nth admitted image. |
| Corrective work | An image initially predicted to need no selected LLM work can require corrective inference at execution, subject to existing stage policies. Actual distinct LLM-work images can exceed N, with no inherent twice-N cap. This does not authorize regeneration of every invalid artifact. |
| Selected stages | Registry order remains `desc`, `json`, `xmp`. Do not add omitted prerequisite stages. An XMP-only invocation is uncapped by the LLM allowance and requires no model. |
| Routing | Existing-output predictions and budget exclusions permit early routing; they are not successful stage results. Confirm same-image prerequisites/continuation without waiting for unrelated upstream inference. Non-LLM work arrives progressively. |
| Failure continuation | Preserve all three HLD policies: **continue to the next selected stage**, **stop the current image and advance to another eligible image**, and **abort the entire batch**. Ordinary stage failures default to **stop current image**. A2 freezes syntax, transitions, and aggregation, not whether to implement these choices. |
| Concurrency | Enabled by default; at most one active worker per selected stage, allowing different stages to process different images. Disabled mode finishes selected stages and eligible accumulation for one image before starting the next. |
| State | Preserve CLI > YAML > nearest initialized CWD ancestry > nearest initialized image ancestry > memory, per image. Retain each image's selected state through prompt reads and eligible accumulation. Never make the first image's discovered repository the whole batch's default. |
| Category accumulation | Preserve generated/valid-skipped JSON eligibility and the accumulation-disable setting. Existing CLI accumulation occurs after that image's selected stages finish. Preserve this lifecycle; any proposed change is an explicit Phase A product-behavior decision. Concurrent guidance may depend on timing. |
| State failures | During ordinary processing, report state errors visibly without invalidating otherwise valid stage work or silently substituting another persistent store. Dedicated management commands have strict, visible failure outcomes. |
| Category commands | List is read-only, including open/validation, with no migration/init. Clear deletes categories only. Rebuild adds existing JSON categories using current extraction rules, keeps prior categories, continues past invalid/unreadable inputs, retains successful partial accumulation, and changes nothing for an empty result. |
| Reporting | Separate predictions, actual skips, completions, failures, budget exclusions, and interrupted/not-attempted work. Report initial admission, distinct corrective-overrun images, actual distinct LLM-work images, and per-stage counts separately. Accounted-for progress reaching 100% does not imply success. |
| Safety and compatibility | Preserve source bytes, persisted handoffs, create-only/regeneration rules, envelope/provenance, user-owned prompts, XMP policies, selected-stage preflight, and safe writes/recovery. SQLite sharing and lock-free sidecar races remain separate contracts. |

## 2. Inspected implementation and extension boundaries

Recheck the baseline before executing a step. The paths and symbols below exist at the inspected revision. New module and test names elsewhere in this plan are proposed until Phase A confirms them.

| Concern | Existing paths and symbols | Implementation implication |
| --- | --- | --- |
| CLI | `src/image_clarus/cli.py`, `_main()`, `OnceAction`, `main()` | The CLI accepts one `IMAGE` and rejects directories/globs. Preserve singleton-option checks, registry-order selection, help/version behavior, path quoting, redaction, and concise single-image output while adding native selection. |
| Config | `config.py`, `DEFAULTS`, `resolve_config()`, `_selected()` | Add settings through defaults, strict shape/key validation, dedicated/generic overrides, and precedence. Selected XMP preflight currently invokes `exiftool -ver`; dry-run needs a static-resolution boundary before execution-only probes. |
| Pipeline/results | `pipeline.py`, `STAGE_REGISTRY`, `run_pipeline()`, `StopToken`; `results.py`, `StageResult`, `PipelineResult` | The current coordinator is single-image; descriptors, batch planning, scheduling, timing, and aggregate accounting are new. Preserve primary result/exit semantics. Current stage failure continuation is stop-current-image or continue; global batch abort requires an explicit contract. |
| Description/JSON | `stages/description.py`, `run_description()`, `_valid()`; `stages/structure.py`, `run_structure()`, `_read_envelope()` | Both recover and validate before `output_exists`. An invalid primary without regeneration fails. Existing valid JSON can skip before checking its description. Do not silently strengthen skip validation to a new current-payload-schema requirement. |
| Artifact boundary | `artifacts.py`, `ArtifactService.recover()` and `write()` | Recovery reads content and may restore/remove files. It is execution work and cannot be called by the metadata-only planner. Reuse the publication contract. |
| XMP | `stages/xmp.py`, `run_xmp()`, `prepare_updates()`; `xmp_backend.py` | Existing XMP alone cannot predict a skip. Evaluation reads persisted JSON/XMP and may use ExifTool; keep all of it out of planning. |
| Cancellation | CLI `_SignalInterrupt`, `InterruptibleProvider`, shared `state.interruptible`; provider/schema/XMP subprocess boundaries | The existing main-thread signal mechanism assumes a single active operation. Define concurrent cancellation, subprocess ownership, and safe-write completion before choosing a worker topology. |
| State | `state/resolution.py`, `select_directory()`; `state/service.py`, `StateService`; `state/storage.py`, `SQLiteStorage`, `MemoryStorage` | Preserve per-image resolution. Processing service fallback is intentionally permissive; management cannot reuse it unchanged. SQLite opening can migrate and uses writable access; read-only listing needs a distinct access contract. |
| Categories/prompts | `state/accumulation.py`, `accumulate_categories()`, `_extract()`; `state/categories.py`; `prompt_expansion.py` | Reuse current supported envelope/schema/extraction/deduplication semantics. Keep parsing/domain policy out of the batch coordinator; retain image-state association and post-image accumulation ownership. |
| Resources/quality | `pyproject.toml`, `uv.lock`, `resources.py`, `prompts/`, `schemas/`, `tests/unit/`, `tests/integration/` | Python 3.12 minimum, 3.13 development, uv/Hatch packaging, pytest/Ruff, four packaged prompt/schema resources. No new dependency is assumed by this plan. |

**Dependency direction:** CLI assembles resolved configuration and services. Discovery produces eligible identities/paths without stage policy. Planning uses generic descriptors and metadata-only predicates. Execution invokes stage-owned authoritative decisions and transformations. Reporting consumes facts/events; it does not change eligibility. State resolution, storage, category extraction, and management remain separate from queue scheduling. Providers remain transport boundaries. Confirm proposed imports and avoid new cycles.

## 3. Phase summary checklist

Phase M is the separate category-management phase required by S4-15–17. It is placed between batch implementation and closeout while retaining the project's Phase A design, Phase B implementation, and Phase C verification convention. Steps are assigned in displayed linear order across phases; dependencies describe inputs, not permission to skip preceding steps. M1 uses A5 and B1; M2 also uses B2. Category management has no functional dependency on the concurrent batch engine, although B3–B6 precede it in the displayed sequence.

### Phase A Discovery and design completion

- [x] Step A1 - Freeze selection and configuration contracts [DESIGN]
- [x] Step A2 - Freeze stage routing and execution contracts [DESIGN]
- [x] Step A3 - Freeze state and category management contracts [DESIGN]
- [x] Step A4 - Freeze reporting and memory estimation contracts [DESIGN]
- [ ] Step A5 - Complete design and verify implementation readiness [DESIGN]

### Phase B Batch implementation

- [ ] Step B1 - Extend configuration and command boundaries [CODE]
- [ ] Step B2 - Implement reusable deterministic discovery [CODE]
- [ ] Step B3 - Implement stage capabilities and metadata planning [CODE]
- [ ] Step B4 - Implement per-image execution and state lifecycle [CODE]
- [ ] Step B5 - Implement concurrent stage coordination and shutdown [CODE]
- [ ] Step B6 - Integrate dry-run progress and actual metrics [CODE]

### Phase M Category management

- [ ] Step M1 - Implement strict category list and clear [CODE]
- [ ] Step M2 - Implement additive category rebuild [CODE]
- [ ] Step M3 - Verify category command boundaries and concurrency [TEST]

### Step B7 - Document Slice 4 usage and compatibility [DOCS]

- [ ] Step B7 - Document Slice 4 usage and compatibility [DOCS]

### Phase C Verification and closeout

- [ ] Step C1 - Verify batch behavior through the CLI [TEST]
- [ ] Step C2 - Verify failure interruption and resume boundaries [TEST]
- [ ] Step C3 - Run regression packaging and quality checks [TEST]
- [ ] Step C4 - Reconcile evidence and close Slice 4 [DOCS]

| Handoff | Dependencies |
| --- | --- |
| A5 design-completion gate | A1–A4 reconciled; significant decisions closed and required product decisions approved |
| Batch foundations | A5 → B1 → B2 → B3 |
| Batch execution/reporting | B3 → B4 → B5 → B6 |
| Category delivery | A5 + B1 → M1; M1 + B2 → M2 → M3 |
| User documentation | B6 + M2 + M3 → B7 |
| Integrated acceptance | B6 + M3 → C1 → C2 |
| Quality/closeout | B7 + M3 + C1 + C2 → C3 → C4 |

## 4. Detailed steps

### Phase A Discovery and design completion

**Entry:** Design work is assigned. Reconcile any checkout changes since the inspected baseline. A1–A4 are completed historical steps; their shared contracts must agree before A5. Design records distinguish fixed requirements, observed behavior, proposed decisions, and approved decisions.

### Step A1 - Freeze selection and configuration contracts [DESIGN]

**Goal:** Make selection, traversal, configuration precedence, and command startup unambiguous before implementation.

**Inputs:** S4-01–05, S4-08–09, S4-11–13, S4-15–18; parent input/configuration sections; HLD §§3–5; `cli.py`, `config.py`, `endpoint.py`, resources and current configuration/CLI tests.

**Actions**

1. Freeze exact positional grammar for files/directories/patterns, multiple selections/roots, quoted versus shell-expanded patterns, recursive-pattern meaning, and treatment of no matches, nonexistent/unreadable roots, unsupported explicit files, and empty selections. Preserve explicit-single-file versus batch provenance even when a pattern matches one image.
2. Specify root ordering, per-directory file and subdirectory sorting, case/Unicode behavior, depth anchoring for patterns, and deterministic deduplication before admission. Define image identity for repeated paths, overlapping roots, explicit symlink aliases, and hard links; state what identity does and does not guarantee. Decide discovered-symlink handling for pattern expansion as well as traversal.
3. Freeze YAML keys, types, defaults, dedicated flags, generic overrides, repeated/conflicting option rules, and diagnostics for process/rebuild depth, extensions, concurrency, `--max-work-files`, `--dry-run`, and `--verbose`. The approved flags retain their names. Work limits must be positive integers; specify null/unlimited representations and reject invalid controls. Preserve origin-based path resolution and the existing macro-depth meaning.
4. Define selection-dependent missing-prerequisite defaults below explicit YAML/CLI overrides. A directory or pattern remains batch-context even with one result. Preserve dedicated flag/generic override precedence; do not overwrite a user's explicit `fail` while applying batch-default `skip`.
5. Separate configuration/static validation from execution-only preflight. Specify the exact dry-run access boundary, selected-stage configuration validation, allowed configuration/prompt/schema resource reads, and diagnostics when runtime prerequisites cannot be checked. No ExifTool probe, provider call, state opening/migration, sidecar recovery, or image/sidecar-content read may occur along dry-run startup/error paths. Actual execution must still preflight every selected stage before any stage writes.
6. Define reusable discovery interfaces for image processing and JSON-sidecar rebuild, with independent eligibility policies and depth settings. Discovery must not import stage, provider, state-storage, or XMP policy. Record proposed modules/test files and configuration examples for B1/B2 and M1/M2.

**Outputs:** Selection/identity/ordering and configuration/startup tables in [IMPL-A1-COMPLETED.md](IMPL-A1-COMPLETED.md); exact CLI/YAML examples; selected discovery interfaces and proposed test locations.

**Completion:** A1's selected contracts, evidence and product-behavior approval handoff are recorded in [IMPL-A1-COMPLETED.md](IMPL-A1-COMPLETED.md). A2–A4 must reconcile shared choices and A5 owns the Phase A gate; no implementation is implied.

**Subsequent Product Owner decision:** Classify each selection literal-first: an existing exact file or directory wins even when its name contains glob metacharacters; otherwise use the A1 Bash-style glob rules. Shell expansion remains external and quoting alone is not observable. The A1 record contains the updated contract and acceptance scenarios.

**Subsequent Product Owner decision — platform design:** Discovery must be designed and implemented for Linux and Windows, using native portable Python path/filesystem facilities and host-appropriate syntax; this is Slice 4 work, not a later portability project. B2 must exercise Windows drive, UNC and separator interpretation with host-independent pure-path tests on Linux as well as actual Linux traversal tests. Such tests do not prove Windows filesystem/runtime behavior; no Windows machine or cross-platform CI is required. A1's subsequent platform contract governs.

**Acceptance**

- [x] Every supported selection/control has a documented valid, invalid, and empty-case outcome, including duplicate identities and explicit/discovered symlink boundaries.
- [x] Defaults and overrides retain existing precedence; process/rebuild/category-macro depth are distinct.
- [x] Dry-run startup and failure paths have a demonstrable metadata-only boundary, while real execution retains selected-stage preflight.
- [x] New product-behavior decisions have an outcome, rationale, acceptance scenario, and required approval before A5.

**Dependencies:** Governing requirements and assignment; reconcile shared controls with A2–A4 before A5.

### Step A2 - Freeze stage routing and execution contracts [DESIGN]

**Goal:** Resolve provisional bypass validation, frozen admission, same-image sequencing, concurrent execution, and shutdown without duplicating stage policy.

**Inputs:** S4-04–11, S4-14, S4-18; HLD §§2–3 and 7; A1 selection/configuration; `pipeline.py`, `results.py`, all stages, `artifacts.py`, CLI signal wrappers, provider/schema-worker/XMP boundaries; existing stage and signal tests.

**Actions**

1. Select the descriptor representation, metadata predictor, authoritative inspection/execute interfaces, and dependency direction. Keep predicates reusable while separating metadata prediction from content validation/recovery. Specify what remains owned by a stage and how single-image execution uses the same authoritative decisions.
2. Complete the runtime decision table seeded in §7. Cover every initial class—admitted, initially no selected LLM work, known budget-excluded—and valid, missing, invalid, recovered, externally created, and externally changed outputs. Include regeneration, selected subsets, missing prerequisites, and stop/continue/abort. Invalid primary output without regeneration retains its existing failure; do not invent a recovery success or strengthen existing JSON skip validity.
3. Freeze the plan entry/admission identity and routing state machine. Document predicted route, pending authoritative confirmations, ready work, correction routing, stage outcome, terminal image, and interruption. Define queue ownership, exactly-once accounting, duplicate-enqueue prevention, exhausted-input detection, drain/closure, and worker-error propagation.
4. Select a concrete bypass-validation and forwarding protocol. Show how existing-output candidates advance without waiting for unrelated long-running upstream inference while downstream work for that same image obeys real validation and continuation. A provisional prediction cannot be passed off as `output_exists`. Clarify the one-worker-per-stage invariant and ownership of lightweight confirmation versus transformation so the design does not hide a second stage worker.
5. Freeze inference admission checks at the execution boundary. Known exclusions must never call selected LLMs, even after sidecars change. Initially no-work images may make permitted corrections; omitted stages remain omitted. Define how a budget-excluded selected JSON stage with existing valid output retains applicable validation/accumulation side effects without permitting inference.
6. Define sequential image-first execution using the same frozen plan, actual stage behavior, and admission rules. Define image termination and state-finalization callbacks with A3; concurrency may reorder different images but not invent success or bypass same-image continuation.
7. Select worker topology and cancellation mechanics after tracing actual synchronous HTTP, main-thread signal, schema subprocess, and ExifTool behavior. Define SIGINT/SIGTERM, stop accepting/dispatching work, request cancellation, in-progress safe writes, repeated signals, worker exceptions, and resource cleanup. A blocked provider must not silently degrade to waiting for its ordinary request timeout. Preserve completed publications when shutdown arrives.
8. Freeze implementation mechanics for the HLD's **three required failure policies**: continue to the next selected stage, stop the current image and advance to the next eligible image (**ordinary stage-failure default**), and abort the entire batch. Define exact config/CLI syntax, state transitions, termination/forwarding, and aggregate exits with A4. Do not treat any of the three as optional design scope. Preserve explicit-single-image and missing-prerequisite semantics. Distinguish preflight failure, per-file failure, ordinary skip, budget exclusion, global abort, and signal. Design a deterministic early-stage failure case with a usable persisted input for a later selected stage and another eligible image; each policy must produce observably different effects on the current image and subsequent batch work.

**Outputs:** Descriptor/inspection contracts, full admission/sidecar decision table, queue lifecycle and cancellation protocol, and deterministic barrier scenarios in [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md); chosen modules/test boundaries.

**Acceptance**

- [x] Every significant routing/validation/shutdown branch has an outcome, rationale, and acceptance scenario; no prediction is itself an authoritative stage result.
- [x] The protocol supports unrelated-image overlap, same-image coordination, one worker per selected stage, and actual sequential mode.
- [x] Admission is immutable; corrections and known exclusions are distinct; no slot replenishment or assumed twice-N bound appears.
- [x] All three required HLD continuation choices and the stop-current-image default have a concrete transition/exit contract and a two-image, valid-downstream-data acceptance scenario; no policy was dropped during design.
- [x] Recovery, invalid-artifact, prerequisite, failure, safe-write, and cancellation contracts match existing behavior or have an explicit approved change.
- [x] B3–B5 have concrete interfaces and deterministic test coordination, not an unresolved choice of queue or cancellation architecture.

**Dependencies:** A1 inputs as available; reconcile lifecycle/state/reporting with A3/A4 before A5.

### Step A3 - Freeze state and category management contracts [DESIGN]

**Goal:** Preserve per-image state behavior and define strict management operations independently of batch scheduling.

**Inputs:** S4-02–03, S4-07, S4-10, S4-15–18; parent application-state requirements; Slice 3 A2/C1/C3 records; state modules, CLI post-pipeline accumulation, prompt expansion, supported metadata schemas, and state/accumulation tests.

**Actions**

1. Define state identity and lifecycle per image, including explicit/CWD sharing, separate image-ancestor collections, no-store memory sharing, failed-store memory fallback, diagnostics, and safe service reuse/closure under concurrency. Do not blindly share a mutable fallback-prone `StateService` across unrelated images. Preserve no persistent substitution and no transaction spanning inference or a whole batch.
2. Preserve the current post-selected-stage accumulation boundary and actual-result eligibility. Define exactly-once finalization after success, later-stage failure, budget bypass, interruption, and accumulation disabled. Resolve valid existing JSON on budget-excluded images without classifying a budget bypass itself as `output_exists`. Sequential finalization precedes the next image; planning/dry-run never accumulates.
3. Freeze command grammar and selection context for list/clear with no image argument and rebuild with source selections. State how CLI, generic overrides, YAML, CWD, source-root context, and absent persistent state are handled. Rebuild targets one consistently chosen repository; do not silently scatter updates according to individual source files or choose another repository on failure.
4. Define a genuinely read-only repository open/validation path for list, including directory/database/journal effects, inaccessible/corrupt/unsupported-version state, and migration-required reporting. Existing writable construction can migrate and is insufficient. Management failures must not fall back to temporary state and claim persistent success.
5. Define category-only clear transactions and returned outcomes, preserving unrelated domains/schema data and sidecars. Define migration policy for mutating management commands separately from read-only list. Reconcile it with rebuild's empty-result no-change requirement; an empty scan must not mutate the store indirectly during startup.
6. Define shared result-bearing JSON extraction for ordinary accumulation and rebuild. Preserve `_extract()` acceptance: recognized envelope/schema identities, valid historical no-category inputs, custom identity rules, candidate validation, exact full paths and deduplication. Do not require unrelated payload fields that current extraction does not require, import stage code into state-domain code, or infer categories from XMP.
7. Define rebuild enumeration, source identity, explicit sidecar inputs if supported, orphan sidecars/image association policy, transaction granularity, successes/no-category skips/failures, interruption, and storage errors. Invalid/unreadable inputs continue best effort; already committed additions remain. Define truthful counts for inspected inputs, category-bearing inputs, eligible paths, and inserted paths without attributing concurrent writers' additions to this command.
8. Complete management decision tables for no-store/access/migration errors, empty input, partial success, failed clear/update/commit, interruption, concurrent list/add/clear/rebuild, and ordinary processing during management. Preserve short SQLite transactions and order-dependent results; neither a whole-scan lock nor replacement rebuild is authorized. Specify independent-process tests.

**Later Product Owner clarification (A5):** The read-only contract is logical application data/schema read-only with stdlib `sqlite3`; ordinary journal/WAL/shared-memory and access-time effects are permitted. List does not initialize or migrate. Registered migrations are allowed transactionally with clear or the first eligible update of a nonempty rebuild; empty/no-category rebuild does not migrate. This supersedes stricter physical no-write interpretations without changing the historical A3 record.

**Outputs:** Per-image state/finalization contract, management selection/access/result tables, extraction boundary, and concurrency scenarios in [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md); confirmed implementation paths for B4 and Phase M.

**Acceptance**

- [x] Multi-collection state, memory/fallback ownership, diagnostics, and close boundaries are fully specified without changing precedence.
- [x] List is read-only from startup through failure, with migration-required reporting; management never silently substitutes memory or another persistent store.
- [x] Clear preserves other domains; rebuild is additive, best effort, empty-safe, and uses existing extraction semantics.
- [x] Accumulation timing/eligibility, budget-excluded valid JSON, interruption, and concurrent management have explicit outcomes and test boundaries.
- [x] All significant product decisions have the required disposition before A5; routine storage mechanics do not create unnecessary approval gates.

**Dependencies:** A1 selection/configuration and A2 execution contracts as available; reconcile metrics with A4 before A5.

### Step A4 - Freeze reporting and memory estimation contracts [DESIGN]

**Goal:** Define output and accounting that describe the plan and actual work truthfully, including failures and corrections.

**Inputs:** S4-05, S4-08, S4-11–17; A1–A3; current CLI output/redaction, `StageResult`/`PipelineResult`, logging/configuration tests, and the required examples in §8.

**Actions**

1. Define event/result schemas and their owners: discovery, initial classification/admission, planned route/bypass, stage start and actual result, provider-work observation, image finalization, state diagnostics, cancellation, and command summary. Keep planning facts immutable and primary outcomes separate from optional state diagnostics.
2. Define exact counting boundaries. An actual LLM-work image must be observed at the agreed inference boundary, not inferred from `completed`: an attempted request can fail, while a stage can skip before calling a provider. Distinguish stage evaluations, LLM transformation executions, provider retries if reported, image slots, corrective-overrun identities, and XMP evaluation versus write/no-change.
3. Define per-stage and overall plan-relative denominators, prospective bypasses, budget-excluded work, completed/failed/skipped outcomes, interruptions, and not-attempted work. Show progress when corrections add actual work and when the plan contains zero work. Final accounting must reconcile without calling 100% success or hiding unattempted records.
4. Freeze concise single-image compatibility, default batch summary, `--verbose` output, dry-run aggregate/per-file output, stdout/stderr/logging ownership, exit-code aggregation, and sanitized actionable errors. Keep outputs unambiguous for scripts; do not invent an unrelated output-format feature. Ensure logging configuration does not hide required state errors.
5. Select and document the mandatory dry-run memory-estimation method. Estimate the real plan/queues and tracking representation selected in A2, including retained paths/identities, per-stage references, deduplication structures and relevant overhead. State units, assumptions, included/excluded memory, runtime/interpreter dependence, and whether execution services/buffers are excluded. Avoid double-counting shared objects. Do not present a measurement or hard/peak bound.
6. Define aggregate/streamed dry-run operation without retaining every per-file record where feasible. Account honestly for retained sorting/identity data; do not promise constant memory without evidence. The real planner and dry-run use the same classification/admission logic. Predictions and estimates need not anticipate all external changes or corrective work.
7. Assign observable assertions for summaries, event ordering, redaction, partial results, no-work selections, 10,000-image routing, beyond-N and beyond-2N corrections, and the 997-success/3-failure rebuild example.

**Outputs:** Reporting/exit/counting tables, event ownership, sample outputs, memory-estimation method/scope, and accounting scenarios in [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md).

**Acceptance**

- [x] Initial admission, corrective images, actual distinct LLM-work images, stage evaluations/executions, retries, and writes cannot be confused in the documented output.
- [x] Progress and final summaries account for partial, failed, aborted, interrupted, and empty runs with defined channels and exits.
- [x] Every completed dry-run plan has a labeled estimate with a reproducible method, stated scope/assumptions, and no unsupported bound claim; an incomplete plan reports that the estimate is unavailable.
- [x] All output/access decisions needed by B6 and Phase M are resolved and cross-referenced before A5.

**Dependencies:** Reconciled inputs from A1–A3; may be drafted alongside them.

### Step A5 - Complete design and verify implementation readiness [DESIGN]

**Goal:** Close all significant design decisions and make both implementation phases executable without deferring product policy to coding.

**Inputs:** A1–A4 records; current governing documents; this plan's requirement, evidence, decision, risk, and allocation matrices; actual checkout and test layout.

**Actions**

1. Verify S4-01–18 and all 16 REQ acceptance outcomes have implementation/evidence owners. Confirm the additional failure boundaries in §6 are assigned.
2. Reconcile the selection, descriptor, admission, confirmation, queue, cancellation, state, management, output, and memory contracts together. Walk the fixed examples and difficult branches through concrete decisions; do not accept prose that still requires the coder to choose a significant policy.
3. Record each significant decision with outcome, rationale, acceptance scenario, owner, and approval reference when it is a new product-behavior decision. Reference existing decisions without requesting them again. Resolve genuine scope conflicts with the Product Owner.
4. Replace provisional module/interface/test paths in the dependent steps with chosen names. Confirm contracts for every CODE step, test coordination, dependency direction, actual command support, and evidence ownership. No feature implementation is performed by this readiness step.
5. Audit the decision ledger for unresolved significant TBDs, contradictory defaults, hidden migrations/content reads, implicit prerequisite expansion, duplicated completion logic, or acceptance that fabricates recovery success. If any remain, Phase A is incomplete and implementation cannot advance.
6. Synchronize plan/phase status and document genuine exceptions with approval. Readiness follows normal orchestration; it does not create a second REQ acceptance gate or apply retroactively to previous slices.
7. Resolve the A2 transport review: compare the concrete per-request subprocess baseline with cancellable `httpx.AsyncClient`, including cooperative versus forcible cancellation, actor/event-loop ownership, provider behavior and privacy, deterministic testability, and Windows-by-design implications. Select and justify one, record acceptance scenarios and reconcile all affected A2/A5/B3–B5/C2 contracts before closing Phase A; no significant transport decision may be deferred to implementation.
8. Apply the Product Owner decision: use Python stdlib `sqlite3` on normal Linux/Windows installations for logical data/schema read-only list, with ordinary SQLite journal/WAL/shared-memory and OS access-time effects allowed. List never initializes, migrates, repairs or changes application data/schema; report inaccessible, corrupt or migration-required state. Do not add a custom VFS, bundled SQLite, C extension, detached snapshot or custom packaging. Reconcile portable best-effort repository replacement detection without requiring optional filesystem identity, and reconcile the target, transaction/migration and sidecar decisions before Phase A closes.

**Outputs:** [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md), with the complete decision index, approvals where required, crosswalk/readiness findings, and updated plan references.

**Acceptance**

- [ ] A1–A4 agree, every significant design decision is resolved, and no significant TBD remains.
- [x] Required product decisions are approved; already decided behavior has not been reopened unnecessarily.
- [ ] Every implementation/evidence step has concrete inputs, observable outcomes, dependencies, and future completion-record links.
- [ ] Requirements, accepted examples, failure boundaries, and end-state allocation are covered without silent scope deferral.
- [ ] The orchestrator can advance to B1 using the completed design evidence, then follow the displayed step sequence.

**Dependencies:** A1–A4 are complete; A5 owns reconciliation of the later Product Owner SQLite decision and portable identity, without rewriting historical A3 work. A5 completion is mandatory before any B or M implementation.

### Phase B Batch implementation

**Entry:** A5 is complete and the next step is assigned. Use focused behavioral tests throughout implementation. Proposed file names must be confirmed in A5; existing files remain extension points rather than permission to replace unrelated logic.

### Step B1 - Extend configuration and command boundaries [CODE]

**Goal:** Implement the frozen controls and separate static resolution from execution-only startup.

**Inputs:** A1–A5; `cli.py`, `config.py`, `config_errors.py`; existing CLI/configuration/override tests; management grammar shared with M1/M2.

**Actions**

1. Extend defaults, known-key/type validation, path-origin handling, dedicated options and `--set` overrides for approved selection/depth/format/work/concurrency/dry-run/verbose controls, including invocation-only process/rebuild `-i` / `--ignore-case`. Preserve current singleton and conflicting-option behavior unless A1 explicitly changes it.
2. Implement explicit-single versus batch contextual defaults without overriding YAML or CLI intent. Preserve model/prompt/schema and state-directory precedence, selected-stage ordering, and missing-prerequisite overrides.
3. Separate metadata-only configuration/startup from execution dependency probes. Ensure dry-run does not construct/open state, run recovery, invoke ExifTool, or call models; real execution still validates all selected stages before any stage writes.
4. Provide the shared management configuration boundary defined by A3 without routing management through image-processing preflight. Keep unselected provider/XMP configuration from blocking unrelated category operations under the frozen contract.
5. Exercise valid/invalid values, null/unlimited forms, aliases if approved, repeated flags, unrelated stage isolation, sanitized errors, and old single-image syntax. Do not advertise unfinished execution as successful.

**Outputs:** Configuration/CLI boundaries and focused tests; [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md).

**Acceptance**

- [ ] Every approved setting is usable through its designed YAML/CLI forms with tested precedence and diagnostics.
- [ ] Process/rebuild/macro depth settings are independent; nonpositive work limits and other invalid controls fail as designed.
- [ ] Batch-default skip does not override explicit missing-prerequisite policy.
- [ ] Dry-run and management startup avoid execution-only side effects; real selected-stage preflight and existing CLI behavior remain covered.

**Dependencies:** A5.

### Step B2 - Implement reusable deterministic discovery [CODE]

**Goal:** Supply deterministic reusable selection for image processing and category rebuild without stage or state effects.

**Inputs:** A1/A3 selection contracts; B1 resolved controls; existing explicit-image path/symlink tests; proposed discovery module and test paths fixed by A5.

**Actions**

1. Implement native file/directory/pattern selection, deterministic roots/files/subdirectories, files-before-descent, configured extension eligibility and overrides, and unlimited/0/1/N depth. Implement case-sensitive native patterns by default and `-i` / `--ignore-case` for process and rebuild using A1's defined Unicode/bracket behavior without changing literal-first or identity. Test dotfiles, shell-expanded arguments, quoted patterns, pattern anchors, Unicode, brackets, distinct case-variant files and both commands. Explicitly test the six initial default extension candidates `jpg`, `jpeg`, `png`, `webp`, `tif`, `tiff` (including relevant case variants), distinguishing **discovery eligibility** from actual model/adapter decoding support and recording any selected-adapter failure as such.
2. Implement explicit/discovered symlink distinctions throughout enumeration and pattern handling. On symlink-capable systems exercise cycles, outside-root links, broken links, image links, and explicit directory roots; record unsupported-platform skips honestly.
3. Deduplicate with the frozen image identity rules before admission and execution. Preserve deterministic first occurrence and selection provenance across overlaps and multiple roots; do not repeatedly traverse aliases contrary to the contract.
4. Expose reusable traversal/selection primitives with separate image and JSON-sidecar eligibility. Apply rebuild's independently resolved depth without importing stage/LLM/XMP/state-storage logic.
5. Implement designed no-match, empty, missing/unreadable, and enumeration-error outcomes; a mixed invalid selection aborts before writes. Use synthetic directory trees and metadata-access spies to prove no image/sidecar content reads or mutations. B6/C1 verify empty-run startup and preflight at the integrated CLI boundary.
6. Implement the A1 cross-platform path contract using portable Python APIs and no Bash dependency; parse Windows drive/UNC and both native separator forms before wildcard components. Exercise pure Windows path interpretation on Linux and real Linux traversal separately, including platform-specific identity, ordering, case, encoding and symlink boundaries; do not label pure-path checks as Windows runtime validation. Review affected subprocess and filesystem operations for portability without expanding into unrelated platform remediation.

**Outputs:** Reusable discovery/identity implementation, synthetic traversal tests, and [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md).

**Acceptance**

- [ ] Repeated unchanged selections yield the documented order and deduplicated identities across files, roots, and patterns.
- [ ] Depth and symlink behavior match A1/A3, including independent rebuild controls.
- [ ] The default candidate set visibly covers `jpg`, `jpeg`, `png`, `webp`, `tif` and `tiff`, subject to documented adapter support; configuration/CLI overrides work without claiming eligible extensions are decodable.
- [ ] Discovery handles empty/errors as designed and performs no stage, state, or content operations.
- [ ] Portable design and host-independent Windows drive/UNC/separator parsing tests, plus real Linux traversal, cover the A1 platform contract without claiming unperformed Windows runtime verification.

**Dependencies:** B1 and completed A1/A3 contracts.

### Step B3 - Implement stage capabilities and metadata planning [CODE]

**Goal:** Build the complete initial plan and reusable stage-decision boundaries without changing authoritative stage behavior.

**Inputs:** A2/A4 descriptor/admission/representation contracts; B1/B2; `pipeline.py`, stage implementations, artifact naming/validation contracts, and existing stage/skip tests.

**Actions**

1. Extend the fixed ordered registry with the approved generic capabilities and stage-owned metadata predictors. Preserve existing stable stage identifiers and ordering. No XMP-name special case belongs in budgeting or routing.
2. Extract or adapt shared output/configuration decision logic as designed. Keep metadata prediction free of `ArtifactService.recover`, content validation, and execution effects. Reuse the authoritative branch in existing single-image stages; preserve JSON skip-before-prerequisite and current validity semantics.
3. Build the initial plan before any execution, retaining distinct identity, immutable admission class, selected stages, predicted bypasses/routes, and accounting inputs. Respect regeneration and omitted stages. Deduplicate before spending slots.
4. Admit the first N initially LLM-needy images once each; keep initial-no-work and known-excluded classes distinct. Do not refill after runtime skip or stop scanning at the budget boundary. Route excluded images toward selected non-LLM work generically.
5. Support aggregate/streamed planning for dry-run using the same predicates, with memory-estimation inputs from A4. Do not fabricate actual results or state changes while constructing predictions.
6. Exercise all metadata combinations, selected subsets, regeneration, overlaps, no limit, N=1, no-LLM selections, initial queue counts and the 10,000-image example. Add guards against image/sidecar-content reads, state opening, artifact writes, provider use and ExifTool during planning.

**Outputs:** Stage capabilities/shared decision seams, initial plan/admission/routing implementation, planner tests, and [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md).

**Acceptance**

- [ ] Planning is complete before execution and respects the metadata-only boundary on success and failure paths.
- [ ] Initial admission counts distinct images, honors deterministic order/regeneration, and does not suppress selected non-LLM eligibility after N.
- [ ] Stage subsets never expand implicitly; XMP-only planning consumes no LLM slots.
- [ ] Existing authoritative stage skip/recovery behavior remains correct after shared-logic extraction.
- [ ] Required queue-count examples and generic-capability tests pass without using predictions as stage-success evidence.

**Dependencies:** B2; A2/A4 contracts.

### Step B4 - Implement per-image execution and state lifecycle [CODE]

**Goal:** Execute the frozen plan in sequential image-first mode with authoritative results, correct admission enforcement, and per-image state.

**Inputs:** B3; A2/A3 execution/finalization contracts; `run_pipeline`, real stages, `StateService`, `accumulate_categories`, prompt expansion, and existing state/timing/CLI tests.

**Actions**

1. Implement the shared image lifecycle and sequential executor using actual stage functions and the frozen admission/validation protocol. Confirm predicted bypasses, apply permitted correction, and enforce known-excluded inference boundaries without adding omitted stages.
2. Retain real recovery, missing-prerequisite, invalid-artifact, regeneration, stop/continue/abort, and safe-write behavior. Forward or terminate from authoritative outcomes; do not manufacture a completed stage for reporting convenience.
3. Resolve and retain state per image with CLI/YAML/CWD/image precedence. Implement the frozen memory/service lifetime, diagnostics and cleanup. Ordinary state failures remain visible/nonblocking and cannot cause writes to another persistent repository.
4. Perform eligible category accumulation exactly at the per-image finalization boundary from A3. Preserve enabled/disabled behavior, generated/valid-skipped JSON, later-stage failure, and interruption rules. The next sequential image begins only after this finalization.
5. Emit execution facts at the A4 boundaries, including failed inference attempts and corrected identities, without treating provider retries as extra admitted images. Keep initial plan facts unchanged.
6. Test missing/changed/recovered outputs after planning, valid JSON with missing description, invalid primary without regeneration, no replenishment, initially known exclusions, multi-collection state, and prior-image category visibility using authored prompt fixtures and local stubs.

**Outputs:** Shared image lifecycle, sequential plan execution, per-image state integration and focused tests; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md).

**Acceptance**

- [ ] Sequential mode completes one image's selected stages and eligible accumulation before the next starts.
- [ ] Rechecks/corrections/exclusions preserve the Phase A tables and existing stage policies; actual results override predictions only in actual reporting.
- [ ] State identity remains correct across collections and all precedence/fallback cases; no optional state error changes otherwise valid primary success.
- [ ] Generated and valid-skipped JSON contribute as designed; planning, unrelated skips and disabled accumulation do not.
- [ ] Existing single-image outcomes and persisted handoffs remain covered by relevant regressions.

**Dependencies:** B3; frozen A2/A3/A4 contracts. Phase M implementation is not a dependency.

### Step B5 - Implement concurrent stage coordination and shutdown [CODE]

**Goal:** Add default inter-stage overlap while retaining the sequential contracts and reliable stop behavior.

**Inputs:** B4; A2 worker/queue/cancellation protocol; A3 service ownership; actual provider/schema/ExifTool and safe-write boundaries; existing signal tests.

**Actions**

1. Implement the selected in-memory worker topology and queue lifecycle with one authoritative stage actor per selected stage and at most one transport-only provider child per actor. Seed initial routes only after planning completes; derive confirmations from masks, progressively forward actual outcomes and apply the same-image confirmation protocol.
2. Preserve early downstream progress for existing-output candidates while unrelated upstream inference is held. Handle corrective rerouting, known budget exclusions, worker exceptions, empty queues, termination, and exactly-once accounting without global upstream barriers or unbounded wait cycles.
3. Share the B4 image/state finalization logic without cross-image repository leakage or unsafe service closure. Concurrent prompt snapshots may reflect completion timing; do not add a taxonomy synchronization barrier.
4. Implement stop/abort signaling and cleanup from A2. Serialize result acceptance with stop; discard unaccepted late results and separately gate publication, draining already-admitted safe writes. Cancel/reap owned inference and unprotected schema/ExifTool subprocesses, preserve child privacy and produce real partial outcomes. Do not rely on the existing single shared `state.interruptible` flag across workers.
5. Wire the default-enabled control and disabled sequential executor. Exercise actual simultaneous stages using deterministic barriers, assert per-stage activity never exceeds one, and verify absence of prohibited same-image overlap.
6. Cover correction and failure while another stage is active, stage subsets, all-bypass/no-work plans, concurrent state use, shutdown during request construction, held response, provider parsing, result/stop races, read/write/finalization, and resumed invocation. Test local provider barriers without a live service; do not assume arbitrary in-process transport objects serialize to the child. Treat cross-process sidecar races according to existing limits.

**Outputs:** Concurrent executor and cancellation/resource ownership, deterministic worker tests, and [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md).

**Acceptance**

- [ ] Measured stage activity proves real overlap on different images and a maximum of one active worker per selected stage.
- [ ] Bypass candidates make downstream progress before unrelated upstream inference completes, without violating same-image validation/continuation.
- [ ] Disabling concurrency actually runs image-first, including eligible accumulation timing.
- [ ] Failures, aborts and signals cannot silently strand queues, start prohibited inference, or report unattempted work as completed.
- [ ] Held-provider and publication-barrier tests preserve cancellation, safe-write, cleanup and partial-result contracts.

**Dependencies:** B4.

### Step B6 - Integrate dry-run progress and actual metrics [CODE]

**Goal:** Deliver working CLI planning/execution and truthful summaries across single-image and batch invocations.

**Inputs:** B1–B5; A4 reporting/exit/memory contracts; existing concise CLI/logging/redaction behavior; proposed reporter and CLI tests fixed in A5.

**Actions**

1. Integrate the completed planner/executors into `process`, retaining existing single-image syntax and concise output. Implement `--verbose` for single/batch with image/stage identity, reasons, timing, plan-relative progress and end-of-run summaries.
2. Implement dry-run from the common planning path without initializing execution services. Provide an observable **file-level work-budget report** identifying in deterministic discovery order each initially admitted LLM-work image, each known budget-excluded LLM-work image, and each initially no-LLM-work image, including the exact file where the allowance is exhausted. Aggregate-only presentation may also be supported but must not replace access to the required file-level information. Report admission/bypass/route counts and the mandatory labeled plan/queue memory estimate.
3. Consume execution facts for actual distinct LLM-work identities, distinct corrective-overrun identities, per-stage evaluation/execution/outcome counts, deviations and elapsed time. Do not count planned work as performed, infer inference solely from success, or confuse XMP evaluation with an XMP write.
4. Implement partial/failed/aborted/interrupted/not-attempted accounting, zero-denominator behavior, summary exit codes, channel separation and redaction. Keep optional state errors visible and independent of otherwise valid processing exits.
5. Exercise true CLI startup, invalid configuration, unavailable execution prerequisites, empty/no-work selections, dry-run versus real-plan parity, correction growth, failures, signal summaries, logging settings, secret sentinels and escaped unusual filenames.
6. Validate estimator arithmetic and representation assumptions from A4 with synthetic plan shapes; record scope and approximation limits. Verify the aggregate route does not retain unnecessary per-file output records. This is not a promise of bounded peak process memory.

**Outputs:** Native `process` integration, dry-run/verbose/reporter/estimator implementation and CLI tests; [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md).

**Acceptance**

- [ ] Single-image compatibility and default concurrent batch behavior are reachable through the actual CLI.
- [ ] Dry-run obeys content/execution/mutation boundaries even during startup/failure; each completed plan reports the required labeled estimate, and an incomplete plan reports that the estimate is unavailable.
- [ ] Actual CLI dry-run identifies admitted, initially no-work, and known budget-excluded file paths in deterministic order and marks precisely where N is reached; aggregate totals alone cannot satisfy this check.
- [ ] Initial and actual image/stage metrics reconcile for successes, skips, failures, corrections, interruption and no-work cases.
- [ ] Progress and exits follow A4 without claiming success from 100% accounted progress.
- [ ] Diagnostics are useful, sanitized, channel-correct and compatible with existing concise output.

**Dependencies:** B5; B1–B4 delivered contracts.

### Phase M Category management

**Entry:** A5 is complete. This phase owns S4-15–17 as a separate capability; it is required for Slice 4 and must not be deferred because batch work is larger. M1 depends on B1's shared controls; M2 also reuses B2 discovery. These commands do not invoke the batch executor.

### Step M1 - Implement strict category list and clear [CODE]

**Goal:** Give users reliable inspection and removal of known categories without side effects outside the requested operation.

**Inputs:** A1/A3/A4 management contracts; B1; `cli.py`, `state/resolution.py`, `state/storage.py`, `state/categories.py`; existing state storage/security/migration/CLI tests.

**Actions**

1. Implement management repository selection and strict errors, including no-store, invalid/inaccessible store and unsupported/migration-required cases. Preserve explicit selection; do not use ordinary `StateService` fallback to make a failed operation appear successful.
2. Implement logical data/schema read-only open/validation and category listing with stdlib `sqlite3`, without initialization, migration, repair, application data/schema mutation or provider/XMP activity. Normal SQLite journal/WAL/shared-memory and OS access-time effects are allowed; do not restore timestamps. Do not rely on a read method on the existing migration-capable writable constructor.
3. Extend category/storage interfaces for category-only clear with short transaction, contention and stop behavior. A registered required migration and clear occur atomically in the same transaction; preserve unrelated domains, source images and sidecars, and schema except for the registered migration. Failure/rollback must not be reported as successful clear.
4. Wire actual list/clear CLI grammar, useful output and exact exit/channel behavior from A4. Clear must support explicit noninteractive usage under the accepted command contract.
5. Test unchanged application data and schema around successful and failed list, including migration-needed fixtures; permit normal journal/WAL/shared-memory and access-time effects rather than asserting unchanged database bytes or directory contents. Test clear preservation, transactional migration and rollback, empty categories, failed update/commit, stop boundaries and unchanged ordinary-processing fallback.
6. Exercise stdlib SQLite read-only listing with rollback-journal and WAL fixtures, including concurrent access and clear errors when SQLite cannot read safely; test ordinary installation without custom SQLite packaging. Do not claim unperformed Windows runtime results.

**Outputs:** Strict access/list/clear interfaces and commands, focused tests, and [IMPL-M1-COMPLETED.md](IMPL-M1-COMPLETED.md).

**Acceptance**

- [ ] List is logically data/schema read-only throughout opening/validation/reporting, including migration-needed and inaccessible-store cases; normal SQLite and OS read effects are allowed.
- [ ] Missing or invalid persistent state cannot appear as an empty successful persistent listing.
- [ ] Clear removes categories only, with any registered migration in the same transaction, and reports transaction/access failures accurately without another persistent destination or memory substitution.
- [ ] Dedicated command behavior and ordinary optional-processing state behavior remain distinct and tested.

**Dependencies:** A5, B1. M1 does not depend on B3–B6.

### Step M2 - Implement additive category rebuild [CODE]

**Goal:** Accumulate categories from existing JSON using the current extraction rules, preserving previous state and successful partial work.

**Inputs:** A1/A3/A4; M1 strict target/access boundary; B2 discovery; `state/accumulation.py`, category/storage interfaces, injected envelope reader, and current accumulation tests.

**Actions**

1. Extract or extend the shared result-bearing JSON/category reader chosen in A3. Keep ordinary accumulation's accepted envelope/schema/candidate behavior, full path identity, deduplication, and state-to-stage dependency boundary intact.
2. Implement rebuild source selection with recursive default, independent depth and the approved symlink/duplicate/sidecar eligibility rules. Select and retain the single management target independently from source enumeration.
3. Add eligible categories to existing state in short transaction units. For a nonempty rebuild requiring a registered migration, perform migration and the first eligible update in the same transaction; on failure roll both back. Do not clear, replace, normalize, infer, invoke XMP, regenerate JSON, or hold a write lock across the scan. Empty/no-category results perform no migration or application data/schema mutation.
4. Continue past invalid/unreadable input; retain already committed valid contributions after partial failure or interruption. Handle storage failures according to A3 and expose them instead of silently falling back.
5. Report inspected/successful/no-category/skipped/failed inputs and category contributions using the defined counts, without attributing other writers' changes to this invocation. Preserve exact exit and interruption outcomes.
6. Test existing categories, duplicates, historical/custom schemas, missing candidates, invalid envelope/candidates, unreadable input, zero inputs, no-category-only scans, independent depth, explicit/discovered symlinks, partial success and interrupted accumulation. Verify migration plus first update commit/rollback atomically and no migration for empty/no-category rebuild. Include the 997-of-1,000 case.

**Outputs:** Additive rebuild command and shared extraction/reporting code with tests; [IMPL-M2-COMPLETED.md](IMPL-M2-COMPLETED.md).

**Acceptance**

- [ ] Rebuild retains existing categories and adds recognized full paths under current extraction rules, with no XMP/model/artifact mutation.
- [ ] Independent traversal and deduplication behave as A1/A3 specify; an empty result makes no changes.
- [ ] Invalid/unreadable inputs do not prevent eligible later inputs; valid partial additions remain and failures are visible.
- [ ] Interrupted/failed storage operations and counts are truthful; ordinary accumulation semantics and dependency direction remain intact.

**Dependencies:** M1, B2; completed A3/A4 contracts.

### Step M3 - Verify category command boundaries and concurrency [TEST]

**Goal:** Establish actual CLI and independent-process evidence for category commands and their interaction with ordinary processing.

**Inputs:** M1/M2; A3 management matrix; existing state concurrency, migration-fault, signal and post-primary timing tests; isolated synthetic repositories and authored sidecars.

**Actions**

1. Exercise real CLI list/clear/rebuild with CLI/YAML/CWD/source contexts and the frozen no-store outcomes. Verify logical data/schema read-only list and visible command failures without provider/ExifTool dependencies or application data/schema changes; allow normal SQLite journal/WAL/shared-memory and OS access-time effects.
2. Exercise clear preservation, explicit clear-then-rebuild, prior-category retention, supported/unsupported JSON, empty scans, partial results and the 997-success/3-failure example. Compare source/sidecar bytes and unrelated state domains.
3. Use independent OS processes and deterministic transaction barriers for list during mutation, concurrent additions, rebuild/rebuild, clear/rebuild, contention, and interruption around commit. Assert valid outcomes consistent with transaction order, not a deterministic final union in the presence of clear.
4. Verify ordinary image processing can read/update state during management within the existing storage contract, with no transaction held across inference or a whole rebuild. Preserve visible nonblocking processing failures and separate strict command exits.
5. Record actual commands/results and the difference between injected permission/migration failures, real subprocess behavior, and unperformed physical-failure tests.

**Outputs:** Category CLI/concurrency acceptance tests and evidence; [IMPL-M3-COMPLETED.md](IMPL-M3-COMPLETED.md).

**Acceptance**

- [ ] Actual CLI evidence covers list read-only/open failures, category-only clear, additive/empty/partial rebuild and selection contexts.
- [ ] Independent-process tests establish required sharing/transaction behavior and interruption retention without stronger whole-run guarantees.
- [ ] Command counts/exits and persistence match observable outcomes; failed state access never masquerades as success.
- [ ] Ordinary processing's nonblocking state and post-primary timing contracts remain covered.

**Dependencies:** M2; B1/B2 interfaces used by the commands.

### Step B7 - Document Slice 4 usage and compatibility [DOCS]

**Goal:** Document the delivered commands, planning limits, and operational expectations using verified behavior.

**Inputs:** B6 and M2 delivery records; A1–A4 examples; `README.md`, `examples/config.yaml`, parent REQ/HLD, and the acceptance examples in §8.

**Actions**

1. Update usage/help/configuration examples for files/directories/patterns, recursion/depth/symlinks, extensions, selected stages, work limits, concurrency opt-out, dry-run and verbose output using actual frozen grammar.
2. Explain distinct-image initial admission, no replenishment, permitted corrective overruns with no twice-N cap, known exclusions, uncapped non-LLM evaluation, and XMP evaluation versus publication. Include the progressive 10,000-image example and a correction example.
3. Document metadata-only prediction limits and required memory estimate scope; distinguish an LLM work allowance from file-count, request, runtime or memory caps.
4. Document per-image state precedence, concurrent versus sequential category timing, category list/clear/additive rebuild, independent rebuild depth, error/partial/empty behavior, and explicit clear-then-rebuild usage. Preserve ordinary nonblocking state versus strict management failures.
5. Document interruption/resume, continuation/abort, exits/channels, source safety, and existing sidecar race limitations. Reconcile current parent design/roadmap descriptions without rewriting prior completion records or claiming closeout prematurely.
6. Check all examples against implemented help/parser/config behavior with synthetic or dry-run fixtures where appropriate. Record privacy review of changed public artifacts.

**Outputs:** Updated current usage/configuration/design documentation and example checks; [IMPL-B7-COMPLETED.md](IMPL-B7-COMPLETED.md).

**Acceptance**

- [ ] Documented options and examples match implemented behavior and current defaults.
- [ ] Admission, correction, non-LLM routing, memory-estimate and category-rebuild semantics are explicit and accurate.
- [ ] Current parent docs distinguish implementation progress from acceptance; historical Slice 1–3 records remain intact.
- [ ] Public examples contain fictitious data and no sensitive infrastructure identifiers or credentials.

**Correction:** B7 is sequenced after M3 to eliminate the B7-before-M2 forward dependency identified in A5. The M3 category-verification step completes before B7 documents the verified behavior; B6 and M2 remain structural inputs. Final acceptance evidence is reconciled in C4.

**Dependencies:** B6 + M2 + M3. B7 documentation follows verified category behavior; it is sequenced after M3 to respect the linear orchestration contract.

### Phase C Verification and closeout

**Entry:** Batch implementation and category verification have reached their declared acceptance. These steps integrate and reconcile evidence; they do not defer basic behavior testing until the end. Correct any discovered defect within the authorized step boundary or obtain a disposition for an actual scope change.

### Step C1 - Verify batch behavior through the CLI [TEST]

**Goal:** Prove the complete native workflow, including plan versus execution, using the real CLI and stage boundaries.

**Inputs:** B6, M3; A1–A4 tables; §6 acceptance crosswalk; synthetic collections, authored prompts/JSON and local controlled HTTP providers; real ExifTool for applicable XMP integration.

**Actions**

1. Exercise actual single-image, directory, pattern and overlapping-root invocations, selected subsets, the six default extension candidates and depth/extension overrides, discovered/explicit symlinks and contextual prerequisite defaults. Distinguish discovery eligibility from actual adapter decoding. Check deterministic admission independently from concurrent completion order.
2. Measure stage overlap and per-stage maximum activity using deterministic barriers. Hold upstream inference while ready downstream candidates progress; verify the same-image protocol and compare with actual image-first mode.
3. Verify distinct-image budgets, regeneration, no slot replenishment, known exclusions, XMP-only uncapped evaluation, the 10,000-image progressive example, and permitted runtime corrections beyond N and 2N. Use real stage decisions for missing/invalid/recovered cases rather than fabricated success results.
4. Verify state identity across multiple collections in both execution modes, explicit/CWD sharing, memory/fallback behavior, generated/skipped JSON accumulation, prior-image prompt visibility in sequential mode, and accepted concurrent timing.
5. Compare dry-run predictions to the real run's initial plan on unchanged fixtures. With a small deterministic multi-root selection and allowance N, assert **specific file identities and order** in dry-run's admitted, initially no-work, and known budget-excluded groups, including the boundary file where N is reached; ensure aggregate-only reporting, when provided, does not remove that observable detail. Verify estimates and no-content/no-execution/no-mutation boundaries through startup and failure. Check default/verbose outputs, channels, redaction, exact file/stage accounting and XMP writes versus evaluations.
6. Use scalable synthetic discovery/queue fixtures for the 10,000 case and assert 10,000 actual entries into the selected XMP evaluation boundary, not only predicted routes; use provider-free controlled collaborators and preserve real result/prerequisite decisions. Separately exercise representative real CLI/stage/XMP integration. Record each evidence boundary; a scheduler fixture alone does not prove all XMP mappings or 10,000 writes.

**Outputs:** Integrated acceptance tests and actual E01–E12/E17–E19 evidence from §6; [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md).

**Acceptance**

- [ ] Real CLI evidence establishes native selection/planning/execution, actual overlap/sequential behavior and stage subsets.
- [ ] Budget/correction/routing examples reconcile distinct image and stage counts without treating XMP evaluation as guaranteed publication.
- [ ] State identity, accumulation timing, dry-run boundaries, verbose output and estimates have observable evidence.
- [ ] Every covered acceptance row identifies commands, assertions, versions and limitations rather than inferring success from unit mocks.

**Dependencies:** B6, M3.

### Step C2 - Verify failure interruption and resume boundaries [TEST]

**Goal:** Prove that failure and stopping preserve valid work, produce truthful summaries, and permit rescan-based resume.

**Inputs:** C1; A2/A3/A4 failure/cancellation contracts; §7 tables; existing signal/write/recovery/state-fault tests and deterministic local provider/subprocess barriers.

**Actions**

1. Exercise missing prerequisites, invalid primary outputs, valid/invalid backups, changed/deleted/recreated sidecars between plan and execution, known budget exclusions, and optional state faults. Explicitly test **all three required failure policies** (continue next stage, stop current image, abort batch), including the **default stop-current-image** path: fail an early stage for image A, give its downstream selected stage valid persisted input, and include another eligible image B. Assert which later stage runs on A, whether B starts, and the final stage/file/exit accounting under each choice.
2. Send SIGINT and SIGTERM to actual CLI subprocesses during discovery/planning, held inference in different stages, sidecar preparation/publication, XMP work, queued work, and state finalization. Verify cleanup, safe-write boundaries, stop propagation and no new dispatch after stop under A2.
3. Exercise worker exceptions and cancellation with downstream work queued or blocked. Verify terminal accounting for completed, failed, skipped, budget-excluded, interrupted and not-attempted work; no deadlock, silent omission or fabricated completion.
4. Invoke a fresh run on the resulting synthetic collection. Confirm valid prior outputs are reused, unfinished work remains eligible under the new plan, and no durable queue/database is needed. Preserve ordinary invalid-artifact policy; retry is not permission to regenerate invalid output automatically.
5. Recheck independent-process sidecar race tests and SQLite tests within their separate guarantees. Record complete-valid-output/recovery behavior without asserting a winning sidecar writer or atomic state-plus-sidecar commits.

**Outputs:** Failure/signal/resume and partial-reporting evidence, including E10/E13/E18/E20; [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md).

**Acceptance**

- [ ] All three HLD failure-continuation policies, including the stop-current-image default, are distinguished through actual two-image CLI behavior with usable downstream persisted input and accurate per-image/batch results.
- [ ] Real-process SIGINT/SIGTERM, failure/abort and worker-exception cases preserve valid publications and clean up owned work.
- [ ] Rechecks distinguish recovery, valid skip, permitted correction, invalid failure and missing-prerequisite policy.
- [ ] Final counts/exits describe partial execution accurately; a later invocation resumes by scanning sidecars.
- [ ] No stronger sidecar serialization or storage durability guarantee is claimed than the observed/inherited contract.

**Dependencies:** C1, M3.

### Step C3 - Run regression packaging and quality checks [TEST]

**Goal:** Establish fresh regression and packaging evidence at the actual delivered version and audit changed production boundaries.

**Inputs:** B7, M3, C1, C2; §9 commands; prior Slice 3 C2/C3 records as command/evidence examples, not current passes.

**Actions**

1. Run the appropriate focused regressions and full locked Linux suites on Python 3.13 and minimum-supported 3.12 with ExifTool available for applicable tests. Record interpreter/application/ExifTool versions, commands, passes, failures and skips; required blocked checks remain unchecked without an approved exception.
2. Run lock consistency, lint, format and distribution build. Install the resulting wheel with normal dependencies into an isolated environment outside the checkout, with source-path injection removed. Verify version/help, packaged prompt/schema resources, native dry-run/selection, synthetic processing and category commands. **Invoke the retained `search` stub**, not only `search --help`, and assert its existing not-implemented diagnostic and exit code `3` without a provider call. Use local stubs for other applicable processing; no live model calls.
3. Preserve prompt-fixture independence: check new tests do not freeze editable production prompt wording and exercise a disposable prompt-edit regression where affected by integration. Verify existing schema/provenance, selected-stage, XMP isolation, state, source-byte and artifact safety behavior.
4. Audit replaced code reachability and imports; remove confirmed orphans within scope, reconcile obsolete glob-rejection/single-image-only tests, and record any approved retention. Check dependency direction/cycles for changed modules, including state extraction and XMP's model/prompt isolation.
5. Check public-artifact privacy within a recorded scope, relative documentation links, example grammar, step labels and status consistency. Confirm per-delivery version synchronization; do not relabel earlier results with a later package version.

**Outputs:** Fresh quality/package/regression evidence and bounded cleanup/privacy findings; [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md).

**Acceptance**

- [ ] Required full/focused suites, lint/format, lock and build checks have recorded outcomes at stated versions.
- [ ] Installed-wheel CLI/resources/batch/category smoke checks pass outside the checkout, including the provider-free search stub's not-implemented diagnostic and exit `3`, or have an explicit approved exception.
- [ ] Existing prompts/schema/stages/state/XMP/source/safety contracts remain supported by regression evidence.
- [ ] Reachability/import/privacy audits have explicit scope, findings and disposition; no unrecorded orphan exception remains.
- [ ] Documentation/status/version references match actual evidence, including limitations and unperformed checks.

**Dependencies:** B7, M3, C1, C2 (B7 completed after M3).

### Step C4 - Reconcile evidence and close Slice 4 [DOCS]

**Goal:** Reconcile every requirement and acceptance outcome and record Slice 4's actual completion boundary.

**Inputs:** All step completion records; current parent/slice documents; §§5–11 of this plan; actual implementation and verification results.

**Actions**

1. Complete the requirement/acceptance crosswalk with concrete tests, commands, versions, outcomes and evidence limits. Close no row solely because its implementation step exists.
2. Reconcile summary/detail checkboxes, phase/overall status, design decisions, approvals, deviations and in-scope deferrals. Unmet acceptance remains visible; only an explicit Product Owner disposition can change required scope.
3. Reconcile parent REQ/HLD roadmap and current usage with actual delivery. Preserve historical Slice 1–3 acceptance and keep remaining end-state capabilities allocated without inventing future slice numbering or commitments.
4. Record test-order policy, actual limitations, manual/unperformed checks, packaging/runtime versions and any approved exceptions. Distinguish functional closeout from commit/push/release state.
5. If C4 delivers repository changes, perform **C4's own patch-version synchronization** under the established delivery convention: update `pyproject.toml`, `uv.lock` and affected exact-version assertions, then run and record focused lock-consistency, CLI `--version`, and affected version-assertion tests **after those edits**. Record the final delivered version explicitly. Preserve C3's actual full-suite/build/wheel-tested version and do not claim those checks were rerun against C4's later version unless they actually were.

**Outputs:** Reconciled plan/parent status and [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md).

**Acceptance**

- [ ] S4-01–18 and all required acceptance outcomes have supporting evidence or an explicit approved disposition.
- [ ] Phase/overall status and deviations reflect observed results; no significant design decision or acceptance gap is silently carried forward.
- [ ] Current documentation and remaining parent allocation are accurate; prior-slice records retain their historical meaning.
- [ ] Final C4 version/lock/CLI and affected version-assertion checks have actual post-change outcomes; C3's earlier packaging and regression results retain their tested version without attribution to C4's later delivery.
- [ ] Orchestration can close Slice 4 based on the recorded outcome without an extra REQ acceptance or test-order gate.

**Dependencies:** C3 and all preceding required step evidence.

## 5. Requirements to steps

Each S4 requirement has a design owner, delivery owner and observable evidence. C4 reconciles every row; it does not substitute for its tests.

| Requirement | Design | Implementation | Verification and evidence |
| --- | --- | --- | --- |
| S4-01 Multi-image selection and traversal | A1 | B1, B2, B6 | E01/E02/E17; traversal and actual CLI selection/depth/format cases |
| S4-02 Symlink boundaries | A1, A3 | B2, M2 | E01/E02/E15/E17; explicit versus discovered links, cycles and aliases |
| S4-03 Independent traversal controls | A1, A3 | B1, B2, M2 | E01/E15; process/rebuild/macro-depth independence |
| S4-04 Stage capability metadata | A2 | B3 | E03/E04/E05; generic descriptors and regeneration, no XMP-name budget exception |
| S4-05 Metadata-only initial plan | A1, A2, A4 | B3, B6 | E03/E11/E19; access guards and plan-before-worker ordering |
| S4-06 Front-loaded bypass and routing | A2 | B3–B5 | E04/E05/E07/E18; initial routes and real progressive forwarding |
| S4-07 Authoritative execution | A2, A3 | B3–B5 | E06/E08/E10/E18; recovery, changes, actual results and skipped-JSON side effects |
| S4-08 Initial LLM-work admission | A1, A2, A4 | B1, B3–B6 | E05/E06/E12/E18; distinct identities, exclusions, no refill, corrections and fixed examples |
| S4-09 Default optional concurrency | A1, A2 | B1, B4, B5 | E07; actual overlap/worker bound and sequential image-first execution |
| S4-10 Category timing and per-image state | A2, A3 | B4, B5 | E08/E09; post-image finalization, prompt snapshots, independent collections and fallback |
| S4-11 Stop resume and failure handling | A1, A2, A4 | B1, B4–B6 | E10/E13/E20; prerequisite defaults, continuation, signals, worker errors and resumed CLI |
| S4-12 Dry-run | A1, A2, A4 | B3, B6 | E03/E11/E19; parity, estimate and startup/failure access boundaries |
| S4-13 Verbose single and batch execution | A4 | B6, B7 | E02/E12/E20; identity/timing/reasons/channels and concise compatibility |
| S4-14 Batch summary and metrics | A2, A4 | B3–B6 | E05/E06/E12/E20; planned/actual distinct-image and per-stage counts |
| S4-15 List categories | A1, A3, A4 | M1 | E14, M3; genuinely read-only open/list and strict failure/migration outcomes |
| S4-16 Clear categories | A3, A4 | M1 | E14, M3; category-only transaction, failure/stop/concurrent preservation |
| S4-17 Additive JSON rebuild | A1, A3, A4 | B2, M2 | E15, M3; existing extraction, prior data, independent depth, empty/partial/interrupted/concurrent cases |
| S4-18 Preserve Slice 1–3 behavior | A1–A5 | All affected CODE steps | E02/E08–E10/E14–E16; C3 regressions/package/import checks and truthful test evidence |

## 6. Acceptance to evidence

E01–E16 map in order to the 16 required acceptance rows in the Slice 4 REQ. E17–E20 make cross-cutting edge cases explicit. All evidence is **Not run** at plan drafting; replace status only with observed step evidence.

| ID | REQ acceptance area | Required observable evidence | Evidence owners | Initial status |
| --- | --- | --- | --- | --- |
| E01 | Discovery | Synthetic tree and CLI demonstrate deterministic files-before-descent, recursion, depth 0/1/N/unlimited, **the six initial default extension candidates** and overrides, patterns, and no discovered-symlink following; adapter decoding support remains separately qualified. | B1, B2, C1 | Not run |
| E02 | Single-image compatibility | Existing syntax, explicit image symlink, stage subsets/order, overrides, default prerequisite failure, outputs/exits, source bytes and concise output remain correct; verbose adds the approved detail. | B1, B4, B6, C1, C3 | Not run |
| E03 | Planning | Known sidecar arrangements produce correct predicted classifications/routes before any worker starts; metadata/content/mutation guards prove the planning boundary. | B3, B6, C1 | Not run |
| E04 | Queue bypass | With unrelated upstream inference held, confirmed existing-output candidates reach downstream work. Same-image invalidation/correction obeys A2; omitted stages are never invoked. | B4, B5, C1 | Not run |
| E05 | Work budget | Deterministic distinct-image initial admission, regeneration, one slot for multiple LLM stages, no refill, continued known exclusion, uncapped XMP-only work and the 10,000-image progressive example. | B3–B6, C1 | Not run |
| E06 | Corrective overruns | Initially no-work images with disappeared outputs execute permitted corrections despite full admission; real invalid-artifact cases retain ordinary failure. Actual distinct identities exceed N and 2N in controlled cases; known exclusions never infer. | B4–B6, C1, C2 | Not run |
| E07 | Concurrency | Barrier-controlled real activity proves different stages overlap on different images, at most one active worker per selected stage, no forbidden same-image execution, and actual sequential image-first mode when disabled. | B5, C1 | Not run |
| E08 | Category timing | Generated/valid-skipped JSON accumulates once after selected stages under current eligibility, with no inference for a confirmed skip. Disabled/dry-run paths do not accumulate; next sequential image sees prior eligible categories. | B4, B5, C1, M3 | Not run |
| E09 | Per-image state resolution | Multi-collection CLI invocations exercise dedicated/generic CLI, YAML, CWD, each image ancestry and memory; retained identity, explicit sharing, visible nonblocking failures and no persistent substitution hold in both modes. | B4, B5, C1 | Not run |
| E10 | Rechecks and failures | Missing/invalid/changed/recovered sidecars, missing prerequisites, existing JSON before prerequisite check, and failure continuation use real stage outcomes and never publish failed generation. | B3–B5, C1, C2 | Not run |
| E11 | Dry-run | Actual CLI produces matching initial plan/counts, a labeled memory estimate, and deterministic **per-file admitted/no-work/excluded identities and allowance-exhaustion boundary** (not merely correct totals); no stages, inference, ExifTool, image/sidecar-content reads, accumulation or mutations. Aggregate-only presentation remains optional. | B1, B3, B6, C1 | Not run |
| E12 | Verbose and metrics | Per-image/stage starts/outcomes/timings and final counts reconcile planned bypasses, actual results, initial admission, corrective identities, actual LLM identities, retries if reported, deviations and elapsed time. 100% accounted is not reported as universal success. | B6, C1, C2 | Not run |
| E13 | Interruption/resume | Actual SIGINT/SIGTERM processes cancel held inference, preserve started safe writes, report unattempted/interrupted work and resume from valid sidecars in a fresh invocation. | B5, C2 | Not run |
| E14 | Categories list/clear | Actual commands cover logical data/schema preservation on list, with normal SQLite journal/WAL/shared-memory and OS access-time effects allowed, no-store/access/corruption/migration-needed failures, WAL/rollback-journal reads or clear errors if unsafe/unavailable, category-only clear with transactional registered migration, rollback/stop behavior and concurrent transactions. | M1, M3 | Not run |
| E15 | Categories rebuild | Existing categories retained; recognized JSON paths deduplicate; independent traversal; no XMP/inference; empty/no-category rebuild never migrates; registered migration and first eligible nonempty update commit or roll back together; invalid/unreadable/partial/interrupted/storage-failure/concurrent outcomes; 997/3 example and explicit clear-then-rebuild. | M2, M3 | Not run |
| E16 | Regression | Fresh relevant/full suites and installed package preserve stage/config/prompt/schema/state/XMP/source/artifact contracts; imports/reachability/privacy/version evidence is recorded at its real version. | All CODE steps, C3 | Not run |
| E17 | Selection identity and errors | Overlapping roots/patterns/explicit paths deduplicate by approved exact resolved-path spelling. Case-variant/other aliases retaining distinct spellings may process and consume allowance separately; hard-link names remain distinct. Test deterministic ordering, no-match/unreadable selections and invalid controls without claiming physical-file deduplication. | B1, B2, C1 | Not run |
| E18 | Runtime admission boundaries | Table-driven cases distinguish all three initial classes across recovered/invalid/new/missing outputs, selected subsets, regeneration and continuation; no accidental refill or unbudgeted promotion of known exclusions. | B3–B5, C1, C2 | Not run |
| E19 | Startup and empty-run boundaries | Dry-run with selected XMP, unavailable execution dependencies, bad/old state, no-work/empty selections and startup errors preserves its access limits; estimate and zero-denominator behavior match A4. A valid empty real batch skips runtime-only preflight after static validation; nonempty execution retains it before writes. | B1, B6, C1 | Not run |
| E20 | Partial abort and worker failures | A two-image case with early-stage failure and valid downstream persisted data distinguishes continue-next-stage, default stop-current-image, and abort-batch; other work follows the selected policy. Abort, worker exception and signal cannot deadlock or hide outcomes. Exit and summary reconcile all terminal/not-attempted records. | B5, B6, C2 | Not run |

## 7. Phase A decision-table obligations

These tables identify required coverage and fixed constraints. They are **not completed Phase A design evidence**. A2/A3 must expand them into concrete transitions, result/reason/exit forms and acceptance scenarios, recording outcomes/rationale and required approvals before A5. A1 owns selection/identity tables; A4 owns counting/output/estimate tables.

### 7.1 Runtime prediction and execution

| Initial class or condition | Execution observation | Required constraint for the A2 decision |
| --- | --- | --- |
| Any selected skippable stage, no regeneration | Valid primary output remains | Preserve authoritative `output_exists` and eligible execution side effects; prediction alone is insufficient. |
| Admitted because metadata predicted work | Another process completes output first | Validate/skip under current rules; retain the original admitted slot and do not admit a replacement. |
| Initially no selected LLM work | Primary disappears, valid backup exists | Recover through the execution artifact service; a recovered valid output can skip without inference. Do not perform recovery in planning. |
| Initially no selected LLM work | Primary and backup are absent | Permit corrective inference for selected LLM stages if their prerequisites/policies permit; do not require spare initial admission. |
| Initially no selected LLM work | Invalid primary remains, regeneration off | Preserve current `invalid_artifact` failure and continuation. A valid backup does not automatically overwrite an existing invalid primary. |
| Output missing, backup invalid | Recovery cannot establish valid output | Preserve existing failed-recovery/invalid-artifact behavior and backup retention; do not fabricate successful correction. |
| Regeneration enabled | Existing output valid or invalid | Metadata prediction already classifies selected LLM work as needed; admission/exclusion applies. Preserve stage recovery/prerequisite rules. |
| Known budget-excluded image | Any selected LLM output condition | No selected LLM inference, including after external changes. Keep selected non-LLM eligibility under ordinary policies. |
| Known budget-excluded image with existing JSON | Confirmed valid JSON can supply categories | Define the actual-result/inspection path preserving applicable skip side effects without using the budget bypass as proof or enabling inference. |
| Any image with valid JSON but no description | JSON selected without regeneration | Preserve existing JSON skip before description prerequisite checking; do not introduce a new false failure. |
| Selected stage needs missing prerequisite | Explicit image versus batch context | Use the resolved fail/skip policy; preserve user override. Missing input is not output completion. |
| Earlier selected stage fails | Later stage could use persisted data | Apply approved stop-current-image, continue, or batch-abort policy; an earlier failure is not an invented universal dependency failure. |
| Predicted bypass becomes corrective work | Downstream route was seeded provisionally | Gate/revise same-image execution using the chosen protocol while unrelated images continue. Account for the correction exactly once. |
| Stage omitted | A prerequisite would otherwise be missing | Do not invoke the omitted stage, regardless of allowance or correction eligibility. |
| Stop or worker error | Pending/in-flight work exists | Follow the frozen cancellation/write/finalization transitions and report real partial outcomes; never mark every plan entry complete. |

### 7.2 State and category management

| Boundary | A3 must settle and verify |
| --- | --- |
| Multi-collection processing | Per-image selection/lifetime and explicit/CWD precedence; memory sharing and fallback ownership; no first-image repository promotion. |
| Ordinary selected-state failure | Visible sanitized diagnostics, no silent persistent substitution, preserved valid primary outcome, and exact fallback/update behavior. |
| List/clear with no image | Exact selection anchor, allowed overrides, absent-store behavior and actionable diagnostics. |
| Rebuild sources and destination | Supported source grammar/sidecar identity and a single consistently selected destination, independent from traversal of source collections. |
| List opening/validation | Logical data/schema read-only access using stdlib SQLite, existing schema/version checks, no migration/init/repair; normal SQLite journal/WAL/shared-memory and OS access-time effects allowed; report migration-required. |
| Management target error | No successful empty result or transient-memory mutation presented as persistent success; precise exit/reporting. |
| Clear success/failure/interruption | Category-only atomic transaction, including any registered required migration; preserved other domains, rollback/stop boundary, contention and visible failed mutation. |
| Rebuild valid categories or valid no-category input | Preserve current extractor acceptance, full-path identity and deduplication; classify successful inspection versus contribution distinctly. |
| Rebuild invalid/unreadable input | Report failure and continue eligible later inputs; retain prior categories and committed valid contributions. |
| Rebuild empty input/result | No application data/schema changes or implicit startup migrations; defer registered migration until the first eligible update of a nonempty rebuild, in the same transaction. |
| Rebuild update/commit failure or interruption | Retain committed contributions; report failed/unattempted inputs; do not claim rollback of the whole scan or replay failed writes silently. |
| Concurrent list/add/clear/rebuild | Use short existing storage transactions; outcomes depend on commit order. No whole-run lock, deterministic winner or guaranteed union across clear. |
| Counting concurrent additions | Distinguish successful inputs, eligible paths and actual inserts only if observed reliably; before/after totals alone cannot attribute another writer's work. |
| Skipped JSON finalization | Require real eligible JSON results/validation; preserve post-primary timing and disabled/interrupted rules. Planning never accumulates. |

## 8. Fixed examples and test expectations

### 8.1 Progressive routing for 10,000 images

Use `desc,json,xmp`, with 6,000 images having both description and JSON, 1,000 having only a description, and 3,000 having neither. Use valid synthetic outputs for the unchanged-artifact case. The required limited example orders discovery so 1,000 images needing both LLM stages are admitted first; another discovery order can yield a different admitted mix.

| Plan | Initial description route | Initial JSON route | Initial XMP route | Later progress |
| --- | --- | --- | --- | --- |
| No allowance | 3,000 | 1,000 | 6,000 | Completed/eligible upstream images progressively join downstream work. |
| `--max-work-files 1000` with 1,000 neither-output images admitted | 1,000 | 0 | 9,000 | Admitted images later run JSON and reach XMP; 3,000 initially known LLM-needy images remain excluded from LLM inference. |

The limited initial XMP route is 6,000 already-complete predictions plus the 1,000 description-only and 2,000 neither-output images excluded from LLM work. These are initial routing predictions, subject to the authoritative confirmation protocol. They do not mean XMP executes before necessary same-image checks.

If predicted existing outputs validate, admitted stages succeed, no earlier stage stops an image, and the run is neither aborted nor interrupted, all 10,000 reach XMP **evaluation**: 9,000 through their initial routes and 1,000 progressively. Earlier validation failures instead follow configured continuation and may stop an image. The 3,000 excluded images without JSON have their ordinary prerequisite outcomes; the other evaluations can write or return `no_change`. The admitted 1,000 can cause 1,000 description and 1,000 JSON LLM executions while consuming only 1,000 image slots. Do not assert 10,000 successful XMP writes.

### 8.2 Corrective work and the absence of a twice-N cap

- With 1,000 admitted images and one additional initially no-work image whose description disappears, a permitted description correction can yield 1,001 actual LLM-work images. If all admitted images execute both LLM stages and the extra image's JSON remains valid, the actual LLM executions are 1,001 description and 1,000 JSON. Report the extra identity separately from initial admission.
- For a compact beyond-2N fixture, set N=1, admit one image, and initially predict no LLM work for three other images. After planning, remove those three descriptions while retaining valid JSON and no recoverable backups. If ordinary stage policies permit all description calls, four distinct images receive LLM work—greater than 2N. Do not replenish admission or reinterpret those images as initially admitted.
- A valid backup can turn the same missing-primary case into recovery and skip, yielding no additional LLM-work image. An invalid existing primary without regeneration can fail instead. These outcomes require real stage/validator behavior in tests.
- Images initially known to need work but excluded from admission never enter the correction class merely because their files later change.

### 8.3 Other allowance cases

| Scenario | Required result |
| --- | --- |
| `xmp` only with 10,000 eligible images and N=1,000 | Zero initial LLM admission; all eligible XMP evaluations remain available under normal policies. |
| Both LLM stages selected for one admitted image | One slot, potentially two LLM stage executions and additional configured provider attempts. |
| Only `json` selected, description absent | No implicit `desc`; ordinary prerequisite result. Planning may still admit the image based on missing JSON. |
| An admitted image gains both outputs before execution | Authoritative skips; initial admission remains unchanged and no replacement image is admitted. |
| `--regenerate` with existing selected LLM outputs | Initially count as potential work; apply admission/exclusion normally. |
| Overlapping paths select one identity repeatedly | One plan identity/admission under A1, with no duplicate stage scheduling. |

### 8.4 Category management

Begin with existing categories and 1,000 selected JSON inputs, of which 997 are successfully processed and three are invalid or unreadable. Rebuild retains the starting categories and adds eligible full paths from the 997 successful inputs. Report the three failures and distinguish successful inputs with no categories from category-bearing inputs. Rerunning deduplicates; an empty result does not clear or otherwise mutate the repository.

Explicit clear followed by rebuild permits reconstruction as two separate commands. It is not a replacement transaction: concurrent additions or clear operations can affect the result according to the storage transaction order. List must not migrate a store in any of these cases.

## 9. Verification execution and evidence discipline

### 9.1 Existing tests and proposed additions

Extend existing contracts where the behavior already exists; add focused files for new boundaries only after A5 fixes their names. Candidate additions include discovery, planning/admission, executor, reporting/dry-run, and category-management unit/integration tests. These are proposed areas, not claims that such modules/tests currently exist.

| Boundary | Existing tests to extend or preserve |
| --- | --- |
| CLI/configuration/pipeline | `tests/unit/test_cli.py`, `test_cli_acceptance.py`, `test_cli_config_acceptance.py`, `test_config.py`, `test_slice3_config.py`, `test_config_diagnostics.py`, `test_pipeline.py`, `test_results.py` |
| Stage validity and recovery | `tests/unit/test_description_stage.py`, `test_structure_stage.py`, `test_slice2_structure.py`, `test_artifacts.py`, `test_recovery_invalid_backup.py`, `test_xmp_stage.py` |
| State resolution and errors | `tests/unit/test_state_resolution.py`, `test_b3_precedence_matrix.py`, `test_state_service.py`; `tests/integration/test_state_b3_primary.py`, `test_c1_state_faults.py` |
| Category extraction and timing | `tests/unit/test_state_accumulation.py`, `test_cli_state_accumulation.py`, `test_cli_state_interrupt.py`; `tests/integration/test_state_accumulation_cli.py`, `test_state_accumulation_timing.py` |
| State storage/concurrency/migration | `tests/unit/test_state_storage.py`, `test_state_security.py`, `test_state_init_races.py`, `test_state_migration_faults.py`; `tests/integration/test_c1_state_inference.py`, `test_state_accumulation_signals.py` |
| Prompt and dependency boundaries | `tests/unit/test_prompt_expansion.py`, `test_prompt_expansion_boundaries.py`, `test_prompt_expansion_security.py`, `test_config_error_imports.py`, `test_schema_dependency_boundaries.py`, `test_schema_extracted_units.py` |
| Real CLI/write/signal integration | `tests/integration/test_single_image_pipeline.py`, `test_c2_signal_safety.py`, `test_c2_write_safety.py`, `test_c2_xmp_safety.py`, `test_xmp_signal_b5.py`, `test_xmp_cli_b5.py` |

Use deterministic barriers/events at real execution/transaction/publication boundaries, not fragile sleeps or assertions based only on total duration. Distinguish metadata stubs used for large routing tests from real CLI/stage/provider-stub and ExifTool integration. Independent-process SQLite and signal claims require OS processes; threads alone do not establish them.

No selected live model or private photo is necessary. Interoperability observations from earlier slices retain their original attribution; a new automated XMP test is not proof of a new manual digiKam exercise.

### 9.2 Commands supported by the existing repository

These are planned verification commands, based on the manifest and prior recorded workflow. They have not been run by drafting this plan. Replace `<affected-test-paths>` with actual existing/new test paths chosen in A5 and record the exact expanded command.

| Check | Command or established procedure |
| --- | --- |
| Lock consistency | `uv lock --locked` |
| Focused development harness | `uv run --locked --extra dev --python 3.13 pytest -q <affected-test-paths>` |
| Full development-runtime suite | `uv run --locked --extra dev --python 3.13 pytest -q` |
| Minimum-supported-runtime suite | `uv run --locked --extra dev --python 3.12 pytest -q` |
| Lint | `uv run --locked --extra dev --python 3.13 ruff check .` |
| Format | `uv run --locked --extra dev --python 3.13 ruff format --check .` |
| Distribution build | `uv build --python 3.13` |
| Version and existing help | `uv run --locked --python 3.13 image-clarus --version`; top-level, `process`, `init` and `search` help |
| Existing search stub behavior | Invoke `image-clarus search` in the installed CLI without a provider; assert the retained not-implemented diagnostic and exit status `3` |
| New help and command smoke | Exact category and new process invocations frozen in A1/A3, exercised with disposable synthetic fixtures |
| Installed distribution | Follow the isolated installed-wheel procedure in Slice 3 C2, outside the checkout and without source-path injection; record actual install/runtime/resource/command checks |

Use separate isolated locked environments as necessary to establish each interpreter version accurately. Record unavailable runtimes or ExifTool, skipped tests and failures; do not convert missing prerequisites into a claimed pass. Repeat or broaden verification to resolve a concrete risk or satisfy a required gate, not to manufacture test volume.

Historical Slice 3 C3 records full suites at earlier versions and focused checks at `0.3.3`; it does not establish a full-suite or installed-wheel pass at this plan's baseline. Each step and C3 must state the actual tested version. C4 must repeat focused lock/CLI/version-assertion checks after its own version-bearing delivery and record the final version. Earlier C3 full-suite/build/wheel results are not evidence at that final version unless actually rerun.

### 9.3 Public artifacts and cleanup

Record a bounded review of changed public code, tests, docs and fixtures for secrets, identifying image metadata and internal infrastructure values. Use fictitious replacements without changing required preservation behavior for real user XMP. Check new imports/callers and the existing state-to-stage separation. Remove superseded production paths only after confirming reachability and supported contracts; record any explicitly approved orphan retention.

## 10. End-state requirements allocation

The parent REQ uses named areas rather than numbered requirements. This matrix allocates them without inventing IDs or treating every parent capability as a Slice 4 delivery. "Candidate later Release 1 delivery" means remaining work for later planning, not a committed slice, order, or release promise.

| Parent area | Slice 4 allocation | Remaining allocation and prerequisites | Evidence or limit |
| --- | --- | --- | --- |
| Runtime dependencies, packaging, license and version | Preserve Python 3.12+, development 3.13, uv/Hatch, version reporting, existing Apache-2.0 artifacts and selected-stage ExifTool isolation; design Slice 4 discovery for Linux and Windows. | Broader platform automation remains later work; Windows runtime execution and an exhaustive OS/filesystem matrix are not required. | C3 fresh runtime/package checks and B2 pure Windows path parsing on Linux; no unperformed Windows runtime claim. |
| Processing stages and artifacts | Preserve independent `desc`/`json`/`xmp`, registry order, persisted handoffs, source integrity and approved regeneration/update policies; add reusable capabilities. | Later extensions require their own stage/provider/schema design. | E02/E03/E10/E16. |
| Input selection and traversal | Deliver native files/directories/patterns, deterministic recursion, depth, formats, identity handling and symlink policy. | Later goals include exclusion filters and expanded decoder support; require selection/adapter design. | E01/E17; extension eligibility alone is not decoder support. |
| Batch planning and execution | Deliver metadata Option A, initial image admission, corrections, progressive routing, default optional concurrency and sequential mode. | Later goals include Option B, retaining Option A, and extra workers/model-aware scheduling if separately approved. | E03–E07/E18; no persistent queue or hard memory/runtime cap. |
| Stage dependencies and failures | Preserve prerequisite/continuation rules and deliver documented batch abort/partial aggregation within Slice 4 scope. | Broader category-specific retry/backoff policy is candidate later Release 1 planning, subject to cost and product decisions. | E10/E20; no unapproved retry expansion. |
| Providers and model controls | Preserve named providers/models, current transport, reasoning controls and selected-stage validation. | Broader generation parameters are candidate later Release 1 planning; other protocols/decoders remain later goals. | Existing provider regressions; concurrency adds no new protocol. |
| User-owned prompts and macros | Preserve both replaceable prompt inputs, safe namespaces, hierarchy formatting, secret exclusion and fixture independence. | Further macro/state consumers are later goals requiring explicit contracts. | E08/E09/E16; no hidden guidance injection or new prompt input. |
| Structured metadata and provenance | Preserve current envelopes, schema identities, optional prompt hash and custom-schema behavior. | New schema/search-field needs require separate design; no taxonomy normalization added here. | E10/E15/E16 and existing schema/resource tests. |
| Known categories and application state | Deliver per-image batch state and list/clear/additive JSON rebuild; preserve optional state, full paths, storage sharing and migrations where applicable. | Historical categories from other metadata/digiKam and additional state domains are later goals; JSON rebuild does not implement those imports. | E08/E09/E14/E15; read-only list never migrates. |
| XMP integration | Preserve current deterministic mapping, ownership roots, field policies and unrelated metadata; include native non-LLM batch evaluation. | Additional representations/backends are later goals with mapping/interoperability prerequisites. | Existing accepted history plus E05/E10/E16; no new digiKam acceptance condition. |
| Native deterministic search | Preserve the existing help-only stub; no search implementation in this slice. | Candidate later Release 1 delivery: matching/field-selection/output contracts and shared discovery. | Still unmet; external photo tools do not replace the native requirement. |
| Configuration and precedence | Add only required Slice 4 controls through existing precedence/validation and independent command contexts. | Optional split provider files and broader configuration features remain later goals. | E01/E02/E09/E14/E17/E19. |
| Logging and operational results | Deliver verbose, dry-run, mandatory estimate, progress and accurate batch/category summaries with preserved concise behavior. | Broader log destinations and operational controls remain candidate later Release 1 planning where not already implemented. | E11/E12/E14/E15/E20; verbose alone does not complete all parent logging goals. |
| External scheduling, stop and resume | Deliver native unattended runs, initial LLM allowance, coordinated stop and sidecar-rescan resume. | Time-window/other run controls are candidate later Release 1 planning when useful; external schedulers own timing. | E05/E13/E20; no internal scheduler. |
| Safe writes and concurrency | Reuse existing recovery/publication and lock-free sidecar limits; preserve separate short SQLite transactions. | Compatibility changes require demonstrated need; no new cross-process sidecar serialization or atomic state/sidecar transaction. | E10/E13–E16. |
| Semantic search and richer filters | No delivery. | Later goals; embeddings are explicitly outside Release 1 requirements. | No implied dependency on Slice 4 acceptance. |
| Delivery process and scope evolution | Deliver Phase A design closure, separate category phase, traceable evidence and forward parent reconciliation. | Later scopes/order remain subject to their own planning. | A5/C4; no retroactive prior-slice gate or invented acceptance. |

## 11. Risks decision ownership and deviations

### 11.1 Risks and required resolution

| Risk | Consequence | Owner and required evidence |
| --- | --- | --- |
| Treating existence as successful validation | Premature downstream work, lost category side effects, wrong correction/skip counts. | A2 → B3–B5 → E04/E10/E18. |
| Incorrect admission identity or class changes | Duplicate spending, refill, or inference for known-excluded images. | A1/A2 → B2–B6 → E05/E06/E17/E18. |
| Reusing single-operation signal wrappers concurrently | Uncancelled requests, unsafe shutdown, stuck queues or wrong outcomes. | A2 → B5 → real-process C2 barriers. |
| Reusing execution preflight during dry-run | ExifTool calls, state migration or content reads before planning. | A1/A4 → B1/B6 → E11/E19. |
| Sharing mutable state services incorrectly | Cross-collection writes, broadened fallback, closed resources or stale guidance. | A3 → B4/B5 → E08/E09. |
| Reusing permissive processing state for management | Failed list appears empty; failed clear/rebuild appears successful. | A3 → M1–M3 → E14/E15. |
| Empty rebuild migrates on startup | A nominal no-change operation mutates persistent state. | A3 explicit access/migration decision → M2/M3. |
| Broadening extraction or skip validation | Previously supported artifacts stop skipping or contributing categories. | A2/A3 → B3/M2 → current envelope/extractor regressions. |
| Misleading progress or memory claims | Planned work looks completed, request counts become image counts, estimate appears a hard bound. | A4 → B6 → E12/E19/E20. |
| Large collections and long paths | Full execution plan/identity/sorting structures consume memory despite small LLM allowance. | A2/A4 representation and estimator; B3/B6 synthetic scaling checks; no invented fixed queue limit. |
| Concurrent clear/add/rebuild | Final category set depends on transaction order; whole-run replacement expectations would be wrong. | A3 → M3 independent-process evidence and B7 documentation (after M3). |

### 11.2 Design register and closure rule

| Decision area | Owner | Required completion |
| --- | --- | --- |
| Exact CLI/config grammar, roots/patterns, order, identity, invalid controls and contextual defaults | A1 | Concrete tables/examples and chosen interfaces before A5. |
| Descriptors, sidecar confirmation, admission/correction, routing, workers, continuation/abort and cancellation | A2 | Complete decision/transition tables and deterministic acceptance scenarios before A5. |
| Per-image memory/service lifetime, management selection/access, clear/rebuild/error/concurrency contracts | A3 | Concrete operation/outcome tables, extraction/lifecycle ownership and independent-process acceptance scenarios before A5. |
| Work observation, metrics/progress, output/channels/exits and memory estimate | A4 | Exact counting/output examples and estimation method/scope before A5. |
| Cross-contract reconciliation, product approvals, proposed paths and evidence ownership | A5 | No significant TBD, contradiction or unowned acceptance at Phase A close. |

This proposed plan assigns design work; it does not claim these decisions have already been made. A significant decision cannot be relabeled a routine coding choice to bypass Phase A. Conversely, choosing ordinary implementation details within a completed contract does not require another approval.

### 11.3 Missing inputs conflicts and assumptions

- **Missing repository inputs:** None required to draft this plan. Revalidate the checkout and any changes since the inspected commit when executing A1–A5.
- **Current governing-document conflicts:** None identified that prevents drafting. The REQ's allowance for corrective work remains qualified by existing stage policies; malformed existing output does not thereby acquire automatic-regeneration behavior.
- **Pending design choices:** Those explicitly assigned to A1–A4 above. New product-behavior outcomes need the required approval by A5; approved image-based admission, corrective overruns, per-image state, read-only list and additive rebuild are not reopened.
- **Assumptions:** No live provider or private-image access is needed. The established Linux/uv/Python test environment and optional ExifTool will be used during execution; availability and actual verification results remain to be recorded, not presumed.
- **Historical limitations:** Prior full-suite and package results retain their actual versions. Existing dependency-range/private-library-API concerns recorded in Slice 3 closeout are not silently converted into a new Slice 4 dependency-upgrade project; any observed blocker receives an explicit disposition.

### 11.4 Deviations and deferrals ledger

**Scope deviations:** None.

**In-scope deferrals:** None. Category management is required in Phase M, and the dry-run memory estimate is required in B6.

**Already excluded later work:** The items in §1.2 and §10 remain outside Slice 4; they are not newly discovered implementation exceptions.

If an exception is approved during execution, record the affected requirement, exact change, rationale, approval reference, owner, and carry-forward in this ledger and the affected completion record. Keep any remaining unchecked acceptance visible.

## 12. Completion boundary

Slice 4 is ready for orchestration closeout when native selection/planning/execution, initial LLM-work admission and permitted corrections, default optional inter-stage concurrency, sequential image-first mode, traversal controls, mandatory dry-run estimate, verbose/progress/actual metrics, and strict category list/clear/additive rebuild satisfy the REQ and this plan's evidence crosswalk without regressing accepted behavior.

Phase A must already have closed every significant design decision. Required execution and failure-boundary evidence must be present at the actual tested versions. Native search, content-aware Option B, multiple workers per stage, scheduling, new provider protocols and new manual digiKam interoperability are not Slice 4 completion conditions.

Plan drafting does not implement the slice, execute its tests, create completion records, change package versions, or establish final acceptance.
