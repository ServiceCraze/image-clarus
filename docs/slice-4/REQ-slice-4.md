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
- Batch processing must not require persistent job state or a particular photo-management program.

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
- Example: among 1,000 eligible files, 400 with existing descriptions can reach `json` immediately while the `desc` worker processes the other 600. Subsequent existing-JSON candidates can similarly advance to XMP.
- After a stage handles an image, forward it according to the established stage continuation and prerequisite policies, whether the stage completed or skipped due to an existing output. Failures, missing prerequisites and interruptions are **not** equivalent to successful `output_exists` skips.
- A selected subset, such as `--stages json,xmp` or `--stages desc`, must execute without adding omitted prerequisite stages. Preserve dependency handling using persisted artifacts.

### S4-07 - Execution remains authoritative

- Queue consumption must reuse the existing single-image stage behavior, including validation/recovery, skip rechecks, regeneration, failure classification, and safe writes. A file may have changed since planning, including due to a different process; actual stage results override predictions in reporting.
- Where a planned bypass requires execution-time behavior (notably category accumulation from an existing valid JSON artifact), execute that behavior without introducing a model call merely to confirm a skip.
- Initial plan membership and `--max-work-files` admission **do not change retroactively** due to runtime skips, newly created sidecars, or external work. Report predicted-versus-actual outcomes accurately.
- Planning must not introduce a second, divergent implementation of stage completion semantics; isolate reusable inspection/decision logic as needed while keeping content-based validation in execution.

## 5. Work limits and concurrency

### S4-08 - `--max-work-files` limits distinct images needing LLM work

- Provide optional positive-integer `--max-work-files N` with configuration support. Without a limit, no LLM work-file budget is imposed.
- An image consumes **one** unit if the initial metadata-only plan identifies at least one **selected** `usesLLM` stage that needs execution; it does not consume one unit per stage. Existing-output bypasses do not consume units unless regeneration makes the selected LLM stage require work.
- The limit uses the **initial plan**. Runtime rechecks do not reclaim or replace budgeted images, and a file needing multiple LLM stages still counts once.
- Non-LLM stages do not consume the budget. An `xmp`-only run may process all 10,000 eligible images even with `--max-work-files 1000`; the limit is not an overall cap on discovered or non-LLM-processed files.
- The limit does not promise a hard bound on memory, runtime, or total provider requests, and its relationship to non-LLM execution must be clearly reported.

### S4-09 - Inter-stage concurrency enabled by default

- With concurrency **enabled** by default, each selected stage has at most one active worker; different selected stages may process **different images** simultaneously, with stage-to-stage forwarding as work becomes eligible.
- This allows a local vision stage and a separate JSON model/backend to overlap without introducing multiple concurrent requests **within the same stage**.
- Provide a configuration and CLI control to disable inter-stage concurrency.
- With concurrency **disabled**, run selected stages sequentially for each image, then advance to the next image (image-first). This favors category guidance being available from previously processed images over throughput.
- Do not require a model-aware scheduler, multiple workers per stage, or a permanent queue for this slice.

### S4-10 - Category-guidance timing under concurrency

- Preserve existing state-macro expansion and category accumulation semantics. Under concurrency, a description may begin before a previous image's JSON categories have been accumulated; this timing dependence is accepted.
- Under sequential image-first execution, eligible JSON category accumulation for one image should occur before the following image begins, so the next image can use the latest available category guidance.
- No additional model call, taxonomy normalization, or cross-stage synchronization barrier is required solely to make category prompts deterministic.

### S4-11 - Stop, resume and failure handling

- Retain the existing missing-prerequisite distinction: an explicitly selected single image defaults to failure; directory or pattern batch selections default to skip-and-continue. Preserve configurable overrides and selected-stage preflight.
- Reuse stage failure policies and structured error categories. An individual file failure must not silently mark its missing outputs complete or strand unrelated eligible files in the current run.
- On SIGINT/SIGTERM, coordinate stage workers to stop accepting additional work, cancel in-flight inference when safe, and preserve the existing safe-write and recovery guarantees. Report actual completed/skipped/failed work rather than treating an interrupted plan as complete.
- A subsequent invocation resumes by rescanning and using existing sidecars, without requiring a durable job database. Preserve the documented lock-free sidecar concurrency limitations and the independent SQLite state-concurrency contract.

## 6. Dry-run, diagnostics and reporting

### S4-12 - Dry-run

- Provide `--dry-run` on `process` (single-image or multi-image) to show the planned selection and prospective per-stage work/bypasses without executing stages.
- Dry-run performs **no model calls, XMP processing, image/sidecar-content reads, artifact writes, category accumulation, or persistent-state mutations**. Directory entry and file-existence metadata may be inspected.
- Apply the same selection, depth, symlink, selected-stage, regeneration and work-budget rules as an execution plan. Show which files are counted toward the LLM work budget and when the budget is reached.
- Permit aggregate summaries without retaining all per-file plan records. Per-file output, when requested, may be streamed rather than accumulated in memory. Dry-run must report a memory estimate, clearly labeled as an estimate rather than a measurement or guaranteed bound; its scope and estimation method are design work.
- Dry-run results are predictions; malformed existing outputs, XMP no-change decisions and external modifications may produce different actual outcomes.

### S4-13 - `--verbose` for single and batch execution

- Add `--verbose` to the existing single-image `process` path and to native multi-image `process`.
- Expose image/stage identification, start and completion/skip/failure progress, meaningful reasons, elapsed time and an end-of-run summary. For a batch, provide per-stage and overall plan-relative progress so the user can see how much accounted-for work remains.
- Clearly distinguish **planned bypass**, **actual stage skip**, **completed stage**, **failure**, and **interrupted/not attempted** work; progress reaching 100% must not imply all work succeeded.
- Preserve existing concise output and exit semantics when verbosity is not requested. Keep diagnostics on the appropriate output channel, avoid disclosing configured secrets, and define script-friendly output details during design.

### S4-14 - Batch summary and metrics

- Report at least eligible files discovered, files admitted as planned LLM work, planned bypasses by stage, actual completed/skipped/failed stage counts, runtime deviations from the plan, and total elapsed time.
- Distinguish the number of **files** from the number of **stage operations**, especially when one file needs both `desc` and `json`.
- Provide authoritative file/stage outcome reporting independent of digiKam status or provider request dashboards. The summary must reflect partial completion and failure/interruption without rewriting valid sidecars.

## 7. Category-state CLI operations

**Implementation-plan separation:** Give the following category-management capability its **own phase**, separate from batch discovery/execution. It belongs in Slice 4 and must not be deferred merely because it is independently implementable.

### S4-15 - List categories

- Provide a CLI operation conceptually equivalent to `image-clarus state categories list` to show the category paths currently held in the selected state repository.
- Use existing category state and state-directory selection semantics. Report inaccessible or invalid state visibly instead of silently presenting an empty persistent collection.
- Do not regenerate images, call a model, or change state as part of listing.

### S4-16 - Clear categories

- Provide a CLI operation conceptually equivalent to `image-clarus state categories clear` to remove **all known categories** from the selected repository while leaving other state domains and all image/sidecar files untouched.
- Do not silently substitute another repository or claim success when a requested persistent-state mutation fails. Keep this suitable for explicit noninteractive CLI usage.

### S4-17 - Rebuild categories from existing JSON

- Provide a CLI operation conceptually equivalent to `image-clarus state categories rebuild` that **replaces** the known-category set using existing `.desc.json` sidecars in a selected collection.
- Reuse the **same supported JSON envelope, recognized schema identities, candidate extraction, validation, deduplication and full-path storage rules** as existing Slice 3 accumulation. Do not derive categories from XMP, invent new taxonomy rules, or regenerate JSON.
- Rebuild supports recursive discovery by default, independent `--max-depth` configuration/override, and the S4-02 symlink policy.
- Report how many candidate files were inspected, how many supplied eligible categories, and invalid/unreadable inputs. A failed rebuild must not falsely report a complete replacement; preserve other state domains and avoid exposing a partially replaced category set as successful.
- Use the chosen state repository explicitly and consistently; warn/document that rebuilding a shared repository from a limited collection replaces the repository's category set with only that selection's categories.

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
| Work budget | `--max-work-files N` admits at most N distinct initially identified LLM-work images; regeneration counts; runtime skips do not replenish; XMP-only work is not capped |
| Concurrency | Default inter-stage overlap occurs on different images with one active worker per selected stage; disabling it yields image-first sequential behavior |
| Category timing | Skipped valid JSON can still accumulate categories during execution without model inference; dry-run does not accumulate; sequential mode exposes completed prior-image categories to subsequent prompts |
| Rechecks and failures | Actual stage execution detects changes since planning and retains recovery, prerequisite, continuation and error semantics |
| Dry-run | Correct plan/aggregate counts, work-budget behavior and a clearly labeled memory estimate, with no inference, ExifTool operation, sidecar-content reads or mutations |
| Verbose and metrics | Single-image and batch execution show useful timing/status; batch progress and final counts distinguish predicted skips from actual results and failures |
| Interruption/resume | Graceful stop preserves completed artifacts and reports partial results; a later run skips prior valid outputs |
| Categories list/clear | List reflects persistent categories; clear removes categories only, leaving sidecars and unrelated state intact |
| Categories rebuild | Rebuild from recognized existing JSON replaces the category set using existing extraction logic, honors independent traversal depth, and performs no model inference |
| Regression | Prior accepted stage, artifact, state, config, XMP and source-image contracts remain intact |

Use synthetic fixtures and isolated repositories for verification, with limited optional real-image/manual testing. Measure actual concurrency, progress, and summary behavior rather than relying only on inferred outcomes. The implementation plan defines precise commands, test harnesses, and evidence capture.

## 9. Design decisions and parent-document reconciliation

The implementation plan must resolve exact option/configuration keys beyond those approved here, stage descriptor representation, plan entry representation, directory sorting, queue shutdown/forwarding mechanics, concurrency toggle syntax, progress output format and channels, category-command CLI grammar, and error/result aggregation. These are design decisions **within** the requirements, not permission to expand the product scope.

The Product Owner must explicitly decide whether selected non-LLM stages run for images excluded because the initial LLM work budget is exhausted in a mixed-stage batch. XMP-only runs remain uncapped; do not infer the mixed-stage policy from that separate decision. The plan must also resolve provisional-bypass validation and downstream coordination without treating a prediction as a validated stage result or sacrificing the required early forwarding.

After Product Owner review of this Slice 4 REQ, reconcile the parent REQ/HLD and relevant user documentation. In particular:

- The HLD's previous **image-first default for multi-image execution** must be revised to reflect **inter-stage concurrency enabled by default**, with image-first retained as an explicit mode.
- Preserve the parent REQ's **recursive-by-default** traversal rule; add the approved depth, symlink and work-budget semantics rather than reversing that default.
- Update the roadmap/allocation to identify native batch, `--verbose`, and category list/clear/rebuild as Slice 4 scope, without implying native search is delivered.
- Preserve prior-slice closeout and historical decision records; reconcile forward rather than rewriting history.

## 10. Completion boundary

Slice 4 can be accepted when native batch planning and execution, metadata-only dry-run, the LLM work-file budget, default optional inter-stage concurrency, controllable traversal, verbose progress and metrics, and category list/clear/rebuild meet the outcomes above without regressing Slices 1-3.

Native search, model-parallel workers, content-aware planning Option B, built-in scheduling and digiKam-specific integration are **not** Slice 4 acceptance conditions.
