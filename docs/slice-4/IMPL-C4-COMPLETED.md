# Step C4 - Reconcile evidence and close Slice 4 [DOCS]

**Status:** Complete and ready for review. The Product Owner authorized and the implementation corrected the two observed discrepancies. No prior completed step was unchecked. Review acceptance, commit and release remain separate from work completion.

**Scope deviations:** Approved: the Product Owner authorized the two narrowly scoped production corrections discovered during C4, without changing the accepted prerequisite-admission outcome.

**File inventory:** Created `docs/slice-4/IMPL-C4-COMPLETED.md`. Updated `README.md`, `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, `docs/slice-4/IMPL-PLAN-slice-4.md`, `pyproject.toml`, `uv.lock`, `src/image_clarus/stage_registry.py`, `src/image_clarus/batch_plan.py`, `src/image_clarus/batch_reporting.py`, `tests/unit/test_stage_registry.py`, `tests/unit/test_batch_plan.py`, `tests/unit/test_b6_cli_reporting.py`, `tests/integration/test_c1_verbose_execution.py`, `tests/integration/test_prerequisite_admission.py`, and `tests/integration/test_slice4_c2_policies.py`. Removed: none.

## Crosswalk and evidence boundary

C1, C2 and C3 refer below to their linked completion records at application versions 0.3.55, 0.3.56 and 0.3.57, respectively. M1, M2 and M3 refer to their records at 0.3.50, 0.3.51 and 0.3.52. Commands, test counts, fixture boundaries and limitations are preserved in the linked records; a step's existence alone is not proof of an outcome. The following maps observed evidence and flags findings; it is not a blanket assertion that every requirement is satisfied.

| Requirement | Evidence and qualification |
| --- | --- |
| S4-01 discovery | [C1](IMPL-C1-COMPLETED.md), `tests/integration/test_slice4_c1_selection.py`, `tests/unit/test_discovery.py`: actual CLI selection, depths, patterns and extension eligibility; eligibility does not prove decoding of every format. |
| S4-02 symlinks | [C1](IMPL-C1-COMPLETED.md), [M2](IMPL-M2-COMPLETED.md): explicit and discovered links and rebuild selection; hard-link spellings are distinct identities. |
| S4-03 independent depth | [C1](IMPL-C1-COMPLETED.md), [M2](IMPL-M2-COMPLETED.md): process and rebuild depth; macro path depth is independently configured. |
| S4-04 stage capabilities | [B3](IMPL-B3-COMPLETED.md), `tests/unit/test_stage_registry.py`, `tests/unit/test_batch_plan.py`: descriptors and generic LLM/non-LLM routing. The later stage-name admission discrepancy has been corrected through descriptor-owned prediction; see findings below. |
| S4-05 metadata-only planning | [B3](IMPL-B3-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md): access guards and initial-plan parity; the latter captures execution rows using test-only instrumentation. |
| S4-06 bypass and routing | [B5](IMPL-B5-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md): confirmation, real held-provider overlap and progressive routing in controlled cases. |
| S4-07 authoritative execution | [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md): recovery and mutation cases; C2's nine post-plan mutations cover sequential description execution, not every interleaving. |
| S4-08 work admission | [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md), `tests/integration/test_prerequisite_admission.py`: admission/correction and later JSON-prerequisite correction. The controlled 10,000-image fixture establishes XMP evaluations, not 10,000 XMP writes. |
| S4-09 concurrency | [B5](IMPL-B5-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md): barrier-controlled overlap, worker ownership and sequential behavior on exercised Linux paths. |
| S4-10 state timing | [C1](IMPL-C1-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): selection and accumulation; concurrent cross-image memory visibility is timing-dependent and not independently established as deterministic. |
| S4-11 failure and resume | [C2](IMPL-C2-COMPLETED.md): actual CLI policy cases, Linux signals, protected writes and fresh-invocation resume; no physical-fault or remote-cancellation claim. |
| S4-12 dry-run | [C1](IMPL-C1-COMPLETED.md): access guards, exact initial plan parity and startup boundaries; estimate is not measured peak memory. |
| S4-13 verbose | [C1](IMPL-C1-COMPLETED.md), `tests/integration/test_c1_verbose_execution.py`: starts, dispositions, timing, progress and counts. Corrected verbose output now includes the failure category; see findings below. |
| S4-14 metrics | [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md): observed planned/actual counts and partial outcomes in exercised cases. |
| S4-15 list | [M1](IMPL-M1-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): logical data/schema read-only behavior and strict errors; ordinary SQLite/OS filesystem effects are permitted. |
| S4-16 clear | [M1](IMPL-M1-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): transactional category-only clear, fault and separate-process evidence; injected faults are not physical failures. |
| S4-17 rebuild | [M2](IMPL-M2-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): actual-CLI 997-valid/3-invalid case, additive updates and separate-process transaction ordering; a scan is not one atomic transaction. |
| S4-18 compatibility | [C3](IMPL-C3-COMPLETED.md): full suites on Python 3.13.15 and 3.12.14 and installed-wheel smoke at 0.3.57, with the record's explicit boundaries. |

### Acceptance evidence E01–E20

| ID | Recorded evidence and boundary |
| --- | --- |
| E01 | [C1](IMPL-C1-COMPLETED.md) selection CLI and discovery tests: traversal, depth, extension candidates, patterns and symlinks; extension eligibility is not decoder proof. |
| E02 | [C1](IMPL-C1-COMPLETED.md), [C3](IMPL-C3-COMPLETED.md): single-image compatibility and installed-wheel smoke; that smoke did not exercise XMP. |
| E03 | [B3](IMPL-B3-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md): planning access guards and CLI parity using test-only plan instrumentation; generic prerequisite correction below. |
| E04 | [B5](IMPL-B5-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md): confirmation and held-provider overlap in controlled cases. |
| E05 | [C1](IMPL-C1-COMPLETED.md): budget and controlled 10,000-image progressive-success fixture; XMP evaluation is not a write. |
| E06 | [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md): corrections and exclusions; C2 mutation scope is sequential description-stage execution. |
| E07 | [B5](IMPL-B5-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md): barrier-controlled actor overlap and sequential mode. |
| E08 | [C1](IMPL-C1-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): category accumulation and sequential visibility; concurrent visibility is timing-dependent. |
| E09 | [C1](IMPL-C1-COMPLETED.md): per-image state selection and fallback; deterministic concurrent cross-image memory visibility is not established. |
| E10 | [C2](IMPL-C2-COMPLETED.md): recovery and post-plan mutations with stated stage/mode scope. |
| E11 | [C1](IMPL-C1-COMPLETED.md): dry-run guards and ordered plan parity; memory estimate is not a peak bound. |
| E12 | [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md): observed status, timing, metrics and partial failures; 0.4.4 correction supplies failed-stage categories. |
| E13 | [C2](IMPL-C2-COMPLETED.md): real Linux signals, held inference, protected publication and fresh resume; no interruption inside a filesystem or SQLite syscall is claimed. |
| E14 | [M1](IMPL-M1-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): logical read-only state, strict errors and management concurrency; M3 includes independent processes. |
| E15 | [M2](IMPL-M2-COMPLETED.md), [M3](IMPL-M3-COMPLETED.md): actual-CLI 997/3 case, clear/rebuild and independent transactions; injected faults are not physical failures. |
| E16 | [C3](IMPL-C3-COMPLETED.md): 2,001 passed on each of Python 3.12 and 3.13, build and wheel smoke at 0.3.57, with stated limitations. |
| E17 | [C1](IMPL-C1-COMPLETED.md): selection identities and hard-link discovery; no physical-file deduplication is claimed. |
| E18 | [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md), `test_prerequisite_admission.py`: admission and recovery, including controlled post-plan arrival; not every concurrent interleaving. |
| E19 | [C1](IMPL-C1-COMPLETED.md): startup and empty/dry-run guards; the old-state fixture is not proven migratable. |
| E20 | [C2](IMPL-C2-COMPLETED.md): actual two-image policy CLI tests and injected coordinator worker exceptions; not an OS child failure. |

## Findings and authorized corrections

1. The 0.4.2 planner used stage-name conditionals for prerequisite-aware admission. The Product Owner authorized moving prediction to stage metadata while preserving the accepted outcome. `stage_registry.py` now owns the JSON prerequisite prediction and `batch_plan.py` calls a generic optional capability; fictional-stage tests exercise independent dependencies and upstream ordering. The original 0.4.2 prerequisite behavior and its **2,037-test** Linux suite remain historical evidence; `tests/integration/test_prerequisite_admission.py` was rerun with the correction.
2. Failed stages previously rendered `reason=-` despite having an error category. `batch_reporting.py` now renders the sanitized category for failures without changing event/reconciliation facts; missing or unsafe categories render `unknown`. `tests/unit/test_b6_cli_reporting.py`, `tests/integration/test_c1_verbose_execution.py`, `test_prerequisite_admission.py`, and `test_slice4_c2_policies.py` cover the corrected output and redaction. The two new direct reporting tests were observed failing before the correction; historical C1 evidence retains its original version and output.

C4 was designated a documentation step; the Product Owner explicitly authorized the two production corrections. The earlier completed steps remain checked. Production QA acceptance remains distinct from this formal requirements reconciliation.

## Verification and version

- C4 version 0.4.3: `uv lock`, `uv sync --locked --extra dev`, `uv lock --check`, and `uv run --no-sync --locked image-clarus --version` passed; CLI reported `image-clarus 0.4.3`.
- `uv run --no-sync --locked --extra dev pytest tests/unit/test_cli.py -q -k 'version'`: **2 passed, 56 deselected**. `ruff check .`, `ruff format --check .` and `git diff HEAD --check` passed after the version update.
- The later 0.4.2 full Linux suite passed **2,037 tests**; C3's separate Python 3.12/3.13 full suites and wheel/build evidence remain at **0.3.57**. No full suite or wheel build is claimed at 0.4.3.
- At 0.4.4, `uv run --no-sync --locked --extra dev pytest tests/unit/test_stage_registry.py tests/unit/test_batch_plan.py tests/unit/test_batch_execution.py tests/unit/test_batch_concurrency.py tests/unit/test_b6_cli_reporting.py tests/integration/test_c1_verbose_execution.py tests/integration/test_prerequisite_admission.py tests/integration/test_slice4_c2_policies.py -q`: **507 passed**. `uv lock --check`, CLI version, Ruff, format and both working-tree and staged whitespace checks passed.
- At 0.4.4 on Linux with ExifTool on PATH, `uv run --no-sync --locked --extra dev pytest -q -p no:cacheprovider`: **2,045 passed in 986.15s**. This is separate from C3's wheel and dual-interpreter evidence; a new 0.4.4 wheel or Windows run is not claimed.

## Limits and decisions

No Windows runtime, live provider, physical disk fault, power-loss test, or new consumer-GUI interoperability test is claimed. C3's installed-wheel smoke did not run XMP; its macro-free prompt-edit probe included one timeout. State and sidecar writes are not a joint transaction, and concurrent sidecar publication remains lock-free. Test and implementation may evolve together; no historical RED-first gate or extra requirements-acceptance gate is imposed. Native search, content-aware planning Option B, additional stage workers and built-in scheduling remain outside this slice; later allocation is not a release commitment.

## Acceptance

- [x] S4-01–18 and all required acceptance outcomes have supporting evidence or an explicit approved disposition.
- [x] Phase/overall status and deviations reflect observed results; no significant design decision or acceptance gap is silently carried forward.
- [x] Current documentation and remaining parent allocation are accurate; prior-slice records retain their historical meaning.
- [x] Final C4 version/lock/CLI and affected version-assertion checks have actual post-change outcomes; C3's earlier packaging and regression results retain their tested version without attribution to C4's later delivery.
- [x] Orchestration can close Slice 4 based on the recorded outcome without an extra REQ acceptance or test-order gate.
