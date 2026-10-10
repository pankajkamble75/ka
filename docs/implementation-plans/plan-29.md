# Plan 29 - AgentX contract core: health, capabilities, one invoke endpoint, durable operations, AgentX's error envelope, the AgentX caller (research-05 R2, R3, R10)

Created: 2026-10-10 13:00 UTC

## Problem Description

AgentX's side is fixed as PROPOSED v1 (research-05 §1, from the AgentX session 2026-10-10): AgentX pulls `GET {base}/v1/capabilities`, invokes
`POST {base}/v1/capabilities/{id}/invoke` with an `InvokeRequest`, receives an `OperationState` (terminal for sync, polled at
`GET {base}/v1/operations/{id}` for async, cancelled at `…/cancel`), and reads errors as `{"error": {code, message, retryable, details}}`.
This plan builds that core in KA over the existing services, with four capabilities — `knowledge.acquire` (async), `knowledge.search`,
`knowledge.read`, `knowledge.revise` (sync) — and the AgentX caller identity. Review, conflict resolution, publication and push registration
are plan-30.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Adopt AgentX PROPOSED v1, not a competing contract | research-05 §1 | ⏳ decided | **builds it** (core) |
| One governance pipeline; agents cannot decide | `knowledge-acquisition.md` §4 | ✅ built | **obeyed** — revise reaches `propose_revision` / `request_retirement`; nothing decides here |
| Invariant 1 (no runtime retrieval) | `ka/runtime_guard.py` | ✅ built | **obeyed** — search/read are governance reads, labelled so in the descriptors |
| Q1/Q4 access (containment; identity open) | `knowledge-acquisition.md` §10 | ✅ built / open | **extends it** — `KA_AGENTX_TOKEN` bearer for `/v1`; `caller.user` recorded as actor (interim) |
| Background work on a thread (plan-17) | `ka/research.py` | ✅ built | **the precedent** for async operations |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R12)

Source: [research-05](../research/research-05.md) — **12 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R2 contract + handlers + aliases | ✅ in scope (acquire, search, read, revise) | Phases 1–2; review/resolve/publish handlers are plan-30 |
| R3 operations | ✅ in scope | Phase 1 (callbacks via outbox: plan-30, with push registration) |
| R10 caller identity | ✅ in scope | Phase 1 |
| R4, R5 | ⏭️ plan-30 | |
| R7, R8 | ⏭️ plan-31 | |
| R9 | ⏭️ plan-32 | |
| R1, R6, R11, R12 | ⏭️ plan-33 | |

**Covered here: 3 of 12.**

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT2 acquisition → operation id → poll → succeeded → candidates | R2, R3 | **GREEN** |
| PT3 search and read governed knowledge (nugget + article) with provenance | R2 | **GREEN** |

## Scope

In: `ka/agentx/` (new package: `contract.py` — AgentX models, error classes, envelope; `operations.py` — `Operation` store and runner;
`capabilities.py` — descriptors and handlers; `router.py` — `/v1` routes, aliases, auth); `ka/model.py` (`Operation`); `ka/repository.py`
(collection); `ka/config.py` (`KA_AGENTX_TOKEN`, `KA_SERVICE_ID`); `ka/api.py` (mount the router, `/healthz` gains AgentX keys additively,
error handlers scoped to `/v1`); tests; flow.

Out: review/resolve/publish, interactions, push registration, callbacks (plan-30).

## Protected-code impact (summary)

✅ No protected code touched.

## Assumptions

- `/v1` auth: when `KA_AGENTX_TOKEN` is set, `Authorization: Bearer <KA_AGENTX_TOKEN>` is required (401 `unauthorized` otherwise) — also
  from loopback; when unset, the console's containment (`require_access`) applies. The console token is not accepted on `/v1` when the AgentX
  token is set.
- `caller.permissions` must contain the descriptor's `permissions` (403 `forbidden`); `caller.user` is the actor (`owner`, `by`).
- Input models are pydantic; descriptor schemas come from `model_json_schema()` (JSON Schema 2020-12); invalid input → 400 `schema_invalid`
  with the pydantic errors in `details`.
- Idempotency: the `Idempotency-Key` header (or `idempotency_key` in the body) is stored on the operation with a sha256 of
  `(capability_id, input)`; a repeat with the same hash returns the stored operation; a different hash → 409 `conflict`.
- Async runner: a daemon thread per operation (bounded by a semaphore of 4); statuses `accepted → running → succeeded | failed |
  cancelled`; progress 0..1; `cancel` honoured while `accepted` (and between steps for research), else 409 `conflict` with
  `details.reason = "not_cancellable"`.
- `knowledge.acquire` input `{kind: text|note|link|research|gap, raw_content?, uri?, name, scope {scope_type, scope_id}, authority?,
  visibility?, target?{structure_id?, instance_id?, leaf_id?}, question?, metadata?}`; output `{source_id, source_version_id, candidates[],
  refusals[], mission_id?, request_id?}`; `refusals` come from the version's extraction report `dropped`.
- `knowledge.search` input `{query, scope?, instance_id?, domain_id?, kind?: nugget|article|all, limit?}` → `{hits[{id, kind, title, snippet,
  status, scope, provenance}]}`; `knowledge.read` `{item_id}` → `{item, provenance}`; `knowledge.revise` `{item_id, change {statement} |
  {retire: true}, rationale}` → `{proposal_id, status, review_required: true}`.
- Aliases: `POST /v1/acquisitions` (body = acquire input + optional `caller`), `GET /v1/acquisitions/{id}`, `GET /v1/knowledge/search?query=`,
  `POST /v1/knowledge/search {query, instance_id?, domain_id?, limit}` → `{results[], version}` (Knowledge Worker's preview adapter),
  `GET /v1/knowledge/{id}`, `POST /v1/knowledge/{id}/revisions`; each builds an `InvokeRequest` and calls the same code.

## Phases

### Phase 1 - Contract models, operations, auth, errors
- `ka/agentx/contract.py`, `ka/agentx/operations.py`, `ka/model.py`, `ka/repository.py`, `ka/config.py`.
- **Protected-code touched:** none

### Phase 2 - Capabilities and routes
- `ka/agentx/capabilities.py`, `ka/agentx/router.py`, `ka/api.py`.
- **Protected-code touched:** none

### Phase 3 - Tests and flow
- `ka/tests/test_plan29_agentx_core.py`; `e2e/plan29_agentx_flow.py` (a fake AgentX client over real HTTP); architecture note.
- **Protected-code touched:** none

## Code blocks (B1..B7)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/agentx/contract.py` | AgentX models, error classes |
| B2 | `ka/agentx/operations.py` | operation store and runner |
| B3 | `ka/agentx/capabilities.py` | descriptors and four handlers |
| B4 | `ka/agentx/router.py` | `/v1` routes and aliases |
| B5 | `ka/model.py`, `ka/repository.py` | `Operation` + collection (one block each) |
| B6 | `ka/config.py` | two settings |
| B7 | `ka/api.py` | mount, health keys, error handlers |

## Deliverables (D1..D9)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `InvokeRequest`, `Caller`, `OperationState`, `AgentXError` with AgentX's classes and the envelope | `ka/agentx/contract.py` | 1 |
| D2 | `Operation` record + collection | `ka/model.py`, `ka/repository.py` | 1 |
| D3 | `Operations` — create (idempotent), run sync/async, poll, cancel, progress | `ka/agentx/operations.py` | 1 |
| D4 | `/v1` auth (`KA_AGENTX_TOKEN`), permission check, tenant check | `ka/agentx/router.py`, `ka/config.py` | 1 |
| D5 | descriptors (AgentX shape) for acquire/search/read/revise with pydantic-generated schemas | `ka/agentx/capabilities.py` | 2 |
| D6 | handlers: acquire (async; text/note/link/research/gap), search, read, revise | `ka/agentx/capabilities.py` | 2 |
| D7 | routes: `GET /v1/capabilities`, `POST /v1/capabilities/{id}/invoke`, `GET /v1/operations/{id}`, `POST …/cancel`; aliases | `ka/agentx/router.py` | 2 |
| D8 | `/healthz` additive keys `status, service_id, checks`; `/v1` error handlers | `ka/api.py` | 2 |
| D9 | live flow; architecture note | `e2e/plan29_agentx_flow.py`, docs | 3 |

**Total deliverables: 9.**

## Positive Test Cases (P1..P8)
- **P1** — `GET /v1/capabilities` → `{service_id, schema_version:"1", capabilities}`; every descriptor has exactly AgentX's keys; schemas are JSON objects with `type`.
- **P2** — PT2: invoke `knowledge.acquire` (text) → 202-style `accepted`/`running` with an `operation_id`; polling reaches `succeeded` with `source_id` and `candidates`; the candidates are PENDING_REVIEW in KA.
- **P3** — PT3a: invoke `knowledge.search` (sync) → `succeeded` with hits including an ACTIVE nugget and a wiki article, each with provenance.
- **P4** — PT3b: invoke `knowledge.read` on a nugget ref, a canonical id and a wiki key → item + provenance chain (sources, evidence spans, decision).
- **P5** — invoke `knowledge.revise` with a changed statement → a PENDING_REVIEW revision (`propose_revision`), and with `retire:true` → a retirement request (`request_retirement`); nothing ACTIVE changes.
- **P6** — idempotency: the same key + same input returns the same operation and creates one source; research acquisition links its mission.
- **P7** — `/healthz` returns `status: ok`, `service_id`, `version`, `checks` (and the old keys); the aliases return the same data as invoke; `POST /v1/knowledge/search` serves KW's shape.
- **P8** — live flow: a fake AgentX over real HTTP pulls capabilities, invokes acquire, polls to succeeded, searches and reads.

## Negative Test Cases (N1..N6)
- **N1** — with `KA_AGENTX_TOKEN` set: no/wrong bearer → 401 `{"error": {"code": "unauthorized"}}`; the console token is refused on `/v1`.
- **N2** — `caller.permissions` without the needed permission → 403 `forbidden`; tenant mismatch → 403 `forbidden`.
- **N3** — invalid input → 400 `schema_invalid` with details; unknown capability → 404 `not_found`; wrong `capability_version` major → 409 `stale_version`.
- **N4** — same `Idempotency-Key`, different input → 409 `conflict`; nothing executed twice.
- **N5** — cancel a queued/accepted operation → `cancelled`; cancel a finished one → 409 `conflict` `not_cancellable`; unknown operation → 404.
- **N6** — a handler failure → operation `failed` with `error.code` (`bad_request` for GovernanceError, `internal` otherwise) and `retryable` set; the console routes and their tests are unchanged.

## Plan totals

**Research points covered: 3 of 12 · Deliverables: 9 · Positive cases: 8 · Negative cases: 6 · Test cases total: 14 ·
Product tests served: 2 of 9 (PT2, PT3 turn green here).**

## Implementation Notes
- Written against `010d525`. No protected code. AgentX's schema files are not pushed yet; descriptor key sets follow the AgentX session's message verbatim.
