# Slice 3 Implementation Plan

**Date:** 2026-11-19

**Status:** Phases A and B complete. Phase C is in progress: C1 and C2 are complete; C3 remains open. Cross-step acceptance evidence remains open until all assigned portions are verified.

**Governing REQ:** [REQ-slice-3.md](REQ-slice-3.md), accepted by the Product Owner.

**Goal:** Deliver fully user-owned model instructions and namespaced prompt macros, hierarchical preferred-category guidance, reusable application state with category accumulation, and explicitly opt-in `prompt_sha256`, while preserving independent single-image processing.

**Intended repository path:** `docs/slice-3/IMPL-PLAN-slice-3.md`

**Inspected baseline:** `image-clarus`, `main` at commit `357b6dcd809fc9ae0b5f8ed67679410dc39a8481`; package version `0.2.3`. Repository files were inspected for this draft. No application tests, builds, model calls, or implementation steps were executed.

**Authority:** [Parent REQ](../REQ-image-clarus.md) → [Parent HLD](../HLD-image-clarus.md) → [Slice 3 REQ](REQ-slice-3.md) → this plan → implementation. The [Slice 2 plan](../slice-2/IMPL-PLAN-slice-2.md) and [closeout](../slice-2/IMPL-C5-COMPLETED.md) establish accepted history and evidence limits.

**Orchestration:** The orchestrator assigns work and determines acceptance by advancing the process. Assignment establishes the governing requirements as ready and accepted for that step. Phase A includes a technical readiness check; it does not introduce another requirements-acceptance or routine Product Owner sign-off gate.

## Implementer and reviewer protocol

1. Execute only the assigned step, after its dependencies are satisfied. Resolve routine implementation mechanics within approved scope. Raise a real product-scope conflict rather than silently changing, narrowing, substituting, or deferring a requirement.
2. For every completed step, create `docs/slice-3/IMPL-<StepId>-COMPLETED.md` and link it in that step's Outputs. The links below identify planned outputs; the records do not exist merely because this plan names them. Do not create completion records while drafting the plan.
3. Each record includes the exact step heading and status; decisions and rationale; files created, updated, and removed; actual commands and results; blockers, limitations, and unchecked criteria; and `Scope deviations: None` or the specific approval reference, reason, owner, and carry-forward.
4. Reviewers read the completion record first, then examine the implementation and evidence supporting its acceptance rows. A record's existence is not proof that its criteria passed.
5. Keep summary checkboxes, detailed acceptance, completion records, phase status, requirement mappings, and overall status consistent. Check only work supported by actual evidence. Orchestration advancement records acceptance; it does not turn an unexecuted test into a pass.
6. CODE steps follow focused test → observed RED → implementation → observed GREEN → relevant regression. Record commands and the expected reason for failure. Supplemental tests against existing behavior may start GREEN; describe them honestly. If the required test-first sequence cannot be demonstrated, record the exception for orchestration disposition rather than inventing evidence.
7. Preserve existing patterns and production consumers. For each replaced path, audit remaining callers, tests, resources, and exports. Remove confirmed orphaned production code and obsolete tests or fixtures. Retaining a confirmed orphan requires the established explicit Product Owner exception, documented purpose, and an adjacent code comment; tests or unsupported exports alone are not a retention reason.
8. Use synthetic inputs, independent prompt fixtures, controlled local provider stubs, and fictitious credentials and infrastructure identifiers in publishable work. Record actual privacy-scan scope. No live provider call or new digiKam manual acceptance exercise is required by this plan.
9. **The delivering step owns version synchronization.** For each assigned step (A1–A3, B1–B7, C1–C3) that delivers repository changes, apply the project's patch-version increment convention at that step's delivery boundary, not later in C2 or closeout. The same delivering step updates the authoritative `pyproject.toml` version, synchronizes `uv.lock`, updates affected exact-version assertions (including `tests/unit/test_cli.py` and `tests/unit/test_resources.py` where applicable), verifies those updates, and records them in its completion record. This applies to code, test, and documentation deliveries under the project convention. Do not preselect future versions or modify repository files merely because this plan is drafted.
10. Commits, pushes, and history changes are not acceptance gates or actions authorized by this plan.

## 1. Scope and inherited contracts

### 1.1 Included

- Both existing prompt inputs remain fully replaceable and support the same optional `config` and `state` macros. Move model-facing instructions and contextual framing out of hardcoded request construction and into the existing prompt texts.
- Generic per-macro hierarchy expansion under `prompt_expansion.macros`, including CLI overrides, delimiter, depth, and deduplication.
- Complete hierarchical preferred-category paths, retaining single-segment support and advisory meaning.
- General-purpose application state with separated location resolution, storage, and domains; SQLite persistence and an in-memory equivalent; category paths as the first domain.
- Explicit `image-clarus init`, the accepted state-selection precedence, independent-process sharing, schema evolution, migrations, and nonblocking state errors.
- Default-enabled JSON category accumulation after the selected stages finish, including valid existing JSON skipped by the selected JSON stage; configuration can disable accumulation.
- Default omission and explicit YAML/CLI enablement of the existing `prompt_sha256` field; compatible shared validation and XMP consumption.
- Focused implementation tests, acceptance evidence, regression checks, user documentation, packaging verification, and cleanup of superseded paths.

### 1.2 Excluded

Native batching, directory traversal, patterns, scheduling controls, native search, batch history, digiKam-specific integration, historical collection imports or state rebuilds, automatic taxonomy reconciliation, additional taxonomy model calls, new prompt-tracking features, new retry policies, additional XMP mappings, and changes to sidecar ownership or publication policies are outside Slice 3.

External scripts may benefit from state across single-image invocations. That benefit does not complete the independent native batch or native search requirements.

### 1.3 Fixed behavior carried into implementation

| Contract | Required treatment |
| --- | --- |
| Prompt ownership | Use the existing description and JSON prompt inputs only. A replacement may omit any macro or guidance without application code restoring it. |
| Built-in description | Preserve exactly `Fully describe and explain everything about this image.` |
| Built-in JSON | Include preferred categories through the configuration macro by default. The REQ does not require adding a known-state macro to the built-in prompt; test state access with an explicitly authored fixture prompt. |
| Expansion | Default delimiter `/`; omitted or `null` depth is unlimited; positive depth retains at most that many segments; zero yields `[]`; negative depth is invalid configuration; deduplicate truncated paths. Preserve source prompt, resolved configuration, and full stored state. |
| State precedence | Explicit CLI choice → selected YAML choice → nearest initialized CWD ancestor, including CWD → nearest initialized image-directory ancestor, including that directory → memory. Search the image ancestry only if CWD discovery finds none. |
| Initialization | Only `init` initializes a persistent repository. It creates `.image-clarus/` in CWD. Ordinary processing must not create a persistent repository accidentally. |
| State errors | Report visible, sanitized error output even when primary processing succeeds. State failures do not invalidate otherwise successful stages or sidecars, including failures of explicitly selected state. Never silently choose a different persistent repository. |
| Accumulation | Enabled by default, configurable off, and performed after selected-stage processing. With it enabled, selected JSON that skips an existing valid artifact contributes categories without another model call or regeneration. Disabling it prevents both generated-JSON and skipped-JSON accumulation. |
| JSON hash | When explicitly enabled, hash the existing raw prompt source bytes using the existing representation. Do not change the meaning to expanded request content or add another hash. |
| Other JSON fields | Preserve `provider_alias`, `model_alias`, `model_id`, `prompt_id`, `description_sha256`, and custom-schema SHA-based version identification. No automatic freshness regeneration is added. |
| Stage independence | Preserve `desc`, `json`, `xmp` registry order, selection, persisted handoffs, skip/regeneration rules, failure continuation, source-image integrity, and interruption semantics. |
| XMP | Preserve deterministic publication, current mappings, ownership roots, policies, unrelated metadata, and ExifTool optionality. XMP must not require inference, prompt expansion, or available state. |
| Concurrency | SQLite state sharing is separate from existing lock-free sidecar writes. Do not hold a state transaction during inference or promise serialized sidecar updates. |
| Historical acceptance | Slice 2 remains complete and accepted. This slice remedies its recorded prompt-control gap without rewriting earlier acceptance or claiming earlier tests ran again. |

## 2. Inspected implementation and planned boundaries

These are existing files and observed behavior at the stated baseline. Recheck changed files before execution; use each file's established interfaces rather than assuming ownership of the whole file.

| Concern | Existing paths and symbols | Implication for Slice 3 |
| --- | --- | --- |
| CLI and service construction | `src/image_clarus/cli.py`, `_main()` | Route `init` before the branch that assumes an image argument; integrate optional state and independent diagnostics into ordinary processing. |
| Config and overrides | `src/image_clarus/config.py`, `DEFAULTS`, `_validate_keys()`, `_validate_shape()`, `resolve_config()` | Extend defaults, validation, path handling, and overrides consistently. Preserve CLI > one selected YAML file > defaults and selected-stage validation. |
| Literal dotted macro keys | `resolve_config()` currently splits every dot in an override path | Freeze an unambiguous CLI form for keys such as `state.categories.known` inside `prompt_expansion.macros`; do not publish an example the parser cannot accept. |
| Hierarchy validation | `_valid_tag_segment()` is shared by preferred categories and XMP validation | Add appropriate full-path handling without weakening XMP root or individual-segment rules. JSON-stage validation must agree with config validation. |
| Stages and results | `pipeline.py::run_pipeline()`, `results.py::StageResult`, `PipelineResult.exit_code` | Keep state errors outside primary-stage failure aggregation. The coordinator must not gain JSON parsing or category policy. |
| Prompt use | `stages/description.py::run_description()`, `stages/structure.py::run_structure()` | Expand prompts at their read/use boundary while preserving create-only skipping. The JSON stage currently skips before reading its prompt or prerequisite description. |
| Request construction | `providers/openai_compatible.py::OpenAICompatible.structured()` | Remove hardcoded description/schema/category framing as required by prompt ownership. Retain necessary input data, protocol fields, and existing bounded validation feedback. |
| Shared envelope | `stages/structure.py` defines envelope validation; `stages/xmp.py` imports its helpers | Update all shared consumers for an optional hash. Avoid making XMP import or execute macro/state functionality as a side effect of validator reuse. |
| Category source | `schemas/image-structure.schema.json` uses `tag_candidates` arrays of path segments; the historical v1 schema does not | Freeze extraction and compatible custom-schema handling explicitly. Do not infer a new category-node versus leaf-tag rule. |
| Sidecar safety | `artifacts.py::ArtifactService`, existing XMP backend/stage | Reuse current publication and recovery contracts. State persistence does not join the sidecar transaction. |
| Resources and packaging | `resources.py`, `prompts/`, `schemas/`, `pyproject.toml` | Keep the two existing prompt inputs and four packaged prompt/schema resources. SQLite uses the standard-library backend selected in the HLD. |
| User documentation | `README.md`, `examples/config.yaml` | Document actual frozen options, precedence, defaults, error behavior, and single-image examples after implementation. |

**A1/A2-selected additions:** B2–B3 implemented the `state` package, storage, category, resolution and invocation-local service modules and their tests. B4 implemented `src/image_clarus/prompt_expansion.py` and its unit tests; B6 implemented `src/image_clarus/state/accumulation.py`. A1 retains the existing shared envelope helpers in `stages/structure.py` and specifies deferred/stage-local prompt imports to preserve XMP independence. A2 reconciles the per-invocation state service, snapshot and diagnostics with A1; A3 records the readiness clarifications. See [A1](IMPL-A1-COMPLETED.md), [A2](IMPL-A2-COMPLETED.md), [A3](IMPL-A3-COMPLETED.md), [B2](IMPL-B2-COMPLETED.md), [B3](IMPL-B3-COMPLETED.md), [B4](IMPL-B4-COMPLETED.md) and [B6](IMPL-B6-COMPLETED.md).

**Dependency direction:** CLI/orchestration supplies resolved configuration and shared services; stages use prompt expansion; prompt expansion reads a safe configuration view and state-domain values; state domains use storage; location resolution selects a backend independently. Provider adapters remain transport boundaries. JSON parsing/extraction stays in a metadata/domain component rather than the stage coordinator. Audit changed imports against the existing graph; do not turn this slice into a repository-wide rewrite of documented historical cycles.

## 3. Phase summary checklist

All headings below exactly match their corresponding detailed step headings.

### Phase A Discovery and contract freeze

- [x] Step A1 - Freeze configuration and prompt contracts [DESIGN]
- [x] Step A2 - Freeze state and accumulation contracts [DESIGN]
- [x] Step A3 - Verify implementation readiness [DESIGN]

### Phase B Implementation

- [x] Step B1 - Extend configuration and JSON hash compatibility [CODE]
- [x] Step B2 - Implement state storage and category operations [CODE]
- [x] Step B3 - Implement initialization and state resolution [CODE]
- [x] Step B4 - Implement safe namespaced macro expansion [CODE]
- [x] Step B5 - Integrate fully user-owned prompts [CODE]
- [x] Step B6 - Integrate category accumulation after processing [CODE]
- [x] Step B7 - Document Slice 3 usage and compatibility [DOCS]

### Phase C Verification and closeout

- [x] Step C1 - Verify requests persistence and state failure behavior [TEST]
- [x] Step C2 - Run regression packaging and quality checks [TEST]
- [ ] Step C3 - Reconcile evidence and close Slice 3 [DOCS]

## 4. Detailed steps

### Phase A Discovery and contract freeze

**Entry:** The Slice 3 REQ is accepted. The orchestrator assigns design work. Revalidate the inspected baseline if the checkout has advanced. Phase A produces design records and an executable handoff; production implementation begins in Phase B.

### Step A1 - Freeze configuration and prompt contracts [DESIGN]

**Goal:** Settle the precise configuration, macro, request, and JSON compatibility mechanics needed to implement S3-01 through S3-05 without changing their behavior.

**Inputs:** Parent REQ sections on configuration, prompts, and structured metadata; HLD §§4–5; Slice 3 S3-01–S3-05, S3-09, S3-11–S3-12; the existing CLI/config/provider/stage/resource paths in §2; `tests/unit/test_config.py`, `test_slice2_config.py`, `test_openai_compatible.py`, `test_structure_stage.py`, `test_slice2_structure.py`, `test_structure_resources.py`.

**Actions**

1. Recheck the revision and relevant symbols. Record current behavior separately from required changes, design choices, and accepted history.
2. Freeze names, types, defaults, and YAML/CLI forms for explicit state selection, accumulation enablement, and prompt-hash enablement. Preserve the REQ's `prompt_expansion.macros` shape. Specify an unambiguous override grammar for literal dotted macro keys, duplicate/conflicting overrides, and actionable sanitized errors using existing CLI conventions.
3. Preserve existing origin-based relative-path conventions where applicable: YAML paths are based on the selected config file; CLI paths on CWD. Keep state repository availability checks out of fatal primary-stage config preflight. Distinguish malformed configuration from optional state access failures; negative expansion depth remains invalid configuration.
4. Freeze hierarchy-path validation separately from XMP segment validation. Define handling of eligible array-valued macros and delimiter/depth transforms without changing source values or requiring a particular database representation.
5. Freeze macro grammar, literal/escape handling, lookup, serialization of supported values, and malformed/unknown-reference behavior. Specify unavailable-state handling that preserves S3-09. Define a secret-safe view of resolved configuration, including containing-object expansion and environment credential protection, without altering provider configuration.
6. Specify the actual request shapes for both stages. Account for all existing description/schema/category contextual framing, not just the category block. Move instructions into the existing prompt texts; retain required input data and schema/protocol payloads. Preserve provider reasoning, response validation, and retry behavior. Validation feedback may remain data; any instructional wording around it follows the same prompt-ownership rule.
7. Freeze optional-hash configuration and shared validation changes. Preserve raw prompt source-byte hashing when enabled, the other approved JSON fields, custom-schema versions, and existing skip behavior. Identify obsolete prompt/framing assertions and independent fixtures needed for replacements.
8. Record the selected module/test paths and interfaces, including whether shared validation needs a neutral location. Update affected plan references to those choices. No new prompt input or tracking feature enters the handoff.

**Outputs:** Configuration, macro, request, validation, and test contracts in [IMPL-A1-COMPLETED.md](IMPL-A1-COMPLETED.md); confirmed touchpoints and updated plan references.

**A1 result:** Configuration names and overrides, secret-safe macro and request contracts, optional-hash compatibility, selected paths, and planned evidence are frozen in the linked record. A2 reconciled state storage and lifecycle, and A3 records the subsequent readiness clarifications. This is design evidence, not implemented Slice 3 behavior.

**Acceptance**

- [x] A1 records exact YAML and CLI examples for all new settings, including usable per-macro overrides, defaults, types, and precedence.
- [x] A1 provides request examples for built-in and replacement prompts in both stages and identifies every hardcoded instruction path to remove.
- [x] A1 defines secret exclusion, source immutability, eligible-array behavior, and nonblocking unavailable-state expansion with observable tests.
- [x] A1 defines old/new envelope validation and source-byte hash behavior without changing the approved fields or skip contract.
- [x] A1 classifies actual conflicts and contains no unresolved implementation choice needed by B1 or B4; any scope change has an explicit Product Owner disposition.

**Dependencies:** Current accepted requirements and orchestrator assignment. A2 may proceed alongside A1, with their shared configuration and lifecycle contracts reconciled before A3.

### Step A2 - Freeze state and accumulation contracts [DESIGN]

**Goal:** Define the general-purpose state boundary, safe lifecycle, and post-image accumulation mechanics for S3-06–S3-10.

**Inputs:** HLD §§2–4.5 and 7; Slice 3 S3-06–S3-12; A1's configuration/macro contract as it becomes available; `cli.py`, `pipeline.py`, `results.py`, `stages/structure.py`, `stages/xmp.py`, both metadata schemas; existing subprocess integration helpers.

**Actions**

1. Separate resolution, storage, and domain operations. Freeze backend/service interfaces and an in-memory implementation with the same domain-facing behavior. Limit production domains to categories; batch history remains a possible later consumer.
2. Define initialized-repository recognition, SQLite location and schema, domain evolution/version tracking, transactions, connection lifetime, migration dispatch, and failure reporting. Ensure normal processing opens existing state without an accidental database-create path.
3. Specify safe repeated/concurrent initialization, existing non-state content, partial initialization, unsupported versions, and failed migrations. Preserve existing state rather than deleting or replacing it to make initialization succeed.
4. Detail explicit-path meaning, relative paths, upward traversal termination, symlink handling, inaccessible candidates, nested repositories, and discovery/open failures under the fixed precedence. Distinguish no repository found from a selected repository failing; never silently route that failure to another persistent repository.
5. Define short transaction boundaries and bounded lock-contention handling. No state transaction spans model inference or primary sidecar work. Specify concurrent reads/updates and migration coordination without changing sidecar concurrency semantics.
6. Freeze category extraction from available valid structured metadata, including canonical segment arrays, historical artifacts, and supported custom schemas. Preserve complete hierarchy information, without an unapproved leaf/category exclusion or dependence on XMP selection, publication root, or tag limit.
7. Specify the post-selected-stage lifecycle owner and eligibility for generated JSON, `output_exists` skips, later-stage failure, missing prerequisites, interrupted/not-run stages, and accumulation disabled. Do not treat every kind of `skipped` as a reusable artifact. Preserve existing JSON completion decisions even if optional accumulation cannot read or validate metadata.
8. Define visible sanitized state diagnostics independently of `StageResult` and primary exit aggregation, including logging levels that would suppress ordinary log messages. Specify nonpersistent fallback and unavailable macro values. Preserve graceful interruption and never report a failed state update as successful.
9. Define deterministic test coordination for independent processes, held inference, post-stage timing, and migration/fault fixtures. A test migration can exercise the mechanism without inventing a speculative production migration or a second product domain.

**Outputs:** State, discovery, schema/migration, accumulation, diagnostics, and test contracts in [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md); confirmed implementation paths and dependency directions.

**A2 result:** The linked design freezes resolution, SQLite/memory interfaces and migrations, diagnostics, category extraction and post-stage eligibility. It reconciles the state snapshot and service lifetime with A1. A3 subsequently resolved technical readiness details; the design is not implemented.

**Acceptance**

- [x] A2 enumerates every state-precedence boundary and failure route, including explicit failures, and proves normal processing has no initialization path by design.
- [x] A2 specifies versioned SQLite/in-memory interfaces, non-destructive evolution, independent-process sharing, and transaction lifetimes.
- [x] A2 gives an extraction/eligibility table and a lifecycle sequence showing accumulation after selected stages, with both default-on and disabled behavior.
- [x] A2 defines observable state diagnostics that cannot change otherwise valid primary results or silently select another persistent repository.
- [x] A1/A2 agree on settings, safe macro values, service lifetime, and the tests required before implementation.

**Dependencies:** Current accepted requirements; final reconciliation with A1 before A3.

### Step A3 - Verify implementation readiness [DESIGN]

**Goal:** Make Phase B code-ready using the completed design records and accepted scope.

**Inputs:** A1 and A2 records; current parent/slice documents; this plan's requirement, acceptance, failure, and allocation matrices; actual checkout and test layout.

**Actions**

1. Verify all S3 requirements and all 14 S3-12 outcomes have implementation owners and observable evidence.
2. Check A1/A2 interfaces together: settings reach the right consumers; optional state never enters a fatal stage prerequisite; XMP remains independent; post-image work has one owner.
3. Replace provisional module/test references with the chosen paths where needed. Confirm each CODE step has frozen inputs, expected RED cases, dependencies, and bounded outputs.
4. Resolve technical contradictions and record any actual scope conflict with its disposition. Routine design choices stay with the assigned designers and reviewers.
5. Confirm the deviations ledger and evidence status. Record readiness through the orchestrator's normal advancement; do not request a second acceptance of the already accepted REQ.

**Outputs:** [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md), with the technical readiness findings and any unresolved blockers; updated plan cross-references.

**A3 result:** The linked record maps all requirements and acceptance outcomes, resolves the state-design readiness findings in A2, and identifies the B1–B6 handoff. Phase A technical readiness is complete; implementation still requires the orchestrator to assign the relevant step.

**Acceptance**

- [x] A1/A2 supply the exact contracts needed by B1–B6, and the crosswalk has no unowned acceptance outcome.
- [x] Shared services and dependencies are compatible; no unresolved design blocker is silently pushed into CODE work.
- [x] Summary/detail headings, output links, evidence IDs, and scope boundaries agree.
- [x] The readiness record supports orchestration advancing to Phase B without another REQ acceptance gate.

**Dependencies:** A1, A2.

### Phase B Implementation

**Entry:** A3 readiness is recorded and the orchestrator assigns the next step. Every CODE step follows the test-first protocol. Tests named below are existing extension points unless explicitly described as proposed; A1/A2 settle additions.

### Step B1 - Extend configuration and JSON hash compatibility [CODE]

**Goal:** Implement the approved settings, hierarchical preference validation, and backward-compatible optional JSON hash before new consumers depend on them.

**Inputs:** A1/A2 contracts; `config.py`, `cli.py`, `stages/structure.py`, `stages/xmp.py`; `tests/unit/test_config.py`, `test_slice2_config.py`, `test_config_diagnostics.py`, `test_structure_stage.py`, `test_slice2_structure.py`, `test_xmp_stage.py`; `tests/integration/test_c1_compatibility.py`.

**Actions**

1. Add failing focused tests for settings/defaults/overrides, full preferred-category paths, shared-validator compatibility, and default hash omission. Use independent prompt fixtures for exact text/hash assertions.
2. Extend defaults, known keys, type/shape validation, path origins, and CLI handling according to A1. Keep new state availability failures out of fatal configuration preflight and preserve unrelated selected-stage isolation.
3. Implement full preferred-path validation in config and JSON processing without relaxing XMP segment/root validation.
4. Make `prompt_sha256` optional in every shared-envelope consumer while retaining validation when present. Implement generation omission by default and explicit YAML/CLI enablement with the existing raw source-byte calculation.
5. Preserve the other approved envelope fields, schema-version behavior, existing JSON skip/regeneration, and XMP compatibility. If A1 chose a shared-validation relocation, move only the needed functionality and update genuine consumers.
6. Reconcile obsolete assertions and run affected configuration, JSON, XMP, and diagnostics regressions. Record RED/GREEN and any retained compatibility boundary.

**Outputs:** Implemented settings/validation/hash behavior; focused tests and cleaned affected references; [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md).

**Acceptance**

- [x] Tests demonstrate CLI > YAML > defaults for the new controls, including literal dotted macro keys and negative-depth rejection.
- [x] Single and hierarchical preferred paths pass; XMP segment/root validation and unrelated stage configuration remain unchanged.
- [x] Default generation omits the hash; explicit YAML/CLI enablement includes the expected fixture-source hash.
- [x] Shared validation and XMP accept old valid artifacts with the field and new valid artifacts without it, and reject an invalid present hash.
- [x] Tests preserve `prompt_id`, raw-description hashing, model identifiers, custom-schema hashing, and create-only/regeneration behavior.

**Dependencies:** A3.

### Step B2 - Implement state storage and category operations [CODE]

**Goal:** Supply the general-purpose state foundation independently of discovery and prompt consumers.

**Inputs:** A2 storage/domain/migration contracts; B1 settings interfaces; existing package layout; proposed state unit/process test files confirmed in A2.

**Actions**

1. Write failing tests for the backend/domain contract, memory lifetime, persistence, full category paths, deduplication, schema/version handling, and non-destructive failures.
2. Implement the selected interfaces with SQLite through `sqlite3` and the in-memory backend. Keep repository selection separate; category operations use the storage boundary rather than selecting folders themselves.
3. Implement initialization/open distinctions, short transactions, migration handling, concurrent access, and bounded contention behavior from A2. Normal open must not create absent persistent state.
4. Preserve complete category information independently of prompt formatting and depth. Do not add a second production domain, historical import command, or taxonomy inference.
5. Exercise reopen across independent processes, controlled concurrent updates, migration preservation, and injected storage errors. Clean up test processes and temporary state deterministically.

**Outputs:** State storage/domain implementation and tests; [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md).

**Acceptance**

- [x] Memory and SQLite implementations satisfy the A2 domain contract; a separate process reads persisted full hierarchy.
- [x] Independent concurrent processes access/update one store without corruption or loss attributable to the state transaction design in the tested scenario.
- [x] Migration/version tests preserve existing data; unsupported or failed operations do not destructively replace the repository.
- [x] Transaction lifetime and contention behavior match A2, with no model/stage dependency in storage.
- [x] Resolution, storage, and domain responsibilities remain separate, with no speculative state consumer.

**Dependencies:** B1; frozen A2 interfaces.

### Step B3 - Implement initialization and state resolution [CODE]

**Goal:** Expose intentional initialization and the fixed discovery order while keeping state optional during processing.

**Inputs:** A1/A2 contracts; B1 settings and B2 backends; `cli.py`, `config.py`, `pipeline.py`, `results.py`; existing CLI/config tests and the state-resolution tests selected in A2.

**Actions**

1. Add failing tests for `init`, no automatic creation, every precedence boundary, conflicting/nested locations, and invalid explicit selections.
2. Route `init` independently of the image-processing argument and provider/stage validation path. Apply A2's safe repeated/concurrent initialization behavior.
3. Integrate resolution and state service lifetime with single-image processing. Honor CLI/YAML choice, CWD ancestry, then image ancestry, then memory, with the path semantics frozen in Phase A.
4. Implement visible sanitized state diagnostics and the specified nonpersistent fallback. Do not insert a failed state result into primary stages or silently substitute another persistent repository.
5. Cover missing/corrupt/inaccessible/incompatible selected state and discovery/open failures. Test `init` failures separately from ordinary successful processing with a state error.
6. Preserve ordinary CLI help, version, process/search behavior, stage results, and primary exit aggregation.

**Outputs:** `init`, state selection/lifecycle integration, diagnostic handling, and focused CLI tests; [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md).

**Acceptance**

- [x] `init` initializes in CWD, and ordinary processing in an uninitialized tree leaves no persistent repository.
- [x] Table-driven tests cover the entire precedence order, nearest nested matches, unrelated-collection sharing, and CWD winning over a different image repository.
- [x] An invalid explicit selection emits a state error and does not update another persistent repository; otherwise valid primary work retains its outcome.
- [x] Diagnostics remain visible under supported logging-level settings and exclude synthetic secret values.
- [x] Existing CLI and selected-stage behavior remain supported; `init --help` is available without an image or configured model.

**Dependencies:** B1, B2.

### Step B4 - Implement safe namespaced macro expansion [CODE]

**Goal:** Implement reusable macro lookup and hierarchy transformation independently of stage request assembly.

**Inputs:** A1 macro/security contracts and A2 state view; B1 resolved settings; B2 state-domain interface; existing config/diagnostic test patterns; the macro unit tests selected in A1.

**Actions**

1. Write failing tests using independent prompt fixtures, both namespaces, eligible non-category arrays, nested configuration objects, and synthetic inline/environment credentials.
2. Implement the frozen grammar and value serialization over a safe resolved-config view and the state interface. Do not expose credentials by expanding a parent object or let sanitization alter provider configuration.
3. Implement per-macro delimiter/depth controls: default/unlimited, explicit `null`, positive depth, zero as `[]`, negative rejection, and deduplication after truncation. Apply them to eligible arrays in either namespace.
4. Verify expansion is a derived output: prompt source, resolved configuration, full hierarchy, and backend representation remain independent.
5. Implement malformed/unknown-reference and unavailable-state behavior exactly as frozen in A1/A2, with sanitized diagnostics and nonblocking state failure.
6. Run focused macro and config regressions before stage integration.

**Outputs:** Macro implementation and unit tests; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md).

**Acceptance**

- [x] Tests cover both namespaces and a non-category hierarchical-string array, demonstrating a generic mechanism.
- [x] Default, `null`, positive, zero, negative, delimiter, deduplication, and per-macro independence behave as specified.
- [x] Snapshot comparisons show no prompt/config/state mutation after expansion, including depth zero.
- [x] Direct, environment-resolved, and containing-object credential cases cannot expose secret values in expansions or diagnostics.
- [x] Unavailable state values use the frozen nonblocking behavior; no stage-specific prompt instruction is embedded in the engine.

**Dependencies:** B1, B2; B3 diagnostic/service contracts available for integration.

### Step B5 - Integrate fully user-owned prompts [CODE]

**Goal:** Apply the same macro engine to both existing prompt inputs and remove mandatory instructions from request-building code.

**Inputs:** A1 request contract; B1 hash compatibility, B3 services, B4 expansion; `stages/description.py`, `stages/structure.py`, `providers/openai_compatible.py`, `resources.py`, both prompt files; provider/stage/resource tests and captured-request integration helpers.

**Actions**

1. Add failing captured-request tests for built-in and replacement prompts in both stages and replacement prompts omitting category guidance. Explicitly cover all four prompt/namespace combinations with authored fixture prompts: description/config, description/state, JSON/config, and JSON/state.
2. Expand prompt snapshots immediately before use while preserving stage skip/preflight behavior and the original prompt bytes for explicitly enabled hashing.
3. Consolidate existing default instructional framing into the two prompt texts as A1 specifies. Preserve the exact built-in description text. Update the built-in JSON prompt to include preferred-category guidance through its configuration macro, removing the obsolete `when supplied separately` wording from `prompts/image-structure.txt` while retaining guidance that categories are optional, advisory, and not a closed taxonomy.
4. Remove the superseded mandatory category payload and hardcoded contextual instructions. Preserve required image/description/schema data, transport/protocol behavior, reasoning mapping, and bounded validation feedback.
5. Verify captured requests for each of the four stage/namespace combinations, including a macro-bearing fixture whose source hash differs from its expanded text. Verify built-in JSON requests at default depth, configured positive depth, and depth zero. Do not inject known-state context unless the authored prompt asks for it.
6. Update obsolete framing/category injection assertions; retain tests for real protocol and input-data contracts. Audit affected provider arguments and helpers for genuine remaining consumers.

**Outputs:** Integrated prompts, request assembly, updated built-in JSON prompt, fixture-based tests, and removal of superseded instruction paths; [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md).

**Acceptance**

- [x] Captured provider requests separately prove description/config, description/state, JSON/config, and JSON/state expansion through authored prompt fixtures; replacements can omit category guidance without automatic reinsertion.
- [x] At the default unlimited depth, the built-in JSON request includes complete configured preferred paths, including single-segment values. With a configured positive depth it uses truncated paths, and with depth zero it emits `[]`, as specified by the per-macro setting.
- [x] Product/resource inspection confirms the required description default, and confirms the built-in JSON prompt no longer says categories are `supplied separately` while preserving advisory, non-closed-taxonomy guidance; wording-dependent unit tests use fixtures instead of freezing production text.
- [x] Opt-in hash testing proves the stored hash remains the raw source-byte hash after expansion.
- [x] Required stage data, custom schema support, reasoning, bounded validation retries, independent stage selection, and prior sidecar behavior remain intact.

**Dependencies:** B1, B3, B4.

### Step B6 - Integrate category accumulation after processing [CODE]

**Goal:** Reuse JSON category hierarchies across invocations without making state part of primary-stage completion.

**Inputs:** A2 extraction/eligibility/lifecycle contract; B1–B5; `cli.py`, `pipeline.py`, `results.py`, shared metadata validation and category-domain code; existing pipeline and subprocess integration helpers.

**Actions**

1. Add failing tests for generated and `output_exists` JSON accumulation, default-on/off settings, post-selected-stage timing, and state-update failure with unchanged primary results.
2. Invoke the A2 post-image operation after selected-stage processing. Keep JSON parsing/extraction in the chosen domain/metadata component and keep the coordinator free of category policy.
3. Accumulate complete valid paths under the frozen extraction rules. Reuse a selected skipped JSON artifact without a provider request, sidecar regeneration, or changing its primary skip result.
4. Honor configuration disabling accumulation for both generated and skipped JSON. Do not apply prompt expansion depth to state capture.
5. Handle later-stage failure, unusable optional metadata, interruption, and other eligibility cases according to A2. Preserve already published artifacts and existing primary results if optional reading or state update fails.
6. Demonstrate a subsequent independent CLI invocation using the same repository and an explicit state-macro fixture. Include shared state across unrelated image directories.
7. Audit lifecycle ownership so updates occur once at the intended boundary, without sidecar/state transaction coupling or extra model calls.

**Outputs:** Post-image accumulation and independent-invocation tests; [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md).

**Acceptance**

- [x] An observer confirms accumulation occurs after selected stages finish, not between JSON and another selected stage.
- [x] Default-enabled successful JSON contributes complete paths; a later independent CLI invocation can expand them.
- [x] Existing valid selected JSON contributes without a request or changed artifact bytes; disabling accumulation prevents updates in both generated and skipped cases.
- [x] State-read/update failure emits a visible error while preserving primary results, exit behavior, and sidecars.
- [x] Eligibility tests distinguish `output_exists` from other skips/failures and retain the established JSON validation/skip contract.
- [x] Extraction is independent of prompt depth, XMP selection, XMP ownership root, and publication limit.

**Dependencies:** B1–B5.

### Step B7 - Document Slice 3 usage and compatibility [DOCS]

**Goal:** Explain the implemented controls with accurate, usable examples.

**Inputs:** A1/A2 frozen contracts; B1–B6 implementation/evidence; `README.md`, `examples/config.yaml`, current CLI help, parent/slice requirements and HLD.

**Actions**

1. Document `init`, explicit state selection, relative-path meanings, discovery precedence, memory-only operation, and state errors that accompany successful image processing.
2. Use synthetic collection layouts to explain nearest nested discovery, CWD winning over another image collection, and explicit shared state across unrelated collections.
3. Document user-owned prompts, both namespaces, secret exclusions, eligible arrays, delimiter/depth defaults, zero hiding context, per-macro CLI overrides, and unchanged full state capture.
4. Document accumulation timing, default enablement, disabling generated/skipped accumulation, and reuse of existing valid JSON without extra model calls.
5. Document optional prompt SHA, its source-byte meaning, preserved JSON fields, compatibility, and unchanged skip/regeneration behavior.
6. Keep examples single-image and invocation-neutral. Preserve the distinction between useful external scripts and future native batch/search. Update parent HLD implementation-status references only where needed to reflect completed work, without adding requirements or rewriting Slice 2 history.
7. Check each documented option/example against the implemented grammar and CLI help; report what was actually exercised.

**Outputs:** Updated user documentation, example configuration, and narrowly necessary architecture-status references; [IMPL-B7-COMPLETED.md](IMPL-B7-COMPLETED.md).

**Acceptance**

- [x] Documentation covers every delivered control and its default/precedence with syntax verified against the implementation.
- [x] Examples contain only synthetic data and no private guidance, credentials, infrastructure identifiers, or local development paths.
- [x] State and prompt limitations are accurate; no native batch, search, scheduler, taxonomy import, or model-quality claim is implied.
- [x] The plan and documentation agree with the frozen contracts and actual behavior.

**Dependencies:** B1–B6.

### Phase C Verification and closeout

**Entry:** Assigned implementation steps are complete with recorded focused evidence. Reuse valid evidence from earlier steps; extend or rerun checks where integration or a concrete remaining risk requires it.

### Step C1 - Verify requests persistence and state failure behavior [TEST]

**Goal:** Establish the Slice 3 acceptance outcomes through actual CLI requests, independent processes, and controlled fault scenarios.

**Inputs:** B1–B6 records and tests; §6 acceptance crosswalk and §7 failure matrix; existing `tests/integration/test_single_image_pipeline.py`, `test_c1_compatibility.py`, `test_config_diagnostics_cli.py`, `test_xmp_cli_b5.py`; focused state/macro integration tests selected in Phase A.

**Actions**

1. Capture outbound requests from real CLI subprocesses using controlled local provider stubs. Verify all four authored prompt/namespace combinations (description/config, description/state, JSON/config, JSON/state), replacement without category advice, secret exclusion, and opt-in hash. For the built-in JSON prompt, verify full paths at default unlimited depth and truncated/`[]` output at configured positive/zero depth.
2. Exercise fresh JSON and selected existing-JSON skips, accumulation enabled/disabled, post-selected-stage timing, a second independent invocation, and explicit cross-collection sharing.
3. Exercise the full discovery precedence and no-auto-creation matrix with conflicting/nested repositories and explicit selection failures.
4. Exercise state open/read/update/migration/permission/corruption/version/contention failures with expected visible diagnostics, successful otherwise-valid primary artifacts, and no persistent substitution.
5. Use independent OS processes and deterministic synchronization for concurrency. Hold a synthetic provider response while another process accesses/updates state to demonstrate that inference does not hold a state transaction.
6. Verify old/new JSON through shared validation and real XMP processing, plus XMP-only processing without inference, macro execution, or working state.
7. Adapt helpers that currently assume empty stderr only for scenarios expecting state diagnostics; retain ordinary no-error assertions. Record exact commands, cases, outcomes, and environment limits.

**Outputs:** Integrated acceptance evidence and any focused corrective tests; [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md).

**Acceptance**

- [x] The runtime outcomes assigned to C1 in §6 have passing observed evidence. C2-owned prompt-edit, regression, and package checks remain pending C2. Blocked or failed required C1 cases stay unchecked unless an explicitly approved exception is recorded.
- [x] Persistence/sharing evidence uses independent processes, not only object reuse or threads.
- [x] Failure scenarios demonstrate diagnostic visibility, primary-outcome independence, preserved sidecars, and no alternate persistent writes.
- [x] Concurrency/inference evidence proves the required state behavior without adding stronger sidecar-race guarantees.
- [x] Live provider calls, extra model-quality benchmarks, and new digiKam manual acceptance were not made prerequisites.

**Dependencies:** B1–B6; B7 examples available when used for verification.

### Step C2 - Run regression packaging and quality checks [TEST]

**Goal:** Verify the delivered slice against inherited processing, packaging, supported-runtime, and cleanup contracts.

**Inputs:** B1–B7 and C1 records; current manifest/lock/resources; existing unit/integration suites; [Slice 2 C4](../slice-2/IMPL-C4-COMPLETED.md) and [C5](../slice-2/IMPL-C5-COMPLETED.md) as historical conventions, not new passes.

**Actions**

1. Run the project commands in §8 on Linux with the development and minimum supported Python versions. Record actual output, environment, skips, failures, and limits.
2. Verify independent/subset stage selection, persisted handoffs, existing artifact skipping, explicit regeneration, source bytes, missing prerequisites, custom schema support, selected-stage provider/ExifTool optionality, signal behavior, and existing XMP policies/preservation.
3. In a disposable source copy, change production prompt wording and rerun unit checks that could have depended on it. Fixture-based text/hash tests must remain valid. Keep bundled-default product checks separate from unit tests that should tolerate wording changes.
4. Build/install the distribution in a separate environment and run outside the checkout with `PYTHONPATH` unset. Check version, top-level/process/search/init help, packaged prompt/schema resources, and synthetic processing/state usage. A source-tree import must not conceal a missing packaged resource.
5. Audit replaced instruction/category-injection paths, obsolete assertions/fixtures, new dependency directions, and new cycles. Preserve legitimate supported consumers; do not reopen unrelated historical architecture work.
6. Confirm each step that delivered repository changes performed its own delivery-boundary patch-version increment and synchronized `pyproject.toml`, `uv.lock`, and affected version assertions. C2 verifies those deliveries; it does not defer or take ownership of earlier steps' version updates or invent an additional release bump solely for closeout. Check documentation links, exact step headings, crosswalks, status markers, and requirement scope.
7. Scan the actual new/changed publishable files and recorded evidence for known private identifiers, credentials, and local paths. Report scope and findings rather than claiming exhaustive secrecy.

**Outputs:** Runtime, regression, package, dependency, cleanup, version, and privacy evidence; [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md).

**Acceptance**

- [x] Required Linux Python 3.13 and 3.12 suites, lint/format, lock consistency, and build checks pass, with actual outcomes and any skips recorded. Failed or blocked required checks remain unchecked unless an explicitly approved exception is recorded.
- [x] Installed CLI/resource/state checks pass outside the checkout. A blocker is recorded and leaves the affected criterion unchecked unless an explicitly approved exception is recorded.
- [x] Prompt wording changes do not break previously passing unit behavior that should use independent fixtures.
- [x] Inherited stage/XMP/source/safe-write/signal behavior is protected by relevant regression evidence.
- [x] The bounded cleanup/import audit identifies removed or retained paths and introduces no unrecorded exception.
- [x] Version references, document links, step labels, scope, and privacy-scan findings are reconciled.

**Dependencies:** B1–B7, C1.

### Step C3 - Reconcile evidence and close Slice 3 [DOCS]

**Goal:** Provide an accurate closeout for orchestration using the completed requirement and evidence crosswalks.

**Inputs:** A1–C2 completion records; current code and documentation; §§6–10; accepted Slice 3 REQ and parent documents.

**Actions**

1. Reconcile each S3 requirement and E01–E14 outcome with actual implementation and evidence. Distinguish automated results, any operator observations, design review, and remaining limits.
2. Record the delivered version and exact completion-record references. Preserve Slice 2 acceptance and identify its prompt-control gap as remedied only to the extent supported by Slice 3 evidence.
3. Reconcile every summary/detail/phase/status marker. Do not close incomplete criteria by restating a requirement or by the mere existence of a completion record.
4. Confirm no in-scope item was silently narrowed or deferred. Record any explicit exception in the ledger with its approval, reason, owner, and carry-forward.
5. Update current roadmap/status references to distinguish delivered Slice 3 behavior from still-planned native batch, search, and other later work. No future slice number, release date, or additional feature commitment is assigned.
6. Present completion evidence to orchestration and record its advancement/closeout decision in the normal process. Do not add a separate reacceptance form or duplicate Product Owner gate.

**Outputs:** [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md), completed evidence crosswalk, reconciled plan/status references, and final deviation/limitation record.

**Acceptance**

- [ ] Every in-scope requirement and acceptance outcome is supported by recorded evidence or an explicitly approved exception; nothing is silently deferred.
- [ ] Phase and overall status match actual evidence and the orchestrator's closeout decision.
- [ ] Historical acceptance remains intact, and remaining parent requirements are accurately allocated without new commitments.
- [ ] The deviations/deferrals ledger and evidence limitations are explicit and consistent.

**Dependencies:** C1, C2, all earlier assigned steps.

## 5. Requirements to steps

| Slice requirement | Design | Implementation | Verification and evidence |
| --- | --- | --- | --- |
| S3-01 Fully user-editable instructions | A1 | B5 | B5 request tests; C1 E01; C2 resource/regression checks |
| S3-02 Namespaced macros and generic expansion | A1, A2 | B1, B4, B5 | E02–E03; configuration and request tests |
| S3-03 Secret configuration protection | A1 | B4, B5 | E04; nested/inline/environment sentinels and diagnostics |
| S3-04 Optional prompt SHA and fixture independence | A1 | B1, B5 | E05–E07; C2 disposable prompt-edit and package checks |
| S3-05 Hierarchical preferred categories | A1 | B1, B5 | E08; full paths at default depth, configured truncation/zero, and replacement tests |
| S3-06 General-purpose state | A2 | B2, B3 | Backend/domain review, E09, E11, E13 |
| S3-07 Known category state and accumulation | A2 | B2, B6 | E09–E10; post-stage/default-on/off and second-process evidence |
| S3-08 Explicit initialization and precedence | A1, A2 | B1, B3 | E11; all precedence boundaries and no-auto-creation tests |
| S3-09 State must not inhibit processing | A1, A2 | B3–B6 | E12; failure matrix and primary result/sidecar comparisons |
| S3-10 State sharing and evolution | A2 | B2, B3, B6 | E13; independent processes, migrations, held-inference checks |
| S3-11 Preserve prior processing behavior | A1, A2 | B1–B6 | E14; C2 existing regression and installed-package evidence |
| S3-12 Required acceptance outcomes | A3 | B1–B7 | E01–E14 in C1/C2, reconciled by C3 |

## 6. Acceptance to evidence

The Expected evidence column specifies future proof, not completed verification. Completion records must name actual test cases, commands, and results.

| ID | S3-12 area | Expected observable evidence | Evidence owner | Initial status |
| --- | --- | --- | --- | --- |
| E01 | Full prompt replacement | Captured built-in/replacement requests show author-controlled instructions and no hidden mandatory framing; required data remains present. | B5, C1 | Not run |
| E02 | Namespaced macros | Captured requests separately verify description/config, description/state, JSON/config, and JSON/state with authored fixture prompts; omission does not inject category context. | B4, B5, C1 | Not run |
| E03 | Hierarchy expansion | Both namespaces and a non-category array cover delimiter/default/null/positive/zero/negative, deduplication, per-macro CLI precedence, and unchanged sources. | B1, B4, C1 | Not run |
| E04 | Secret safety | Inline/environment sentinels and containing-object references are absent from expanded requests and diagnostics; provider authentication still works through its normal channel. | B4, B5, C1 | Not run |
| E05 | Prompt edits and tests | Stable text/hash cases use fixtures; a disposable production-prompt wording change leaves relevant unit checks passing. | B1, B5, C2 | Not run |
| E06 | Optional prompt SHA | Default omission; YAML/CLI enablement; raw source-byte fixture hash despite expansion; old/new/invalid-present validator and XMP cases. | B1, B5, C1 | Not run |
| E07 | Preserved JSON fields | Assertions for approved identifiers, raw persisted-description hash, and custom-schema hash remain valid. | B1, C1, C2 | Not run |
| E08 | Hierarchical guidance | Captured built-in JSON requests contain complete single/multisegment paths at default unlimited depth; configured positive depth truncates them and zero yields `[]`; replacements can change or omit guidance. | B1, B5, C1 | Not run |
| E09 | Known categories | Default-on successful JSON accumulates after selected stages; a second CLI process expands persisted full paths; disabling accumulation prevents updates. | B6, C1 | Not run |
| E10 | Existing JSON accumulation | Selected JSON with valid existing output accumulates with zero provider calls and unchanged sidecar bytes; disabled setting prevents updates. | B6, C1 | Not run |
| E11 | Initialization and resolution | CLI tests show intentional init, no automatic repository creation, all precedence boundaries, nested/conflicting repositories, and explicit shared-state selection. | B3, C1 | Not run |
| E12 | Nonblocking state failures | Fault cases show visible state errors, unchanged otherwise-successful primary outcomes/artifacts, and no silent alternate persistent writes. | B3–B6, C1 | Not run |
| E13 | State concurrency and evolution | Independent-process read/update and reopen tests, migration preservation/failure fixtures, and another process accessing state during held inference. | B2, C1 | Not run |
| E14 | Regression | Existing stage order/selection, sidecar recovery, XMP policies, source integrity, compatibility, signals, and installed-package behavior remain covered. | B1–B6, C2 | Not run |

## 7. Failure and regression matrix

Use controlled fixtures and deterministic fault injection. Verify the relevant observable outcomes, not only that an exception was caught.

| Scenario | Primary processing expectation | State or diagnostic evidence |
| --- | --- | --- |
| No initialized repository anywhere in the required searches | Normal selected stages operate with memory state | No persistent files created; memory lifetime matches A2 |
| Missing or unusable explicit CLI/YAML state directory | Otherwise valid stages and sidecars complete | Visible state error; no implicit fallback to a different persistent repository |
| Corrupt or unsupported-version state | Ordinary processing retains its result | Error identifies the state problem; existing files are not destroyed |
| Discovery, open, read, update, or migration failure | Optional state does not become a fatal primary prerequisite | Injected boundary is identifiable; failed state operation is not reported successful |
| Repository locked by another process | Contention follows A2's bounded policy; no indefinite state wait gates processing | Concurrent success or visible nonblocking state failure, as the controlled case specifies |
| Failed or repeated initialization | `init` may fail independently | No destructive replacement of existing state; safe A2 behavior is observed |
| State macro unavailable during either model stage | Valid primary work can proceed under the frozen fallback | Visible sanitized state error and defined fallback expansion |
| Secret reference or containing-object expansion | Follow the frozen safe-reference behavior | No inline/environment secret in prompt or diagnostics |
| Negative expansion depth or malformed new setting | Existing configuration-error policy applies where relevant | Actionable sanitized key-specific error; distinguish it from optional repository failure |
| Selected JSON skips existing valid output | Preserve the existing skip result and artifact | When enabled, accumulate recognizable valid categories without regeneration or a model call |
| Metadata unusable only for optional accumulation | Do not retroactively fail or regenerate a skipped/successful primary stage | A2 extraction/diagnostic outcome; no fabricated category state |
| Accumulation disabled | Primary processing unchanged | No JSON-derived updates from generated or skipped artifacts |
| Later selected stage fails after valid JSON exists | Preserve its real failure and earlier published artifacts | Post-processing follows A2 eligibility; state work does not replace the primary error |
| Interrupted processing | Preserve established signal and safe-write behavior | State lifecycle follows A2; do not delay shutdown with unbounded optional work |
| XMP-only invocation with unavailable state or missing/unused model settings permitted by existing selected-stage validation | Retain selected-stage isolation and deterministic XMP processing | No provider request or prompt expansion required; state cannot block publication |
| Simultaneous state users and sidecar writers | State follows SQLite contract; sidecars retain existing last-replacement-wins limits | Separate state assertions from sidecar race outcomes; do not invent a winning writer |

## 8. Test execution and quality checks

### 8.1 Existing test infrastructure

- `tests/integration/test_single_image_pipeline.py::rig` supplies CLI subprocesses, synthetic image data, captured loopback requests, and held/released provider responses.
- `tests/unit/test_openai_compatible.py` supplies transport-level request assertions and synthetic credential/error cases.
- `tests/unit/test_structure_stage.py` and `test_slice2_structure.py` supply independent prompt/schema fixtures and generation/skip/recovery cases.
- `tests/integration/test_c1_compatibility.py` covers historical/custom metadata compatibility and existing-artifact behavior.
- `tests/integration/test_xmp_cli_b5.py` and the existing XMP unit/integration suites protect deterministic XMP behavior and source/metadata preservation.
- `tests/unit/test_pipeline.py`, CLI/config diagnostics suites, and existing process/barrier tests provide patterns for outcome independence and concurrency.

Extend these selectively. Add focused state/macro tests where no existing suite owns the concern. A test helper's previous framing or empty-stderr assumption must not dictate new product behavior.

### 8.2 Commands established by the repository

These commands are planned verification. Run from the executing checkout with its current lockfile; record results rather than copying historical pass counts.

| Check | Command |
| --- | --- |
| Lock consistency | `uv lock --locked` |
| Focused implementation tests | `uv run --locked --extra dev --python 3.13 pytest -q <affected-test-paths>` |
| Full development-version suite | `uv run --locked --extra dev --python 3.13 pytest -q` |
| Minimum supported-version suite | `uv run --locked --extra dev --python 3.12 pytest -q` |
| Lint | `uv run --locked --extra dev --python 3.13 ruff check .` |
| Formatting | `uv run --locked --extra dev --python 3.13 ruff format --check .` |
| Distribution build | `uv build --python 3.13` |

Installed-package checks use the repository's established `uv venv` and `uv pip install --python` approach with the actual built wheel. Verify `image-clarus --version`, top-level help, `process --help`, `search --help`, and `init --help`, plus synthetic state/prompt processing. The existing search command remains a stub; its functionality is not delivered here.

Use Linux for required evidence. Do not create a new exhaustive OS/filesystem certification requirement. Record missing interpreter/tool environments as blockers to their assigned checks, not passing results.

### 8.3 Prompt and public-data checks

Unit tests must not freeze production prompt wording. Existing resource tests may compare the currently packaged resource with the current source file; exact instruction/hash assertions use independent fixtures. Separately inspect the required built-in description text and the built-in JSON macro behavior for product acceptance.

Keep schema compatibility tests and approved schema hashing intact. Do not introduce prompt hash snapshots, expanded-request hashes, or additional generated metadata under the guise of testing.

Privacy checks cover the actual changed public files, examples, fixtures, plans, and completion records. Use fictional provider/model aliases, paths, and credentials. Existing source-image and XMP preservation requirements apply to user data; repository fixture sanitization is not a runtime metadata-scrubbing feature.

## 9. End-state requirements allocation

This table separates current delivery from retained parent capabilities. It does not assign future slice numbers, dates, or new Release 1 commitments.

| Parent area | Slice 3 allocation | Later allocation and dependency | Evidence or limit |
| --- | --- | --- | --- |
| Runtime, packaging, license, version | Preserve Python 3.12+, development 3.13, uv/Hatch packaging, Apache-2.0, version reporting | Portability remains desirable; no exhaustive platform promise | C2; existing manifest and historical closeout |
| Single-image stages, sidecars, source integrity | Preserve accepted behavior while adding optional services | Reused by future traversal and unattended processing | E14; persisted handoff and source-byte checks |
| Providers and model controls | Preserve existing adapter, credential behavior, independent models, reasoning controls | Other adapters and broader controls remain separately planned | B5/C2 regressions; no extra provider capability here |
| User-owned prompts and macros | Deliver S3-01–S3-03 and generic expansion | Future config keys/state domains can use the boundary without new mandatory framing | E01–E05 |
| Structured JSON and schema replacement | Deliver optional prompt hash and compatible validation; preserve approved fields/schemas | No automatic regeneration, new tracking, or arbitrary schema rewrite | E06–E07 |
| Hierarchical category guidance and known paths | Deliver full preferences, state exposure, and post-image accumulation | Historical metadata imports/rebuilds and taxonomy reconciliation are excluded; any later scope needs its own decision | E08–E10 |
| General application state | Deliver intentional init, selection, SQLite/memory, sharing, schema evolution, and nonblocking failures | Other domains, including possible batch history, remain later possibilities | E09, E11–E13 |
| Configuration | Extend existing precedence and CLI conventions for approved controls | Future settings follow the same independent boundary | A1, B1, B7 |
| XMP integration and preservation | Preserve accepted digiKam-compatible behavior and old/new JSON consumption | Other consumers/backends remain extensibility work; no new mapping commitment | E06, E14; accepted Slice 2 interoperability history |
| Native input selection and batch traversal | No native batch implementation | Retained parent delivery requiring selection/traversal planning; state is one supporting dependency | Still unmet; external scripts do not complete it |
| Native deterministic search | Preserve existing stub only | Retained parent delivery requiring matching/output/selection design | Still unmet; no substitute via external photo tools |
| Failure policies, retries, logging | Add required state diagnostics; preserve existing primary policies and bounded retries | Broader operations/logging/retry policies need later planning and cost constraints reconciled | E12, E14; no retry expansion |
| External scheduling, stop, resume | Preserve single-image invocation, signals, and sidecar-based completion | External schedulers and future batch/time controls are distinct later work | C2 signals; no scheduler or run-window feature |
| Shared safe writes and concurrency | Preserve artifact service and accepted sidecar-race limitations | Future compatibility changes only for demonstrated needs | E14; state concurrency has separate E13 evidence |
| Exclusion filters, expanded formats, semantic search | No delivery | Later goals; semantic search is explicitly beyond Release 1 requirements | No implied numbering or release commitment |

## 10. Design register and deviations

### 10.1 Routine design work

These items have resolution owners and are not new Product Owner acceptance gates.

| Item | Owner | Due | Required result |
| --- | --- | --- | --- |
| Setting names, exact CLI syntax, dotted macro keys, relative paths | A1 implementer/reviewer | A1 | Usable examples and unambiguous precedence/validation contract |
| Macro parsing, value formatting, eligibility, delimiter behavior, literal syntax | A1 implementer/reviewer | A1 | Fixture cases and exact output rules consistent with S3-02 |
| Safe config view and unavailable-state expansion | A1/A2 implementers | Before A3 | Secret-safe and nonblocking contract |
| Request data versus editable instructions; shared validator location | A1 implementer/reviewer | A1 | Request snapshots and dependency plan |
| Initialization recognition, paths, ancestry/symlinks, failure fallback | A2 implementer/reviewer | A2 | Fixed-precedence resolution/failure matrix |
| SQLite schema, domain evolution, migrations, contention and lifetime | A2 implementer/reviewer | A2 | Storage contract and independent-process evidence plan |
| Category extraction for built-in/historical/custom metadata and accumulation eligibility | A2 implementer/reviewer | A2 | Explicit extraction/eligibility table without taxonomy policy expansion |
| Post-image lifecycle, diagnostics, and interruption | A2 implementer/reviewer | A2 | One lifecycle owner and unchanged primary results |
| Final new module/test paths and crosswalk consistency | A3 implementer/reviewer | A3 | Code-ready dependent steps |

### 10.2 Reconciliation notes

- The current Slice 3 REQ is accepted. Earlier draft-status wording does not create another gate.
- Historical mandatory prompt-hash behavior is intentionally changed by S3-04. Preserve historical records while implementing optional output now.
- Parent requirements describe broader end-state capabilities; exclusions such as native batch and search are allocation boundaries, not completed work.
- The parent REQ's failure-policy text still includes unlimited attempts. The Product Owner's subsequent cost concern does not authorize unlimited model-response retries. Slice 3 adds no retry policy; preserve current bounded behavior. Reconcile the broader wording when retry policy is separately addressed, without making it a Slice 3 implementation blocker.
- Slice 2 closeout and header establish its accepted completion even where a historical progress sentence is stale. Do not reopen its acceptance.

### 10.3 Missing inputs and product decisions

No missing repository input or unresolved Product Owner decision blocks the A3 technical readiness handoff. The plan and A1–A3 records now exist; state and macro implementation remains planned. Recheck the baseline when an execution step is assigned.

A1/A2 mechanics and A3 readiness clarifications are recorded in their completion artifacts. A decision is escalated only if its proposed resolution changes approved product behavior or scope. Do not infer approval for an extra capability from its usefulness.

### 10.4 Deviations and deferrals

**Scope deviations:** None.

**In-scope deferrals:** None.

If an exception is explicitly approved during execution, record the affected requirement, exact change, reason, approval reference, owner, and carry-forward here and in the relevant completion record. Later parent capabilities already excluded from Slice 3 are not new deviations.

## 11. Completion boundary

Slice 3 is ready for orchestration closeout when its delivered behavior and recorded evidence satisfy S3-01–S3-12, the acceptance crosswalk is reconciled, and required compatibility/quality checks have actual outcomes. Keep any limitations or approved exceptions visible.

Native batch, search, scheduling, digiKam-specific automation, historical taxonomy import, and future state domains are not Slice 3 completion conditions. Acceptance follows orchestration advancement through this plan; no additional requirements-acceptance gate is introduced.

