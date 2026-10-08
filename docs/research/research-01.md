# Research 01 - Process-oriented knowledge into the EOS typed graph: bind to the grammar EOS already has, publish through the proposals EOS already runs

Created: 2026-10-08 14:30 UTC
Source note: [KA-enhancement.md](../user-research/notes/KA-enhancement.md) (KA-ENH-001)
Class: PRODUCT
Severity: MAJOR
Verdict: Aligned with corrections

Repositories reviewed at: `ka` `7c83aa3` (main), `enterprise-os-070626` `6221526` (main). Enterprise OS paths below are
relative to `/root/enterprise-os-070626/knowledge_worker/` and written `KW/…`; `ka` paths are repo-relative.

## What this research is about

The note asks KA to stop producing *sentences about the business* and start producing *knowledge about processes*: what a
process is, what it does and, where a document actually says so, how it operates — decomposition, type, actors, inputs,
outputs, rules, events, states, data. It asks that this knowledge be bound to the vocabulary Enterprise OS (EOS) owns
and published into the EOS graph through a validated, versioned, idempotent contract, from sources that include personal
and workplace content behind real connectors and the open web behind real discovery, all under authentication that does
not exist today.

The question under that is one of ownership. Plan-01 built KA as a self-contained compiler: a governed nugget becomes a
graph element that KA itself names, shapes and writes (`ka/graph_change.py:75-126`). EOS, meanwhile, already owns a
governed grammar (`KW/graph_model/grammar.json:2` `grammar/v2`), a governed process-type table
(`KW/graph_model/process_types.json:2` `process-types/v2`), a validator that never raises but reports findings
(`KW/graph_model/validate.py:38`), and a proposal lifecycle with named-person approval and stale-base refusal
(`KW/graph_store/proposals.py:560,653,719,790`). The implicit problem the note is solving is: **KA must become a client of
those three things, not a second implementation of them.** The note says this in its principal invariant (note §1) and
then, in REQ-006/009/011, designs new contracts in places where EOS already has the mechanism. This report separates the
two.

## Why it matters

Three things are wrong or at risk today, in order of weight.

1. **Graph identity is derived from a title slug.** `ka/graph_change.py:97` mints `f"{prefix}.{_slug(v.title)}"`; two
   governed nuggets about the same process with different titles produce two elements. The note's publication invariant 6
   ("no duplicate graph identities because titles differ", note §6.3) is violated by construction. This is the one defect
   that would corrupt an EOS domain graph the first time KA publishes into one.
2. **Compilation is grammar-blind.** `KIND_FOR_KNOWLEDGE` (`ka/graph_impact.py:45`) maps a nugget's knowledge type to one of
   KA's own `GraphElementKind`s; `_value_props` (`ka/graph_change.py:34-40`) carries the statement and the first number it
   finds. Nothing produces `props.process_type`, a `contains` nesting, a `consumes`/`produces` edge or a slot — the ten node
   kinds and fifteen edge pairs EOS validates (`KW/graph_model/grammar.json:3,78`). EOS's "process-oriented knowledge" is
   unreachable from KA as built.
3. **Both services are unauthenticated.** KA checks no caller (`ka/api.py:177-196` — `Depends(get_ka)` only;
   `docs/architecture/knowledge-acquisition.md:120`). EOS has no authentication either, only a loopback containment that
   its own docstring calls "not an access policy" (`KW/backend/agent_x_mount.py:56-59, 2661`), and EOS architecture records
   authentication as deferred (`docs/architecture/prompt-approval-asymmetry.md:67`). Personal and workplace sources
   (note §3) cannot be ingested responsibly into either.

If nothing is done, KA keeps governing well and publishing badly: the governance half of plan-01 (immutable versions,
conflicts, lineage) holds, and the compiled half writes untyped, duplicate-prone elements into a graph whose navigation is
grammar-first and process-typed (`docs/architecture/grammar-first-navigation.md` §1).

## What the code does today

**KA — what the note gets right about the baseline.** All six "verified design limitations" (note §2) are confirmed:

| Note §2 claim | Evidence |
|---|---|
| `connect()` takes a prefetched payload; no provider sync | `ka/ingestion.py:84-87` — `payload: bytes`, docstring "the connector has already fetched `payload`" |
| Internet agent fetches explicit URLs behind `KA_RESEARCH_INTERNET` | `ka/research.py:194-202` — URLs filtered from mission fields with `startswith("http")`; `config.get("KA_RESEARCH_INTERNET")` gate at :199 |
| `PROCESS_STEP` alone does not express the typed graph | `ka/vocab.py:118`; its only consumer maps it to `GraphElementKind.STEP` at `ka/graph_impact.py:48` |
| `_changes_from` compiles generic node/edge changes | `ka/graph_change.py:75-126`; props from `_value_props` :34-40; id from title slug :97 |
| Auth at the API edge deferred | `docs/architecture/knowledge-acquisition.md:120`; `docs/implementation-plans/plan-01.md:26` |
| Scanned PDFs yield unavailable text | `ka/extraction.py:120` — `UNAVAILABLE` when `extract_text()` returns nothing, note "no text layer (scanned PDF?)" |

**KA — what already exists toward the note's direction, and is reusable as is:**

- Sources are immutable with checksum, owner, author, effective date, visibility and a permissions list
  (`ka/model.py:54-70`); same location + owner with a changed checksum becomes a new `SourceVersion`
  (`ka/ingestion.py:146-151`, `content_version` bump at :112-118); bytes are kept under `blobs/` (`ka/ingestion.py:32,129-131`).
  REQ-001's idempotency acceptance is already true (`ka/tests/test_plan01_phase1_foundation.py::test_P2`, `::test_P3`).
- Evidence has a locator (`ka/model.py:94`) and extractors already emit section-level locators — `p.N` for PDF pages
  (`ka/extraction.py:118`), headings for Markdown and Word, `table N`, `slide N`, `sheet X`
  (`ka/extraction.py:94,140-142,165-180`). What is missing for REQ-004 is span stability (character offsets) and cell/row
  granularity, not locators as such.
- One governance pipeline for every channel (`ka/governance.py:78,110,147,232`); research agents cannot decide
  (`ka/governance.py:235`, `research_agent_ids` :74). The note's REQ-007 lifecycle rules are already enforced:
  immutable semantic fields (`ka/versioning.py:15-16`), CONTRADICTS / SPECIALIZES / CONTEXTUALIZES classification by
  value, qualifier and scope (`ka/conflict.py:123-155`), lowest valid scope (`ka/scope.py:111-122`), narrowest source
  visibility inherited by the nugget (`ka/governance.py:112`), and agents barred from sources more restricted than the
  mission's clearance (`ka/research.py:140`).
- Lineage both ways (`ka/lineage.py:104-107` writes `{nugget_id, version, governance_decision_id, graph_change_id}` to the
  element; `GraphDependency` registry), and the EOS adapter already refuses any element change without that lineage
  (`ka/graph_adapter.py:217,389-…`).
- The gap seam exists: `POST /runtime/graph-gap` (`ka/api.py:569-572`) creates a `KnowledgeAcquisitionRequest` and optionally
  a mission (`ka/runtime_guard.py:35`); the answer door raises (`ka/runtime_guard.py:48`).
- Events are an in-process bus with an append-only `events.jsonl` sink (`ka/events.py:1,33-51`), names at :16-24.

**EOS — what the note assumes must be designed, and already exists:**

- **Grammar and types are versioned files, loaded and validated by Python.** `grammar.json` carries `"version": "grammar/v2"`
  (`KW/graph_model/grammar.json:2`), ten node kinds (:3), fifteen edge pairs with inverses (:78-270), fifteen slots (:271),
  seven intents (:351), vocabularies for transformations and lifecycle states (:381), five core data roles (:557), and two
  structures of which `universal-typed@1` pins `process_type_table: "process-types/v2"` (:618). `process_types.json` carries
  `"version": "process-types/v2"` (:2) and exactly ten types — transformation, transaction, decision, analysis, control,
  interaction, planning, coordination, creation, learning — each with required/recommended/optional slots and per-intent
  traversals. Loaders: `load_grammar` (`KW/graph_model/grammar.py:174`, raises one `GrammarError` :54),
  `load_type_table` (`KW/graph_model/process_types.py:160`, `TYPE_NAMES` governed per Q409 :16).
  **No read-only endpoint exposes either** — no router imports `load_grammar` or `load_type_table`. **No digest exists** on
  the grammar; only version strings and lineage refs of the form `grammar:kind/process@v2`, `type:decision@v2`
  (`KW/graph_model/lineage_refs.py:1-30`).
- **Process typing is a prop, and incompleteness is a finding.** The primary type is `props.process_type`, up to two
  `props.secondary_types` (`KW/graph_model/process_types.py:12-13`). `check_process_typing` (:392) reports `process_type.unknown`,
  `.multi_typed`, `.table_version_mismatch` as errors, an untyped process as a **warning** (:378), and a typed process missing a
  required slot as `process_type.incomplete` (:349-378). Nesting is `contains` only, max depth 8
  (`KW/graph_model/validate.py` — `contains_cycle`, `contains_multiple_parents`, `process_depth_exceeded`); "Activity" is
  display only (`KW/graph_model/model.py:158`). This is exactly the "unknown / not_evidenced" semantics the note asks for in
  REQ-005: **EOS already has a place for partial process knowledge, and it is a warning or an `incomplete`, not a rejection.**
- **Validation never raises; the store refuses.** `validate(graph, structure) -> list[Finding]` (`KW/graph_model/validate.py:38`);
  `GraphStore._validate` refuses any graph with an `error` finding via `GraphRejected(.findings)`
  (`KW/graph_store/errors.py:23`); provenance (`props.realizes`) is store-checked (`KW/graph_store/store.py:781-787`).
- **A proposal lifecycle exists, with approval by a named person.** `propose_instance_change(instance_id, ops, *, actor, reason)`
  (`KW/graph_store/proposals.py:653`) builds the candidate graph and refuses on new error findings;
  `propose_promotion(substructure_id, base_version, …)` (:719) previews with `pinned_instances`; `approve(pid, *, actor, …)`
  (:560) refuses "system", "automation" and "hotl:" actors; `apply(pid)` (:599); promotions refuse `stale_base` (:790,796) and
  `put_substructure(graph, parent=…)` raises `StaleParent` (`KW/graph_store/store.py:159`; `errors.py:87`). `ChangeOp` is
  `add_node | add_edge | set_props | remove_node | remove_edge` with `extra="forbid"` (:146). **Instance changes have no
  base version or stale check**, and **no proposal has an idempotency key** — ids are `uuid4` (:443). Locking is one in-process
  `RLock` per store root; "cross-process writers are out of scope" (:355).
- **Domain versions are immutable and instances pin them.** `put_substructure` writes the next version once and returns the
  existing version for identical content; `repin(iid, sid, version, apply=False)` previews a `RepinDiff` and only writes with
  `apply=True` (`KW/graph_store/store.py:159,899`); `pinned_by` (:676). Note §6.3 invariant 5 ("no silent repinning") is EOS's
  existing behaviour (`docs/architecture/process-typed-graph.md`, R15/Q409 row).
- **The runtime gap path mutates the graph itself.** `act_on_gaps` (`KW/gap_v2/act.py:777`) founds, grows or adds locally,
  gated by HOTL points (`instance_graph_change`, `domain_confirmation`, :62) whose mode defaults to `auto`
  (`KW/governance/hotl.py:141-144`, fail-closed to `human` on unknown values). It does not call KA. Spec §43 and Invariant 2
  say it should raise a gap instead.
- **Data grammar exists.** Core roles (`KW/graph_model/data_graph.py:67`), canonical data objects as `Tier.data_object`
  graphs (`KW/graph_store/data_library.py`; `put_data_object` at `store.py:434`), `object_lineage`, `canonical_attribute`,
  `data_refs`, and author-only proposal kinds `data_object_new`, `data_object_version`, `domain_attribute`
  (`proposals.py:1589`). Architecture: `docs/architecture/data-layer.md` §1–§7.
- **The EOS console frontend is frozen.** `KW/tests/test_q418_frontends_unchanged.py` fingerprints `console/frontend/**`;
  `docs/architecture/process-typed-graph.md` "The UIs through the switch-over — Q418" rules it byte-identical. The nearest
  host for a process evidence panel is the node card in `console/frontend/src/GraphPanel.tsx:1231` (`graph-node-card`), but
  touching it is the author's ruling, not a plan's.

## Architecture this research obeys

| decision | where | bearing on this |
|---|---|---|
| Knowledge is governed first, compiled second, consumed through the graph (Inv. 1, 2) | `knowledge-acquisition.md` §1 | constrains every point; R1 obeys it — publication still ends in an EOS proposal, never a direct write |
| One governance pipeline for every channel; agents cannot decide | `knowledge-acquisition.md` §4 | constrains R3, R9, R10 — connectors and discovery feed `ingest_candidate`, not a new path |
| Nugget versions are immutable; a semantic change is a new version (Inv. 3) | `knowledge-acquisition.md` §4 | constrains R2 — bindings are recomputed into a *new* binding record, never into a governed version |
| Compilation: `KIND_FOR_KNOWLEDGE`, title-slug ids, `props.knowledge_lineage` entry shape | `knowledge-acquisition.md` §5 | **this research extends it**: R1 replaces the compiler with grammar-bound `ChangeOp` emission; the lineage entry shape is kept |
| Scope registry; lowest valid scope; inheritance states derived from `props.realizes` | `knowledge-acquisition.md` §3 | constrains R2 and R6; not touched |
| Research agents, synthesis, visibility clearance | `knowledge-acquisition.md` §6 | **this research extends it**: R9 adds discovery in front of the Internet agent |
| Security §42: visibility modelled, enforcement deferred | `knowledge-acquisition.md` §10 | **this research completes it**: R4 (containment + service token), R5 (upload cap, SSRF) |
| Console: four tabs + Images | `knowledge-acquisition.md` §8 | **this research proposes a new row**: R12 adds a Processes tab; R13 decides the note's five pages against the four tabs |
| EOS: one recursive typed Process kind; depth by `contains`; substructure versions immutable, instances pin; Structure and process types proposal-only | EOS `process-typed-graph.md` (R16/Q408, R15/Q409) | constrains R1, R2, R7 — KA emits nested processes, never a new kind; never edits types |
| EOS: grammar is one governed, versioned, hand-edited file checked by Python identifiers | EOS `process-typed-graph.md` (research-219 R1/Q433) | constrains R2 and R8 — the "descriptor" is these files plus a version; no second schema |
| EOS: grammar-first navigation over Structure → Domain → Instance; per-instance lineage table | EOS `grammar-first-navigation.md` §1, §4 | constrains R1 — published elements must carry the lineage refs the table reads |
| EOS: console frontend byte-identical | EOS `process-typed-graph.md` (Q418) | constrains R14 — the EOS evidence panel is a decision, not a build |
| EOS: data grammar, core roles, canonical objects; data proposals author-only | EOS `data-layer.md` §1–§7 | constrains R2 — KA binds to existing roles/objects, proposes none |
| Authentication for the EOS backend | no document owns this (`prompt-approval-asymmetry.md:67` records it as deferred) | silent — see R4 (decide) |
| Durable events / outbox between KA and EOS | no document owns this (proposed only in EOS research-65 R15, research-132) | silent — see R15 (decide) |
| Should the runtime gap path call KA instead of `act_on_gaps` | no document owns this; spec §43 asserts it, EOS code contradicts it | silent — see R11 (decide) |

## Reading of the source note

The note proposes fourteen requirements in five groups: sources (unified registration, managed connectors, web discovery,
layout-aware extraction), a process-aware model bound to EOS grammar, evidence/conflict/scope rules, security, an EOS
publication and feedback contract with APIs and events, two user interfaces (a five-page KA console and an EOS evidence
panel), and observability. It frames EOS as the owner of grammar, types, graph and navigation, and KA as the acquirer and
governor. It asks for a read-only discovery report first and no code until that is approved.

| Claim in the note | Verdict | Evidence |
|---|---|---|
| §1 "EOS owns Process Grammar, Process Types, Data Grammar, graph structure" | Confirmed | `KW/graph_model/grammar.json:2`, `process_types.json:2`, `data_graph.py:67`; EOS `process-typed-graph.md` Q433 |
| §2 the six design limitations | Confirmed (all six) | table above, "What the code does today" |
| §2 "EOS v2 uses recursive Process nodes … versioned substructures with pinned instances" | Confirmed | `KW/graph_model/process_types.py:392`, `validate.py` depth checks; `store.py:159,676,899` |
| REQ-001 "content-hash duplicates shall not create duplicate versions" (as a gap) | Already true | `ka/ingestion.py:112-118` returns the existing version on equal checksum; `test_P2`, `test_P3` |
| REQ-001 "capture tenant_id, principal_id, source class (personal/team/enterprise/public)" | Partly true | owner, permissions, `Visibility` PERSONAL/TEAM/DOMAIN/INSTANCE/ENTERPRISE exist (`ka/model.py:56-63`, `vocab.py`); no tenant, no `public` class |
| REQ-004 "evidence can link back to an exact page, section or row" (as a gap) | Partly true | page/section/table/slide/sheet locators exist (`ka/extraction.py:94,118,140,165`); no stable span ids, no row/cell granularity, no OCR (`:72-73`) |
| REQ-005 "introduce typed process assertions … rather than replacing nugget types" | Confirmed as a gap | `ka/model.py:120-152` has statement/normalized_meaning/graph_group only; no subject/predicate/value |
| REQ-005 "represent unknown / not_evidenced without fabricating" | Confirmed, and EOS already models it | `process_type.untyped` is a warning, `process_type.incomplete` a finding (`process_types.py:349-378`) |
| REQ-006 "expose a read-only, versioned grammar descriptor contract from EOS" | Partly true | the versioned artefacts exist; **no endpoint and no digest** — see R8 |
| REQ-006 "fail closed on incompatible revisions" | EOS precedent exists | `typed_universal()` raises `GrammarError` on table version mismatch (`KW/graph_model/structure.py:64`) |
| REQ-007 lifecycle rules (dup/support/refine/contradict/specialize/supersede; lowest scope; no silent overwrite) | Already true | `ka/conflict.py:123-155`, `ka/scope.py:111`, `ka/versioning.py:15`; `phase2 ::test_P1–P6` |
| REQ-007 "personal evidence must not promote to broader visibility" | Partly true | nugget visibility = narrowest source (`ka/governance.py:112`); promotion to a parent scope does not re-check visibility (`ka/promotion.py:22-…`) |
| REQ-008 "authentication at all API/UI boundaries" (as a gap) | Confirmed, and EOS has none either | `ka/api.py:177-196`; `KW/backend/app.py:118` CORS only; `agent_x_mount.py:56,2661` loopback containment |
| REQ-009 "replace the simplistic nugget-to-generic-node compiler" | Confirmed as a defect | `ka/graph_change.py:34-40,95-97` |
| REQ-009 "duplicate retries cause no duplicate elements" needs idempotency | Confirmed as a gap — **on both sides** | KA: no key (`grep idempot` empty); EOS: `uuid4` ids (`proposals.py:443`), instance changes without base version (:672) |
| REQ-009 "domain changes create new immutable substructure versions; instances stay pinned" | Already true in EOS | `store.py:159,899`; `ka/graph_adapter.py:445` already calls `put_substructure` |
| REQ-010 "extend `/runtime/graph-gap` with an authenticated, versioned contract" | Partly true | seam exists (`ka/api.py:569`); EOS never calls it — `act_on_gaps` mutates directly (`KW/gap_v2/act.py:777`) |
| REQ-011 new `/v1/*` routes | Proposal | none exist; the note says so itself |
| REQ-012 "five simple task-based pages" | Conflicts with the author's own ruling of 2026-10-08 (four tabs) | `ka/console/app.js` `TAB_LABELS`; see "Where I differ" |
| REQ-013 EOS Knowledge/Evidence view | Blocked by Q418 | `KW/tests/test_q418_frontends_unchanged.py`; `GraphPanel.tsx:1231` is the host |
| REQ-014 "validate whether JSON-per-object is acceptable at volume" | Fair; measured nowhere | `ka/repository.py:38-56` loads a whole collection into memory and `where()` scans it |
| §6.1 identity hierarchy Source → SourceVersion → EvidenceSpan → AtomicAssertion → GovernedNuggetVersion → GrammarBinding → GraphElementVersion | Partly true | five of seven exist (`ka/model.py`); `AtomicAssertion` duplicates the nugget — see "Where I differ" |
| §7 phases 0–5 | Out of scope for research | belongs to `create-implementation-plan` |

## The research

### 1. The publication bridge is `proposals.py`, and KA's compiler becomes a binder

The note's REQ-009 and REQ-011 design a publication contract (`prepare`, `commit`, idempotency keys, optimistic concurrency,
state machine). EOS already has the state machine (`ProposalStatus`, `TRANSITIONS` at `proposals.py:111`), the candidate
validation (`_candidate` :497 refuses new error findings), the human approval (`approve` :560 refuses non-person actors),
the stale-base refusal for promotions (:790) and the preview with affected pinned instances (:719). What EOS does not have
is a client that produces well-formed `ChangeOp`s from governed knowledge. That is the whole of what KA's "compiler"
should become.

Proposal: `GraphChangeService` stops minting elements and emits `ChangeOp`s. For each activated nugget version with a
grammar binding (§2 below):

| binding says | ChangeOps emitted |
|---|---|
| process, new | `add_node{kind: process, props: {process_type?, knowledge_lineage, lineage}}`; `add_edge{contains}` from the bound parent process when evidenced |
| process, existing canonical id | `set_props` on that node — description, `process_type` only if `binding_status == bound`, `knowledge_lineage` appended |
| input / output / acts-on entity | `add_edge{consumes | produces | acts_on}` process → entity; entity by `object_lineage` match, never a new entity without a data proposal (author-only, `proposals.py:1589`) |
| actor, rule, event, state transition | `add_node`/`add_edge` of the matching kind and pair (`performed_by`, `governed_by`, `emits`, `transitions_to`) |
| not evidenced | nothing — EOS reports `process_type.incomplete`; KA records the slot as `not_evidenced` on the binding |

Instance scope → `propose_instance_change(iid, ops, actor=<approver>, reason=<decision reason>)`. Domain scope →
`propose_promotion(sid, base_version=<pinned version KA read>, ops=…)`, which gives KA stale-base protection for free and
leaves repinning to `repin(apply=True)` as EOS already requires. `GraphChangeProposal` in KA keeps its role as the *impact
and approval record* (inheritance effects, overridden descendants, `requires_approval` at `ka/graph_change.py:64-65`) and
gains `eos_proposal_id`, `eos_base_version` and the EOS findings as `validation_results`. Rollback becomes "propose the
inverse ops", because EOS versions are immutable — KA's in-memory `rollback_change` stays for the shadow adapter only.

What this buys: EOS validates kinds, endpoints, depth, typing and provenance with its own checks; a KA bug can at worst
produce a *refused* proposal, never a corrupted graph. What it costs: KA can no longer `apply` into EOS itself — the
`EnterpriseOSGraphAdapter.apply_change` write path (`ka/graph_adapter.py:443-445`) is retired for domain and instance
graphs. That path was never exercised against the live store (plan-01 handoff), so nothing shipped is lost.

### 2. Process assertions are nugget versions with a subject and a binding, not a new layer

The note's §6.1 inserts `AtomicAssertion` between `EvidenceSpan` and `GovernedNuggetVersion`, and `GrammarBinding` after it.
Two of those already exist under other names: `Evidence` *is* the evidence span (locator + excerpt, `ka/model.py:94`), and a
nugget version *is* the atomic, independently governable claim (spec §5; `ka/versioning.py:15` makes it immutable). Adding
an assertion object under the nugget would give the governance pipeline two units to decide on and the console two things
to show for one fact. The note itself says "preserve one nugget or assertion per independently governable claim" (REQ-005):
the right reading is that **the assertion is the nugget**.

Proposal: extend `KnowledgeNuggetVersion` with two optional, typed blocks, and leave `statement` as the human sentence.

```text
subject:   {kind: process|entity|actor|rule|event|state, canonical_key: "merchant_underwriting", aliases: [...]}
predicate: description | decomposes_into | typed_as | consumes | produces | acts_on | performed_by |
           governed_by | emits | transitions | precondition | postcondition | related_to
object:    {kind, canonical_key} | literal value
binding:   {grammar_version: "grammar/v2", type_table_version: "process-types/v2",
            process_type: "decision" | null, slot: "input" | null,
            binding_status: bound | proposed | unresolved | not_applicable,
            method: evidenced | inferred, confidence, alternatives: [...], bound_at}
```

`subject`, `predicate`, `object` are semantic and therefore immutable with the version (join `SEMANTIC_FIELDS`). `binding`
is **not** semantic: it is recomputed when EOS releases a new grammar (REQ-006 acceptance) and written as a new
`GrammarBinding` record keyed by `(nugget_ref, grammar_version, type_table_version)`, so historical versions never change and
a reader can ask "how did v3 bind under process-types/v2 vs v3". The **process profile** of REQ-005 and §6.2 is then a
query — all ACTIVE versions whose `subject.canonical_key` matches, grouped by predicate — rendered by a Processes tab (R12),
exactly the "composed view, not a giant nugget" the note asks for.

Canonical identity (REQ-005 "separate human-readable name from process identity") is the fix for §Why-it-matters 1: the
element id becomes `p.<canonical_key>` and `set_props` enriches it, instead of `p.<slug(title)>` creating a sibling. The
canonical key is proposed by extraction, resolved against existing subjects (same aliases machinery KA's conflict detector
uses for statements, `ka/conflict.py:20-35`) and confirmed in review when confidence is low.

### 3. Extraction becomes two passes, and the second one is where process knowledge comes from

`CandidateExtractor` asks for "discrete, independently governable statements" (`ka/extraction.py:233-256`) — sentences. A
process is not a sentence; it is a structure in the document (a heading with numbered steps, a swim-lane, a RACI table).
Proposal: keep pass one (statements → nuggets of type rule/policy/definition/fact — it works, and it is what governance
compares), and add pass two, **process extraction**, over the same `TextExtraction.sections`:

- input: a section or a window of sections, with their locators;
- output: a list of `(subject, predicate, object, locator, excerpt, confidence, scope_hint)` tuples using the closed
  predicate list above and the closed EOS type list (`TYPE_NAMES`) and slot list (`grammar.json:271`) in the prompt —
  the same "closed lists, one repair, then drop and disclose" discipline EOS already applies to question breakdown
  (`grammar-first-navigation.md` §2–§3);
- every tuple becomes one `CandidateInput`; the heuristic fallback produces `description` and `decomposes_into` tuples from
  numbered lists under a heading, nothing more.

Layout fidelity (REQ-004) is a precondition for pass two to cite correctly: stable span ids (section index + character
offsets inside the stored `SourceVersion.text`), table rows as `table N row M` rather than joined strings
(`ka/extraction.py:140-142` joins cells with " | "), and OCR behind an optional dependency with an explicit
`extraction_version` on `SourceVersion` so re-extraction after an upgrade is a new version, not an overwrite. Image
extraction stays `UNAVAILABLE` (`:72-73`) until an OCR/vision provider is configured; the note's "configurable OCR" is the
right shape.

### 4. Security: match EOS's containment now, decide IAM once, for both repos

REQ-008 is right that nothing personal should enter either service unauthenticated, and right that it is a launch blocker
for any exposure beyond the host. It is wrong to scope it to KA alone: the graph KA publishes into is served by an EOS
backend bound to `0.0.0.0` (`KW/backend/__main__.py:51`) with CORS as its only middleware (`app.py:118`). Authenticating KA
while EOS stays open protects the evidence and leaves the compiled knowledge open.

Two steps, deliberately separated:

1. **Now, in KA, no decision needed**: the same loopback containment EOS uses (`_require_local`, `agent_x_mount.py:2661`) on
   every `/api/knowledge-acquisition/*` route, with a documented warning that it inverts behind a reverse proxy — plus a
   shared service token for KA ↔ EOS calls so the gap seam (R11) and the proposal client (R1) can tell each other apart from
   a browser. Plus the two concrete holes: `upload` reads the whole body with no cap (`ka/api.py:247`; `ka/images.py:17`
   shows the 10 MB pattern to copy) and `link()` follows redirects to any address (`ka/ingestion.py:63`) — an SSRF guard
   (block loopback, link-local, RFC1918, metadata ranges; allowlist option) belongs there before `KA_RESEARCH_INTERNET` is
   ever enabled on a networked host.
2. **Once, as an architecture decision across both repos**: identity provider, tenant model, and what happens to derived
   knowledge after source revocation. The note's "intersection / most restrictive effective audience" rule for multi-source
   nuggets is already KA's rule (`ka/governance.py:112` uses `narrowest_visibility`); what is missing is checking it against a
   *caller*, which needs a caller.

### 5. Connectors and discovery are new modules behind the existing ingestion door

REQ-002's `Connector` contract (`authorize`, `enumerate`, `fetch`, `get_permissions`, `checkpoint`, `sync_incremental`,
`revoke`) is sound and absent. It should sit in a new `ka/connectors/` package whose only exit is
`IngestionService.connect()` / `record_derived()` — the provenance, checksum and versioning rules then apply unchanged, and
"new, modified, moved, deleted" reconcile to "new source / new version / location change on the same source / source
marked revoked" without a second store. The first connector is the local folder (it exercises enumerate, checkpoint and
incremental sync with zero credentials); which cloud and which enterprise provider come next is a decision the note
correctly leaves open (note §10.2).

REQ-003's discovery (query → results → selection → fetch) is a `DiscoveryAgent` placed *before* `InternetResearchAgent` in
the coordinator's list (`ka/research.py` agents list), producing URLs the existing agent fetches. The search provider is a
decision. The gate stays `KA_RESEARCH_INTERNET`; the SSRF guard from §4 is a precondition; `robots.txt` and an allowed-domain
list are the budget controls. The note's rule "never treat model-generated text as a verified internet source" is already
enforced by authority: LLM agents record `LLM_GENERATED` (`ka/research.py:160-170`) and fetched pages record
`INTERNET_RESEARCH` (:208), and the §13 auto-resolution ranks them accordingly.

### 6. The feedback loop needs an EOS decision, not a KA contract

REQ-010 asks for a richer gap request (principal, grammar intent, missing semantics, correlation id). The KA side is cheap:
`GapIn` (`ka/api.py:162`) grows those fields and `KnowledgeAcquisitionRequest` stores them. The hard part is in EOS:
`act_on_gaps` (`KW/gap_v2/act.py:777`) founds and grows graphs under HOTL points that default to `auto`
(`hotl.py:141`). Until EOS routes `found_new` / `grow_existing` through a KA request, KA will receive gaps only from code
nobody has written. The spec is unambiguous (§43, Invariant 1 and 2), the EOS code is unambiguous the other way, and no EOS
architecture document owns the question. This is a `decide` for the author, and it is the one that makes the note's
scenario A10 real.

### 7. Idempotency has to be built on both sides, and it is cheap on KA's side

KA can make publication idempotent without waiting for EOS: an `idempotency_key = sha256(nugget_ref + sorted ops)` stored
on the KA proposal, so a retried `propose_for` finds the existing record and returns it. Against EOS, promotions are safe
today through `base_version` (stale-base refusal), instance changes are not (`_apply_instance` :672 re-applies ops to the
current graph). The EOS-side fix — an optional `base_digest` or idempotency key on `propose_instance_change` — is a small
proposal to EOS, and the note's scenarios A8/A9 cannot pass without it.

### 8. Durable events: use the file you already have

REQ-011 asks for durable, versioned, at-least-once events. Neither repo has a broker; EOS's only bus is the in-process
`LineageChanged` registry. KA's `events.jsonl` (`ka/events.py:1`) is already an append-only, ordered, durable log. The
cheapest correct design is to make it the outbox: add `version` and a monotonic `seq` to each record, expose
`GET /events?after=<seq>`, and let EOS (or anything) consume at-least-once by remembering `seq`. A broker is a decision for
later, with a measured reason.

## Where I differ

1. **"Replace the compiler" (REQ-009) understates the change.** The compiler should not be replaced by a better compiler
   inside KA; it should be removed, and KA should emit `ChangeOp`s into EOS's proposal lifecycle (§1). The note's own
   principal invariant demands this, but its REQ-011 table (`/v1/graph-publications/prepare|commit`) and §10.5 ("ensure
   mutation is executed by EOS … not unreviewed KA direct store writes") read as if a new contract must be negotiated.
   `proposals.py:560,653,719` is the contract. Evidence that the note was written before seeing it: it proposes "optimistic
   concurrency" and "conflict-on-stale" that `stale_base` (:790) already provides for promotions.
2. **The identity hierarchy has one layer too many** (§6.1 `AtomicAssertion`). See §2: the nugget version is the atomic
   claim. Adding a sub-nugget unit would split governance decisions and contradict spec §5's "do not treat the document as
   the minimum governance unit" by introducing a unit *below* the one governance already decides on.
3. **A grammar "descriptor contract" overbuilds what EOS needs** (REQ-006). The artefacts are two JSON files with version
   strings, governed by Q433 as hand-edited and Python-checked. The right exposure is a read-only EOS endpoint that returns
   those files plus a sha256, and a KA cache keyed by `(grammar_version, type_table_version, digest)` that fails closed the
   way `typed_universal()` already does (`structure.py:64`). Designing a separate descriptor schema would create a second
   representation of the grammar — the thing Q433 ruled against.
4. **Five pages (REQ-012) against four tabs.** The author ruled on 2026-10-08 that the console is Add knowledge · Knowledge
   nuggets · Browse by scope · Dashboard (plus Images, added the same day). The note's five pages map onto them with one
   genuine addition: *Sources* is the Add tab's result list plus sync health; *Knowledge* and *Review* are the Knowledge
   nuggets tab's sub-tabs; *Publications* is the graph-change queue now on the Dashboard; **Processes is new** and is the
   profile view of §2. I recommend a Processes tab and a Publications sub-tab, not a re-layout — but this is the author's
   call (R13).
5. **The EOS evidence panel (REQ-013) is not buildable by a plan.** Q418 freezes `console/frontend/**` and the fingerprint
   test fails on any change. It needs a ruling first (R14).
6. **Security is framed as a KA requirement; it is a two-repo decision** (§4). The note's acceptance "cross-tenant access
   tests deny all read/write and inference paths" cannot be met while EOS serves the published graph unauthenticated.
7. **Several REQ-001/REQ-007 items are already true** and should not be re-planned: idempotent re-ingestion, new version on
   change, conflict classification, lowest scope, narrowest visibility (table above). A plan that re-implements them would
   be the "rewrite of the user's note" failure in code.

## Open questions

- **Will EOS route `found_new`/`grow_existing` through KA?** Settles whether scenario A10 is reachable (R11). Evidence: the
  author's ruling; then a test that `act_on_gaps` posts a gap and does not call `compose_substructure`.
- **Which identity provider and tenant model, for both repos?** Settles R4 step 2 and the retention policy after revocation.
- **Which search provider and which first cloud/enterprise connector?** Settles R9 and R10's second connector. Evidence:
  what the business actually uses; credentials available to the deployment.
- **Does EOS accept an idempotency/base key on `propose_instance_change`?** Settles whether A8/A9 are KA-only or need an
  EOS change (R7).
- **Does the JSON-per-object store hold at the expected volume?** `Collection._load` reads every file of a collection into
  memory (`ka/repository.py:45-52`). Evidence: a benchmark at 10k and 100k nuggets before anyone proposes a migration (R16).
- **Will the author re-pin the EOS frontend for a process evidence panel (Q418)?** Settles R14.

## What this does not cover

Phasing, sequencing and work packages — the note's §7, §8 and §12 — belong to `create-implementation-plan`; this report
deliberately gives no build order. Golden-corpus design for process extraction (note §9 quality gates) is test
infrastructure for the plan that builds R3. Operational telemetry thresholds (REQ-014) are "agreed during Phase 0 rather
than guessed", as the note says, and are not researched here. ADR format for the §10 decisions is the author's; the
decisions themselves are listed as `decide` rows below.

## Research points (16)

| # | Research point | Kind | Class | Severity | Where argued |
|---|---|---|---|---|---|
| R1 | Retire KA's element compiler and EOS write path; emit EOS `ChangeOp`s and publish through `propose_instance_change` / `propose_promotion(base_version)`; KA's `GraphChangeProposal` becomes the impact-and-approval record carrying the EOS proposal id and findings | build | PRODUCT | MAJOR | §1, Why 1–2 |
| R2 | Add `subject / predicate / object` (semantic) and a separately-versioned `GrammarBinding` (non-semantic, recomputable per grammar release) to the nugget model; canonical subject keys replace title-slug element ids | build | PRODUCT | MAJOR | §2 |
| R3 | Second extraction pass for process knowledge over sections, with EOS's closed type and slot lists in the prompt and a numbered-list heuristic fallback; `not_evidenced` recorded, never filled | build | PRODUCT | MAJOR | §3 |
| R4 | Security step 1 now: loopback containment on every KA route (EOS pattern), a KA↔EOS service token; step 2 as a two-repo decision: identity provider, tenant model, retention after revocation | build + decide | PRODUCT | MAJOR | §4 |
| R5 | Close the two concrete holes before any networked deployment: body cap on `/sources/upload`, SSRF guard on `link()` and the Internet agent | fix | PRODUCT | MAJOR | §4 |
| R6 | Re-check visibility on upward promotion and on CHANGE_SCOPE so personal/team evidence never reaches a broader scope without an explicit decision field | fix | PRODUCT | MAJOR | §Reading (REQ-007 row) |
| R7 | Idempotency: KA-side content key on proposals; propose to EOS an optional base key on `propose_instance_change` | build + investigate | PRODUCT | MAJOR | §7 |
| R8 | EOS exposes grammar and type table read-only with a sha256; KA caches by version+digest and fails closed on mismatch — no separate descriptor schema | build (EOS) + build (KA) | PRODUCT | MAJOR | §Where I differ 3 |
| R9 | `DiscoveryAgent` ahead of the Internet agent (search provider is a decision); robots and allowed-domain budget; keep the `KA_RESEARCH_INTERNET` gate | build + decide | PRODUCT | MAJOR | §5 |
| R10 | `ka/connectors/` with the note's `Connector` protocol, local folder first; cloud and enterprise providers are a decision | build + decide | PRODUCT | MAJOR | §5 |
| R11 | Decide whether EOS routes `found_new` / `grow_existing` through a KA acquisition request instead of mutating in `act_on_gaps`; grow `GapIn` with principal, intent, correlation id either way | decide + build | PRODUCT | MAJOR | §6 |
| R12 | Processes tab in the KA console: the profile view (subject-grouped ACTIVE assertions, each field linking to its evidence, unknowns shown as such) | build | PRODUCT | MAJOR | §2, §Where I differ 4 |
| R13 | Decide the console shape: keep four tabs + Images and add Processes (recommended), or adopt the note's five pages | decide | PRODUCT | MINOR | §Where I differ 4 |
| R14 | Decide whether to re-pin the EOS console frontend (Q418) for a process evidence panel on `GraphPanel.tsx`'s node card | decide | PRODUCT | MINOR | §Where I differ 5 |
| R15 | Events as an outbox: `seq` + `version` on `events.jsonl` records and `GET /events?after=`; a broker only on measured need | build | PRODUCT | MINOR | §8 |
| R16 | Benchmark the JSON-per-object store at 10k and 100k nuggets before proposing any migration; layout-aware extraction extras (span ids, row/cell locators, `extraction_version`, OCR behind an optional dependency) | investigate + build | PRODUCT | MINOR | §3, Open questions |

**Total research points: 16.** 9 `build`, 3 `decide`, 1 `fix`-only (R5; R6 is also a fix), 1 `investigate`-led (R16); several rows combine a build with the decision that unblocks it (R4, R7, R9, R10, R11).

**Class and severity split:** 16 `PRODUCT`, 0 `TEST INFRASTRUCTURE`; 0 `CRITICAL`, 12 `MAJOR`, 4 `MINOR`. Nothing shipped is
giving a user a wrong answer today — KA is not in production — so no row is CRITICAL; the MAJOR rows are claimed capabilities
(process knowledge into the EOS graph, personal sources, web discovery) that are unreachable as built, plus the identity and
security defects that would corrupt or expose data the first time they are reached.

**Coverage of the source note:** covers all 14 requirements (REQ-001–014), the six §2 limitations, the nine §6.3 invariants
and the seven §10 decisions. Not addressed: §7 phases, §8 agent work allocation and §12 first instruction (implementation
process, not research), §9 quality-gate thresholds (to be measured), and §11 definition of done (restated by the product
tests below).

## Product tests (8)

| # | Product test | Proves | Runnable today? |
|---|---|---|---|
| PT1 | From a synthetic underwriting SOP, KA produces a process subject with a description and five nested activities, each activity bound to one of EOS's ten process types or marked `unresolved`, every populated field linking to a page/section evidence span, and no field filled that the document does not state | R2, R3 | no — needs the plans for R2, R3 |
| PT2 | Approving a domain-scoped process nugget creates an EOS `substructure_promotion` proposal with `base_version` equal to the version KA read; EOS validation reports no `error` findings; after a named person approves and applies, a new substructure version exists and every previously pinned instance still pins the old version | R1, R8 | no — needs R1, R8 |
| PT3 | Submitting the same approved knowledge twice yields one KA proposal and one EOS proposal; the graph has one process node for the subject whether its two source documents titled it differently or not | R1, R2, R7 | no — needs R1, R2, R7 |
| PT4 | A proposal built against a stale domain version is refused by EOS with `stale_base` and KA records it as FAILED with that finding; the graph is unchanged | R1, R7 | no — needs R1 |
| PT5 | A request to any KA route from a non-loopback peer is refused; an upload over the configured cap is refused; `link()` to a loopback, link-local or private address is refused and the Internet agent never fetches it | R4, R5 | no — needs R4, R5 |
| PT6 | A PERSONAL-visibility note's knowledge cannot be promoted to a domain scope or re-scoped broader without a decision whose record names the visibility change | R6 | no — needs R6 |
| PT7 | A mission with a general process question, with discovery enabled and the Internet gate on, yields candidates whose sources are fetched URLs with publisher and retrieval time, none of authority `LLM_GENERATED` presented as an internet source | R9 | no — needs R9 and a search provider decision |
| PT8 | Dropping a changed SOP into the watched local folder produces a new `SourceVersion` of the same source, re-runs extraction, and surfaces the contradiction with the prior version's effective dates in the Knowledge nuggets Conflicts view | R10 | no — needs R10 |

**Total product tests: 8.** None can run today; PT1–PT4 wait on the model and publication plans (R1–R3, R7, R8), PT5–PT6 on
the security and visibility fixes (R4–R6), PT7–PT8 on discovery and the first connector (R9, R10) and their provider
decisions.
