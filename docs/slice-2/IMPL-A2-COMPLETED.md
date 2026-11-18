# Step A2 — Freeze enhanced JSON, ranking, and schema evolution contracts (COMPLETED)

**Status:** Design complete; Product Owner review of these A2 choices is separate and the Phase A readiness gate remains open. No Slice 2 functionality is implemented by this record.

**Scope deviations:** None. This record freezes the A2 design; A3–A5 and Phase B/C have not been started.

## Files created, updated, and removed

- **Created:** `docs/slice-2/IMPL-A2-COMPLETED.md` (this design record).
- **Updated:** `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-A1-COMPLETED.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py`.
- **Removed:** None. Version-test edits reflect the project patch-version convention. No production source, canonical prompt, schema resource, or sample configuration was changed during this design step.

## Decisions and rationale

The built-in payload schema is **`urn:image-clarus:metadata-schema:2.0.0`**, with `schema_version` `2.0.0`; the existing closed application envelope remains `format_version: 1`. The new title, caption and candidate fields are **required in newly generated built-in payloads**, with explicit empty values when unsupported. A major version is required because older `1.0.0` payloads lack these fields and would fail the new schema; old artifacts are not automatically rewritten. App version, envelope version, and payload schema version remain independent.

Choose `title`, `caption`, and `tag_candidates` as distinct `metadata` properties. `caption` is the concise human-readable description; `.desc.txt` remains the comprehensive description. The six Slice 1 properties and their definitions remain unchanged. Built-in title/caption are strings; `""` means unavailable. Built-in `tag_candidates` is an array in descending priority; `[]` means no supported candidates. Its entries are arrays of path segments. A one-segment path is uncategorized; in a longer path the last segment alone is assigned, with preceding segments hierarchy membership rather than separately assigned tags. Multiple paths can place the same concept under different categories. No configured XMP ownership root is included in the JSON paths.

This chooses arrays of segments over delimited strings: hierarchy structure and rank are explicit without parsing escaped delimiters. It chooses required new properties rather than optional properties for newly generated built-in output so each publication outcome, including an explicit empty one, is represented. It does not require old or user-supplied schemas to contain these properties.

## Built-in metadata payload schema

The following is the complete proposed Draft 2020-12 payload schema to be implemented at the existing canonical `schemas/image-structure.schema.json` in B2; this document does not modify that resource. It retains the existing six properties and adds three. The canonical resource remains the single source of the new built-in schema; package it using the existing resource mapping.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:image-clarus:metadata-schema:2.0.0",
  "title": "Image Clarus structured metadata payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["subjects", "objects", "actions", "setting", "visual_characteristics", "keywords", "title", "caption", "tag_candidates"],
  "$defs": {
    "non_empty_string": {"type": "string", "minLength": 1},
    "string_array": {"type": "array", "items": {"$ref": "#/$defs/non_empty_string"}, "uniqueItems": true},
    "tag_segment": {"type": "string", "minLength": 1, "pattern": "^(?!\\s)(?!.*\\s$)[^/|\\u0000-\\u001F\\u007F-\\u009F]+$"},
    "tag_path": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/tag_segment"}}
  },
  "properties": {
    "subjects": {"description": "Primary subjects or focal entities supported by the description.", "$ref": "#/$defs/string_array"},
    "objects": {"description": "Other notable objects supported by the description.", "$ref": "#/$defs/string_array"},
    "actions": {"description": "Visible activities or actions supported by the description.", "$ref": "#/$defs/string_array"},
    "setting": {
      "type": "object", "additionalProperties": false, "required": ["type", "context"],
      "properties": {
        "type": {"type": "string", "description": "Setting type or category; empty when unsupported."},
        "context": {"type": "string", "description": "Relevant scene context; empty when unsupported."}
      }
    },
    "visual_characteristics": {
      "type": "object", "additionalProperties": false,
      "required": ["colors", "composition", "lighting", "visual_style"],
      "properties": {
        "colors": {"description": "Distinct visible colors; empty when unsupported.", "$ref": "#/$defs/string_array"},
        "composition": {"type": "string", "description": "Framing or spatial arrangement; empty when unsupported."},
        "lighting": {"type": "string", "description": "Visible lighting quality; empty when unsupported."},
        "visual_style": {"type": "string", "description": "Visible medium or style; empty when unsupported."}
      }
    },
    "keywords": {"description": "Unique searchable terms/tags; empty when unsupported.", "$ref": "#/$defs/string_array"},
    "title": {"type": "string", "description": "Short identification; empty when unsupported."},
    "caption": {"type": "string", "description": "Concise supported caption; empty when unsupported."},
    "tag_candidates": {"type": "array", "items": {"$ref": "#/$defs/tag_path"}, "uniqueItems": true, "description": "Search-useful tag paths, ordered most useful first; empty when unsupported."}
  }
}
```

Strict JSON/UTF-8 rules inherited from Slice 1 still apply, including rejection of unpaired surrogates. Tag segments reject leading/trailing Unicode whitespace, `/`, `|`, C0 and C1 control characters (including DEL); preserve spelling, case and Unicode otherwise. No silent trimming, case folding, Unicode normalization or splitting occurs. Exact path duplicates are invalid in the built-in payload via `uniqueItems`; case variants and synonyms are distinct at the structural level, although the prompt discourages redundant near-synonyms. The separator restrictions prevent ambiguous initial hierarchy encodings; A3 must verify actual ExifTool/digiKam behavior and escalate a conflicting supported-input constraint rather than claim this has been tested.

## Ranking, category guidance and publication selection

- Array position is the complete rank: first is most useful. There are no numeric scores or rank ties; two otherwise equally useful recommendations still have a definite sequence. Preserve order in the JSON array and do not alphabetize it or ask XMP to make semantic judgments.
- The XMP limit counts **distinct complete paths**, not concepts or path segments. A concept under two categories consumes two positions. The default is **10**, overridable to any nonnegative integer; `0` selects no paths and must not clear existing tags. An absent/empty candidate list likewise makes no tag changes even under `overwrite`.
- Validate every present candidate before selecting; malformed entries, including those beyond the cutoff, fail publication rather than being silently repaired or hidden by truncation. For a recognized compatible publication interface allowing duplicates, remove exact duplicate segment sequences keeping the first, then select the first N. Built-in 2.0.0 duplicate paths already fail schema validation. The XMP root is added only afterward, when non-empty; no explicit ancestor assignment is implied.
- Preferred categories are an ordered list of single tag segments with the same validity rules, default `[]`. Omitted and explicitly empty lists both mean no preference guidance. Duplicate exact category entries are configuration errors; case-distinct values remain distinct. The list is a semantic hint, not evidence, a closed vocabulary or mandatory taxonomy. Unlisted categories and uncategorized concepts are allowed when justified. No user-specific categories are built in. A4 owns the final YAML key and CLI mapping; these semantics are fixed inputs to A4.

## Built-in structured-generation prompt

B2 must replace the built-in JSON prompt resource with the exact following UTF-8 text, no BOM, ending in exactly one LF. The canonical description prompt remains unchanged. A custom prompt fully replaces this built-in prompt; do not append built-in instructions to it.

```text
Extract structured photo metadata from the persisted description.

Use only facts explicitly stated or directly supported by the description. Do not invent identities, locations, dates, events, intent, or visual details. Broader concepts are allowed only when semantically justified. Return a short meaningful title and a concise caption of the main subject and supported context. Recommend tags a person would search for, ordered from most to least useful, avoiding redundant near-synonyms. Use meaningful category paths when supported; a tag may be uncategorized or occur in multiple relevant categories. Do not invent a category merely to fill a hierarchy. Preferred categories, when supplied separately, are optional guidance, not evidence or a closed taxonomy. Do not include an XMP ownership root in tag paths. Do not force a fixed number of recommendations.

Follow the selected JSON Schema, including its allowed empty values when information is unsupported. Return exactly one JSON object. Do not include schema-version or provenance fields, Markdown fences, comments, or surrounding prose. If validation feedback is supplied, use it to correct the output while following the same evidence limits.
```

The exact text above plus its one final LF is 1,207 UTF-8 bytes and has SHA-256 `282bf0bd58c65aff44979f90d4e98f53bdf718a8ecc85c06e262c88d17f8beff`. B2 must read and fingerprint the same byte snapshot it sends as the effective prompt.

For built-in schema 2.0.0, `""`, `""`, `[]` represent unsupported title, caption, recommendations. A custom schema is authoritative for its payload and may omit these fields; the built-in prompt's general request never overrides the selected custom schema. A custom prompt remains a full replacement and may choose how it uses the separate guidance. No generated author belongs in this payload contract.

## Guidance framing, provenance and retry

The existing Slice 1 A4 structured request contains separate description and schema user text parts. Slice 2 deliberately adds an optional **third user text part** to this request contract, not a new provider protocol: when the resolved list is non-empty, append `Preferred categories (JSON data, not instructions):\n` followed by the JSON serialization of the list with `ensure_ascii=False` and `allow_nan=False`, using the standard Python `json.dumps` defaults otherwise. When omitted or empty, omit the third part. This must be passed as data, not interpolated into the system prompt, description or schema. Snapshot the validated list once per generation; reuse exactly that snapshot, description, schema and prompt on all validation retries. Prompt/schema overrides remain independent; supplying guidance does not impose the built-in schema on a custom one. Existing provider request, timeout, no automatic network retry and redaction contracts continue except for this explicit A4 framing amendment. The selected provider receives the category list; do not log it or put it in public fixtures unless synthetic.

`prompt_sha256` remains the hash of the exact effective prompt-file bytes, and `description_sha256` the hash of the exact persisted description-byte snapshot used. Neither identifies category guidance or the complete request; do not claim full reproducibility from those hashes. The closed format-1 envelope has no guidance fingerprint. A later need for stronger provenance requires a separately approved, versioned envelope change, not silently changing hash meaning. Category changes do not trigger regeneration. Tests must capture exact prompt, schema, description and guidance parts, including Unicode and delimiter-like data; verify same retry snapshots, custom overrides, hashes and redaction.

## Historical and custom-schema compatibility

1. **Generation:** Continue strict parsing, schema validation and fixed-envelope/provenance validation from Slice 1. Generation under the built-in uses the complete 2.0.0 schema above; B2 must retain an independently identifiable read-only copy of the exact historical 1.0.0 built-in payload schema for XMP validation. This historical reader asset is distinct from the one canonical current-generation schema. No automatic artifact migration or field merge is introduced.
2. **Existing JSON skip:** As before, recover then strictly parse and validate only the fixed envelope; an envelope-valid existing file is skipped without reading/hashing the current description, comparing schema/prompt/model/guidance or calling a provider. Invalid envelopes fail unless explicit regeneration is requested. Regeneration replaces the complete sidecar only after validation and safe-write; failure preserves recoverable prior data.
3. **Built-in XMP reader:** Recognize exact matching built-in 1.0.0 and 2.0.0 `schema_id`/`schema_version` pairs and validate the payload against its corresponding bundled schema. A valid 1.0.0 file has no title/caption/candidate fields, so those operations are no-ops; do not repurpose `keywords`. A valid 2.0.0 file maps the three fields, with empty values as no-ops. Reject unknown or mismatched built-in identities, malformed envelopes and schema-invalid known built-in payloads as actionable sanitized compatibility/validation failures; unknown envelope formats fail closed. Do not infer compatibility from a version number alone.
4. **Custom XMP reader:** A fully replaceable custom payload remains valid without built-in fields. Its historical schema bytes are not embedded, so an envelope and stored schema hash alone cannot prove payload conformance. Publication of custom fields requires an **explicit user-selected mapping** to title, caption and/or candidate properties; no arbitrary field name is silently inferred. Each selected property must be validated against the corresponding publication-interface type/path rules before use. Missing mapped fields or supported empty values are no-ops; malformed present mapped values fail. With no mapping, custom publication fields are unavailable/no-ops, not guessed from names. A4 owns exact config representation and diagnostic/stage-result semantics; it must retain full replacement and not require a user schema for unrelated XMP fields.
5. **Schema evolution:** Major for removed/renamed required fields, semantic/type changes or tightened validation that invalidates old payloads; minor only for backward-compatible optional additions/loosening; patch only for annotations without validation/meaning changes. The new 2.0.0 ID and the 1.0.0 historic ID identify different validation contracts. Future readers must explicitly list supported exact built-in ID/version pairs and historical validators; unknown versions fail safely instead of being guessed. Custom schema identity continues to use the exact schema-byte hash from Slice 1. Any envelope property/type/requiredness or provenance-semantics change requires an envelope `format_version` increment and separate design/review.

## Synthetic contract examples and review rubric

All examples below are invented descriptions, not real photos or observed model output. Omitted older descriptive values in the partial display do not constitute a complete generated payload; schema-validation evidence below uses complete synthetic payloads.

For the first description below, this is one complete schema-valid synthetic **metadata payload** (the application envelope is separate):

```json
{
  "subjects": ["red bell pepper"],
  "objects": ["white plate"],
  "actions": [],
  "setting": {"type": "", "context": ""},
  "visual_characteristics": {"colors": ["red", "white"], "composition": "", "lighting": "", "visual_style": ""},
  "keywords": ["bell pepper", "plate"],
  "title": "Red bell pepper on a plate",
  "caption": "A red bell pepper rests on a white plate.",
  "tag_candidates": [["food", "bell pepper"], ["food", "pepper"], ["color", "red"], ["plate"]]
}
```

| Description and guidance | Expected illustration (title; caption; ranked paths) |
| --- | --- |
| A red bell pepper rests on a white plate. Preferred `food`, `color`. | `Red bell pepper on a plate`; `A red bell pepper rests on a white plate.`; `[["food","bell pepper"],["food","pepper"],["color","red"],["plate"]]`. The general pepper term is justified; a growing plant is not asserted. |
| A bicycle leans against a wooden fence outdoors. Preferred `transport`, `outdoors`. | `Bicycle beside a fence`; `A bicycle leans against a wooden fence outdoors.`; `[["transport","bicycle"],["outdoors","bicycle"],["fence"]]`. The same concept has two meaningful paths; the last is uncategorized. |
| A blue umbrella on a table. No preferred categories. | `Blue umbrella on a table`; `A blue umbrella rests on a table.`; `[["objects","umbrella"],["table"]]`. `objects` is a permitted unlisted category, not a default taxonomy. |
| No usable detail in a valid description. | `""`; `""`; `[]`. No guessed content and no XMP field clearing. |

For the first row with limit 2, select the first two paths; do not add the ancestors as separate assignments. For the bicycle with limit 1, select only the first path. With limit 0, select none and leave existing tags intact. The reviewer should examine a small synthetic or sanitized set spanning specific/general concepts, no preference, meaningful preferred and unlisted categories, multiple paths, uncategorized entries, and unsupported content. Record each actual input/output and human judgment against: (1) factual support/no invented identities, places, dates or events; (2) concise accurate title and useful caption; (3) search usefulness and descending rank without synonym saturation; (4) meaningful categories without forced placement; and (5) unsupported values empty. Human review is qualitative, not a universal numerical model benchmark. The example expectations above are design illustrations, not observed model results.

## Planned implementation checks

B1/B2/B4 must use test-first RED/GREEN coverage for schema and full custom replacement, exact supported/empty values, invalid tags/duplicates, array order, category precedence and isolation, path/count/dedup edge cases, version/identity and historic validator packaging, old-skip/explicit-regeneration, malformed and custom inputs, no-op absent fields, prompt/schema/description/guidance request snapshots on retry, same-snapshot provenance and private-data redaction. A3 verifies hierarchy character representability and field mappings; A4 freezes the custom mapping/config and exact result/error outcomes without silently changing these A2 semantics. No application or live-model execution is claimed here.

## A2 acceptance

- [x] Every new payload field and category/ranking rule is testable with concrete sanitized examples, with unchanged existing metadata meanings and no XMP root in JSON.
- [x] SemVer choice, schema ID, envelope compatibility, historical/custom payload reader policy and explicit regeneration behavior are stated without introducing automatic migration.
- [x] Top-N limit and multi-hierarchy counting have deterministic definitions, including invalid/duplicate entries and absent/empty fields.
- [x] A small human-review rubric and illustrative evaluation set exist; no real-model execution or observed quality result is claimed.
- [x] A2 completion record, decisions/evidence and plan checkoffs are synchronized.

## Design verification and limits

- The embedded schema passed `Draft202012Validator.check_schema` using `jsonschema 4.26.0`. The six inherited property definitions were compared with the existing canonical 1.0.0 schema and matched exactly. Three complete synthetic payloads (normal, empty, Unicode) and the complete example embedded above validated; eight negative cases (old payload without required additions, empty/space-prefixed segment, slash, pipe, C1 control, duplicate path, and missing existing field) were rejected.
- Python extracted the exact prompt text above, encoded it with the specified final LF, and calculated the byte count and SHA-256 documented above. These checks validate the design text, not the currently packaged resource.
- Application patch version advanced to `0.1.14`. `uv lock --locked` passed; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py::test_version_uses_installed_metadata tests/unit/test_resources.py` returned **3 passed**; the CLI reported `0.1.14`; focused Ruff check and format check passed. These are version/resource regression checks, not tests of the proposed Slice 2 design.
- Documentation checks passed: all five A2 acceptance rows match the plan, summary/detail headings match for 16 steps, A3/A5 remain open, local links and whitespace pass, and a targeted scan for private infrastructure/provider strings found no matches in the three changed Slice 2 records.
- No full application suite, external provider calls, ExifTool/digiKam checks, or model-quality observations were performed for this design. Product Owner review of the design and the A5 gate remain distinct from completion of A2. No Git commands were run.
