# Plan 30 - Review, conflict resolution and publication for AgentX: human input as AgentX interactions, the task list, push registration and callbacks through the outbox (research-05 R4, R5)

Created: 2026-10-10 14:30 UTC

## Problem Description

plan-29 gave AgentX four capabilities. The governance half is missing: a person reviewing a candidate, resolving a conflict, and publishing
approved knowledge. research-05 §3–§4 and AgentX's contract (its session, 2026-10-10; schemas vendored in `ka/agentx/schemas/`) decide the
shape: `knowledge.review` and `knowledge.resolve_conflict` start an operation that moves at once to `awaiting_input` with an
`interaction {interaction_id, prompt, ui_schema, required_permission}` in AgentX's declarative UI schema; AgentX renders it and posts
`POST /v1/operations/{id}/input {interaction_id, values, submitted_by}`; KA turns that into `governance.decide(by=submitted_by)`, refusing a
research-agent user. `knowledge.publish` (`requires_approval: true` — AgentX inserts its own approval first; Q3: a named person) approves and
applies a graph change proposal or publishes a wiki proposal, and succeeds only when the change is applied. `GET /v1/tasks` lists open review
work so AgentX knows what to start. With `KA_AGENTX_URL` set, KA pushes its capability list to AgentX and POSTs `OperationEvent`s to an
invocation's `callback_url`, both through the plan-20 outbox (durable, retried).

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| One governance pipeline; agents cannot decide | `knowledge-acquisition.md` §4; `ka/governance.py:316` | ✅ built | **obeyed** — every decision is `decide`; no second path |
| Q3: graph changes approved and applied by a named person | `knowledge-acquisition.md` §5 | ✅ built | **obeyed** — publish needs `caller.user`; `requires_approval: true` |
| Q19 wiki publication records a digest | `knowledge-acquisition.md` §8a | ✅ built | **reused** — publish of a wiki proposal is `WikiService.publish` |
| plan-20 outbox: durable operations with retry and dead-letter | `knowledge-acquisition.md` §11 | ✅ built | **extends it** — two new handler kinds (`agentx_register`, `agentx_callback`) |
| AgentX PROPOSED v1 (interactions, `required_permission`, OperationInput, OperationEvent) | research-05 §1, §4 | ⏳ decided | **builds it** |
| Protected code | `docs/protected.md` | — | **not touched** — `decide`, `approve`, `apply` are called as they are |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R12)

| Research point | This plan | Where / why |
|---|---|---|
| R2, R3, R10 | ✅ shipped | plan-29 (this plan adds three handlers to R2's registry and callbacks to R3) |
| R4 descriptors + registration | ✅ in scope | Phase 2 |
| R5 interactions + tasks | ✅ in scope | Phase 1 |
| R7, R8 | ⏭️ plan-31 (publish to Knowledge Worker over HTTP) | |
| R9 | ⏭️ plan-32 | |
| R1, R6, R11, R12 | ⏭️ plan-33 | |

**Covered here: 2 of 12.**

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 seven descriptors pulled (and pushed) and accepted by AgentX | R4 | **GREEN** for the descriptors (no EOS-free start until plan-31) |
| PT4 review through an interaction; agent user refused | R5, R10 | **GREEN** |
| PT5 a /v1 revision and a wiki edit reach the same pipeline | R2, R5 | **GREEN** |
| PT6 publication succeeds only on confirmation | R3, R7 | GREEN for the local adapter; the KW half is plan-31 |

## Scope

In: `ka/agentx/governance_caps.py` (new: review, resolve_conflict, publish handlers, the UI schemas, input handling, task listing),
`ka/agentx/operations.py` (`await_input`, `submit_input`, refresh hook, callbacks), `ka/agentx/router.py` (`POST /v1/operations/{id}/input`,
`GET /v1/tasks`, `POST /v1/capabilities/register`, aliases `POST /v1/knowledge/{id}/review`, `POST /v1/publications`),
`ka/agentx/registration.py` (new: push + callback outbox handlers), `ka/service.py` (attach the extension and the outbox handlers),
`ka/config.py` (`KA_AGENTX_URL`), tests, flow.

Out: Knowledge Worker over HTTP (plan-31); identity beyond the interim (Q4).

## Protected-code impact (summary)

✅ No protected code touched.

## Assumptions

- `knowledge.review` input `{item_id}` (a PENDING_REVIEW/CONFLICT nugget ref, or a wiki proposal id `WP-…`); `knowledge.resolve_conflict`
  input `{item_id}` (a CONFLICT version). Unknown or not open → `failed` `not_found` / `conflict`.
- The interaction: `interaction_id = "<op id>:1"`, `required_permission = "knowledge.review"`, `ui_schema` = AgentX UiSchema v1 — one form
  `decision` with fields `outcome` (select: allowed outcomes), `reason` (textarea, required), `merged_statement` (textarea, MERGE only by
  help text), views `candidate` (detail bound to `interaction.candidate`), `evidence` (table), `conflicts` (table), actions `approve`,
  `reject` (and `submit`). The candidate, evidence and conflicts travel in `operation.references` so views can bind to them.
- Input → `decide(ref, outcome, by=submitted_by, reason, merged_statement?, existing_ref?)`; a research-agent `submitted_by` → 403
  `forbidden`; values not matching the form → 400 `schema_invalid`; a stale `interaction_id` → 409 `conflict`. Result `{decision_id,
  outcome, resulting_refs, graph_change_ids}`.
- If the version is decided elsewhere (console) before input arrives, the next poll completes the operation `succeeded` with
  `message: "decided elsewhere"` and the decision id.
- `knowledge.publish` input `{proposal_id}` (graph change `GCP-…` or wiki proposal `WP-…`) or `{item_id}` (an ACTIVE nugget ref → its
  newest READY/APPROVED proposal). Graph: `approve(by=caller.user)` if READY, then `apply(by=…)`; `succeeded` when APPLIED, `failed` with
  `conflict` when FAILED. Wiki: `WikiService.publish(key, by, proposal_id)`. `caller.user` required (Q3) and not a research agent.
- `GET /v1/tasks` → `{tasks: [{task_id, kind: review_candidate | resolve_conflict | review_wiki_proposal | review_retirement, item_id, title,
  summary, scope, created_at, start: {capability, input}}]}`.
- Registration push: `KA_AGENTX_URL` + `KA_SERVICE_ID` + `KA_AGENTX_TOKEN` → `PUT {agentx}/api/v1/services/{service_id}/capabilities`
  `{capabilities}` through the outbox (`agentx_register`, key = sha of the list) on start and on `POST /v1/capabilities/register`.
- Callbacks: when an operation has `callback_url`, each status change enqueues `agentx_callback` (key = `<op id>:<status>:<n>`) with
  `OperationEvent {service_id, operation}`; the outbox processes it at once (and retries on its schedule).

## Phases

### Phase 1 - Governance capabilities and interactions (R5)
- `ka/agentx/governance_caps.py`, `ka/agentx/operations.py`, `ka/agentx/router.py`, `ka/service.py`.
- **Protected-code touched:** none

### Phase 2 - Registration and callbacks (R4)
- `ka/agentx/registration.py`, `ka/config.py`, `ka/service.py`.
- **Protected-code touched:** none

### Phase 3 - Tests and flow
- `ka/tests/test_plan30_agentx_governance.py`; `e2e/plan30_agentx_review_flow.py` (a fake AgentX HTTP server receives the push and the
  callbacks; review → approve via input → publish → applied).
- **Protected-code touched:** none

## Code blocks (B1..B5)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/agentx/governance_caps.py` | three handlers, UI schemas, input, tasks |
| B2 | `ka/agentx/registration.py` | push + callback outbox handlers |
| B3 | `ka/agentx/operations.py`, `ka/agentx/router.py` | interaction support; new routes (one block each) |
| B4 | `ka/service.py` | wiring |
| B5 | `ka/config.py` | `KA_AGENTX_URL` |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `knowledge.review` and `knowledge.resolve_conflict` → `awaiting_input` with an AgentX-valid UI schema and `required_permission` | `governance_caps.py` | 1 |
| D2 | `POST /v1/operations/{id}/input` → `decide(by=submitted_by)`; agents refused; stale interaction refused; decided-elsewhere completion | `governance_caps.py`, `operations.py`, `router.py` | 1 |
| D3 | `knowledge.publish` (graph change approve+apply, wiki publish); success only when applied; named user required | `governance_caps.py` | 1 |
| D4 | `GET /v1/tasks` | `governance_caps.py`, `router.py` | 1 |
| D5 | aliases `POST /v1/knowledge/{id}/review`, `POST /v1/publications` | `router.py` | 1 |
| D6 | push registration through the outbox; `POST /v1/capabilities/register` | `registration.py`, `router.py`, `config.py` | 2 |
| D7 | `OperationEvent` callbacks through the outbox | `registration.py`, `operations.py` | 2 |
| D8 | tests; live flow with a fake AgentX server | tests, `e2e/` | 3 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P8)
- **P1** — seven descriptors; each passes AgentX's descriptor schema and code rules; review/resolve declare `ui_schema`; publish has `requires_approval: true`.
- **P2** — PT4: review a PENDING candidate → `awaiting_input`; the interaction's `ui_schema` passes AgentX's UiSchema rules and carries `required_permission`; input APPROVE by `alice` → ACTIVE, decision `by` = alice, operation `succeeded` with the decision id.
- **P3** — resolve a CONFLICT with ACCEPT_NEW and, separately, MERGE (merged statement) → the decided outcome, prior superseded.
- **P4** — decided elsewhere: a console decision while the operation waits → the next poll is `succeeded` with "decided elsewhere".
- **P5** — PT5: a `/v1` revise and a wiki-draft submission both produce candidates that `knowledge.review` decides through the same `decide`.
- **P6** — publish a READY graph change by proposal id and by nugget ref → APPLIED, `succeeded` with execution and graph ids; publish a resolved wiki proposal → `published`.
- **P7** — `GET /v1/tasks` lists candidates, conflicts, wiki proposals and retirement requests with a ready `start` invocation.
- **P8** — with `KA_AGENTX_URL` (a fake AgentX server): start pushes the capability list (bearer, service path); an operation with `callback_url` delivers `OperationEvent`s valid against AgentX's schema for each status change; both ride the outbox.

## Negative Test Cases (N1..N6)
- **N1** — input by a research-agent user → 403 `forbidden`; the version stays PENDING; input without `submitted_by` → 403.
- **N2** — values not in the form (unknown outcome, MERGE without merged statement, missing reason) → 400 `schema_invalid`; nothing decided.
- **N3** — a wrong `interaction_id`, or input to an operation not awaiting input → 409 `conflict`.
- **N4** — publish without `caller.user` → 403; publish of a REJECTED or already APPLIED proposal → `failed` `conflict`; review of a non-open item → `failed`.
- **N5** — AgentX unreachable: the push and the callbacks stay `pending`/`dead` in the outbox with the error; the operation itself is unaffected.
- **N6** — plan-29's 14 cases and the console's governance tests pass unchanged.

## Plan totals

**Research points covered: 2 of 12 · Deliverables: 8 · Positive cases: 8 · Negative cases: 6 · Test cases total: 14 ·
Product tests served: 4 of 9 (PT4, PT5 green; PT1, PT6 partly).**

## Implementation Notes
- Written against `6921320` (plan-29).
