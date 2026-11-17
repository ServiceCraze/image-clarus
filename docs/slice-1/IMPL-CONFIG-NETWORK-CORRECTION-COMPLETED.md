# Slice 1 — Configuration diagnostics and endpoint correction

**Status:** Complete. C4 and C5 were subsequently completed; see their linked completion records.

**Product Owner decision:** The earlier B2 restriction on HTTP destinations is superseded. Syntactically valid HTTP and HTTPS base URLs support DNS names, localhost, IPv4, and IPv6, without application-level destination restrictions or preflight hostname resolution. DNS and connection failures occur during requests. HTTP does not encrypt credentials or request data; HTTPS is preferred. Configuration diagnostics identify a safe configuration key and actionable reason without echoing sensitive values. This is a correction to an earlier accepted policy, not a claim that the earlier policy was never accepted.

**Scope deviations:** The Product Owner explicitly approved this correction before C4. No live provider call was made.

**Files created:** `src/image_clarus/endpoint.py`, `tests/unit/test_endpoint_networking.py`, `tests/unit/test_config_diagnostics.py`, `tests/integration/test_config_diagnostics_cli.py`, and this record.

**Files updated:** `src/image_clarus/config.py`, `src/image_clarus/providers/openai_compatible.py`, `tests/unit/test_config.py`, `tests/unit/test_openai_compatible.py`, `README.md`, `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, `docs/slice-1/IMPL-A2-COMPLETED.md`, `docs/slice-1/IMPL-A4-COMPLETED.md`, `docs/slice-1/IMPL-B2-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.

**Files removed:** None.

## Implementation and evidence

- One shared validator is used by configuration preflight and the provider adapter. It validates syntax without DNS and avoids duplicate completion paths after URL normalization. The adapter leaves TLS verification on and distinguishes request-time network failures from malformed configuration. Existing URL user-info, query and fragment restrictions remain.
- Diagnostics identify schema-owned key paths, reasons and corrective actions while avoiding raw configuration, credentials, hostnames, private paths, aliases and unknown user-supplied keys. YAML errors, invalid references, selected-file errors and override failures are covered. Existing configuration/authentication exit categories are retained.
- Behavioral RED → GREEN was observed for a hostname reaching the provider transport and for safe unknown-key diagnostics and hostname preflight; additional diagnostic regressions and normalized-path/authority defects were observed failing before their respective fixes. Additional endpoint matrix, redaction and CLI subprocess tests were supplemental GREEN coverage, not historical RED evidence.
- A real HTTP request reached a disposable loopback server using a synthetic hostname with a controlled resolver seam; a separate synthetic DNS failure occurred at request time and was classified as provider unavailable. Tests using `httpx.MockTransport` are transport doubles, not live-network evidence.
- Linux, CPython 3.12.14: full suite **487 passed**. Linux, CPython 3.13.15: full suite **487 passed**. Ruff lint and format checks, `uv lock --check`, and `uv build` passed. The final wheel was installed normally into an isolated Python 3.13 environment; its bare entry point reported `0.1.0`, and an invalid synthetic configuration produced an actionable key-specific error with exit 2 outside the checkout.
- Public repository files were searched for the user-specified private host, provider and model terms; no matches were found. Examples and tests use fictitious names. This targeted search is not proof that no other private information exists.

## Limitations

- YAML merge-key duplicate handling was not changed; an explicit override of an anchored mapping can still be rejected as a duplicate. That behavior predates this correction and was not assessed as a supported YAML compatibility contract.
- When several provider or model aliases have the same schema-owned path, sanitized override context for shape errors cannot always distinguish the aliases. Values and aliases are deliberately not disclosed.
- At this correction's closeout, actual-provider compatibility, model quality and real-user installation had not been established. The operator subsequently completed the separately authorized provider smoke test; see [C4](IMPL-C4-COMPLETED.md). This correction does not establish external DNS behavior beyond its controlled tests.
