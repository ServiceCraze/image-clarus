# B5 - Concurrency ownership and lifetime invariants

**Status:** Normative for the B5 actor refactor. Derived from A2 §4 and A3.

These are the rules the implementation must satisfy. Each one names the single
owner and the exact transition; anything not covered here is a bug, not a case
to be discovered later.

## 1. Owners

| Thing | Sole owner | Everyone else |
| --- | --- | --- |
| Plan, per-image token, queue contents, stop/abort cause | Coordinator | reads through the condition |
| Which image an actor is running | That actor | coordinator via `_active` |
| Stage decision, continuation, validation, publication call | The stage actor | — |
| Provider child process | The stage actor that spawned it | coordinator may terminate on stop |
| Publication admission | `PublicationGate` | — |

There is one actor per selected stage and no confirmation worker. A provider
child is transport only: it never inspects, validates, retries or publishes.

## 2. Image token

An image is in exactly one of: `queued(stage)`, `active(stage)`, `terminal`.

- `queued -> active`: the actor dequeues under the condition.
- `active -> queued(next)`: the actor forwards after its stage is terminal.
- `active -> terminal`: its own real result arrives, or the interruption path
  settles it (§4).
- `queued -> terminal`: only the coordinator settles it (§4).

Exactly one terminal record per image, ever. Duplicate finalization is a no-op.

## 3. The actor turn (A2 §4)

The actor owns its queue and must never block inside one image's provider I/O.
Per turn, in order:

1. **Check stop/abort first.** If interrupting, service nothing new.
2. **Service a ready provider result** if one has arrived.
3. **Take at most one FIFO confirmation**; then recheck (1) and (2) before
   taking another.
4. **Start a transformation** only if no request is outstanding for this stage.

With an inference outstanding, the actor continues to admit and service
confirmations for *other* images; it admits no second inference and runs no
second transformation or publication. Bound the confirmation run at eight per
turn before returning to a queued transformation, then reset the counter.

At most one active job per stage, at all times.

## 4. Interruption and abandonment

When a signal or abort is observed, the coordinator closes dispatch and settles
**queued** images as `not_attempted` (`batch_aborted`) or `interrupted`
(no termination event). It never settles an **active** image: that operation
still owns its token and is inside a stage decision, provider request or
admitted publication.

An actor that abandons an image marks it itself, immediately, from its own
finalization path. An operation abandoned without being marked is a defect.

The interruption cause is captured once and applied to queued and active work
alike, so a signal is never reported as `batch_aborted` nor the reverse.

## 5. Publication

Admission is linearized against stop: once stop holds, `begin()` refuses and
the stage reports `interrupted` rather than publishing.

- An **admitted** write keeps its ownership until it returns. Its result is
  the stage's result.
- Shutdown drains admitted work for a bounded time, then reports failure. A
  batch whose publication could not be proven finished is never reported as a
  clean success.
- A refused publication changes nothing on disk.

## 6. Provider child

Admitted before it can be observed as active; stop is rechecked immediately
after spawn. Every exit path — success, refusal, timeout, malformed frame,
actor exception — terminates and reaps it. Both pipe directions are bounded by
the request deadline. A late completion for an already terminal image/stage is
discarded and cannot publish.

## 7. Test obligations

Each invariant above needs a test that fails when the invariant is violated:

- held inference with a confirmable candidate behind it (early forwarding)
- one active job per stage while that holds
- partially writable pipe (no mocked selector)
- stalled publication detected at the drain deadline
- a refused publication changes nothing on disk
- interruption between each pair of transitions: before dequeue, after dequeue,
  during stage work, at publication admission, after publication
- no duplicate terminal records under abort plus signal
