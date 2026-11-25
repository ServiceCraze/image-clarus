# Step B5 - Implement concurrent stage coordination and shutdown [CODE]

**Status:** Open. Patch 039 corrections are implemented and current focused/full-suite
regression evidence is recorded below. B5 has not been accepted: final acceptance
reconciliation remains open.

**Version:** 0.3.40

**Scope deviations:** None.

## Files created/updated

- Created: `src/image_clarus/provider_frame.py`, `src/image_clarus/provider_worker.py`, `tests/unit/test_batch_concurrency.py`.
- Updated: `src/image_clarus/batch_execution.py`, `src/image_clarus/stage_protocol.py`, `pyproject.toml`, `uv.lock`, `docs/slice-4/IMPL-PLAN-slice-4.md`, this record.
- Removed: None.

## 1. What is implemented and verified

**Topology (A2 §4).** One long-lived actor per selected stage; an image is in at
most one queue or held by at most one actor, so same-image work is ordered and
two stages overlap only across different images. Confirmation obligations are
kept separately from terminal outcomes and dispatched to the owning stage actor.
Sequential mode is unchanged and remains the disabled control.

**Provider child (A2 §6).** `provider_frame.py` is a length-prefixed, tagged
binary codec: description requests carry real image bytes, which no text
serialiser can transport unchanged. The child performs transport only; the
provider mapping travels on private stdin and never in argv, logs or files.

| Property | Evidence |
| --- | --- |
| Each stage's work runs only on its own actor; two stages are simultaneously active | `test_stage_actors_own_their_stages_and_overlap_in_activity` |
| Predicted bypasses are obligations, not results; the prerequisite is checked first | `test_bypassed_stage_is_still_confirmed_authoritatively`, `test_bypassed_prerequisite_is_checked_before_downstream` (blank sidecar, `on_stage_failure=stop`) |
| Binary requests cross the child boundary intact | `test_vision_request_crosses_the_child_boundary` |
| Malformed child replies are sanitized, never fatal | `test_malformed_child_reply_is_sanitized_not_fatal` |
| Child conversations are deadline-bounded in both directions | `test_held_child_is_timed_out_and_reaped`, `test_child_that_never_reads_its_request_is_a_timeout`, `test_real_full_pipe_bounds_a_large_request` (a genuine capacity-filled OS pipe, no mocked selector) |
| Abort, interruption and refused publication stay distinct | `test_aborted_queued_work_is_not_attempted_not_interrupted`, `test_stop_before_execution_marks_selected_stages_not_attempted`, `test_refused_publication_is_reported_not_hidden` |
| Events are ordered under concurrency | `test_events_are_unique_and_ordered_under_concurrency` |
| Active work is never settled by dispatch closure | `_close_dispatch` settles queued work only; an actor marks its own operation when its real result arrives or when it abandons it |
| Publication drains for a real bounded time | `run()` drains `PublicationGate` with a deadline fixed at run start; a refused or undrained publication makes the batch unsuccessful |

### Verification performed

- `uv run --no-sync --locked pytest tests/unit/test_batch_concurrency.py tests/unit/test_batch_execution.py -q` — **70 passed** (0:01:26).
- `uv run --no-sync --locked pytest -q -p no:cacheprovider` — **1,712 passed, 67 skipped** (0:05:36).
- `uv run --no-sync --locked ruff check src/image_clarus/batch_execution.py tests/unit/test_batch_concurrency.py tests/unit/test_resources.py` — All checks passed.
- `uv run --no-sync --locked ruff format --check src/image_clarus/batch_execution.py tests/unit/test_batch_concurrency.py tests/unit/test_resources.py` — 3 files already formatted.
- `uv sync --locked --extra dev && uv run --no-sync --locked image-clarus --version` — `image-clarus 0.3.40`.

### Correction provenance

Each correction was re-checked by reverting it and confirming its test fails:

| Correction | Revert result |
| --- | --- |
| Upstream confirmation precedes downstream execution | fails (`['json', 'desc']`) |
| Write side is deadline-bounded | fails (`blocking stream write must not be used`) |
| Malformed UTF-8 is a `FrameError` | fails (`UnicodeDecodeError`) |
| Child writes nothing to stderr | fails |
| A dequeued-but-unstarted image is not stranded | fails (hang) |
| Large writes bounded by the deadline | hangs past the timeout |
| A confirmation cannot reach provider transport | fails (`2 inferences were outstanding for one stage`) |
| Pending accounting is per stage | fails (`two stages never held requests at once`) |
| Unpollable pipes never block the actor | fails (`KeyError: 'v'` — the caller never returned) |

The Patch 036 review identified a test-fixture exception rather than normal
coordinator shutdown as the reason a two-stage overlap probe closed dispatch.
The test had treated the `Path` passed to inspection as an object with
`image_id`, and also imported `StageResult` from the wrong module. Both faults
became an internal stage failure. The repaired test now reaches each expected
transport and asserts valid terminal outcomes.

Direct regressions now cover the reviewed correction seams:

| Correction | Direct regression |
| --- | --- |
| Confirmation defers unexpected work before provider execution | `test_confirmation_defers_work_until_held_request_finishes` holds one request, observes candidate inspection exactly once, proves no factory fallback or candidate transport while held, then verifies saved-continuation transport and completed results after release. |
| Deferred work is not repeatedly consumed as confirmation | The same test asserts one candidate inspection during the held request. |
| Pending accounting is per stage | `test_two_stages_hold_requests_for_different_images_at_once` observes simultaneous `desc` and `json` transports, asserts all expected requests, and verifies completed results. |
| A partial POSIX pipe write cannot block | `test_write_all_makes_a_partially_writable_pipe_nonblocking` verifies the pipe is nonblocking before each large `os.write`; `test_real_full_pipe_bounds_a_large_request` exercises a capacity-filled OS pipe. |
| A later-stage actor retains settlement ownership | `test_dequeued_later_stage_is_settled_after_prior_stage_completed` proves the prior `desc` actor cannot settle the image after `json` has dequeued it; only the explicit JSON owner can settle it. |
| A completed request can immediately retry | `test_completed_transport_releases_stage_slot_before_waking_retry` holds `done.set()` and proves the retry is admitted only after the completed request released its stage slot. |
| Batch abort reaps a late provider spawn | `test_child_reaps_late_spawn_after_batch_cancellation` aborts while `Popen` is blocked before registration, then verifies the late child is killed and reaped. |
| Batch abort refuses new publication | `test_abort_refuses_publication_after_another_stage_inference` holds a description request, causes JSON abort, proves the batch does not return while the transport remains live, then releases it and verifies no artifact write is admitted. |
| Timed-out publication still drains before return | `test_timed_out_publication_is_reported_but_drained_before_return` holds an admitted write past the reporting deadline, proves the batch is still live, then releases and verifies the write completed before return. |

## 2. Why B5 is not accepted

The current Patch 039 corrections have focused and full-suite evidence, but this
record remains open pending final acceptance reconciliation against the complete
B5 plan. The Windows helper-thread path was exercised only by a forced
non-portable-pipe unit test on POSIX, not on Windows itself. No live provider or
user-facing batch CLI integration was run; neither is claimed as evidence here.

The full suite and the direct regressions establish the corrected in-process
contracts listed above. They do not establish Windows runtime behavior or close
unreviewed B5 acceptance rows.

## 3. Limits of this evidence

- No Windows runtime was exercised. Pipe readiness uses `select` on POSIX;
  Windows uses a helper thread bounded by the deadline, implemented but only
  reasoned about, not run.
- No live provider service was called; all provider-boundary evidence uses the
  framed child with synthetic payloads.
- B5 has no CLI integration, so no user-facing batch path, real OS signal, or
  fresh-invocation resume was exercised. C2 owns that evidence.
- Report here is consistent with tests and injected stage faults only.
