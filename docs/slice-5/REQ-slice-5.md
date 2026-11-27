# REQ - Image Clarus Slice 5

**Date:** 2026-11-27  
**Status:** Draft for Product Owner review  
**Project:** `image-clarus`  
**Intended repository path:** `docs/slice-5/REQ-slice-5.md`  
**Parent requirements:** [`../REQ-image-clarus.md`](../REQ-image-clarus.md)  
**Architecture:** [`../HLD-image-clarus.md`](../HLD-image-clarus.md)  
**Previous slice:** [`../slice-4/REQ-slice-4.md`](../slice-4/REQ-slice-4.md)  
**Previous implementation:** [`../slice-4/IMPL-PLAN-slice-4.md`](../slice-4/IMPL-PLAN-slice-4.md)

## 1. Purpose and authority

Slice 5 adds **configurable concurrent LLM requests per processing stage** to increase the throughput available from models and providers that can serve multiple requests simultaneously. It builds on Slice 4's native batch execution, stage actor coordination, resumable inference, work admission, and interruption handling.

This slice has one functional objective. Its remaining requirements preserve established architecture and behavior while increasing the number of outstanding inference requests permitted within a stage. `S5-` identifies Slice 5 requirements. This document defines behavior and acceptance outcomes; implementation mechanics belong in the implementation plan. Historical Slice 1-4 requirements and evidence retain their original meaning.

## 2. Scope boundary

### Included

- A per-stage `max_concurrent_requests` configuration setting for every registered stage, with a default of `1`.
- Up to the configured number of outstanding inference requests within a selected LLM stage, for distinct images.
- Retention of the existing single-actor-per-stage architecture and authoritative, serial stage decision and publication boundaries.
- Preservation of existing batch planning, stage ordering, state, result accounting, failure policies, and stop/resume behavior.
- Focused concurrency and regression verification.

### Excluded

- Additional stage actors or concurrent workers executing stage logic within the same stage.
- Adaptive or automatically tuned concurrency, global/provider/model-level capacity scheduling, shared model quotas, or performance guarantees.
- New model/provider interfaces, transport protocols, request retry policies, or stages.
- Changes to discovery, `--max-work-files` admission, category semantics, prompt/schema contents, XMP publication policy, or sidecar locking.
- Scheduling, a persistent job queue, native search, or unrelated CLI features.

## 3. Requirements

### S5-01 - Generic per-stage configuration

- Support `stages.<stage-name>.max_concurrent_requests` through the existing YAML and `--set` configuration facilities and their established precedence and validation rules. A separate dedicated CLI option is not required.
- The value is a **positive integer**, rejecting booleans, zero, negative values, and non-integers. The default is **`1`** for each registered stage.
- The key is consistently accepted and validated for **every registered stage**, including stages that do not use an LLM. For a non-LLM stage, the value is **ignored during execution**, with no operational side effects.
- Application of the limit depends on the stage's generic LLM capability, not checks for the `desc`, `json`, or `xmp` names. Preserve existing unknown-stage and unknown-setting rejection rules.

### S5-02 - Concurrent inference limit

- With concurrent batch execution enabled, each selected LLM stage may have up to its own configured number of **outstanding provider requests** simultaneously, involving **different images**. A stage must never exceed that limit.
- Limits are **independent per stage**, not a combined ceiling across stages. A request from another stage may be outstanding concurrently under that stage's own limit, even if both stages use the same model or provider.
- All provider requests, including configured JSON validation-feedback retries, occupy a stage request slot while outstanding. A retry must not bypass or exceed the configured limit; existing retry and image-admission semantics are unchanged.
- Responses may complete in any order. Request overlap must not cause duplicate inference for the same image/stage attempt, duplicate publication, or an image advancing before its authoritative stage result.
- The setting is a concurrency **maximum**, not a requirement to keep every slot busy or a guarantee of better throughput or latency.

### S5-03 - Preserve stage actor ownership

- Retain **one long-lived stage actor per selected stage** and the existing coordinator ownership of lifecycle, queues, and terminal results. Increasing concurrency must **not** create additional actors that independently execute stage logic.
- The stage actor remains the sole executor of its stage's inspection, continuation decisions, validation, and publication. These operations remain **serial within the stage**; only provider requests may overlap.
- Preserve each image's resumable stage continuation, request identity, generation, ownership, and authoritative outcomes while several different images have pending requests in the same stage. A response may resume only its matching live continuation.
- While requests are outstanding, preserve the ability to confirm/bypass unrelated ready images and dispatch eligible inference up to the limit. Pending responses and queued work must not be indefinitely stranded by request overlap or confirmation traffic.
- Retain existing provider-child isolation, resource ownership, cancellation, and cleanup boundaries. Detailed scheduling and data structures are implementation decisions.

### S5-04 - Preserve batch and stage semantics

- Keep the current metadata-only initial plan, provisional bypasses, authoritative execution rechecks, stage capability metadata, selected-stage subsets, and early forwarding. Do not introduce a second planning model or implicit prerequisites.
- `--max-work-files` continues to limit **distinct images initially admitted for predicted LLM work**; it does not limit simultaneous requests. An admitted image may use multiple stages and existing permitted retries without additional admission slots. Known budget exclusions remain excluded; allowed corrective inference retains its current rules.
- A single image never executes multiple stages simultaneously or publishes more than one terminal outcome for a stage. Preserve current prerequisite, regeneration, safe-write, backup/recovery, and XMP behavior.
- Preserve per-image state resolution and category accumulation. Cross-image category visibility under concurrent processing remains timing-dependent; do not add a global synchronization barrier.
- **`--no-inter-stage-concurrency` retains image-first sequential execution**, regardless of configured request limits. A single-image invocation also retains existing behavior and output contracts.

### S5-05 - Preserve interruption and failure handling

- SIGINT, SIGTERM, or a configured batch abort must prevent new inference dispatch, request cancellation of **all** outstanding cancellable requests, and settle each affected image exactly once with truthful results.
- Preserve protection and draining of already-admitted artifact publications, cleanup/reaping of owned provider children, and safe-write recovery semantics. No pending request, image token, or worker resource may be silently abandoned or leave the batch hung.
- Provider failures, timeouts, invalid results, validation retries, and worker failures retain their current categorization and `continue`, `stop`, or `abort` policies. A failure of one image does not implicitly fail other images or change the configured concurrency limit.
- Preserve fresh-invocation resumption by rescanning existing sidecars. Do not add a durable job database or claim cancellation of remote computation after local termination.

### S5-06 - Preserve observable accounting

- Existing verbose output and batch summaries must remain accurate with out-of-order requests and completions, including per-stage evaluated/transformed/completed/skipped/failed/interrupted counts, request and retry counts, distinct LLM-work images, corrective work, and plan-relative progress.
- Track each request and terminal stage outcome once. Do not mistake simultaneous provider calls for additional admitted images or consider fully accounted progress proof of universal success.
- Preserve meaningful sanitized failure categories, existing stdout/stderr ownership, exit codes, and concise single-image output. No new telemetry subsystem or reporting format is required.

### S5-07 - Backward compatibility and verification

- With settings omitted or set to `1`, preserve the behavior established and verified through Slice 4, including stage overlap across different stages, early forwarding, sequential mode, and resource cleanup.
- Exercise real overlapping provider requests using controlled local providers and observable barriers, without relying on wall-clock timing or GPU utilization to prove concurrency. Verify limits `1` and `2`, and a higher configured limit to establish that `2` is not hardcoded.
- Verify independent per-stage limits, non-LLM ignore behavior, configuration precedence and rejection, selected-stage subsets, budget independence, retries, out-of-order completion, and one terminal outcome per image/stage.
- Exercise provider failure, worker failure, interruption, abort and shutdown with multiple requests pending, plus the existing safe-publication and resume boundaries.
- Run focused and appropriate full regressions for prior-slice functionality. Record actual application/runtime versions and evidence limits; Linux is the required test platform, while Windows runtime claims require Windows execution.

## 4. Observable acceptance outcomes

| Area | Required evidence |
| --- | --- |
| Configuration | Omitted setting and explicit `1` produce the existing effective limit; `2` and a higher positive integer validate; invalid values fail; `--set` follows existing precedence; a non-LLM stage accepts but ignores the value. |
| Same-stage overlap | A controlled provider holds request A while a second request from the **same stage** starts for image B with limit `2`. With limit `1`, B does not start until a slot is released. No configured limit is exceeded. |
| Independent stages | Distinct stage limits operate independently, including when their model/provider configuration is shared. Stage logic/publication is still serial within each stage. |
| Out-of-order completion | B completes before A without cross-wiring results, duplicating requests/publication, violating image-stage order, or corrupting final accounting. |
| Retry and admission | Validation-feedback retries consume request capacity; work-file admission, corrective overruns, and known exclusions retain their established behavior. |
| Failure and shutdown | Multiple pending requests are cancelled/settled correctly on stop or abort; owned subprocesses and protected publications follow the existing contracts; no hang or leaked image lifecycle. |
| Compatibility | Sequential image-first mode overrides limits above `1`; omitted/`1` settings preserve Slice 4 behavior and reporting; regression evidence has explicit tested versions and limitations. |

## 5. Implementation boundary

The present Slice 4 coordinator has one long-lived actor per selected stage, an outstanding-request slot per stage, and resumable per-image stage continuations. Slice 5 changes **only the outstanding-request concurrency constraint** and the coordination required to uphold these requirements. The implementation plan must address multiple pending continuations, completion arbitration, capacity release, failure and cancellation races, and serial actor ownership without silently widening this slice to a general worker-pool redesign.

Slice 4's original one-outstanding-request design remains accurate historical evidence. Current architecture and usage documentation should describe the new effective limits only after implementation and verification; do not retroactively rewrite previous-slice acceptance claims.

## 6. Acceptance boundary

Slice 5 is complete when the configurable per-stage request limit operates as specified, the concurrency and failure scenarios above have observed evidence, and the prior stage, batch, artifact, and CLI contracts remain intact. This REQ does not impose a specific throughput-improvement percentage or require a live provider benchmark for acceptance.
