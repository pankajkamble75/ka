# Plan 33 - KA as a service: the source inventory, the `/v1/events` view, the service documentation and OpenAPI, and a two-process EOS-free run (research-05 R1, R6, R11, R12)

Created: 2026-10-10 18:30 UTC

## Problem Description

Plans 29–32 made KA an independently running service: AgentX's v1 contract (capabilities, operations, interactions, tasks, push
registration, callbacks), Knowledge Worker over HTTP, the real Data Platform. Four research-05 points remain. **R1**: the author decided the
active KA is `pankajkamble75/ka`; the note asks for a written inventory (commit, routes, stores, wiki UI, nugget lifecycle, connectors) and
an ownership/dependency map. **R6**: the note asks for durable events under its own names with event ids, schema versions, provenance and
replay; KA's `/events` outbox (`ka/repository.py:286–297`, `ka/api.py:1281`) already persists every event with a `seq`, but under KA's names.
**R11**: nothing describes KA as a service — deployment, settings, the OpenAPI document, examples, failure handling. **R12**: no run proves,
in one go over real HTTP, that KA starts with no Enterprise OS checkout and that AgentX, Knowledge Worker and the governance pipeline work
together.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §38 events carry ids, never content; the outbox `seq` resumes exactly | `knowledge-acquisition.md` §9 | ✅ built | **constrained by it** — the v1 view is a read of the same log, no second log |
| One governance pipeline; agents cannot decide | `knowledge-acquisition.md` §4 | ✅ built | **obeyed** — the two-process run decides only through `/v1` input with a named user |
| AgentX services contract PROPOSED v1, adopted | research-05 §1, plan-29 | ✅ built | **obeyed** |
| KA as a service (AgentX, KW, DP over HTTP) | — | ⏳ built in plans 29–32, not written down | **builds it** — architecture §13 |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R12)

| Research point | This plan | Where / why |
|---|---|---|
| R2–R5, R7–R10 | ✅ shipped | plans 29–32 |
| R1 inventory + ownership map | ✅ in scope | Phase 1 |
| R6 `/v1/events` | ✅ in scope | Phase 2 |
| R11 docs, OpenAPI, README | ✅ in scope | Phase 3 |
| R12 two-process run | ✅ in scope | Phase 4 |

**Covered here: 4 of 12. With plans 29–32: 12 of 12.**

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT7 every v1 event replayable by `after`, with event id, schema version and provenance; duplicate delivery idempotent | R6 | **GREEN** |
| PT1–PT6, PT8 | — | already GREEN (plans 29–31); re-proved together over HTTP by the two-process run |

## Scope

In: `docs/integration/` (new: `source-inventory.md`, `README.md` deployment/settings/failure handling/examples, `openapi-v1.json`);
`ka/agentx/events.py` (new); `ka/agentx/router.py` (`GET /v1/events`); `tools/export_openapi.py` (new); `docs/architecture/knowledge-acquisition.md`
(§13); `docs/architecture/architecture-index-lookup.md` (row) if present; `README.md` (section); tests; `e2e/plan33_two_process_flow.py`.

Out: AgentX's own work; retiring the legacy eos-local adapter.

## Protected-code impact (summary)

✅ No protected code touched — new modules, a route in the plan-29 router, documents.

## Assumptions

- The v1 view maps KA's event names to the note's: `knowledge.candidate.created → knowledge.review.required`; `correction.submitted`,
  `wiki.draft.submitted` → `knowledge.revision.proposed`; `knowledge.conflict.detected` (same name); `graph.change.approved → knowledge.publication.approved`;
  `graph.change.applied`, `wiki.published` → `knowledge.publication.completed`; `knowledge.acquisition.completed` (same). Other KA events
  are not in the view (`/events` keeps them all).
- Each v1 event: `{event_id (KA's, stable), type, schema_version: "ka.v1", seq, occurred_at, subject (the event's ids), provenance:
  {service_id, source_event, ka_version}}`; `GET /v1/events?after=<seq>&limit=` → `{events, next_after, schema_version}`. Replay by `after`;
  a consumer de-duplicates by `event_id` (stable across replays) — that is the idempotent delivery the note asks for.
- The OpenAPI document is generated from the app (`app.openapi()`), filtered to `/v1` and `/healthz`, written to
  `docs/integration/openapi-v1.json`; a test fails when it is stale.
- The two-process run: KA (`python -m ka serve`, no `KA_ENTERPRISE_OS_ROOT`) + a fake AgentX over HTTP (receives push registration and
  callbacks) + the plan-31 fake Knowledge Worker over HTTP.

## Phases

### Phase 1 - Inventory (R1)
- `docs/integration/source-inventory.md`. **Protected-code touched:** none

### Phase 2 - Events view (R6)
- `ka/agentx/events.py`, `ka/agentx/router.py`. **Protected-code touched:** none

### Phase 3 - Documentation (R11)
- `docs/integration/README.md`, `docs/integration/openapi-v1.json`, `tools/export_openapi.py`, architecture §13, README section. **Protected-code touched:** none

### Phase 4 - Two-process run (R12)
- `ka/tests/test_plan33_service.py`, `e2e/plan33_two_process_flow.py`. **Protected-code touched:** none

## Code blocks (B1..B3)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/agentx/events.py` | the v1 event view |
| B2 | `ka/agentx/router.py` | `GET /v1/events` |
| B3 | `tools/export_openapi.py` | OpenAPI export |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | source inventory + ownership/dependency map | `docs/integration/source-inventory.md` | 1 |
| D2 | `v1_events(ka, after, limit)` + the name map | `ka/agentx/events.py` | 2 |
| D3 | `GET /v1/events` | `ka/agentx/router.py` | 2 |
| D4 | integration guide (deployment, settings, examples, failure handling) | `docs/integration/README.md` | 3 |
| D5 | OpenAPI document + exporter | `docs/integration/openapi-v1.json`, `tools/export_openapi.py` | 3 |
| D6 | architecture §13 "KA as a service" (+ index row) | `docs/architecture/knowledge-acquisition.md` | 3 |
| D7 | README section | `README.md` | 3 |
| D8 | two-process flow | `e2e/plan33_two_process_flow.py` | 4 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P6)
- **P1** — PT7: after an acquisition and a review, `/v1/events` lists `knowledge.acquisition.completed` and `knowledge.review.required` with `event_id`, `schema_version: "ka.v1"`, `seq`, provenance naming the KA event.
- **P2** — PT7: `after=<seq>` resumes exactly; two reads of the same range return the same `event_id`s (idempotent replay).
- **P3** — an approved graph change and its application appear as `knowledge.publication.approved` and `knowledge.publication.completed`; a wiki publication as `knowledge.publication.completed`.
- **P4** — `docs/integration/openapi-v1.json` equals the app's current `/v1` + `/healthz` OpenAPI (the export is not stale) and lists every route.
- **P5** — the inventory, the integration guide and architecture §13 exist and name every `/v1` route and every `KA_` setting the service plans added (29–32).
- **P6** — the two-process flow exists and covers start-up with no EOS root, push registration, acquire, review by a named user, publish through KW, events.

## Negative Test Cases (N1..N4)
- **N1** — `/v1/events` without the AgentX token → 401 `unauthorized` (when `KA_AGENTX_TOKEN` is set).
- **N2** — KA events outside the map (e.g. `physical.binding.available`) are not in the v1 view but remain in `/events`.
- **N3** — `limit` is bounded (0 < limit ≤ 1000); a negative `after` is `schema_invalid`.
- **N4** — an event payload never carries content: every v1 `subject` value is an id or short label (≤ 200 chars), as §38 requires.

## Plan totals

**Research points covered: 4 of 12 (set: 12 of 12) · Deliverables: 8 · Positive cases: 6 · Negative cases: 4 · Test cases total: 10 ·
Product tests served: 1 of 9 turns green here (PT7); all 9 GREEN after this plan.**

## Implementation Notes
- Written against `2ca0dea` (plan-32).
