# Plan 22 - Nugget versions as immutable derived artefacts on knowledge events; content read through the Data Platform; the images side door (research-03 R6, R7)

Created: 2026-10-09 15:20 UTC

## Problem Description

KA's governed knowledge lives only in `ka_storage/` JSON. research-03 §6 decides that every governed nugget version also exists in the
Data Platform as an **immutable derived artefact** — one per `(canonical_id, version, status)` — carrying the note's payload (interpretation,
status, authority, confidence, effective dates, evidence spans, source asset/version ids, extraction/model versions, governance and
graph-change ids, scope, visibility). It is written by a **service subscriber** on `knowledge.*` events through the plan-20 outbox,
never inside governance (protected). §7 decides that content is read through DP when bytes live there: `reextract` already does
(plan-18); "view source" and the images side door do not yet.

Desired outcome (PT4): an approved nugget resolves, through its DP derived artefact, to the source asset version, the evidence span and
the governance and graph-change ids.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| One governance pipeline; Invariant 3 (semantic fields immutable); protected `ka/governance.py` | `knowledge-acquisition.md` §4; `docs/protected.md` | ✅ built | **constrained by it** — the publisher is a bus subscriber in the service (plan-11's pattern); governance is not touched |
| Invariant 2: lineage on every graph change | `knowledge-acquisition.md` §5 | ✅ built | **constrained by it** — DP ids are recorded beside `knowledge_lineage`, never instead |
| §11 outbox: operations KA owes DP are queued, retried, idempotent (plan-20) | `knowledge-acquisition.md` §11 | ✅ built | **extends it** — `put_derived` handler joins the registry |
| Visibility: a nugget is never wider than its narrowest source | research-03 §6, §7 | ⏳ decided | **obeyed** — the artefact carries the nugget's visibility, which KA already computes |
| Invariant 1: no runtime path reads nuggets/sources to answer a question | `ka/runtime_guard.py` | ✅ built | **not touched** — publication writes outward; the content route is a human "view source", not a runtime answer |

**Open questions in the sections this plan touches:** Q16 (tenant) — interim constant, not blocking.

## Research coverage (R1..R14)

Source: [research-03](../research/research-03.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 | ✅ decided | — |
| R2–R5, R9, R11 | ✅ shipped | plans 18–21 |
| R6 derived artefacts | ✅ in scope | Phases 1–2 |
| R7 content through DP | ✅ in scope | Phase 2 — the read path (view source, images). The research itself puts DP **search** "later", and the v1 contract (plan-19 fixture) has no search endpoint; that half is recorded, not built |
| R8, R10 | ⏭️ parked | Q15, Q16 |
| R12, R13, R14 | ⏭️ deferred | plan-23 |

**Covered here: 2 of 14.** Deferred: 3; parked: 2.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT4 approved nugget → DP derived artefact → source asset version, evidence span, governance and graph-change ids | R6 | **GREEN** |
| PT5 bytes and derived copies through DP; local rollback | R2, R3, R6 | **GREEN** (the derived half lands here) |

## Scope

In: `ka/derived.py` (new: `DerivedPublisher` subscriber + payload builder + `put_derived` outbox handler), `ka/model.py` (`DerivedArtefact`),
`ka/repository.py` (collection), `ka/service.py` (wiring, `nugget_detail.derived`, images mirror), `ka/api.py`
(`GET /sources/{id}/versions/{n}/content`, `GET /nugget/{ref}/derived`, images mirror on save), `ka/console/app.js` (nugget page "DP copy"
line; version "view bytes" link), `ka/events.py` (`physical.derived.published`), tests, flow, docs.

Out: DP search (no v1 endpoint; research §7 "later"); any change to governance; a second approval path.

## Protected-code impact (summary)

✅ No protected code touched by any phase — the publisher subscribes to events governance already emits.

## Assumptions

- Events that publish: `knowledge.candidate.created`, `knowledge.approved`, `knowledge.rejected`, `knowledge.superseded` (ref = the
  superseded prior). Each writes one artefact for the version's CURRENT status at that moment; key `ka:<tenant>:nugget:<canonical>:<version>:<status>`.
- Payload (JSON): `canonical_id, version, ref, title, statement, normalized_meaning, knowledge_type, subject/predicate/object, binding
  (status, grammar digest from `ka.binding` when present), status, authority_type, authority_rank, confidence, effective_from/to, scope,
  visibility, evidence[] (id, source_id, source_version_id, span_id, start, end, locator, dp_asset_id, dp_asset_version_id), sources[]
  (source_id, version_id, dp ids from bindings), extraction_version per source version, research_run_refs, governance_decision_id,
  graph_change_refs, derived_graph_refs, supersedes/superseded_by, created_at/by, approved_at/by, ka_version`. Provenance: `{"producer":
  "ka", "event": <name>, "ka_version"}`. Parent: the first source version's binding ref (if DP ids exist).
- `DerivedArtefact(id, canonical_id, version, status, ref, kind="nugget_version", idempotency_key, backend, dp_asset_id,
  dp_asset_version_id, sha256, parent_asset_id, state pending|available|failed, op_id, event, created_at)`; one per key.
- On the local backend the publisher runs the outbox synchronously (`process_once`) after enqueueing, so a derived JSON lands in
  `<storage>/derived/nugget_version/` immediately; on DP the worker processes it (PT5 rollback: local keeps working).
- Content route returns the bytes with the version's media type through the physical store (local or DP); 409 when not available.
- Images: on the DP backend `images.save` is followed by `physical.put` and the index row gains `dp_asset_id`/`dp_asset_version_id`; a DP
  failure leaves the local image and records `dp_error` on the row (images are not knowledge; no outbox op).

## Phases

### Phase 1 - Model, publisher, handler
- `ka/model.py`, `ka/repository.py`, `ka/derived.py`, `ka/events.py`.
- **Protected-code touched:** none

### Phase 2 - Wiring, routes, console
- `ka/service.py`, `ka/api.py`, `ka/console/app.js`.
- **Protected-code touched:** none

### Phase 3 - Tests, flow, docs
- `ka/tests/test_plan22_derived.py`; `e2e/plan22_derived_flow.py` (DP-backed server: paste → approve → the nugget page shows the DP copy with
  asset ids; the fake holds a `nugget_version` asset whose payload names the source asset version and the evidence span; "view bytes" returns the pasted text).
- **Protected-code touched:** none

## Code blocks (B1..B6)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/derived.py` | publisher, payload, handler |
| B2 | `ka/model.py` | `DerivedArtefact` |
| B3 | `ka/repository.py` | collection |
| B4 | `ka/service.py`, `ka/api.py` | wiring + detail; routes (one block each) |
| B5 | `ka/console/app.js` | nugget page DP copy line; version view-bytes link |
| B6 | `ka/events.py` | event name |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `DerivedArtefact`; `derived_artefacts` collection | `ka/model.py`, `ka/repository.py` | 1 |
| D2 | `build_payload(repo, version) -> dict` with evidence spans, source/DP ids, governance and graph-change ids | `ka/derived.py` | 1 |
| D3 | `DerivedPublisher` subscribed to the four knowledge events; enqueues `put_derived` once per key; local runs synchronously | `ka/derived.py`, `ka/service.py` | 1–2 |
| D4 | `put_derived` outbox handler → artefact `available` with DP ids; `physical.derived.published` | `ka/derived.py`, `ka/events.py` | 1 |
| D5 | `nugget_detail["derived"]`; `GET /nugget/{ref}/derived` | `ka/service.py`, `ka/api.py` | 2 |
| D6 | `GET /sources/{id}/versions/{n}/content` through the physical store | `ka/api.py` | 2 |
| D7 | images mirrored to DP on the DP backend; row carries DP ids | `ka/api.py`, `ka/service.py` | 2 |
| D8 | console DP-copy line + view-bytes link; live flow; architecture §11 | `ka/console/app.js`, `e2e/`, docs | 2–3 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P7)
- **P1** — candidate created → one `nugget_version` artefact (status CANDIDATE) with the payload's canonical id, version, statement, scope, visibility.
- **P2** — PT4: approve → a second artefact (status ACTIVE) whose payload carries the source's DP asset/version ids (from the binding), the evidence span (`span_id`, `start`, `end`), `governance_decision_id` and `graph_change_refs`; the fake's asset has the source as parent.
- **P3** — supersede via a revision → artefacts for the prior (SUPERSEDED) and the new version; keys distinct; nothing overwritten (immutability per key).
- **P4** — local backend: the same events produce `derived/nugget_version/*.json` synchronously; `nugget_detail["derived"]` lists them with backend `local`.
- **P5** — content route returns the bytes and media type for an available version on both backends; 404 for an unknown version.
- **P6** — images on the DP backend: save → row has `dp_asset_id`; `GET /images/{n}` still serves locally.
- **P7** — live flow: nugget page shows "Data Platform copy · available · asset …"; view-bytes link serves the pasted text.

## Negative Test Cases (N1..N5)
- **N1** — DP down when the event fires → artefact `pending` with a queued op; the worker's later run makes it `available`; exactly one DP asset for the key.
- **N2** — the same event replayed (double emit) → one artefact, one op, one DP asset.
- **N3** — the publisher never writes a nugget version (byte-compare the version file before/after publication); governance file untouched by diff.
- **N4** — content route on a `pending`/`failed`/`revoked` version → 409 with the binding reason; no bytes leak.
- **N5** — the payload contains no DP service token and no local filesystem path.

## Plan totals

**Research points covered: 2 of 14 · Deliverables: 8 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 2 of 9 (PT4, PT5 turn green here).**

## Implementation Notes
- Written against `ce28607` (plan-21). No protected code. The live service stays on the local backend; publication there writes local derived JSON.
