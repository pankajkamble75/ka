# Plan 03 - Process assertions on nuggets, and a grammar registry that binds them to what EOS owns

Created: 2026-10-08 15:05 UTC

## Problem Description

A nugget today carries a sentence (`statement`), a normalized paraphrase and a `knowledge_type`
(`ka/model.py:118-129`). Nothing says *what* the sentence is about in terms Enterprise OS (EOS) can place on its graph: which
process, which predicate (describes / decomposes into / consumes / produces / is performed by …), which object. And nothing
checks a candidate process type against the ten types EOS governs (`knowledge_worker/graph_model/process_types.json`,
`process-types/v2`) or a candidate relation against the fifteen edge pairs and fifteen slots of `grammar.json` (`grammar/v2`).

research-01 R2 asks for `subject / predicate / object` as semantic fields on the nugget version plus a *separately versioned*
`GrammarBinding` that can be recomputed when EOS releases a new grammar without touching governed versions; and for canonical
subject keys with aliases so two documents naming one process resolve to one subject. R8's KA half asks for a grammar registry
that reads the two EOS files by version string and sha256 digest, caches that, and fails closed when the files move under it.

Desired outcome: a candidate can be created with `subject={kind: process, canonical_key: merchant_underwriting}`,
`predicate=typed_as`, `object="decision"`; the binder marks it `bound` (a known type) or `unresolved` ("decisionmaking" is not
a type) with alternatives; a relation predicate maps to the EOS edge and slot it would compile to; a grammar file change with
the same version string makes every binding `stale` and refuses new ones until the registry is refreshed deliberately; and the
nugget detail page shows all of it. Element-id derivation from the canonical key (the last clause of R2) lands in plan-05
with the compiler rewrite, so the protected `ka/graph_change.py` is edited once, not twice.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Nugget versions are immutable; a semantic change is a new version (Inv. 3) | `knowledge-acquisition.md` §4 | ✅ built | **constrained by it** — subject/predicate/object join `SEMANTIC_FIELDS`; bindings live in their own collection so recomputation never writes a governed version |
| One governance pipeline; every channel calls `ingest_candidate` | `knowledge-acquisition.md` §4 | ✅ built | **extends it** — `CandidateInput` carries the assertion fields; the pipeline stores and binds them (Phase 4, protected) |
| Compilation: `KIND_FOR_KNOWLEDGE`, title-slug ids | `knowledge-acquisition.md` §5 | ✅ built | **not touched** — id derivation from canonical keys is plan-05's, said so in R2's coverage row |
| EOS: the grammar is one governed, versioned, hand-edited file checked by Python identifiers (Q433) | EOS `process-typed-graph.md` | precedent | **obeyed** — KA reads the files as they are; no second schema (research-01 §Where-I-differ 3) |
| EOS: one recursive typed Process kind; `props.process_type`; untyped is a warning, missing required slot is `incomplete` | EOS `process-typed-graph.md` (Q408/Q409); `process_types.py:349-392` | precedent | **constrained by it** — binding statuses mirror EOS findings: `unresolved` ≈ `process_type.unknown`, `not_evidenced` ≈ `incomplete` |
| EOS: data grammar core roles and canonical objects are author-only proposals | EOS `data-layer.md` | precedent | **constrained by it** — entity subjects bind to a core role by name only; KA proposes no data object |
| Q7 — EOS exposes grammar read-only with a digest | `questions/knowledge-acquisition.md` Q7 | ❓ open | this plan does NOT need it: the registry reads the files from the checkout (`KA_GRAMMAR_DIR`); the endpoint, when EOS adds it, becomes a second source behind the same registry |
| Q8 — console shape | `questions/knowledge-acquisition.md` Q8 | ❓ open | not needed: this plan adds fields to existing pages only |

**Open questions in the sections this plan touches:** Q7 (not needed, see above); Q8 (not needed). None blocking.

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 ChangeOps into EOS proposals | ⏭️ deferred | plan-05 — rests on this plan's bindings |
| R2 subject/predicate/object + versioned GrammarBinding; canonical keys | ✅ in scope (fields, bindings, canonical keys) | Phases 1–4; **element-id derivation deferred to plan-05** so `graph_change.py` is edited once |
| R3 process extraction pass | ⏭️ deferred | plan-04 — produces the assertions this plan can store |
| R4 security | ✅ shipped | plan-02 (`7388f52`) |
| R5 upload cap, SSRF | ✅ shipped | plan-02 |
| R6 visibility on scope change | ✅ shipped | plan-02 |
| R7 idempotency | ⏭️ deferred | plan-05 |
| R8 grammar + digest (KA half) | ✅ in scope | Phase 1 — registry, digest, fail-closed; EOS half parked Q7 |
| R9 discovery agent | ⏭️ deferred | plan-07 |
| R10 connectors | ⏭️ deferred | plan-08 |
| R11 gap routing | ⏭️ deferred | plan-09 |
| R12 process profile view | ⏭️ deferred | plan-06 — reads the subjects this plan creates |
| R13 console shape | ⏭️ deferred | Q8 parked |
| R14 EOS frontend re-pin | ⏭️ deferred | Q9 parked |
| R15 events outbox | ⏭️ deferred | plan-09 |
| R16 store benchmark; layout extras | ⏭️ deferred | plan-04 / plan-09 |

**Covered here: 2 of 16** (R2 in part, R8 KA half). Deferred: 11. Shipped earlier: 3. Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 SOP → process subject, description, nested typed activities bound or `unresolved`, evidence per field, nothing invented | R2, R3 | still RED — the model and binder exist; the extraction that fills them is plan-04 |
| PT3 one process node whether two documents titled it differently | R1, R2, R7 | still RED — canonical keys exist; id derivation and publication are plan-05 |

## Scope

In: `ka/grammar.py` (registry), `ka/binding.py` (binder), `ka/identity.py` (canonical keys, subject registry), model fields,
`CandidateInput` and `ingest_candidate` storing + binding, `Repository.bindings` / `subjects` collections, API routes, console
nugget detail and Knowledge-nuggets table, test fixture grammar, tests, architecture §2 and §5 notes.

Out: process extraction from documents (plan-04); element ids and EOS publication (plan-05); the EOS grammar endpoint (Q7);
the Processes view (plan-06).

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/governance/` (Inv. 3; verified 2026-10-08 plan-02), touched by Phase 4.
HOW: `GovernanceService.ingest_candidate` (`ka/governance.py:110-145`) copies `subject`, `predicate`, `object` from `CandidateInput`
onto the new `KnowledgeNuggetVersion` (both the new-nugget and the `new_version_from` branches) and, after storing the version,
calls `Binder.bind(version)` so every candidate carries a binding record from birth. `propose_revision` passes the prior
version's assertion fields through unless overridden. `SEMANTIC_FIELDS` in `ka/versioning.py` (a shared dependency of the area)
gains the three fields.
WHY: `ingest_candidate` is the one door into the pipeline (architecture §4); setting the fields after the fact would race
with `analyze()` and bypass the immutability guard for versions created by MERGE/CHANGE_SCOPE/promotion, which all go
through this door.
Regression risk: every candidate creation; the conflict pool and scope decision are unaffected (they read `statement`).
Characterization gap: no test pins that `ingest_candidate` ignores unknown input fields or that `SEMANTIC_FIELDS` is exactly
its current eight names.
Re-verify: governance suites unmodified (`test_plan01_phase2_governance.py`, `test_plan01_phase6_propagation.py`,
`test_plan01_api_console.py`, `test_plan02_security_visibility.py`) + live console: create a note whose candidate carries a
subject and predicate (via the API body), open the nugget — assertion block and binding status shown. Bump the Verified date.

Not protection-driven: the binder is a separate module rather than a method on `GovernanceService` because it is also
called by `rebind_all` on grammar refresh, outside any governance decision.

## Assumptions

- Plan-02 landed (`7388f52`); the tree is as of that commit.
- `KA_GRAMMAR_DIR` defaults to `<KA_ENTERPRISE_OS_ROOT>/knowledge_worker/graph_model`; with neither set, the registry is
  **absent** and every binding is `unresolved` with reason `no grammar loaded` — fail closed, never a guess.
- The registry snapshot (`ka_storage/grammar_snapshot.json`: both version strings, both sha256 digests, loaded-at) is the
  reference. `refresh()` is deliberate (API/CLI). Reading files whose digest differs from the snapshot with the **same**
  version string is a mismatch: the registry marks itself `stale`, `bind()` returns `stale` bindings, and `refresh(force=True)`
  is the only way forward. A new version string with a new digest is a normal release: refresh re-reads and `rebind_all`
  writes new binding records.
- Predicates are a closed list: `description`, `typed_as`, `decomposes_into`, `consumes`, `produces`, `acts_on`,
  `performed_by`, `governed_by`, `emits`, `transitions_to`, `precondition`, `postcondition`, `related_to`. The mapping to
  EOS edges and slots is a table in `ka/binding.py` (`consumes`→edge `consumes`, slot `input`; `produces`→`produces`/`output`;
  `acts_on`→`acts_on`/`entity`; `performed_by`→`performed_by`/`actor`; `governed_by`→`governed_by`/`rule`;
  `emits`→`emits`/`event`; `transitions_to`→`transitions_to`/`target_state`; `decomposes_into`→`contains`/`action`;
  `typed_as`→prop `process_type`; `description`/`precondition`/`postcondition`/`related_to`→prop fallback, no edge).
- A subject has `kind` ∈ EOS node kinds ∪ {`process`}, a `canonical_key` (slug), a display `name`, `aliases`. The subject
  registry is a collection; resolution is exact key, then alias, then normalized-name similarity ≥ `KA_DUPLICATE_THRESHOLD`
  within the same kind, else a new subject. Scope is not part of identity: "merchant underwriting" is one subject whether
  the claim is domain- or instance-scoped.
- Binding `method` is `evidenced` when the predicate/object came from extraction or a person, `inferred` when the binder
  filled the slot from the predicate table. `confidence` for a `bound` type is 1.0 on exact match, else the best alias
  similarity; `alternatives` lists the top three types by name similarity for an `unresolved` type.
- The console shows the assertion and binding on the nugget detail page and a subject column in the Knowledge-nuggets
  table; no new tab (Q8).

## Phases

### Phase 1 - Grammar registry (R8 KA half)

- `ka/grammar.py`: `GrammarRegistry(dir, snapshot_path)` with `load()` (reads `grammar.json`, `process_types.json`; sha256 of
  each; validates the version strings start with `grammar/` and `process-types/`), `descriptor()` (versions, digests,
  node kinds, edge pairs with from/to, slots, type names, per-type slot levels), `is_stale()`, `refresh(force=False)`,
  `types()`, `slot_for_edge(edge)`, `edge_spec(name)`, `type_grammar(name)`. Snapshot persisted via `ka.json_io`.
- `ka/config.py`: `KA_GRAMMAR_DIR` (str, "").
- `ka/tests/fixtures/grammar/` — a **small** fixture pair in the real shape (3 node kinds subset is NOT allowed: keep all 10
  kinds and the 15 slots, but only 3 types and 6 edge pairs) so tests do not depend on the checkout; one integration test
  reads the real files when the checkout is present.
- **Protected-code touched:** none

### Phase 2 - Model: assertion fields, binding record, subjects

- `ka/model.py`: `Subject(kind, canonical_key, name, aliases)`, `ObjectRef(kind|None, canonical_key|None, value|None)`,
  `KnowledgeNuggetVersion.subject / predicate / object` (optional), `GrammarBinding(id, nugget_ref, grammar_version,
  type_table_version, digest, process_type, edge, slot, binding_status ∈ {bound, proposed, unresolved, not_applicable, stale},
  method, confidence, alternatives, reasons, bound_at)`, `SubjectRecord(canonical_key, kind, name, aliases, created_at,
  first_ref)`.
- `ka/vocab.py`: `PREDICATES` (closed list) and `BindingStatus`.
- `ka/repository.py`: `bindings`, `subjects` collections; `binding_for(ref)` (latest by `bound_at`), `bindings_of(ref)`,
  `subject(key)`, `nuggets_by_subject(key)`.
- `ka/versioning.py`: `SEMANTIC_FIELDS += ("subject", "predicate", "object")`; `diff()` shows them.
- **Protected-code touched:** none (`ka/versioning.py` is a shared dependency of `ka/governance/`; the change is additive and is
  covered by the characterization in Phase 4 — see N3)

### Phase 3 - Identity and binder

- `ka/identity.py`: `canonical_key(name)`, `SubjectRegistry(repo)` with `resolve(kind, name, aliases=()) -> (SubjectRecord,
  created: bool)` using exact key, alias, then similarity; `add_alias(key, alias)`.
- `ka/binding.py`: `Binder(registry, repo)` with `bind(version) -> GrammarBinding` per the predicate table and assumptions;
  `rebind_all() -> int` writing a new record per ACTIVE/PENDING version under the current grammar; `PREDICATE_TABLE`.
- **Protected-code touched:** none

### Phase 4 - Pipeline integration (protected)

1. **Declare.** `ka/governance.py::ingest_candidate` and `propose_revision`; `CandidateInput` gains `subject`, `predicate`,
   `object`; `GovernanceService.__init__` takes a `Binder`. Why protected path: see summary.
2. **Characterize first** (own commit): P8 — a candidate created today has `subject is None`, `predicate is None`,
   `object is None` and no binding record; N3 — `SEMANTIC_FIELDS` today is exactly the eight names of plan-02's tree, and
   `save()` refuses a `statement` edit on a governed version.
3. **Add coverage before the change**: N4 — `ingest_candidate` with a predicate outside `PREDICATES` raises `GovernanceError`
   (written red, goes green with the change); P9 — `propose_revision` of a version with a subject keeps the subject on v2.
4. **Change** per Declare; `KnowledgeAcquisition` (`ka/service.py`) constructs `GrammarRegistry`, `SubjectRegistry`, `Binder`
   and hands the binder to governance; `nugget_detail` includes `assertion`, `binding`, `bindings_history`, `subject`.
5. **Existing covering tests pass UNMODIFIED**: N7.
6. **Re-verify live**: the console flow in the summary.
7. **Bump `Verified:`** for `ka/governance/` in `docs/protected.md`.
- **Protected-code touched:** ⚠️ `ka/governance/` — `ingest_candidate`, `propose_revision`, `CandidateInput`; shared dependency
  `SEMANTIC_FIELDS` (`ka/versioning.py`).

### Phase 5 - API, console, docs

- `ka/api.py`: `GET /grammar` (descriptor + stale flag), `POST /grammar/refresh` (`force` body), `GET /nugget/{ref}/binding`,
  `POST /nugget/{ref}/rebind`, `POST /grammar/rebind-all`, `GET /subjects`, `GET /subjects/{key}` (record + nuggets);
  `NoteIn`/`PasteIn` unchanged; new `AssertionIn` fields (`subject_kind`, `subject_name`, `predicate`, `object_value`,
  `object_kind`, `object_name`) accepted by `POST /sources/note` and by `propose-revision` so a person can state an assertion.
- `ka/console/app.js`: nugget detail "Process assertion" card (subject · predicate · object; binding status pill with
  reasons/alternatives; grammar versions; Rebind button); Knowledge-nuggets table shows the subject key; Dashboard shows
  grammar versions + stale warning with a Refresh button.
- `docs/architecture/knowledge-acquisition.md` §2 (objects) and new §5a "Grammar binding"; README one paragraph.
- **Protected-code touched:** none

## Code blocks (B1..B10)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/grammar.py` | the registry: load, digest, snapshot, stale detection, descriptor, lookups |
| B2 | `ka/binding.py` | predicate table, binder, rebind_all |
| B3 | `ka/identity.py` | canonical keys and subject resolution |
| B4 | `ka/model.py` | `Subject`, `ObjectRef`, assertion fields, `GrammarBinding`, `SubjectRecord` |
| B5 | `ka/vocab.py` | `PREDICATES`, `BindingStatus` |
| B6 | `ka/repository.py` | `bindings`/`subjects` collections and queries |
| B7 | `ka/versioning.py` | `SEMANTIC_FIELDS` extension and `diff` |
| B8 | `ka/governance.py` | `CandidateInput` fields; storing and binding in `ingest_candidate`; `propose_revision` pass-through |
| B9 | `ka/service.py` | registry/binder wiring; `nugget_detail` additions |
| B10 | `ka/api.py` | grammar, binding, subject routes; `AssertionIn` |
| B11 | `ka/console/app.js` | assertion card, binding pill, subject column, grammar status |
| B12 | `ka/config.py` | `KA_GRAMMAR_DIR` |

## Deliverables (D1..D12)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `GrammarRegistry` with `load`, `descriptor`, `is_stale`, `refresh`, `slot_for_edge`, `type_grammar` | `ka/grammar.py` | 1 |
| D2 | `KA_GRAMMAR_DIR` setting | `ka/config.py` | 1 |
| D3 | fixture grammar pair in the real shape | `ka/tests/fixtures/grammar/grammar.json`, `process_types.json` | 1 |
| D4 | `Subject`, `ObjectRef`, `GrammarBinding`, `SubjectRecord`; `subject/predicate/object` on the version | `ka/model.py` | 2 |
| D5 | `PREDICATES`, `BindingStatus` | `ka/vocab.py` | 2 |
| D6 | `bindings`, `subjects` collections; `binding_for`, `bindings_of`, `nuggets_by_subject` | `ka/repository.py` | 2 |
| D7 | `SEMANTIC_FIELDS` includes the three assertion fields | `ka/versioning.py` | 2 |
| D8 | `canonical_key`, `SubjectRegistry.resolve` | `ka/identity.py` | 3 |
| D9 | `Binder.bind`, `Binder.rebind_all`, `PREDICATE_TABLE` | `ka/binding.py` | 3 |
| D10 | `CandidateInput.subject/predicate/object`; `ingest_candidate` stores and binds; `propose_revision` pass-through | `ka/governance.py` | 4 |
| D11 | routes `/grammar`, `/grammar/refresh`, `/grammar/rebind-all`, `/nugget/{ref}/binding`, `/nugget/{ref}/rebind`, `/subjects`, `/subjects/{key}`; `AssertionIn` on note and revision | `ka/api.py` | 5 |
| D12 | console assertion card, binding pill, subject column, grammar status | `ka/console/app.js` | 5 |

**Total deliverables: 12.**

## Positive Test Cases (P1..P12)

- **P1** — the registry loads the fixture pair: versions `grammar/v2` and `process-types/v2`, 10 node kinds, 15 slots, the fixture's 3 types; digests are 64-hex; the snapshot file exists.
- **P2** — the registry loads the REAL EOS files when the checkout is present (skip otherwise): 10 types, 15 edge pairs.
- **P3** — `typed_as decision` on a process subject → `bound`, confidence 1.0, `process_type == "decision"`, grammar versions recorded.
- **P4** — `consumes merchant_application` → `bound` with `edge == "consumes"`, `slot == "input"`, method `inferred` for the slot.
- **P5** — `description` → `not_applicable` (prop fallback, no edge), still recorded with versions.
- **P6** — `SubjectRegistry.resolve("process", "Merchant Underwriting")` then `resolve("process", "Underwrite merchant applications", aliases=["merchant underwriting"])` return the same record (alias hit), and a third unrelated name creates a new one.
- **P7** — a grammar release (new version string, new digest) followed by `refresh()` and `rebind_all()` leaves every historical binding record intact and adds one new record per ACTIVE/PENDING version; the governed versions are byte-identical before and after.
- **P8** — characterization: today `ingest_candidate` leaves `subject/predicate/object` None and creates no binding (pinned before Phase 4).
- **P9** — `propose_revision` of a version with a subject produces a v2 carrying the same subject and predicate and a fresh binding.
- **P10** — `GET /nugget/{ref}` includes `assertion` and `binding`; `GET /grammar` reports versions and `stale: false`; `GET /subjects/{key}` lists the nugget.
- **P11** — `POST /sources/note` with `subject_name="Merchant underwriting"`, `predicate="typed_as"`, `object_value="decision"` yields a candidate whose binding is `bound`.
- **P12** — console: the nugget detail page renders the assertion card and the binding pill (live flow, `e2e/plan03_binding_flow.py`).

## Negative Test Cases (N1..N9)

- **N1** — `typed_as decisionmaking` → `unresolved`, `alternatives` lead with `decision`, reasons name the type table version.
- **N2** — files changed under the same version string → `is_stale()` True; `bind()` returns `stale`; `refresh()` without `force` raises `GrammarMismatch`; `refresh(force=True)` re-reads and clears it.
- **N3** — characterization: `SEMANTIC_FIELDS` today is exactly plan-02's eight names and `save()` refuses a `statement` edit on a governed version (pinned before Phase 4; after Phase 4 the same test asserts the eleven names — so it is written as two cases, N3a pre-change and N3b post-change, both named here).
- **N4** — `ingest_candidate` with `predicate="frobnicates"` → `GovernanceError`; with a subject whose kind is not an EOS node kind → `GovernanceError`.
- **N5** — no grammar directory configured → every binding `unresolved` with reason `no grammar loaded`; `GET /grammar` reports `loaded: false`; nothing raises on candidate creation.
- **N6** — editing `subject` on a governed version through `versioning.save` → `ImmutableVersionError`; writing a binding record for it is allowed.
- **N7** — regression gate: every covering test for `ka/governance/` passes UNMODIFIED.
- **N8** — `POST /grammar/refresh` from a research-agent principal is not a thing (no `by`); but `POST /grammar/refresh` with `force=false` on a stale registry → 409 with the mismatch detail.
- **N9** — `rebind_all` on a stale registry refuses (`GrammarMismatch`) and writes nothing.

## Plan totals

**Research points covered: 2 of 16 · Deliverables: 12 · Positive cases: 12 · Negative cases: 9 (N3 counted once; written as
N3a/N3b) · Test cases total: 21 · Product tests served: 2 of 8 (0 turn green here).**

## Implementation Notes

- **Re-check this plan against the tree before implementing.** It was written after plan-02 landed (`7388f52`); nothing
  later has landed, but confirm `SEMANTIC_FIELDS` still has eight names and `CandidateInput` still has no assertion fields.
- Phase 4's characterization (P8, N3a) lands in its own commit before any governance change.
- The fixture grammar must be in the real shape so plan-04 and plan-05 can reuse it; copy the real files' top-level keys and
  trim the lists, never invent new keys.
- Live flow for P12: create a note via the API with assertion fields, open `#/nugget/<ref>` headlessly, assert the card.
