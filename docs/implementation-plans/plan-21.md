# Plan 21 - Inbound Data Platform events: idempotent handling, bindings that flip, and one revocation rule for connectors and DP alike (research-03 R5, R9)

Created: 2026-10-09 14:20 UTC

## Problem Description

KA now writes to the Data Platform (plans 18–20) but hears nothing back. research-03 §5 lists the six DP events and how KA must answer:
`data.asset.committed.v1` flips a `pending` binding to `available` (for asynchronous commits); `data.asset.access_revoked.v1` and
`data.asset.quarantined.v1` return every ACTIVE nugget derived from the source to review (plan-10's `reopen_for_revocation`);
`data.asset.deleted.v1` marks the source revoked exactly as a deleted connector file does (`ka/connectors/sync.py:126-135`);
`data.index.ready.v1` and `data.ingestion.completed.v1` are recorded. Handlers are idempotent on `event_id`; the cursor is durable.
R9 adds the rule: connector deletions and DP revocations go through ONE function.

Desired outcome (PT7): a `data.asset.access_revoked.v1` event puts every ACTIVE nugget derived from that source back into review, and a
`deleted` event marks the source revoked, through the same path a deleted connector file takes.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q4 revocation is a governance event: derived knowledge returns to review (plan-10) | `knowledge-acquisition.md` §2, §10 | ✅ built | **extends it** — DP revocation, quarantine and deletion feed the same `reopen_for_revocation` |
| plan-08 deletion path: `Source.revoked_at`, derived nuggets flagged, `source.revoked` event, audit | `ka/connectors/sync.py:126-135` | ✅ built | **refactors it into one function** `SyncService.revoke_source` that both callers use (R9) |
| Events as an outbox with `seq`; handlers idempotent by id (plan-09) | `knowledge-acquisition.md` §9 | ✅ built | **the precedent** — inbound events get a durable cursor and an id set |
| §11 binding states; outbox worker on the DP backend (plans 18, 20) | `knowledge-acquisition.md` §11 | ✅ built | **extends it** — `revoked` binding state becomes reachable; polling rides on the worker's tick |
| Protected code | `docs/protected.md` | — | **not touched** — `reopen_for_revocation` is CALLED, not changed |

**Open questions in the sections this plan touches:** none blocking.

## Research coverage (R1..R14)

Source: [research-03](../research/research-03.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 | ✅ decided | — |
| R2, R3, R4, R11 | ✅ shipped | plans 18–20 |
| R5 inbound events | ✅ in scope | Phases 1–2 |
| R9 one revocation rule | ✅ in scope | Phase 1 |
| R6, R7 | ⏭️ deferred | plan-22 |
| R8, R10 | ⏭️ parked | Q15, Q16 |
| R12, R13, R14 | ⏭️ deferred | plan-23 |

**Covered here: 2 of 14.** Deferred: 5; parked: 2.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT7 `access_revoked` → every ACTIVE derived nugget back into review; `deleted` → source revoked, through the connector-deletion path | R5, R9 | **GREEN** |

## Scope

In: `ka/data_platform/inbound.py` (new: cursor, handlers, `poll`), `ka/connectors/sync.py` (`revoke_source` factored out and used by the
deletion loop), `ka/outbox.py` (the worker gains tick hooks so inbound polling runs on the DP backend), `ka/service.py` (wiring, status),
`ka/api.py` (`GET /physical/inbound`, `POST /physical/inbound/poll`), `ka/events.py` (`physical.event.received`, `physical.binding.revoked`),
`ka/console/app.js` (source page: `revoked` binding reason; Dashboard inbound cursor on the physical line), `ka/config.py`
(`KA_DP_INBOUND_INTERVAL`), tests, live flow, docs.

Out: DP search index use (plan-22 R7); nugget derived publication (plan-22); acknowledging events back to DP (the contract has no ack —
the cursor is the acknowledgement).

## Protected-code impact (summary)

✅ No protected code touched by any phase — `ka/governance.py::reopen_for_revocation` is called as plan-10 built it.

## Assumptions

- Cursor file `<storage>/dp_inbound.json`: `{"after": <seq>, "handled": [event_id…], "last_poll_at", "unmatched": n}`; `handled` keeps the last
  5,000 ids (the cursor makes older replays impossible anyway).
- Handlers by type: `committed` → binding with those DP ids: `pending` → `available` (no-op otherwise); `access_revoked`, `quarantined`,
  `deleted` → binding `revoked` with the reason, `SyncService.revoke_source(src, by="data-platform", reason=<type>)` (sets `revoked_at`,
  flags derived nuggets, emits `source.revoked`, audits, calls `reopen_for_revocation`); `index.ready` → binding `extracted_text_asset_id`
  when the event names a derived asset, else recorded; `ingestion.completed` → recorded. Unknown types are recorded and ignored.
- Every handled event is appended to KA's `events.jsonl` as `physical.event.received` with `dp_event_id`, `type`, `asset_id` (ids only).
- `OutboxWorker` gains `ticks: list[Callable[[], None]]` run after `process_once`; the service registers `inbound.poll` on the DP backend.
- `revoke_source` is the ONE rule: the sync loop's deletion branch becomes a call to it (behaviour unchanged, plan-08/10 tests unmodified).

## Phases

### Phase 1 - The one revocation rule and the inbound handlers
- `ka/connectors/sync.py::revoke_source`; `ka/data_platform/inbound.py`; `ka/events.py`; `ka/config.py`.
- **Protected-code touched:** none

### Phase 2 - Worker tick, routes, console
- `ka/outbox.py` ticks; `ka/service.py`; `ka/api.py`; `ka/console/app.js`.
- **Protected-code touched:** none

### Phase 3 - Tests, flow, docs
- `ka/tests/test_plan21_inbound_events.py`; `e2e/plan21_inbound_flow.py` (DP-backed server, 2 s interval; paste + approve; `fake.revoke` →
  the source shows revoked and the Dashboard lists the re-review); `.env.example`; architecture §11.
- **Protected-code touched:** none

## Code blocks (B1..B7)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/data_platform/inbound.py` | cursor, handlers, poll |
| B2 | `ka/connectors/sync.py` | `revoke_source` + the deletion loop calling it |
| B3 | `ka/outbox.py` | worker ticks |
| B4 | `ka/service.py`, `ka/api.py` | wiring, status, routes (one block each) |
| B5 | `ka/console/app.js` | revoked reason on the version pill; inbound cursor on the Dashboard line |
| B6 | `ka/events.py`, `ka/config.py` | names; setting (one block each) |
| B7 | — | — |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `SyncService.revoke_source(src, *, by, reason)` — the one rule; the deletion loop uses it | `ka/connectors/sync.py` | 1 |
| D2 | `InboundEvents` with a durable cursor, `handled` id set, `poll(client)`, per-type handlers, `status()` | `ka/data_platform/inbound.py` | 1 |
| D3 | `physical.event.received`, `physical.binding.revoked`; `KA_DP_INBOUND_INTERVAL` | `ka/events.py`, `ka/config.py` | 1 |
| D4 | `OutboxWorker.ticks`; the service registers polling on the DP backend; `physical_status` carries inbound | `ka/outbox.py`, `ka/service.py` | 2 |
| D5 | `GET /physical/inbound`, `POST /physical/inbound/poll` | `ka/api.py` | 2 |
| D6 | console: revoked reason on the version pill; Dashboard inbound cursor | `ka/console/app.js` | 2 |
| D7 | live flow; `.env.example`; architecture §11 | `e2e/plan21_inbound_flow.py`, docs | 3 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P7)
- **P1** — `poll` reads events after the cursor, handles each once, advances the cursor, persists it; a second poll with no new events does nothing.
- **P2** — `committed` for a binding that is `pending` with those DP ids flips it to `available` (asynchronous commit).
- **P3** — PT7a: `access_revoked` → binding `revoked`, `Source.revoked_at` set, derived ACTIVE nuggets flagged and re-review candidates created (plan-10), `source.revoked` emitted, audit present.
- **P4** — PT7b: `deleted` → the same path with reason `deleted`; the version's bytes are no longer `available`.
- **P5** — `quarantined` → revoked with reason `quarantined`; `index.ready` naming a derived asset sets `extracted_text_asset_id`; `ingestion.completed` is recorded.
- **P6** — routes: status shows the cursor and handled count; `POST …/poll` runs one poll; the Dashboard carries inbound figures.
- **P7** — R9: the connector deletion path and the DP deletion path both call `revoke_source` (spied), and plan-08/plan-10's own tests still pass unmodified.

## Negative Test Cases (N1..N5)
- **N1** — an unknown event type is recorded as received and ignored; nothing raises; the cursor still advances.
- **N2** — an event for an asset KA does not know is counted as `unmatched`, recorded, ignored.
- **N3** — the same `event_id` delivered twice is handled once (the second is a no-op even if the cursor were reset).
- **N4** — DP unavailable during poll → the cursor does not advance, nothing raises, the next poll resumes.
- **N5** — on the local backend no polling tick is registered and the cursor file is never created.

## Plan totals

**Research points covered: 2 of 14 · Deliverables: 7 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 1 of 9 (PT7 turns green).**

## Implementation Notes
- Written against `306fab9` (plan-20). No protected code. The live service stays on the local backend.
