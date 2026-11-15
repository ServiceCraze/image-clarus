# Step A3 — Freeze the JSON schema, prompt, and provenance contract (COMPLETED)

**Status:** ✅ Complete

**Scope deviations:** None

**Files Created/Updated/Removed:**
- Created: `docs/slice-1/IMPL-A3-COMPLETED.md`
- Updated: `docs/slice-1/IMPL-PLAN-slice-1.md`; `docs/slice-1/IMPL-A2-COMPLETED.md` (historical progress cross-reference only)
- Removed: None

---

## Summary

Completed Step A3 as a design-only step. This record freezes the default structured-metadata payload schema and prompt, a fixed application-owned output envelope and provenance contract, built-in and custom schema identification, validation and serialization behavior, the bounded opt-in validation-retry contract, and synthetic examples and test cases. It also resolves the review findings by fingerprinting the exact persisted description input and defining create-only skip behavior across schema changes. Step B7 owns creating and packaging the actual prompt/schema assets and implementing their tests. No production code, test files, prompt/schema resource files, or user-facing config examples were created. At A3 closeout, Steps A4–A6 and Phases B/C were pending. Steps A4/A5 have since completed; Erik accepted A3 as documented during A6, and the Phase A readiness gate has passed. Phase B/C remain unstarted.

The schema fields, envelope, prompt, schema dialect, retry limit, description fingerprint, and existing-output skip policy below are A3 design choices made to complete the authorized step. Erik explicitly accepted this A3 contract as documented during A6; no revisions were requested.

**Product Owner decision:** Erik explicitly accepted A3 as documented during A6, covering the prompt, metadata fields, envelope/custom-schema boundary, provenance (including the persisted-description fingerprint), schema-versioning rules, create-only skip behavior, and retry contract. The two review findings have explicit contract resolutions below; no revisions were requested. A6 records the passed Phase A readiness gate. Phase B implementation has not started.

## Canonical paths and resource ownership

- Default prompt source: `prompts/image-structure.txt`.
- Default metadata-payload schema source: `schemas/image-structure.schema.json`.
- B7 maps those canonical root assets into `image_clarus/resources/prompts/image-structure.txt` and `image_clarus/resources/schemas/image-structure.schema.json` with Hatchling. Maintain one source copy; do not add duplicate package-resource copies.
- `stages.json.prompt_file` and `stages.json.schema_file` continue to use the A2 overrides and path-resolution rules. A custom prompt fully replaces the built-in prompt text. A custom schema fully replaces the built-in **metadata payload** schema; neither override replaces the application-owned output envelope or required provenance.

## Built-in structured-metadata prompt

The exact UTF-8 prompt content is:

```text
Extract structured photo metadata from the persisted description.

Use only facts explicitly stated or directly supported by the description. Do not invent identities, locations, dates, or visual details. When a value is not supported, use the empty string or empty array allowed by the selected schema. Return exactly one JSON object that conforms to the selected JSON Schema. Do not include schema-version or provenance fields, Markdown fences, comments, or surrounding prose. If validation feedback is supplied, use it to correct the output while following the same evidence limits.
```

The file is UTF-8 without a BOM and ends with one LF. Read the effective prompt bytes once; hash and use that same byte snapshot so provenance identifies the exact instructions sent. The persisted `.desc.txt` is supplied as data separately from this static prompt; it is not interpolated into a template. A4 owns Chat Completions message framing and must pass the persisted description and selected schema without changing this prompt text; that framing is subsequently frozen in [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md). The prompt directs the model to return only the metadata payload. Image Clarus adds the envelope and provenance after model output has passed validation.

Prompt provenance records `prompt_id: "builtin:image-structure"` for this resource and `prompt_id: "custom"` for an override. In both cases `prompt_sha256` is the lowercase SHA-256 of the exact UTF-8 bytes of the effective prompt file, including its final LF, before the description or retry feedback is added. Never record the override's local path.

For a JSON generation attempt, read the persisted `.desc.txt` bytes once. Compute `description_sha256` as the lowercase SHA-256 of those exact bytes before decoding, then strictly decode that same byte snapshot as UTF-8 (without BOM-stripping) and pass the decoded text as description data. Do not trim text or normalize line endings. Invalid UTF-8 is an `invalid_artifact` failure before any provider request. This fingerprint identifies the exact persisted textual input to the JSON stage; it does not identify the source image or the provider/model/prompt that originally produced the description. It is provenance, not an automatic staleness or regeneration trigger.

This field is part of the initial `format_version: 1` contract. The earlier A3 draft was pre-acceptance, not a released wire format; no application implementation or generated `.desc.json` artifacts existed when this design was refined, so this clarification requires no artifact migration. Once accepted, subsequent envelope changes follow the version-increment rule below.

## Built-in metadata-payload schema

The schema file is JSON Schema Draft 2020-12 with this exact initial content:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:image-clarus:metadata-schema:1.0.0",
  "title": "Image Clarus structured metadata payload",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "subjects",
    "objects",
    "actions",
    "setting",
    "visual_characteristics",
    "keywords"
  ],
  "$defs": {
    "non_empty_string": {
      "type": "string",
      "minLength": 1
    },
    "string_array": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/non_empty_string"
      },
      "uniqueItems": true
    }
  },
  "properties": {
    "subjects": {
      "description": "Primary subjects or focal entities supported by the description.",
      "$ref": "#/$defs/string_array"
    },
    "objects": {
      "description": "Other notable objects supported by the description.",
      "$ref": "#/$defs/string_array"
    },
    "actions": {
      "description": "Visible activities or actions supported by the description.",
      "$ref": "#/$defs/string_array"
    },
    "setting": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "type",
        "context"
      ],
      "properties": {
        "type": {
          "type": "string",
          "description": "Setting type or category; empty when unsupported."
        },
        "context": {
          "type": "string",
          "description": "Relevant scene context; empty when unsupported."
        }
      }
    },
    "visual_characteristics": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "colors",
        "composition",
        "lighting",
        "visual_style"
      ],
      "properties": {
        "colors": {
          "description": "Distinct visible colors; empty when unsupported.",
          "$ref": "#/$defs/string_array"
        },
        "composition": {
          "type": "string",
          "description": "Framing or spatial arrangement; empty when unsupported."
        },
        "lighting": {
          "type": "string",
          "description": "Visible lighting quality; empty when unsupported."
        },
        "visual_style": {
          "type": "string",
          "description": "Visible medium or style; empty when unsupported."
        }
      }
    },
    "keywords": {
      "description": "Unique searchable terms/tags; empty when unsupported.",
      "$ref": "#/$defs/string_array"
    }
  }
}
```

All six top-level fields are required. `subjects`, `objects`, `actions`, colors and keywords are arrays of unique, non-empty strings and may be empty. `setting.type`, `setting.context`, and every visual-characteristics string are required strings and may be empty. Empty values mean the persisted description does not support a useful value; the model must not add guessed details. No controlled vocabulary is imposed. `keywords` is the single canonical searchable-term/tag field; do not duplicate it with another `tags` field. Every object in the built-in payload schema rejects additional properties. Later XMP mapping is not decided here.

## Output envelope, provenance, and replacement behavior

Every `.desc.json` is one UTF-8 JSON object with the fixed application-owned envelope below. The model returns only the object validated as `metadata`; the application adds the remaining fields. The envelope is not replaceable by `--json-schema`.

```json
{
  "format_version": 1,
  "metadata": {
    "actions": [
      "resting on a plate"
    ],
    "keywords": [
      "bell peppers",
      "green",
      "red",
      "vegetables"
    ],
    "objects": [
      "white ceramic plate"
    ],
    "setting": {
      "context": "Several peppers arranged on a plate.",
      "type": "Kitchen counter"
    },
    "subjects": [
      "red bell peppers"
    ],
    "visual_characteristics": {
      "colors": [
        "green",
        "red",
        "white"
      ],
      "composition": "Close view from slightly above.",
      "lighting": "Soft natural light.",
      "visual_style": ""
    }
  },
  "provenance": {
    "description_sha256": "4ddc3c884d9a44a0a9649004a55aedad0049ed287cb4db5fde526eeaadbaf836",
    "model_alias": "local-vision",
    "model_id": "synthetic-vision-model",
    "prompt_id": "builtin:image-structure",
    "prompt_sha256": "15b5dd95690fbaf9dae7f485628a80eff2ac7a12945e7c19281456359f30a683",
    "provider_alias": "local"
  },
  "schema_id": "urn:image-clarus:metadata-schema:1.0.0",
  "schema_version": "1.0.0"
}
```

The sample is synthetic and non-identifying. Its `.desc.txt` fixture bytes are the UTF-8 encoding of `Several red bell peppers, one with a green stem, rest on a white plate on a kitchen counter in soft natural light.` followed by exactly one LF and no BOM (115 bytes). The example `description_sha256` is the SHA-256 of those exact bytes. The prompt hash is the SHA-256 of the exact built-in prompt bytes shown above.

The application-owned envelope has these fixed rules:

| Field | Type and rule |
| --- | --- |
| `format_version` | Integer constant `1`; identifies the envelope shape, not the application or metadata schema version. |
| `schema_id` | Non-empty string. Built-in: `urn:image-clarus:metadata-schema:1.0.0`; custom: `urn:image-clarus:custom-metadata-schema`. |
| `schema_version` | Non-empty string. Built-in: `1.0.0`; custom: `custom-sha256:<64 lowercase hexadecimal characters>`. |
| `provenance` | Closed object requiring non-empty `provider_alias`, `model_alias`, `model_id`, and `prompt_id`, plus lowercase 64-hex `prompt_sha256` and `description_sha256` strings. |
| `metadata` | JSON object validated against the complete selected payload schema when generated; existing-output skip validation is envelope-structural only, as defined below. |

The exact fixed envelope schema is embedded in `stages/structure.py`; it is not a second user-selectable asset. It validates `metadata` as an object, while the selected payload schema validates that object separately:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:image-clarus:output-envelope:1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "format_version",
    "schema_id",
    "schema_version",
    "provenance",
    "metadata"
  ],
  "properties": {
    "format_version": {
      "type": "integer",
      "const": 1
    },
    "schema_id": {
      "type": "string",
      "minLength": 1
    },
    "schema_version": {
      "type": "string",
      "minLength": 1
    },
    "provenance": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "provider_alias",
        "model_alias",
        "model_id",
        "prompt_id",
        "prompt_sha256",
        "description_sha256"
      ],
      "properties": {
        "provider_alias": {
          "type": "string",
          "minLength": 1
        },
        "model_alias": {
          "type": "string",
          "minLength": 1
        },
        "model_id": {
          "type": "string",
          "minLength": 1
        },
        "prompt_id": {
          "type": "string",
          "minLength": 1
        },
        "prompt_sha256": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$"
        },
        "description_sha256": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$"
        }
      }
    },
    "metadata": {
      "type": "object"
    }
  }
}
```

Every newly generated artifact passes only when the fixed envelope schema and selected payload schema both validate. An envelope-validation failure is an application/configuration failure, not a model-output validation retry. The built-in metadata schema has SemVer `1.0.0`, independently of application SemVer. Increment its major version when a change removes/renames a required field, changes a field's type/meaning, or tightens validation so previously valid payloads fail; increment minor for backward-compatible optional-field additions or loosened constraints; increment patch only for annotation/documentation changes that do not affect validation or field meaning. Newer built-in versions must continue to accept payloads valid under prior compatible versions; incompatible changes require a major increment.

`format_version: 1` identifies this exact closed envelope contract and is separate from `schema_version`. Any change to the envelope's properties, types, requiredness, or provenance semantics requires an integer `format_version` increment and a matching envelope-schema `$id` suffix; do not silently accept an unknown envelope format. Changes to the metadata payload schema use its independent SemVer and do not change `format_version`.

## Existing JSON and create-only skip behavior

A2's existing-output policy is create-only: when `.desc.json` exists and JSON regeneration is not requested, first perform the A2 recovery check, then strictly parse the existing file and validate only the fixed `format_version: 1` envelope contract before prerequisite checks. A structurally valid existing artifact is exactly one strict JSON object with no duplicate keys or non-finite numbers that passes the closed envelope schema, including required provenance and object-valued `metadata`. The envelope requires non-empty `schema_id` and `schema_version` strings but does not require them to match a schema currently installed or selected.

If that structural check passes, return `skipped` with `output_exists`, leave the existing bytes unchanged, and make no provider request. Do not read or hash the current `.desc.txt`, compare `description_sha256`, compare prompt/model provenance, or validate `metadata` against the currently selected payload schema. In particular, a valid existing artifact remains skipped when its recorded built-in/custom `schema_id` or `schema_version` differs from the selected schema. The create-only default does not perform schema migration or stale-input detection; use explicit regeneration to apply a changed description, prompt, model, or schema. Because historical custom-schema contents are not stored in the envelope, this skip check proves JSON/envelope structure, not conformance to an unavailable historical payload schema.

Malformed JSON, duplicate keys, non-finite values, an unsupported envelope format, or any other envelope-structure failure is `invalid_artifact`; without explicit regeneration, fail without replacing the existing file or making a provider request. With explicit regeneration, generate from the current persisted description and selected schema, include the current `description_sha256`, and replace the destination only after the complete output validates through A5 safe-write. Any generation/validation failure preserves the existing artifact.

A custom schema fully replaces the metadata payload schema: it is not merged with the built-in field set and need not retain those field names. It must be valid JSON Schema Draft 2020-12 and declare root `"type": "object"`; when `$schema` is absent, Draft 2020-12 is assumed, and a declared different dialect is rejected. Only same-document fragment `$ref` references are allowed; filesystem and remote references are rejected before any provider request. Draft 2020-12 `format` keywords are annotation-only in Slice 1. The custom schema controls its own payload properties and `additionalProperties` behavior. The fixed envelope and provenance remain required, so a custom schema cannot remove them.

Custom schema identity uses `schema_id: "urn:image-clarus:custom-metadata-schema"` and `schema_version: "custom-sha256:<hex>"`, where `<hex>` is the lowercase SHA-256 of the exact custom schema file bytes. Read the effective bytes once and compute the hash and parsed schema from that same snapshot. Formatting or line-ending changes therefore produce a distinct custom version. A custom schema's `$id`, if any, is not copied into the output; artifact identity uses only the application-owned ID and exact-content hash. Whether a schema identifier is transmitted to a provider is part of A4's explicit request/data-transfer contract. This scheme does not add a configuration key and remains independent of the application release.

Provenance values come from the resolved A2 configuration: `provider_alias`, `model_alias`, and the selected provider's `model_id`. `prompt_id` and `prompt_sha256` follow the prompt rules above; `description_sha256` fingerprints the exact persisted `.desc.txt` byte snapshot consumed for that generation. Do not store the description text itself in provenance. Do not include `base_url`, local prompt/schema paths, inline or resolved credentials, authorization headers, raw request/response headers, or other secret-bearing URL components in the output, logs, errors, or retry feedback. Do not add a timestamp; it is not needed to identify the producer and would make otherwise identical outputs nondeterministic.

## Parsing, validation, retries, and serialization

- Validate the selected schema during selected-stage preflight, before any model request. Reject malformed JSON, duplicate schema keys, an invalid Draft 2020-12 schema, non-object custom root schemas, `$dynamicRef`, and non-fragment `$ref` references as configuration errors (A2 exit `2`). No provider request occurs on this failure.
- Accept exactly one strict JSON object from the model. Reject leading/trailing prose, Markdown fences, comments, malformed JSON, duplicate object keys at any depth, unpaired surrogate code points, `NaN`, `Infinity`, and `-Infinity`; do not strip, extract, repair, or silently coerce output. The selected schema then validates the model's payload. A non-object payload fails the schema's root-object constraint.
- Construct the fixed envelope only after the payload validates. Validate the envelope separately, then persist only the complete validated result through the A5 safe-write service. A parse/schema failure never creates or replaces `.desc.json`; an existing artifact remains intact.
- Serialize as UTF-8 without a BOM using `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)` followed by exactly one LF. Reject unpaired surrogate code points rather than replacing them. This preserves Unicode and gives stable key ordering without claiming a cross-version canonical JSON encoding.
- `stages.json.validation_retries` remains default `0`; its accepted values are exact non-boolean integers `0`, `1`, or `2`. The value counts additional model attempts after the first, so at most three responses are processed. Values outside the range or booleans are selected-stage configuration errors before provider access.
- Retry only malformed model JSON, invalid Unicode in model JSON, or model payload schema-validation failures; do not retry authentication, provider, network, schema-file, or input failures under this setting. Reuse the same selected model, prompt, schema, and persisted description. Keep the prior invalid model response in the provider conversation context and append only the normalized feedback object below. A4 freezes the transport/message roles and preserves this feedback content.
- For parse failures, feedback is one JSON object: `{"kind":"json_parse","code":"invalid_json"}`, `{"kind":"json_parse","code":"duplicate_key"}`, `{"kind":"json_parse","code":"non_finite_number"}`, or `{"kind":"json_parse","code":"invalid_unicode"}`. Do not include raw response text or parser exception messages.
- For schema failures, feedback is one JSON object with `kind: "schema_validation"`, `total_errors`, `truncated`, and `errors`. Each error has only `instance_path`, `schema_path`, and `keyword`; paths are RFC 6901 JSON Pointers relative to the model's metadata payload (the empty string denotes the root; escape `~` as `~0` and `/` as `~1`). Sort by `(instance_path, schema_path, keyword)`, deduplicate identical entries, include at most the first 20, and set `truncated` according to whether more exist. Do not include instance values or unstable validator message text. For example, an `actions` type error normalizes to `{"kind":"schema_validation","total_errors":1,"truncated":false,"errors":[{"instance_path":"/actions","schema_path":"/properties/actions/type","keyword":"type"}]}`. If retries are exhausted, report the A2 `schema_validation` failure and write no output.

## Synthetic validation examples and test assertions

Synthetic source description:

> Several red bell peppers, one with a green stem, rest on a white plate on a kitchen counter in soft natural light.

Positive metadata payload: the `metadata` object in the example envelope above. It exercises each built-in category while using only facts in the synthetic description. The empty `visual_style` value is valid because the description supplies no style claim.

Negative cases:

| Case | Expected result |
| --- | --- |
| Missing `keywords` or another required built-in property | Payload validation failure at the missing property path. |
| `actions` is a string instead of an array, or an array item is empty | Payload validation failure. |
| An extra top-level or nested built-in property | Payload validation failure because built-in objects are closed. |
| Duplicate keyword/subject entries | Payload validation failure due to `uniqueItems`. |
| Custom payload schema requires only `caption` and rejects other payload keys | Accepted as full payload replacement when `metadata` matches it; envelope and provenance remain present. |
| Invalid schema JSON, duplicate schema keys, wrong dialect, non-object root, `$dynamicRef`, or non-fragment `$ref` | Preflight configuration failure; no model call and no output write. |
| Missing/invalid envelope provenance (including either fingerprint), wrong `format_version`, or extra envelope keys | Fixed-envelope validation fails; no JSON artifact is published and no model-output retry is attempted. |
| Fenced JSON, prose-wrapped JSON, duplicate JSON keys, malformed JSON, unpaired surrogate, or non-finite number | Strict parse failure; no silent cleanup; eligible for configured validation retry only. |
| Unicode metadata values | Preserved as UTF-8 without a BOM; parsed output round-trips exactly. |
| Custom schema bytes change, even only by formatting | Custom `schema_version` hash changes; the application version is not used. |
| The persisted `.desc.txt` bytes change | A generation fingerprints the exact byte snapshot it consumes; the same description hash is provenance only and does not trigger automatic regeneration. |
| Existing `.desc.json` has a valid fixed envelope but its schema ID/version or recorded description hash differs from current selections/files | Skip as `output_exists`, preserve bytes, and do not call the provider, read/hash `.desc.txt`, or validate metadata against the newly selected payload schema. |
| Existing `.desc.json` has a valid fixed envelope but `.desc.txt` is missing | Skip as `output_exists` before prerequisite validation; do not call the provider or require/read the description. |
| Existing `.desc.json` has malformed/duplicate-key JSON, non-finite values, unsupported envelope version, or invalid envelope structure | Fail as `invalid_artifact`, preserve the file, and make no provider request unless explicit regeneration is requested. |
| Credential, endpoint URL, prompt path, schema path, raw invalid response, or parser/validator message | Absent from persisted provenance and diagnostics. |
| Retry count `0`, `1`, `2`, `true`, `-1`, or `3` | Calls are bounded to 1/2/3 attempts for `0`/`1`/`2`; booleans and out-of-range values fail selected-stage preflight. |
| More than 20 schema violations | Retry report is deterministically sorted, contains 20 entries, the full `total_errors`, and `truncated: true`. |
| Validation retry exhaustion with no existing JSON and with an existing JSON | `schema_validation` failure; no incomplete artifact is published and any existing artifact is preserved. |

B7's tests also verify the final envelope separately from the selected payload schema, the exact built-in prompt bytes/hash, the exact persisted-description byte hash and same-snapshot decode, built-in and custom schema-version values, source-tree and wheel resource lookup, and that `json` consumes persisted `.desc.txt` without invoking `desc`. Existing-output tests verify schema-version mismatch skips without reading the description or calling the provider, while malformed envelope artifacts fail without being overwritten. These are test assertions for later implementation, not tests claimed as run in A3.

## Decisions and rationale

- Kept required provenance and schema identity in an application-owned envelope rather than inside the replaceable metadata payload. This is the explicit interpretation of full replacement: a user schema wholly replaces the payload shape while the fixed wrapper guarantees provenance for every generated file.
- Chose a single metadata payload schema file plus a fixed, separately validated envelope contract. This avoids forcing every custom schema to restate or preserve application-owned provenance fields.
- Chose SHA-256 of exact custom schema bytes as the custom schema version rather than adding a user-supplied version field or configuration key. This identifies precisely what validated the payload and cannot be mistaken for application SemVer.
- Chose strict JSON rejection rather than stripping fences or extracting JSON from prose; silent repair could change model output and hide malformed responses.
- Chose two opt-in validation retries (three maximum responses) to bound cost/latency while keeping the accepted default at zero. A4 subsequently froze provider-layer automatic retries at zero; see [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md).
- Added `description_sha256` for the exact persisted description bytes used by a JSON generation, without claiming the vision-stage producer identity or using the hash as a cache key.
- Kept A2's create-only default: a strictly parsed existing artifact with a valid fixed envelope skips even when its schema or source-description fingerprint differs from current selections. This avoids implicit migration; explicit regeneration applies new inputs/schema. The envelope check does not claim to revalidate an unavailable historical custom schema.
- Chose a small descriptive schema with empty values for unsupported information and no controlled vocabularies; avoid speculative taxonomies and XMP mappings in Slice 1.

## Acceptance

- [x] Schema, prompt, and provenance are defined before any JSON production-code step begins.
- [x] Every required semantic category from the REQ is represented and testable.
- [x] Full custom-schema replacement and provenance interaction have an explicit, non-contradictory rule.
- [x] The generated metadata schema has an independent, identified version and explicit compatibility/evolution rules, including custom-schema behavior.
- [x] Provenance fingerprints the exact persisted `.desc.txt` bytes used for generation and states the limits of that identity.
- [x] Existing JSON structural validity and create-only skip behavior across schema-version changes are explicit and testable.
- [x] No secrets or identifying photo/device data can enter the public example contract.
- [x] [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md) is complete and linked.

## Verification and environment notes

- This was a `[DESIGN]` step. No application code, tests, package metadata, prompt/schema resource files, or user-facing configuration examples were created. No application tests, builds, or provider requests were run.
- The built-in schema and synthetic example are design artifacts in this record; B7 creates the canonical resource files and tests them against the installed package and wheel.
- Synthetic contract checks with Python's standard library and `jsonschema 4.26.0` passed: both schemas passed `Draft202012Validator.check_schema`; built-in and custom-payload envelopes validated; three negative payload cases and four negative envelope cases (missing/malformed description fingerprint, boolean format version, and extra envelope key) were rejected; and Unicode serialization round-tripped as UTF-8 without a BOM and with one final LF. These checks validate the documented contract, not application code.
- The prompt SHA-256 in the example was calculated from the exact UTF-8 prompt bytes above, including the final LF, and matched the hash embedded in the example. The description SHA-256 was calculated from the exact 115-byte UTF-8 fixture (one final LF, no BOM) and matched the embedded `description_sha256`.
- Documentation checks passed: 20/20 plan summary/detail step headings matched; all eight A3 acceptance rows were checked in both plan and completion record; local links in A2/A3 resolved; all other missing plan links were intentionally future step-completion artifacts; no trailing whitespace was found in the changed documents.
- Step A4 subsequently froze provider request/response semantics and capability/error mapping; see [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md). Step A5 has since frozen safe-write/recovery and concurrency details; see [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md). Erik accepted A3 during A6, which passed the Phase A readiness gate. Phase B/C work remains unstarted.
