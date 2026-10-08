# Knowledge Acquisition — how the `ka` package realises the specification

Source: [`knowledge-acquisition-requirements.md`](../../knowledge-acquisition-requirements.md). Section numbers below are its.

## 1. Position in Enterprise OS (§1, §2, §19, §43)

```text
Sources ─► ka.ingestion ─► ka.extraction ─► ka.governance ─► ACTIVE KnowledgeNuggetVersion
                                                                     │  knowledge.approved (event)
                                                                     ▼
                                  ka.graph_impact ─► ka.graph_change (proposal → validate → approve → apply)
                                                                     │  via ka.graph_adapter
                                                                     ▼
                                              Structure / Domain / Instance graph (props.knowledge_lineage)
                                                                     │
                                  Enterprise Console runtime navigates the GRAPH. Never this package.
                                  On a gap it POSTs /runtime/graph-gap  → KnowledgeAcquisitionRequest / ResearchMission.
```

`ka.runtime_guard.RuntimeGuard.retrieve_for_answer` exists only to raise. There is no endpoint that answers a question.

## 2. Objects (§4.1, §6, §16, §22, §37) — `ka/model.py`

| Object | Notes |
|---|---|
| `Source`, `SourceVersion` | Raw content. Same location + owner re-ingested with a new checksum → new `SourceVersion`; plan-04 adds `extraction_version` (re-extraction after an extractor upgrade is a new version, `IngestionService.reextract`) and `extraction_report` (`content_version` +1). Bytes under `ka_storage/blobs/`. |
| `Evidence` | A located excerpt (`locator` = "Section 4.2", "p.3", "¶7", URL) of one source version. Carries `visibility`. plan-04 adds `span_id`/`start`/`end` — `SourceVersion.text[start:end]` is the section the evidence sits in (`ka/extraction.py::spans_for`). |
| `KnowledgeNuggetVersion` | The §6 schema verbatim plus `authority_rank`, `visibility`, `graph_group`, `inherited_from`, `analysis`; plan-03 adds `subject`, `predicate`, `object` (§5a). `ref` = `KN-983:v3`. |
| `GrammarBinding`, `SubjectRecord` | plan-03 (§5a): one binding per version per grammar release; one subject per (kind, canonical key). |
| `KnowledgeRelationship` | §10 types, with `explanation` so a reviewer sees why. |
| `GovernanceDecision` | §33 outcomes plus APPROVE / REJECT / AUTO_RESOLVED_BY_AUTHORITY. `automatic=True` for §13 auto-resolution. |
| `KnowledgeCorrection` | §23 form fields + `resolved_lineage`, `suggested_scope`, `scope_rationale`, `candidate_ref`. |
| `ResearchMission`, `ResearchRun` | §16 fields verbatim. `permitted_visibility` bounds what agents may read (§42). |
| `GraphDependency` | The §20 registry row: element ↔ nugget version, with `inheritance_state`. Indexed both ways by `ka.lineage`. |
| `GraphChangeProposal`, `GraphChangeExecution` | §22 schema; executions make rollback possible (§26). |
| `PromotionProposal` | §25. |
| `KnowledgeAcquisitionRequest` | §43. |
| `AuditRecord` | §41: who / what / when / why / before / after / source / scope / approval / affected. |

**Managed connectors (plan-08, R10).** `ka/connectors/` is the provider-agnostic contract (`Connector`: authorize / enumerate /
fetch / get_permissions / checkpoint / sync_incremental / revoke) and `ka/connectors/local_folder.py` the first implementation.
`Connection` (model) names a kind, a root under `KA_CONNECTOR_ROOTS`, scope, authority, visibility and an optional `secret_ref`
(the NAME of an environment variable; the value is never stored). `ka/connectors/sync.py::SyncService.sync` reconciles a delta
through the one ingestion door: new → `Source`; modified → new `SourceVersion` of the same source, re-extracted; moved → same
source, location updated; deleted → `Source.revoked_at`, versions kept, derived nuggets flagged (plan-08) and — **Q4, ✅ built by plan-10** — returned to review as same-statement candidate revisions (`GovernanceService.reopen_for_revocation`) so a person decides: APPROVE keeps, REJECT retires the prior (OBSOLETE) and `GraphChangeService.propose_retirement` proposes removing its elements;
permission-changed → `Source.visibility` updated, derived nuggets flagged. A revoked connection refuses to sync. **Q6 — ⏳ DECIDED 2026-10-08, not built:** the first
provider after the folder is Microsoft 365 / SharePoint (one Graph app registration; permission lists → visibility; client secret via
`secret_ref`); Google Workspace and a file share follow the same pattern.

**Store size (plan-09, R16 benchmark half).** `tools/bench_store.py` fills a fresh repository and times cold load, status and
scope queries, search, put and get; the measured 10k and 100k rows are in `docs/research/benchmarks/store-bench-2026-10-08.md`.
The numbers are evidence for a later decision; this plan changes nothing about the store.

## 3. Scope and inheritance (§7–§9, §24) — `ka/scope.py`

`ScopeRegistry` is configuration: `STRUCTURE ⊃ PARENT_DOMAIN ⊃ DOMAIN ⊃ INSTANCE`. enterprise-os has no Parent Domain in
code, so it is operator-defined here; `KnowledgeAcquisition.sync_scopes_from_graph()` fills domains and pinned instances
from the store. `ScopeDecisionEngine.decide` votes with the signals §24 lists (graph location, original scope, user wording,
evidence scope, similar nuggets, sibling-instance pattern) and flags `requires_approval` when the winner is broader than
the location and touches ≥2 instances.

Inheritance states (§9) are *derived* from the graph: an instance element with `props.realizes` is compared with its
parent — identical → INHERITED, extra props → LOCALLY_EXTENDED, changed values → OVERRIDDEN, parent missing → CONFLICTING,
parent element with no copy → LOCALLY_REMOVED. See `InMemoryGraphAdapter.calculate_inheritance` and the enterprise-os twin.

**Content as an attack surface (Q10 — ✅ built by plan-11, 2026-10-08).** Document text is data, never instruction: the extraction
prompt quotes it inside a delimited block with the instructions outside, and the model is told the block may contain text aimed
at it. Trust tiers follow authority: INTERNET_RESEARCH and LLM_GENERATED sources are heuristic-only — they may yield candidate
statements, but a typed assertion (process type, predicate, edge) from such a source stays `proposed` and never binds without a
reviewer's decision. A verifier model call per assertion was declined for now (doubles model cost) and is revisited on a measured
need. Ledger: `docs/questions/knowledge-acquisition.md` Q10. Lives in `ka/prompting.py` (`fence`, `UNTRUSTED_NOTICE`), the four prompts
(`ka/extraction.py`, `ka/process_extraction.py`, `ka/research.py`, `ka/conflict.py`), `ka/binding.py::Binder.bind` (`HEURISTIC_ONLY` cap,
lifted by `method="approved"`; `rebind_all` remembers approval) and `ka/service.py::_rebind_on_approval` (subscribed before the proposal).

## 4. The governance pipeline (§11–§13) — `ka/governance.py`

```text
ingest_candidate ─► CANDIDATE ─► analyze():
    related pool = ACTIVE/PENDING/APPROVED on the candidate's inheritance chain (ancestors + descendants)
    ka.conflict classifies each pair; relationships stored with explanations
    scope decision recorded in analysis.scope_decision
    ─► ANALYZED ─► (CONFLICT →) PENDING_REVIEW          or REJECTED by §13 auto-resolution
decide(outcome) ─► APPROVED ─► ACTIVE; prior ACTIVE of the same canonical id → SUPERSEDED; ACCEPT_NEW also supersedes the partner
```

Auto-resolution (§13): a candidate whose `authority_rank` is ≥ `KA_AUTO_RESOLVE_AUTHORITY_GAP` below a contradicting ACTIVE
nugget is REJECTED automatically with the explanation preserved. It never applies to FEEDBACK (human corrections).
`authority_rank` is looked up per scope through `config.AuthorityPolicy` (§13 "configurable by organization/domain").

Conflict classification (`ka/conflict.py`) distinguishes the spec's cases: same subject + different value + same scope →
CONTRADICTS; + qualifier ("international") → SPECIALIZES (both valid); candidate at a narrower scope → SPECIALIZES (an override);
candidate at a broader scope than an existing override → CONTEXTUALIZES (override preserved). The LLM, when present, only
adds `why_conflict / both_valid / suggested_resolution` to the finding.

**Duplicates (Q11 — ✅ built by plan-10, 2026-10-08).** When a candidate is analysed as `duplicate_of` an ACTIVE nugget, APPROVE
does not create a second ACTIVE version. It auto-resolves as Keep Existing: the candidate closes as a duplicate, and its source
reference and evidence are attached to the existing nugget so the second document still counts. Refusing or allowing were
considered and declined (reasoning in `docs/questions/knowledge-acquisition.md`, Q11 ledger). Same scope only: the same statement approved in sibling instances is repeated instance knowledge for promotion (§25), not a duplicate. Lives in `ka/governance.py::decide` (the duplicate branch) and `attach_provenance`; characterization 48d4685.

## 5. Compilation, impact, publication (§19–§22, §26, §39, §40) — plan-05

`knowledge.approved` → `GraphChangeService.propose_for(v)`:

1. `GraphImpactService.analyze(v)` — elements depending on prior versions of `v.canonical_id`; INHERITED → "proposed update",
   OVERRIDDEN → "review only"; per descendant scope an `InheritanceEffect`; the §21 counts.
2. `emit_ops` (research-01 R1, R2) — a nugget WITH a subject becomes ops on the element whose id derives from the subject's
   canonical key (`ka/graph_change.py::element_id_for`: `p.<key>`, child process `p.<parent>.<child>`, `e.`/`ac.`/`r.`/`ev.`/`s.` by
   kind); `typed_as` sets `props.process_type` and relation predicates add the object node and the edge ONLY when the grammar
   binding is `bound` (§5a); `description` sets the node's description; every op carries `props.knowledge_lineage =
   [{nugget_id, version, governance_decision_id, graph_change_id}]` (§40 — a reference, never the nugget). A nugget WITHOUT a
   subject keeps plan-01's statement compilation (`r.<slug(title)>` + `props.statement/value`). `to_change_ops` renders KA's
   `ElementChange`s as EOS `ChangeOp` dicts (`add_node | set_props | add_edge | remove_*`).
3. Idempotency (R7, KA half): `idempotency_key = sha256(refs + ops)`; a live proposal with the same key is returned instead of a
   second one. The EOS-side base key on instance changes is Q7.
4. `validate` — Invariant 2 (lineage on every op), adapter validation, governed-knowledge check → READY or FAILED.
5. `requires_approval` when affected instances ≥ `KA_HIGH_IMPACT_INSTANCES` or any descendant is OVERRIDDEN; the policy flag
   `auto_approve_low_impact` may approve, and publishes only under `KA_EOS_AUTO_ACTOR` (a person) when the adapter needs one. **Q3 — ✅ DECIDED 2026-10-08, built:** the switch is OFF by default; every proposal is a deliberate second approval by a named person; revisit with volume data.
6. `apply` — **publication through the adapter**, never a direct write: `InMemoryGraphAdapter.publish` validates and applies to the
   shadow graph; `EnterpriseOSGraphAdapter.publish` goes through EOS's own lifecycle (`proposals.py`): INSTANCE scope →
   `propose_instance_change` → `approve(actor)` → `apply`; DOMAIN scope → `propose_promotion(base_version)` → `request_approval` →
   `approve` → `apply`, which writes a NEW immutable substructure version and leaves instance pins alone (`pinned_instances` reported
   as "repin required", Q2). `ProposalRefused` (incl. `stale_base`) / `GraphRejected` → KA FAILED with the code. Under an untyped
   structure (`universal@1`) `process_type` is omitted with a note. Then `LineageService.register` for every element read back
   → Invariants 4/5. The adapter's direct `apply_change` is retired (`NotImplementedError`).
7. `rollback(execution_id)` — publishes the inverse ops (EOS: a second proposal) and restores the old lineage.

## 5a. Process assertions and grammar binding (research-01 R2, R8 — plan-03)

A nugget version may carry an **assertion**: `subject` (an EOS node kind + canonical key + name + aliases), a `predicate`
from the closed list in `ka/vocab.py::PREDICATES`, and an `object` (another subject or a literal). These three are semantic
and join `SEMANTIC_FIELDS`, so they are immutable with the version. A **GrammarBinding** (`ka/binding.py`) says what the
assertion would be on the EOS graph — `props.process_type` for `typed_as`, an edge + slot for relation predicates, a
property for `description` and the like — with status `bound | proposed | unresolved | not_applicable | stale`. Bindings
are records in their own collection keyed by nugget ref and grammar versions, so a grammar release recomputes them
(`Binder.rebind_all`) without touching any governed version.

The grammar is EOS's (`ka/grammar.py::GrammarRegistry`): `grammar.json` and `process_types.json` read from
`KA_GRAMMAR_DIR` (default `<KA_ENTERPRISE_OS_ROOT>/knowledge_worker/graph_model`), snapshotted by version string **and**
sha256. Files that change under the same version string make the registry stale: new bindings are `stale`, `rebind_all`
refuses, and only `refresh(force=True)` accepts them. No grammar loaded → every binding `unresolved`, never a guess.
Subjects resolve through `ka/identity.py::SubjectRegistry` (exact key → alias → similarity within kind); element ids
derived from canonical keys land in plan-05.

**The second extraction pass (plan-04, R3).** `ka/process_extraction.py::ProcessExtractor` reads processes out of the same
sections: with a model, a prompt carrying the closed lists (EOS node kinds, `PREDICATES`, the loaded type names, slots) whose
out-of-list output is dropped and disclosed in `SourceVersion.extraction_report`; without one, a heuristic over headings and
numbered lists that emits `description`, `decomposes_into`, `performed_by` and never a type. `GovernanceService.extract_from_source`
runs it after the statement pass, so both share source, scope and the one governance door; every assertion's evidence carries a span.

**Evidence in the Enterprise console (Q9 — ✅ DECIDED 2026-10-08: not yet).** The Live Console frontend stays pinned (EOS Q418); the
evidence behind a published node is read through KA's lineage API and the Knowledge Console. Revisit once real published graphs exist.

**Repinning after a domain write (Q2 — ✅ built by plan-12, 2026-10-09).** KA never repins an instance automatically. After a
promotion is applied, the graph-change page lists every instance still pinned to the previous substructure version (the
`pinned_instances` the adapter already reports) with a Repin action; a named person repins each one, KA calls the store's own
`repin`, and the audit records who moved which instance to which version. Until repinned, the instance's inheritance state
shows it behind the domain. Lives in `ka/graph_adapter.py` (`RepinResult`, `pinned_versions`, `repin` on both adapters — the EOS one
calls `store.repin(..., apply=)` and maps `RepinBlocked` to an unapplied result), `ka/graph_change.py::repin` / `repin_status` /
`awaiting_repin` (a `by` that is a policy id or a research agent is refused), routes `GET/POST /graph-changes/{id}/repin(s)`, the
change page's "Instances pinned to this domain" table and the Dashboard count. Ledger: `docs/questions/knowledge-acquisition.md` Q2.

## 6. Research (§3.2, §16–§18) — `ka/research.py`

`ResearchOrchestrator.run_mission`: Enterprise Content (reads repository sources on the scope chain, filtered by
`permitted_visibility`), Domain, Standards/Regulatory, Internet (off unless `KA_RESEARCH_INTERNET=1`), LLM Knowledge → `SynthesisAgent`
(clusters by similarity, one candidate per cluster, authority = max of the cluster, every finding kept as `Evidence`) →
`GovernanceService.ingest_candidate(channel=RESEARCH)`. Runs record sources, evidence, candidates, tokens, cost, errors.
`GovernanceService.research_agent_ids` makes `decide(by=<agent>)` fail (§17). `knowledge_for_domain` is the §18 Domain Builder entry:
reuse ACTIVE knowledge on the scope chain, open a mission only for the gap.

**Discovery (plan-07, R9).** `ka/discovery.py::DiscoveryAgent` runs first in the coordinator: the objective and questions become
queries for a `SearchProvider` (`none` or `fixture` today; **Q5 — ⏳ DECIDED 2026-10-08, not built:** a paid web-search API chosen on price, one provider class behind this seam, key in the environment, `KA_SEARCH_MONTHLY_CAP` on top of the per-mission budget); results are canonicalised (fragments and
tracking parameters dropped), deduplicated, filtered by `KA_ALLOWED_DOMAINS`, `is_safe_url` and `robots.txt` (fetched through
`safe_fetch`, cached per run; unreachable = allowed, recorded), ranked by overlap with the objective and cut at `KA_DISCOVERY_BUDGET`;
every skip carries its reason in `ResearchRun.discovery`. The Internet agent fetches the selection only when `KA_RESEARCH_INTERNET`
is on and stamps `canonical_url / publisher / published_at (never guessed) / retrieved_at / query` on the `Source`. Fetched pages
are `INTERNET_RESEARCH`; model answers stay `LLM_GENERATED`, so a model answer is never presented as an internet source.

## 7. Corrections and promotion (§23–§25) — `ka/corrections.py`, `ka/promotion.py`

`CorrectionService.submit` resolves lineage from the registry *and* from the element's `props.knowledge_lineage`, records the form as a
`Source(type=correction)` + `Evidence`, stores Note / Upload / URL / Existing Source evidence, asks the Scope Decision Engine, and creates
the candidate (next version of the resolved nugget, or a new nugget). `PromotionService.detect(parent)` clusters ACTIVE instance nuggets
shared by ≥ `KA_PROMOTION_MIN_INSTANCES` instances and proposes; `decide(approve=True)` creates a *candidate* at the parent scope.

## 8. Console and API (§27–§35) — `ka/api.py`, `ka/console/`

Static single-page console at `/console/`: Overview · Needs attention (§32 queues + promotions + gap requests) · Search (§35 filters) ·
Graph changes · Add knowledge (Upload / Paste / Write / Link) · Correct this (§23 form) · per-scope tabs Overview / Knowledge / Sources /
Conflicts / Research / Changes / Graph impact / History (§28) · Instance view with Inherited / Instance-specific / Overrides / Extensions /
Removed / Pending corrections (§30) · Nugget detail with every §31 field and action · Conflict resolution with the §33 layout and actions.

**The process profile (plan-06, R12).** `ka/profile.py::ProfileService.profile(key)` composes, for one process subject, the ACTIVE
assertions by predicate — description, type (bound / proposed / unresolved / not evidenced), activities in document order,
actors, inputs, outputs, entities, rules, events, states — each field carrying its nugget ref, evidence spans and the element it
is published as; PENDING ones are listed apart; `coverage` reports the bound type's required and recommended slots as evidenced
or not, from EOS's slot grammar, and nothing is ever filled in. It is a query, never a stored object. Surfaces:
`GET /processes`, `GET /processes/{key}`, the "Processes" mode of Browse by scope, and the subject page for process subjects.
**Q8 — ⏳ DECIDED 2026-10-08, not built:** Processes becomes a fifth top-level tab (Add knowledge · Knowledge nuggets · Browse by scope
· Processes · Dashboard, plus Images) pointing at this view; the note's five-page layout is declined.
No new tab while Q8 is parked.

## 9. Events and audit (§38, §41)

`ka.events.EventBus` — the §38 names, payloads are ids (a value longer than 200 chars is refused), every event appended to `events.jsonl`.
`ka.audit.Auditor.record` on every state change → `audit.jsonl`; `GET /audit?object_id=` reconstructs any object's history.

**Events as an outbox (plan-09, R15).** `events.jsonl` is the durable, ordered log KA already had; `Repository.append_event` now
stamps every record with a monotonic `seq` and `version: "ka-events/1"` (records from before plan-09 are served with their
1-based line number and `ka-events/0`). `GET /events?after=<seq>&limit=` returns records ascending with `next_after`, so any
consumer (EOS included) reads at-least-once by remembering `seq`; `tail=1` keeps the "last N" view. A broker is a later
decision, taken on a measured need.

**The gap request lifecycle (plan-09, R11 KA half).** `KnowledgeAcquisitionRequest` carries `principal`, `intent`
(`found_new | grow_existing | answer | other`), `missing_semantics`, `correlation_id` and a `dedupe_key`; the same gap raised
while a request is OPEN or IN_RESEARCH returns that request (`GapOutcome.deduplicated`). `open_mission=True` puts it
IN_RESEARCH; approving a candidate from that mission marks it FULFILLED (`ka/service.py` subscriber → `RuntimeGuard.fulfil_from_approval`);
`cancel` works from the live states only. Routes `GET /runtime/requests[?status=]`, `GET /runtime/requests/{id}`,
`POST /runtime/requests/{id}/cancel`; the Dashboard's needs-attention table shows principal · intent, status and Cancel.
The door (`retrieve_for_answer`) is unchanged. **Q7 — ⏳ DECIDED 2026-10-08, not built (EOS repo):** Enterprise OS routes `found_new` through this contract first (intent `found_new`, principal = the EOS runtime, correlation id = the EOS gap id); `grow_existing` stays in EOS for now. The same EOS change exposes the grammar read-only with a digest and accepts a base key on instance proposals. Delivered under the Enterprise OS pipeline. Ledger: `docs/questions/knowledge-acquisition.md` Q7.

## 10. Security (§42)

**Step 1 — ✅ DECIDED by the author 2026-10-08 (Q1: loopback + bearer token) and built by plan-02 (2026-10-08).** Every `/api/knowledge-acquisition/*` route runs `require_access`
(`ka/security.py`) under `KA_ACCESS_POLICY`: `token` (default, Q1's recommendation) admits loopback peers and non-loopback
peers presenting `Authorization: Bearer <KA_ACCESS_TOKEN>`; `loopback` copies enterprise-os's containment; `open` is the
pre-plan-02 behaviour. Uploads are capped by `KA_MAX_UPLOAD_MB` (`ka/api.py::_read_capped`, 413). `link()` and the Internet
agent fetch only through `is_safe_url` / `safe_fetch` (loopback, link-local, private, reserved addresses refused; redirects
re-checked per hop; `KA_URL_ALLOWLIST` for intranet hosts). A CHANGE_SCOPE or promotion that would widen a nugget's
visibility is refused unless the decision carries `widen_visibility=True`, and then records `visibility_change`
(`ka/vocab.py::required_visibility`, `ka/governance.py` CHANGE_SCOPE branch, `ka/promotion.py::decide`). **Step 2** —
identity provider and tenant model remain a two-repo plan (Q4, provider not yet named). **Retention after revocation is decided (Q4, 2026-10-08): re-review** — every ACTIVE nugget derived from a revoked source becomes a candidate revision in Pending with `source_revoked`; APPROVE keeps it on its other evidence, REJECT retires the prior version (OBSOLETE) and raises a graph proposal; never automatic, never silently live. ✅ built by plan-10 (`ka/governance.py`, `ka/graph_change.py::propose_retirement`, `ka/connectors/sync.py` trigger).

`Source.visibility`/`permissions`; a nugget's `visibility` is the narrowest of its sources; research agents skip sources more restricted
than the mission's `permitted_visibility` unless the requester owns them. Access *enforcement* at the API edge (authn) is out of scope for
plan-01 and tracked as a question.

## 11. What is deliberately not here (§45)

No vector index, no chat, no document browser as the primary view, no agent path that writes to the graph, no runtime answer endpoint.
