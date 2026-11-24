# REQ - Image Clarus Slice 4

**Date:** 2026-11-23  
**Status:** Draft for Product Owner review; not yet accepted  
**Project:** `image-clarus`  
**Intended repository path:** `docs/slice-4/REQ-slice-4.md`  
**Parent requirements:** [`../REQ-image-clarus.md`](../REQ-image-clarus.md)  
**Architecture:** [`../HLD-image-clarus.md`](../HLD-image-clarus.md)  
**Previous slice:** [`../slice-3/REQ-slice-3.md`](../slice-3/REQ-slice-3.md)

## 1. Purpose and authority

Slice 4 adds native unattended multi-image processing, observable execution with `--verbose`, and commands to inspect and repair accumulated category state. These capabilities build on the accepted `desc -> json -> xmp` pipeline, persisted sidecars, optional state service, and configuration contracts from Slices 1-3.

This document states required behavior and observable acceptance outcomes, not a prescribed worker/thread implementation. Requirements identified as `S4-` apply to Slice 4. The parent REQ remains the end-state authority; approved Slice 4 choices that supersede an older HLD default must be reconciled in the parent documentation after review. No part of this draft changes previously recorded implementation history.

## 2. Scope boundary

### 2.1 Included

- Native multi-image `process` using directories and supported file patterns/selections, with recursive traversal, depth control, image-format eligibility, and unattended operation.
- A metadata-only batch plan that identifies prospective stage work and routes already-present outputs past skippable stages.
- Optional `--max-work-files` limiting **distinct images initially identified as requiring LLM work**, not raw discovered image count or non-LLM operations.
- `--dry-run` planning and reporting without image/sidecar-content reads, model calls, or state/artifact mutation.
- Optional inter-stage concurrency, **enabled by default**, with at most one worker per selected stage; sequential image-first execution when disabled.
- `--verbose` diagnostics for single-image and batch `process`, including progress and elapsed-time information.
- Category-state CLI operations: `list`, `clear`, and `rebuild` from existing JSON, in a dedicated implementation-plan phase.
- Reuse of existing stage, state, artifact, configuration, error, and interruption behavior; acceptance and regression evidence.

### 2.2 Not included

- Multiple concurrent workers within a single stage or adaptive provider/model-aware worker pools.
- Built-in scheduling, a persistent batch queue, or required per-file job history in SQLite.
- Native search or semantic/embedding search.
- New LLM stages, model/provider protocols, prompt/schema changes, or taxonomy inference/reconciliation.
- XMP-derived category rebuilding or changes to XMP ownership/merge policies.
- Content-aware planning or synchronization inspection of XMP and JSON to predict changes; this is a **deferred Option B**. Metadata-only **Option A must remain available** if B is introduced later, and may remain the default.
- Following discovered symbolic links, advanced exclusion rules, or new image decoder support beyond the existing provider contract.
- A digiKam plugin or dependence on digiKam's Batch Queue Manager.

## 3. Requirements traceability

| Parent area | Slice 4 delivery | Requirements |
| --- | --- | --- |
| Input selection and traversal | Native multi-image discovery, formats, depth and symlink policy | S4-01 to S4-03 |
| Stage independence and resumption | Reusable stage capabilities, read-only planning, runtime recheck | S4-04 to S4-07 |
| External scheduling and failure policies | Work budgets, concurrency, interruption, failure continuation | S4-08 to S4-11 |
| Logging and operational output | Dry-run, verbose progress, metrics and summaries | S4-12 to S4-14 |
| Application state and category guidance | Existing JSON accumulation; list, clear and rebuild commands | S4-15 to S4-17 |
| Prior-slice contracts | Source integrity, stage semantics, state and XMP compatibility | S4-18 |

## 4. Discovery and stage planning

### S4-01 - Multi-image selection and traversal

- Extend the existing `process` operation to accept a single image, a directory, or supported path patterns that select multiple images. Preserve the existing single-image invocation and stage identifiers `desc`, `json`, `xmp`.
- Directory traversal is **recursive by default**, with no depth limit unless configured or overridden. `--max-depth 0` processes files in the selected directory only; `1` includes immediate subdirectories; positive N includes directories through N levels. No limit means unrestricted recursion.
- Discover eligible files in the current directory before descending into its subdirectories, using deterministic traversal order so a work budget selects a predictable set when the collection is unchanged. Actual execution order may differ under concurrent processing.
- Preserve configurable extension eligibility and a CLI override. Initial supported candidates remain `jpg`, `jpeg`, `png`, `webp`, `tif`, and `tiff` unless the selected adapter's actual format support requires an explicit failure. File-extension eligibility does not promise successful model decoding.
- Native patterns include dot-prefixed names and match case-sensitively by default on Linux and Windows. Provide invocation-only `-i` / `--ignore-case` for case-insensitive native-pattern matching in `process` and category `rebuild`. For example, quoted `'photos/*.jpg'` does not match `PHOTO.JPG` by default but does with `-i`; directory extension eligibility remains case-insensitive. Literal-first selection, exact resolved-path identity, ordering and discovered-link rules are unchanged. Shell-expanded arguments cannot be retroactively matched by this option; quote patterns when native expansion is desired.
- Configured image extensions are a nonempty list of dotless ASCII-alphanumeric suffixes. The CLI override rejects empty entries and whitespace; explicit files remain exempt from discovery eligibility.
- Valid empty directories and unmatched valid patterns contribute no files; a fully empty batch succeeds after static selected-stage configuration validation without runtime-only provider or ExifTool preflight. Invalid, missing or unreadable inputs and discovery errors abort the entire initial plan before processing or writes, even when another input is valid.
- Batch processing must not require persistent job state or a particular photo-management program.
- Design and implement discovery for both Linux and Windows using portable Python filesystem APIs, without a Bash dependency or POSIX-only path assumptions. Interpret paths according to the host: Windows accepts drive, UNC, backslash and forward-slash syntax; Linux retains POSIX path behavior. Keep literal-first selection and the approved glob concepts. Define portable ordering, matching, symlink and path-identity behavior with explicit filesystem limitations. Linux can exercise Windows path parsing with pure-path tests; this does not establish Windows filesystem or runtime behavior. Linux remains the required test platform; no Windows machine or cross-platform CI matrix is required.

### S4-02 - Symlink boundaries

- Do not follow symlinks encountered during directory discovery, whether they reference images or subdirectories. Avoid recursive cycles, duplicate traversal through symbolic aliases, and accidental traversal outside the selected collection.
- Preserve existing explicit-file behavior: a directly supplied symlink to an image may resolve to its target. A directly supplied symlink to a directory may designate the starting collection root; discovered symlinks below it are still not followed.
- Apply the same policy to category rebuild. On filesystems without symbolic links, ordinary traversal applies without special cases.

### S4-03 - Independent traversal controls

- Batch `process` and category `rebuild` must each support an independently configured directory-depth limit with a CLI override. Both default to unlimited recursive traversal.
- Directory depth is distinct from Slice 3's prompt-macro `max_depth`, which truncates *category paths* and must retain its existing semantics.
- Rebuild should reuse the same discovery rules where applicable, without coupling its depth setting to batch processing.

### S4-04 - Stage capability metadata

- Expose stage capabilities through reusable stage metadata instead of stage-name conditionals in batch orchestration. The approved concepts are:
  - `usesLLM`: whether execution is delegated to an LLM and counts as potential LLM work.
  - `skipIfValidOutputExists`: whether an existing valid owned output may bypass the stage under its current configuration.
- For existing stages, `desc` and `json` have both capabilities; `xmp` has neither (`usesLLM=false`, `skipIfValidOutputExists=false`). XMP can still return `skipped` for `no_change` **during execution**; it is not automatically bypassable from existence alone.
- Effective skip eligibility must honor `--regenerate` and relevant stage configuration. Future stages should be incorporable through these capabilities without batch-specific knowledge of XMP or other stage names.

### S4-05 - Metadata-only initial plan

- Build an initial plan from discovered image paths, directory entries, extension eligibility, and existence metadata for relevant sidecars. **Do not open image files, read sidecar contents, invoke ExifTool, call models, or mutate state/artifacts during planning.** Reading configuration to resolve selected behavior is permitted.
- Existence is a **provisional** prediction of `skipIfValidOutputExists`, not validation of a sidecar's contents. Planning must not claim that mere existence proves an artifact valid or that XMP is synchronized.
- The plan identifies selected files, stage candidates, prospective bypasses, initial queues/work counts, and enough tracking information for batch metrics. A plan is scoped to the current invocation; no persisted queue is required.
- Produce the plan before running the batch. Implementation details of queue structures and memory representation are deferred to design.

### S4-06 - Front-loaded bypass and queue routing

- When adding an image to a selected stage's queue, use its capability metadata and the planned skip decision to bypass prospective existing-output work and immediately forward the image to the next **selected** stage. The next stage applies the same rule, potentially forwarding further without waiting for upstream LLM inference.
- Initial routing also bypasses selected LLM stages for images excluded by the work budget, forwarding them to the earliest remaining selected non-LLM stage. Admitted images progress through selected stages as their work completes or skips; non-LLM stages receive images progressively, including those routed directly to them. Apply capabilities generically, not stage-name-specific XMP budgeting.
- Example: among 1,000 eligible files, 400 with existing descriptions can reach `json` immediately while the `desc` worker processes the other 600. Subsequent existing-JSON candidates can similarly advance to XMP.
- After a stage handles an image, forward it according to the established stage continuation and prerequisite policies, whether the stage completed or skipped due to an existing output. Failures, missing prerequisites and interruptions are **not** equivalent to successful `output_exists` skips.
- A selected subset, such as `--stages json,xmp` or `--stages desc`, must execute without adding omitted prerequisite stages. Preserve dependency handling using persisted artifacts.

### S4-07 - Execution remains authoritative

- Queue consumption must reuse the existing single-image stage behavior, including validation/recovery, skip rechecks, regeneration, failure classification, and safe writes. A file may have changed since planning, including due to a different process; actual stage results override predictions in reporting.
- If an image initially predicted to need no selected LLM work is found to need corrective LLM inference because a sidecar is missing or invalid, permit that work even when the initial admission budget is exhausted. Existing recovery, validation, failure and continuation policies still govern whether work proceeds; a prediction is never itself a validated result.
- Where a planned bypass requires execution-time behavior (notably category accumulation from an existing valid JSON artifact), execute that behavior without introducing a model call merely to confirm a skip.
- Initial plan membership and `--max-work-files` admission **do not change retroactively** due to runtime skips, newly created sidecars, or external work. Report predicted-versus-actual outcomes accurately.
- Planning must not introduce a second, divergent implementation of stage completion semantics; isolate reusable inspection/decision logic as needed while keeping content-based validation in execution.

## 5. Work limits and concurrency

### S4-08 - `--max-work-files` limits initial LLM-work admission

- Provide optional positive-integer `--max-work-files N` with configuration support. Without a limit, no LLM work-file budget is imposed.
- An image consumes **one** unit if the initial metadata-only plan identifies at least one **selected** `usesLLM` stage that needs execution; it does not consume one unit per stage. Existing-output bypasses do not consume units unless regeneration makes the selected LLM stage require work.
- Admit up to N qualifying images in deterministic discovery order. One admitted image may execute every selected LLM stage while consuming one slot; images initially predicted to require no LLM work consume no initial admission slots. The admission limit counts images, not stage executions, model requests, retries or non-LLM operations.
- The limit applies to **initial planned admission**, not a hard maximum on actual distinct images receiving LLM work. Runtime skips do not reclaim or replace admitted slots. A file needing multiple LLM stages still counts once for initial admission.
- Images known at planning to need LLM work but excluded by the budget remain excluded from LLM stages. Separately, images initially predicted to need no selected LLM work may receive corrective inference after authoritative validation discovers missing or invalid sidecars, even when the budget is exhausted. Such corrective overruns may exceed N by any amount; they are not inherently capped at twice N. Normal recovery, validation and continuation policies apply.
- When a predicted-existing JSON sidecar of a known budget-excluded image is inspected for a selected stage and proves invalid, report its real stage failure and apply the configured continuation policy; do not issue excluded LLM work or fabricate a successful skip.
- Selection and admission identity use exact host-resolved path spellings. Case-variant or other aliases that refer to one physical file but retain different resolved spellings may be processed and counted separately; hard-link paths remain distinct. Do not assume all Windows filesystems are case-insensitive or collapse distinct case-sensitive files.
- Non-LLM stages do not consume the budget. An `xmp`-only run may process all 10,000 eligible images even with `--max-work-files 1000`; the limit is not an overall cap on discovered or non-LLM-processed files.
- In mixed-stage runs, images excluded from LLM work bypass selected LLM stages but remain eligible for all selected non-LLM stages, subject to normal prerequisites, skips, failures, interruption and continuation policies. A missing prerequisite produces its ordinary outcome, not an additional LLM call. Users budget LLM workload by image while inter-stage concurrency allows stages for different images to overlap.
- The limit does not promise a hard bound on memory, runtime, or total provider requests, and its relationship to non-LLM execution must be clearly reported.

**Routing example:** For 10,000 images with `desc,json,xmp` selected, assume 6,000 have both description and JSON, 1,000 have description only, and 3,000 have neither. Without a limit, their initial predicted queues are 6,000 XMP, 1,000 JSON and 3,000 description; the remaining images advance to XMP as upstream work finishes. With `--max-work-files 1000`, if deterministic discovery admits 1,000 images that need both LLM stages, the initial predicted queues are 1,000 description, zero JSON and 9,000 XMP (6,000 with existing JSON and 3,000 excluded from LLM work). The admitted 1,000 move through JSON and then XMP as work completes. If existing predicted outputs validate, admitted LLM stages succeed, no earlier stage stops an image, and execution is not interrupted or aborted, XMP evaluates all 10,000; missing JSON yields the ordinary prerequisite outcome, not necessarily an XMP write. Invalid existing outputs and other earlier-stage failures instead follow the configured continuation policy. The admitted 1,000 may produce 2,000 LLM stage executions while consuming 1,000 image slots. These are provisional routing predictions, not proof of sidecar validity.

**Corrective-overrun example:** With 1,000 initially admitted images, if one additional image initially predicted to need no LLM work requires a corrective description execution and applicable policies permit it, actual distinct LLM-work images become 1,001. If all admitted images execute both LLM stages, actual description executions are 1,001 and JSON executions 1,000. Report the one corrective-overrun image separately from the 1,000 initially admitted images.

### S4-09 - Inter-stage concurrency enabled by default

- With concurrency **enabled** by default, each selected stage has at most one active worker; different selected stages may process **different images** simultaneously, with stage-to-stage forwarding as work becomes eligible.
- This allows a local vision stage and a separate JSON model/backend to overlap without introducing multiple concurrent requests **within the same stage**.
- Provide a configuration and CLI control to disable inter-stage concurrency.
- With concurrency **disabled**, run selected stages sequentially for each image, then advance to the next image (image-first). This favors category guidance being available from previously processed images over throughput.
- Do not require a model-aware scheduler, multiple workers per stage, or a permanent queue for this slice.

### S4-10 - Category-guidance timing under concurrency

- Preserve existing state-macro expansion and category accumulation semantics. Under concurrency, a description may begin before a previous image's JSON categories have been accumulated; this timing dependence is accepted.
- Resolve state **per image**, using the existing Slice 3 precedence: explicit CLI selection, YAML selection, nearest initialized CWD ancestor, nearest initialized image-directory ancestor, then in-memory state. Do not select one persistent repository for an entire batch merely because an earlier image resolved to it. Images sharing an explicitly selected or CWD-discovered repository continue to share that repository; when neither takes precedence, images in different collections can resolve to their respective repositories.
- Apply the existing visible, nonblocking state-failure behavior to each affected image without silently selecting another persistent repository. Keep the resolved state associated with that image for its prompt expansion and eligible category accumulation across selected stages, including concurrent execution.
- Under sequential image-first execution, eligible JSON category accumulation for one image should occur before the following image begins, so the next image can use the latest available category guidance.
- No additional model call, taxonomy normalization, or cross-stage synchronization barrier is required solely to make category prompts deterministic.

### S4-11 - Stop, resume and failure handling

- Retain the existing missing-prerequisite distinction: an explicitly selected single image defaults to failure; directory or pattern batch selections default to skip-and-continue. Preserve configurable overrides and selected-stage static validation; nonempty real execution also performs runtime preflight before stage writes.
- Reuse stage failure policies and structured error categories. An individual file failure must not silently mark its missing outputs complete or strand unrelated eligible files in the current run.
- On SIGINT/SIGTERM, coordinate stage workers to stop accepting additional work, cancel in-flight inference when safe, and preserve the existing safe-write and recovery guarantees. Report actual completed/skipped/failed work rather than treating an interrupted plan as complete.
- A subsequent invocation resumes by rescanning and using existing sidecars, without requiring a durable job database. Preserve the documented lock-free sidecar concurrency limitations and the independent SQLite state-concurrency contract.

## 6. Dry-run, diagnostics and reporting

### S4-12 - Dry-run

- Provide `--dry-run` on `process` (single-image or multi-image) to show the planned selection and prospective per-stage work/bypasses without executing stages.
- Dry-run performs **no model calls, XMP processing, image/sidecar-content reads, artifact writes, category accumulation, or persistent-state mutations**. Directory entry and file-existence metadata may be inspected.
- Apply the same selection, depth, symlink, selected-stage, regeneration and work-budget rules as an execution plan. Show planned work admission, stage routing and counts, which files are counted toward the LLM work budget and when the budget is reached.
- Permit aggregate summaries without retaining all per-file plan records. Per-file output, when requested, may be streamed rather than accumulated in memory. Dry-run must report a memory estimate, clearly labeled as an estimate rather than a measurement or guaranteed bound; its scope and estimation method are design work.
- Every completed dry-run plan reports the numeric labeled estimate. If parsing, configuration or selection fails before the plan completes, report that the estimate is unavailable instead of inventing a number.
- Dry-run results and memory estimates cannot predict all execution-time corrections; malformed existing outputs, XMP no-change decisions and external modifications may produce different actual outcomes and corrective LLM overruns.

### S4-13 - `--verbose` for single and batch execution

- Add `--verbose` to the existing single-image `process` path and to native multi-image `process`.
- Expose image/stage identification, start and completion/skip/failure progress, meaningful reasons, elapsed time and an end-of-run summary. For a batch, provide per-stage and overall plan-relative progress so the user can see how much accounted-for work remains.
- Clearly distinguish **planned bypass**, **actual stage skip**, **completed stage**, **failure**, and **interrupted/not attempted** work; progress reaching 100% must not imply all work succeeded.
- Preserve existing concise output and exit semantics when verbosity is not requested. Keep diagnostics on the appropriate output channel, avoid disclosing configured secrets, and define script-friendly output details during design.

### S4-14 - Batch summary and metrics

- Report eligible files discovered, the initial admitted LLM-work image count, distinct additional images receiving corrective LLM work (corrective overruns), actual distinct images receiving LLM work, actual per-stage execution counts, planned bypasses by stage, completed/skipped/failed stage counts, runtime deviations from the plan, and total elapsed time.
- For new batch and category-management commands, use exit 0 for complete success or ordinary skips; 1 for failure or partial results; 2 for invalid input or configuration; and `128 + signal` for a handled signal. Preserve existing single-image and categorized startup exceptions, including authentication exit 1.
- Distinguish the number of **files** from the number of **stage operations**, especially when one file needs both `desc` and `json`.
- Provide authoritative file/stage outcome reporting independent of digiKam status or provider request dashboards. The summary must reflect partial completion and failure/interruption without rewriting valid sidecars.

## 7. Category-state CLI operations

**Implementation-plan separation:** Give the following category-management capability its **own phase**, separate from batch discovery/execution. It belongs in Slice 4 and must not be deferred merely because it is independently implementable.

### S4-15 - List categories

- Provide a CLI operation conceptually equivalent to `image-clarus state categories list` to show the category paths currently held in the selected state repository.
- Use existing category state and state-directory selection semantics. Report inaccessible or invalid state visibly instead of silently presenting an empty persistent collection.
- Listing must be **read-only**, including repository opening and validation: do not initialize, migrate, clear, update or otherwise mutate persistent state, regenerate images, or call a model. If the repository cannot be listed without migration, report the condition rather than migrating it as part of list. Precise diagnostic/exit form remains design work.
- Read-only means no change to logical stored data or schema, including during opening and validation. Normal SQLite journal, WAL and shared-memory activity and operating-system-maintained access-time updates are permitted; do not restore timestamps. Do not reject a WAL repository merely because such activity may occur; report genuine access, integrity or other read failures visibly. Use Python's standard-library `sqlite3` with normal Windows and Linux clone/install workflows, without a native extension, bundled SQLite, detached snapshot or custom packaging. This Product Owner decision supersedes the earlier physical-nonmutation and unsafe-WAL-rejection requirements.

### S4-16 - Clear categories

- Provide a CLI operation conceptually equivalent to `image-clarus state categories clear` to remove **all known categories** from the selected repository while leaving other state domains and all image/sidecar files untouched.
- Do not silently substitute another repository or claim success when a requested persistent-state mutation fails. Keep this suitable for explicit noninteractive CLI usage.
- A registered migration may run for clear; migration and clear must be admitted in the same transaction. Failures must be visible and preserve the existing atomic migration contract.

### S4-17 - Rebuild categories from existing JSON

- Provide a CLI operation conceptually equivalent to `image-clarus state categories rebuild` that **adds** categories from existing `.desc.json` sidecars in a selected collection to the selected repository's existing categories; rebuild never deletes known categories or changes other state domains.
- Reuse the **same supported JSON envelope, recognized schema identities, candidate extraction, validation, deduplication and full-path storage rules** as existing Slice 3 accumulation. Do not derive categories from XMP, invent new taxonomy rules, or regenerate JSON.
- Rebuild supports recursive discovery by default, independent `--max-depth` configuration/override, and the S4-02 symlink policy.
- Continue past invalid or unreadable inputs and report inspected files, successes, skips and failures, including how many supplied eligible categories. Valid accumulation may remain after partial failure without rollback; report partial outcomes accurately. An empty result makes no changes. Concurrent updates follow the existing state-storage concurrency contract.
- For example, if 997 of 1,000 JSON inputs are processed successfully and three fail, retain prior categories, accumulate eligible categories from successful inputs, and report the three failures.
- Use the chosen state repository explicitly and consistently without silently substituting another persistent repository. To reconstruct categories from a selected collection, users can explicitly clear and then rebuild; rebuild alone retains prior categories. Concurrent activity follows the existing state-storage concurrency contract.
- Use configured state or the CWD-selected repository as the single destination; rebuild source roots do not select it. An explicit `--state-dir` overrides that selection. Accept explicit `.desc.json` inputs and include orphan sidecars, subject to the existing symlink boundary.
- A registered migration may run for rebuild with eligible categories, with migration and the first eligible update admitted in the same transaction. An empty or no-category rebuild never initializes, migrates or otherwise changes logical state.

## 8. Compatibility and acceptance

### S4-18 - Preserve accepted Slice 1-3 behavior

- Existing single-image `process` commands, stage identifiers, stage subsets, selected-stage validation, prompt/model overrides, state resolution precedence, optional/nonblocking state during ordinary processing, and source-image immutability must remain compatible.
- Preserve description/JSON create-only and explicit-regeneration behavior, persisted handoffs, JSON provenance/envelope compatibility, XMP no-change/merge policies, ExifTool isolation, and safe-write/recovery behavior.
- Category-state mutation failures may fail their dedicated commands; they must not make otherwise successful ordinary image processing fail merely because state is optional.
- Unit tests should remain the primary iterative implementation harness, with focused behavioral experiments and truthful observed regression evidence; no prescribed historical RED-before-implementation gate.

### Required acceptance outcomes

| Area | Observable outcome |
| --- | --- |
| Discovery | A directory/pattern selection discovers eligible images in documented order, recurses by default, honors depth 0/1/N and extension overrides, and does not follow discovered symlinks |
| Single-image compatibility | Existing `process image.jpg --stages ...` behavior remains correct; an explicit image symlink still resolves as before |
| Planning | For known sidecar arrangements, metadata-only planning predicts per-stage work and bypasses without opening image/sidecar content or modifying state |
| Queue bypass | Existing descriptions and JSON reach downstream selected stages before unrelated upstream inference finishes; selected subsets do not implicitly run missing stages |
| Work budget | `--max-work-files N` admits at most N initially identified LLM-work images; regeneration counts, runtime skips do not replenish slots, and known budget-excluded images remain excluded from LLM work. An admitted image may execute both LLM stages for one slot; XMP-only work is uncapped. For the synthetic 10,000-image example with limit 1,000, verify all 10,000 reach XMP evaluation through progressive routing when predicted existing outputs validate, admitted LLM stages succeed, no earlier stage stops an image, and execution is not interrupted or aborted; missing inputs produce ordinary prerequisite outcomes, not necessarily writes |
| Corrective overruns | When an initially no-LLM-work image has a missing or invalid sidecar at execution and existing policies permit correction, inference can occur even with admission full; verify actual distinct LLM-work images can exceed N, known budget-excluded images remain excluded, and initial admission, corrective-overrun images, actual distinct images and per-stage executions are separately reported |
| Concurrency | Default inter-stage overlap occurs on different images with one active worker per selected stage; disabling it yields image-first sequential behavior |
| Category timing | Skipped valid JSON can still accumulate categories during execution without model inference; dry-run does not accumulate; sequential mode exposes completed prior-image categories to subsequent prompts |
| Per-image state resolution | A multi-collection batch preserves CLI > YAML > CWD ancestry > each image's ancestry > memory, including separate image-ancestor repositories when higher-priority choices are absent; prompt reads and eligible accumulation use each image's selected state in sequential and concurrent modes |
| Rechecks and failures | Actual stage execution detects changes since planning and retains recovery, prerequisite, continuation and error semantics |
| Dry-run | Correct plan/aggregate counts, work-budget behavior and a clearly labeled memory estimate, with no inference, ExifTool operation, sidecar-content reads or mutations |
| Verbose and metrics | Single-image and batch execution show useful timing/status; batch progress and final counts distinguish predicted skips from actual results and failures |
| Interruption/resume | Graceful stop preserves completed artifacts and reports partial results; a later run skips prior valid outputs |
| Categories list/clear | List reflects persistent categories without changing logical data or schema or initializing/migrating; normal SQLite journal/WAL/shared-memory activity and read access-time updates are permitted. Exercise WAL reads and report genuine failures and required migration rather than silently migrating or presenting a failed read as an empty collection. Clear removes categories only, leaving sidecars and unrelated state intact; any migration and clear share a transaction |
| Categories rebuild | Rebuild adds recognized JSON categories without deleting existing categories or other domains, deduplicates, honors independent traversal depth, and invokes neither XMP nor inference. Invalid/unreadable inputs do not prevent processing others; successes, skips and failures are reported, valid partial accumulation remains, empty results make no changes, and concurrent updates respect the existing storage contract. Explicit clear followed by rebuild permits reconstruction |
| Regression | Prior accepted stage, artifact, state, config, XMP and source-image contracts remain intact |

Use synthetic fixtures and isolated repositories for verification, with limited optional real-image/manual testing. Measure actual concurrency, progress, and summary behavior rather than relying only on inferred outcomes. The implementation plan defines precise commands, test harnesses, and evidence capture.

## 9. Design decisions and parent-document reconciliation

The implementation plan must resolve exact option/configuration keys beyond those approved here, stage descriptor representation, plan entry representation, directory sorting, queue shutdown/forwarding mechanics, concurrency toggle syntax, progress output format and channels, category-command CLI grammar, and error/result aggregation. These are design decisions **within** the requirements, not permission to expand the product scope.

The Product Owner decided that initially known LLM-work images excluded by the admission budget bypass selected LLM stages but remain eligible for selected non-LLM stages, subject to normal prerequisites and continuation policy. Unexpected corrective inference for images initially predicted to need no LLM work may exceed the initial budget; XMP-only runs remain uncapped. Category rebuild is additive and best-effort, rather than replacement.

The Product Owner also selected existing per-image state resolution for batches, read-only category listing, CWD-selected management state with an explicit override, explicit/orphan JSON sidecars, and registered migrations for clear and nonempty rebuild only. Preserve existing user-facing behavior where applicable; the logical read-only and standard-library SQLite decision above supersedes the earlier physical-nonmutation and unsafe-WAL-rejection policy. Other unselected policy questions remain design work rather than being inferred from these decisions.

**Slice 4 Phase A design-completion requirement:** The implementation plan must make completion of Phase A a prerequisite for Phase B. No significant design decision may remain TBD at Phase A close. Produce decision tables and documented contracts covering (1) sidecar bypass predictions, validation, recovery, post-planning changes and corrective overruns; (2) queue routing and downstream coordination in concurrent and sequential modes; (3) category operations, errors, interruption and concurrent access; (4) management-command state selection and multi-collection processing; and (5) duplicate selections, failure continuation, work accounting and progress. Each significant decision needs an outcome, rationale and associated acceptance scenario. Product behavior decisions require Product Owner approval before Phase A closes; minor coding choices may remain for implementation. Resolve early forwarding without treating a prediction as validated or sacrificing overlap of unrelated images.

The parent REQ and HLD have already been reconciled to the planned concurrent default, recursive traversal, depth and symlink controls, and Slice 4 roadmap. Reconcile these documents forward as decisions evolve; preserve prior-slice closeout and historical records. Native search remains outside Slice 4.

## 10. Completion boundary

Slice 4 can be accepted when native batch planning and execution, metadata-only dry-run, the LLM work-file budget, default optional inter-stage concurrency, controllable traversal, verbose progress and metrics, and category list/clear/rebuild meet the outcomes above without regressing Slices 1-3.

Native search, model-parallel workers, content-aware planning Option B, built-in scheduling and digiKam-specific integration are **not** Slice 4 acceptance conditions.
