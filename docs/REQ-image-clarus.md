# REQ - image-clarus

**Status:** End-state requirements captured; Slice 1 implementation and closeout complete; later-slice capabilities remain planned.

**Date:** 2026-11-13

**Project name:** image-clarus

## Purpose

Create an open-source command-line tool to make collections of photographs searchable and reusable for blog posts, articles, and other content. Photos currently reside in device-specific directories, often on external drives, and are difficult to find by subject or context.

The tool will use configurable vision and language models to produce descriptive and structured sidecar metadata, optionally synchronize selected metadata to digiKam-compatible XMP sidecars, and search the results. It must support small interactive invocations and externally scheduled long-running processing without requiring a built-in scheduler.

## Guiding requirements

- Linux is the required platform; portability to other operating systems is desirable for an open-source project.
- Prefer one CLI with subcommands rather than separate programs for generation and search.
- Processing stages must be independently invocable and composable. The user may invoke any chosen stage(s) for one image, or use file selection to process multiple images.
- The built-in behavior must remain useful for a simple interactive command. Configuration and CLI overrides support automated jobs; do not hard-code special scheduling behavior.
- The source images remain unchanged. Generated artifacts are sidecar files in the same directory as their images.
- Build in small, independently usable slices, starting with one operation on one image. Preserve the end-state requirements without implementing every feature in the first slice.

## Runtime and external dependencies

- Implement in Python, support Python 3.12 or newer, and use Python 3.13 as the development baseline.
- Application releases follow Semantic Versioning. Slice 1 starts at `0.1.0`; releases within Slice 1 remain on the `0.1.x` line. Maintain one authoritative package version source, selected in Phase A1 of the Slice 1 plan.
- The CLI exposes the application version through `image-clarus --version`.
- Define project metadata and dependencies in `pyproject.toml`; use `uv` for dependency management, commit `uv.lock`, and use an isolated Python environment for development.
- Description and structured JSON generation must not require external executables beyond Python.
- ExifTool is the recommended external executable for XMP processing. If used, it must be required only when the XMP stage is selected.

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
- Do not require automatic source-image change detection. Most camera photos are treated as immutable; a user can request regeneration with a different model or prompt.

## Input selection and traversal

- Accept a single image path, a directory, and file patterns/filters that can select multiple files.
- Allow recursive directory traversal, **enabled by default**, with an option to disable it.
- Within recursive traversal, process eligible files in the current directory before descending into another directory. A depth-first approach without a persistent queue is acceptable.
- Default file eligibility uses a configurable image-extension allowlist. Initial candidate defaults may include `jpg`, `jpeg`, `png`, `webp`, `tif`, and `tiff`, but actual decoding must be compatible with the configured vision model or its adapter.
- Extension selection is not a guarantee that a model can decode the file. Handle unsupported and corrupt images explicitly.
- Allow CLI overrides for configured image formats.
- Exclusion patterns (e.g., thumbnails, backups) are desired in a later slice.
- For a selected stage, use existing output sidecars to decide whether work is already complete. A missing prerequisite does not create a false completion marker.

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

## XMP metadata integration

- Integrate with existing digiKam-compatible `.xmp` sidecar files; preserve all unrelated XMP data, including camera/exposure metadata and manual tags.
- Update **digiKam tag representation(s) only by default**. Writing other metadata representations (e.g., Lightroom, Microsoft, other keyword variants) must be independently optional through configuration.
- Generated tags belong beneath a configurable hierarchical root, **`ai` by default**, not digiKam's special `auto` branch. digiKam's automatic-tagging replacement behavior can remove tags beneath `auto`.
- Supported tag update policies: `add`, `overwrite`, `new`, `disabled`. Built-in default: **`add`**.
  - `add`: merge generated tags within the configured root without duplicates.
  - `overwrite`: replace only tags belonging to the configured root; do not remove unrelated tags.
  - `new`: populate generated tags only if the configured root currently has no tags on the image.
  - `disabled`: do not modify those tags.
- Other XMP tag/keyword representations are **disabled by default** and must offer configurable update behavior; their exact mappings are design work.
- Optional XMP title and description population must each have **independent** configuration. The built-in default for each is `new` (populate only if absent/empty); each also supports `overwrite` and `disabled`.
- Determine which JSON fields map to hierarchical tags, title, and description during design. Not every JSON field must become an XMP tag.
- XMP tags remain editable through digiKam. Integration validation must verify generated tags are displayed and editable in digiKam, and manual tags remain intact.
- Synchronizing historical removals from regenerated JSON into XMP is **not automatically required**. `overwrite` deliberately replaces only the configured generated-tag root; do not attempt automatic general-purpose tag reconciliation in the initial implementation.

## Search

- Search is a subcommand of the same CLI.
- Initial search uses deterministic, case-insensitive keyword/text matching against `.desc.txt` and structured `.desc.json` content.
- Search should be able to use structured fields for more precise matching; matching rules and field-selection configuration are design details.
- Support human-readable file-path/results output and scripting-friendly machine-readable output such as JSON.
- Use the same file selection and traversal mechanisms where relevant.
- Future semantic search using embeddings is an explicit goal but **not a release-one requirement**. An external LLM runner reading the files may provide an interim natural-language search workflow without being built into this CLI.

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

## External scheduling, stop and resume

- Do not implement an internal scheduler as a requirement. The CLI must be usable from systemd services/timers, cron, scripts or other external orchestrators.
- A scheduler may invoke only description processing, only JSON processing, only XMP processing, or combined stages.
- Separate processes for different stages may run concurrently when externally orchestrated; internal model-aware pipeline concurrency is **not required**. Avoid introducing unnecessary shared mutable queues or mandatory databases.
- On a graceful stop request, cancel any model request still in flight when safe; once a file-writing operation has started, allow that operation to finish safely before exit.
- Resume by rescanning eligible files and skipping already completed output sidecars. Do not require persistent in-memory job state.
- Support externally controlled run bounds or time-window behavior where useful for long-running batch invocation, without requiring an internal clock-based scheduler. Precise controls may be designed in the appropriate slice.
- The initial architecture uses no application-level file locks. Safe-write and recovery guarantees apply to an individual operation; when processes concurrently update the same output, the last successful replacement wins. Lost updates, including concurrent XMP edits, and backup/cleanup races are accepted limitations; do not promise serialized updates or conflict detection.

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
- Linux is the required test platform; a full cross-platform CI matrix is not required, though portability to other operating systems is desirable.
- Tests should cover available development filesystems and representative compatibility cases. Testing every filesystem, driver, and operating-system combination is **not** required.
- Never promise fully crash-proof writes on filesystems that cannot guarantee them. Recovery behavior is required.

## Delivery approach and scope

The project follows **REQ → High-Level Design → Implementation Plan → Implementation**. This document records **end-state requirements**, not a commitment to deliver all features in the first slice. Each numbered delivery slice has its own implementation plan; `Phase A`, `Phase B`, `Phase C`, and step identifiers are scoped within that plan and are not slice names.

- **First buildable slice (Slice 1):** single-image Description and Structure (`desc` and `json`) processing, with each stage independently invocable and composable through the persisted `.desc.txt` handoff; model/provider configuration, configurable prompts and schema, JSON validation/provenance, and correct output handling. XMP, multi-image selection/traversal, batch processing, and search remain later slices.
- **Completed Slice 1:** The [implementation plan](slice-1/IMPL-PLAN-slice-1.md) and [C5 closeout](slice-1/IMPL-C5-COMPLETED.md) record the implemented single-image `desc` + `json` delivery and its evidence. XMP, multi-image selection/traversal, batch processing, and search remain later-slice work.
- **Further buildable slices:** XMP integration; selection and traversal; deterministic search; external batch operation and operational controls. Their ordering remains indicative; each slice's own implementation plan defines its phases, steps, and validation.
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
- XMP fields and representation-specific mappings, with tests against digiKam
- Stage prerequisites and configurable actions on failure
- Search matching syntax, field filters and output formats
- Safe-write implementation details and interruption recovery on supported/representative filesystems
- Implementation slices and verification strategy

