# REQ - Image Clarus Slice 3

**Date:** 2026-11-19

**Status:** Draft for Product Owner review; not accepted or authorized for implementation.

**Project:** `image-clarus`

**Intended repository path:** `docs/slice-3/REQ-slice-3.md`

**Parent requirements:** [`../REQ-image-clarus.md`](../REQ-image-clarus.md)

**Architecture:** [`../HLD-image-clarus.md`](../HLD-image-clarus.md)

**Previous slice closeout:** [`../slice-2/IMPL-C5-COMPLETED.md`](../slice-2/IMPL-C5-COMPLETED.md)

## 1. Purpose and authority

Slice 3 delivers three approved capabilities: complete control of model-facing prompt instructions with optional namespaced macros; hierarchical preferred-category guidance; and reusable application state, with accumulated category hierarchies as its first use. It also changes the existing JSON prompt hash from mandatory to explicitly opt-in.

This document defines **Slice 3 behavior and acceptance outcomes**. It does not replace the parent REQ or rewrite completed slices. The parent HLD establishes SQLite as the initial persistent-state implementation. Specific interfaces, storage schemas, macro parsing rules, and testing procedures belong to subsequent design and implementation planning.

Requirements identified as `S3-` apply to this slice. Decisions not explicitly made by the Product Owner must be raised rather than silently included in implementation scope.

## 2. Scope boundary

### 2.1 Included

- Complete user control over prompts for the existing model-driven stages, including previously hardcoded instructional framing.
- Optional, extensible `config` and `state` macros in user-configurable prompts, with secret-bearing configuration excluded.
- Complete hierarchical paths in `stages.json.preferred_categories`, retaining single-segment compatibility.
- General-purpose application state using embedded SQLite when initialized and in-memory state otherwise; known category paths are its first domain.
- Explicit `image-clarus init`, state-directory selection, discovery and reuse across separate invocations.
- Reporting state problems without making optional application state a dependency of `desc`, `json`, or `xmp` processing.
- An opt-in setting for including `prompt_sha256` in generated JSON, **disabled by default**.
- Regression and acceptance checks for these approved behaviors.

### 2.2 Not included

- Native multi-image batch selection, directory traversal, pattern processing, or batch history.
- Native deterministic or semantic search.
- A built-in scheduler or new scheduling controls.
- A digiKam plugin, application-specific batch integration, or mandatory digiKam dependency.
- Historical import or rebuilding of category state from existing collections; automatic taxonomy reconciliation, category-renaming engine, or additional model calls for taxonomy selection.
- Changes to existing XMP publication policies, ownership roots, field mappings, source-image integrity, or sidecar safe-write semantics.
- New prompt-identification or prompt-tracking features beyond the specifically approved optional `prompt_sha256` behavior.
- New retry policies or expansion of existing provider/model retry behavior.

Native batching and search remain independent end-state requirements. External scripts and digiKam-driven commands can already invoke the single-image CLI, but do not replace future native functionality.

## 3. Requirements traceability

| Parent area | Slice 3 delivery | Requirements |
| --- | --- | --- |
| Model providers and prompts | Complete replaceability, optional macros, secret protection, prompt-file test independence | S3-01 to S3-03 |
| Structured metadata expectations | Make the existing `prompt_sha256` field opt-in while preserving approved JSON fields and prior artifacts | S3-04 |
| Category guidance and known state | Full hierarchical preferences and accumulated known paths | S3-05, S3-07 |
| Application state | General-purpose infrastructure, SQLite/in-memory, explicit initialization, discovery and concurrency | S3-06 to S3-10 |
| Stage independence, sidecars, configuration | State must not interrupt ordinary stage processing; preserve existing contracts | S3-09, S3-11 |
| Input selection, search, scheduling | Retained as parent requirements, not implemented here | Section 2.2 |

**Historical boundary:** Slice 2 was accepted with an exception for hardcoded model-facing JSON category framing. Slice 3 remedies that exception without changing the recorded Slice 2 acceptance.

## 4. Prompt and JSON requirements

### S3-01 - Fully user-editable model instructions

- All model-facing **instructions**, including contextual framing previously supplied in a hardcoded user message, must be replaceable through the existing prompt configuration mechanisms.
- Consolidate default instructions into the existing description and JSON prompt texts; do not introduce additional prompt inputs or hide unchangeable prompt instructions in code. Users own both prompts and can remove, change or rearrange any instruction or macro.
- Do not automatically append category advice or any other mandatory instructional language when the user has supplied a replacement prompt.
- Preserve the exact default description prompt: `Fully describe and explain everything about this image.`
- Required image data, persisted description text, and schema/protocol payloads may still be transmitted as stage inputs. Their presence must not be used to conceal additional mandatory instructions.
- Preserve the existing independent `desc`, `json`, and `xmp` stage contracts.

### S3-02 - User-controlled namespaced macros

- Support optional macros in model-facing prompt text with separate `config` and `state` namespaces.
- Apply macro substitution to both existing prompt inputs, description and JSON, whether built in or user supplied; do not require a separate prompt to use macros.
- `config` exposes eligible non-sensitive **resolved** configuration; `state` exposes available application state.
- Examples: `{{config.stages.json.preferred_categories}}` and `{{state.categories.known}}`.
- A prompt author decides which macros to include, where they appear, and their surrounding instructions. No category macro is mandatory.
- The mechanism must permit additional configuration keys and future state domains without hardcoding a separate prompt instruction for each one.
- The exact grammar, value serialization, and behavior of malformed or unavailable references are design matters, subject to the stage-independence requirement in S3-09.

### S3-03 - Protect secret configuration

- API credentials and other secret-bearing configuration values must not be accessible through prompt macros, directly or by expanding containing configuration objects.
- This protection applies to credentials supplied in configuration and resolved from environment variables.
- Interpolation and its diagnostics must not disclose those values. Existing configuration and model-selection behavior must remain intact.

### S3-04 - Optional prompt SHA in generated JSON

- **Default behavior:** The JSON stage must omit `prompt_sha256` from newly generated `.desc.json` artifacts.
- The user may explicitly enable the field through YAML configuration or a CLI override, consistent with existing configuration precedence.
- **Enabled behavior:** Preserve the existing `prompt_sha256` calculation and field representation; this is an optional capability, not a condition of ordinary JSON generation.
- Continue supporting the already implemented and Product Owner-approved `provider_alias`, `model_alias`, `model_id`, `prompt_id`, and `description_sha256` fields, as well as existing custom-schema SHA-based version identification.
- Previously generated JSON artifacts containing `prompt_sha256` must remain valid. New artifacts without the field must also pass the application's JSON envelope validation and remain usable by downstream stages.
- Changing the text of a built-in, user-configurable prompt must not cause previously passing unit tests to fail. Tests requiring a particular prompt text or hash must use their own fixed fixtures and may explicitly enable `prompt_sha256` when needed.
- No change to the completed Slice 1 implementation is required as part of the historical Slice 1 closeout; this is a Slice 3 behavior change.

## 5. Hierarchical category requirements

### S3-05 - Hierarchical preferred categories

- Extend `stages.json.preferred_categories` to accept entire category paths, for example `food/desserts/cookies` and `equipment/kitchenware`.
- Existing single-segment values such as `food` must remain supported.
- Preserve the hierarchy in the configured guidance instead of reducing it to a top-level category.
- Category guidance is advisory and not a closed taxonomy. The model may recommend other categories when appropriate.
- The user controls whether and how this guidance enters a prompt through S3-02. Do not reinstate hardcoded instructional framing.
- During implementation, the built-in JSON prompt may be changed to migrate its existing guidance into the prompt text and must use the configuration macro to include preferred categories by default. Users may remove or change the macro and its surrounding text in their replacement prompt; no guidance is injected when omitted.

## 6. Application state requirements

### S3-06 - General-purpose state facility

- Provide a reusable application-state facility, not a database specialized solely for categories.
- Separate responsibilities for selecting the state location, accessing storage, and handling individual state domains so future uses can be added without replacing the facility.
- Use the embedded SQLite approach selected in the parent HLD for initialized persistent state, and an in-memory implementation when persistent state is not selected or discovered.
- Support independently evolving state domains and stored-state schema evolution. Future native batch history is a possible consumer, **not** part of this slice.
- State must not replace per-image `.desc.txt`, `.desc.json`, or `.xmp` sidecars as the authoritative stage artifacts.

### S3-07 - Known hierarchical category state

- Maintain previously accumulated known category hierarchy paths as the first application-state domain.
- Make those paths available to prompts through `{{state.categories.known}}` when the prompt author explicitly references the macro.
- Persistent state allows reuse across separate CLI invocations and different images/directories sharing a selected repository; in-memory state is limited to its process lifetime.
- The model remains free to recommend new categories; state does not impose an authoritative or closed taxonomy.
- Exact extraction, deduplication, and update timing rules for category paths from processing results belong to design. Do **not** introduce an unapproved distinction between category nodes and leaf tags as a product requirement.

### S3-08 - Explicit initialization and location precedence

- Provide `image-clarus init` to initialize `.image-clarus/` in the current working directory.
- Ordinary `process` execution must not automatically initialize or create a persistent state repository.
- Resolve state-directory selection in this order:
  1. Explicit CLI state-directory choice.
  2. YAML-configured state directory.
  3. Search the current working directory and then its ancestors for an initialized `.image-clarus/`.
  4. If absent, search the image's directory and then its ancestors.
  5. If absent, use in-memory state.
- CWD ancestry takes precedence over image-directory ancestry even if the image is inside another initialized collection. Within an ancestry search, the nearest initialized repository wins.
- Explicit selection allows one repository to serve unrelated photo collections; nested repositories must be discoverable according to this precedence.
- The selection mechanism must be separate from the storage backend so future discovery policies can evolve without replacing persistence. Configurable discovery precedence is not required now.

### S3-09 - State must not inhibit processing

- Application state is an **optional enhancement**, not a prerequisite for any of the three primary stages: `desc`, `json`, or `xmp`.
- Missing, inaccessible, invalid, corrupted, or incompatible state, including an explicitly selected state directory, must not by itself cause otherwise valid primary stage processing to fail or prevent sidecar publication.
- Report state failures through visible error output identifying the state problem, including when the primary operation succeeds. Do not silently report a failed state operation as successful; the primary stage's ordinary completion result remains independent of the state error.
- An invalid explicit state directory must not silently select a different persistent repository. Failure handling may use nonpersistent state for the current invocation, without altering the user's explicit persistent selection.
- State updates and sidecar publication must remain independent: failure to save category history must not invalidate successfully generated image metadata or change the ordinary completion result of a primary stage.
- A state-management operation such as `init` may fail when it cannot fulfill its own purpose. The nonblocking rule applies to ordinary image processing.
- The exact diagnostic format and handling of unavailable state-macro values are design questions. They must preserve this nonblocking behavior.

### S3-10 - State sharing and evolution

- Persistent state must remain usable across independent process invocations and support safe concurrent state access, including reads and updates.
- Support state schema versioning and migration for future state-domain evolution.
- Do not hold a state transaction open throughout model inference. State access must not turn optional state into a blocking dependency of the three processing stages.
- Existing lock-free sidecar-write behavior is unchanged; SQLite transactions do not imply new locking or conflict-resolution guarantees for XMP or other sidecars.
- Do not silently destroy or overwrite existing persistent state while initializing, reading, updating, or migrating it.

## 7. Compatibility and acceptance

### S3-11 - Preserve prior processing behavior

- Preserve independent selection of `desc`, `json`, and `xmp`, persisted interstage handoffs, existing stage skip/regeneration behavior, configuration precedence and source-image integrity.
- The `xmp` stage remains deterministic and must not require model inference, prompt macros, or available application state.
- Preserve existing XMP tag ownership, publication policies, title/caption behavior, and unrelated metadata.
- State is independent of whether a single-image invocation is started directly, by a script, or by digiKam; no digiKam dependency is introduced.

### S3-12 - Required acceptance outcomes

| Area | Observable outcome |
| --- | --- |
| Full prompt replacement | The two existing prompt inputs control all model-facing instructions; application code appends no hidden mandatory instructions, and replacement prompts may remove or change guidance |
| Namespaced macros | User-selected `config` and `state` references work in both description and JSON prompt inputs; omitting them does not force category context into prompts |
| Secret safety | Direct and environment-resolved credentials cannot be interpolated, including by referencing a containing object |
| Prompt edits and tests | Production prompt text can change without breaking unit tests that should use stable independent fixtures |
| Optional prompt SHA | Default JSON omits `prompt_sha256`; explicit YAML/CLI enablement includes it using existing calculation; the shared envelope validator accepts valid prior and new JSON, validates the hash when present, and XMP can consume both |
| Preserved JSON fields | `prompt_id`, `description_sha256`, approved model-identification fields, and custom-schema SHA version handling continue to work |
| Hierarchical guidance | Single and multi-segment preferred category paths reach the actual built-in JSON request through its macro; a user replacement can omit or change guidance without injected category instructions |
| Known categories | A synthetic successful JSON generation accumulates a category hierarchy, and a later independent CLI invocation using the same initialized repository can access it |
| Initialization and resolution | `init` creates a repository in CWD; normal processing does not; CLI > YAML > CWD ancestors > image ancestors > memory works, including nested/conflicting repositories |
| Nonblocking state failures | Primary stages still complete and publish valid sidecars when state is unavailable or fails; visible error output reports the state problem even on primary success, without silent substitution of another persistent repository |
| State concurrency/evolution | Independent processes can safely reuse one repository; versioned state supports migrations without destructive replacement |
| Regression | Existing stage independence, XMP policies, source-image preservation, and prior accepted compatibility behaviors remain intact |

Tests should rely on synthetic data and independent prompt fixtures where exact text is required. They should establish application behavior, not judge the accuracy of a particular user-selected model. The implementation plan will specify the necessary test cases; this REQ does not mandate additional live model calls.

## 8. Design decisions requiring Product Owner review if scope changes

The implementation design must settle mechanics needed to fulfill the approved behaviors, including macro parsing and value formatting, JSON envelope compatibility, category accumulation rules, SQLite schema/migrations/concurrency, initialization details, directory discovery, and nonblocking state diagnostics.

These are **design details, not permission to add product requirements**. Any proposal to add historical taxonomy imports, automatic reconciliation, prompt tracking, sidecar/state transaction coupling, extra retries, or new functionality must be presented separately for explicit Product Owner approval before entering a requirements document or implementation prompt.

## 9. Completion boundary

Slice 3 can be accepted when the fully user-controlled prompts and macros, hierarchical preferred-category paths, general-purpose state with reusable category history and explicit initialization/discovery, nonblocking state behavior, and opt-in `prompt_sha256` meet the above outcomes.

Native batching, native search, scheduling, digiKam-specific automation, and historical taxonomy import are not Slice 3 acceptance conditions. Acceptance of this document is separate from authorization to implement it.
