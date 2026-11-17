# Image Clarus Slice 2 - Discovery

**Date:** 2026-11-17

**Status:** Discovery record for review; not an implementation plan or an approved replacement for the canonical requirements

**Project:** `image-clarus`

**Intended repository path:** `docs/slice-2/DISCOVERY-slice-2.md`

## 1. Purpose and evidence boundaries

Record the observations, experiments, discussions, and product decisions leading toward Slice 2: enhancing structured JSON for useful image metadata and publishing selected metadata into digiKam-compatible XMP sidecars. Preserve the distinction between observed application behavior, agreed functional direction, and choices still requiring detailed design.

Slice 1 is closed at application version `0.1.7`. Slice 2 has not yet been implemented. The proposed [`REQ-slice-2.md`](REQ-slice-2.md) records scope and traceability; a later implementation plan will resolve technical contracts and execution steps.

**Sources consulted**

- Canonical repository: `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, `docs/slice-1/IMPL-A3-COMPLETED.md`, and `docs/slice-1/IMPL-C5-COMPLETED.md` on `main` as inspected 2026-11-17.
- Current resources: `prompts/image-description.txt`, `prompts/image-structure.txt`, and `schemas/image-structure.schema.json` on `main`.
- Product Owner's interactive digiKam tests, screenshots, and six successive XMP sidecar snapshots shared during the 2026-11-17 conversation.
- Conversation continuity record dated 2026-11-16, used for context rather than as a substitute for the canonical repository documents.

**Public-repository privacy boundary:** The uploaded XMP snapshots contain real device and photographic metadata. They were used for analysis only. Do not commit the raw samples, original photographs, unsanitized screen captures, paths, device identifiers, owner information, locations, or other personal metadata. Examples in this record are limited to generic tag structures and metadata property names. Public regression fixtures must be synthetic or explicitly sanitized.

## 2. Starting point - what Slice 1 provides

The existing single-image pipeline is:

    image.jpg
      -> desc stage -> image.jpg.desc.txt
      -> json stage -> image.jpg.desc.json
      -> future xmp stage -> image.jpg.xmp

- The default description prompt is exactly `Fully describe and explain everything about this image.` The persisted `.desc.txt` is intentionally comprehensive.
- The JSON stage consumes the persisted description; it does not require the description stage to run in the same invocation.
- The built-in JSON payload schema is currently identified as `urn:image-clarus:metadata-schema:1.0.0`. The application separately supplies the envelope and provenance.
- The current `metadata` payload contains `subjects`, `objects`, `actions`, `setting`, `visual_characteristics`, and `keywords`. It has **no dedicated title, concise caption/description, or ranked hierarchical tag recommendations**.
- The default JSON prompt limits assertions to information explicitly stated or directly supported by the persisted description. This evidence boundary should be retained when deriving more user-oriented metadata.
- The built-in schema allows replacement with a custom schema. Schema identity/version is separate from application version. Existing valid JSON outputs normally skip unless explicitly regenerated.
- Stage selection, persisted handoffs, source-image immutability, artifact validation, safe-write/recovery, and stage-specific ownership were established in Slice 1.
- At Slice 1 closeout, the XMP writer was not implemented; directory/pattern traversal, batching, and functional search were deferred.

**Discovery gap:** Descriptive fields and searchable keywords are useful information, but they are not automatically a well-selected title, a publication-ready caption, or an intentionally ranked set of XMP tags. The JSON product should remain rich enough for other future consumers; it should not be reduced to the requirements of digiKam alone.

## 3. What makes a useful tag

### 3.1 Tag purpose

The Product Owner defined the central goal: **tags are concepts a person will look for when trying to find an image**. Extraction of visible nouns alone is insufficient.

A useful set may include:

- Specific subjects, such as `bell pepper`.
- General searchable concepts, such as `pepper` or `vegetable`.
- Relevant scene/context concepts, such as `garden`, `plant`, or `gardening`, **when supported** by the description.
- Distinct applicable concepts rather than an arbitrary fixed number of tags.

For example, a pepper still growing on a plant can support `plant`; a picked pepper on a plate does not automatically establish that a plant is depicted. Recognized broad categories may be useful without being separately named in the input description, but generated claims should not invent unsupported circumstances, identities, locations, or events.

### 3.2 Ranking and limits

**Agreed functional direction**

- JSON produces tag recommendations in **descending order of expected search usefulness**.
- The model is not required to manufacture a fixed number of recommendations. A photograph may support a handful or dozens.
- The XMP stage should allow a user-configured **top-N publication limit** (for example, publish 10 of 40 recommendations).
- Ranking should consider both specificity and general discoverability. A broad term is not automatically inferior merely because a more specific term exists.
- Redundant near-synonyms should not crowd more distinct, useful concepts out of a truncated list.

**Unresolved detail:** How a top-N limit counts the same concept mapped into more than one hierarchy (for example, `food/pepper` and `plant/pepper`) has not been decided.

### 3.3 Existing `keywords` versus selected tags

The existing `keywords` field must remain useful for broad structured retrieval and future consumers. Some keywords may be URLs, descriptive context, or other values unsuitable for publication as tags. A ranked tag recommendation is a **derived publishing candidate**, not a replacement for descriptive metadata or an instruction to publish every keyword.

The proposed working name `tag_candidates` is not yet a frozen schema contract. Its shape may need to represent ranking and hierarchical placement explicitly.

## 4. What digiKam revealed about hierarchies

### 4.1 Parent/child assignments are distinct

The Product Owner tested a photograph with manually managed `food/pizza` and an unrelated auto-generated `auto/plate` tag. The sidecar was saved before and after unchecking the *parent* `food` while leaving *child* `pizza` checked.

| Representation | Parent explicitly assigned | Parent unchecked, child retained |
| --- | --- | --- |
| `digiKam:TagsList` | `food`, `food/pizza`, `auto/plate` | `food/pizza`, `auto/plate` |
| `lr:hierarchicalSubject` | `food`, `food\|pizza`, `auto\|plate` | `food\|pizza`, `auto\|plate` |
| `dc:subject` | `food`, `pizza`, `plate` | `pizza`, `plate` |
| `acdsee:categories` | Parent and child marked assigned | Parent unassigned; child assigned |

The rows summarize field values observed in the provided XMP snapshots; they do **not** establish which fields Image Clarus must write.

**Observed user-interface behavior**

- The photograph remained discoverable when filtering on `food` after its explicit assignment was removed, because it still had `food/pizza`.
- The individual image's displayed tags changed from including `food` to showing only the assigned descendant and other tags.
- The checkboxes reflected explicit assignment separately from membership in a category hierarchy.

**Implication:** A hierarchy path and an explicitly assigned parent tag are not the same thing. Publishing `ai/food/pizza` need not also explicitly assign `ai/food` to support ancestor-based browsing. This is the preferred behavior unless later evidence changes the decision.

### 4.2 Representations and separators

Samples showed the following forms for a single hierarchical assignment:

| Field | Example | Observed use |
| --- | --- | --- |
| `digiKam:TagsList` | `food/pizza` | Full hierarchy with `/` |
| `lr:hierarchicalSubject` | `food\|pizza` | Full hierarchy with `\|` |
| `dc:subject` | `pizza` | Flat terminal tag name; loses ancestry |
| `acdsee:categories` | Nested `food` / `pizza` with assignment attributes | Additional application-specific hierarchy state |

The samples demonstrate **coexistence**, not a verified writable-field minimum. `dc:subject` can mix manual and generated terms; careless replacement could destroy unrelated tags. The HLD already requires preserving unrelated metadata and warns against assuming that an observed field, including `lr:hierarchicalSubject`, must be written.

### 4.3 Automatic, manual, and generated roots

The screenshots showed `auto/bell pepper` from digiKam's classifier and the manually organized `food/pepper`. The Product Owner explicitly rejected treating duplication across roots as a primary concern.

**Agreed direction:** Keep Image Clarus tags under the independently controlled configurable root `ai` by default, distinct from digiKam's `auto` and user-maintained hierarchies. The `ai` root is a **tag hierarchy root**, not an XML namespace.

Another screenshot showed digiKam auto tags with comma-separated synonym-like labels and one checkbox per displayed item. This is an observation of the UI, **not proof of the underlying synonym model** and not a convention Image Clarus must reproduce.

### 4.4 Preferred categories supplied by the user

Users may provide their own top-level categories, with others added over time. For example, a fictional taxonomy might include `architecture`, `weather`, and `wildlife`. These are examples of **user preference**, not universal application categories.

**Agreed direction**

- Provide a configurable list of preferred categories to guide **JSON-stage inference**.
- Recommend hierarchy placement when an image concept meaningfully belongs to a preferred category.
- Do not force every tag into a category. Uncategorised recommendations are valid.
- Allow placement in multiple applicable categories when justified, such as a pepper that is both a food and part of a growing plant.
- The category list should be extensible and should not be hard-coded to this user's taxonomy.
- JSON, not XMP, makes the semantic categorization decision; the XMP stage applies the resulting recommendations deterministically.
- JSON recommendations do not include the configured XMP ownership root; the XMP stage applies that root when publishing.

**Not yet decided:** The final configuration key, whether unlisted new categories may be inferred by default, the output representation of multiple assignments, and the details of top-N counting.

## 5. Title, caption/description, and caption author

### 5.1 UI terminology and purpose

The Product Owner located editable **Title**, **Captions**, and **Caption Author** controls under digiKam's **Description** sidebar. Title and caption can also appear below thumbnails when those display settings are enabled.

For Image Clarus:

- `title` means a concise, human-readable identification of the photograph.
- JSON `description` means a shorter, useful **digiKam caption**, different from the comprehensive `.desc.txt` analysis.
- Caption author identifies the person who authored/edited the caption; it is **not** inferable from the image.

A machine-generated title and caption should use visible or otherwise supported information and should not fabricate personal history, location, chronology, or intent. The schema and prompt must distinguish these publication-oriented fields from general descriptive extraction.

### 5.2 Why the initial title and caption were missing in XMP

The first inspected XMP sample lacked the title, caption, and caption-author fields even though those values were visible in digiKam. The Product Owner found that relevant metadata writing options were **not enabled by default in that installation**, enabled them, and edited the caption. The next XMP snapshot contained caption data. Editing the title then produced a subsequent snapshot with title data.

**Observed boundary:** digiKam's database/UI content does not prove that the corresponding XMP sidecar has already been updated. The exact UI/database synchronization behavior for changes made externally by Image Clarus still needs validation.

### 5.3 Observed XMP fields

The successive snapshots from one manually edited image showed:

| Property | Observation |
| --- | --- |
| `dc:description` | Appeared after the caption edit, encoded as `rdf:Alt` with `xml:lang="x-default"` |
| `tiff:ImageDescription` | Also held the caption text |
| `exif:UserComment` | Also held the caption text |
| `acdsee:notes` | Also held the caption text |
| `digiKam:CaptionsAuthorNames` | Contained the caption author entered in the digiKam UI |
| `acdsee:author` | Also held that author value |
| `digiKam:CaptionsDateTimeStamps` | Contained a caption modification timestamp |
| `dc:title` | Appeared only after a separate title edit, encoded as `rdf:Alt` with `x-default` |
| `acdsee:caption` | Appeared with the title value, despite the name `caption` |

`photoshop:CaptionWriter` had been mentioned as a possible general metadata field during discussion, but **was not observed** in the supplied digiKam-generated sample. Do not treat it as an established digiKam mapping.

These are **observed representations**, not an instruction to write all of them. Exact field-write requirements, preservation, XMP language handling, and ExifTool round trips remain detailed-design work.

### 5.4 Agreed title/caption/author behavior

- JSON generation adds publication-oriented `title` and `description` information while keeping the comprehensive description and existing structured information.
- Title and description use the existing HLD policies independently: `new` (default), `overwrite`, and `disabled`.
- Caption author is **optional and config-supplied**, not model-generated. **If no author is configured, Image Clarus must not modify author metadata.**
- If an author is supplied, its update behavior should independently support `new`, `overwrite`, and `disabled`, with `new` the agreed default direction.
- Preserve unrelated user-edited titles, captions, and metadata according to the chosen policies; never alter original image bytes.

## 6. Separation of concerns and pipeline implications

The design preserves the established file-in/file-out processing stages:

    source image
       |
       v
    desc stage -> comprehensive .desc.txt
       |
       v
    json stage -> .desc.json
       |         existing rich descriptive fields
       |         + concise title
       |         + concise caption / description
       |         + ranked tag and hierarchy recommendations
       v
    xmp stage  -> deterministic selection, field policies, XMP mapping
       |
       v
    image.jpg.xmp

- The JSON stage performs semantic inference, ranking, and category placement, using the persisted description and configurable category guidance.
- The XMP stage consumes persisted structured metadata without additional model calls. It applies top-N selection and independently configured tag/title/caption/author update policies.
- The shared artifact service retains responsibility for recoverable writes; ExifTool is the initially selected optional XMP backend per the HLD.
- XMP is a publication target, not the sole authoritative representation for description, context, or future search consumers.
- Adding fields to newly generated JSON does not update existing artifacts. Existing valid JSON is skipped by default; explicit regeneration replaces the complete JSON artifact rather than merging individual fields. Older artifacts lacking information required by a selected XMP operation follow the existing missing-prerequisite policy; the single-image default is an actionable failure.
- The source image is never modified. An existing XMP sidecar may contain manual tags and many unrelated fields that must survive the operation.

The *working names* `title`, `description`, and `tag_candidates` are useful for discussion; the final schema and compatibility contract are **not yet frozen**.

## 7. Connection to the canonical REQ and HLD

This discovery elaborates existing end-state requirements. It does not silently replace or narrow them.

| Canonical area | Relationship to Slice 2 discovery |
| --- | --- |
| `REQ-image-clarus.md` - Structured metadata expectations | Adds detail for useful titles, concise descriptions, ranked tag recommendations, and hierarchical categorization; retains all existing descriptive fields and model/prompt provenance |
| `REQ-image-clarus.md` - XMP metadata integration | Provides real digiKam observations for hierarchy, title, caption, and author; carries forward the ownership root, preservation, and field-specific policy requirements |
| `REQ-image-clarus.md` - Configuration and precedence | Introduces preferred-category guidance, XMP top-N selection, and optional caption-author configuration; exact keys and defaults require design |
| `REQ-image-clarus.md` - Safe-write requirements | Carries forward source-image immutability and shared artifact/recovery requirements, including Slice 1 filesystem compatibility corrections |
| `HLD-image-clarus.md` - XMP design | Keeps ExifTool initially, generated hierarchy under `ai`, tag policy default `add`, and title/description policy default `new`; mapping details and fixture validation remain open |
| `docs/slice-1/IMPL-A3-COMPLETED.md` | The existing JSON `1.0.0` payload contract and provenance envelope must be evolved deliberately; old outputs and custom schemas require compatibility handling |
| Later slices | Multi-image selection/traversal, batch processing/operational controls, deterministic search, and embeddings/semantic search remain outside the proposed single-image Slice 2 |

One historical nuance: Slice 1 A3 described `keywords` as the canonical search-term/tag field. Slice 2's proposed `tag_candidates` should be defined as a **different derived recommendation product**, rather than accidentally duplicating or deleting general-purpose `keywords`. The formal Slice 2 REQ/design should make this change explicit.

## 8. Decisions and unresolved design questions

### 8.1 Agreed functional direction

| Topic | Agreed direction |
| --- | --- |
| Scope | Single-image JSON metadata enhancement and digiKam-compatible XMP publication |
| Tag utility | Recommend concepts a human would search for; support specific and general terms |
| Ranking | Descending usefulness; configurable top-N selection for XMP |
| Tag count | No forced candidate count |
| Hierarchy | Recommend paths when meaningful; do not require a category |
| Categories | User-configured preferences; may use multiple applicable categories |
| Ownership | Configurable `ai` hierarchy root by default; separate from `auto` and manual tags |
| Duplicate concepts across roots | Acceptable; cross-root deduplication is not a priority |
| Semantic work | JSON stage; no model inference inside XMP stage |
| Title | JSON-generated concise title; independent XMP update policy |
| Description | JSON-generated usable caption, distinct from comprehensive `.desc.txt`; independent policy |
| Caption author | Optional config value; absent means **no author-field modification** |
| Data preservation | Preserve unrelated XMP data/manual tags and original image bytes |
| Deferred | Directory/pattern traversal, batch operation, deterministic and semantic search |

### 8.2 Technical details still open

These are **design questions**, not reasons to reopen the completed Slice 1:

1. **JSON representation:** What exact structure represents ranked recommendations and category paths without the XMP ownership root? Strings, structured items, or another form? How are uncategorized recommendations represented?
2. **Ranking/counting:** How does top-N behave when one concept appears in multiple categories? Is ranking by concept, final assignment, or both? How are ties, duplicate paths, case variants, and synonyms handled?
3. **Category configuration:** What exact keys and defaults convey preferred categories to the JSON stage? May the model add new top-level categories not listed by the user, and under what rules?
4. **Tag validity and safety:** How are invalid/empty values, path separators, control characters, misleading inferences, duplicates, and unsupported hierarchical claims handled?
5. **Schema evolution:** Versioning the built-in schema and defining a process for future releases, including supported readers, older `.desc.json` sidecars, explicit migration or regeneration, and replacement user schemas. Create-if-missing and full-artifact regeneration remain the established behavior.
6. **XMP write targets:** Which properties must ExifTool write for digiKam to display and edit hierarchy correctly? If a shared flat keyword must be changed, how can ambiguous ownership be handled without removing unrelated values? Preserve ambiguous values; observed coexistence alone does not require writing the property.
7. **Title/caption/author mappings:** How are `rdf:Alt`/`x-default`, existing localized values, configured caption author, and extra digiKam/vendor representations handled? Which field synchronizations are essential versus observed side effects?
8. **XMP update and recovery:** Merge/preservation validation, existing XMP handling, stage-specific results, recoverable publication, and interaction with the documented lock-free/last-write-wins constraint.
9. **digiKam refresh:** How are externally written sidecars imported or rescanned so the database/UI displays the result? Verify rather than assuming immediate visibility.
10. **Validation fixtures:** Create synthetic or sanitized representative XMP samples and run digiKam/ExifTool round-trip checks without publishing original operator data.

## 9. Suggested handoff to the Slice 2 REQ

Review `docs/slice-2/REQ-slice-2.md`, which proposes Slice 2 functionality, explicit inclusions/exclusions, acceptance criteria, and traceability to the overall REQ. Use this discovery document as supporting evidence, not as a competing specification. Existing canonical requirements and HLD decisions remain in force unless explicitly revised through the project's normal design process.

Then reconcile architectural decisions into `docs/HLD-image-clarus.md` where they establish durable boundaries. Create `docs/slice-2/IMPL-PLAN-slice-2.md` only after the Slice 2 requirements and relevant high-level design are accepted. The plan should resolve the remaining schema, configuration, field-mapping, compatibility, and verification decisions before implementation.
