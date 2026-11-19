# Step C5 — Reconcile Slice 2 evidence and close acceptance

**Status: Complete.** The Product Owner accepted the prompt-configurability gap for Slice 2 closeout, with the future remedy in the [parent REQ](../REQ-image-clarus.md). The Product Owner affirmed C3's accepted demonstration of functionality and usefulness and distinguished evaluation of a chosen model's accuracy from evaluation of Image Clarus. The evidence limitations below remain visible; no unperformed test or general model-accuracy claim is implied.

## Numbered requirement crosswalk

`Supported` means the cited evidence supports the exercised contract, not universal coverage. `Partial` identifies a limitation in evidence or implementation, accepted for closeout as described below. Links refer to Slice 2 completion records; actual commands and limitations are in those records.

| Requirement | Evidence and disposition |
| --- | --- |
| S2-01 Persisted handoffs and independence | **Supported:** [C1](IMPL-C1-COMPLETED.md) records selected-stage ordering and persisted JSON and description handoffs, including the instrumented disk-boundary check. |
| S2-02 Artifact and source-image boundaries | **Supported for tested cases:** [C1](IMPL-C1-COMPLETED.md) source checks; [C2](IMPL-C2-COMPLETED.md) XMP preservation; [C3](IMPL-C3-COMPLETED.md) operator-reported digiKam retest. Unsupported RDF fails closed. |
| S2-03 Additive JSON information | **Supported:** [B2](IMPL-B2-COMPLETED.md) schema and envelope tests; [C1](IMPL-C1-COMPLETED.md) persisted payload and compatibility. |
| S2-04 Title | **Partial:** independent mapping and supported-title instruction are exercised by [C1](IMPL-C1-COMPLETED.md); [C3](IMPL-C3-COMPLETED.md) reports useful examples but does not establish every S2-18 evidence-boundary outcome. |
| S2-05 Caption | **Partial:** independent caption mapping and preservation are tested in [C1](IMPL-C1-COMPLETED.md) and [C2](IMPL-C2-COMPLETED.md); [C3](IMPL-C3-COMPLETED.md) reports useful examples and the same quality-evidence limitation. |
| S2-06 Human-search-oriented ranking | **Partial:** deterministic persisted rank/top-N are tested in [B4](IMPL-B4-COMPLETED.md) and [C1](IMPL-C1-COMPLETED.md); [C3](IMPL-C3-COMPLETED.md) contains qualitative usefulness observations but not a complete representative ranking review. |
| S2-07 Hierarchical categorization | **Partial:** [B4](IMPL-B4-COMPLETED.md) supports path structures and [C3](IMPL-C3-COMPLETED.md) reports hierarchy/filtering. The manual samples do not establish all representative uncategorized and multiple-hierarchy semantic cases. |
| S2-08 Preferred category guidance | **Partial:** [B1](IMPL-B1-COMPLETED.md) and [B2](IMPL-B2-COMPLETED.md) cover configuration and request delivery; [C3](IMPL-C3-COMPLETED.md) does not enumerate all configured guidance and representative semantic placements. |
| S2-09 Inference/publishing separation | **Supported:** [C1](IMPL-C1-COMPLETED.md) exercises independent XMP without model calls and persisted handoff; [B4](IMPL-B4-COMPLETED.md) tests deterministic selection. |
| S2-10 Schema, prompt and history | **Partial, accepted:** [C1](IMPL-C1-COMPLETED.md) records old/custom JSON compatibility, skip/regeneration and mappings. System prompt and schema overrides exist; hardcoded user-message instructions limit independent configurability. The Product Owner accepted this gap for Slice 2, with future remedy in the parent REQ. |
| S2-11 Deterministic digiKam publication | **Supported for tested cases:** [C1](IMPL-C1-COMPLETED.md) real-ExifTool output and [C3](IMPL-C3-COMPLETED.md) Product Owner-reported digiKam import/edit/reread and defect correction. |
| S2-12 Tag ownership and policies | **Supported for tested cases:** [B4](IMPL-B4-COMPLETED.md) policy matrix and [C2](IMPL-C2-COMPLETED.md) real-ExifTool preservation; [C3](IMPL-C3-COMPLETED.md) reports one manual empty-root combination. |
| S2-13 Ranked top-N | **Supported:** [B4](IMPL-B4-COMPLETED.md) deterministic path selection and [C1](IMPL-C1-COMPLETED.md) persisted ranking, limit and invalid-input checks; model-quality limitations remain separate. |
| S2-14 Independent title/caption policies | **Supported for tested cases:** [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md) and [C3](IMPL-C3-COMPLETED.md) record policy/locale tests and operator-reported digiKam behavior. |
| S2-15 Optional caption author | **Supported for tested cases:** [C2](IMPL-C2-COMPLETED.md) tests author policies and unconfigured preservation; [C3](IMPL-C3-COMPLETED.md) reports configured author display. |
| S2-16 XMP safety and failures | **Supported for tested cases:** [C2](IMPL-C2-COMPLETED.md) records recovery, failure injection and overlapping processes; lock-free lost-update and filesystem limits remain. |
| S2-17 Configuration and stage behavior | **Partial, accepted:** [C1](IMPL-C1-COMPLETED.md) and [C4](IMPL-C4-COMPLETED.md) document selected-stage isolation and installed ExifTool optionality; the prompt gap is carried forward under S2-10. |
| S2-18 Required acceptance evidence | **Accepted:** the outcome crosswalk identifies observed evidence and limitations; the Product Owner affirmed C3 functionality and usefulness without requiring model-accuracy benchmarking. |

## S2-18 acceptance-outcome crosswalk

| Outcome | Disposition and evidence |
| --- | --- |
| JSON output extension, old descriptive fields and provenance | Supported: [B2](IMPL-B2-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md). |
| Evidence-bound title/caption/tag claims | **Evidence limitation, accepted:** [C3](IMPL-C3-COMPLETED.md) records useful examples and some unsupported vision inferences; the handoff does not establish a general output boundary or that every unsupported inference originated in the JSON stage. Users choose their models and prompts. |
| Ranking, preferred/multiple/uncategorized paths, top-N | **Accepted with evidence limits:** deterministic rank and cutoff are supported by [B4](IMPL-B4-COMPLETED.md) and [C1](IMPL-C1-COMPLETED.md); [C3](IMPL-C3-COMPLETED.md) does not enumerate every representative category case. No additional model benchmark is required for closeout. |
| Human-reviewed metadata quality | Product Owner-accepted qualitative functionality and usefulness review with explicit limits: [C3](IMPL-C3-COMPLETED.md). This is not a statistical model-accuracy claim. |
| Standalone stages and persisted handoffs | Supported: [C1](IMPL-C1-COMPLETED.md), including a labeled instrumented disk-boundary test. |
| digiKam hierarchy recognition, generated-tag edit/readback and ancestor filtering | Supported by Product Owner-reported manual evidence, not an independent agent GUI test: [C3](IMPL-C3-COMPLETED.md). C3 remains accepted. |
| Nonempty/empty root policy and idempotence | Supported for exercised combinations: [B4](IMPL-B4-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md). |
| Editable title/caption, independent policies | Supported for tested cases: [C1](IMPL-C1-COMPLETED.md), [C2](IMPL-C2-COMPLETED.md), operator report in [C3](IMPL-C3-COMPLETED.md). |
| Optional author, no-author preservation, all policies | Supported for tested cases: [C2](IMPL-C2-COMPLETED.md), operator report in [C3](IMPL-C3-COMPLETED.md). |
| Existing XMP preservation including flat keywords | Supported for tested structures: [C2](IMPL-C2-COMPLETED.md), corrected compatibility case and manual report in [C3](IMPL-C3-COMPLETED.md); unsupported RDF fails closed. |
| Safe writes, failures, ExifTool optionality, no image edits | Supported for exercised paths: [C2](IMPL-C2-COMPLETED.md), [C4](IMPL-C4-COMPLETED.md); lock-free and filesystem limitations apply. |
| Historical/custom JSON handling, schema/version evolution | Supported: [C1](IMPL-C1-COMPLETED.md), [C4](IMPL-C4-COMPLETED.md); the separate prompt-control gap is accepted for Slice 2 and carried forward. |
| CLI-over-YAML precedence, selected-stage isolation | Supported: [B1](IMPL-B1-COMPLETED.md), [C1](IMPL-C1-COMPLETED.md), [C4](IMPL-C4-COMPLETED.md). |
| Public synthetic/sanitized fixtures | Targeted scan of 89 public Markdown, Python and prompt files, including README, found no matches for a bounded set of private infrastructure, model and identifying-image sentinels. This is not exhaustive proof that all private information is absent. [C1](IMPL-C1-COMPLETED.md) and [C2](IMPL-C2-COMPLETED.md) also describe synthetic fixtures. |

## Documentation and boundaries

The README distinguishes Product Owner-reported digiKam 9.1.0 checks from ExifTool-only tests; the HLD and plan reflect accepted closeout. No new provider, batch, traversal, search, or additional vendor-write functionality was implemented in this C5 documentation audit. The parent-REQ enhancements for hierarchical category guidance, independent prompt control, prompt macros and accumulated state are not assigned to a particular future slice or marked implemented.

C4 records **864 passed** on each of Python 3.12 and 3.13, plus lock, Ruff, build, and installed-wheel checks. Those are historical C4 results; this C5 closeout did not rerun the full suites. C4 also records static deferred import cycles without claiming an acyclic graph. For the closeout version bump to 0.2.3, `uv lock --locked`, the CLI and resource unit suites (**60 passed**), Ruff check and format checks passed; `uv run image-clarus --version` reported 0.2.3. No external provider or additional manual model test was run for C5.

## Acceptance

- [x] All S2 requirements and acceptance outcomes map to executed, reviewable evidence or explicitly remain open with an authorized disposition.
- [x] All required tests, digiKam and quality/manual gates are actually satisfied before marking complete.
- [x] Plan, summary/detail checkboxes, completion records, HLD and public documentation agree.
- [x] Product Owner closeout decision and deviations/carry-forward are recorded; C5 record linked.

**Product Owner disposition:** The prompt-control gap is accepted for Slice 2; its future remedy is specified in the parent REQ without a slice assignment. The process failed to identify and raise the gap early; improving that broader process is outside this implementation. The Product Owner affirmed that functionality and usefulness were demonstrated and C3 accepted, and that evaluating a particular model's accuracy is distinct from evaluating the product, which allows users to select models and prompts. No additional model-quality test was performed or required by this decision; the specific evidence limitations remain recorded above. This is acceptance of Slice 2 with the stated exception, not a claim that the gap is fixed.
