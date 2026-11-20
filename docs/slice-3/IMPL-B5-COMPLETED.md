# Step B5 - Integrate fully user-owned prompts [CODE] (COMPLETED)

**Status:** Complete for prompt expansion in both model stages and request assembly. Category accumulation remains B6; cross-step CLI macro coverage remains C1.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `tests/unit/test_cli_state_interrupt.py` and this record.
- Updated: `src/image_clarus/stages/description.py`, `src/image_clarus/stages/structure.py`, `src/image_clarus/providers/openai_compatible.py`, `src/image_clarus/cli.py`, `prompts/image-structure.txt`, `tests/unit/test_openai_compatible.py`, `tests/unit/test_structure_stage.py`, `tests/unit/test_slice2_structure.py`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, `pyproject.toml`, `uv.lock`, the Slice 3 implementation plan, and prior progress notes.
- Removed: the provider's separate preferred-category argument and the superseded fixed description/schema/category request framing; no files removed.

## Behavior and acceptance evidence

1. The description and JSON stages read their selected prompt bytes after the existing stage skip decisions, expand their snapshots using the same safe macro engine, and pass the resulting user-authored system text to the adapter. Four captured-request scenarios exercise config and state references separately in each stage. A replacement without category guidance does not receive automatic category or known-state context. These captures use synthetic HTTP transport; they are not live-model tests.
2. The built-in JSON prompt retains optional, advisory, non-closed-taxonomy category guidance and expands preferred paths from configuration. Captured requests demonstrate complete single- and multi-segment paths by default, truncation at positive depth, and `[]` at depth zero. The stale separately-supplied wording was removed. The built-in description prompt was not modified. Behavior tests use independent prompt fixtures rather than requiring fixed production prose.
3. JSON request user content is a single data object carrying the exact persisted description and selected schema. Tests retain custom schema, reasoning, bounded retry feedback and independent stage selection. Existing skip, regeneration and sidecar behavior remains covered. The optional `prompt_sha256` uses original prompt bytes, including when expansion changes the transmitted text.
4. The stage-local expansion imports keep XMP and schema worker imports independent of macro execution. A production-source audit found no remaining callers of the removed provider category parameter or old fixed request labels; category validation remains used in configuration and as stage-boundary validation. No B6 state accumulation was added.
5. A final audit reproduced a `StateStopped` escaping the CLI during a state macro read. The stage wrapper now maps it to an interrupted stage when the stop token is set, preserves propagation otherwise, and retains service cleanup. Four regression cases inject stop requests for both model stages and both supported signal values; these are injected boundary tests, not real OS-signal delivery at that boundary.

## Verification and limitations

- Before the provider change, `uv run --no-sync pytest tests/unit/test_openai_compatible.py::test_json_parts_reasoning_and_retry_context -q` failed on the old request framing; the provider suite then passed **55 tests**. Four stage/namespace cases initially failed: two showed missing description expansion and two reached the superseded provider argument. After wiring and a correction to the test's description-newline assumption, the focused scenarios passed. The differing failure causes are not represented as four clean behavioral RED cases.
- Before the interruption fix, `pytest tests/unit/test_cli_state_interrupt.py -q` failed all **4 cases** with `StateStopped` escaping; after the fix and a test output-path assertion correction, all **4 passed**. A wider CLI/pipeline/expansion focused run passed **136 tests**. The correction was not itself observed failing before the production fix.
- A disposable copy with both prompt resources replaced by fictional macro-free text initially exposed **4 prompt-dependent test failures**. Those tests now provide their own macro-bearing prompts; a rerun of six affected unit files in that copy passed **190 tests**. This is a scoped prompt-change probe, not the complete suite with every possible prompt.
- With temporary ExifTool 13.55 on `PATH`, `uv run --locked --extra dev --python 3.13 pytest -q` passed **1,105 tests**, no skips. Ruff check passed and format check reported **136 files** formatted. `uv lock --locked` resolved **21 packages** and the CLI reported **0.2.12**.
- No real provider or private credentials were used. Full CLI subprocess captures of the four stage/namespace combinations remain assigned to C1; the B5 request evidence above is at the stage/adapter boundary. Existing real-CLI tests cover the description-to-JSON data handoff and other sidecar behavior.

## B5 acceptance

- [x] Captured provider requests separately prove description/config, description/state, JSON/config, and JSON/state expansion through authored prompt fixtures; replacements can omit category guidance without automatic reinsertion.
- [x] At the default unlimited depth, the built-in JSON request includes complete configured preferred paths, including single-segment values. With a configured positive depth it uses truncated paths, and with depth zero it emits `[]`, as specified by the per-macro setting.
- [x] Product/resource inspection confirms the required description default, and confirms the built-in JSON prompt no longer says categories are `supplied separately` while preserving advisory, non-closed-taxonomy guidance; wording-dependent unit tests use fixtures instead of freezing production text.
- [x] Opt-in hash testing proves the stored hash remains the raw source-byte hash after expansion.
- [x] Required stage data, custom schema support, reasoning, bounded validation retries, independent stage selection, and prior sidecar behavior remain intact.
