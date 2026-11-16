# Step B2 — Implement configuration resolution and precedence (PARTIAL)

**Status:** In progress; completion blocked by unresolved schema/dependency decisions.
**Scope deviations:** No pipeline or provider implementation. A candidate change declares `referencing` directly; this was already a transitive dependency of `jsonschema`, but explicit approval of the direct dependency has not been recorded. The current preflight conservatively rejects nested `$id`; A3 does not explicitly authorize that restriction.
**Files created:** `src/image_clarus/config.py`, `tests/unit/test_config.py`, and this record.
**Files updated:** `pyproject.toml`, `uv.lock`, `docs/slice-1/IMPL-A2-COMPLETED.md`, `docs/slice-1/IMPL-A4-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.
**Files removed:** None.

## Progress and evidence

Implemented a configuration resolver and tests for discovery, precedence, YAML handling, stage preflight, credential-safe errors, path origins, reasoning mappings, and selected schemas. The resolver is not wired to the process CLI; B8 owns that wiring. B3 owns provider use of credentials.

The Product Owner selected HTTP for `localhost`, loopback addresses, and literal private-network IP addresses; other hosts require HTTPS. A2/A4 record this clarification. Private-network HTTP remains unencrypted. A dedicated HTTP-policy test was observed failing before the correction and passing afterward.

Review-driven regression work recorded RED/GREEN for CLI-layer precedence, schema handling, deep inputs, stage isolation, and sanitized errors. One subsequent audit identified unresolved same-document references and nested `$id` rebasing; the current candidate rejects all nested `$id` rather than implementing valid same-document rebasing. That restriction has not been approved and is not claimed to satisfy A3.

Most recent independently run checks: `uv run --locked --extra dev pytest -q` — **50 passed**; `uv run --locked --extra dev ruff check .` and `ruff format --check .` passed; `uv lock --check` passed. These results do not prove the unapproved schema restriction is correct.

## Acceptance

- [ ] All precedence and file-selection rules in A2 have passing tests using temporary config roots, not the host's real config files.
- [x] Explicit config never discovers or merges another file.
- [ ] Selected-stage validation is isolated and deterministic.
- [ ] No credentials are emitted in diagnostics.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md) is linked.

## Open decisions and follow-up

1. Decide whether nested `$id` values are supported when references remain within the document, or explicitly disallowed as an A3 contract change. Current code disallows them.
2. Decide whether `referencing`, already installed transitively by `jsonschema`, may be declared as a direct runtime dependency. Current candidate declares it. Neither decision was answered in the clarification request; no approval is inferred.
3. After those decisions, complete implementation and contract/security review, rerun tests and quality checks, update this record and all acceptance rows, and check B2's summary only when satisfied. B3 and later steps remain unstarted.
