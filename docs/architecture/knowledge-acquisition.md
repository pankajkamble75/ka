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
| `Source`, `SourceVersion` | Raw content. Same location + owner re-ingested with a new checksum → new `SourceVersion` (`content_version` +1). Bytes under `ka_storage/blobs/`. |
| `Evidence` | A located excerpt (`locator` = "Section 4.2", "p.3", "¶7", URL) of one source version. Carries `visibility`. |
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

## 3. Scope and inheritance (§7–§9, §24) — `ka/scope.py`

`ScopeRegistry` is configuration: `STRUCTURE ⊃ PARENT_DOMAIN ⊃ DOMAIN ⊃ INSTANCE`. enterprise-os has no Parent Domain in
code, so it is operator-defined here; `KnowledgeAcquisition.sync_scopes_from_graph()` fills domains and pinned instances
from the store. `ScopeDecisionEngine.decide` votes with the signals §24 lists (graph location, original scope, user wording,
evidence scope, similar nuggets, sibling-instance pattern) and flags `requires_approval` when the winner is broader than
the location and touches ≥2 instances.

Inheritance states (§9) are *derived* from the graph: an instance element with `props.realizes` is compared with its
parent — identical → INHERITED, extra props → LOCALLY_EXTENDED, changed values → OVERRIDDEN, parent missing → CONFLICTING,
parent element with no copy → LOCALLY_REMOVED. See `InMemoryGraphAdapter.calculate_inheritance` and the enterprise-os twin.

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

## 5. Compilation, impact, change (§19–§22, §26, §39, §40)

`knowledge.approved` → `GraphChangeService.propose_for(v)`:

1. `GraphImpactService.analyze(v)` — elements depending on prior versions of `v.canonical_id`; per element INHERITED → "proposed
   update", OVERRIDDEN → "review only"; per descendant scope an `InheritanceEffect`; the §21 counts.
2. `_changes_from` — new knowledge compiles to one element (`KIND_FOR_KNOWLEDGE`: rule/policy/constraint/condition → rule,
   process_step → step, definition/concept → concept, relationship → edge …) with `props.statement`, `props.value` (first
   number) and `props.knowledge_lineage = [{nugget_id, version, governance_decision_id, graph_change_id}]` (§40 — a reference,
   never the nugget). A revision updates every dependent element. An instance nugget that SPECIALIZES a parent nugget updates the
   *realized copy* of the parent's element (an override), not a second rule. Downward propagation (§26) adds updates for every
   INHERITED realized copy in descendant scopes and leaves OVERRIDDEN / LOCALLY_REMOVED ones alone.
3. `validate` — Invariant 2 (lineage on every change), adapter validation, governed-knowledge check → READY or FAILED.
4. `requires_approval` when affected instances ≥ `KA_HIGH_IMPACT_INSTANCES` or any descendant is OVERRIDDEN; otherwise a policy flag
   (`auto_approve_low_impact`) may approve + apply.
5. `apply` — adapter writes, then `LineageService.register` for every element (retiring the old version's dependency) → Invariants 4/5.
6. `rollback(execution_id)` — inverse of the applied changes, old lineage restored.

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

## 6. Research (§3.2, §16–§18) — `ka/research.py`

`ResearchOrchestrator.run_mission`: Enterprise Content (reads repository sources on the scope chain, filtered by
`permitted_visibility`), Domain, Standards/Regulatory, Internet (off unless `KA_RESEARCH_INTERNET=1`), LLM Knowledge → `SynthesisAgent`
(clusters by similarity, one candidate per cluster, authority = max of the cluster, every finding kept as `Evidence`) →
`GovernanceService.ingest_candidate(channel=RESEARCH)`. Runs record sources, evidence, candidates, tokens, cost, errors.
`GovernanceService.research_agent_ids` makes `decide(by=<agent>)` fail (§17). `knowledge_for_domain` is the §18 Domain Builder entry:
reuse ACTIVE knowledge on the scope chain, open a mission only for the gap.

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

## 9. Events and audit (§38, §41)

`ka.events.EventBus` — the §38 names, payloads are ids (a value longer than 200 chars is refused), every event appended to `events.jsonl`.
`ka.audit.Auditor.record` on every state change → `audit.jsonl`; `GET /audit?object_id=` reconstructs any object's history.

## 10. Security (§42)

**Step 1 — built by plan-02 (2026-10-08).** Every `/api/knowledge-acquisition/*` route runs `require_access`
(`ka/security.py`) under `KA_ACCESS_POLICY`: `token` (default, Q1's recommendation) admits loopback peers and non-loopback
peers presenting `Authorization: Bearer <KA_ACCESS_TOKEN>`; `loopback` copies enterprise-os's containment; `open` is the
pre-plan-02 behaviour. Uploads are capped by `KA_MAX_UPLOAD_MB` (`ka/api.py::_read_capped`, 413). `link()` and the Internet
agent fetch only through `is_safe_url` / `safe_fetch` (loopback, link-local, private, reserved addresses refused; redirects
re-checked per hop; `KA_URL_ALLOWLIST` for intranet hosts). A CHANGE_SCOPE or promotion that would widen a nugget's
visibility is refused unless the decision carries `widen_visibility=True`, and then records `visibility_change`
(`ka/vocab.py::required_visibility`, `ka/governance.py` CHANGE_SCOPE branch, `ka/promotion.py::decide`). **Step 2** —
identity provider, tenant model, retention after revocation — remains Q4.

`Source.visibility`/`permissions`; a nugget's `visibility` is the narrowest of its sources; research agents skip sources more restricted
than the mission's `permitted_visibility` unless the requester owns them. Access *enforcement* at the API edge (authn) is out of scope for
plan-01 and tracked as a question.

## 11. What is deliberately not here (§45)

No vector index, no chat, no document browser as the primary view, no agent path that writes to the graph, no runtime answer endpoint.
