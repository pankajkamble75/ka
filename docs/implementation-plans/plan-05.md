# Plan 05 - Publish through EOS: KA emits ChangeOps into the proposal lifecycle, keyed by canonical identity, idempotently

Created: 2026-10-08 16:05 UTC

## Problem Description

KA compiles governed knowledge into graph elements itself: `GraphChangeService._changes_from` (`ka/graph_change.py:75-126`)
mints an element id from a title slug (`:97`), carries the statement and the first number as props (`_value_props`, `:34-40`),
and `apply` writes through `EnterpriseOSGraphAdapter.apply_change` (`ka/graph_adapter.py:405-445`), which calls
`put_instance_graph` / `put_substructure` directly — bypassing EOS's proposal lifecycle, its named-person approval and its
stale-base refusal. Two nuggets about one process with different titles become two elements (research-01 §Why-it-matters 1).

EOS already owns the publication contract (research-01 §1): `propose_instance_change(instance_id, ops, *, actor, reason)`
returns an `awaiting_approval` proposal under `KW_HOTL_MODE=human`; `propose_promotion(substructure_id, base_version, *, ops,
actor, reason)` previews with `pinned_instances`; `request_approval`, `approve(pid, *, actor)` and `apply(pid)` move it to
`applied`; a promotion writes a new immutable substructure version and leaves instance pins alone. Measured in a temporary
store this session: an instance `set_props` + `add_node` carrying `knowledge_lineage` round-trips to `applied`; a domain
promotion from base `"1"` yields version `"2"` with `pins: {'ka-inst': '1'}`; a second promotion on the stale base is
accepted at propose time (the `stale_base` refusal is at apply).

Desired outcome: an activated nugget with a subject becomes `ChangeOp`s on a node whose id is `p.<canonical_key>` (so a
second document about the same process updates that node), published through EOS proposals by the KA approver's name,
with KA's `GraphChangeProposal` as the impact-and-approval record carrying the EOS proposal id, base version, findings and
`pinned_instances`; a retry of the same knowledge produces no second proposal (content key); a stale base is reported as
FAILED with `stale_base`; the in-memory adapter keeps working for the standalone console and tests. R2's last clause
(canonical-key ids) lands here, as plan-03 promised.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Inv. 2: no semantic graph mutation without governed lineage; compilation via proposals (§5) | `knowledge-acquisition.md` §1, §5 | ✅ built (KA-side compiler) | **rebuilds it** — the compiler becomes a ChangeOp emitter; §5 rewritten on upload |
| Research-01 §1: the publication bridge IS `proposals.py`; KA's EOS write path is retired | `research-01.md` §1, R1 | decided by the report, not built | **builds it** |
| Research-01 §2: canonical subject keys replace title-slug ids | `research-01.md` §2, R2 (last clause) | ⏳ decided, not built (plan-03 deferred it here) | **builds it** |
| Grammar binding: `bound` means the type/edge is in the loaded grammar; never coerce | `knowledge-acquisition.md` §5a | ✅ built | **constrained by it** — only `bound` bindings produce `process_type` props or edges; `proposed`/`unresolved` produce nothing |
| EOS: substructure versions immutable; instances pin; no silent repin (R15/Q409) | EOS `process-typed-graph.md` | precedent | **obeyed** — a domain publication is a promotion; repin is reported, never done (Q2) |
| EOS: a proposal is approved by a named person; "system"/"automation"/"hotl:" refused | EOS `proposals.py::approve` | precedent | **obeyed** — KA passes the human who approved the KA proposal as `actor` |
| EOS: validation never raises; the store refuses error findings | EOS `validate.py:38`, `errors.py:23` | precedent | **obeyed** — `ProposalRefused` / `GraphRejected` become KA `validation_results` and FAILED |
| Q2 — who repins instances after a domain write | `questions/knowledge-acquisition.md` Q2 | ❓ open | this plan does NOT need it: the proposal lists `pinned_instances` and says "repin required"; repinning is not performed |
| Q7 — EOS base key on instance changes | `questions/knowledge-acquisition.md` Q7 | ❓ open | this plan does NOT need it: KA's content key covers retries on KA's side; EOS instance changes stay last-writer |

**Open questions in the sections this plan touches:** Q2, Q7 — neither needed (see rows). None blocking.

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 ChangeOps into EOS proposals; KA write path retired | ✅ in scope | Phases 2–4 |
| R2 canonical keys replace slug ids (last clause) | ✅ in scope | Phase 2; the rest shipped in plan-03 |
| R3 process extraction | ✅ shipped | plan-04 (`0ddf147`) |
| R4 / R5 / R6 | ✅ shipped | plan-02 (`7388f52`) |
| R7 idempotency — KA content key | ✅ in scope | Phase 3; EOS half parked Q7 |
| R8 grammar registry | ✅ shipped | plan-03 (`27d187d`) |
| R9 discovery | ⏭️ deferred | plan-07 |
| R10 connectors | ⏭️ deferred | plan-08 |
| R11 gap routing | ⏭️ deferred | plan-09 |
| R12 process profile view | ⏭️ deferred | plan-06 |
| R13 / R14 decisions | ⏭️ deferred | Q8 / Q9 parked |
| R15 outbox | ⏭️ deferred | plan-09 |
| R16 benchmark half | ⏭️ deferred | plan-09 |

**Covered here: 3 of 16** (R1, R2 last clause, R7 KA half). Deferred: 7. Shipped earlier: 6. Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT2 approving a domain-scoped process nugget creates an EOS promotion with `base_version` = the version KA read; no error findings; after a named person approves and applies, a new version exists and pinned instances still pin the old one | R1, R8 | **GREEN** — this plan is what makes it true (run from the EOS interpreter against a temp store) |
| PT3 the same approved knowledge twice → one KA proposal and one EOS proposal; one process node for the subject whether two documents titled it differently | R1, R2, R7 | **GREEN** — this plan |
| PT4 a proposal built against a stale domain version is refused by EOS with `stale_base`; KA records FAILED; the graph is unchanged | R1, R7 | **GREEN** — this plan |

## Scope

In: `ka/graph_change.py` (rewrite of `_changes_from` → `ChangeOp` emission by canonical identity; `apply` through a
publisher; idempotency key; stale handling), `ka/graph_adapter.py` (`publish` on the protocol; in-memory publish = apply;
EOS adapter publishes through `proposals.py`, `apply_change` retired), `ka/model.py` (`GraphChangeProposal.idempotency_key`,
`eos_proposal_id`, `eos_base_version`, `eos_status`, `pinned_instances`, `ops`), `ka/config.py` (`KA_EOS_ACTOR_FALLBACK` —
no: the approver's name is used; see assumptions), tests on both adapters, architecture §5 rewrite, `docs/protected.md`.

Out: repinning instances (Q2); the EOS idempotency key (Q7); Structure-tier publication (author-only in EOS);
data-object proposals (author-only); the process profile view (plan-06).

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/graph_change/` (Inv. 2; verified 2026-10-08 plan-01), touched by Phases 2–4.
HOW: `_changes_from` is replaced by `emit_ops(version, report) -> list[ElementChange]` whose element ids derive from the
subject's canonical key and whose edges come from `bound` bindings; `propose_for` computes `idempotency_key` and returns
an existing live proposal on a match; `apply` calls `adapter.publish(...)` and records the EOS result; `rollback` publishes
inverse ops. `validate` keeps the Invariant-2 check (every op carries `knowledge_lineage`).
WHY: the compiler IS the protected area; there is no non-protected path to a different compiler.
Regression risk: every activation (auto-approve path in tests); every apply; rollback.
Characterization gap: no test pins the slug id itself (`r.refunds_above_500_require_manager_approval`) as the current
element id, nor that a second nugget about the same subject creates a second element today.
Re-verify: phase3 + phase6 suites unmodified; live: approve a process nugget in the console, open the proposal, see ops and
the publication record. Bump the Verified date.

⚠️ TOUCHES PROTECTED — `ka/graph_change/`'s Invariant-2 twin in the adapters (`validate_change`, `docs/protected.md` lists
the adapter validators as covering the same invariant), touched by Phase 4: the EOS adapter's `apply_change` is retired in
favour of `publish`; `validate_change` unchanged.

Not protection-driven: `publish` is added to the adapter protocol rather than making `GraphChangeService` know about
`proposals.py`, because the in-memory adapter must keep the standalone console and the suite working without EOS.

## Assumptions

- Plans 02–04 landed (`0ddf147`); `KnowledgeNuggetVersion.subject`, bindings and the grammar registry exist.
- **Element identity**: subject kind → prefix (`process`→`p.`, `entity`→`e.`, `actor`→`ac.`, `rule`→`r.`, `event`→`ev.`,
  `state`→`s.`, `attribute`→`a.`, `metric`→`m.`, `goal`→`g.`, `physical_source`→`ps.`); id = `<prefix><canonical_key>`. A
  `decomposes_into` child process gets `p.<parent_key>.<child_key>` and a `contains` edge. Statement-only nuggets (no subject)
  keep today's `r.<slug(title)>` — unchanged behaviour, out of R2's scope, noted.
- **Ops per predicate** (only when the binding is `bound`): `typed_as` → `set_props{process_type}` on the subject node;
  relation predicates → `add_node` for the object when absent (kind from the binding/object) + `add_edge{<edge>}` with id
  `<edge>:<src>-><tgt>`; `description` → `set_props{description}`; everything else → `set_props{statement}` only. Every op's
  props carry `knowledge_lineage` entries (merged: other nuggets' entries kept, this canonical id's replaced).
- **Publication**: KA `apply` requires a KA-approved proposal (unchanged). `adapter.publish(scope, changes, actor, reason,
  base_version)` → in-memory: applies and returns `{"applied": True}`; EOS: INSTANCE scope → `propose_instance_change`, then
  `approve(actor=<KA approver>)` + `apply` when EOS left it `awaiting_approval` (HOTL `human`), or just read the status when
  HOTL `auto` applied it; DOMAIN scope → `propose_promotion(base_version)` → `request_approval` → `approve` → `apply`; the
  result carries `eos_proposal_id`, `eos_status`, `new_version`, `pinned_instances`. `ProposalRefused` / `GraphRejected` →
  KA FAILED with the code and findings in `validation_results`.
- **Actor**: the `by` of KA's `approve` (a person's name from the console "You" field). EOS refuses "system"/"automation";
  KA's auto-approval (`auto_approve_low_impact`) therefore publishes under `KA_EOS_AUTO_ACTOR` only if that setting names a
  person, else the proposal stays APPROVED-not-applied with a note. Setting declared in `ka/config.py`.
- **Base version**: for DOMAIN scope, read at proposal time from `store.versions(sid)[-1].version` and stored as
  `eos_base_version`; `stale_base` at apply → FAILED, retryable by re-proposing (new key because the base changed).
- **Idempotency key** = sha256 over sorted nugget refs + canonical JSON of ops (ids, op, props without timestamps). A live
  proposal (PROPOSED/VALIDATING/READY/APPROVED/APPLIED) with the same key is returned instead of a new one.
- **Descendants under EOS**: a domain promotion lists `pinned_instances` as `inheritance_effects` with action "repin required
  (Q2)"; KA performs no repin and no per-instance ops for realized copies. Under the in-memory adapter the plan-01 propagation
  to INHERITED copies continues (it is the shadow of what repin would do).
- EOS-path tests run under the EOS interpreter against a temporary `KW_STORAGE_ROOT` with `KW_HOTL_MODE=human`, like
  `test_plan01_enterprise_os_adapter.py`; they skip in the plain suite.

## Phases

### Phase 1 - Model and settings

- `ka/model.py`: `GraphChangeProposal.idempotency_key`, `ops` (the EOS-shaped ops as dicts), `eos_proposal_id`, `eos_base_version`,
  `eos_status`, `new_version`, `pinned_instances`; `ElementChange.op` (`add_node|set_props|remove_node|add_edge|remove_edge`) and
  `edge` (`kind, source, target`) for edge changes.
- `ka/config.py`: `KA_EOS_AUTO_ACTOR` (str, "").
- **Protected-code touched:** none

### Phase 2 - Emit ops by canonical identity (protected)

1. **Declare.** `ka/graph_change.py`: `emit_ops` replaces `_changes_from`; `element_id_for(subject)`; `_value_props` keeps the
   statement; new `_ops_for_assertion`. Why: the compiler is the protected area.
2. **Characterize first** (own commit): P6 — today a rule nugget compiles to `r.<slug(title)>`; P7 — today two nuggets with
   the same subject and different titles create two elements under the in-memory adapter; P8 — today `apply` registers one
   dependency per changed element and `rollback` restores `before`.
3. **Add coverage before the change**: N4 — a change without `knowledge_lineage` is refused by both adapters (exists:
   phase3 `::test_N1`; re-asserted on ops); N5 — a `proposed`/`unresolved` binding yields no `process_type` and no edge
   (written red, goes green with the change).
4. **Change** per the assumptions; `ElementChange` gains `op`/`edge`; `to_change_ops(changes)` converts to EOS dicts.
5. **Existing covering tests pass UNMODIFIED**: N7.
6. **Re-verify live**; 7. **bump `Verified:`**.
- **Protected-code touched:** ⚠️ `ka/graph_change/`

### Phase 3 - Idempotency and the publication record (protected)

- `propose_for`: compute the key; return the live match; store `ops`; for DOMAIN scope read `eos_base_version` through
  `adapter.base_version(scope)` (in-memory: `None`).
- `apply`: `result = adapter.publish(scope, changes, actor=by, reason=p.reason, base_version=p.eos_base_version)`; record
  `eos_*` fields and `pinned_instances`; FAILED on `PublishRefused` with `validation_results += [{code, detail}]`; lineage
  registration unchanged (uses the elements the adapter reads back).
- `rollback`: publishes the inverse ops as a new publication (EOS) or applies them (in-memory); records the rollback execution.
- Auto-approval: when `auto_approve_low_impact` and no person is available, `apply` is skipped and the proposal stays APPROVED
  with `impact_summary["note"] = "awaiting a named approver (KA_EOS_AUTO_ACTOR unset)"`.
- **Protected-code touched:** ⚠️ `ka/graph_change/` (same characterization commit as Phase 2)

### Phase 4 - Adapters publish

- `ka/graph_adapter.py`: protocol gains `publish(...) -> PublishResult` and `base_version(scope) -> str | None`;
  `PublishRefused(code, detail, findings)`; in-memory `publish` = validate + apply, `base_version` = None; EOS adapter
  `publish` per the assumptions (`proposals.propose_instance_change` / `propose_promotion` + `request_approval` + `approve` +
  `apply`, errors mapped), `base_version` = latest substructure version, `apply_change` → raises `NotImplementedError("publish")`,
  `rollback_change` likewise; `validate_change` unchanged.
- **Protected-code touched:** ⚠️ the adapters' Invariant-2 validators are not changed; the EOS write path is retired — named here
  because `docs/protected.md` lists the validators under `ka/graph_change/`'s covering tests.

### Phase 5 - Console, docs, EOS-path tests

- `ka/console/app.js`: the graph-change page shows `ops`, `eos_proposal_id`, `eos_status`, `new_version`, `pinned_instances`
  with the "repin required" note, and the idempotency key.
- `docs/architecture/knowledge-acquisition.md` §5 rewritten (emission, identity, publication, idempotency, repin as Q2);
  `docs/protected.md` row for `ka/graph_change/` names `publish` and the EOS test.
- `ka/tests/test_plan05_eos_publication.py` (EOS interpreter only): temp store, typed-or-universal domain, PT2/PT3/PT4.
- **Protected-code touched:** none

## Code blocks (B1..B5)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/graph_change.py` | `emit_ops`, identity, idempotency key, publish-based apply/rollback, auto-actor rule |
| B2 | `ka/graph_adapter.py` | `publish`/`base_version` on the protocol and both adapters; `PublishRefused`; EOS write path retired |
| B3 | `ka/model.py` | proposal publication fields; `ElementChange.op`/`edge` |
| B4 | `ka/config.py` | `KA_EOS_AUTO_ACTOR` |
| B5 | `ka/console/app.js` | publication record on the graph-change page |

## Deliverables (D1..D10)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `GraphChangeProposal.idempotency_key/ops/eos_proposal_id/eos_base_version/eos_status/new_version/pinned_instances`; `ElementChange.op/edge` | `ka/model.py` | 1 |
| D2 | `KA_EOS_AUTO_ACTOR` | `ka/config.py` | 1 |
| D3 | `element_id_for(subject)` and `emit_ops(version, report)` (canonical-key ids; ops only from `bound` bindings) | `ka/graph_change.py` | 2 |
| D4 | `to_change_ops(changes)` → EOS-shaped dicts | `ka/graph_change.py` | 2 |
| D5 | `idempotency_key_for(refs, ops)`; `propose_for` returns the live match | `ka/graph_change.py` | 3 |
| D6 | `apply` publishes via the adapter and records the EOS result; `stale_base`/refusal → FAILED | `ka/graph_change.py` | 3 |
| D7 | `rollback` publishes inverse ops | `ka/graph_change.py` | 3 |
| D8 | `GraphAdapter.publish`, `base_version`, `PublishRefused`; in-memory publish | `ka/graph_adapter.py` | 4 |
| D9 | `EnterpriseOSGraphAdapter.publish` through `proposals.py`; `apply_change` retired | `ka/graph_adapter.py` | 4 |
| D10 | console publication record; architecture §5; protected.md | `ka/console/app.js`, docs | 5 |

**Total deliverables: 10.**

## Positive Test Cases (P1..P12)

- **P1** — a `typed_as decision` nugget (bound) on subject `merchant_underwriting` activates into `add_node p.merchant_underwriting` with `props.process_type == "decision"` and `knowledge_lineage`; a second, differently titled nugget about the same subject yields `set_props` on the same id (in-memory).
- **P2** — a `decomposes_into` nugget yields `add_node p.merchant_underwriting.collect_application` (kind process) and `add_edge contains:p.merchant_underwriting->p.merchant_underwriting.collect_application`.
- **P3** — a `performed_by` nugget yields `add_node ac.underwriting_team` and `add_edge performed_by:…`; `consumes` yields an entity node and a `consumes` edge.
- **P4** — the same knowledge proposed twice → one KA proposal (same `idempotency_key`), returned by `propose_for`.
- **P5** — `to_change_ops` renders `[{"op":"add_node","node":{…}}, {"op":"set_props","id":…,"props":{…}}, {"op":"add_edge","edge":{…}}]` in EOS's shape.
- **P6** — characterization: today a rule nugget compiles to `r.refunds_above_500_require_manager_approval` (pinned before).
- **P7** — characterization: today two nuggets with the same subject and different titles create two elements (pinned before; after the change the same test asserts ONE — written as P7a/P7b).
- **P8** — characterization: `apply` registers one dependency per element and `rollback` restores `before` (holds before and after).
- **P9** — EOS path (temp store, HOTL human): activating a domain process nugget with `auto_approve_low_impact` off → KA READY; approve by "Pankaj Kamble"; `apply` → EOS promotion `applied`, `new_version == "2"`, `pinned_instances == ["ka-inst"]`, the instance still pins `"1"`; `eos_base_version == "1"` (PT2).
- **P10** — EOS path: an instance-scoped nugget publishes through `propose_instance_change` → `applied`; the realized node carries `knowledge_lineage` (read back through the adapter).
- **P11** — EOS path: proposing the same knowledge twice yields one KA proposal and one EOS proposal id; one `p.merchant_underwriting` node (PT3).
- **P12** — console live flow: approve a process nugget, open the graph change, see ops and the publication record (`e2e/plan05_publication_flow.py`).

## Negative Test Cases (N1..N9)

- **N1** — EOS path: a second domain proposal built on base `"1"` after version `"2"` exists → KA FAILED with `stale_base` in `validation_results`; `store.versions` unchanged (PT4).
- **N2** — ops with a `node` lacking `knowledge_lineage` are refused by `validate` before any publish (in-memory and EOS).
- **N3** — EOS `ProposalRefused` (an op whose edge endpoints violate the grammar) → KA FAILED with the code; nothing applied.
- **N4** — a change without lineage is refused by both adapters (re-asserted on ops).
- **N5** — a `proposed` or `unresolved` binding yields no `process_type` and no edge; the node still gets `statement` and lineage.
- **N6** — auto-approved proposal with `KA_EOS_AUTO_ACTOR` unset under the EOS adapter stays APPROVED, not applied, with the note; under the in-memory adapter it applies (no actor rule).
- **N7** — regression gate: every covering test for `ka/graph_change/` passes UNMODIFIED.
- **N8** — `EnterpriseOSGraphAdapter.apply_change` raises `NotImplementedError` naming `publish`.
- **N9** — rollback of an EOS publication creates a second EOS proposal with the inverse ops and marks the KA execution ROLLED_BACK; the KA proposal is ROLLED_BACK.

## Plan totals

**Research points covered: 3 of 16 · Deliverables: 10 · Positive cases: 12 · Negative cases: 9 · Test cases total: 21 ·
Product tests served: 3 of 8 (3 turn green here).**

## Implementation Notes

- **Re-check this plan against the tree before implementing.** Written after plan-04 landed (`0ddf147`). Confirm
  `_changes_from` still mints `f"{prefix}.{_slug(v.title)}"` and the EOS adapter still writes directly.
- Characterization (P6, P7a, P8) lands in its own commit before any `graph_change.py` edit.
- EOS-path tests: run `KW_STORAGE_ROOT=<tmp> KW_HOTL_MODE=human PYTHONPATH=/root/ka:/root/enterprise-os-070626
  /root/enterprise-os-070626/.venv/bin/python -m pytest -o addopts="" ka/tests/test_plan05_eos_publication.py`.
- The domain used by EOS tests is created in the temp store by the test (two processes + `contains`), under `universal@1`;
  typed validation (`process_type`) is checked by the binder, not by the store under that structure.
- **Correction recorded before implementation (EOS survey, 2026-10-08 16:10 UTC):** under `universal@1` a `process_type` prop is the
  ERROR finding `process_type.no_table` (`process_types.py:398-401`); only `universal-typed@1` accepts it. The EOS publisher therefore
  reads the target graph's `structure_id` and omits `process_type` (with a note in the publish result) when the structure has no
  type table. EOS-path tests build the temp store with `typed_universal()` and graphs pinned to `universal-typed@1`. Also confirmed:
  `approve` refuses only blank/"system"/"automation"/"hotl:*" actors; `Proposal` has no `findings` field (refusal codes come via
  `ProposalRefused.code`); the HOTL approvals log lives under `KW_STORAGE_ROOT/governance`, so tests set `KW_STORAGE_ROOT` too.
