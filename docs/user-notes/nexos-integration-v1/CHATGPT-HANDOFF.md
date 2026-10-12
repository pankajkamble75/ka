# NEXOS — ChatGPT architecture review handoff: Knowledge Acquisition (KA)

**Repository:** `pankajkamble75/ka` · **tested implementation:** `e360f89` (plan-34) · **written:** 2026-10-11 ~21:10 UTC on `srv1886827`
· **scope:** report only. No functionality was added, and no running service or other repository was changed while writing this.

Facts below are **verified** (inspected or measured today) unless marked *assumption*. Evidence links are relative to this folder.


## Update 2026-10-12 ~01:05 UTC — ChatGPT priority 1 done: KA no longer answers on the public IP

Ordered by the ChatGPT review (relayed by AgentX) and approved by KA's author. Done in this order:

1. **Rebind (plan-35).** A new setting, `KA_BACKEND_HOST` (comma list; default `0.0.0.0` unchanged), is set in KA's gitignored `.env` to
   `10.77.0.2,127.0.0.1`, with `KA_PUBLIC_BASE_URL=http://10.77.0.2:8011`. The service was restarted. Listeners are now **`10.77.0.2:8011`**
   (WireGuard) and **`127.0.0.1:8011`** (loopback) only. Auth is unchanged. Rollback: [`ROLLBACK-bind.md`](ROLLBACK-bind.md). The previous
   `.env` is backed up outside the repository (mode 600).
2. **Verified** ([`evidence/bind-vpn-only.txt`](evidence/bind-vpn-only.txt)): over `10.77.0.2` with AgentX's bearer, `/healthz` → 200 and
   `/v1/capabilities` → 200 (6 capabilities); without a token → 401; loopback `/healthz` → 200. **`2.25.98.235:8011` → connection refused
   (curl exit 7).** That was checked from this host; AgentX confirms from `srv2050509`. `/v1/screens` launch URLs now use
   `http://10.77.0.2:8011`.
3. **Token handover (operator-controlled, as decided).** AgentX's one-time receiver was not used; it is shut down. `KA_AGENTX_TOKEN` is
   written to **`/root/ka-agentx.token`** on `srv1886827` (mode 600, root). The operator copies it over SSH to
   `srv2050509:/root/nexos-operator/ka.token`. The value is not in this repository, any log or any message.
4. **Not yet done, by design:** `KA_AGENTX_URL=http://10.77.0.1:8765` (push registration and callbacks) is set only after the operator
   confirms AgentX holds the token; a push before that would be refused and dead-lettered. AgentX's gateway answers over WireGuard
   (`GET http://10.77.0.1:8765/healthz` → 200). Knowledge Worker's WireGuard listener (`10.77.0.1:8101`) is not up yet, so `knowledge.publish`
   stays unavailable.

Effect on §6: gap #2 (public plain HTTP) is **resolved**. Traffic between the VPSes runs over WireGuard; HTTP inside the tunnel is
encrypted by WireGuard. Gap #1 (no private network) is **resolved at the network layer** and now waits on credentials and KW's listener.

This repository has a single ChatGPT file, this one (`CHATGPT-HANDOFF.md`). The "four CHATGPT-* files" AgentX mentions are presumably the
other services' files plus this one.

---

## 1. Executive status

**Implemented and working (verified)**
- KA runs as an independent service: `enterprise-os-ka` (systemd) on `srv1886827`, `0.0.0.0:8011`, prefix `/api/knowledge-acquisition`,
  running the `e360f89` code (service started 2026-10-11 20:14:52 UTC). `/healthz` → `status: ok`.
- AgentX `agentx-services/v1` surface: capability discovery, invoke, durable operations, status, human input, cancel, typed errors,
  idempotency, tasks, events, push registration, callbacks and a screen manifest. **15/15 live conformance checks** pass against AgentX's
  vendored JSON Schemas ([`api-matrix.md`](api-matrix.md)).
- Governance is unchanged and enforced: one `decide` pipeline; only a named person approves; agents and anonymous callers are refused;
  versioned nuggets; provenance; the computed wiki.
- Honest capability set: 6 capabilities live; `knowledge.publish` is withheld because no Knowledge Worker is attached.
- Data Platform `/v1` client verified **8/8 against the real Data Platform service** ([`evidence/dp-real.txt`](evidence/dp-real.txt)).
- Real LLM (Anthropic) and real web research (Brave) verified through `/v1` on 2026-10-11.

**Partially implemented**
- Knowledge Worker publication: client, adapter, contract and fixtures are built and aligned with KW's `knowledge-worker/v1` envelope, but
  only **MOCK**-tested; the real KW is unreachable from this host.
- The live service uses local byte storage, not the Data Platform, although a real Data Platform is now running on this host (`:8100`).
- Specialist UI: preserved and exposed through `/v1/screens`. There is no dedicated publications list screen, and no embedding
  (`embed_url: null`).

**Missing or blocked**
- **BLOCKED:** cross-VPS reachability. AgentX (`srv2050509`) and KA (`srv1886827`) have no private network, and KA serves plain HTTP.
- **BLOCKED:** a real Knowledge Worker round trip, for the same reason, plus KA's KW token isn't on this host.

**Overall readiness:** KA's side is **ready at G0/G1** and verified live. G2–G4 cross-service checks wait on infrastructure, not on KA code.

---

## 2. Current architecture

| module | responsibility |
|---|---|
| `ka/governance.py` (protected) | the single approval pipeline (`ingest_candidate`, `decide`, `propose_revision`) |
| `ka/repository.py`, `ka/model.py` | file-per-object JSON store (`ka_storage/`), 25 collections, `events.jsonl`, `audit.jsonl` |
| `ka/ingestion.py`, `ka/extraction.py`, `ka/llm/` | sources, versions, evidence, extraction (Anthropic or stub) |
| `ka/research.py`, `ka/discovery.py`, `ka/search.py` | research missions, internet discovery (Brave), explicit discovery search |
| `ka/wiki*.py` | articles computed from governed nuggets; edits go through governance |
| `ka/graph_change.py` (protected), `ka/graph_adapter.py` | governed graph change proposals; adapters: in-memory shadow, Knowledge Worker over HTTP, legacy Enterprise OS import |
| `ka/agentx/` | the AgentX v1 surface: capabilities, operations, interactions, tasks, events, registration, availability, screens, vendored schemas |
| `ka/knowledge_worker/` | KW client and wire-level fake (KA's intake contract) |
| `ka/data_platform/` | DP client and store (real `/v1` and the superseded ka-subset), outbox, derived assets |
| `ka/console/` | the specialist UI (Add, Nuggets, Browse, Processes, Dashboard, Images, Wiki) |

**APIs exposed to other services** (OpenAPI: [`../../integration/openapi-v1.json`](../../integration/openapi-v1.json); base
`http://<host>:8011/api/knowledge-acquisition`):

| path | purpose | auth |
|---|---|---|
| `GET /healthz` | health in AgentX's `Health` shape plus `checks.capabilities_unavailable` | AgentX token or console token |
| `GET /v1/capabilities` | the `CapabilityList` (schema_version "1") | AgentX token |
| `POST /v1/capabilities/{id}/invoke` | `InvokeRequest` → `OperationState`; `Idempotency-Key` honoured | AgentX token |
| `GET /v1/operations/{id}`, `POST …/cancel`, `POST …/input` | poll, cancel, human input `{interaction_id, values, submitted_by}` | AgentX token |
| `GET /v1/tasks` | open human review work | AgentX token |
| `GET /v1/events?after=` | the note's events, `schema_version: ka.v1`, stable `event_id` | AgentX token |
| `GET /v1/screens` | specialist screen manifest in KW's shape | AgentX token |
| `POST /v1/capabilities/register` | push the capability list to AgentX | AgentX token |
| `POST /v1/knowledge/search` | KW preview adapter shape `{results[], version}` | AgentX token |
| aliases `/v1/acquisitions`, `/v1/knowledge/{id}[/revisions\|/review]`, `/v1/publications` | the requirements note's paths, mapped onto the same capabilities | AgentX token |
| `POST /runtime/graph-gap` | KW → KA `found_new` gaps | console token (KW holds it as `KW_KA_TOKEN`) |

**Dependencies on other components:** Knowledge Worker (graph changes, grammar), Data Platform (bytes, derived assets), AgentX
(orchestration, human tasks UI), Anthropic and Brave (extraction, research). None is required for KA to start.

**Deployment (verified):** systemd `enterprise-os-ka`, `python -m ka serve` from `/root/ka` with the gitignored `/root/ka/.env`. Bound to
`0.0.0.0:8011`; host firewall inactive. Live settings: provider `anthropic`; graph mode `memory`; storage `local`; console access policy
`token` (callers on this machine pass, others need a bearer); dedicated `KA_AGENTX_TOKEN` set. Secrets are not reproduced here.

**Other services seen on this host (read-only observation):**

| port | service |
|---|---|
| 127.0.0.1:8100 | Data Platform (`/root/dataplatform`), `status ok` |
| 127.0.0.1:8020 | final-sdlc (`/root/sdlc-final`), `status ok` |
| 127.0.0.1:8765 | an `sdlc-orchestrator` browser, **not AgentX** |
| 127.0.0.1:5176 | the archived Enterprise OS console |

AgentX itself runs on `srv2050509`.

**Tested SHA:** `e360f89`. Live evidence was taken at `e360f89`-equivalent code: the working tree was committed unchanged.

---

## 3. Integration status

| service | direction / contract | state | evidence and notes |
|---|---|---|---|
| **AgentX** | AgentX → KA, `agentx-services/v1` (schema_version "1"), endpoints above | **BLOCKED** (live) · **MOCK** (11/11) | AgentX on `srv2050509` can't reach `srv1886827:8011`: no private network or TLS. KA's surface is LIVE-verified against AgentX's schemas from this host (15/15). A two-process journey with a fake AgentX passed 11/11. AgentX confirmed both shapes (`@118c994`) |
| AgentX | KA → AgentX: push `PUT {agentx}/api/v1/services/knowledge-acquisition/capabilities`; callbacks `POST {callback_url}` | **MOCK** · BLOCKED (live) | through KA's retrying outbox; verified with a fake AgentX |
| **Knowledge Worker** | KA → KW: `POST /v1/graph-changes`, `GET /v1/graph-changes/{id}`, `GET /v1/graph-versions`, `GET /v1/graph-model` (`knowledge-worker/v1` envelope; contract `docs/contracts/knowledge-worker-v1-ka.md`) | **MOCK** (7/7, 8 fixtures) · **BLOCKED** (live) | KW reports the intake live on its host (`knowledge-worker@064bdf4`); unreachable from here, and KA's token isn't on this host |
| Knowledge Worker | KW → KA: `POST /runtime/graph-gap`, `POST /v1/knowledge/search` | **LOCAL** (tests) · BLOCKED (live) | |
| **Knowledge Acquisition** | this service | **LIVE** | 15/15 conformance on the running service; restart recovery verified |
| **Data Platform** | KA → DP `/v1`: `POST /v1/assets/uploads`, `PUT content_url`, `POST commit_url` (Idempotency-Key), `POST /v1/knowledge-bindings`, `GET /v1/assets/{id}/versions/{n}/content`, `POST /v1/derived-assets` (contract `docs/contracts/data-platform-v1-real.md`) | **LIVE** (8/8, real DP code `d5eefbd`, a separate process) | the test started its own DP instance on `:8110` with a fresh root. The standing DP on `:8100` is **not connected** to the live KA (KA uses local storage) |
| **final-sdlc** | none | **NOT IMPLEMENTED** | KA's requirements give it no final-sdlc integration; operational apps come through AgentX |

---

## 4. Capabilities available

| id | mode | timeout (operation) | permission | readiness | limitations |
|---|---|---|---|---|---|
| `knowledge.acquire` | async | 600 s | `knowledge.acquire` | **live** | kinds: text, note, link, research, gap. Research needs the internet gate and Brave (budgeted). Returns candidates, never graph mappings |
| `knowledge.search` | sync | 30 s | `knowledge.read` | **live** | governed, ACTIVE knowledge plus the wiki; explicit discovery read (Invariant 1) |
| `knowledge.read` | sync | 30 s | `knowledge.read` | **live** | a nugget with versions and evidence, or a wiki article |
| `knowledge.revise` | sync | 30 s | `knowledge.revise` | **live** | creates a new candidate version (or a retirement request); never edits a governed version |
| `knowledge.review` | async | 7 days | `knowledge.review` | **live** | `awaiting_input` with AgentX's UiSchema; only a named person decides |
| `knowledge.resolve_conflict` | async | 7 days | `knowledge.review` | **live** | ACCEPT_NEW / KEEP_EXISTING / MERGE / … by a person |
| `knowledge.publish` | async | 7 days | `knowledge.publish` | **unavailable on the live service** | needs a Knowledge Worker (`KA_KW_URL`, `KA_KW_TOKEN`). `requires_approval`; succeeds only when KW reports `applied` |

---

## 5. Tests and evidence

| what | counterpart | result | evidence |
|---|---|---|---|
| full automated suite (stub LLM), including the Enterprise OS adapter suites | in-process | **510 passed, 5 skipped**, 0 failed (today) | skips: 3 × the Enterprise OS checkout isn't reachable; 1 × live Brave search test without the key in the test env; 1 × M365 app registration not provided |
| suite as recorded with the evidence | in-process | 499 passed, 2 skipped | [`evidence/suite.txt`](evidence/suite.txt) |
| plan-34 NEXOS tests | in-process, MOCK KW | 12/12 | [`evidence/plan34-tests.txt`](evidence/plan34-tests.txt) |
| live conformance of the running KA | **LIVE** | 15/15 (first run 14/15: a `/healthz` auth defect, fixed) | [`api-matrix.md`](api-matrix.md), [`evidence/live-*.json`](evidence/) |
| restart recovery | **LIVE** | pass | [`evidence/restart-recovery.json`](evidence/restart-recovery.json) |
| KA ↔ Data Platform | **LIVE** (real DP code) | 8/8 | [`evidence/dp-real.txt`](evidence/dp-real.txt) |
| real Anthropic extraction through `/v1` | **LIVE** (external API) | 12/12 | commit `b3ecb78`; `FLOW_LIVE_LLM=1 e2e/plan33_two_process_flow.py` |
| real research (Brave + Anthropic), 58 candidates, all pending review | **LIVE** (external APIs) | pass | commit `295f185`; `e2e/live_keys_research_flow.py` |
| AgentX journey (register, acquire, review, publish, events) | **MOCK** AgentX + MOCK KW | 11/11 | [`evidence/two-process-mock-peers.txt`](evidence/two-process-mock-peers.txt) |
| publication waits for KW `applied` | **MOCK** KW | 7/7 | [`evidence/kw-publish-mock-kw.txt`](evidence/kw-publish-mock-kw.txt) |
| specialist screens | **LIVE** console | 6/6 rendered, 0 JS errors | [`screenshots/index.md`](screenshots/index.md) |

**End-to-end scenarios completed:** acquisition → human review → approval → publication to KW (**MOCK** KW); rejected change; conflicting
versions; duplicate delivery; missing Data Platform; restart recovery (LIVE). **Not completed:** any scenario through the real AgentX or the
real Knowledge Worker. The source audit is in [`source-audit.md`](source-audit.md), the test detail in [`test-results.md`](test-results.md),
and plan-34's account in [`implementation-report.md`](implementation-report.md).

---

## 6. Gaps and technical debt

| # | issue | class | severity |
|---|---|---|---|
| 1 | No private network or TLS between the VPSes: the real AgentX and KW can't reach KA, so G2–G4 can't be shown | infrastructure | **Critical** |
| 2 | ~~KA serves plain HTTP on `0.0.0.0:8011`, publicly reachable~~ **RESOLVED 2026-10-12**: bound to `10.77.0.2` + `127.0.0.1` only (plan-35). The host firewall is still inactive (not KA's to change) | security | ~~High~~ resolved |
| 3 | Real KW round trip unverified: KW hasn't run KA's fixtures against its live intake; KA has only MOCK evidence | integration | **High** |
| 4 | Single shared service token per peer; no per-user identity. AgentX asserts the user (interim Q1/Q4); KA trusts the assertion for `submitted_by` | security / contract | **High** |
| 5 | KW's DEV setting `KW_HOTL_MODE=auto` would apply KA's changes immediately and push them to KW's `graphs/dev` git branch. A first live publish would be unreviewed on KW's side | governance across services | **High** |
| 6 | Single tenant (`KA_TENANT_ID`); no multi-tenant isolation test | scalability / isolation | **Medium** |
| 7 | File-per-object JSON storage and a JSONL event log; in-process operation workers (semaphore of 4); one host | scalability | **Medium** |
| 8 | Data Platform derived assets have no idempotency key on DP's side: a lost 201 followed by a retry duplicates a version | contract (DP) | **Medium** |
| 9 | Ingestion doesn't pass domain/instance/team tags to DP, so such sources are stored PERSONAL (narrowed, never widened) | contract | **Medium** |
| 10 | The live KA uses local storage although a real DP now runs on the same host | configuration | **Medium** |
| 11 | DEV store hygiene: 927 pending candidates (mostly research output) and leftover end-to-end records on the live store | data | **Low** |
| 12 | No publications list screen; no embedding (`frame-ancestors` not set) | UI | **Low** |
| 13 | The legacy `eos-local` graph mode still imports Enterprise OS when explicitly selected (deprecated, off by default) | architecture debt | **Low** |

---

## 7. Dependencies and blockers

| need | owner | why |
|---|---|---|
| A private network between `srv1886827` and `srv2050509` (WireGuard), or a TLS endpoint with a certificate in front of KA `:8011` | **infrastructure / operator** | AgentX ↔ KA and KW ↔ KA calls (G2–G4) |
| Copy `KA_AGENTX_TOKEN` (KA's `.env`) into AgentX's `AGENTX_KNOWLEDGE_ACQUISITION_TOKEN`; set `AGENTX_KNOWLEDGE_ACQUISITION_URL` to the reachable origin + `/api/knowledge-acquisition` | **operator + AgentX** | authenticated discovery and invoke |
| KW reachable from KA's host; KW's token for KA (client `ka`, scopes `graph-changes:propose`, `graphs:read`) put in KA's `.env` as `KA_KW_TOKEN` | **operator + Knowledge Worker** | turns `knowledge.publish` on |
| Decide KW's `KW_HOTL_MODE` for KA-originated changes (`human` recommended for first runs) | **author / Knowledge Worker** | §6 #5 |
| KW to run KA's fixtures `ka/tests/fixtures/kw_contract/01–08` against its live intake | **Knowledge Worker** | contract parity evidence |
| Idempotency on `POST /v1/derived-assets` | **Data Platform** | §6 #8 |
| Nothing from final-sdlc | — | no KA integration required |

---

## 8. Next recommended actions

| # | required change | owning repository | dependencies | acceptance criteria | complexity |
|---|---|---|---|---|---|
| 1 | Private authenticated networking (WireGuard) or TLS for KA; bind KA to the private address or put it behind the proxy; set `KA_PUBLIC_BASE_URL` | infrastructure (operator); KA config only | none | `tools/nexos_evidence.py --public https://<origin>` passes from AgentX's VPS; plain HTTP no longer exposed publicly | Medium |
| 2 | Real AgentX → KA run: AgentX registers KA, invokes `knowledge.search`, `knowledge.acquire` and `knowledge.review`; a named user approves in AgentX Human Tasks | AgentX (driver), KA (no code expected) | #1, the token handover | AgentX run log shows the operation ids; KA's audit shows `decide(by=<user>)`; evidence saved in both repos | Medium |
| 3 | Real KA → KW publication with KW holding changes for a person (`KW_HOTL_MODE=human`) | Knowledge Worker (mode, fixtures), KA (config) | #1, KW's token, the HOTL decision | KA's fixtures pass against live KW; a publish stays `running` until a KW approver applies it, then `succeeded` with KW's proposal id; the change is visible in KW's graph | Medium |
| 4 | Connect the live KA to the standing Data Platform (`KA_STORAGE_BACKEND=data_platform`, `KA_DP_BASE_URL=http://127.0.0.1:8100`), with a backfill rehearsal of existing sources | KA (config + backfill tool from plan-23) | DP owner's consent to share its `:8100` instance | new uploads `available` on DP with knowledge bindings; derived nugget assets present; rollback to local documented | Medium |
| 5 | Security hardening: firewall `:8011` to the private network or proxy only; per-user identity from AgentX (signed user assertion) replacing the trusted-service interim | KA + AgentX (contract) | #1; a contract decision (§9) | an unauthenticated public request can't reach KA; `submitted_by` is verifiable, not just asserted | Large |

---

## 9. Decisions needed from ChatGPT

1. **Network model for NEXOS DEV:** WireGuard mesh across the two VPSes, or TLS endpoints per service? This also decides what
   `launch_url`s AgentX shows for specialist screens.
2. **Human approval across services:** when a person already approved knowledge and its graph change in KA (via AgentX Human Tasks), should
   KW also hold the change for its own human approval (`KW_HOTL_MODE=human`), or is KA's approval sufficient? Today two independent
   approval gates exist, and they disagree in default posture.
3. **User identity:** AgentX currently asserts `caller.user` and `submitted_by` with a shared service token. Is a signed per-user assertion
   (or token exchange) required before G3, and which service issues it?
4. **Shared Data Platform instance:** should KA (and others) use the single DP on `srv1886827:8100`, and under which tenant and principal
   model?
5. **Gap routing:** AgentX's assessment lists `missing_graph_knowledge` owned by KA. Should AgentX call `knowledge.acquire` with
   `kind: gap` (KA's existing path), or should KW's `POST /runtime/graph-gap` remain the trigger? Today both exist.
6. **Event delivery:** AgentX polls operations and doesn't consume `/v1/events`. Keep events as an optional feed, or standardise one
   cross-service event contract?

No shared contract was changed unilaterally. The two shapes added on 2026-10-11 (unavailable capabilities, `/v1/screens`) were agreed with
the AgentX agent first.

---

## 10. Message to ChatGPT

**Readiness.** KA is an independent, running service (`pankajkamble75/ka@e360f89`, `srv1886827:8011`) whose AgentX `agentx-services/v1`
surface passes 15/15 live conformance checks. Six of its seven capabilities are live. `knowledge.publish` is honestly withheld until a
Knowledge Worker is attached.

**Most important accomplishment.** The handoff's "KA source unknown" is resolved. KA was found, audited, brought up to date (it had been
serving pre-`/v1` code), and verified live, without rewriting governance, versioning, provenance or the wiki. The Data Platform path is
verified against the real service.

**Biggest blocker.** There is no private network or TLS between the VPSes, so the real AgentX and the real Knowledge Worker can't reach KA.
Every AgentX/KW result for KA is therefore MOCK, labelled as such.

**Immediate next step.** The operator sets up WireGuard or TLS. Then AgentX runs the first real `knowledge.search` → `knowledge.review` with
a named approver against KA.

**Help needed.** Operator: networking and token handover. Knowledge Worker: run KA's 8 contract fixtures against its live intake, and
decide `KW_HOTL_MODE` for KA's changes. AgentX: drive the first real journey. Data Platform: idempotent derived assets, and consent to
connect KA to the shared `:8100` instance.
