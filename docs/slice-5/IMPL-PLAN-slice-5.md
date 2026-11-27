# Slice 5 Implementation Plan

**Date:** 2026-11-27

**Status:** Phase A in progress. A1 is complete and ready for review at `0.4.5`; see the [A1 contract and evidence](IMPL-A1-COMPLETED.md). A2 and all Phase B/C steps are unstarted. Feature implementation has not started; Phase A remains incomplete.

**Goal:** Add configurable concurrent LLM requests per stage while retaining one stage actor, serial stage decisions/publication, and existing batch, artifact, state and CLI behavior.

**Governing inputs:** [Slice 5 REQ](REQ-slice-5.md), [parent REQ](../REQ-image-clarus.md), and [parent HLD](../HLD-image-clarus.md). The [Slice 4 plan](../slice-4/IMPL-PLAN-slice-4.md), [A2 execution contract](../slice-4/IMPL-A2-COMPLETED.md), [A3 state contract](../slice-4/IMPL-A3-COMPLETED.md), [A4 reporting contract](../slice-4/IMPL-A4-COMPLETED.md), [A5 reconciliation](../slice-4/IMPL-A5-COMPLETED.md), and [C4 closeout](../slice-4/IMPL-C4-COMPLETED.md) establish inherited contracts and version-attributed evidence. Later approved logical read-only state behavior in the parent documents supersedes the historical A3 backend choice.

**Inspected baseline:** `main`, revision `7eada1c2f7b35430e8d35b054f3c1e5a080e6548`, package version `0.4.4`. Source, tests, manifest, sample configuration, packaged prompt/schema assets and governing documents were inspected. No application test, benchmark, build or installation is claimed by drafting this plan. Recheck the worktree at execution time.

## 1. Scope and execution boundary

Deliver S5-01 through S5-07 in full. The only new user setting is `stages.<stage-name>.max_concurrent_requests`, default `1`, through existing YAML and `--set` facilities. Each selected LLM stage has an independent request ceiling; limits do not combine when providers or models are shared. Every outstanding validation-feedback retry consumes capacity. Non-LLM stages accept/validate the setting but ignore it during execution. Preserve existing validation scope and precedence rather than extending selected-stage validation into unrelated settings.

One long-lived actor per selected stage remains the only executor of that stage's inspection, continuation decisions, validation and publication. Provider transport can overlap for different images. A provider child is not a stage worker. Image-stage ownership, request identity/generation and authoritative terminal results remain distinct from request-capacity ownership.

Excluded: extra stage actors; concurrent execution of stage logic within a stage; adaptive concurrency; global provider/model quotas; new provider interfaces/protocols; new retry policy; discovery/admission changes; category or prompt/schema changes; XMP policy or sidecar-locking changes; search; scheduling; persistent job queues; performance guarantees. The setting is a maximum, not a promise to saturate it or accelerate a particular provider.

`--no-inter-stage-concurrency` retains image-first sequential processing regardless of configured limits. The explicit single-image path retains its output and operational contracts. `--max-work-files` still limits initially admitted distinct images, not simultaneous requests, retries or corrective overruns. Existing configuration validation still applies in sequential, empty and dry-run contexts; ignoring a setting operationally does not make an invalid value valid.

### Implementer and reviewer handoff

- Execute the assigned step only, in displayed order. Each step is owned by one agent, which may use helpers within that step. Dependencies identify available inputs, not permission to jump ahead. Plan authoring does not authorize implementation, commits, pushes or releases.
- Requirements and HLD decisions are fixed constraints. Resolve routine implementation mechanics within the assigned design step. Escalate genuine requirement conflicts, new product behavior or proposed scope reductions; do not add a routine per-step Product Owner approval gate. The REQ's draft label is preserved; assignment of a step establishes readiness for that assignment without claiming separate REQ acceptance.
- Completion records are created only when their steps execute. Each has the step title/status, `Scope deviations: None` or approved exception details, decisions/rationale, **Files Created/Updated/Removed**, exact commands/results and runtime/application versions, limitations, and acceptance rows matching the plan. Review the record first. Update detailed rows, summary checkbox, phase gate and overall status together when work is complete and ready for review. Review acceptance and work completion are separate; a reviewer verdict alone never unchecks completed work.
- Unit tests are the primary development harness. Tests and implementation evolve together; no mandatory RED-before-implementation sequence. Use independent prompt fixtures and synthetic data. Real overlap claims require observable provider barriers, not elapsed-time guesses. Fault-injected evidence is labeled as such.
- Preserve supported synchronous stage/pipeline entry points. When replacing internal paths, audit production callers/imports, registry entries, supported exports, tests and fixtures. Remove confirmed superseded/orphaned production code and obsolete tests; test-only references do not justify retention. A true retention exception requires explicit Product Owner approval, purpose and an adjacent code comment.
- Retain one-way module boundaries: CLI assembles services; generic coordination consumes registry/protocol contracts; stages own artifact/domain decisions; providers transport requests; reporting consumes facts. Do not move stage decisions to transport threads or introduce reverse imports/cycles to preserve an old internal seam.
- All examples, fixtures and records are publishable: repository-relative paths, fictional models/providers and synthetic credentials only. Use isolated local loopback providers; no live provider or private image access is authorized. Do not copy external operational guidance into repository documents.
- At each executed delivery follow the established patch-version convention: authoritative `pyproject.toml`, synchronized `uv.lock`, affected version assertions and CLI version checks. Do not preassign future numbers or bump the package merely for drafting this plan. Record each suite at the version actually tested; later version-only checks do not rerun earlier evidence.

## 2. Existing code and intended changes

Paths in this table already exist. Unimplemented helper names and new test files are explicitly proposals; A1/A2 must freeze their exact contracts/locations before CODE steps begin. Prefer existing modules and standard-library facilities; no new dependency is presumed.

| Boundary | Observed implementation | Slice 5 change boundary |
| --- | --- | --- |
| Configuration | `src/image_clarus/config.py`: `DEFAULTS`, `_validate_keys()`, `_validate_shape()`, `_selected()`, `resolve_config()`; `src/image_clarus/cli.py` handles `--set` and execution-mode selection | Add the common setting for registered stages through existing resolution. Handle it before XMP-specific value validation. Keep unrelated unselected-stage settings/dependencies unvalidated as today. |
| Registry/planning | `src/image_clarus/stage_registry.py`: `StageDescriptor`, `STAGES`, `uses_llm`; `src/image_clarus/batch_plan.py`: `PlanningInput`, `build_plan()`, `route()` | Use generic capabilities for limit application. Preserve metadata-only plan, identities, admission and bypass confirmation. No new planner. |
| Resumable driver | `src/image_clarus/stage_protocol.py`: `WorkRequired`, `Request`, `ProviderResult`, `Publish`, `PublicationResult`, `Terminal`, `drive()` | Introduce an actor-usable suspension/resumption boundary without changing provider wire interfaces. `drive()` currently submits and immediately awaits, so increasing a dictionary limit alone cannot implement same-stage overlap. |
| Stage-owned continuations | `src/image_clarus/stages/description.py` and `stages/structure.py`: `inspect()`, `start_or_resume()`, synchronous `run_description()`/`run_structure()`; JSON `_Context` owns retry history and input snapshots | Keep each image's context independent. Preserve skip/recovery/rechecks, input snapshots, retry feedback and publication acknowledgements. Refactor only shared driving mechanics unless a demonstrated seam defect requires a bounded stage change. |
| Actor coordination | `src/image_clarus/batch_execution.py`: `_ConcurrentCoordinator`, `_run_thread()`, `_process()`, `_run_stage()`, `_submit()`, `_await()`, `_confirm()`, `_stage_requests`, `_pending`, `_deferred`, `_owners`, `_active` | Replace single-pending assumptions with independently bounded pending requests and actor-owned resumable turns. Existing `_await()` services confirmations only, not additional inference. Remove the superseded concurrent wait path after new integration works. |
| Transport and cleanup | `batch_execution.py`: `ChildProvider`, `_PendingRequest`, `_children`, `_transport_threads`, `PublicationGate`, `_close_dispatch()`, `run()`; `src/image_clarus/provider_worker.py` and `provider_frame.py` | Keep disposable request children/private IPC. Register and retain every request/transport through spawn, result, cancellation and reap; stop can no longer assume one active continuation per actor. |
| State and publication | `batch_execution.py`: `_finalize_locked()`, `GatedArtifacts`; `src/image_clarus/state/accumulation.py`, `state/service.py`, `artifacts.py` | Preserve per-image state/service lifetime and final accumulation after selected stages. Admission/refusal/draining of writes remains separate from accepting a provider result. |
| Reporting and CLI | `src/image_clarus/batch_reporting.py`: `BatchReporter.consume()`, `render_summary()`; `batch_execution.py`: `ExecutionEvent`, `_request_metadata()`; `cli.py` | Preserve existing output format, request/attempt correlation, distinct-image counts, sanitized failure reasons and exits under out-of-order completion. |
| Packaging/resources | `pyproject.toml`, `uv.lock`, `src/image_clarus/resources.py`, `prompts/`, `schemas/`, `examples/config.yaml`, `README.md` | Keep Python 3.12 minimum/3.13 development baseline, uv/Hatch packaging and existing packaged assets. Change sample config and usage only after implementation evidence. |

### Design questions with bounded owners

| Question | Owner | Required artifact before implementation |
| --- | --- | --- |
| Nonblocking driver API, saved callbacks/transform state, exact continuation/request keys, generic config validation scope and defaulting | A1 — complete | [A1 record](IMPL-A1-COMPLETED.md) freezes `StageDriver`, `perform_publication()`, synchronous adapter compatibility, common defaults/selected-stage validation, identity/state tables and exact B1/B2 handoffs |
| Capacity acquire/release, retry arbitration, ready-response fairness, transport cleanup and stop/result/publication races | A2 using A1 | Complete lifecycle/ownership and fault matrices, evidence ownership, exact B2–B5 interfaces and code-ready handoff |

A1/A2 compare viable local refactoring choices against the existing seams and select a concrete approach. Do not start a general scheduler/transport investigation. Significant questions above must have outcomes, rationales and acceptance scenarios at Phase A exit. Only a genuinely new product choice needs Product Owner disposition. A2 must not be required to complete an A1 acceptance criterion; it consumes and reconciles A1's already-completed contract.

## 3. Phases and steps summary

### Phase A — Design

- [x] Step A1 — Freeze configuration and resumable actor contracts [DESIGN]
- [ ] Step A2 — Freeze lifecycle safety and implementation readiness [DESIGN]
- [ ] Phase A complete — contracts and exact implementation/test handoffs are ready; no significant TBD remains.

### Phase B — Implementation

- [ ] Step B1 — Add generic per-stage request configuration [CODE]
- [ ] Step B2 — Add suspendable stage driving with synchronous compatibility [CODE]
- [ ] Step B3 — Implement bounded request ownership and transport lifecycle [CODE]
- [ ] Step B4 — Integrate multi-request stage actors and shutdown [CODE]
- [ ] Step B5 — Reconcile concurrent accounting and compatibility [CODE]
- [ ] Phase B complete — configured same-stage concurrency and inherited behavior have focused evidence.

### Phase C — Verification and closeout

- [ ] Step C1 — Verify request concurrency through the real CLI [TEST]
- [ ] Step C2 — Verify concurrent failures interruption and resume [TEST]
- [ ] Step C3 — Document verified concurrency behavior [DOCS]
- [ ] Step C4 — Run regression packaging and quality checks [TEST]
- [ ] Step C5 — Reconcile evidence and close Slice 5 [DOCS]
- [ ] Phase C complete — required evidence, package checks and documentation are reconciled.

All steps execute in the order shown, including across phases. Each is estimated below one working day; estimates are planning bounds, not runtime guarantees. If execution reveals a necessary scope/sizing change, report it rather than silently splitting or deferring acceptance.

## 4. Detailed steps

### Phase A — Design

#### Step A1 — Freeze configuration and resumable actor contracts [DESIGN]

**Goal:** Select a code-ready nonblocking stage-driving contract and the generic configuration rules without changing product behavior.

**Dependencies:** Governing REQ/HLD and inspected implementation only. **Estimate:** 0.75 day.

**Inputs:** `REQ-slice-5.md`; parent REQ/HLD; `src/image_clarus/config.py`, `stage_registry.py`, `stage_protocol.py`, `batch_execution.py`, `stages/description.py`, `stages/structure.py`, `stages/xmp.py`; existing `tests/unit/test_config.py`, `test_slice4_config.py`, `test_description_stage.py`, `test_structure_stage.py`, `test_batch_execution.py`, `test_batch_concurrency.py`; Slice 4 A2/A4/A5 records.

**Actions:**

1. Trace `inspect → WorkRequired → Request → ProviderResult → Publish → Terminal`, JSON retries and the synchronous `drive()` callers. Select the smallest common driver decomposition that lets the actor retain a pending request and return to its turn loop without running stage logic in another thread. Preserve synchronous entry points and injected provider seams. Freeze exact changed/new function signatures, continuation ownership, error propagation and callback lifetime; distinguish proposed APIs from existing ones.
2. Define a stage turn and per-image states for ready inspection, deferred work, request pending, response ready, publish, terminal and finalization. Keep one actor and one owner per image; different pending images must not share mutable retry/snapshot/event state. Ready responses may resume independently of submission order, with stage work still serial.
3. Specify strict integer handling/default `1`, YAML/ordered `--set`/parent replacement behavior, selected-stage validation scope, generic applicability through `uses_llm`, non-LLM execution ignore, and unknown-key/stage rejection. Preserve the existing validation boundary for unselected settings; distinguish it from accepting the key for every registered stage. Include `true`, `false`, `0`, `-1`, `1.5`, `"2"`, `null`, arrays and mappings as rejection cases when that stage's value is validated.
4. Freeze exact production/test paths for B1/B2 and the actor-facing request interface consumed by B3/B4. Proposed new tests: `tests/unit/test_slice5_config.py` and `tests/unit/test_stage_protocol.py`; confirm absence/name conflicts before creation. Preserve default-one/single-image behavior and existing resource/schema/prompt contracts.

**Outputs:** [IMPL-A1-COMPLETED.md](IMPL-A1-COMPLETED.md) containing the chosen contracts, alternatives/rationale, transition/config tables, exact interfaces/paths and acceptance scenarios; bounded updates to this plan if the handoff changes.

**Completed handoff:** The [A1 record](IMPL-A1-COMPLETED.md) freezes additions in `src/image_clarus/stage_protocol.py`: `StageDriver` with `current`, `advance()` and `request_started()`, plus `perform_publication()`, while preserving the synchronous `drive()` signature/adapter precedence and stage-owned contexts. B1 adds `COMMON_STAGE_DEFAULTS` and `_validate_max_concurrent_requests()` in `config.py`, with selected-stage common-leaf validation before stage-specific branches. Exact signatures, callback lifetime, identity/state and layering tables, and B1/B2 tests are in that record. A2 owns capacity/cleanup/arbitration mechanics, not an unresolved part of this completed driver/configuration contract.

**Acceptance:**

- [x] Driver and per-image ownership contracts specify exact APIs, callbacks, snapshots, requests, retries, publication acknowledgements and terminal handling without provider-thread stage execution.
- [x] Configuration table covers default/valid/invalid inputs, existing precedence and selected-stage validation, generic applicability, non-LLM ignore and sequential behavior without broadening unrelated validation.
- [x] Existing synchronous consumers and tests are traced; B1/B2 handoffs are code-ready with no unresolved decision owned by a later step.
- [x] `IMPL-A1-COMPLETED.md` is created, linked in Outputs, and records decisions, file inventory, evidence limits and scope disposition; no feature implementation is claimed.

#### Step A2 — Freeze lifecycle safety and implementation readiness [DESIGN]

**Goal:** Resolve request-capacity, cancellation, reporting and cleanup mechanics using A1's completed actor contract.

**Dependencies:** A1. **Estimate:** 0.75 day.

**Inputs:** A1 record; `batch_execution.py` ownership/transport/gate/finalization code; `provider_worker.py`, `provider_frame.py`, `batch_reporting.py`, `cli.py`, `state/accumulation.py`; Slice 4 A2/A3/A4/A5 and C4 records; existing child/signal/publication tests listed in §7.

**Actions:**

1. Freeze capacity acquisition before launch and exactly-once release for success, start failure, transport failure, timeout, cancellation and retry. Specify whether capacity ends at transport completion or a later owned cleanup boundary; distinguish occupancy from retention of an unconsumed response and retained child/helper resources. A free slot must never imply an abandoned child or permission to exceed the request maximum. Do not reserve a request slot for the whole image or count a retry as another admitted image.
2. Select exact per-stage pending/ready collections and identity keys including image, stage, generation and request/attempt identity as applicable. Define retry waiting when other images consume released capacity, response/confirmation/new-work arbitration and event-notification wakeups. Prevent stale, duplicate or mismatched results from resuming/publishing; prevent either confirmation traffic or completion traffic indefinitely starving eligible work. No strict completion order or absolute latency guarantee is added.
3. Write an ownership/stop table covering queued, preparing, spawning, request-pending, response-ready, validating, publication-admitted and finalizing work. Serialize result acceptance and new dispatch against stop; separately serialize publication admission. Already-admitted writes drain with their true outcome. Retain ownership through registration races, child reap and helper/thread join; an actor dying with several pending images must not leave them unowned.
4. Freeze request-local `continue`/default `stop`/`abort` versus unconditional actor/coordinator fatal abort. Specify late-result disposition, queued `not_attempted/batch_aborted`, active interruption, signal exit precedence, protected-result preservation and exactly-once finalization. Preserve local-only cancellation limitations and nonblocking state errors.
5. Freeze event identity/count rules using the existing reporting vocabulary, including retries and transformation callbacks across suspended turns. Audit the affected import direction and planned orphan cleanup. Allocate every §6 evidence row to a concrete B/C boundary and test path; ensure B3 can pass at its helper/current-one-request caller boundary without B4, and B4 owns complete shutdown implementation rather than depending on later C2 code.

**Outputs:** [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md) with capacity/ownership/fault matrices, exact B3–B5 interfaces and test handoffs, dependency/reachability findings and readiness decision; updated plan if required.

**Acceptance:**

- [ ] All acquire/release, retry, fairness, late-result and identity outcomes have concrete decisions and deterministic scenarios.
- [ ] Stop/result/publication admission, actor death and spawn/reap/helper races cover multiple pending requests without unsafe publication or lost tokens.
- [ ] Reporting, state lifetime and dependency-direction contracts agree with A1 and inherited requirements; all implementation steps are code-ready and independently completable in displayed order.
- [ ] Every S5 requirement and acceptance/evidence row has an implementation and verification owner; no significant TBD or unapproved behavior change remains at Phase A exit.
- [ ] `IMPL-A2-COMPLETED.md` is created, linked in Outputs, and records the complete design/readiness decision and file/evidence/scope inventory without claiming runtime proof.

### Phase B — Implementation

#### Step B1 — Add generic per-stage request configuration [CODE]

**Goal:** Accept, resolve and validate the new setting without changing scheduling yet.

**Dependencies:** A1, A2. **Estimate:** 0.35 day.

**Inputs:** A1/A2; `src/image_clarus/config.py`, `stage_registry.py`, `cli.py`; existing config/override tests and A1-selected `tests/unit/test_slice5_config.py`.

**Actions:**

1. Add default `1` for each registered stage and accept the leaf through normal YAML/`--set` key checking, including parent assignments. Integrate strict positive-integer checking before stage-specific validators so XMP does not treat it as one of its own policy/string settings. Keep registry/config dependency direction acyclic.
2. Preserve configuration selection, override repair/replacement semantics, unknown-key/stage errors and selected-stage dependency preflight. No new dedicated CLI flag or plugin/stage-registration framework.
3. Test every built-in stage, omitted/explicit `1`, `2`, `3`, invalid types/values, YAML versus ordered overrides, unknown names/settings, sequential and dry-run static validation. Verify valid XMP-only config resolution needs no provider; actual execution ignore belongs to B4/C1.
4. Run focused new/existing configuration tests and inherited CLI configuration acceptance. Scheduling still behaves as the existing one-request baseline at this intermediate boundary; do not claim S5-02 is implemented.

**Outputs:** Configuration changes/tests and [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md).

**Acceptance:**

- [ ] Defaults, valid values, strict rejection, YAML/`--set` precedence/parent replacement and unknown-key behavior pass focused tests for registered stages.
- [ ] Non-LLM acceptance and existing selected-stage validation/preflight separation are preserved; no dedicated flag or unrelated behavior change is introduced.
- [ ] Exact focused test/version checks and limits are recorded; configuration acceptance is not presented as runtime concurrency proof.
- [ ] `IMPL-B1-COMPLETED.md` is created and linked in Outputs with accurate file inventory and scope disposition.

#### Step B2 — Add suspendable stage driving with synchronous compatibility [CODE]

**Goal:** Make one stage continuation suspendable at a provider request without changing stage-owned semantics.

**Dependencies:** B1 and Phase A contracts. **Estimate:** 0.75 day.

**Inputs:** A1/A2; `src/image_clarus/stage_protocol.py`, `batch_execution.py`, `stages/description.py`, `stages/structure.py`, `stages/xmp.py`; existing stage/pipeline tests and A1-selected `tests/unit/test_stage_protocol.py`.

**Actions:**

1. Implement A1's common bounded driver interface. A call returns control at an outstanding request; a later actor turn supplies only the matching result and resumes the same context. Keep validation, retry decisions and publication on the caller/actor thread. Preserve `Request`/`ProviderResult` and child wire contracts.
2. Build the existing synchronous `drive()` adapter on the same mechanics and route production synchronous callers through it. Preserve `call_provider`, submit/await and observation callbacks where legitimately consumed, or migrate internal consumers with evidence. Do not create a test-only alternate production driver.
3. Preserve transform-start callback ownership across suspensions: per-image state must not be overwritten by another image's turn, and a retry must not double-count transformation. Test two independent contexts interleaved manually, retry resumption, stale/wrong/duplicate results, cross-context publication acknowledgements, deferred `WorkRequired`, skip/recovery/rechecks, provider/write failures and existing JSON snapshots/provenance.
4. Run protocol, description/structure, pipeline and batch-execution focused suites. Audit production uses and remove superseded driver internals only when all supported callers are accounted for. The scheduler remains one-request at this step; manual interleaving is driver evidence only.

**Outputs:** Shared driver/adapter changes, focused tests and [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md).

**Acceptance:**

- [ ] The common driver can suspend and resume independent image contexts without cross-wiring requests, snapshots, callbacks or publication acknowledgements.
- [ ] Retries, skip/recovery/create-only/regeneration and synchronous stage/pipeline contracts pass focused tests without a second stage-policy implementation.
- [ ] Production callers use the shared implementation; reference/orphan and import-boundary audits have explicit findings/disposition.
- [ ] `IMPL-B2-COMPLETED.md` is created and linked in Outputs with actual tests/version, file inventory, limits and scope disposition.

#### Step B3 — Implement bounded request ownership and transport lifecycle [CODE]

**Goal:** Provide independently bounded per-stage request tracking with cancellation-safe transport ownership.

**Dependencies:** B2 and Phase A contracts. **Estimate:** 0.75 day.

**Inputs:** A2's exact capacity API; `src/image_clarus/batch_execution.py`: `_PendingRequest`, `ChildProvider`, `_submit()`, `_stage_requests`, `_pending`, `_children`, `_transport_threads`; `provider_worker.py`, `provider_frame.py`; `tests/unit/test_batch_concurrency.py` and proposed `tests/unit/test_slice5_request_lifecycle.py`.

**Actions:**

1. Implement A2's capacity/ownership helper in the selected existing module unless A2 justified another exact path. Replace the single-value stage slot with the frozen request-keyed tracking. Register before launching, notify readiness without executing stage code on transport threads, release capacity exactly once, and retain cleanup ownership after slot release when necessary.
2. Route the existing one-request production submit/wait caller through the new tracking, preserving its intermediate behavior. Exercise helper-level limits above `1` directly; full actor overlap is B4, not this step's acceptance. Do not introduce a runtime feature flag or leave a new helper used only by tests.
3. Test independent stage capacities `1`, `2`, `3`, shared-provider independence, capacity exhaustion/refill, retry reacquisition, failed thread/child start, delayed spawn registration, timeout, malformed/missing response, stop during transfer and duplicate completion. Verify all spawned children and helper threads remain owned through termination/reap/join; check bounded pipe behavior and private IPC remain intact.
4. Preserve request-local error categories; fatal registry/coordinator invariant violations must not be disguised as ordinary provider failures. Run inherited child and cancellation regressions; keep immutable request/result messages separate from actor-only decisions.

**Outputs:** Capacity/transport tracking and tests; [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md).

**Acceptance:**

- [ ] Helper-level requests cannot exceed independent configured capacities, including retries; all terminal/failure paths release once and retain required cleanup ownership.
- [ ] Spawn/registration/cancellation/timeout/protocol races have deterministic tests with no unowned child/helper or provider-thread stage logic.
- [ ] Existing production one-request callers use the new helper and pass focused regressions; no unsupported end-to-end overlap claim or temporary feature flag is introduced.
- [ ] `IMPL-B3-COMPLETED.md` is created and linked in Outputs with tests/version, reachability/import audit, file inventory and scope disposition.

#### Step B4 — Integrate multi-request stage actors and shutdown [CODE]

**Goal:** Run several pending image continuations per stage with one actor, safe ordering and complete shutdown ownership.

**Dependencies:** B3; B1 configuration and B2 driver. **Estimate:** 0.9 day.

**Inputs:** A1/A2; `src/image_clarus/batch_execution.py`: `_run_thread()`, `_process()`, `_run_stage()`, `_submit()`, `_await()`, `_confirm()`, `_offer()`, `_close_dispatch()`, `_finish_if_interrupted()`, `_finalize_locked()`, `run()`; B2/B3 APIs; `tests/unit/test_batch_concurrency.py`, `test_batch_execution.py`; proposed `tests/unit/test_slice5_actors.py`.

**Actions:**

1. Replace the nested one-image wait with the frozen actor-turn loop. Service matching ready responses, inspect/confirm unrelated candidates and dispatch eligible requests while capacity remains, using `uses_llm` rather than stage names. Retain exactly one stage-logic thread and serial inspection, validation, retry decisions and publication. Do not block ready B behind held A merely to preserve submission order.
2. Preserve one image's stage ownership until its authoritative result; early-forward other images only through real confirmation. Keep known budget exclusions, corrective work, selected subsets and existing prerequisite/regeneration policies intact. Capacity controls requests, not inspection/confirmation or image admission. XMP ignores its setting operationally.
3. Implement A2's complete multi-pending shutdown now: close dispatch and publication admission coherently; cancel all owned outstanding requests; handle response/stop and spawn/registration races; discard late/stale results; drain admitted writes; join/reap every owned child/helper; settle active, suspended, deferred and queued images once. A dead actor's pending images must be settled by the fatal cleanup path, not left waiting for that actor.
4. Preserve request-local `continue`, default `stop` and `abort`, and unconditional infrastructure abort regardless of policy. Preserve real protected-write results, not-attempted versus interrupted distinctions, per-image services and eligible final accumulation/closure. Keep sequential and explicit single-image routes unchanged except shared-driver maintenance already covered in B2.
5. Add deterministic focused tests proving same-stage overlap at limits `2` and `3`, upper bounds, serial actor operations, independent stages, out-of-order publication/results, retries under occupied capacity, fairness/early bypass, non-LLM ignore and default-one behavior. Include multi-pending abort, signal, actor failure and protected-write drain tests; C2 later supplies broader real-process evidence, not missing implementation.
6. Remove the superseded concurrent single-request wait/arbitration path and obsolete tests that encode it as a permanent restriction. Preserve legitimate default-one tests and synchronous adapters. Audit production callers, internal exports and static imports for the changed paths; no test-only orphan retention.

**Outputs:** Integrated actors/cleanup and focused tests; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md).

**Acceptance:**

- [ ] Focused tests demonstrate configurable same-stage overlap/ceilings, independent stages and serial stage logic with matching out-of-order results and no duplicate request/publication/terminal outcome.
- [ ] Multiple pending requests survive retry, request-local failure, configured abort, handled stop and fatal actor/coordinator failure without stranded tokens, unsafe new writes or unowned resources.
- [ ] Early forwarding, admission/correction/exclusion, state lifetime, non-LLM ignore, default-one and sequential/single-image paths have focused compatibility evidence.
- [ ] Superseded production coordination is removed after supported-consumer checks; dependency direction and reference/orphan audit are recorded.
- [ ] `IMPL-B4-COMPLETED.md` is created and linked in Outputs with exact test/version results, file inventory, limitations and scope disposition.

#### Step B5 — Reconcile concurrent accounting and compatibility [CODE]

**Goal:** Preserve truthful existing reports and CLI behavior under out-of-order requests and terminal events.

**Dependencies:** B4. **Estimate:** 0.5 day.

**Inputs:** A2; `src/image_clarus/batch_execution.py`, `batch_reporting.py`, `cli.py`; `tests/unit/test_b6_cli_reporting.py`, `test_b6_cli_routing.py`, `test_c2_failure_request_accounting.py`; proposed `tests/unit/test_slice5_accounting.py`.

**Actions:**

1. Connect the existing `ExecutionEvent` vocabulary to B4's suspend/resume lifecycle. Emit each request start/result once using its real nonce/attempt; distinguish retry counts from admitted and actual distinct-image counts. Preserve generation/image/stage correlation and exactly-once terminal facts.
2. Check reducer reconciliation for shuffled response ordering, duplicate/stale delivery, retry/failure, cancellation and already-completed protected publications. Preserve planned-versus-actual counts, evaluated/transformed counts, corrective work, progress denominator, sanitized failure categories, stdout/stderr ownership and existing exit precedence. No telemetry or new reporting format.
3. Verify CLI dispatch for omitted/explicit `1`, sequential mode with high valid limits, explicit single image, one-image directory/pattern, empty input and metadata-only dry-run. Verify no runtime-only preflight or new state/provider/write activity in dry-run and empty-run boundaries. Reuse existing selection/admission code rather than compensating in reports.
4. Run focused reporting/routing/protocol/concurrency suites. Fix in-scope event wiring/reducer discrepancies and verify the emitter/reducer independently; do not silence reconciliation errors or rewrite final outcomes to match counters.

**Outputs:** Event/reducer/CLI corrections where necessary, tests and [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md).

**Acceptance:**

- [ ] Request/attempt and terminal accounting reconcile under out-of-order, retry, stale/duplicate and partial-failure scenarios without conflating requests and images.
- [ ] Existing verbose/concise output contracts, sanitized categories, channels, exits and progress semantics pass focused tests with no new report format.
- [ ] Omitted/`1`, sequential/single-image, empty and dry-run compatibility have observed evidence; dry-run remains metadata-only.
- [ ] `IMPL-B5-COMPLETED.md` is created and linked in Outputs with actual tests/version, file inventory and scope disposition.

### Phase C — Verification and closeout

#### Step C1 — Verify request concurrency through the real CLI [TEST]

**Goal:** Prove new request concurrency and inherited admission behavior at the CLI/provider boundary.

**Dependencies:** B5. **Estimate:** 0.75 day.

**Inputs:** Phase B records; existing `tests/integration/test_slice4_c1_overlap.py`, `test_slice4_c1_budget.py`, `test_slice4_c1_corrections.py`, `test_prerequisite_admission.py`, `test_c1_plan_parity.py`; proposed `tests/integration/test_slice5_concurrency_cli.py` and `test_slice5_compatibility_cli.py`.

**Actions:**

1. Extend the existing subprocess/loopback-provider harness. With enough distinct eligible images, hold requests using explicit arrival/release barriers and record active/peak counts and image/stage/attempt identities at the actual HTTP boundary. At limit `2`, B must arrive while A is held; at `3`, a third request must arrive before release. For limit `1`, combine ordered provider trace with an observable actor/capacity test proving B was eligible but blocked; a short sleep and absence of arrival alone are not proof.
2. Run separate selected stages and a mixed-stage fixture with unequal limits, including stages sharing a provider/model. Use independent ready images with existing prerequisite sidecars to make simultaneous independent capacities observable. Verify serial stage work/publication using actor-side test instrumentation as a separate boundary; HTTP overlap alone cannot prove actor serialization.
3. Complete B before A and verify B's corresponding artifact/result while A remains held, then release A. Assert exact source-to-output matching, stage ordering, one publication/outcome and truthful summaries. For JSON, force a validation-feedback retry while another request occupies capacity and verify peak, retry snapshots and counts.
4. Exercise work-budget independence with concurrency above `1`: admitted images using multiple stages/retries, known exclusions making no calls, runtime skip not replenishing admission, and permitted corrective work beyond the original admission including a compact beyond-2N fixture. Use real stage decisions for correction; label any post-plan instrumentation.
5. Verify YAML and `--set` precedence/rejection, XMP-only execution ignoring valid limits with real ExifTool, selected subsets, default/explicit `1`, sequential override, single image, empty selection and dry-run. Reuse prior compatibility tests for prompts, categories, safe writes and source integrity; no new live-model or GUI acceptance gate.

**Outputs:** Integration tests and [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md); evidence references for §6 E01–E08 and E12.

**Acceptance:**

- [ ] Actual CLI/provider barriers prove limits `1`, `2`, `3` and independent stage ceilings, including shared-provider/model cases; actor-side serialization is separately demonstrated.
- [ ] Out-of-order B-before-A completion and retry capacity show correct artifacts, identities, counts and ordering without duplicate work.
- [ ] Admission/correction/exclusion and generic config/non-LLM/sequential/default/single-image/empty/dry-run cases have actual boundary-specific evidence.
- [ ] Tests preserve source bytes and clean up all spawned test servers/processes; missing prerequisites or skipped cases remain explicit unsatisfied evidence, not a pass.
- [ ] `IMPL-C1-COMPLETED.md` is created and linked in Outputs with exact commands, versions, per-scenario evidence, files and scope disposition.

#### Step C2 — Verify concurrent failures interruption and resume [TEST]

**Goal:** Demonstrate request-local versus fatal failures and truthful multi-pending shutdown/resume.

**Dependencies:** C1 and existing B4/B5 implementation. **Estimate:** 0.75 day.

**Inputs:** A2 and B4/B5 records; `tests/unit/test_batch_concurrency.py`; existing `tests/integration/test_slice4_c2_policies.py`, `test_slice4_c2_worker_failures.py`, `test_slice4_c2_signal_matrix.py`, `test_slice4_c2_protected_signals.py`, `test_slice4_c2_signal_resume.py`, `test_slice4_c2_validator_group.py`; proposed `tests/integration/test_slice5_failures.py` and `test_slice5_shutdown.py`.

**Actions:**

1. Hold multiple requests in one stage, fail one provider call by HTTP error/timeout/invalid response and by real provider-child exit or malformed/missing frame. Under `continue`, later selected work for that image may use valid persisted input and unrelated work remains eligible; under default `stop`, suppress that image's later stages only; under `abort`, stop new dispatch and settle active work. Repeated request-local failures must not silently escalate policy while infrastructure remains functional.
2. Separately inject stage-actor death and coordinator invariant failure while several images are pending; assert fatal batch abort under every configured policy and full cleanup. Label injected actor/coordinator tests separately from real child-process failures. Verify stale, duplicate, wrong-generation and late completion cannot publish or add a second terminal outcome.
3. Send real Linux SIGINT and SIGTERM after multiple held requests have arrived. Exercise stop against result acceptance, child spawn/registration and publication admission, repeated handled signals and process-group signals during protected validation. Already-admitted writes drain and retain their real outcome; a response accepted before stop still cannot start an unadmitted write afterward. Check queued/not-attempted, active/interrupted, preserved completed results and signal exit precedence.
4. Observe owned children/helper termination and CLI exit before claiming cleanup, including delayed spawn and a partially transferred response; assert no leaked image lifecycle or test process. Use bounded test deadlines only as hang guards, not product cancellation-time promises.
5. Launch a fresh CLI process over the resulting synthetic sidecars, confirm rescan/skip/resume and no regeneration of valid outputs. Preserve backup/recovery and post-selected-stage category accumulation boundaries, no new optional accumulation after handled interruption, visible nonblocking state errors, sanitized diagnostics and source bytes.

**Outputs:** Failure/signal/resume tests and [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md); evidence references for §6 E09–E12.

**Acceptance:**

- [ ] Request-local failures obey all three policies with multiple pending requests; actor/coordinator failures always abort, with evidence distinguishing real child faults from injected infrastructure faults.
- [ ] Real handled SIGINT/SIGTERM, result/stop/publication races and protected-write draining preserve truthful outcomes and forbid new dispatch/publication after their respective gates close.
- [ ] Spawn/registration/transfer/late-result races, owned child/helper cleanup, exactly-once finalization and fresh-process resume have observed evidence without leaks or hangs.
- [ ] Sanitized diagnostics, signal/abort exits, state accumulation timing, source integrity and recovery remain compatible; platform and injection limitations are explicit.
- [ ] `IMPL-C2-COMPLETED.md` is created and linked in Outputs with actual versions/results, file inventory and scope disposition.

#### Step C3 — Document verified concurrency behavior [DOCS]

**Goal:** Explain the delivered control without retroactively rewriting Slice 4 or claiming unverified performance.

**Dependencies:** C2, including C1's functional evidence. **Estimate:** 0.35 day.

**Inputs:** `README.md`, `examples/config.yaml`, parent REQ/HLD; Slice 5 REQ; A/B/C1/C2 records.

**Actions:**

1. Document per-stage defaults/positive-integer validation and YAML/`--set` examples, independent stages sharing a model/provider, generic non-LLM ignore, sequential override, retry capacity and work-image admission distinction. Keep the sample default `1`; do not enable a higher operational default silently.
2. Explain one actor versus N requests, timing-dependent category guidance, out-of-order responses, cancellation of all owned requests and remote cancellation/billing limitations. No throughput percentage or provider quota promise.
3. Reconcile current parent architecture/roadmap and README against demonstrated behavior while preserving historical Slice 4 claims and review/implementation distinctions. Do not change the Slice 5 REQ acceptance label without Product Owner direction.
4. Validate sample config using synthetic credential values, execute provider-free help/version and dry-run examples with isolated synthetic inputs, and identify provider-calling examples as manual/authorized-only. Check links, existing option grammar and publishable values.

**Outputs:** Usage/config/parent-document updates and [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md).

**Acceptance:**

- [ ] README/sample and parent docs accurately describe verified controls, scope, compatibility and limitations with default `1` and no claim of additional stage workers.
- [ ] Sample validation, provider-free documented command checks, local links and privacy checks have actual outcomes; no live calls or private inputs were used.
- [ ] Historical evidence and REQ acceptance status are preserved; new implementation claims cite the appropriate Slice 5 records.
- [ ] `IMPL-C3-COMPLETED.md` is created and linked in Outputs with file inventory, checks/version and scope disposition.

#### Step C4 — Run regression packaging and quality checks [TEST]

**Goal:** Establish fresh runtime, distribution and quality evidence after all implementation/test/usage changes.

**Dependencies:** C3 and all preceding implementation/evidence. **Estimate:** 0.75 day.

**Inputs:** `pyproject.toml`, `uv.lock`, all changed source/tests/docs/assets; Slice 4 C3 installed-wheel procedure; §7 commands and §6 crosswalk.

**Actions:**

1. Run the full suite on Python 3.13 and minimum Python 3.12 in separate locked environments, including actual ExifTool coverage. Record exact application/interpreter/platform/tool versions, counts, failures, skips and limitations. Historical suites are not a fresh baseline. Missing runtime or ExifTool blocks its required evidence unless the Product Owner explicitly approves a disposition.
2. Run lock consistency, Ruff lint/format, focused version assertions and CLI version/help. Build sdist and wheel; install the tested artifact with normal dependencies into an isolated environment, run outside the checkout with `PYTHONPATH` unset, and verify packaged resources match source bytes.
3. In that installed CLI, run controlled loopback same-stage overlap at a limit above `1`, default-one and sequential smoke cases; verify artifacts/source integrity and no source-path fallback. Exercise provider-free help including `init`/category commands, retained search-stub diagnostic and exit `3`, and category smoke. Include a synthetic XMP operation with real ExifTool or leave that installed-path evidence explicitly unsatisfied.
4. Audit all affected production reachability and cleanup, supported synchronous consumers, static imports including function-local imports, and no new cycles. Scope any baseline-cycle finding explicitly; a successful import is not a no-cycle proof. Scan changed public artifacts for credentials, identifying metadata and external/internal infrastructure references. Run link/checklist/whitespace checks.

**Outputs:** Tests or narrowly required in-scope corrections if needed, built artifact identities and [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md). Keep disposable distributions/environments outside the tracked tree.

**Acceptance:**

- [ ] Full Python 3.13 and 3.12 regressions, actual ExifTool coverage, lint/format, lock, build and version checks have passing recorded results or an explicit Product Owner-approved exception for the affected criterion.
- [ ] Installed-artifact overlap/compatibility/resources/CLI/category/XMP checks pass outside the checkout with no source-path injection, with exact artifact/runtime identities and limitations recorded.
- [ ] Production reachability/orphan, static dependency/cycle, privacy, link, checklist and whitespace audits have concrete scope and disposition; no unapproved retained orphan remains.
- [ ] All evidence is attributed to its tested version after the final source/test change; failures and skipped prerequisites are not presented as passes.
- [ ] `IMPL-C4-COMPLETED.md` is created and linked in Outputs with commands/results, file inventory, limits and scope disposition.

#### Step C5 — Reconcile evidence and close Slice 5 [DOCS]

**Goal:** Reconcile all S5 requirements and acceptance outcomes to actual evidence without expanding scope.

**Dependencies:** C4 and all preceding records. **Estimate:** 0.35 day.

**Inputs:** Slice 5 REQ and this plan; A1–C4 completion records; §6 crosswalk, §8 allocation and §9 ledger; current README/parent REQ/HLD.

**Actions:**

1. Map every S5-01–07 clause and §4 acceptance outcome to actual tests/commands and their tested versions, distinguishing unit/helper/actor tests, real CLI/provider evidence and installed-distribution checks. Reconcile all E01–E13 rows; no record's existence substitutes for evidence. Preserve historical limitations.
2. Reconcile overall/phase/summary/detailed acceptance markers and current usage/parent delivery status. Leave unperformed criteria unchecked and report exact blockers; do not silently defer a required scenario or let a review verdict choose orchestration state.
3. Record final version/lock/CLI and affected exact-version tests after this delivery's version synchronization. Attribute C4's full suites and artifact checks to their real version; rerun them if source/tests/assets changed, or if making a final-version full-suite/package claim. Documentation/version-only closeout does not silently relabel earlier suites.
4. Verify local links, exact summary/detailed step headings and acceptance-row mirroring, whitespace, scoped public-value scan and complete file inventory. Do not repair production code under this DOCS assignment without explicit authority; report any newly discovered out-of-scope correction needed.

**Outputs:** Reconciled plan/current documentation and [IMPL-C5-COMPLETED.md](IMPL-C5-COMPLETED.md), including requirement/evidence crosswalk, final version checks and limitations. The C5 record is an output, never a prerequisite input.

**Acceptance:**

- [ ] S5-01–07, all observable acceptance outcomes and E01–E13 have actual boundary-appropriate evidence or an explicit Product Owner-approved disposition; no required case is silently omitted.
- [ ] Detailed rows, summary/phase checkboxes, overall status, completion records and current docs agree; historical Slice 4 and earlier Slice 5 evidence retain their version and scope.
- [ ] Final version/lock/CLI/version-assertion and documentation checks are recorded after the last delivery edit; no unperformed full-suite/build claim is made at that version.
- [ ] Scope/deviation/remaining-allocation and file inventories are complete; no unauthorized production change, commit, release or new approval gate is introduced.
- [ ] `IMPL-C5-COMPLETED.md` is created and linked in Outputs with the completed evidence reconciliation and truthful completion determination.

## 5. Dependency walk and step boundaries

| Step | Available predecessors | Evidence boundary closed by this step |
| --- | --- | --- |
| A1 | Governing requirements and existing implementation | Its own selected config/driver/actor contracts, not later integration |
| A2 | A1 | Capacity/failure/accounting contracts and complete readiness, no feature proof |
| B1 | A1, A2 | Configuration resolution/validation, not scheduling |
| B2 | B1 and A1/A2 | Common suspendable driver and synchronous production adapter, not automatic overlap |
| B3 | B2 plus B1 | Multi-request capacity/transport unit boundary and existing production one-request caller |
| B4 | B3 plus B1/B2 | Integrated actor concurrency, ordering, cancellation and cleanup with focused tests |
| B5 | B4 | Integrated events/reducer/CLI routing and compatibility |
| C1 | B5 | Real CLI/provider positive concurrency and admission evidence |
| C2 | C1 plus B4/B5 | Broader real-process failure/signal/resume evidence |
| C3 | C2 | Usage/sample/current-doc alignment to C1/C2 evidence |
| C4 | C3 | Fresh full regression and installed distribution after usage changes |
| C5 | C4 and earlier records | Final evidence reconciliation and final-version checks |

Later tests strengthen earlier implementation evidence; they are not prerequisites for completing an earlier step's own focused acceptance. B4 cannot postpone shutdown implementation to C2, and C3 cannot claim a package pass that only C4 will establish. No mandatory manual/live-provider/GUI step is needed for this slice.

## 6. Requirement-to-evidence crosswalk

All rows start **Pending**. Each completion record names actual tests, commands, versions and limits. A row spanning several owners stays pending until its full specified boundary is demonstrated; a helper test alone cannot close an HTTP/CLI or process-lifetime claim.

| ID | Requirements and acceptance area | Required observation | Implementation owner | Final evidence owner | Status |
| --- | --- | --- | --- | --- | --- |
| E01 | S5-01; Configuration | Defaults/explicit `1`, `2`, `3`; strict invalid-value rejection at established validation scope; every registered stage accepts the key; YAML/ordered overrides/parent replacement; unknown names/keys unchanged | B1 | C1 | Pending |
| E02 | S5-02/07; Same-stage overlap | Actual held HTTP requests at `1`, `2`, `3`, enough eligible images, peak never above limit, capacity refill; observable capacity refusal at `1` rather than sleep-only absence | B3, B4 | C1 | Pending |
| E03 | S5-02/03; Independent stages | Unequal simultaneous stage capacities with shared provider/model; generic fictional-stage actor test; only one executor of stage logic/publication | B3, B4 | C1 | Pending |
| E04 | S5-02/03; Out-of-order completion | B's result/artifact before held A; exact matching contexts/identities/generations; no duplicate inference, publication, advancement or terminal facts; stale/mismatched/duplicate rejection | B2, B4 | C1, C2 | Pending |
| E05 | S5-02/04; Retry and admission | JSON feedback retry at occupied capacity; preserved snapshots/history and exact request/retry counts; one admitted image across stages/retries | B2–B5 | C1 | Pending |
| E06 | S5-03/04; Fairness and early forwarding | Held same-stage requests permit unrelated confirmations/bypasses and eligible dispatch; ready responses and queued work are not indefinitely starved; same image never overlaps stages | B4 | C1 | Pending |
| E07 | S5-04; Budget and stage semantics | No admission refill, known exclusion never calls, permitted corrective work including beyond-2N, selected subsets, authoritative rechecks/recovery/regeneration and prerequisite policy preserved | B4, B5 | C1 | Pending |
| E08 | S5-01/04/07; Compatibility | Non-LLM execution ignores valid limit with real XMP; omitted/`1` retain stage overlap; sequential overrides higher limits; single-image, empty and dry-run boundaries unchanged | B1–B5 | C1 | Pending |
| E09 | S5-05; Request-local versus fatal failure | Child start/exit/protocol/provider/timeout/invalid-result cases obey three policies; actor death/coordinator invariant always abort regardless of policy; unrelated work eligible only under non-aborting request-local policies | B3, B4 | C2 | Pending |
| E10 | S5-03/05; Shutdown and owned resources | Multiple held requests, real SIGINT/SIGTERM, configured abort, spawn/registration/transfer races; no new dispatch, no stale publication, all owned children/helpers retained to cleanup, no leaked lifecycle | B3, B4 | C2 | Pending |
| E11 | S5-04/05; Publication, state and resume | Stop/result/publication gate races, drained admitted writes and real outcomes, safe recovery, fresh CLI rescan/skip, per-image state retained, final accumulation timing/disable/interruption and nonblocking errors preserved | B4 | C2 | Pending |
| E12 | S5-06/07; Observable accounting | Per-stage evaluated/transformed/outcomes, exact request/retry/distinct/corrective counts and accounted progress; truthful partial exits, concise single-image output, channels and sanitized categories | B5 | C1, C2 | Pending |
| E13 | S5-07; Regression and delivery | Focused plus full 3.13/3.12 suites, actual ExifTool and installed-artifact overlap/compatibility/resources, lint/format/build/lock/version; final docs and version-attributed limits | All B steps | C3, C4, C5 | Pending |

## 7. Verification execution

### Existing regression anchors

- Configuration/CLI: `tests/unit/test_config.py`, `test_slice4_config.py`, `test_cli_config_acceptance.py`, `test_config_diagnostics.py`, `test_b6_cli_routing.py`, `test_b6_cli_reporting.py`.
- Stage/protocol: `tests/unit/test_description_stage.py`, `test_structure_stage.py`, `test_slice2_structure.py`, `test_structure_edge_cases.py`, `test_pipeline.py`, `test_batch_execution.py`. Preserve request snapshots, stale/cross-context rejection and publication acknowledgements.
- Actor/children: `tests/unit/test_batch_concurrency.py`, especially `test_actor_serves_queued_candidates_while_its_request_is_outstanding`, `test_completed_transport_releases_stage_slot_before_waking_retry`, `test_abort_refuses_publication_after_another_stage_inference`, and child-registration/helper/shutdown cases. Old default-one tests remain applicable; tests assuming one pending image for all configurations must be updated, not weakened wholesale.
- Reporting: `tests/unit/test_b6_cli_reporting.py`, `test_c2_failure_request_accounting.py`; `tests/integration/test_c1_verbose_execution.py`, `test_slice4_c2_policies.py`.
- State/artifact compatibility: `tests/unit/test_state_accumulation.py`, `test_artifacts.py`, `test_recovery_invalid_backup.py`; `tests/integration/test_state_accumulation_timing.py`, `test_state_accumulation_signals.py`, `test_slice4_c1_state.py`, `test_slice4_c2_recovery.py`.
- CLI and process barriers: existing `tests/integration/test_slice4_c1_overlap.py`, budget/correction/prerequisite tests, and C2 signal/worker/validator tests named in the steps. Keep synthetic test servers and child processes disposable and owned by a `finally` cleanup path.

### Planned commands

Run from the repository root. These are future execution instructions, not claims that drafting ran the application suites. Use a separate disposable environment directory in `UV_PROJECT_ENVIRONMENT` when testing another interpreter; record the expanded paths/commands privately as needed and publish portable command forms. `$DIST_DIR` and `$CHECK_ENV` designate disposable directories chosen by the implementer, not repository artifacts.

```sh
uv sync --locked --extra dev --python 3.13
uv lock --check
uv run --no-sync --locked --extra dev pytest -q -p no:cacheprovider
uv run --no-sync --locked --extra dev ruff check .
uv run --no-sync --locked --extra dev ruff format --check .
uv run --no-sync --locked image-clarus --version
uv run --no-sync --locked --extra dev pytest -q tests/unit/test_cli.py -k version
uv build --out-dir "$DIST_DIR"
```

For focused steps, use the same pytest form with the actual files listed in that step, including newly created tests only after their owning step creates them. Run full suites after final source/test corrections, not before a last fix. Isolate a Python 3.12 environment with `UV_PROJECT_ENVIRONMENT="$CHECK_ENV" uv sync --locked --extra dev --python 3.12`, then use that same environment and interpreter in the full-suite run. Verify the interpreter identity; do not infer it from the command label. Do not overwrite the normal development environment to obtain minimum-version evidence.

The full suite must exercise real ExifTool-dependent tests; availability/skips are recorded. Linux is required. Windows-compatible process/pipe design is retained, but Linux tests or a simulated branch do not establish Windows runtime verification. No mandatory Windows runtime or broad CI-matrix project is added.

For distribution smoke, build an sdist and wheel, install the exact selected wheel into an isolated environment with normal dependencies, clear `PYTHONPATH` and run from outside the checkout. Record which wheel was actually installed and whether it came from the sdist. Verify both packaged prompts and both schema assets against the tested source snapshot. Do not reuse a source-tree subprocess harness with a source `PYTHONPATH` override as installed-wheel evidence.

Verify all retained help entry points: top-level, `process`, `init`, `search`, `state`, `state categories`, and category `list`, `clear`, `rebuild`; verify `--version` and search's unchanged not-implemented execution/exit `3`. The local-provider harness must use fictional responses and no credentials or private photographs.

Documentation checks after the final edit: exact summary/detailed heading equality, one completion output per step, matching detailed/record acceptance rows at execution time, local Markdown links, new-file whitespace, no unexpected source changes and a bounded public-value scan. Future completion links may be absent only while the corresponding step is unchecked. No historical test totals are copied into new execution records as fresh results.

## 8. End-state requirements allocation

This carries forward the parent's remaining capabilities without assigning new slice numbers or Release 1 commitments. Candidate later Release 1 work is uncommitted and requires its own requirements/design/verification. Historical completed delivery is not reopened by this allocation.

| Parent area | Slice 5 allocation | Remaining work and prerequisites | Evidence/limit |
| --- | --- | --- | --- |
| Purpose and guiding requirements | Improve configurable processing capacity while retaining CLI composition, immutable sources and independent native batch capability | Further user workflows require separate scope | E02–E13; no guaranteed speedup |
| Runtime, dependencies, packaging, license and version | Preserve Python 3.12+, 3.13 baseline, uv/Hatch and Apache-2.0; verify distribution/version/resources | Broader platforms/automation are later goals, not mandatory Windows runtime acceptance | E13 |
| Processing stages and artifacts | Preserve selected `desc/json/xmp`, persisted handoffs, skip/regeneration and generic capabilities; serial actor logic | New stages/artifacts require their own contract | E03–E08, E11 |
| Input selection and traversal | Preserve Slice 4 deterministic native selection, formats, symlinks and resolved-path identity | Exclusion filters/expanded decoder support remain later goals | Existing regressions and E07/E08 |
| Batch planning and execution | Deliver independent per-stage concurrent requests; retain metadata-only Option A, early forwarding, admission/corrections and sequential override | Content-aware Option B, multiple stage workers or adaptive/model-aware scheduling remain outside Slice 5 | E02–E08 |
| Stage dependencies | Preserve persisted prerequisites and selected-subset policy with no implicit stages | Further dependency behavior requires separate design | E06–E08 |
| Model providers and prompts | Preserve named models/providers, HTTP adapter/security, reasoning settings and editable prompts | Broader generation parameters are candidate later Release 1 work; other protocols/decoders are later goals | E05/E08/E13; no new provider interface |
| Structured metadata and provenance | Preserve schema/envelope versions, custom schema and optional source prompt hash | New schema/search-field needs require their own versioned design | E04/E05/E13 |
| Category guidance and known state | Preserve full hierarchical paths, secret-safe macros and timing-dependent cross-image visibility | Other metadata/digiKam category imports and further domains remain later goals | E11/E13; no global category barrier |
| Application state | Preserve per-image selection, memory fallback, visible nonblocking errors, concurrent SQLite, migrations and category commands | Future state domains require explicit contracts; no durable job database introduced | E11/E13 |
| XMP integration | Preserve existing mappings, root/field policies, source safety and unrelated metadata | Additional representations/backends remain later goals requiring interoperability evidence | E08/E11/E13; no new GUI test claim |
| Native deterministic search | Preserve registered help and not-implemented execution | Candidate later Release 1 work: matching, fields, output contracts and discovery reuse | Still unmet; external photo tools are not a replacement |
| Configuration and precedence | Deliver generic concurrency leaf/default/validation through YAML and existing overrides | Optional split provider files and broader configuration features remain later goals | E01/E08 |
| Failure policies, retries and logging | Preserve request-local policy versus fatal abort; exact concurrent accounting and sanitized existing reports | Broader category-specific retries/backoff and log destinations remain candidate later Release 1 work where not yet delivered | E05/E09/E12/E13; no new retry or telemetry system |
| External scheduling, stop and resume | Deliver multi-request cancellation/cleanup with sidecar rescan; preserve external orchestration | Run bounds/time windows are candidate later Release 1 planning when useful; no internal scheduler | E10/E11 |
| Safe-write requirements | Preserve recovery, backup, permissions behavior and admitted-publication draining; SQLite separate from sidecar races | Filesystem-specific changes only for demonstrated need; no cross-process sidecar locking | E11/E13; no universal crash-proof claim |
| Requirements evolution | Preserve accepted user-owned prompt/state decisions and historical evidence from earlier slices | Early-escalation process lesson is not additional product scope | Source docs and E13 |
| Delivery approach and design handoff | Produce this slice's design, implementation, evidence and closeout with explicit remaining allocation | Later scope/order and Release 1 inclusion remain uncommitted | A1/A2/C5 |
| Known non-goals, semantic search and richer extensions | No hardcoded model, scheduler, automatic photo-change detection, mandatory job store, general XMP reconciliation or semantic search | Semantic search explicitly outside Release 1 requirements; other extensions need separate scope | Not acceptance prerequisites |

## 9. Risks, deviations and remaining work

| Risk | Required mitigation and owner |
| --- | --- |
| Raising a slot count while still awaiting one continuation | A1/B2 driver decomposition; B4 actor turns; real same-stage barriers in C1 |
| Capacity freed while ownership is lost or retry bypasses the ceiling | A2 lifecycle matrix; B3 release/reap tests; C1 retry overlap |
| Image contexts overwrite callbacks/history/services | A1 ownership contract; B2 interleaved contexts; B4/B5 event and finalization tests |
| Starvation or hidden head-of-line waiting | A2 arbitration choice; B4 focused ready-response/confirmation/dispatch tests; C1 B-before-A observation |
| Abort cancels only the currently executing image | A2 complete pending registry; B4 fatal cleanup; C2 multiple-pending real signals and actor-death cases |
| Accepted response incorrectly grants publication after stop | Preserve separate acceptance/publication gates in B4 and race them in C2 |
| Tests preserve obsolete one-pending internals or hide orphaned production code | B2/B4 supported-consumer audit and deletion; C4 reachability/import review |
| High configured concurrency increases payload/child memory and provider load | Retain a configurable maximum, no slot-filling/performance promise; C3 explains tradeoff; no new hard resource ceiling or telemetry |
| Package appears green only through checkout imports | C4 install outside checkout with no `PYTHONPATH`, actual wheel/resource/overlap checks |

**Scope deviations:** None.

**In-scope deferrals:** None.

**Open design items:** A1's configuration/driver decisions are complete in its [record](IMPL-A1-COMPLETED.md). A2's bounded capacity, cleanup, arbitration, failure and accounting questions in §2 remain unstarted and must be resolved before B1. No unresolved product choice is invented by this plan, and completed Slice 4 choices are not reopened.

**Remaining execution:** A1 design is complete at `0.4.5`; its record distinguishes disposable contract-probe and existing focused-regression evidence from feature acceptance. A2 and all B/C steps are unstarted. Selected driver/configuration APIs and future test additions are not implemented. Remaining completion records must not be pre-created. Original plan authoring did not change the application version or run feature tests; the later A1 delivery has its own version-attributed checks.

Any approved exception must name the requirement, exact change, reason, approval reference, owner and carry-forward milestone in this ledger and the relevant completion record. A failed or unavailable mandatory test stays unsatisfied unless explicitly dispositioned; a new issue outside a step's authority is reported, not silently repaired or deferred.

## 10. Completion boundary

Slice 5 work is complete when S5-01–07 and their observable acceptance outcomes are demonstrated through the mapped boundaries: configurable independent request ceilings, one actor/serial stage logic, correct identities and retries, unchanged image admission and stage/state/artifact semantics, complete multi-pending failure/stop/cleanup, truthful accounting and preserved default/sequential/single-image behavior. Current documentation and package evidence must match what was actually verified. Completion does not imply reviewer acceptance, a release, remote cancellation or a throughput guarantee.
