# Step A1 — Freeze configuration and resumable actor contracts [DESIGN]

**Status:** Complete and ready for review. Review acceptance is separate. A2 has not started; Phase A is not complete and feature implementation has not started.

**Date:** 2026-11-27

**Scope deviations:** None.

**Requirements and plan:** [Slice 5 REQ](REQ-slice-5.md), [A1 in the implementation plan](IMPL-PLAN-slice-5.md#step-a1--freeze-configuration-and-resumable-actor-contracts-design), [parent REQ](../REQ-image-clarus.md), [HLD](../HLD-image-clarus.md).

**Version:** Inspected implementation `0.4.4`; this design delivery synchronizes application metadata to `0.4.5`. Verification below identifies its tested version. No production feature code, repository tests, prompts or schemas were changed.

## Files Created/Updated/Removed

- Created: `docs/slice-5/IMPL-A1-COMPLETED.md`.
- Updated: `docs/slice-5/IMPL-PLAN-slice-5.md` — A1's frozen handoff, detailed/summary completion and overall status; A2 and all later steps remain pending.
- Updated: `docs/slice-5/REQ-slice-5.md` and `README.md` — plan-progress link labels only; no requirement or acceptance-status change.
- Updated: `pyproject.toml` and `uv.lock` — application version `0.4.5`, with unchanged dependency declarations/resolutions.
- Removed: None.

Disposable prototype files and test data were created outside the repository for design validation. They are not shipped implementation or new repository test modules.

## 1. Decision and alternatives

**Selected:** Add a small, caller-driven `StageDriver` in the existing `src/image_clarus/stage_protocol.py`. It advances one stage-owned continuation to the next protocol boundary and returns control without performing provider I/O. Preserve `drive()` as a synchronous adapter over this same driver. Extract its existing publication invocation into `perform_publication()` so synchronous and actor callers use one artifact-adapter implementation. Existing stages retain their inspection, validation, retry decisions, snapshots, publication policies and result types.

| Alternative | Disposition and rationale |
| --- | --- |
| Raise `_stage_requests` capacity but keep the existing submit/immediate-await driver | Rejected: the actor still waits for one image, and `_await()` services only confirmations. It cannot dispatch several independent continuations. |
| Add a thread/worker running the complete stage per image | Rejected: violates the one-actor/serial-stage-logic requirement and moves validation/publication ownership outside that actor. |
| Replace the provider boundary with an asynchronous client or a general task scheduler | Rejected for this slice: widens scope and reopens established provider-child isolation. Only request transport overlaps; existing provider interfaces and private framed IPC remain unchanged. |
| Have a suspendable actor implementation separate from the synchronous stage driver | Rejected: duplicates stage-driving/error/publication behavior and invites compatibility drift. |
| Caller-driven driver plus synchronous adapter | Selected: the stages already emit `Request`, `Publish` and `Terminal` with saved context; the missing facility is returning control at those boundaries. |

No new dependency, stage, dynamic plugin system, provider API, wire protocol or command-line flag is selected. These are internal stage-driving mechanics within S5-02/03, not new product behavior.

## 2. Observed contracts and consumer trace

The source trace below describes the inspected implementation, not a claim that the new APIs already exist.

| Existing consumer/boundary | Current path and behavior | Required preservation |
| --- | --- | --- |
| Description | `src/image_clarus/stages/description.py`: `run_description() → inspect() → drive()`; `start_or_resume()` validates request/publication identities | Source/config snapshot, authoritative recheck, create-only/regeneration, failure categories and synchronous return value |
| JSON | `src/image_clarus/stages/structure.py`: `run_structure() → inspect() → drive()`; `_Context` holds `attempt`, `history`, `snapshot`; `_request()` creates an independent request nonce for each attempt | Snapshot reuse across validation-feedback retries, attempt/history isolation, schema/envelope/provenance and publication acknowledgement |
| XMP | `src/image_clarus/stages/xmp.py`: `run_xmp() → inspect() → drive()`; transform callback is passed into backend work | Remains non-LLM and synchronous on its actor, with existing policies, ExifTool isolation, safe publication and no new request runtime |
| Batch common seam | `src/image_clarus/batch_execution.py`: `_run_stage()` supplies `start_or_resume=execute_stage`, provider adapters and observation callbacks to `drive()` | Generic invocation, event identity, categorized error reduction, one terminal result and per-image transform state |
| Concurrent batch | `_ConcurrentCoordinator._run()` supplies `ChildProvider.call`, `_submit()` and `_await()`; confirmations have no provider adapter and return `WorkRequired` before transformation | Keep confirmation/deferred-work ownership; B4 replaces the concurrent single-request wait, not the synchronous stage contracts |
| Single-image pipeline/CLI | `src/image_clarus/pipeline.py`: `run_pipeline()` invokes supplied stage runners; `cli.py` assembles the stage services/runners | Registry order, selected subsets, concise output, existing signal/error/exit handling; no N-way execution for one image |
| Registry | `src/image_clarus/stage_registry.py`: `StageDescriptor.inspect`, `.start_or_resume`, `.run` resolve stage functions lazily | New generic driver imports no concrete stage or registry execution property; metadata-only planning remains separate |

### Adapter compatibility details

Keep the current `drive()` signature unchanged:

```python
def drive(
    stage, work, services, *, start_or_resume=None, call_provider=None,
    on_provider_request=None, on_provider_result=None,
    submit_provider=None, await_provider=None,
    defer_transformation=False, resume=None,
): ...
```

Provider adapter precedence remains **a complete submit/await pair → call_provider → services.provider_factory**. A lone submit or await hook does not silently become a new asynchronous mode. The pair still synchronously awaits in this compatibility adapter; the new concurrent actor uses `StageDriver` directly instead.

There are two existing resume seams, which must not be conflated:

- `drive(resume=step)` starts from that protocol step instead of invoking `start_or_resume(work.context, None)`. No production caller currently passes this keyword, but the adapter retains it and B2 tests it.
- Batch `_run_stage(resume=step)` skips fresh inspection and passes the preserved `WorkRequired` as `work` to `drive()`; it does not forward the `resume` keyword. Preserve this path until the replacement actor integrates.

Initial confirmation deferral remains in `_run_stage()` before `drive()` is entered. The synchronous adapter also retains its existing handling of a `WorkRequired` returned by a continuation when `defer_transformation=True`. Do not change cold-start ordering in the synchronous adapter merely to implement the actor's explicit deferral API.

### Existing test anchors

- `tests/unit/test_description_stage.py`: `test_resumable_request_identity_snapshot_and_publication`, `test_cross_context_publication_acknowledgement_rejected`, `test_interrupted_provider_and_publication_are_not_stage_failures`, `test_transformation_is_announced_once_request_is_prepared`.
- `tests/unit/test_structure_stage.py`: `test_resumable_retry_snapshots_stale_and_publication`, `test_resumable_exclusion_and_recheck`, `test_resumable_provider_and_publication_failures`, `test_transformation_is_announced_only_when_json_is_published`, `test_missing_description_is_not_a_transformation`.
- `tests/unit/test_batch_concurrency.py`: `test_actor_serves_queued_candidates_while_its_request_is_outstanding`, `test_confirmation_defers_work_until_held_request_finishes`, `test_two_stages_hold_requests_for_different_images_at_once`, `test_completed_transport_releases_stage_slot_before_waking_retry`.
- `tests/unit/test_c2_failure_request_accounting.py`: `test_held_request_is_single_consume_under_concurrent_confirmations`.
- `tests/unit/test_xmp_integration.py` and `tests/unit/test_xmp_stage.py`: existing no-change, prerequisite and successful-publication transform callback cases.
- `tests/integration/test_stage_lifetimes.py`: `test_cli_full_stage_lifetimes`.

The last three groups are traced compatibility anchors, not claims that all those modules were freshly run in A1. Actual executed coverage is listed in §8.

## 3. Frozen internal driver API for B2

The following names and signatures are **selected additions**, not existing source symbols. They live in `src/image_clarus/stage_protocol.py`:

```python
class StageDriver:
    def __init__(
        self, stage, work: WorkRequired, services, *,
        start_or_resume=None,
        on_transform_started=None,
        on_provider_request=None,
        on_provider_result=None,
        resume=None,
    ): ...

    @property
    def current(self) -> WorkRequired | Request | Publish | Terminal: ...

    def advance(
        self, result: ProviderResult | PublicationResult | None = None, *,
        defer_transformation: bool = False,
    ) -> WorkRequired | Request | Publish | Terminal: ...

    def request_started(self, request: Request) -> None: ...


def perform_publication(step: Publish, services) -> PublicationResult: ...
```

### Construction and boundaries

1. Construction retains the exact `WorkRequired` and services, the selected `start_or_resume` callable, and observer callbacks. It performs no inspection, transformation, I/O, provider call, validation or publication. `current` initially exposes `work`, or the explicitly supplied `resume` protocol step. Only the driver changes its current step.
2. With a current `WorkRequired`, `advance(None)` invokes the selected stage callable with that step's context and `None`, then returns the emitted boundary. With `defer_transformation=True`, it returns the identical work/context untouched and does not call the stage. Initial actor inspection is still stage-owned and occurs outside the driver.
3. With a current `Request` or `Publish`, `advance(None)` returns that same boundary without a callback, resubmission, publication or state change. It is inspection of the suspended boundary, not a second attempt.
4. With a current `Request`, `request_started(request)` accepts only that exact current request and only once for that attempt. It marks the attempt started and invokes `on_provider_request(request)` once. The caller invokes it immediately before its admitted dispatch attempt, never while the request merely waits for capacity. In the synchronous adapter the same method brackets its selected provider adapter. Slot admission and launch/cleanup mechanics belong to A2/B3, not this API.
5. `advance(ProviderResult)` requires a started current request and its exact full request ID. It invokes `on_provider_result(request, result)` once, then calls the stage with `request.continuation` and the result. The next boundary can be another `Request` (a retry), `Publish` or `Terminal`. A new request starts unsubmitted and must pass `request_started()` independently. No driver-created retry or implicit provider call is permitted.
6. `advance(PublicationResult)` requires the current publication's exact ID, then calls the stage with its continuation and the acknowledgement. The driver does not infer success from response acceptance or from having prepared bytes.
7. A terminal result is read from `current.result`. Advancing after terminal consumption, re-starting the same request, supplying a result before start, an incorrect response type/identity or an invalid protocol step raises a value/type error without embedding private values. Input identity rejection must not consume a different valid continuation. The coordinator rejects stale/duplicate/generation-mismatched envelopes before calling the driver; a rejected external result must not automatically become a fresh image failure.
8. Unexpected stage or observer exceptions propagate to the existing batch fatal-error reduction. Restore callback state in `finally`; the owning caller must retire the failed driver, never re-enter it to replay uncertain stage work. Artifact/provider domain failures continue through their existing sanitized result contracts. No new blanket catch converts infrastructure faults into provider failures.

### Publication helper and synchronous loop

`perform_publication()` extracts the existing artifact-adapter operation: call `services.artifacts.write(step.continuation.output, step.validated_bytes, step.validator, validation_category=step.continuation.validation_category)`; return the matching `PublicationResult`, wrapping an `ArtifactError` as its error. Other exceptions, including the existing gate-refusal exception, propagate to their existing owner. It adds no recovery algorithm, policy or publication authorization. The actor supplies the already-gated service; stop/publication arbitration remains A2's responsibility.

`drive()` constructs one driver, preserves its existing initial-call versus `resume` behavior, then loops over protocol boundaries. For a request, call `request_started()`, run the selected adapter synchronously, and supply its `ProviderResult` to `advance()`. For a publication, call `perform_publication()` and supply its acknowledgement. Return `Terminal.result` or the existing permitted deferred `WorkRequired`. Both paths use the same stage continuation and publication helper; do not retain a parallel old implementation of policy or artifact invocation.

### Callback lifetime and transformation accounting

The driver captures one image-stage transform callback, explicitly supplied by the actor or captured from the services at driver construction. Capture once, not when a different image happens to be resumed. On each invocation of the stage callable, temporarily bind `services.on_transform_started` to the driver's once-only forwarding closure and restore its exact previous value in `finally`; if the attribute was absent, restore absence. No callback binding remains installed while a request is pending.

A driver retains its own `transform_started` latch across all its retries and turns. The closure forwards at most once to that image's callback. Existing stage timing remains authoritative: description announces transformation when its request is prepared; JSON announces it only after valid output is ready for publication; XMP announces it at its existing backend transformation point. Do not equate request count, transform count and terminal completion. Preparing a request is not itself permission to dispatch it.

Each image retains its selected services/state until its selected stages and eligible accumulation finalize. Different image contexts do not share mutable retry histories/snapshots or driver callback latches. Per-image stage execution remains sequential, so two stage actors never concurrently bind that same image's services. The driver does not open, close or accumulate state itself.

## 4. Actor-facing identity and state contract

### Identities

- **Continuation key:** `(image_id, stage_name, generation)` in the coordinator. One live driver per image-stage generation, with at most one pending request for that driver at a time.
- **Request ID:** preserve the stage-produced opaque tuple. Built-ins currently use `(str(image_path), stage_name, attempt_number, nonce)`; do not truncate to stage or image alone. The full tuple is internal and must not be rendered as a diagnostic.
- **Pending request identity:** continuation key plus full request ID. A response resumes only that live driver and current attempt. Actor/coordinator maps retain the key even though the provider frame/result type is unchanged.
- **Publication ID:** preserve the existing per-publication ID and matching acknowledgement. Multiple images' publications are serialized by their stage actor, never conflated into a stage-wide acknowledgement.
- **Reporting identity:** retain `_request_metadata()`'s safe nonce plus attempt and existing image/stage/generation event fields. No new persisted identity or provider wire field.

These define matching semantics, not A2's choice of collection classes, capacity-release boundary or fairness algorithm.

### Per-image progression and ownership

| State | Owner and permitted transition | Forbidden behavior |
| --- | --- | --- |
| Queued for inspection/confirmation | Coordinator owns queue/token; owning stage actor calls its authoritative `inspect()` | A provisional bypass is not terminal success |
| Deferred `WorkRequired` | Same stage owner retains exact context; actor may later call its driver's `advance()` | No secondary worker, reinspection by scheduler or lost continuation |
| Preparing a stage turn | Stage actor alone executes `start_or_resume()` and temporary callbacks | No other actor/transport thread runs that image's stage decisions |
| Request ready | Driver retains request/context; coordinator may arrange capacity and dispatch | Preparing it does not create another admitted image or bypass capacity |
| Request pending | Transport owns request I/O; actor is free to run unrelated image turns | No duplicate request for that image/attempt; no downstream image-stage advancement |
| Response ready | Coordinator checks live identity/generation and stop ownership; stage actor alone resumes | Transport thread cannot validate stage output, select retry, publish or finalize |
| Publication ready/admitted | Stage actor invokes the common helper through existing publication gate, then consumes matching acknowledgement | Response acceptance is not publication permission |
| Stage terminal | Coordinator records one authoritative outcome and applies continuation policy | No second terminal outcome or unselected prerequisite stage |
| Image finalizing/terminal | Existing finalization owner performs eligible accumulation/cleanup exactly once after selected stages | No driver-owned state close or duplicate accumulation |

A stage may have several **different images** in request-pending/response-ready states while only one actor executes stage logic. Out-of-order completion is valid: accept B's matching ready result, validate/publish B serially on the actor, and forward B when its real stage outcome permits it while A remains pending. Do not wait for A merely to preserve submission order. Exact arbitration and cleanup races are A2 outputs and do not change this ownership contract.

## 5. Frozen configuration contract for B1

### Placement and validation implementation

Use `src/image_clarus/config.py` only for the common setting schema/default and validation. Add `COMMON_STAGE_DEFAULTS = {"max_concurrent_requests": 1}` and apply a fresh copy of its leaves to every existing `DEFAULTS["stages"]` entry. The existing fixed registered-stage/config schema remains; no dynamic stage loader is introduced. Add a parity test against `stage_registry.STAGES`, so a future registered stage cannot silently omit the common configuration key. No new production import from configuration to concrete stages is needed.

Add `_validate_max_concurrent_requests(value, stage_name) -> None`, with the predicate `type(value) is int and value > 0`. On failure raise a `ConfigurationError` identifying the known key and expected positive integer, never the submitted value or raw exception. Invoke it for the selected stage's common leaf in `_validate_shape()` **before** the `stage == "xmp"` branch, then continue rather than passing the value to `_validate_xmp_value()` or string/model setting validation. `resolve_config()`'s public signature is unchanged.

The setting is not a path, provider model field, image budget or dedicated flag. Existing `DEFAULTS`-based `_validate_keys()`, `_override_path()` and overlay mechanics recognize it once the common defaults are present. Do not implement a second configuration parser.

### Values and validation scope

| Input or context | Frozen outcome |
| --- | --- |
| Omitted leaf | Effective resolved value `1` for each registered stage |
| Integer `1`, `2`, `3` or any larger positive integer | Valid; no new arbitrary upper cap |
| Boolean `true` or `false` | Invalid even though Python bool subclasses int |
| `0`, negative integer, float including `1.0`, quoted numeric string, `null`, list | Invalid when the corresponding stage's final value is validated |
| Mapping at the leaf | Not a valid scalar. Nonempty unknown mapping keys fail existing per-layer key checking even if a later override could replace them; an empty mapping fails final selected-stage positive-integer validation unless repaired by a higher layer |
| Known leaf in an unselected stage with invalid scalar value | Preserve existing selected-stage validation: accept the known key but do not newly validate that stage's value/dependencies. Selecting that stage later rejects the value |
| Unknown stage or unknown setting, selected or unselected | Existing global/per-layer unknown-key rejection remains |
| Selected non-LLM stage with valid value | Validate normally, then ignore operationally; do not instantiate provider/request capacity resources or alter XMP behavior |
| Sequential mode, single image or dry-run with a selected stage | Existing selected-stage validation still runs; a high valid value does not enable same-stage overlap in sequential/single-image execution |
| Valid empty batch | Static selected-stage validation still applies; runtime-only preflight remains skipped |
| Category management | Keep existing management reset/ignore of processing configuration after global unknown-key checking; the new leaf must not introduce processing requirements into category commands |

The REQ's reference to established validation rules is preserved: accepting the key for every registered stage does not globally validate all unused stage values or introduce an unused-stage credential requirement. This is an application of the existing boundary, not a new exception.

### Layering and replacement table

Examples below concern the selected `xmp` stage, with runtime-only preflight disabled for configuration tests. They demonstrate configuration resolution, not XMP execution or provider calls.

| Selected YAML and ordered overrides | Resolved leaf or outcome |
| --- | --- |
| No YAML/override | `1` |
| YAML `3` | `3` |
| YAML `3`, then `--set stages.xmp.max_concurrent_requests=2` | `2` |
| Leaf overrides `2`, then `3` | `3` |
| YAML `3`, leaf override `2`, then `--set 'stages.xmp={}'` | `1`; parent replacement drops the old leaf, defaults are reapplied |
| Parent replacement `{}`, then leaf override `2` | `2` |
| YAML/earlier scalar `0`, repaired by a later leaf `2` | `2`; replaceable value validation occurs after layering |
| Earlier nonempty mapping with unknown child key, later valid scalar | Existing unknown-key error, not repair of forbidden structure |
| Parent `stages={}` | Restore defaults for all omitted stage fields, not only the concurrency leaf; any separately selected LLM stage still needs a valid model setting |
| Valid leaf `3` plus `--no-inter-stage-concurrency` | Resolved leaf stays `3`; execution is image-first sequential, not a mutation of saved configuration |

### Generic operational interpretation

In concurrent batch execution a descriptor with `uses_llm=True` uses its own resolved maximum. A descriptor with `uses_llm=False` has no LLM request capacity to allocate and ignores the leaf. This decision is based on capability, not `desc/json/xmp` string checks. Stages sharing model/provider configuration still have independent ceilings. Sequential and single-image invocation retain their existing serial behavior without rewriting user configuration. Actual acquisition/release and retry arbitration are A2/B3/B4, not B1 implementation work.

## 6. Exact implementation and test handoff

### B1 — configuration

**Production changes:** `src/image_clarus/config.py`: add `COMMON_STAGE_DEFAULTS`, apply it to every stage defaults entry, add `_validate_max_concurrent_requests()`, and integrate selected-stage validation before stage-specific branches. Audit `DEFAULTS`, `_validate_keys()`, `_override_path()`, `_validate_shape()`, `resolve_config()` for the existing behavior above; no new resolver signature, CLI flag or provider field. `src/image_clarus/stage_registry.py` needs no new field or production change for this setting.

**New test file, confirmed absent:** `tests/unit/test_slice5_config.py`. Cover every value/scope/layer row above; built-in `desc/json/xmp` all accept the leaf, selected XMP needs no provider, and registry/config common-key parity holds. Use a fictional configured model/provider for selected LLM static preflight. Include sequential/empty/dry-run static validation, management isolation, unknown keys in unselected stages, parent replacement and scalar repair. Extend existing `tests/unit/test_config.py`, `test_slice4_config.py` and `test_cli_config_acceptance.py` only where shared regressions belong. Do not create this test file during A1.

**Boundary:** Configuration-only delivery. Passing these tests does not demonstrate an actor dispatching concurrent requests.

### B2 — common driver and synchronous adapter

**Production changes:** `src/image_clarus/stage_protocol.py`: selected `StageDriver`, `perform_publication()` and refactored `drive()` preserving its signature and precedence. Keep `mark_transform_started()` callable and its existing stage timing. `src/image_clarus/batch_execution.py` may adapt callback capture/constructor plumbing while retaining its one-request production path until B4. Stage modules retain their `inspect()`, `start_or_resume()` and synchronous runner signatures; do not rewrite stage policies or move snapshot ownership to the coordinator.

**New test file, confirmed absent:** `tests/unit/test_stage_protocol.py`. Use real protocol types and both synthetic/real stage contexts. Required cases:

1. Construction and deferred `advance()` perform no stage/provider/publication work; request-ready polling is idempotent.
2. Two manually interleaved real description contexts complete B before A with matching artifacts, no cross-wiring and isolated callbacks.
3. Two real JSON contexts retain independent attempts/history/snapshots; a failed validation issues a new request ID for only that context. Input/config mutation after capture does not rewrite a retry snapshot.
4. Request start/result callbacks occur exactly once per attempt in the correct sequence; no callback merely from pending-capacity polling. Wrong request, wrong publication acknowledgement, duplicate result/ack and consumed continuation are rejected without a second side effect.
5. Temporary transform binding restores the previous value or absence on normal return and exception; description/JSON/XMP retain their existing distinct transform timing; retries do not double-count a transform.
6. `perform_publication()` passes exact bytes/validator/category to the existing artifact adapter; ArtifactError produces the matching failed acknowledgement while gate/infrastructure exceptions propagate to their established owner.
7. Synchronous `drive()` matches prior observable outcomes through complete submit/await pair, `call_provider` fallback and provider factory; partial pairs keep existing fallback precedence. Exercise both `resume` semantics and existing confirmation/continuation deferral boundaries.
8. Existing skip, recovery, regeneration, validation/provenance, interrupted provider/publication, selected-subset and XMP/no-model compatibility remain intact.

**Preserve/extend:** `tests/unit/test_description_stage.py`, `test_structure_stage.py`, `test_pipeline.py`, `test_batch_execution.py`, `test_batch_concurrency.py`, `test_c2_failure_request_accounting.py`, `test_xmp_integration.py`, `test_xmp_stage.py`; integration lifetimes are later regression evidence.

### B3/B4 actor-facing consumption

B3/B4 can rely on the fixed driver API and identity/state semantics above. An actor advances a ready driver to a request boundary, arranges capacity using A2's later selected transport API, calls `request_started()` once at dispatch, and yields control. On a matching accepted response it resumes the driver on the same actor; another request is another capacity-gated attempt. On a publication it calls the common helper through the existing gated service. A terminal outcome returns to coordinator policy/finalization. No additional stage thread or callback on a provider thread is implied.

A2 still owns collection types, exact slot acquire/release/cleanup boundaries, fairness arbitration and multi-pending stop races. B1/B2 require none of those mechanics to implement/test their own boundaries; they are not unresolved pieces of the A1 driver/configuration API.

## 7. Dependency, reachability and scope checks

- Keep additions in existing `stage_protocol.py` and `config.py`; no new module or package dependency. The driver depends on protocol values and supplied services/callables, not batch execution, concrete stages, configuration loading or state domain policy. Actor/event callbacks are injected downward; stages continue importing the protocol. The publication helper reuses the existing artifact dependency.
- Configuration common-default insertion iterates the existing configuration stage entries; parity against `stage_registry.STAGES` is a test, not a reverse production import or dynamic registration feature. Capability interpretation remains with generic execution.
- Production consumers are the three synchronous stage runners and batch `_run_stage()`. No source path is orphaned by A1 because no implementation is replaced. B2 must migrate the synchronous driver loop to the new shared mechanics and remove its superseded duplicate loop. B4 later removes the old concurrent one-request wait only after supported callers are migrated. Tests alone never justify retaining obsolete production code.
- No new product decision, behavior deferral, live-provider access or additional acceptance gate was needed. No completed Slice 4 marker or historical evidence was changed.

## 8. Executed design and baseline evidence

### Disposable contract probe

A disposable Python/pytest prototype outside the repository exercised the selected driver/configuration approach using existing protocol dataclasses and real description/JSON continuations. Provider calls were prohibited by a failing provider-factory seam. Provider results were supplied explicitly by the probe; no fabricated runtime result is presented as an actual provider response. The configuration probe temporarily supplied common defaults and a selected-stage validation shim to the real resolver **inside the probe process only**. It did not change `config.py` or prove that B1 is implemented.

The probe demonstrated:

- manual B-before-A description completion, matching artifacts, cross-request and cross-publication rejection, consumed continuation handling and per-image callbacks;
- untouched deferred work, JSON retry/history/snapshot isolation with changed persisted input after snapshot capture, and distinct transformation timing;
- artifact failure propagation and callback restoration after a stage exception;
- positive/invalid value cases, real resolver layering/parent replacement/scalar repair, unselected-stage scope, sequential configuration retention, unknown-key rejection and acceptance/default parity for all three registered stages.

At `0.4.5`, Python `3.13.15`, Linux:

```sh
uv run --no-sync --locked --extra dev pytest -q -p no:cacheprovider "$A1_PROBE_DIR/test_contract_probe.py"
```

**Observed:** `24 passed in 1.04s`. An earlier iteration at `0.4.4` passed 20 checks, followed by 24 after adding all-stage and exception-restoration cases; the result above is the rerun after version synchronization. The probe directory is disposable and not a new repository test location. B1/B2 must implement durable tests at the paths frozen in §6. This prototype demonstrates feasibility of the exercised contract, not actual actor overlap, transport capacity, shutdown safety, all adapter branches or Windows runtime behavior.

### Existing focused regressions and delivery checks

Commands ran from the repository root after metadata synchronization:

```sh
uv sync --locked --extra dev
uv lock --check
uv run --no-sync --locked image-clarus --version
uv run --no-sync --locked python --version
uv run --no-sync --locked --extra dev pytest -q -p no:cacheprovider tests/unit/test_config.py tests/unit/test_slice4_config.py tests/unit/test_description_stage.py tests/unit/test_structure_stage.py tests/unit/test_pipeline.py tests/unit/test_batch_execution.py tests/unit/test_cli.py -k 'not description_prompt_from_installed_wheel'
uv run --no-sync --locked --extra dev ruff check .
uv run --no-sync --locked --extra dev ruff format --check .
```

**Observed:** Lock/sync passed; CLI `image-clarus 0.4.5`; Python `3.13.15`; **288 passed in 40.88s**; Ruff `All checks passed!`; format `238 files already formatted`. The `-k` exclusion matched no test in these selected modules; no deselection/skip was reported. Sync emitted a hardlink-to-copy fallback warning across filesystems; installation completed successfully. No dependency upgrades were made.

These are existing baseline/configuration/stage/pipeline/batch/CLI tests, not Slice 5 feature acceptance. No full-suite, distribution build/installed-wheel, live provider, Windows runtime, throughput or multi-pending actor/shutdown pass is claimed. Focused checks do not relabel Slice 4's historical full-suite evidence.

Documentation closeout checks passed: all **12** summary/detailed step headings match; all **4** A1 acceptance rows match this record exactly; A1 is the only completed step and the Phase A gate remains unchecked. All **55** local link occurrences were checked, including **2** fragment targets; the **11** absent future completion-record targets belong only to unchecked steps. The bounded A1-record scan for local home paths, private tooling paths and named internal infrastructure references passed. Working-tree and new-record whitespace checks passed, and the changed-file inventory matches the six files above. No source, repository test, prompt or schema file changed. These structural/privacy checks do not establish runtime concurrency or universal absence of private data.

## 9. Acceptance

- [x] Driver and per-image ownership contracts specify exact APIs, callbacks, snapshots, requests, retries, publication acknowledgements and terminal handling without provider-thread stage execution.
- [x] Configuration table covers default/valid/invalid inputs, existing precedence and selected-stage validation, generic applicability, non-LLM ignore and sequential behavior without broadening unrelated validation.
- [x] Existing synchronous consumers and tests are traced; B1/B2 handoffs are code-ready with no unresolved decision owned by a later step.
- [x] `IMPL-A1-COMPLETED.md` is created, linked in Outputs, and records decisions, file inventory, evidence limits and scope disposition; no feature implementation is claimed.

## 10. Remaining boundary

A2 is not started. It must consume this fixed driver/configuration contract and select capacity-release/cleanup, pending/ready collection, retry/fairness, stop/result/publication and event-wiring mechanics before Phase A completes. B1/B2 are unstarted; their selected APIs and new test paths above are design deliverables only. This record does not authorize starting A2 or any implementation step.
