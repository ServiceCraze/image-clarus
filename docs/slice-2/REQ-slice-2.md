# REQ - Image Clarus Slice 2

**Date:** 2026-11-17

**Status:** Proposed Slice 2 functional requirements for Product Owner review; not yet an accepted implementation contract

**Project:** `image-clarus`

**Intended repository path:** `docs/slice-2/REQ-slice-2.md`

**Parent requirements:** [`../REQ-image-clarus.md`](../REQ-image-clarus.md)

**Architecture:** [`../HLD-image-clarus.md`](../HLD-image-clarus.md)

**Discovery:** [`DISCOVERY-slice-2.md`](DISCOVERY-slice-2.md)

**Previous slice closeout:** [`../slice-1/IMPL-C5-COMPLETED.md`](../slice-1/IMPL-C5-COMPLETED.md)

## 1. Purpose and document authority

Slice 2 makes the existing single-image structured metadata pipeline useful for **digiKam-compatible XMP publication**. It extends the JSON-stage output with a concise title, a useful caption/description, and ranked recommendations for searchable hierarchical tags. A new, independently selectable XMP stage applies that persisted information using deterministic update policies, without modifying the source image.

This document **specializes the overall REQ for Slice 2**. It does not replace or silently narrow the end-state requirements. The overall REQ governs the project; the HLD governs established architectural boundaries; this document defines Slice 2 deliverables and acceptance outcomes. The discovery document explains the experiments and reasoning but is not itself a normative contract. The subsequent HLD reconciliation and Slice 2 implementation plan will freeze exact field mappings, JSON representation, configuration keys, and detailed execution behavior.

The words **must** and **shall** identify required Slice 2 behavior; **may** denotes permissible behavior subject to design or configuration. Requirements IDs beginning `S2-` are local to this slice, not new identifiers imposed on the overall REQ.

## 2. Scope boundary

### 2.1 Included

- Enhance the **existing `json` stage** for one image to generate title, concise caption/description, and ranked tag recommendations, including meaningful hierarchy placement informed by configurable user-preferred categories.
- Preserve the existing broad structured metadata and provenance as independently useful information, not merely an XMP input.
- Implement the independently selectable **`xmp` stage** for one image, using persisted structured JSON to create/update a `.xmp` sidecar compatible with digiKam.
- Support deterministic tag selection and hierarchy publication, independent policies for tags/title/caption, and an **optional, config-supplied caption author**.
- Preserve unrelated metadata and, for a non-empty generated root, tags outside that root; an explicitly empty root preserves all existing tags. Use the existing shared recoverable sidecar-writing mechanisms.
- Verify the behavior with synthetic/sanitized XMP fixtures, ExifTool round trips, and real digiKam read/edit checks where necessary.

### 2.2 Not included

- Directory selection, file patterns, recursive traversal, multi-image batches, or expanded operational batching controls.
- Functional deterministic search, embeddings, or semantic search.
- Model inference inside the XMP stage; any new model-driven stage beyond the existing JSON stage.
- Synchronization with the user's existing manual hierarchy or deduplication across `ai`, `auto`, and manually maintained tag roots.
- General-purpose reconciliation of prior tags removed from regenerated JSON; only the already defined generated-root `overwrite` policy is in scope.
- A required centralized image database, job queue, internal scheduler, or new provider protocol.
- Synchronization of other applications' tag/keyword representations is outside Slice 2, except where a representation is verified to be necessary for digiKam interoperability. The overall REQ's independently optional mappings remain end-state requirements.
- Exhaustive operating-system/filesystem compatibility testing or a guarantee of crash-proof persistence.

Slice 2 remains useful through a **single-image CLI invocation**, whether running `desc`, `json`, `xmp`, or a selected combination. Later-slice capabilities remain required by the end-state REQ but are not Slice 2 acceptance conditions.

## 3. Requirements traceability

| Overall REQ area | Slice 2 relationship | Local requirements |
| --- | --- | --- |
| **Guiding requirements; Processing stages and artifacts; Stage dependencies** | **Inherit and implement:** independently executable, ordered, persisted single-image stages; no source-image modification | S2-01, S2-02, S2-16 |
| **Model providers and prompts; Structured metadata expectations** | **Refine:** existing structured output gains publication-oriented title/caption and recommended tags, while retaining general-purpose metadata and configurable prompt/schema | S2-03 through S2-10, S2-17 |
| **XMP metadata integration** | **Implement and refine:** deterministic digiKam sidecar publication, default `ai` ownership boundary or explicitly empty additive-only root, tag/title/description policies, metadata preservation, validation | S2-11 through S2-16, S2-18 |
| **Configuration and precedence** | **Extend:** preferred categories, tag publication limit, and optional caption author; inherit CLI > selected file > defaults | S2-08, S2-10, S2-13 through S2-15 |
| **Safe-write requirements; Failure policies, retries and logging** | **Inherit:** recoverability, validation, stage results, error behavior, existing filesystem-capability handling | S2-16, S2-18 |
| **Input selection and traversal; Search; External scheduling** | **Defer from this slice without removing end-state requirements** | Section 2.2 |

**Explicit refinement of the Slice 1 JSON contract:** The Slice 1 A3 design treated `keywords` as the canonical general searchable-term/tag field. Slice 2 introduces **distinct ranked publication candidates**, rather than deleting, repurposing, or duplicating the broad-purpose meaning of `keywords`. This requires a deliberate schema/prompt evolution and documentation reconciliation, not a retroactive rewrite of the Slice 1 closeout.

## 4. Single-image pipeline requirements

### S2-01 - Persisted handoffs and stage independence

- The existing `desc` stage must continue to produce a comprehensive `photo.jpg.desc.txt` using its existing contract; the built-in description prompt remains unchanged.
- The `json` stage must read the persisted `.desc.txt` and produce schema-validated `.desc.json`; it must remain independently invocable.
- The `xmp` stage must read persisted structured metadata and optionally existing `photo.jpg.xmp`; it must remain independently invocable without requiring a model invocation or automatically executing `desc` or `json`.
- Stage selection and registry ordering must follow the existing HLD contract. An XMP update has field-specific policies rather than the description/JSON create-only semantics.

### S2-02 - Artifact and source-image boundaries

- The original image bytes must never change.
- Description, structured JSON, and XMP outputs must retain the established adjacent sidecar naming conventions.
- An XMP edit must preserve information outside fields explicitly authorized for update, including unrelated XML namespaces, manual tags, camera/exposure data, and vendor-specific metadata.

## 5. Structured JSON output requirements

### S2-03 - Additive information product

- The built-in JSON payload must retain the existing `subjects`, `objects`, `actions`, `setting`, `visual_characteristics`, and `keywords` information, together with the application-owned envelope and provenance.
- It must add distinct, explicitly identifiable outputs for a **title**, **concise caption/description**, and **ranked tag recommendations**.
- These outputs must remain persisted and usable by consumers other than XMP. Do not reduce or replace the comprehensive `.desc.txt` with the shorter caption.
- Exact property names, nesting, optionality, and item shape will be frozen in design. Working names `title`, `description`, and `tag_candidates` do not by themselves establish the final schema.

### S2-04 - Title generation

- Generate a short, meaningful, human-readable identification of the image from information supported by the persisted description.
- Avoid inventing identities, locations, dates, relationships, or events not established by the input.
- The title must be independently addressable by the XMP consumer.

### S2-05 - Caption/description generation

- Generate a readable image caption that communicates the main subject and useful supported context.
- The caption must be distinct in purpose from the comprehensive visual analysis in `.desc.txt`; it need not include every visible detail.
- It must not invent a personal story, intent, or other context unavailable from the persisted description.
- The caption must be independently addressable by the XMP consumer. In digiKam this human-readable description is called a *Caption*.

### S2-06 - Human-search-oriented tag candidates

- Recommend concepts a person might reasonably search for to locate the image, not merely a mechanical extraction of nouns.
- Candidates may include specific subjects, useful broader concepts, and relevant scene or activity context when supported by the description.
- Broad generalization is permitted when semantically justified (for example, a bell pepper is a kind of pepper); unsupported contextual assertions are not.
- Recommendations should avoid unnecessary synonym/near-duplicate saturation that would crowd distinct useful concepts out of a shortened list.
- There is **no fixed required candidate count**; produce the useful candidates the input supports, including none when appropriate.
- Recommendations must be ordered **from greatest to least expected search usefulness**, so truncation retains higher-priority candidates.

### S2-07 - Hierarchical categorization

- The JSON stage must recommend hierarchical placement for candidates where a meaningful category relationship exists.
- Recommendations describe categories and tag concepts, not the XMP ownership root. The XMP stage applies the configured root when non-empty; an explicitly empty root adds no prefix. The root is not embedded in JSON tag recommendations.
- A recommendation must be able to remain **uncategorized** when no useful category applies.
- A concept must be able to appear in more than one applicable hierarchy when warranted; no rule may force all concepts into a single exclusive category.
- Category placement must not be fabricated solely to fill a hierarchy. For example, `plant` is appropriate for a depicted growing plant, but should not be automatically inferred as depicted for picked produce on a plate.
- Hierarchical paths must distinguish *path membership* from *explicit parent assignment*. Publication of a descendant (such as `ai/food/pizza`) must not require separately assigning every ancestor as an image tag.

### S2-08 - Preferred categories as user guidance

- Configuration must allow a user to provide **preferred category names** to guide the JSON stage's semantic categorization.
- Preferred categories are examples of a user's taxonomy, not built-in mandatory universal top-level categories. A fictional example list might include `architecture`, `weather`, and `wildlife`; it must not be hard-coded as the application's taxonomy.
- A preferred category must be used only where meaningful, and must not require every candidate to be categorized.
- Multiple meaningful preferred categories may apply to one image or concept.
- Design must decide how recommendations can introduce categories not present in the preferred list and how an absent/empty configured list behaves; no mandatory closed taxonomy is implied.

### S2-09 - Preserve inference/publishing separation

- Model inference, recommendation ranking, and semantic hierarchy decisions belong to the **JSON stage**, informed by its persisted description and selected configuration.
- The **XMP stage must not call a model** to rank, interpret, categorize, or repair recommendations. It must deterministically select and transform already persisted information, validating it before publication.
- Configurable category preferences must be available to the JSON stage, not merely interpreted by the XMP writer.

### S2-10 - Schema, prompt, and historical compatibility

- Continue supporting an independently configurable JSON prompt and a fully replaceable user JSON payload schema, without requiring source-code changes for custom schemas.
- Update and independently version the built-in metadata schema when its payload contract changes; do not confuse schema version with application version or the existing envelope format version.
- Preserve the established application-owned provenance/envelope behavior, including description and prompt identification.
- The enhancement is additive to the built-in payload's information, not an automatic in-place update of existing files. Respect create-if-missing: a structurally valid existing JSON sidecar is skipped by default even if its payload uses an older schema. Explicit JSON regeneration may replace the entire sidecar with newly generated content; it does not promise a field-by-field merge or preservation of manual JSON edits.
- A missing required `.desc.json` artifact follows the existing configurable missing-prerequisite policy; the built-in default for explicit single-image input is failure. XMP must not silently regenerate JSON.
- An absent or supported empty optional title, caption, or tag recommendation list means no update to the corresponding XMP metadata, even under `overwrite`. Other available, valid metadata may still be published according to its policies; no missing-prerequisite failure or JSON regeneration is required merely because an optional field is absent.
- Invalid or incompatible structured input must produce an appropriate validation or compatibility failure, not a false successful publication. Define and test valid empty values, recognized historical and custom-schema mappings, and invalid structures without misinterpreting arbitrary fields. Do not assume that every historical or custom payload is incompatible solely because of its schema identity.
- Define a documented, independently versioned metadata-schema evolution and compatibility process for future releases, including identification, supported readers, handling older artifacts, and explicit migration or regeneration choices where applicable. Do not require automatic migration or regeneration.

## 6. XMP publication requirements

### S2-11 - Deterministic and digiKam-compatible publication

- Add `xmp` as the third registered processing stage, using the established source-image filename plus `.xmp` sidecar suffix.
- Use **ExifTool** behind the established replaceable XMP-backend boundary as the sole initial backend. ExifTool must be required only when the XMP stage is selected.
- Map validated persisted JSON outputs into digiKam-compatible XMP metadata without modifying the source image.
- Validate the actual minimum writable field set using ExifTool round trips and digiKam; the mere presence of a representation in a digiKam-produced sidecar does not establish that Image Clarus must write it.

### S2-12 - Generated tag ownership and policies

- The configurable tag-hierarchy root defaults to the built-in `ai` when the setting is omitted. An explicitly configured empty string (`""`) means no added root prefix and permits publication directly into top-level hierarchies. An omitted setting and an explicit empty string must remain distinct through configuration precedence. This root is **not an XML namespace**. Do not use digiKam's `auto` root by default.
- **Explicit empty-root exception:** With an empty root, `disabled` leaves tags unchanged; each of `add`, `new`, and `overwrite` has the effective behavior of `add`. Add recommended assignments without duplicates and never delete existing XMP tags, including in any tag representations touched by the operation. This override applies only to an explicitly empty root; for a non-empty root the selected policy applies normally. Title, caption, and author policies remain independent.
- Duplication of a concept under other, independently owned roots (for example `auto/bell pepper` versus `ai/food/bell pepper`) is acceptable; cross-root deduplication is not required.
- Support the established tag policies for a non-empty root:
  - `add` (**default**) - add recommended assignments within the generated root without duplicate assignments;
  - `overwrite` - replace assignments **only within the generated root**;
  - `new` - populate recommendations only when the generated root has no existing tags for the image;
  - `disabled` - do not modify generated tags.
- For a non-empty root, never alter assignments outside the configured generated root; all assignments within that root, including manually added ones, are governed by its selected policy.
- Preserve unrelated values in any shared flat keyword property. A flat value may not carry enough information to establish which hierarchy owns it; define and test safe handling before modifying such a property. Preserve ambiguous values rather than removing unrelated metadata, and do not require writing a representation solely because it was observed.
- Preserve the distinction between hierarchy ancestors and explicitly assigned tags. A parent category need not be independently assigned merely because a child is assigned.
- Preserve manual and other-system tags outside a non-empty configured root, and all existing tags when the root is empty. Do not attempt cross-root taxonomy reconciliation.

### S2-13 - Ranked top-N publication

- Configuration must support limiting the number of ranked tag recommendations published to XMP (for example, the top 10 of 40), without requiring the model to generate a fixed number.
- Selection must follow the persisted ranking; the XMP stage may validate and deduplicate deterministically but must not semantically reorder candidates.
- The exact counting rule for one concept mapped into multiple hierarchical paths, default limit, and handling of invalid/duplicate recommendations are detailed-design decisions and must be defined unambiguously and tested before implementation acceptance.

### S2-14 - Title and caption update policies

- The XMP stage must publish available generated title and caption/description independently, following field-specific policies of `new`, `overwrite`, and `disabled`; absent or supported empty source values leave the corresponding destination unchanged.
- For **both** fields the built-in default must be `new`, meaning populate only when the destination field is absent or empty.
- `overwrite` must modify only the corresponding authorized field/value; `disabled` must leave it unchanged.
- Mappings must be compatible with digiKam's title and caption editing. The observed `dc:title` and `dc:description` representations, including `rdf:Alt` / `x-default` language handling, are starting evidence; exact authoritative write targets and preservation rules require validation.
- Do not silently overwrite unrelated localized values or other metadata representations as a side effect of writing a title or caption.

### S2-15 - Optional caption author

- Caption author must be an **optional user-supplied configuration value**, not generated or inferred by the JSON model and not required for ordinary processing.
- **When no caption author value is configured, the XMP stage must not modify any caption-author metadata.** There is no built-in author identity.
- When an author is provided, independently support `new` (**default**), `overwrite`, and `disabled` update policies, analogous to title/caption policies.
- Verify digiKam-compatible author representation before freezing the mapping. The observed `digiKam:CaptionsAuthorNames` is evidence; `photoshop:CaptionWriter` was not observed in the supplied sample and must not be assumed as the required mapping.
- Caption author must not be conflated with the photographer or original image creator.

### S2-16 - Existing XMP, write integrity, and failures

- Creating or updating XMP must reuse the established shared artifact service for staging, validation, safe publication, backups, and recoverability, subject to the documented lock-free/last-write-wins concurrency boundary.
- Field-specific merge behavior must be tested on XMP sidecars containing existing manual tags, unrelated metadata, and vendor properties. An implementation may atomically replace the sidecar file as part of safe publication, but must preserve unrelated metadata within its content.
- Validate the resulting XMP and report failure rather than accepting malformed output or an update that violates required ownership/preservation rules.
- A standalone `xmp` invocation with a missing JSON artifact follows the established missing-prerequisite policy; malformed or incompatible input follows the appropriate failure policy. Missing optional publication fields are handled as specified in S2-10. XMP must not covertly regenerate JSON or invoke a model.
- Honor the established stage result/continuation conventions and filesystem-capability-dependent permission handling from Slice 1. No claim of universally atomic, crash-proof, or universally mode-preserving writes is required.

## 7. Configuration and extensibility

### S2-17 - Configuration and model-stage behavior

- The new category guidance must integrate with the existing stage configuration and precedence model: explicit CLI overrides > selected YAML configuration > built-in defaults.
- XMP tag root, tag update policy, top-N selection, title policy, caption policy, and optional caption-author value/policy must be configurable without hard-coding a particular personal taxonomy or identity.
- Validate stage-specific configuration when that stage is selected, consistent with the HLD, so choosing `desc` or `json` does not require ExifTool or a valid unused XMP configuration.
- Keep the existing configurable model/provider selection and prompt overrides for `desc` and `json`. The XMP stage has no model choice.
- Exact YAML keys, CLI options, default top-N, representation of hierarchy guidance, and custom-schema interaction are implementation-design work, not decided by illustrative configuration examples.

## 8. Verification and acceptance

### S2-18 - Required evidence for Slice 2 closeout

Acceptance requires automated checks where practical and an explicitly identified manual digiKam interoperability check. Evidence must distinguish **executed automated tests**, **operator-observed manual behavior**, and **unverified assertions**.

| Area | Required observable outcome |
| --- | --- |
| JSON evolution | Title, concise caption, and ranked recommendations are present in a valid updated built-in JSON payload; original descriptive fields and application provenance remain usable |
| Description evidence boundary | No unsupported person, place, date, history, or contextual claims introduced by title/caption/tag recommendations in representative samples |
| Ranking and category guidance | Representative examples cover specific/general tags, uncategorized recommendations, preferred categories, and multiple appropriate hierarchy assignments; truncation follows ranking |
| Metadata quality | Human review of a small synthetic or sanitized description set evaluates accurate titles, useful supported captions, search-useful ranking, and meaningful categorization without forced placement; record the examples, criteria, and observed outcomes |
| Standalone stages | `json` consumes a persisted `.desc.txt`; `xmp` consumes persisted JSON without additional generation; selected-stage ordering and missing-input behavior follow existing contracts |
| Hierarchical tag semantics | DigiKam recognizes a generated descendant under `ai`; ancestor-based filtering works without independently assigning every parent; other roots remain unchanged |
| Tag policies | With a non-empty root, `add`, `overwrite`, `new`, and `disabled` act only within that root. With an explicitly empty root, `add`, `new`, and `overwrite` all behave as `add`, preserving existing tags without duplicate additions; `disabled` makes no tag changes. Test omitted versus explicit empty settings, each policy, top-level publication, and repeated invocation |
| Title and caption | DigiKam displays and allows editing the generated title/caption; independent `new`, `overwrite`, and `disabled` policies behave as specified |
| Caption author | With no configured author, existing author metadata is unchanged; with a configured value, each supported update policy behaves as specified |
| Metadata preservation | Before/after comparison confirms preservation of tags outside a non-empty configured root or all existing tags with an empty root, unrelated and ambiguously owned shared keyword values, XML namespaces, and camera/vendor metadata |
| Safe-write and failures | Malformed input/XMP, invalid mappings, failed writes, recovery, and unsupported/missing ExifTool have defined outcomes; source-image bytes never change |
| Compatibility | Existing JSON skip and explicit replacement; missing artifact policy; absent or empty optional fields without destructive updates; malformed/incompatible input; and historical and custom-schema mappings are tested. Schema evolution and provenance are documented |
| Configuration | CLI overrides selected YAML and built-in defaults for new settings; stage-specific validation does not require unused XMP configuration or ExifTool for `desc`/`json` |
| Public fixtures | Only synthetic or sanitized files enter the public repository; no raw personal images, unredacted XMP, device metadata, credentials, or private endpoint data |

A digiKam-produced XMP sidecar may contain `digiKam:TagsList`, `lr:hierarchicalSubject`, `dc:subject`, `dc:title`, `dc:description`, `digiKam:CaptionsAuthorNames`, and several other fields. **Observed coexistence does not mandate writing every one of these properties.** The design and verification must determine the minimal compatible write set while preserving unrelated values.

Externally edited sidecars may require digiKam metadata rereading or database synchronization before changes are displayed. Verification must document the actual procedure and observed behavior rather than assuming instant UI refresh.

## 9. Design questions to resolve before implementation

These questions are **not new functional scope**. They must be resolved explicitly in the HLD reconciliation or Slice 2 implementation plan, with tests matched to the resulting contract.

1. Exact JSON field names, types, ordering representation, hierarchy encoding, and semantics of empty/unsupported title/caption/tag values.
2. Top-N counting for a concept recommended in multiple hierarchies, ties, deduplication, path validity, and default limit.
3. Preferred-category configuration format and default behavior; whether and how unlisted categories can be recommended.
4. Built-in JSON schema version and future evolution process; supported empty-value semantics, historical `.desc.json` handling, and mapping of replacement schemas under the rules in S2-10.
5. ExifTool field-write mappings required for digiKam hierarchy, title/caption, and optional author; safe handling of ambiguous ownership in shared flat fields and multilingual `x-default` values.
6. ExifTool/backend validation, field-specific merge behavior, restoration, and result semantics within established artifact-service constraints.
7. digiKam sidecar import/refresh behavior and selection of publishable synthetic/sanitized test fixtures.

These decisions should respect the current HLD's default `ai` ownership root, the explicit empty-root exception above, independent stage contracts, optional XMP-only ExifTool dependency, and existing safe-write mechanisms. Reconcile the empty-root exception into the canonical HLD before implementation. Do not silently revise Slice 1 decisions or narrow requirements for future consumers.

## 10. Completion boundary

Slice 2 is complete only when the **single-image JSON enhancement and XMP/digiKam integration** satisfy the functional requirements and the recorded acceptance evidence above. Passing JSON generation alone does not complete Slice 2; completing XMP without validated preservation and digiKam interoperability does not complete it either.

The next artifact after Product Owner review is the Slice 2 implementation plan, with any enduring architectural updates reconciled to the canonical HLD first. This document does not authorize implementation, repository mutation, or publication of unsanitized discovery materials.
