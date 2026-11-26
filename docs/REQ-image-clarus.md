# REQ - image-clarus

**Status:** End-state requirements captured; Slices 1–3 implementation and closeout complete. Slice 4 batch and category-management implementation work through M3 is complete; its [requirements](slice-4/REQ-slice-4.md) remain draft, and final verification and closeout remain pending in the [plan](slice-4/IMPL-PLAN-slice-4.md).

**Date:** 2026-11-13

**Project name:** image-clarus

## Purpose

Create an open-source command-line tool to make collections of photographs searchable and reusable for blog posts, articles, and other content. Photos currently reside in device-specific directories, often on external drives, and are difficult to find by subject or context.

The tool will use configurable vision and language models to produce descriptive and structured sidecar metadata, optionally synchronize selected metadata to digiKam-compatible XMP sidecars, and search the results. It must support small interactive invocations and externally scheduled long-running processing without requiring a built-in scheduler.

## Guiding requirements

- Linux and Windows are expected deployment platforms; design and implement for both using portable facilities from the outset. Linux remains the required development and test platform; Windows runtime testing and a cross-platform CI matrix are not required. Do not claim Windows runtime verification without executing it.
- Prefer one CLI with subcommands rather than separate programs for generation and search.
- Processing stages must be independently invocable and composable. The user may invoke any chosen stage(s) for one image, or use file selection to process multiple images.
- The built-in behavior must remain useful for a simple interactive command. Configuration and CLI overrides support automated jobs; do not hard-code special scheduling behavior.
- The source images remain unchanged. Generated artifacts are sidecar files in the same directory as their images.
- Build in small, independently usable slices, starting with one operation on one image. Preserve the end-state requirements without implementing every feature in the first slice.
- Requirements describe capabilities Image Clarus must enable in its operating environment, not necessarily functionality implemented entirely inside Python. External tools may fulfill capabilities using Image Clarus building blocks, without replacing the independent native batch and search requirements.

## Runtime and external dependencies

- Implement in Python, support Python 3.12 or newer, and use Python 3.13 as the development baseline.
- Application releases follow Semantic Versioning. Slice 1 starts at `0.1.0`; releases within Slice 1 remain on the `0.1.x` line. Maintain one authoritative package version source, selected in Phase A1 of the Slice 1 plan.
- The CLI exposes the application version through `image-clarus --version`.
- Define project metadata and dependencies in `pyproject.toml`; use `uv` for dependency management, commit `uv.lock`, and use an isolated Python environment for development.
- Description and structured JSON generation must not require external executables beyond Python.
- ExifTool is the recommended external executable for XMP processing. If used, it must be required only when the XMP stage is selected.
- Core functionality must not depend on digiKam or any other specific photo-management application.

## Processing stages and artifacts

Given `2023_04_23_15_05_42.jpg`:

| Stage | Example output | Purpose |
| --- | --- | --- |
| Description | `2023_04_23_15_05_42.jpg.desc.txt` | Natural-language description derived from the image by a configurable vision model |
| Structure | `2023_04_23_15_05_42.jpg.desc.json` | Schema-validated, structured metadata derived from the description by a configurable language model |
| XMP | `2023_04_23_15_05_42.jpg.xmp` | Create or update selected photo metadata for digiKam and optionally other consumers |

- Each stage must be independently selectable. A single invocation may execute all three stages in dependency order for one image.
- Each stage may also be invoked alone for an entire file selection, supporting separate externally scheduled processes (for example, description work using one model while JSON work uses another).
- The default is to **create only missing outputs**; an existing `.desc.txt` or `.desc.json` is not regenerated without an explicit override.
- Regeneration of owned description and JSON sidecars may replace the complete corresponding artifact when explicitly requested.
- An XMP update is a separate file-writing operation with field-specific update policies rather than blanket replacement.
- Represent reusable stage capabilities `usesLLM` and `skipIfValidOutputExists` independently of stage names. Description and JSON have both capabilities; XMP has neither, though it can report `no_change` during execution. Effective bypass eligibility respects regeneration and stage configuration; existence alone does not establish output validity.
- Do not require automatic source-image change detection. Most camera photos are treated as immutable; a user can request regeneration with a different model or prompt.

## Input selection and traversal

- Accept a single image path, a directory, and file patterns/filters that can select multiple files.
- Native pattern matching includes dot-prefixed names, is case-sensitive by default, and offers `-i` / `--ignore-case` for case-insensitive matching; literal-first selection and resolved-path identity are unchanged. Shell expansion precedes the CLI, so quote patterns for application-controlled matching.
- Allow recursive directory traversal, **enabled by default with unlimited depth**, with an option to disable it. `--max-depth 0` selects files in the starting directory only; positive N permits N directory levels below it. The limit is configurable and overridable.
- Within recursive traversal, discover eligible files in the current directory before descending into its subdirectories, using deterministic ordering for an unchanged collection. Execution order may differ under concurrent processing. A depth-first approach without a persistent queue is acceptable.
- Do not follow symbolic links encountered during discovery, including links to images or directories. An explicitly selected image symlink retains existing target-resolution behavior; an explicitly selected directory symlink may designate the starting root, without following discovered links below it. Apply the same boundary to category rebuild.
- Default file eligibility uses a configurable image-extension allowlist. Initial candidate defaults may include `jpg`, `jpeg`, `png`, `webp`, `tif`, and `tiff`, but actual decoding must be compatible with the configured vision model or its adapter.
- Extension selection is not a guarantee that a model can decode the file. Handle unsupported and corrupt images explicitly.
- Allow CLI overrides for configured image formats.
- Exclusion patterns (e.g., thumbnails, backups) are desired in a later slice.
- For a selected stage, use existing output sidecars to decide whether work is already complete. A missing prerequisite does not create a false completion marker.
- Native multi-image batch processing must support independent, unattended collection processing. digiKam scripting may provide interactive image selection and batch invocation, but is complementary to native batching rather than a substitute.

## Batch planning and execution

- Complete a metadata-only initial batch plan before execution using directory entries, eligible image paths and relevant sidecar existence metadata. Planning may read configuration but must not open images or sidecar contents, invoke ExifTool or a model, or mutate state or artifacts. Sidecar existence is a provisional bypass prediction, not content validation or evidence that XMP is synchronized.
- Use stage capabilities and selected-stage order to forward prospective existing-output bypasses to subsequent selected stages without waiting for unrelated upstream inference. Execution remains authoritative: reuse stage validation, recovery, skip and prerequisite logic, recheck changed files, and perform required execution-time behavior such as accumulating categories from valid skipped JSON. Do not add omitted prerequisite stages or a second divergent completion implementation.
- Support optional positive `--max-work-files N` and configuration limiting **initial admission** of distinct images initially identified as requiring at least one selected LLM stage: admit the first N qualifying images in deterministic discovery order and count each once even if multiple LLM stages run. Regeneration affects initial classification; runtime skips do not replenish admission. Images known to need LLM work but excluded by the budget remain excluded from LLM stages while remaining eligible for selected non-LLM stages under normal policies. An image initially predicted to need no LLM work may instead receive corrective inference if execution discovers missing or invalid sidecars, even after admission is full, subject to existing recovery, validation, failure and continuation policies. Actual distinct LLM-work images can exceed N, without an inherent twice-N cap. Non-LLM work consumes no budget; XMP-only selections are not capped. The budget does not cap stage executions, requests, retries, memory or time.
- Provide optional inter-stage concurrency enabled by default, with at most one active worker per selected stage; different stages may work on different images concurrently. A configuration and CLI control disables concurrency and selects image-first sequential execution. No multiple workers within one stage, model-aware scheduler or persistent queue is required for Slice 4.
- During concurrent processing category guidance can reflect timing of other images' completed JSON. In sequential image-first mode, eligible category accumulation for an image should occur before the next image starts. Existing state and sidecar concurrency guarantees remain separate.
- Support `--dry-run` on single-image and multi-image processing with the same selection, regeneration and work-budget rules; show predictions and a clearly labeled memory estimate without stage execution, content reads, model/ExifTool calls, state mutation or artifact writes. Predictions and estimates cannot anticipate all execution-time corrections. The estimation method and scope are defined in the Slice 4 design; do not present it as a measurement or guaranteed bound. Retain this metadata-only planning option if content-aware planning is added later; that later option is outside Slice 4.

The Product Owner decided that budget-excluded images remain eligible for selected non-LLM stages, with no special XMP-name-based budgeting. The Slice 4 design reconciles early forwarding with authoritative rechecks and defines routing if a predicted bypass proves invalid or disappears; those details are not determined by the provisional plan alone.

## Stage dependencies

- JSON generation depends on an existing valid `.desc.txt`; XMP generation depends on the metadata selected for XMP mapping.
- If required stage input is missing, the **built-in default** is:
  - Explicit single-file input: fail with a clear error.
  - Directory or pattern input (potentially multiple files): skip that file/stage and continue.
- The missing-prerequisite policy must be configurable and overridable by CLI, including for automated single-file invocations.
- Stage selection controls whether prerequisite stages run during a combined invocation; it must not force other stages to run during an explicitly single-stage invocation.

## Model providers and prompts

- Support named providers, named models, and independent selection of a model for each model-driven stage.
- Model selection must be configurable and overridable from the CLI; no particular model or parameter size is required.
- Model communication uses an HTTP client with provider adapters. Support OpenAI-compatible API endpoints, including locally hosted services. Provider configuration should include endpoint URL, model identifier, and optional credentials; other providers may be added through adapters as needed.
- Endpoint base URLs must accept standard absolute HTTP and HTTPS URLs with DNS/FQDN hostnames or any IPv4/IPv6 destination. Apply one shared URL-validation policy at configuration preflight and the provider boundary; do not resolve hostnames or restrict destinations at the application level. DNS and connection failures are request-time errors. Preserve the base-URL syntax restrictions specified in the HLD. HTTP does not encrypt credentials or request data; users must authorize the destination and transfer.
- Configuration errors must identify the affected configuration key and an actionable reason without exposing sensitive values, credentials, full endpoint URLs, or raw exception text.
- An API key may be configured directly or through an explicitly named environment variable, such as `api_key_env`.
- Provide built-in default prompts for description and structured generation.
- The built-in default description prompt is `prompts/image-description.txt`, with the exact text: `Fully describe and explain everything about this image.` No additional instructions are part of this default prompt.
- Support overriding each prompt independently through configuration, an external text file, or CLI parameters; external prompt files should be version-control friendly.
- All model-facing prompt instructions, including contextual framing, must be user-editable. Consolidate default instructions into the existing description and structured-generation prompt texts rather than adding prompt inputs or hiding unchangeable instructions in code. Built-in prompts may use macros but remain fully replaceable; users may remove, change or rearrange their contents. Do not require hardcoded category-guidance injection or other mandatory contextual prompt wording.
- Support extensible namespaced macros in user-configurable prompts: `config` exposes non-sensitive resolved configuration and `state` exposes application state. Secret-bearing configuration values, including API credentials, must not be available for prompt interpolation, including through access to containing configuration objects; this applies whether credentials are configured directly or resolved from an environment variable. Illustrative examples are `{{config.stages.json.preferred_categories}}` and `{{state.categories.known}}`. Users choose whether to include macros, where they appear, and their surrounding instructions. Final macro syntax, expansion and value serialization are design work; these examples do not claim current implementation.
- Changing the text of a built-in, user-configurable prompt must not break previously passing unit tests. Tests requiring stable prompt content must use independent fixtures rather than depend on production prompt wording.
- Support a reasoning-effort setting independently for each model-driven stage, including disabling reasoning where the provider supports it. When unspecified, preserve the provider's default behavior.
- Provide a built-in default JSON schema, replaceable in full by a user-supplied schema file. The actual schema and structured-generation prompt wording are design deliverables, not prescriptive REQ content.
- Validate model-produced JSON against the selected schema. When configured, a validation retry may send validation errors back to the model.
- Include model and prompt provenance in generated JSON, sufficient to identify what produced the result. Determine the exact provenance fields during design.

## Structured metadata expectations

The default schema must support information useful for deterministic photo discovery and XMP mapping, including:

- Subjects and identified objects (for example, peppers or onions)
- Activities/actions and setting/context
- Useful visual characteristics
- Searchable keywords/tags
- Model and prompt provenance

The exact field names, types, controlled vocabularies, schema and structured-generation prompt are design work. A replacement schema must be supported without modifying application source.

The generated metadata format must be versioned independently from the application. Define its identifier/representation and evolution policy during Phase A3 of the Slice 1 plan.

### Category guidance and known state

- Support user-configured `preferred_categories` as complete hierarchical category paths, including single-segment values for backward compatibility. Examples include `food`, `food/desserts/cookies`, and `equipment/kitchenware`. These are guidance rather than a closed taxonomy: a model may introduce new categories when appropriate.
- Support accumulated known category hierarchies, preserving complete paths, and make them available through the `state` prompt-macro namespace. Known categories may come from prior Image Clarus processing or existing categories discovered in image metadata or digiKam. Their availability can help models reuse established categories while allowing new ones.
- Making known categories available through the macro is sufficient by default; users control taxonomy conventions and decide whether and how accumulated categories influence generation. Do not require a separate model call, semantic retrieval system, mandatory centralized database, or automatic taxonomy reconciliation. State persistence and discovery follow the application-state requirements below; storage implementation, macro expansion and serialization are design work.

## Application state

- Provide an extensible, general-purpose state facility supporting multiple independently evolving domains, rather than a category-specific database. Known hierarchical tag categories are the first consumer; native batch execution history is a possible future consumer.
- Persistent state must be available across separate CLI invocations, images and directories, and support concurrent access by independent processes. Support state schema evolution and migrations.
- Provide in-memory state when no state directory is explicitly selected and discovery finds no initialized persistent state. During ordinary image processing, state failures—including a missing, invalid, corrupted or inaccessible explicitly selected directory—must produce visible error output identifying the state problem, but must not by themselves block otherwise valid `desc`, `json`, or `xmp` processing or sidecar publication. Do not silently choose another persistent directory; nonpersistent state may be used for that invocation. A state-management operation such as initialization may fail when it cannot perform its own task. State functionality must be independent of invocation mechanism, including single-image CLI, digiKam scripting and future native batching. Do not require a centralized server or persistent job queue.
- Persistent state is explicitly initialized, never automatically created by normal processing. `image-clarus init` initializes `.image-clarus/` in the current working directory.
- Resolve the state directory in this precedence order:
  1. An explicit CLI parameter.
  2. The state directory configured in YAML.
  3. Discovery from the current working directory and its ancestors.
  4. If not found there, discovery from the image's directory and its ancestors.
  5. If not found, in-memory state.
- Current-working-directory discovery takes precedence over image-directory discovery even if the image belongs to another initialized collection. Explicit selection must support sharing state across unrelated photo collections. Discovery must support nested initialized state directories according to this precedence.
- In batch processing resolve state per image using this same precedence, retaining that selection for its prompt reads and eligible category accumulation. Do not select one image's discovered repository for an entire multi-collection batch; shared explicit or CWD selections continue to apply normally.
- Keep discovery behavior separable from persistence so its precedence can become configurable in a future release without redesigning the state facility. Detailed discovery algorithms, persistence implementation and interfaces belong to design.
- Provide category-state list, clear and rebuild operations. List is read-only, including opening and validation, with no implicit initialization or migration; report when a repository cannot be listed without migration. Clear removes only the selected repository's category domain. Rebuild adds categories from existing JSON sidecars using the same supported envelopes, schema identities and full-path extraction, validation and deduplication rules as ordinary accumulation, never XMP or model calls. It has independently configurable recursive depth; continue past invalid/unreadable inputs and report successes, skips and failures accurately, retaining valid partial accumulation. Empty results make no changes; concurrent updates follow the existing state-storage concurrency contract. Clear followed by rebuild can reconstruct from the selected collection. Do not silently select another repository. Dedicated state-command failures may fail those commands without changing ordinary processing's nonblocking state rule.
- For category management, use the configured state-directory selection or, when none is configured, the CWD-selected repository; rebuild sources do not select the destination. An explicit `--state-dir` overrides it. Rebuild accepts explicitly selected `.desc.json` sidecars and includes orphan sidecars. Registered migrations are permitted for clear and a rebuild with eligible categories; list and empty/no-category rebuild never migrate.
- Category listing is logically read-only: opening, validation and reading must not change stored data or schema, initialize or migrate the repository, or restore timestamps. Normal SQLite journal, WAL and shared-memory activity and operating-system-maintained access-time updates are permitted; WAL repositories are not rejected merely because such activity may occur. Genuine access, integrity or other read failures are reported visibly. Use Python's standard-library `sqlite3`, with ordinary Windows and Linux clone/install workflows; no native extension, bundled SQLite, detached snapshot or custom packaging is required or introduced. This Product Owner decision supersedes the earlier physical-nonmutation and unsafe-WAL-rejection requirements.
- For clear and nonempty rebuild, any registered migration and the clear or first eligible update must be admitted in the same transaction, preserving atomic migration behavior. An empty/no-category rebuild must not initialize, migrate or otherwise mutate logical state.

## XMP metadata integration

- Integrate with existing digiKam-compatible `.xmp` sidecar files; preserve all unrelated XMP data, including camera/exposure metadata and manual tags outside a non-empty generated root. An empty root preserves all existing tags; tags inside a non-empty root follow its selected policy below.
- Update **digiKam tag representation(s) only by default**. Writing other metadata representations (e.g., Lightroom, Microsoft, other keyword variants) must be independently optional through configuration.
- Generated tags normally belong beneath a configurable hierarchical root, **`ai` when the root setting is omitted**, not digiKam's special `auto` branch. digiKam's automatic-tagging replacement behavior can remove tags beneath `auto`. An explicitly configured empty string (`""`) adds no root prefix; it is distinct from an omitted setting. The root is a tag hierarchy, not an XML namespace.
- Supported tag update policies for a non-empty root: `add`, `overwrite`, `new`, `disabled`. Built-in default: **`add`**.
  - `add`: merge generated tags within the configured root without duplicates.
  - `overwrite`: replace only tags belonging to the configured root; do not remove unrelated tags.
  - `new`: populate generated tags only if the configured root currently has no tags on the image.
  - `disabled`: do not modify those tags.
- With an explicitly empty root, `disabled` leaves tags unchanged; `add`, `overwrite`, and `new` each behave as `add` without duplicates and must never delete any existing XMP tags. With a non-empty root, the configured policy governs tags within that root, including manually assigned tags there; tags outside it remain protected.
- Other XMP tag/keyword representations are **disabled by default** and must offer configurable update behavior; their exact mappings are design work.
- Optional XMP title and description population must each have **independent** configuration. The built-in default for each is `new` (populate only if absent/empty); each also supports `overwrite` and `disabled`.
- Determine which JSON fields map to hierarchical tags, title, and description during design. Not every JSON field must become an XMP tag.
- XMP tags remain editable through digiKam. Integration validation must verify generated tags are displayed and editable in digiKam, and manual tags outside a non-empty root (or all existing tags for an empty root) remain intact.
- Synchronizing historical removals from regenerated JSON into XMP is **not automatically required**. `overwrite` deliberately replaces only the configured generated-tag root; do not attempt automatic general-purpose tag reconciliation in the initial implementation.

## Search

- Search is a subcommand of the same CLI.
- Initial search uses deterministic, case-insensitive keyword/text matching against `.desc.txt` and structured `.desc.json` content.
- Search should be able to use structured fields for more precise matching; matching rules and field-selection configuration are design details.
- Support human-readable file-path/results output and scripting-friendly machine-readable output such as JSON.
- Use the same file selection and traversal mechanisms where relevant.
- Future semantic search using embeddings is an explicit goal but **not a release-one requirement**. An external LLM runner reading the files may provide an interim natural-language search workflow without being built into this CLI.
- Native search remains an independent requirement; external photo-management workflows do not replace it.

## Configuration and precedence

Configuration precedence, highest first:

1. Explicit CLI parameters
2. The selected configuration file
3. Built-in defaults

- If an explicit configuration path is provided, load only that file and do not search for or merge another configuration file.
- Otherwise, detect the operating system and select at most one configuration file: search the user-level directory first, then the system-level directory. If neither contains a configuration file, use built-in defaults. Do not implicitly merge user and system configuration files.
- Configuration directories:

  | OS | User-level | System-level |
  | --- | --- | --- |
  | Linux | `~/.config/image-clarus/` | `/etc/image-clarus/` |
  | macOS | `~/Library/Application Support/image-clarus/` | `/Library/Application Support/image-clarus/` |
  | Windows | `%APPDATA%\image-clarus\` | `%PROGRAMDATA%\image-clarus\` |

- Installation must not require administrator privileges or create system configuration directories.
- The main configuration file is YAML named `config.yaml`, with optional separate prompt and schema files in the selected configuration directory. Every optional file also has a built-in fallback.
- Allow the main configuration path and **each** prompt/schema file path to be overridden individually from CLI parameters.
- All configurable values must be overridable from CLI parameters where applicable.
- Configuration should cover providers, models, prompts, schema, allowed formats, file selection behaviors, per-stage policies, XMP mappings/update modes, retries, and logging.

## Failure policies, retries and logging

- **Built-in retry default is zero.** A failing CLI command exits with a clear error and an appropriate nonzero exit status unless configured otherwise.
- Config and CLI parameters may enable retries, delay/backoff, bounded or unlimited attempts, and category-specific actions.
- Distinguish at least these failure categories for configurable policy: invalid configuration, authentication failure, invalid/unknown model, temporary provider unavailability, network timeout, schema validation failure, unsupported/corrupt image, missing prerequisite, and file I/O error.
- Configuration/authentication failures should ordinarily be treated as terminal. Transient model unavailability may be retried with backoff when configured. Failed files in a multi-file run may be skipped or abort the run according to policy.
- Do not write a completed output file when its generation or validation failed.
- Provide configurable logging level and destination (console, file, or both) and suitable process exit codes. Batch invocations should summarize completed, skipped, and failed work.
- Provide `--verbose` for single-image and batch processing with stage/image progress, reasons and elapsed time. Batch reporting distinguishes planned bypasses from actual skips, completions, failures and interrupted/not-attempted work, and reports discovered eligible files, initial LLM-work admission, distinct corrective-overrun images, actual distinct LLM-work images, actual per-stage execution counts, plan deviations and total elapsed time. File counts and stage-operation counts are distinct; 100% accounted progress does not imply success. Preserve concise output when verbosity is not selected.

## External scheduling, stop and resume

- Do not implement an internal scheduler as a requirement. External schedulers can fulfill scheduling needs using Image Clarus execution controls; the CLI must be usable from systemd services/timers, cron, scripts or other external orchestrators.
- A scheduler may invoke only description processing, only JSON processing, only XMP processing, or combined stages.
- Separate processes for different stages may run concurrently when externally orchestrated. Slice 4 also implements default inter-stage concurrency with one worker per selected stage and an opt-out; model-aware scheduling, multiple workers per stage and a mandatory database are not required.
- On a graceful stop request, cancel any model request still in flight when safe; once a file-writing operation has started, allow that operation to finish safely before exit.
- Resume by rescanning eligible files and skipping already completed output sidecars. Do not require persistent in-memory job state.
- Coordinate worker shutdown on SIGINT/SIGTERM: stop accepting additional work, safely handle in-flight inference and writes, and report actual partial outcomes. Continue or abort according to configured failure and prerequisite policies; a later invocation rescans rather than relying on a durable job queue.
- Support externally controlled run bounds or time-window behavior where useful for long-running batch invocation, without requiring an internal clock-based scheduler. Precise controls may be designed in the appropriate slice.
- The initial sidecar-write architecture uses no application-level file locks. Sidecar safe-write and recovery guarantees apply to an individual operation; when processes concurrently update the same output, the last successful replacement wins. Lost updates, including concurrent XMP edits, and backup/cleanup races are accepted limitations; do not promise serialized sidecar updates or conflict detection. This sidecar limitation does not remove the separate requirement for concurrent shared-state access.

## Safe-write requirements

Use one shared safe-write mechanism for generated `.desc.txt`, `.desc.json`, and `.xmp` files:

1. Construct output in a temporary file in the destination directory.
2. Flush, close, and validate the complete temporary output before replacement.
3. If replacing an existing output, preserve a recoverable backup (e.g., `.bak`) and flush it.
4. Use the safest available filesystem/OS replacement operation; do not assume the rename is atomic everywhere.
5. Verify the replacement and remove or retain the backup according to configurable backup-retention policy.
6. Handle failed/interrupted replacements and stale temporary/backup files safely, without silently discarding recoverable originals.
7. Preserve appropriate existing permissions where supported and unrelated XMP metadata. Attempt private `0600` creation and preservation of existing POSIX mode bits for replacement, backup and recovery. Require exact mode verification where the filesystem supports it; do not reject otherwise valid writes solely because that filesystem cannot represent or enforce those bits. Actual permission denials, storage errors and other unrelated failures remain errors. Warn users that filesystem or mount permissions may expose generated metadata and backups; use a suitably private destination when confidentiality matters.

- Do not implement filesystem-specific branches unless a demonstrated compatibility problem requires them; allow a configurable alternate method if testing warrants it.
- Expected environments include common Linux filesystems (such as XFS and ext4), NTFS (including FUSE-backed mounts), VFAT removable media, and virtual or memory-backed filesystems.
- Linux is the required test platform; Windows is an expected deployment platform to design and implement for, but a full cross-platform CI matrix or a Windows test machine is not required.
- Tests should cover available development filesystems and representative compatibility cases. Testing every filesystem, driver, and operating-system combination is **not** required.
- Never promise fully crash-proof writes on filesystems that cannot guarantee them. Recovery behavior is required.

## Requirements Evolution — November 2026 Slice 2 Testing

The original end-state requirements provided independently configurable prompts, structured metadata, hierarchical XMP tags, and independent image processing without requiring a centralized database. Slice 2's accepted design introduced `preferred_categories` as optional guidance using single top-level segments, supplied separately from the replaceable system prompt. These were the design and implementation choices at that time, not an implementation of the enhancements below.

During Product Owner hands-on use of Image Clarus 0.2.1 and digiKam 9.1.0, hierarchical tagging proved valuable for organizing and retrieving photographs. Independently processing images also highlighted the need for more consistent categories across a collection without sacrificing useful depth or the ability to introduce new categories. The Product Owner values user control over models, prompts, categorization conventions, and inference costs.

The resulting refinements require full hierarchical preferred-category paths while retaining single-segment values; accumulated or discovered known category paths exposed as optional prompt context; and user-controlled, namespaced prompt macros. Prompt customization must encompass contextual instructions and dynamically supplied values, not just system-prompt replacement. Users choose how to incorporate the available values, without prescribing additional model calls or automatic taxonomy-selection logic. These are new or refined end-state requirements identified through Slice 2 testing, not claims that Slice 2 already implements them, and they are not assigned to a particular future slice.

Slice 2 testing exposed a gap between independent prompt control and hardcoded user-message framing. The Product Owner accepted that gap for Slice 2 closeout; the prompt-control and macro requirements above are the remedy for future slices, without a committed slice assignment. The larger lesson is that the gap should have been identified and raised earlier during implementation. Early discovery and escalation of such gaps is a broader process issue to address outside this implementation, particularly as this was a new project; no specific process remedy is claimed here.

## Requirements Evolution — November 19, 2026 Discovery

Product discovery refined accumulated categories into the first consumer of a general-purpose, extensible application-state facility. Persistent state is explicitly initialized; explicit CLI and YAML selection precede current-working-directory discovery, which precedes image-directory discovery, with in-memory state when no directory is explicitly selected and discovery finds none. The original discovery decision treated an invalid or inaccessible explicitly selected directory as an error without fallback; the subsequent decision below refines ordinary processing behavior. Prompt control now explicitly covers all model-facing instructions, including contextual framing, and uses extensible, user-placed macros without exposing secret-bearing configuration. External tools may fulfill capabilities such as scheduling and interactive selection, while native unattended batch processing and native search remain independent requirements. These are end-state decisions, not claims of implementation or allocation to a particular delivery slice.

The Product Owner subsequently clarified that application-state errors must be visibly reported but must not block otherwise valid core image processing. This includes an invalid explicitly selected directory: another persistent repository is not silently selected, and nonpersistent state may be used for the invocation. State-management commands may fail independently. The Product Owner also clarified that existing prompt inputs remain user-owned: default instructions are consolidated into those texts, not additional prompt inputs or hidden code instructions.

## Delivery approach and scope

The project follows **REQ → High-Level Design → Implementation Plan → Implementation**. This document records **end-state requirements**, not a commitment to deliver all features in the first slice. Each numbered delivery slice has its own implementation plan; `Phase A`, `Phase B`, `Phase C`, and step identifiers are scoped within that plan and are not slice names.

- **First buildable slice (Slice 1):** single-image Description and Structure (`desc` and `json`) processing, with each stage independently invocable and composable through the persisted `.desc.txt` handoff; model/provider configuration, configurable prompts and schema, JSON validation/provenance, and correct output handling. XMP, multi-image selection/traversal, batch processing, and search remain later slices.
- **Completed Slice 1:** The [implementation plan](slice-1/IMPL-PLAN-slice-1.md) and [C5 closeout](slice-1/IMPL-C5-COMPLETED.md) record the implemented single-image `desc` + `json` delivery and its evidence. At that closeout XMP, multi-image selection/traversal, batch processing, and search remained later-slice work.
- **Completed Slices 2–3:** Slice 2 delivered XMP integration and Slice 3 delivered user-owned prompts, macros and application state; their plans and closeouts preserve acceptance and evidence limits.
- **Slice 4 in progress:** Native batch selection/planning and execution, diagnostics and category-state management are implemented through M3; M4 documentation is complete. The [Slice 4 REQ](slice-4/REQ-slice-4.md) remains draft, and final verification and closeout remain in the [plan](slice-4/IMPL-PLAN-slice-4.md). Phase A completed its documented design decisions before Phase B; that Slice 4 requirement is not retroactive to prior slices. Native deterministic search remains an independent later requirement.
- **Further buildable slices:** Remaining capabilities and ordering are indicative; each slice's own implementation plan defines its phases, steps, and validation.
- **Later goals:** exclusion filters, expanded format/provider support, richer search configuration, and embeddings-based semantic search. Not all later goals need be part of release one.
- Apache-2.0 is the intended license; verify publication notices. Installation packaging, CLI framework and detailed option grammar, specific model-client libraries, structured-generation prompt/schema/provenance details, and exact XMP field mappings remain for implementation planning.

## Known non-goals of the initial implementation

- Hard-coding any specific model or model size
- Built-in scheduling or automatic time-of-day execution
- Mandatory centralized image database or persistent job queue
- Automatic detection of changes to original photos
- Full XMP reconciliation of tags removed from regenerated descriptions/JSON
- Embeddings-based semantic search in release one
- Exhaustive testing on every filesystem or operating system

## Requirements-to-design handoff

Design work must resolve, without silently reducing any requirements above:

- CLI framework, detailed argument grammar, package structure, and result schemas
- Final YAML key schema, generic override semantics, and relative-path resolution for prompt and schema files
- Structured-generation prompt and JSON schema, including provenance representation
- State storage, migration and concurrency behavior, nested discovery details and failure handling; macro expansion and serialization
- XMP fields and representation-specific mappings, with tests against digiKam
- Stage prerequisites and configurable actions on failure
- Search matching syntax, field filters and output formats
- Safe-write implementation details and interruption recovery on supported/representative filesystems
- Implementation slices and verification strategy

