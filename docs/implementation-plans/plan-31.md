# Plan 31 - Knowledge Worker over HTTP: KA's intake contract, a wire-level fake, the HTTP adapter, publication confirmed by KW, grammar over HTTP (research-05 R7, R8)

Created: 2026-10-10 15:40 UTC

## Problem Description

KA publishes graph changes by importing Enterprise OS's private `knowledge_worker.graph_store` (`ka/graph_adapter.py:387–568`) and reads the
grammar from a checkout path. Knowledge Worker is now its own service (`pankajkamble75/knowledge-worker`, `http://127.0.0.1:8101`, `/v1`; its
session, 2026-10-10) with no intake for KA; its session agreed the shape KA proposed and will implement it once KA publishes the contract.
This plan publishes `docs/contracts/knowledge-worker-v1-ka.md` with executable fixtures and an in-repo wire-level fake, adds
`KnowledgeWorkerHTTPAdapter` (KA's shadow graph as read model; publication through `POST /v1/graph-changes`), makes `knowledge.publish`
succeed only when Knowledge Worker reports the change applied, and loads the grammar from KW's `GET /v1/graph-model`.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Invariant 2: graph changes only as governed proposals with lineage | `knowledge-acquisition.md` §5 | ✅ built | **obeyed** — every op carries `props.knowledge_lineage`; KW decides |
| `ka/graph_change.py` is protected; `apply` marks APPLIED when the adapter returns | `docs/protected.md` | ✅ built | **not touched** — the publish capability waits for KW's `applied` before calling `apply`; `apply`'s adapter call is then an idempotent replay |
| Q2/Q3: repin explicit; a named person publishes | `knowledge-acquisition.md` §5 | ✅ built | **obeyed** |
| Grammar snapshot by version + digest, fail closed on drift | `knowledge-acquisition.md` §5a | ✅ built | **extends it** — a URL source |
| KW's v1 conventions (bearer + scope, `X-Correlation-ID`, envelope `{contract_version, correlation_id, status, result, error, provenance}`) | KW session, 2026-10-10 | — | **adopted** for the intake |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R12)

| Research point | This plan | Where / why |
|---|---|---|
| R2–R5, R10 | ✅ shipped | plans 29–30 |
| R7 KW over HTTP | ✅ in scope | Phases 1–3 |
| R8 grammar over HTTP | ✅ in scope | Phase 4 |
| R9 | ⏭️ plan-32 | |
| R1, R6, R11, R12 | ⏭️ plan-33 | |

**Covered here: 2 of 12.**

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 KA starts with no EOS checkout and registers its capabilities | R7, R8 | **GREEN** |
| PT6 publication `running` until KW confirms, then `succeeded` with lineage | R3, R7 | **GREEN** |
| PT8 no `knowledge_worker` import unless eos-local; grammar from URL with digests | R7, R8 | **GREEN** |

## Scope

In: `docs/contracts/knowledge-worker-v1-ka.md` + `ka/tests/fixtures/kw_contract/*.json`; `ka/knowledge_worker/` (new: `client.py`, `fake.py`);
`ka/graph_adapter.py` (new class `KnowledgeWorkerHTTPAdapter` in its own block — the protected `validate_change`/`publish` of the existing
adapters are untouched); `ka/service.py` (`KA_GRAPH_MODE`); `ka/grammar.py` (`KA_GRAMMAR_URL`); `ka/agentx/governance_caps.py` (publish waits
for KW); `ka/config.py`; tests; flow.

Out: KW's implementation (its session); retiring the EOS adapter (kept, explicit).

## Protected-code impact (summary)

✅ No protected code edited. `ka/graph_adapter.py` is a shared dependency of the graph_change area (`validate_change`/`publish` of the
adapters); this plan ADDS a new adapter class in its own block and changes no existing method. The graph_change covering tests must pass
unmodified (N6).

## Assumptions

- Intake (KA's side, KW implements): `POST /v1/graph-changes` with `Authorization: Bearer <KA's KW token>` (scope `graph-changes:propose`),
  `X-Correlation-ID`; body `{target: {kind: instance|substructure, id, base_digest?|base_version?}, ops: [ChangeOp], reason, actor,
  knowledge_refs: [{nugget_ref, decision_id}], idempotency_key}`; response envelope `{contract_version: "1", correlation_id, status: ok|error,
  result: {proposal_id, status: awaiting_approval|applied|refused, applied_digest?, new_version?, pinned_instances?, lineage[]}, error:
  {status, code, message, retryable, detail}, provenance}`; codes `STALE_BASE` 409, `INVALID_REQUEST` 422, `UNKNOWN_INSTANCE` 404,
  `FORBIDDEN` 403, `CONFLICT` 409 (same key, different body). `GET /v1/graph-changes/{id}` → same result. Same `idempotency_key` + same body →
  the existing proposal.
- `KA_KW_URL`, `KA_KW_TOKEN`, `KA_KW_PUBLISH_WAIT_S` (default 30), `KA_GRAPH_MODE` (`auto` default: `kw` when `KA_KW_URL` is set, else
  `eos-local` when `KA_ENTERPRISE_OS_ROOT` is set — legacy, reported in `/healthz` checks as `eos-local (deprecated)` — else `memory`;
  explicit `memory | kw | eos-local` override).
- The KW adapter subclasses `InMemoryGraphAdapter` (KA's shadow graph is the read model for lineage, impact and console); `publish` POSTs with
  `idempotency_key = "ka:" + KA proposal id` (derived from the lineage's `graph_change_id`), polls up to `KA_KW_PUBLISH_WAIT_S`; `applied` →
  the shadow applies the same changes and returns `PublishResult(applied, eos_proposal_id=KW id, eos_status, new_version, pinned_instances)`;
  `awaiting_approval` past the wait or `refused` → `PublishRefused` with KW's code; rollback → `PublishRefused("unsupported")`.
  `base_version(scope)` reads KW's `GET /v1/graph-versions` (instance digest / substructure latest version).
- `knowledge.publish` with the KW adapter: submit (POST) first, keep the operation `running` with "awaiting Knowledge Worker" while polling
  (no wait cap — the operation's own timeout governs), and call `graph_change.approve/apply` only after KW reports `applied`; KW `refused` →
  operation `failed` with KW's code and the KA proposal left APPROVED (retryable by the person).
- Grammar URL: `GET <KA_GRAMMAR_URL>` with `Authorization: Bearer KA_KW_TOKEN` → `{grammar, process_types, grammar_version, type_table_version,
  grammar_digest, type_table_digest}`; KA uses the server's digests as the snapshot identity (same version + different digest → stale, fail
  closed, as today). KA cannot recompute a file-bytes digest from parsed JSON; that limit is stated in the contract.

## Phases

### Phase 1 - Contract and fixtures
- `docs/contracts/knowledge-worker-v1-ka.md`; `ka/tests/fixtures/kw_contract/*.json`.

### Phase 2 - Client and fake
- `ka/knowledge_worker/client.py`, `ka/knowledge_worker/fake.py`.

### Phase 3 - Adapter, selection, publish waits for KW
- `ka/graph_adapter.py` (new class), `ka/service.py`, `ka/agentx/governance_caps.py`, `ka/config.py`.
- **Protected-code touched:** none (shared dependency: additive class only)

### Phase 4 - Grammar over HTTP; tests; flow
- `ka/grammar.py`; `ka/tests/test_plan31_knowledge_worker.py`; `e2e/plan31_kw_flow.py`.

## Code blocks (B1..B6)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/knowledge_worker/client.py` | HTTP client |
| B2 | `ka/knowledge_worker/fake.py` | wire-level fake |
| B3 | `ka/graph_adapter.py` | `KnowledgeWorkerHTTPAdapter` |
| B4 | `ka/service.py`, `ka/config.py` | `KA_GRAPH_MODE` selection; settings |
| B5 | `ka/agentx/governance_caps.py` | publish waits for KW |
| B6 | `ka/grammar.py` | URL source |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | contract document | `docs/contracts/knowledge-worker-v1-ka.md` | 1 |
| D2 | executable fixtures (request/response pairs) | `ka/tests/fixtures/kw_contract/` | 1 |
| D3 | `KnowledgeWorkerClient` (propose, get, graph_versions, graph_model) with envelope + typed errors | `ka/knowledge_worker/client.py` | 2 |
| D4 | `FakeKnowledgeWorker` (wire-level, auto-apply or approval mode, STALE_BASE, idempotency, token scope; `serve()`) | `ka/knowledge_worker/fake.py` | 2 |
| D5 | `KnowledgeWorkerHTTPAdapter` | `ka/graph_adapter.py` | 3 |
| D6 | `KA_GRAPH_MODE` selection + health check | `ka/service.py`, `ka/agentx/router.py` | 3 |
| D7 | publish waits for KW's `applied` | `ka/agentx/governance_caps.py` | 3 |
| D8 | `KA_GRAMMAR_URL` | `ka/grammar.py` | 4 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P7)
- **P1** — every fixture's request is accepted by the fake and its response matches the fixture's expected status and shape.
- **P2** — PT6: approve a nugget with the KW adapter (fake in auto-apply mode) → `knowledge.publish` succeeds with KW's proposal id; KW received ops whose nodes carry `props.knowledge_lineage`, the instance/substructure target and KA's idempotency key; KA's proposal is APPLIED and lineage registered.
- **P3** — PT6: fake in approval mode → the publish operation stays `running` ("awaiting Knowledge Worker") until the fake approves, then `succeeded`.
- **P4** — a repeated publish replays the same KW proposal (idempotency key) — one KW proposal.
- **P5** — PT8: `KA_GRAMMAR_URL` against the fake → grammar loaded with the server's digests; the snapshot written; a changed digest under the same version is stale (fail closed).
- **P6** — PT1/PT8: with `KA_GRAPH_MODE=auto`, no `KA_ENTERPRISE_OS_ROOT` and no `KA_KW_URL`, KA starts on the memory adapter; with `KA_KW_URL` it picks the KW adapter; `knowledge_worker` is not imported in either case.
- **P7** — live flow: a fake KW over real HTTP + a KA server with `KA_KW_URL`, `KA_GRAMMAR_URL`, no EOS root: grammar loads, AgentX-style publish through /v1 reaches KW and succeeds after KW applies.

## Negative Test Cases (N1..N6)
- **N1** — KW refuses `STALE_BASE` → publish operation `failed` (`conflict`), KA proposal stays APPROVED, nothing applied in the shadow.
- **N2** — wrong token / missing scope → KW 403 `FORBIDDEN` → `failed` (`forbidden`).
- **N3** — KW unreachable → `failed` (`unavailable`, retryable); grammar URL unreachable → grammar not loaded (unresolved bindings, as without a directory), no crash.
- **N4** — same idempotency key, different body → `CONFLICT`.
- **N5** — rollback through the KW adapter → `PublishRefused("unsupported")`.
- **N6** — the graph_change covering tests (`test_plan05_publication.py`, `test_plan10_governance_decisions.py`, `test_plan12_eos_repin*` where runnable) pass unmodified.

## Plan totals

**Research points covered: 2 of 12 · Deliverables: 8 · Positive cases: 7 · Negative cases: 6 · Test cases total: 13 ·
Product tests served: 3 of 9 (PT1, PT6, PT8 turn green here).**

## Implementation Notes
- Written against `beae3f1` (plan-30).
