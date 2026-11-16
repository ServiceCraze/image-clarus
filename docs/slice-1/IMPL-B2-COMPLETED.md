# Step B2 — Implement configuration resolution and precedence (COMPLETED)

**Status:** Complete.
**Scope deviations:** Product Owner approved a direct `referencing` dependency and the Slice 1 nested-`$id` restriction described below; no pipeline or provider implementation.
**Files created:** `src/image_clarus/config.py`, `tests/unit/test_config.py`, and this record.
**Files updated:** `pyproject.toml`, `uv.lock`, `docs/slice-1/IMPL-A2-COMPLETED.md`, `docs/slice-1/IMPL-A3-COMPLETED.md`, `docs/slice-1/IMPL-A4-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.
**Files removed:** None.

## Progress and evidence

Implemented a configuration resolver and tests for discovery, precedence, YAML handling, stage preflight, credential-safe errors, path origins, reasoning mappings, and selected schemas. The resolver is not wired to the process CLI; B8 owns that wiring. B3 owns provider use of credentials.

**Historical decision, superseded:** At B2 closeout the Product Owner selected HTTP for `localhost`, loopback addresses, and literal private-network IP addresses, requiring HTTPS for other hosts. A dedicated test of that earlier policy was observed failing before the correction and passing afterward; it does not verify the replacement policy.

**Subsequent Product Owner decision:** The earlier destination restriction is superseded. Standard HTTP and HTTPS endpoints may use DNS/FQDN names or any IPv4/IPv6 destination, with one shared validation policy and no application-level hostname resolution or destination restrictions. DNS and connection failures occur at request time. HTTP does not encrypt credentials or request data. Configuration errors identify the affected key and actionable reason without sensitive values. See [A2](IMPL-A2-COMPLETED.md), [A4](IMPL-A4-COMPLETED.md), and the [correction record](IMPL-CONFIG-NETWORK-CORRECTION-COMPLETED.md) for implementation and test evidence.

Review-driven regression work recorded RED/GREEN for override precedence, schema handling, deep inputs, stage isolation, and sanitized errors. The Product Owner approved declaring `referencing` directly: it was already a transitive dependency of `jsonschema`. The Product Owner also approved rejecting nested `$id` in Slice 1, while supporting local anchors and same-document `$defs` references; this is a supported-subset restriction, not a judgment on JSON Schema validity. Compound-schema support is deferred beyond Slice 1. A3 records the decision.

Patch 016 parser regression: `uv run --locked --extra dev pytest tests/unit/test_config.py::test_custom_schema_rejects_nonfinite_numbers_and_lone_surrogates -q` initially failed because the schema parser accepted `1e9999`; after the fix it passes for positive/negative overflow and lone surrogates in keys/values. A separate positive test accepts finite numbers and a valid Unicode surrogate pair.

Final independently run checks: `uv run --locked --extra dev pytest -q` — **52 passed**; `uv run --locked --extra dev ruff check .` and `ruff format --check .` passed; `uv lock --check` and `uv build --python 3.13` passed. The two targeted strict-schema tests passed. Python 3.12 validation remains C3 work.

## Acceptance

- [x] All precedence and file-selection rules in A2 have passing tests using temporary config roots, not the host's real config files.
- [x] Explicit config never discovers or merges another file.
- [x] Selected-stage validation is isolated and deterministic.
- [x] No credentials are emitted in diagnostics.
- [x] RED/GREEN and regression evidence is recorded; [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md) is linked.

## Follow-up

At B2 closeout, B3 and later steps were unstarted. During B3, an audit identified an HTTPX-invalid URL that B2 preflight accepted; B3 corrected that shared preflight path and added a regression test. See [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md). During B6, a regression test and fix aligned whitespace-only environment credential preflight with the provider's authentication check; see [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md). B8 owns process CLI integration; C3 owns the Python 3.12 compatibility check.
