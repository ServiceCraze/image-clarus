# Step C3 — digiKam interoperability and metadata-quality review (COMPLETED)

**Status: Complete and accepted by the Product Owner.** The Product Owner confirmed the digiKam **Reread Metadata** action and the subsequent screenshot showing the hierarchical leaf remains unassigned while other generated tags remain intact. Earlier ExifTool output confirms preservation of the manual top-level `food` tag. C3 is closed; Slice 2 remains open.

**Subsequent progress:** C4 is complete; see [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md). C5 remains open.

**Evidence provenance:** The Product Owner selected and processed the real photographs, performed the interactive digiKam checks, and authorized the associated model invocations and costs. Another assistant reviewed command output and screenshots during that session. The observations below are reported in the Product Owner's handoff; this documentation review did not independently perform those manual tests, inspect the original screenshots, or invoke a provider. Real photos and original sidecars are not included here.

**Environment:** Fedora Linux 44; digiKam **9.1.0**; Image Clarus **0.2.1**; ExifTool (manual-test version not supplied). Description generation used a locally run small vision model; JSON generation used an operator-selected external service with reasoning disabled. The Product Owner chose the endpoint, inputs, transfer and expenditure. Private host, provider, model and photo identifiers are intentionally omitted.

## Manual interoperability results reported by the Product Owner

| Scenario | Procedure and observed outcome | Evidence boundary |
| --- | --- | --- |
| Initial publication and import | Processed a food photograph and imported its sidecar into digiKam. Generated title, caption, hierarchical descendants under `ai`, and leaf assignments appeared in the Captions and Tags panels without redundant explicit parent assignments; fields were visible and editable. | Reported manual observation; no separate screenshot is stored in this repository. |
| XMP incompatibility and correction | Edited the caption in digiKam and added a manual top-level tag outside `ai`. The first subsequent Image Clarus overwrite failed with `invalid_artifact`: the digiKam-produced structured EXIF property used attributes unsupported by the backend. Patch 001 corrected support for the observed structured XMP form and MicrosoftPhoto namespace preservation; the Product Owner reinstalled version 0.2.1 and repeated the overwrite successfully. The JSON caption replaced the edited caption, the manual external tag and generated tags remained, and other supported metadata was reported preserved. digiKam reread the updated sidecar and displayed title, caption and hierarchy. | The original failure is retained as a genuine defect; the successful retest is operator-reported. No universal RDF support is implied. |
| Ancestor filtering | Selecting a generated ancestor in the left Tags sidebar returned the photograph through its assigned descendant, without explicit assignment of the ancestor. | The Product Owner reports a digiKam 9.1.0 screenshot; the screenshot is not included. |
| Generated-tag edits | Removed a generated flat assignment in digiKam; ExifTool readback showed its absence while unrelated tags remained. A later author-publication invocation used default additive tag policy and restored the removed generated tag from JSON, as expected; it did not isolate author behavior from tag publication. In a separate hierarchical leaf edit, ExifTool confirmed the leaf was absent and other hierarchy assignments and the manual top-level `food` tag remained. The Product Owner used **Reread Metadata**; a subsequent screenshot confirmed the leaf remained unassigned and other generated tags intact. | The Product Owner confirmed the action and screenshot outcome; this documentation review did not independently inspect the screenshot or run digiKam. |
| Optional author | Published a fictional test author through the XMP stage. ExifTool reported the configured author and digiKam displayed it in the caption-author field. | Operator-reported. The same invocation also used the default additive tag policy. |
| Explicit empty root | On temporary copies of image, JSON and XMP, set `tag_root=""`, tag policy `overwrite`, and limit 1 while disabling title, caption and author publication. ExifTool showed the existing generated and manual tags preserved and a rootless hierarchical tag added; the original files were not modified by this test. | This supports the observed additive empty-root case, not all policy combinations. |
| Additional photographs | On a previously untagged group photograph, all three stages completed; digiKam imported title, caption and ten tags from twelve JSON candidates. On a previously untagged shopping photograph, the default pipeline ran all three stages; digiKam displayed metadata and ten tags from eleven candidates. | These are two operator-selected examples, not a representative benchmark. No separate substring-search test was performed. |

The Product Owner identified the metadata-read action as **Reread Metadata** and confirmed the screenshot outcome after the hierarchical leaf edit. This is a reported manual action, not an assumed automatic refresh or a screenshot independently inspected here.

## Metadata-quality review against A2

The following summarizes the Product Owner's qualitative judgments using generalized descriptions rather than personal image data. It is not a statistical evaluation.

| A2 criterion | Reported observations and limits |
| --- | --- |
| Factual support and no invented identities, places, dates or events | The group-photo title and caption were judged accurate, while some vision-model inferences were not established by visual evidence. In the shopping example, a store comparison was illustrative, not an identification of the actual location; a partially obscured product label was transcribed imperfectly. These observations do **not** establish the Slice 2 requirement that representative recommendations contain no unsupported contextual claims. |
| Accurate title and useful caption | The Product Owner judged the group-photo title and caption accurate and found the descriptions useful, with the above qualifications. |
| Search usefulness and ranking | Most group-photo tags were judged useful. The shopping example covered all three operator-identified retrieval concepts, including the object category and a shopping-container term. Ten leading candidates were published in each example; no independent retrieval metric or substring-search result was measured. |
| Meaningful categories and placement | The reviewed examples included relevant food, people and group categories and hierarchical descendants. The handoff does not enumerate a complete preferred-category configuration, all candidate rankings, or a controlled multiple-hierarchy and uncategorized evaluation. |
| Unsupported values empty | Not demonstrated by the reported examples; no absence-of-information case was supplied. |

The Product Owner prioritizes useful search coverage and recall for human-assisted retrieval, while recognizing that users can visually dismiss or edit unwanted tags and choose models, prompts and inference budgets. This is a product-quality interpretation, not authorization to waive the governing evidence-boundary requirement. Imperfect model output is distinct from XMP interoperability, but the unproven S2-18 evidence-boundary and remaining representative-category coverage must remain visible for Slice 2 reconciliation.

## Automated regression and limitations

The structured-XMP correction was separately exercised through synthetic unit and CLI tests using local ExifTool; the previously observed focused run returned **59 passed**, with Ruff, formatting and locked-dependency checks passing. Those checks are not digiKam GUI evidence. A prior Python 3.13 full-suite run returned 862 passed before a subsequent prompt-resource change; a later Python 3.12 full-suite run returned **859 passed, 3 failed** on frozen prompt text/hash expectations. At C3 closeout these quality gates remained for C4; see subsequent progress above.

The operator observed some external-filesystem permission-preservation warnings even though the affected operations completed. Treat these as observed filesystem-capability limitations, not proof of failure or universal permission behavior. The reported external JSON-generation cost was approximately $0.000221 per image, excluding local inference and other costs; it is an observation for that configuration, not a general price guarantee.

**Separate requirements concern:** The JSON-stage system prompt can be replaced, but some accompanying user-message instructions, including preferred-category framing, remain hardcoded. The Product Owner considers this incomplete independent prompt configurability. This remains an open Slice 2 requirements concern, separate from the digiKam findings; this C3 documentation task does not resolve it. Hierarchical preferred categories, accumulated category state and prompt macros are future ideas outside this task, not accepted enhancements or implicit commitments.

## Acceptance

- [x] A real digiKam read/edit/refresh path is observed and recorded; a generated tag is edited and saved, its XMP is read back and refreshed, and hierarchy, title, caption, optional author and preservation meet S2-18.
- [x] Human-reviewed metadata examples and outcomes are recorded with limitations; no unsupported claims pass as evidence.
- [x] External provider/data/cost permission is documented if used; manual evidence is not represented as automated testing.
- [x] Blockers remain unchecked rather than silently converted to success; completion record links to evidence.

**Subsequent C5 disposition:** The Product Owner accepted the independent-prompt gap for Slice 2 closeout with a future remedy in the parent REQ, and affirmed the C3 functionality and usefulness acceptance without requiring an assessment of a particular model's accuracy. See [C5](IMPL-C5-COMPLETED.md) for the decision and evidence limits. The above observations remain the historical C3 record.
