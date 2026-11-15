# Step A4 — Freeze the provider request and security contract (COMPLETED)

**Status:** Complete as a design artifact

**Scope deviations:** None

**Files Created/Updated/Removed:**
- Created: `docs/slice-1/IMPL-A4-COMPLETED.md`
- Updated: `docs/slice-1/IMPL-PLAN-slice-1.md`; `docs/slice-1/IMPL-A2-COMPLETED.md` (subsequent-progress note plus credential and YAML-quoted `off` semantics); `docs/slice-1/IMPL-A3-COMPLETED.md` (subsequent-progress cross-references); `docs/HLD-image-clarus.md` (reconcile Phase A decisions and remaining open items)
- Removed: None

---

## Summary

Step A4 freezes the synchronous OpenAI-compatible Chat Completions boundary used by both `desc` and `json`: endpoint construction, request bodies, image encoding, model/reasoning selection, authentication, HTTP timeout/redirect/TLS behavior, response validation, error categories, retry boundaries, redaction, and hermetic provider tests. Slice 1 supports reasoning effort as its only configurable model-generation parameter; HLD §4.2's broader named-model defaults and generic parameter overrides remain an end-state requirement but are explicitly deferred beyond Slice 1. A4 preserves A2's resolved-image and sidecar-output path reporting; provider-path redaction is scoped to provider-facing data, provider errors, and diagnostics. A4 adds only optional reasoning-mapping leaves under A2's existing provider/model maps; it adds no dependency and does not change A2's configuration-source or CLI precedence.

This was a design-only step. No application modules, test files, user-facing configuration example files, or lockfiles were created; the mapping snippet below is illustrative documentation only. No application tests/builds or live provider requests were run. At A4 closeout, A5 and A6 were pending and Phase B/C work had not started. A5 has since completed; A6 remains pending and Phase B/C work has not started.

**Decision/approval boundary:** These choices complete the A4 design artifact; they are not a Product Owner approval. Erik's A3 Product Owner review remains pending, A6 remains unchecked, and Phase B implementation is not authorized until the Phase A readiness gate passes.

**Subsequent progress:** Step A5 later froze safe-write, backup-retention, recovery, and concurrency details in [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md). This does not change A4's provider contract or pass the Phase A readiness gate.

## Provider boundary and request interface

- Use the A1-selected synchronous `httpx` client and the HLD-selected OpenAI-compatible **Chat Completions** protocol. Send `POST` to `<base_url>/chat/completions`, preserving any configured path prefix and trimming trailing slashes before appending the endpoint. For example, `https://api.example/v1` becomes `https://api.example/v1/chat/completions`.
- A2's `base_url` is an API root/prefix, not a full `/chat/completions` URL. Reject non-absolute URLs, unsupported schemes, URL user-info, query strings, fragments, and an already-appended `/chat/completions` path as `configuration`. API keys belong only in the authorization header, never in a URL.
- Each stage constructs an independent generic model request from its selected `stages.<stage>.model`, resolved model/provider aliases, exact prompt text, and stage input. The shared adapter does not receive a stage-specific configuration object and does not infer or run another stage. Shared model/provider selection means the same configured model identity and adapter, not shared conversation state or cached outputs. Distinct model selections route independently. No model fallback or capability probing occurs.
- The provider result exposed internally to a stage contains only the assistant `content` string. The raw HTTP response, headers, request URL, credential, and provider error body are not returned in that result.

### Description request

Use the canonical/custom description prompt as the exact `system` content. The `user` message contains the source image as an inline data URL; do not send a local path, fetch a remote image URL, or add text to the canonical prompt. The request has one choice and is non-streaming. For both stages, generic `reasoning_effort` is the only configurable model-generation parameter in Slice 1. HLD §4.2's broader named-model default/override capability remains an end-state requirement; temperature, token/output limits, and other generation parameters are deferred beyond Slice 1. Do not add config keys, CLI options, defaults, or arbitrary provider-parameter pass-through for them in this slice.

Illustrative Chat Completions JSON body (the base64 value is a placeholder, not a runnable fixture):

```json
{
  "model": "<configured-model-id>",
  "messages": [
    {
      "role": "system",
      "content": "Fully describe and explain everything about this image."
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,<BASE64_IMAGE_BYTES>"
          }
        }
      ]
    }
  ],
  "stream": false,
  "n": 1
}
```

The initial suffix-to-MIME mapping is case-insensitive: `.jpg`/`.jpeg` → `image/jpeg`, `.png` → `image/png`, `.webp` → `image/webp`, and `.tif`/`.tiff` → `image/tiff`. Unknown suffixes fail as `unsupported_image` before a request. Encode the source bytes directly as base64; do not resize, transcode, strip EXIF, or locally decode them. A recognized suffix supplies the declared MIME type but does not prove the file is valid. The provider may reject corrupt bytes, unsupported formats, or payload-size limits. The standard OpenAI vision guide lists PNG, JPEG, WEBP, and non-animated GIF, not TIFF; therefore the design does **not** claim standard OpenAI endpoints accept TIFF. GIF is not added to A4's initial suffix map. A compatible local/remote endpoint may support a broader set.

The configured endpoint receives the original image bytes, including any embedded metadata. Users must only process images they are authorized to send to that endpoint. Image-format configuration/traversal remains outside this single-image provider contract; A4 introduces no new image-format config root or conversion dependency.

### Structured JSON request

Use the exact effective A3 JSON prompt as `system` content. Pass the exact persisted description text and the selected metadata-payload schema as separate `user` text parts; do not interpolate them into or alter the prompt. Serialize the parsed selected schema as JSON, including its `$schema`, `$id`, and annotations. The schema content is sent to the configured provider on every JSON attempt; its local file path is not sent. Operators must not place credentials or other secrets in custom prompts, descriptions, or schema annotations.

Use Chat Completions JSON mode, not `json_schema` response format:

```json
{
  "model": "<configured-model-id>",
  "messages": [
    {
      "role": "system",
      "content": "<exact UTF-8 content of the selected A3 JSON prompt>"
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Persisted description:\n<exact decoded .desc.txt text>"
        },
        {
          "type": "text",
          "text": "Selected JSON Schema:\n<serialized selected metadata-payload schema>"
        }
      ]
    }
  ],
  "response_format": {
    "type": "json_object"
  },
  "stream": false,
  "n": 1
}
```

The body also contains the resolved native reasoning parameter when the effective generic effort is not `default` and its mapping is not the explicit omit form below. A3 remains authoritative for exact prompt/schema/description-byte fingerprints, strict parsing, application-owned provenance, metadata-schema validation, and bounded validation retries. JSON mode requests syntactically valid JSON but does not enforce the selected Draft 2020-12 schema; local A3 validation remains mandatory. If JSON mode is unsupported, fail as `configuration`; do not fall back to plain text or `json_schema` mode.

For each A3 validation retry, resend the same effective prompt, description, schema, JSON mode, model, and reasoning setting, with the prior invalid assistant content and only A3's normalized feedback appended as conversation messages. This is a new provider request and is distinct from HTTP retry behavior.

## Reasoning configuration and precedence

Within Slice 1, `reasoning_effort` is the only configurable model-generation parameter. HLD §4.2's broader named-model default-generation-parameter and generic-override capability remains an end-state requirement, explicitly deferred beyond Slice 1 rather than removed. Temperature, token/output limits, and other generation parameters have no Slice 1 config keys, CLI overrides, defaults, or generic pass-through. The `reasoning_effort_mapping` below is exclusively a reasoning control, not a general provider-parameter escape hatch.

A2's generic effort source precedence remains unchanged: non-null stage setting → model setting → `default`. `default` omits the native effort property and preserves the endpoint/model default. The Slice 1 Chat Completions default map is:

| Generic setting | Native `reasoning_effort` value |
| --- | --- |
| `off` | `none` |
| `minimal` | `minimal` |
| `low` | `low` |
| `medium` | `medium` |
| `high` | `high` |
| `extra_high` | `xhigh` |
| `max` | `max` |
| `ultra` | `max` |

The `max`/`ultra` collapse is explicit. API support is model-dependent: a model that rejects an explicitly mapped value fails with `configuration`; the adapter does not remove the setting, lower it, or switch models silently.

A4 adds these optional leaves, and no other config root:

```yaml
providers:
  local:
    reasoning_effort_mapping:
      parameter: reasoning_effort
      values:
        "off": "none"
        low: low
        high: high
models:
  local-vision:
    provider: local
    model_id: example-model
    reasoning_effort_mapping:
      parameter: thinking_level
      values:
        "off": false
        low: concise
        high: deep
```

`providers.<name>.reasoning_effort_mapping` and `models.<name>.reasoning_effort_mapping` each have exactly `parameter` and `values`. `parameter` is one non-empty top-level JSON property name for the provider/model's documented native reasoning-control input; it may not be `model`, `messages`, `stream`, `n`, or `response_format`. It is not an arbitrary generation-parameter pass-through. `values` is a non-empty map from supported generic string levels (excluding `default`) to non-null native JSON scalar values (string, finite number, or boolean). For `off` only, the exact object `{"omit": true}` means omit the native property; configure this only when the endpoint's documented omission behavior disables reasoning. Null, sequence, and other object values are invalid. Because A2 parses YAML with PyYAML `safe_load`, quote the YAML key/value `"off"`; a bare YAML `off` can become boolean `false` and fails string-enum validation. For `--set`, preserve the quote characters inside the argument, e.g. `--set 'stages.desc.reasoning_effort="off"'`. A missing selected generic level is a `configuration` error before the request. A model-level mapping replaces the provider-level mapping in full; otherwise use the provider-level mapping; if neither exists, use the built-in map. A4 does not alter A2's built-in/YAML/`--set`/dedicated-flag precedence.

## Authentication and HTTP transport

- Resolve `api_key` or `api_key_env` per A2. Send a non-empty resolved credential only in the HTTP `Authorization` header using Bearer authentication. If a configured environment variable is missing/empty, fail as `authentication` before the request. If neither key source is configured, omit `Authorization`; a provider requiring a key returns the normal authentication failure. Do not put keys in query parameters or shared mutable client defaults.
- Send `Content-Type: application/json` and `Accept: application/json`. Require a JSON response media type (`application/json` or `application/*+json`). Do not enable streaming.
- Use `timeout_seconds` as the same HTTPX connect, read, write, and pool timeout. It is not an absolute total wall-clock deadline; HTTPX read timeout is an inactivity bound between received chunks. No second timeout key is introduced.
- Set `follow_redirects=False` and keep TLS certificate verification enabled. Redirect responses fail as `configuration`; do not forward credentials to a redirected host. HTTP URLs remain allowed by A2 for local endpoints; remote HTTP sends credentials/image/description without transport encryption, so HTTPS is required for remote use.
- Keep HTTPX's `trust_env=True` behavior: standard environment proxy and CA configuration is honored. An operator-configured proxy may route the request; an HTTP or TLS-intercepting proxy can inspect request data/credentials, while a tunneling HTTPS proxy normally sees the target but not the encrypted body. This is an explicit deployment/data-routing boundary, not logged by the application.
- Provider-layer automatic retry/backoff count is zero for every status and transport failure, including 429, 5xx, and timeouts. A timeout may occur after the provider has processed/billed the request; retrying automatically could duplicate cost. Only A3's bounded model-output validation retries can issue a second request.

## Response parsing and empty/malformed results

Accept only a complete, non-streaming Chat Completion response with exactly one choice at index `0`, assistant role, string `message.content`, and `finish_reason == "stop"`; a missing/malformed response envelope, non-JSON body, duplicate-key/non-finite JSON, null/non-string content, refusal, tool call, content filter, or any other finish reason fails as `provider_unavailable` without publishing an artifact. Do not expose provider refusal text or error bodies.

Return the accepted assistant content string unchanged; do not trim, extract fences, or normalize it in the adapter. An empty string is passed to the owning stage: `desc` rejects empty or whitespace-only content as `provider_unavailable` and writes nothing; `json` lets A3's strict parser treat it as invalid JSON and apply only its configured schema-validation retry bound. A non-stop finish reason is an adapter failure and is not sent through A3's validation-retry loop.

## Error-category mapping

Use A2's existing category IDs only. Status and a bounded set of structured error fields may classify a failure; never copy a provider's free-form error message into a result/log.

| Condition | A2 category and action |
| --- | --- |
| Invalid base URL, reserved/unknown reasoning mapping, selected effort absent from the effective mapping, or unsupported request option | `configuration`; fail preflight when knowable, otherwise fail the request without fallback |
| Configured `api_key_env` unset/empty, or HTTP 401/403 | `authentication`; no retry |
| Structured error explicitly identifies an unknown model (for example, `error.code == "model_not_found"` or `error.param == "model"`) | `unknown_model`; do not select another model |
| Recognized invalid/corrupt image error | `corrupt_image` |
| Unknown image suffix, explicit unsupported image/MIME, or HTTP 413 image limit | `unsupported_image` |
| HTTP 408 or HTTPX timeout exception | `network_timeout` |
| HTTP 3xx | `configuration`; redirects are disabled |
| Other HTTP 4xx, including unsupported `response_format` or reasoning parameter/value | `configuration`, except the auth/model/image cases above |
| HTTP 429, HTTP 5xx, connection/proxy/TLS failure, malformed 2xx response envelope, refusal, or non-stop completion | `provider_unavailable` |

Only exact recognized structured fields such as `error.code`, `error.type`, and `error.param` may refine the category. Unknown codes fall back to the status/transport table. A malformed provider HTTP envelope is `provider_unavailable`; malformed assistant JSON or selected-schema violations are A3 `schema_validation` failures. No provider error string, response body, header, or exception representation is returned.

## Redaction and data handling

- Never expose the API key, resolved environment value, Authorization header, request/response body, image bytes/base64, description text, prompt text, schema text, provider error body, or full endpoint URL in application diagnostics or provider-derived errors/results. Do not send local image, prompt, or schema filesystem-path values as request data or transport metadata, and do not include those values in provider error text or diagnostic logs; send only the content specified by the request contract.
- Do not log `str(exc)`, `repr(exc)`, `raise_for_status()` text, HTTPX wire traces, or raw remote messages. Emit only fixed sanitized messages with the A2 category and, where useful, numeric HTTP status, stage/model alias, and attempt number. The provider result contains only the accepted content string for its owning stage and never includes the credential or transport details.
- This provider/diagnostic redaction does not suppress A2's intentional application-facing path reporting: preserve the resolved image path in the internal single-image result and each stage's nullable `output_path` in per-stage records and stdout summaries. These values remain excluded from provider requests and provider-error diagnostics.
- The configured provider receives the original image bytes and, for `json`, the persisted description plus selected prompt/schema content. A4 does not strip EXIF or other image metadata. Users choose the endpoint and any environment proxy and are responsible for authorizing this transfer.
- Tests use synthetic image bytes, synthetic descriptions/schemas, and a dummy credential sentinel only. No actual photo, provider secret, or live endpoint is used.

## Automated provider tests owned by B3

Implement with a local HTTP stub or `httpx.MockTransport`; no external network or real key. Write the failing test first, verify RED, then implement and verify GREEN as required by the plan.

1. Assert API-root path joining, configured path-prefix preservation, invalid URL rejection, no query/user-info keys, JSON headers, `stream: false`, `n: 1`, and no redirect following.
2. Capture description and JSON requests; assert exact selected model IDs, canonical prompt bytes/content, base64 round-trip of synthetic image bytes and MIME mapping, separate persisted-description/schema parts, `response_format: {"type":"json_object"}` only for JSON, the mapped reasoning property, and absence of deferred generation parameters or local file paths.
3. Use separate selected models/providers for `desc`/`json`, and one shared model/provider; assert independent request bodies, per-stage reasoning precedence, no conversation/context leakage, and no cross-provider credential-header leakage.
4. Cover successful response extraction, empty content, malformed/duplicate-key/non-finite response envelopes, wrong choice count/index/role, refusal, null content, tool-call/length/content-filter finish reasons, and JSON mode/model capability mismatch.
5. Inject timeout, connection failure, redirect, 401/403, model-not-found, invalid/unsupported image, 413, 429, 5xx, and generic 4xx responses; assert exact A2 categories and exactly one HTTP attempt per provider call.
6. Include dummy-key and sentinel strings in synthetic error body/URL tests; assert they are absent from captured application logs, exceptions, result messages, and returned objects while confirming the Authorization header was present in the captured request. Assert local paths are absent from provider-bound data and provider-derived errors/diagnostics; separate stage/CLI tests retain A2's resolved-image and sidecar-output path reporting.

## Alternatives and rationale

- Kept Chat Completions because that is the HLD's accepted Slice 1 protocol. Official OpenAI documentation recommends Responses for new work, but A4 does not expand or change the approved protocol boundary.
- Chose JSON mode plus A3 local schema validation instead of provider `json_schema` enforcement: compatible local endpoints/model support and strict-schema keyword subsets vary, while A3 accepts replaceable Draft 2020-12 payload schemas. JSON mode is the narrower common request; unsupported endpoints fail clearly, and no plain-text fallback weakens validation.
- Chose inline data URLs over provider-fetchable image URLs so the client sends the selected local bytes directly and never exposes a local path or requires an image-hosting service.
- Kept HTTP retries at zero because a timeout can follow successful remote processing. A3 validation retries are separate, bounded, and only follow a complete normal completion.
- Used a documented built-in reasoning map with model/provider overrides rather than silently guessing capability. Official API values are model-dependent, so a rejected explicit setting is a configuration failure.

## Patch 009 clarifications

1. **Generation parameters:** Slice 1 exposes only the A2/A4 reasoning-effort controls. The broader named-model generation-parameter defaults and generic overrides in HLD §4.2 remain an end-state requirement, with non-reasoning parameters deferred beyond Slice 1; no general provider-parameter framework or pass-through is introduced.
2. **Path redaction:** A4 prohibits local paths in provider requests, provider-derived errors, and diagnostic logs. It does not override A2's internal resolved-image-path field or per-stage `output_path`/CLI summary contract.

These clarifications address the two Patch 009 findings. This records the design resolution, not reviewer or Product Owner approval.

## Acceptance

- [x] Both stages can use independent named models and can share a provider/model without coordinator-specific configuration objects.
- [x] Unsupported provider capabilities fail clearly; there is no silent reasoning/model fallback.
- [x] B3 automated tests are specified to use no external network or real credentials.
- [x] B3 test coverage is specified to prove a dummy credential is absent from captured logs and error messages while present only in the captured Authorization header.
- [x] HLD §4.2's broader generation-parameter capability is preserved as an end-state requirement; Slice 1 supports only reasoning effort and explicitly defers other parameters without generic pass-through.
- [x] Provider/diagnostic path redaction excludes local paths from provider requests, provider errors, and diagnostic logs while preserving A2's internal and CLI result-path reporting.
- [x] [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md) is complete and linked.

## Verification and environment notes

- Read the REQ, HLD, Slice 1 plan, and A1–A3 completion artifacts before freezing A4. No provider implementation, test harness, or app dependency manifest existed to inspect; `httpx` was already selected in A1.
- Consulted official OpenAI Chat Completions, Structured Outputs/JSON mode, Images and Vision, and reasoning documentation plus HTTPX timeout/client documentation. The design records their limits, especially model-dependent reasoning support and the standard OpenAI image-format list; this research does not claim every OpenAI-compatible service has identical capabilities.
- Parsed the embedded reasoning-mapping YAML with PyYAML `safe_load`; verified the quoted `"off"` key and quoted `--set` value remain strings, while an unquoted YAML `off` becomes boolean `false`. This is a configuration-example check, not an application test.
- This is a `[DESIGN]` closeout. No application tests, typechecks, builds, package installation, or provider calls were run. Planned provider tests are owned by B3; stage-level empty-output behavior is owned by B6/B7.
- Patch 009's two clarification findings are reflected in the design and plan; reviewer acceptance is not inferred from making these edits.
- A4's chosen request schema, mapping, error, and data-transfer decisions remain subject to the Phase A acceptance/readiness process; A3 Product Owner review is still pending.

## References

- [Slice 1 implementation plan](IMPL-PLAN-slice-1.md)
- [Step A2 completion record](IMPL-A2-COMPLETED.md)
- [Step A3 completion record](IMPL-A3-COMPLETED.md)
- [OpenAI Chat Completions API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create/)
- [OpenAI Structured Outputs and JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI Images and Vision](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)
- [OpenAI reasoning guide for Chat Completions](https://developers.openai.com/api/docs/guides/reasoning?api-mode=chat)
- [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/)
- [HTTPX developer API](https://www.python-httpx.org/api/#client)
