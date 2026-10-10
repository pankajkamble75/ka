# Research 05 - KA as an independent service behind AgentX: a versioned /v1 facade over the existing domain, durable operations, a capability manifest, typed human tasks, and HTTP contracts in place of private imports

Created: 2026-10-10 12:10 UTC
Source note: [AgentX-Integration-Technical-Requirements.md](../user-research/notes/AgentX-Integration-Technical-Requirements.md) (copied from `pankajkamble75/knowledge-acquisition` `docs/user-notes/`, commit 5cab618a, 2026-10-10)
Class: PRODUCT
Severity: MAJOR
Verdict: Aligned with corrections

## What this research is about

AgentX becomes the one front door for users and the orchestrator of work across services. The note asks Knowledge Acquisition to stand on
its own as a service that tells AgentX what it can do (a capability manifest), accepts AgentX's requests through versioned JSON APIs with
durable operation ids, hands human review back as typed tasks AgentX can render, emits durable events, and reaches the Data Platform and
Knowledge Worker only through their published APIs — without losing anything KA already does (governed nuggets, versions, conflicts,
provenance, the wiki).

The note's first instruction is to find the authoritative KA before building. **It is this repository** (`pankajkamble75/ka`, `/root/ka`):
the author confirmed it on 2026-10-10 when asked, and the code proves it (§What the code does today). The repository the note names,
`pankajkamble75/knowledge-acquisition`, is an SDLC-generated project whose default branch the note itself describes as "a project README,
not an independently verifiable KA service". Nothing is scaffolded; the work extends this repository.

## Why it matters

- AgentX cannot use KA today: there is no capability manifest, no version prefix, no operation id for long work, and no machine-readable
  review task. Every KA route is shaped for KA's own console (`ka/api.py`, 101 routes under `/api/knowledge-acquisition`).
- KA is not independent of Enterprise OS today: `EnterpriseOSGraphAdapter` imports `knowledge_worker.graph_store` and its `proposals`,
  `errors` and `graph_model.edges` modules (`ka/graph_adapter.py:387, 395, 513, 542, 567–568`), and the grammar is read from a checkout path
  (`ka/grammar.py:51–53`, `KA_ENTERPRISE_OS_ROOT`). The live service sets `KA_ENTERPRISE_OS_ROOT` in its systemd unit. The note's acceptance
  forbids both ("no imports from … Knowledge Worker … private code; no original Enterprise OS runtime dependency").
- A research mission runs for minutes (plan-17's first live mission: 508 s); AgentX must not hold an HTTP request open (note §4).

## What the code does today

**The domain is complete and stays.** Sources and versions with checksums and the physical port (`ka/ingestion.py`, `ka/physical.py`,
plans 18–24); governed nuggets through one pipeline (`ka/governance.py` — `ingest_candidate`, `propose_revision`, `decide`,
`request_retirement`); versioning and immutability (`ka/versioning.py:17`, `SEMANTIC_FIELDS`); conflicts (`ka/conflict.py`); lineage
(`ka/lineage.py`); search (`ka/search.py`); the wiki — computed articles, drafts, reconciliation, review, publication (`ka/wiki.py`,
`ka/wiki_markdown.py`, `ka/wiki_reconcile.py`, plans 25–28); research missions with background runs (`ka/research.py:374–390`,
`start_mission`, plan-17); the gap door (`POST /runtime/graph-gap`, `ka/api.py:1109`, now called by Enterprise OS plan-1033).

**Pieces the facade can reuse.**

| Note asks for | Exists as | Where |
|---|---|---|
| async long work with status | background research missions, RUNNING → COMPLETED/FAILED, polled | `ka/research.py:374–390`; `GET /research/missions/{id}` |
| durable events with replay | events outbox with `seq`, `GET /events?after=` | `ka/repository.py:291–297`; `ka/api.py:1280` |
| review / approve | `governance.decide` (APPROVE, REJECT, ACCEPT_NEW, MERGE, …); agents refused | `ka/governance.py:312` |
| revisions | `POST /nuggets/{id}/propose-revision`; wiki drafts → reconciliation | `ka/api.py:455`; `ka/wiki_reconcile.py` |
| conflict resolution | `GET /conflicts/{ref}` + decide outcomes | `ka/api.py` |
| publication | graph change proposals (`ka/graph_change.py`), wiki publication digest (plan-28), DP derived artefacts (plan-22) | |
| Data Platform client | HTTP client + fake + contract fixtures | `ka/data_platform/`, `docs/contracts/data-platform-v1-ka-subset.md` |
| outbox with retry | `ka/outbox.py` (plan-20) | |

**What is absent.** A `/v1` prefix; a capability manifest; an operation record that spans more than research missions; request/
correlation ids; idempotency keys on write calls (only the DP outbox has them); a typed error envelope (FastAPI's `{"detail": …}`); a
human-task object with a UI schema; a caller principal (Q1: `by` is free text, `ka/security.py:3–14`); an AgentX client; an HTTP path to
Knowledge Worker; OpenAPI published as a file.

## Architecture this research obeys

| decision | where | bearing on this |
|---|---|---|
| One governance pipeline; the LLM recommends, a person decides; agents cannot decide | `knowledge-acquisition.md` §4 | constrains R5 — AgentX decisions go through `decide`, never around it |
| Invariant 1: no runtime retrieval for answering | `ka/runtime_guard.py` | constrains R2 — `knowledge.search`/`read` are governance and research reads, labelled so; AgentX does not answer runtime questions from KA |
| Invariant 2: graph changes only as governed proposals with lineage | `knowledge-acquisition.md` §5 | constrains R7 — KW receives proposals; KA never mutates graphs |
| Q1 access policy (containment) and Q4 (identity, open) | `knowledge-acquisition.md` §10 | constrains R10 — an interim service-token-per-caller + principal header; real identity stays Q4 |
| Q19 the wiki article is a projection; edits are proposals | `knowledge-acquisition.md` §8a | constrains R2, R5 — `knowledge.revise` from a wiki draft and from a nugget reach the same pipeline |
| §11 Data Platform port, binding, outbox, events, derived artefacts | `knowledge-acquisition.md` §11 | constrains R9 — reconcile with the real DP, do not rebuild |
| Q7 (built in EOS plan-1033): found_new → KA; graph-model route; base digest on instance changes | `knowledge-acquisition.md` §9; EOS `data-layer.md` §8 | **extends it** — R7, R8 consume the EOS side over HTTP |
| An external-orchestrator contract (AgentX) | — | **silent — no document owns this; R11 proposes `knowledge-acquisition.md` §13 "KA as a service"** |

## Reading of the source note

| Claim in the note | Verdict | Evidence |
|---|---|---|
| `knowledge-acquisition` main is a README, not a verifiable service; find the authoritative KA | Confirmed | the active KA is `pankajkamble75/ka` (author, 2026-10-10); `knowledge-acquisition` has no deployment here |
| Preserve nugget store and wiki; they synchronise through governance | Confirmed — already true | wiki reconciliation → `ingest_candidate` / `propose_revision` (`ka/wiki_reconcile.py`) |
| KA owns ingest, versions, nuggets, wiki, review, conflicts, provenance, search, publication | Confirmed | modules above |
| DP owns bytes, storage, connectors; KA accesses via DP API | Partly built | DP port + client exist (plans 18–24); connectors stay in KA until DP's registry exists (Q15, 2026-10-09) |
| KW owns graphs; KA publishes through a versioned interface | Contradicted today | private imports (`ka/graph_adapter.py:387–568`) |
| No original EOS runtime dependency | Contradicted today | `KA_ENTERPRISE_OS_ROOT` in the live unit; grammar from a checkout path |
| Proposed `/v1` routes are new contracts | Confirmed | none exist; each maps onto an existing service (§1) |
| Long tasks must not hold HTTP open | Partly built | missions run in background (plan-17); acquisitions from uploads/links are synchronous today |

## The research

### 1. Adopt AgentX's contract; a facade, not a second implementation

AgentX's side is fixed as **PROPOSED v1** (`pankajkamble75/agentx` `docs/contracts/agentx-services-v1.md`, JSON Schemas generated from
`agentx/contracts.py`, fixture `agentx/mocks/service.py`; received from the AgentX session on 2026-10-10 — that repository is not pushed yet,
so its message is the citation until it is). KA **adopts it** rather than publishing a competing contract. Its shape:

- AgentX registers the *service* (`base_url` may be any prefix — `http://127.0.0.1:8011/api/knowledge-acquisition`); capabilities are
  **pulled** from `GET {base}/v1/capabilities` → `{service_id, schema_version:"1", capabilities:[CapabilityDescriptor]}` (or pushed with
  `PUT {agentx}/api/v1/services/{id}/capabilities`). A missing id on a later sync is deregistration; a new MAJOR version makes planned runs
  fail `stale_version`. No heartbeat: AgentX polls `GET {base}/healthz` → `{status: ok|degraded|down, service_id, version, checks}`.
- **One invoke endpoint**: `POST {base}/v1/capabilities/{capability_id}/invoke` with `InvokeRequest {schema_version, request_id,
  idempotency_key, correlation_id, capability_version, input, caller {service_id, user, permissions[]}, callback_url}` and headers
  `Authorization: Bearer`, `X-Service-Id`, `X-Request-ID`, `X-Correlation-ID`, `X-Schema-Version`, `Idempotency-Key`. Answer:
  `OperationState {operation_id, capability_id, status: accepted|running|awaiting_input|succeeded|failed|cancelled|timed_out, progress 0..1,
  message, result, error, interaction, references}` — terminal for `sync`, polled at `GET {base}/v1/operations/{id}` for `async`; cancel at
  `POST …/cancel`; human input at `POST …/input {interaction_id, values, submitted_by}`. Scope travels in `input`.
- **Errors**: `{"error": {code, message, retryable, details}}` with AgentX's error classes (`unavailable, timeout, bad_request,
  schema_invalid, unauthorized, forbidden, not_found, conflict, stale_version, rate_limited, internal, protocol, unsupported, cancelled`).
- **Events**: AgentX polls operations; KA may POST `OperationEvent {service_id, operation}` to the `callback_url` it was given.

Each capability is a handler over a service that already exists; no domain rule moves:

| capability | mode | handler calls |
|---|---|---|
| `knowledge.acquire` | async | `ingestion.paste/link/write_note` (+ `upload` by Data Platform reference) → `governance.extract_from_source` (candidates); `kind=research` → `research.start_mission`; `kind=gap` → `runtime_guard.graph_gap_detected` |
| `knowledge.search` | sync | `SearchService.search` (governed nuggets) + `WikiService.search` (articles) |
| `knowledge.read` | sync | `nugget_detail` + lineage trace (provenance chain) or `WikiService.article` + evidence |
| `knowledge.revise` | sync | `propose_revision` (nugget), wiki draft + submit (article), `request_retirement` (`retire=true`) |
| `knowledge.review` | async, `awaiting_input` | a task over a pending candidate/wiki proposal → `governance.decide` / wiki publish |
| `knowledge.resolve_conflict` | async, `awaiting_input` | the conflict view → `decide` with KEEP_EXISTING / ACCEPT_NEW / MERGE / BOTH_VALID_ADD_CONTEXT |
| `knowledge.publish` | async | graph change proposal approve + apply (Q3: a named person — `requires_approval=true`) or wiki publish; `succeeded` only when applied |

The note's own proposed paths (`POST /v1/acquisitions`, `GET /v1/knowledge/search`, …) are kept as **thin aliases** that build an
`InvokeRequest` and call the same handler, so both shapes reach one implementation. The console and its 101 routes stay as they are.

**The source-into-target mapping AgentX asked about** (`{structure_id, instance_id, leaf_id} → {mapped_into, refusals}`) is part of
`knowledge.acquire`: an optional `target` in the input scopes extraction to that instance/leaf. But KA cannot report `mapped_into` at
acquisition time — Invariant 2 forbids a graph change without governance. The output therefore reports `candidates` (refs awaiting review)
and `refusals` (statements the extractor dropped, with reasons); the eventual `mapped_into` is a `knowledge.publish` result.

### 2. Operations: one record for every long thing

KA stores AgentX's `OperationState` as its own `Operation` record (one JSON per object), plus `idempotency_key`, `request_hash`,
`principal`, `correlation_id`, linked `mission_id` / `request_id` / proposal ids. Async handlers run on a worker thread (plan-17's
pattern); a research acquisition mirrors mission progress into `progress` (0..1) and `message`. The same `Idempotency-Key` with the same
input returns the existing operation and never executes twice; a different input → `conflict`. Cancellation: honoured while `accepted`
and for research missions between agents; otherwise `conflict` with `details.reason = "not_cancellable"`. "Do not claim success until the
owning service confirms it": a publication operation stays `running` until the graph proposal is APPLIED (or Knowledge Worker confirms,
R7). When `callback_url` is given, every status change is POSTed as an `OperationEvent` through the plan-20 outbox (retry, dead-letter,
the operation id + status as idempotency key).

### 3. The capability descriptors

Seven `CapabilityDescriptor`s in AgentX's exact shape (extra keys are refused by AgentX): `id`, `version` (`1.0.0`), `title`,
`description`, `input_schema` / `output_schema` (JSON Schema 2020-12, written by hand from the pydantic models so they are stable),
`permissions` (the END-USER permission AgentX checks — `knowledge.acquire`, `knowledge.read`, `knowledge.revise`, `knowledge.review`,
`knowledge.publish`), `discovery {category: "knowledge", tags, keywords, examples, processes}`, `health_endpoint: "/healthz"`,
`timeout`, `retry`, `invocation {endpoint: "/v1/capabilities/{capability_id}/invoke", mode}`, `idempotent`, `requires_approval`
(`true` only for `knowledge.publish` — Q3), optional `ui_schema`, `deprecated: false`. Registration is pull-first: AgentX reads
`/v1/capabilities`; with `KA_AGENTX_URL` and `KA_AGENTX_SERVICE_ID` set KA also pushes the list on start and on demand (`PUT
{agentx}/api/v1/services/{id}/capabilities`) through the outbox.

### 4. Human tasks as AgentX interactions

`knowledge.review` and `knowledge.resolve_conflict` start an operation that moves at once to `awaiting_input` with
`interaction {interaction_id, prompt, ui_schema}` in **AgentX's declarative UI-schema** (forms of typed fields, views bound to the
operation's data, actions; data only — no markup, templates or `javascript:` URLs). The form carries the candidate statement (readonly),
its evidence and conflicts (views), the allowed outcomes (select), a reason (textarea) and, for MERGE, a merged statement. `POST
…/input {interaction_id, values, submitted_by}` → `governance.decide(by=submitted_by)`; research-agent ids are refused exactly as today;
the operation then `succeeded` with the resulting version refs. KA's console keeps working in parallel: a decision made in either place
resolves the other (an interaction whose candidate is no longer open completes with `message: "decided elsewhere"`). A listing of open
review work (`GET /v1/tasks`) lets AgentX discover what to start review operations for.

### 5. Caller identity and scope (interim, under Q4)

AgentX authenticates with a service bearer token (`KA_AGENTX_TOKEN`, distinct from the console's `KA_ACCESS_TOKEN`; AgentX keeps it as
`AGENTX_KNOWLEDGE_ACQUISITION_TOKEN`). The end user is `caller.user` (and `submitted_by` on input); AgentX has already checked
`caller.permissions` against each descriptor's `permissions`, and KA re-checks that the needed one is present. Scope (tenant / instance /
domain) is in `input` per each schema; the tenant must equal `KA_TENANT_ID`. This is the Q1/Q4 interim — a trusted service asserts the
user — stated as such.

### 6. Events

AgentX polls operations, so KA's durable events are already delivered through operation state plus optional callbacks (§2). KA's own
`/events` outbox stays the full record; a `GET /v1/events?after=` view renames KA events into the note's vocabulary
(`knowledge.review.required`, `knowledge.revision.proposed`, `knowledge.conflict.detected`, `knowledge.publication.approved`,
`knowledge.publication.completed`, `knowledge.acquisition.completed`) with `event_id`, `schema_version: "ka.v1"` and provenance, for any
consumer that wants a replayable feed.

### 7. Knowledge Worker over HTTP, not by import

Knowledge Worker is now its own service (`pankajkamble75/knowledge-worker`, extracted from enterprise-os at `f5f987a`; backend
`http://127.0.0.1:8101`, `/healthz`, API under `/v1`; told to KA by its session on 2026-10-10 — not yet pushed). It has **no HTTP intake for
KA**; `GraphStore.proposals` and `propose_instance_change` (with plan-1033's `base_digest` / `idempotency_key`) are carried in Python only.
Its session asked KA to publish the intake contract under KW's v1 conventions (`docs/contracts/agentx-knowledge-worker-v1.md` §2–§5 on the KW
side): bearer service token with a new scope (`graph-changes:propose`), `X-Correlation-ID`, the envelope `{contract_version, correlation_id,
status, result, error {status, code, message, retryable, detail}, provenance}`.

KA's side, published as `docs/contracts/knowledge-worker-v1-ka.md` with an executable fixture and an in-repo fake:
`POST /v1/graph-changes {target {kind: instance|substructure, id, base_digest | base_version}, ops [ChangeOp with
props.knowledge_lineage on every node/edge], reason, actor, knowledge_refs [nugget refs + decision ids], idempotency_key}` →
`{proposal_id, status: awaiting_approval|applied|refused}`; errors `STALE_BASE`, `INVALID_REQUEST`, `UNKNOWN_INSTANCE`, `FORBIDDEN`,
`CONFLICT`; outcome by polling `GET /v1/graph-changes/{proposal_id}` → `{status, applied_digest?, lineage}`. KW decides the update.

On KA's side the publication target becomes `KnowledgeWorkerHTTPAdapter` (a `GraphAdapter`) behind `KA_KW_URL` / `KA_KW_TOKEN`: KA's graph
change proposal (`ka/graph_change.py`, protected) is unchanged; the adapter's `validate_change` / `publish` speak HTTP, and an APPLIED
outcome is what moves KA's proposal to applied. `EnterpriseOSGraphAdapter` stays only as an explicit local mode
(`KA_GRAPH_MODE=eos-local`), off by default, so KA starts with no Enterprise OS checkout. The in-memory adapter remains the standalone default.

Reverse direction, already live: KW calls KA's `POST /runtime/graph-gap` with `KW_KA_TOKEN` (carried `governance/ka_client.py`). KW's preview
adapter also expects `POST /v1/knowledge/search {query, instance_id?, domain_id?, limit} → {results[], version}`; KA serves that path as one
of the thin aliases of `knowledge.search` (R2).

### 8. The grammar over HTTP

KW serves the grammar and process-type tables with sha256 digests at `GET /v1/graph-model` (bearer token with `graphs:read`), and every
domain/instance digest at `GET /v1/graph-versions`. KA's `GrammarRegistry` gains `KA_GRAMMAR_URL` (+ `KA_KW_TOKEN`): fetch, verify the digests,
write the snapshot as today, fail closed on drift; the directory path stays as a fallback. With `KA_GRAMMAR_URL` set, KA needs no Enterprise
OS checkout for grammar.

### 9. The real Data Platform differs from KA's fake

The Data Platform session (`pankajkamble75/dataplatform`, `/root/dataplatform`, base `http://127.0.0.1:8100`, `schemas/openapi.json`,
`docs/architecture/ka-adapter-contract.md`, reference client `src/data_platform/integrations/ka/client.py`) reported on 2026-10-10 how its
real `/v1` differs from KA's contract (`docs/contracts/data-platform-v1-ka-subset.md`, built 2026-10-09 against a fake):

| KA today | real DP |
|---|---|
| staging body `{asset_type, content_type, owner, visibility}` + `Idempotency-Key` | `{tenant_id, sha256, size_bytes, mime_type, type, scope, tags{domain_id/instance_id/team_id}, asset_id?, provenance?, format?}`; owner = authenticated principal; no key at staging; response carries `content_url`, `commit_url` |
| commit errors `checksum_mismatch`, `idempotency_conflict` | `422 invalid_contract`, `409 conflict` (and `409 conflict` + `details.state=expired` after 7 days); `Idempotency-Key` REQUIRED on commit |
| `POST /v1/assets/derived` `{asset_type, parent ids, provenance, payload_b64}` | `POST /v1/derived-assets {tenant_id, type: extracted_text|nugget|derived, mime_type, parent_asset_version_ids[], content_base64, scope?, metadata?, evidence[]}`; provenance inherited |
| asset families `source_document / extracted_text / nugget_version` | types `document / extracted_text / nugget` |
| `Authorization: Bearer` + `X-KA-Tenant`, `X-KA-Owner` | loopback mode: `X-Principal-Id`, `X-Tenant-Id`, `X-Scopes`, `X-Teams/Domains/Instances`; `static` mode: Bearer only |
| `GET /v1/events` (six types) | **none yet** — a tenant feed is coming; do not build against it |
| — | `POST /v1/knowledge-bindings {tenant_id, ka_source_id, ka_source_version, dp_asset_version_id}`, `POST /v1/search`, `GET /v1/lineage/{id}` |
| error `{error: {code, …}}`-ish | `{code, message, correlation_id, retryable, details}` |

KA's DP client, store and fake are adapted to the real contract (the fake becomes a faithful double of it; the old fixture is kept as
history), `knowledge-bindings` is called on every commit, and inbound event polling stays off until the DP feed exists. The port, binding,
outbox and derived-artefact design (§11, plans 18–24) does not change.

### 10. Coordination with AgentX, Data Platform, Knowledge Worker

On 2026-10-10 KA asked each peer session for its contract (AgentX: registration, invocation, task UI schema, events; Data Platform: whether
its API matches `data-platform-v1-ka-subset.md`; Knowledge Worker: an HTTP intake for approved changes). Until they answer, KA builds to its
own published contracts with fakes at the wire — exactly how the DP integration was built — and records every assumption in the contract
files so each peer can adopt or amend. A contract change on their side is an adapter change on ours, not a redesign.

## Where I differ

1. **The repository.** The note targets `knowledge-acquisition`; the author confirmed on 2026-10-10 that the active KA is `pankajkamble75/ka`,
   which the note's own §1 anticipates. Committing here satisfies "commit changes only to this [KA] repository".
2. **Connectors.** The note says DP owns connectors; the author's Q15 (2026-10-09) keeps KA's connectors until DP's registry exists. Kept.
3. **`/v1/knowledge/search` is not a runtime answer path.** Invariant 1 stands; the capability is described as a governance/research read.
4. **"KA runs independently"** is already true for KA's own process; what is missing is independence from EOS *code* (R7, R8). Packaging is
   a `pyproject` script and a systemd/Docker recipe, not a re-platforming.

## Open questions

- AgentX's contract is PROPOSED v1 and unpushed; when its schemas land, KA's tests switch from the message to the files.
- Knowledge Worker exists as a service with no KA intake yet; KA publishes the intake contract and KW implements it (its session agreed, 2026-10-10).
- Q4 identity provider (unchanged; R10 is its interim).

## What this does not cover

AgentX's own implementation; any change to the Enterprise OS repository (the author: keep it unchanged); moving connectors to DP (Q15).
Phasing belongs to `create-implementation-plan`.

## Research points (12)

| # | Research point | Kind | Class | Severity | Where argued |
|---|---|---|---|---|---|
| R1 | The active KA is `pankajkamble75/ka` (author, 2026-10-10); write `docs/integration/source-inventory.md` (commit, routes, stores, wiki UI, nugget lifecycle, connectors) and the ownership/dependency map | decide | PRODUCT | MAJOR | §What this is about |
| R2 | Adopt AgentX's PROPOSED v1: `GET /healthz` (AgentX shape), `GET /v1/capabilities`, `POST /v1/capabilities/{id}/invoke` (InvokeRequest → OperationState), AgentX's error envelope and classes, request/correlation/idempotency headers; seven capability handlers over existing services; the note's `/v1/acquisitions` etc. as thin aliases; console routes unchanged | build | PRODUCT | MAJOR | §1 |
| R3 | Durable `Operation` records in AgentX's `OperationState` shape: async worker threads, `GET /v1/operations/{id}`, cancel where safe, idempotency (never execute twice), success only on the owning service's confirmation, `OperationEvent` callbacks through the outbox | build | PRODUCT | MAJOR | §2 |
| R4 | Seven `CapabilityDescriptor`s in AgentX's exact shape (JSON Schema 2020-12 in/out, end-user permissions, discovery, timeouts, retry, invocation mode, `requires_approval` for publish); pull registration plus optional push (`KA_AGENTX_URL`, `KA_AGENTX_SERVICE_ID`); a fake AgentX in tests | build | PRODUCT | MAJOR | §3 |
| R5 | Review and conflict resolution as `awaiting_input` interactions in AgentX's declarative UI schema; `POST …/input` → `governance.decide(by=submitted_by)`; agents refused; console decisions resolve them; `GET /v1/tasks` lists open review work | build | PRODUCT | MAJOR | §4 |
| R6 | `GET /v1/events?after=` — KA's outbox under the note's event names with event id, schema version and provenance | build | PRODUCT | MINOR | §6 |
| R7 | Publish `docs/contracts/knowledge-worker-v1-ka.md` (`POST /v1/graph-changes`, `GET /v1/graph-changes/{id}`, KW's envelope and token scope) + fixture + fake; `KnowledgeWorkerHTTPAdapter` behind `KA_KW_URL`; `EnterpriseOSGraphAdapter` only under `KA_GRAPH_MODE=eos-local`, off by default — no EOS import by default | build | PRODUCT | MAJOR | §7 |
| R8 | Grammar over HTTP (`KA_GRAMMAR_URL` → KW `GET /v1/graph-model`, `graphs:read` token, digest-verified, snapshot, fail closed) | build | PRODUCT | MAJOR | §8 |
| R10 | Interim caller identity: `KA_AGENTX_TOKEN` + `X-Principal`, `X-Tenant`, `X-Scope`; principal is the decider on `/v1`; Q4 unchanged | build | PRODUCT | MAJOR | §5 |
| R9 | Adapt KA's DP client, store and fake to the real Data Platform `/v1` (staging body, commit key and codes, `/v1/derived-assets`, types, auth headers, error envelope) and call `/v1/knowledge-bindings`; inbound polling off until DP's feed exists | fix | PRODUCT | MAJOR | §9 |
| R11 | Architecture §13 "KA as a service" + `docs/integration/` (deployment, settings, OpenAPI file, examples, failure handling); README section | build | PRODUCT | MINOR | §Architecture |
| R12 | AgentX mock integration tests + a real two-process run (KA + fake AgentX/KW over HTTP) proving independent startup with no EOS checkout and unchanged governance | build | TEST INFRASTRUCTURE | MINOR | §1–§9 |

**Total research points: 12.** 10 `build`, 1 `fix`, 1 `decide`.

**Class and severity split (`Q231`):** 11 `PRODUCT`, 1 `TEST INFRASTRUCTURE`; 0 `CRITICAL`, 9 `MAJOR`, 3 `MINOR` (R9 rose to MAJOR — KA's DP client does not match the real API; R6 fell to MINOR — AgentX polls operations).

**Coverage of the source note (`Q199`):** covers all seven sections (source review, ownership, independent service, AgentX/UI, contracts,
steps 1–7, acceptance 1–6). Connectors' ownership is kept with KA per Q15 (named in §Where I differ).

## Product tests (8)

| # | Product test | Proves | Runnable today? |
|---|---|---|---|
| PT1 | KA starts with no Enterprise OS checkout and no `KA_ENTERPRISE_OS_ROOT`, serves `/healthz` and `/v1/capabilities` in AgentX's exact shape, and a (fake) AgentX pulls and accepts all seven descriptors | R4, R7, R8, R12 | no |
| PT2 | AgentX initiates an acquisition, gets an operation id at once, polls it to `succeeded`, and reads the produced candidates | R2, R3 | no |
| PT3 | AgentX searches and reads governed knowledge (a nugget and a wiki article) with provenance | R2 | no |
| PT4 | AgentX starts a review, receives `awaiting_input` with a valid UI schema, submits APPROVE as a named user; the nugget becomes ACTIVE through `decide`; an agent user is refused | R5, R10 | no |
| PT5 | A revision through `/v1` and an edit through the wiki reach the same governance pipeline; versions, conflicts and provenance unchanged | R2, R5 | no |
| PT6 | A publication operation stays `running` until Knowledge Worker (fake over HTTP) confirms, then `succeeded` with lineage; KW receives only approved, versioned references | R3, R7 | no |
| PT7 | Every v1 event is replayable by `after`, carries an event id, schema version and provenance, and a duplicate delivery is idempotent | R6 | no |
| PT8 | No module under `ka/` imports `knowledge_worker` unless `KA_GRAPH_MODE=eos-local`; the grammar loads from `KA_GRAMMAR_URL` with digest checks | R7, R8 | no |

| PT9 | With `KA_STORAGE_BACKEND=data_platform` against the real Data Platform `/v1` (or its faithful double), an upload commits, a knowledge binding is created, and a nugget version lands as a `nugget` derived asset | R9 | no |

**Total product tests: 9.** None runnable today; they wait on the plans this research implies (about five).
