# Plan 20 - The pending-operations outbox: DP writes survive a crash and an outage, retry with backoff, dead-letter, reconcile by idempotency key (research-03 R4)

Created: 2026-10-09 13:00 UTC

## Problem Description

With the Data Platform backend, `_ingest` makes one attempt: a 503 or a network failure yields a `failed` binding and the version is
never available (plan-19 N3). research-03 §4 decides the shape: a durable local log of operations KA owes DP, a worker that retries with
backoff and dead-letters after `KA_DP_RETRIES`, reconciliation by the idempotency key `ka:<tenant>:<source>:<version>` (so a crash between
upload and commit replays safely — the fake and the contract return the same asset ids), and no cross-service transaction.

Desired outcome (PT6): DP unavailable between upload and commit → the version stays `pending` (not available), the outbox retries, the
commit lands once, and afterwards there is exactly one source, one version, one binding and one DP asset version.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §11 binding `available` gates the version; a failed physical write never yields an available version | `knowledge-acquisition.md` §11 (plan-18) | ✅ built | **extends it** — a RETRYABLE failure now yields `pending` with a queued operation; a non-retryable one stays `failed` |
| research-03 §4: second durable log, same pattern as the event outbox; no cross-service ACID | `research-03.md` §4 | ⏳ decided | **builds it** |
| Idempotency key `ka:<tenant>:<source>:<version>`; replay returns the same ids (plan-19 fake, contract row 3) | `docs/contracts/data-platform-v1-ka-subset.md` | ✅ built | **relied on** — reconciliation is a replay |
| Background work on a daemon thread kept on the owning service (plan-17) | `ka/research.py` | ✅ built | **the precedent** — the outbox worker follows it |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** none blocking.

## Research coverage (R1..R14)

Source: [research-03](../research/research-03.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 | ✅ decided | — |
| R2, R3, R11 | ✅ shipped | plans 18, 19 |
| R4 outbox | ✅ in scope | Phases 1–3 |
| R5, R9 | ⏭️ deferred | plan-21 (inbound events will enqueue acknowledgements on this outbox) |
| R6, R7 | ⏭️ deferred | plan-22 (derived publication rides on this outbox) |
| R8, R10 | ⏭️ parked | Q15, Q16 |
| R12, R13, R14 | ⏭️ deferred | plan-23 |

**Covered here: 1 of 14.** Deferred: 8; parked: 2.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT6 DP unavailable midway → retry reconciles; commit lands once; no duplicates | R4 | **GREEN** |

## Scope

In: `ka/outbox.py` (new: `PendingOp`, `Outbox`, `OutboxWorker`, handlers), `ka/model.py` (`PendingOp`), `ka/repository.py` (`dp_outbox`
collection), `ka/ingestion.py` (retryable failure → `pending` binding + spooled bytes + queued op), `ka/physical.py` (`DataPlatformError`
retryable detection stays in the DP package), `ka/events.py` (`physical.binding.available`, `physical.outbox.dead`), `ka/service.py` (worker
when the backend is DP; `outbox_status`), `ka/api.py` (`GET /physical/outbox`, `POST /physical/outbox/run`, `POST /physical/outbox/{id}/retry`),
`ka/console/app.js` (Dashboard: outbox counts + Run now; version pill shows `pending`), `ka/config.py` (`KA_DP_OUTBOX_INTERVAL`,
`KA_DP_BACKOFF_BASE`), tests, live flow, docs.

Out: inbound events (plan-21); derived publication (plan-22); a distributed queue.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- `PendingOp(id, kind, idempotency_key, payload: dict, state pending|done|dead, attempts, next_at, last_error, last_code, created_at,
  updated_at, by)`; stored as one JSON per op under `<storage>/dp_outbox/` (the repository's `Collection`, like every other object — the
  research said "same pattern, separate file"; one file per op keeps updates atomic and is recorded as the implementation choice).
- Kinds this plan handles: `upload_source` (payload: `source_version_id`, `binding_id`, `spool_path`, `content_type`, `filename_hint`).
  plan-21/22 add `ack_event` and `put_derived` handlers to the same registry.
- Spool: a retryable failure keeps the bytes at `<storage>/spool/<version-id>.bin` until the op is `done`, then deletes them. The spool is a
  transient staging area, not a second authoritative store.
- Backoff: `next_at = now + KA_DP_BACKOFF_BASE * 2**attempts` (base 5 s); after `KA_DP_RETRIES` attempts → `dead` with `last_code`; the
  binding stays `pending` with the reason; `POST /physical/outbox/{id}/retry` resets to `pending` with `attempts=0`.
- Non-retryable errors (401, 403, 409, 413, 422) → op `dead` at once and binding `failed`.
- `Outbox.reconcile()`: every `pending` binding without an op and with a spool file is re-enqueued; without a spool it is marked `failed`
  ("bytes lost before the operation was queued"). Runs at worker start.
- `OutboxWorker` (daemon thread) runs `process_once()` every `KA_DP_OUTBOX_INTERVAL` seconds only when the backend is `data_platform`;
  `process_once()` is also what the API's Run now calls.

## Phases

### Phase 1 - Model, collection, outbox and worker
- `ka/model.py`, `ka/repository.py`, `ka/outbox.py`, `ka/config.py`, `ka/events.py`.
- **Protected-code touched:** none

### Phase 2 - Ingestion and service wiring
- `ka/ingestion.py` (retryable → pending + spool + enqueue), `ka/service.py` (worker, `outbox_status`), `ka/api.py` routes, console.
- **Protected-code touched:** none

### Phase 3 - Tests, flow, docs
- `ka/tests/test_plan20_outbox.py`; `e2e/plan20_outbox_flow.py` (fake with `fail_next(2)` + DP-backed server with a 2 s interval: a paste is
  `pending` then `available` by itself; Dashboard shows outbox counts); `.env.example`; architecture §11.
- **Protected-code touched:** none

## Code blocks (B1..B7)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/outbox.py` | outbox, worker, handlers |
| B2 | `ka/model.py` | `PendingOp` |
| B3 | `ka/repository.py` | collection |
| B4 | `ka/ingestion.py` | pending + spool + enqueue |
| B5 | `ka/service.py`, `ka/api.py` | worker wiring, status, routes (one block each) |
| B6 | `ka/console/app.js` | Dashboard outbox line + Run now |
| B7 | `ka/config.py`, `ka/events.py` | settings; two event names (one block each) |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `PendingOp`; `dp_outbox` collection | `ka/model.py`, `ka/repository.py` | 1 |
| D2 | `Outbox.enqueue / due / process_once / mark / reconcile`, backoff and dead-letter rules | `ka/outbox.py` | 1 |
| D3 | `upload_source` handler (spool → upload/content/commit by idempotency key → binding available, spool deleted) | `ka/outbox.py` | 1 |
| D4 | `OutboxWorker` thread, DP backend only | `ka/outbox.py`, `ka/service.py` | 2 |
| D5 | ingestion: retryable DP failure → `pending` binding, spool, queued op; non-retryable → `failed` | `ka/ingestion.py` | 2 |
| D6 | routes `GET /physical/outbox`, `POST /physical/outbox/run`, `POST /physical/outbox/{id}/retry`; events | `ka/api.py`, `ka/events.py` | 2 |
| D7 | Dashboard outbox line with Run now; version pill `pending` tone | `ka/console/app.js` | 2 |
| D8 | live flow; `.env.example`; architecture §11 | `e2e/plan20_outbox_flow.py`, docs | 3 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P7)
- **P1** — `enqueue` → `process_once` against a healthy fake: binding `pending` → `available` with DP ids, spool removed, op `done`, event emitted.
- **P2** — backoff: each retryable failure increments `attempts` and pushes `next_at` by base·2^attempts; a due op is picked, a future one is not.
- **P3** — PT6: DP down (`fail_next`) at ingest → binding `pending`, version not available, spool present; the worker's later run commits once; exactly one asset version in the fake, one binding, one source.
- **P4** — crash between content and commit: the first commit call fails after the content was uploaded; the replay with the same key returns the same ids (no duplicate asset).
- **P5** — `reconcile` re-enqueues a `pending` binding with a spool and no op; marks `failed` one with no spool.
- **P6** — routes: status counts by state; Run now processes due ops; retry resets a dead op; the Dashboard carries the counts.
- **P7** — live flow: paste while the fake fails twice → the version shows `pending` then `available` by itself; the Dashboard outbox line moves to 0 pending.

## Negative Test Cases (N1..N5)
- **N1** — a non-retryable error (422) → op `dead` immediately, binding `failed` with the code; no spool left behind.
- **N2** — after `KA_DP_RETRIES` retryable failures → op `dead`, binding stays `pending` with the last error; `retry` resets it and a later run succeeds with one asset.
- **N3** — with the local backend no worker thread is started and `enqueue` is never called by ingestion.
- **N4** — after success the spool directory holds nothing for that version; the DP token appears in no op payload.
- **N5** — two ops for the same idempotency key (double enqueue) collapse to one `done` and one DP asset version.

## Plan totals

**Research points covered: 1 of 14 · Deliverables: 8 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 1 of 9 (PT6 turns green).**

## Implementation Notes
- Written against `7ab11a0` (plan-19). No protected code. The live service stays on the local backend; the flow uses a second server.
