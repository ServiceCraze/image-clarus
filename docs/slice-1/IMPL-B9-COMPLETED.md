# Step B9 — Document Slice 1 installation, configuration, and use (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. Phase C verification remains in the [Slice 1 plan](IMPL-PLAN-slice-1.md#phase-c--verify-and-close-slice-1).

**Files created:** `examples/config.yaml` and this record.

**Files updated:** `README.md`, `docs/slice-1/IMPL-B8-COMPLETED.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.

**Files removed:** None.

## Summary

Documented installation, provider/model configuration and environment-backed credentials; configuration selection, precedence and path origins; single-image desc, json and combined usage; custom prompt/schema overrides; regeneration, result/exit behavior, safety boundaries and deferred functionality. The sample contains placeholder model IDs and an environment-variable name, not a credential. Provider examples are explicitly manual and require authorization for endpoint, model, data transfer and potential cost.

## Verification

- Executed the README's provider-free commands from the project directory: `uv sync --locked`, `uv run --locked image-clarus --version`, and top-level, `process`, and `search` help. Version printed `image-clarus 0.1.0`; all commands exited 0.
- Executed the search stub and verified its exact message and exit 3. Parsed the YAML sample, verified it contains an environment-variable name rather than an inline key, and preflighted both selected stages with a synthetic environment credential. The first sample preflight attempt without that credential failed as expected with `Provider credential unavailable`; it was then rerun successfully with the synthetic credential.
- Verified README local links and whitespace; `ruff check .` and `ruff format --check .` passed. No application test suite was run for this documentation-only step. Existing CLI behavior and synthetic-provider test results are recorded in [B8](IMPL-B8-COMPLETED.md).
- The manual processing examples require a provider and were not run against a live provider. No real credential or personal image was used. `uv sync --locked` removed development-only packages, which were restored by subsequent `uv run --locked --extra dev` verification.

## Acceptance

- [x] Examples match actual help and CLI behavior.
- [x] Configuration precedence, secret handling, and current scope are clear.
- [x] No unimplemented batch/search/XMP behavior is presented as available.
- [x] Documentation links and commands are validated; [IMPL-B9-COMPLETED.md](IMPL-B9-COMPLETED.md) is linked.

B9 does not execute Phase C; C1–C3 remain open.
