# Plan 12 - Repin after a domain write: explicit, per instance, by a named person (Q2)

Created: 2026-10-09 00:20 UTC

## Problem Description

Applying a domain promotion creates a new Enterprise OS substructure version and leaves every instance pinned to the old one.
KA reports the pinned instances as `repin_required` (`ka/graph_change.py:348-352`) and the console shows a pill
(`ka/console/app.js:144`); nothing in KA can move a pin, and the store's `repin(instance_id, substructure_id, new_version,
apply=)` (`store.py:899`) is reachable only from the operator CLI. The author decided (Q2, 2026-10-08): KA never repins
automatically; the graph-change page lists each pinned instance with a Repin action; a named person repins each one through
the store's own `repin`; the audit records who moved which instance to which version.

Desired outcome: PT4 of research-02 passes under the EOS interpreter — after a promotion is applied, the proposal lists each
pinned instance with Preview and Repin; a named person repins one; the store shows that instance on the new version, the
others unchanged, with an audit record. The console shows the table and the Dashboard counts instances awaiting repin.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q2 explicit per-instance repin, audited, never automatic | `knowledge-acquisition.md` §5 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| EOS: instances pin substructure versions; `repin` is the only way to move a pin | EOS `process-typed-graph.md`; `store.py:899` | ✅ built (EOS) | **constrained by it** — KA calls `store.repin`, never writes a manifest or pin index |
| Publication only through the store's lifecycle; Invariant 2 lineage | `knowledge-acquisition.md` §5 | ✅ built | **constrained by it** — repin moves a pin to a version that already carries lineage; no new ops |
| Q3 auto-apply stays off; a named person applies | `knowledge-acquisition.md` §5 | ✅ built | **constrained by it** — `by` must be a person: `ka.*` policy ids and research agent ids are refused |
| In-memory adapter propagates downward at apply (§26) | `ka/graph_change.py:248` | ✅ built | **relied on** — for the reference adapter a repin is "already current" |

**Open questions in the sections this plan touches:** none blocking (Q12, Q13 unrelated).

## Research coverage (R1..R9)

Source: [research-02](../research/research-02.md) — **9 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1, R2, R3 | ✅ shipped | plan-10 (6943177), plan-11 (f1b5bd8) |
| R4 repin | ✅ in scope | Phases 1–4 |
| R5, R6, R7 | ⏭️ deferred | plan-13, plan-14, plan-15 |
| R8, R9 | ⏭️ deferred | author decisions Q12, Q13 |

**Covered here: 1 of 9.** Deferred: 5. Shipped earlier: 3.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT4 after a domain promotion is applied, the graph-change page lists each pinned instance with Preview and Repin; a named person repins one; the store shows it on the new version, others unchanged, audit record | R4 | **GREEN** — this plan (EOS interpreter test for the store half; live console flow on the reference adapter) |

## Scope

In: `ka/graph_adapter.py` (`RepinResult`; `GraphAdapter.repin` + `pinned_versions`; both adapters), `ka/graph_change.py`
(`GraphChangeService.repin`, `repin_status`), `ka/events.py` (`graph.instance.repinned`), `ka/api.py` (two routes), `ka/service.py`
(Dashboard queue `instances_awaiting_repin`), `ka/console/app.js` (per-instance table with Preview/Repin; Dashboard tile), tests
(in-process + EOS interpreter), live flow, docs, `docs/protected.md` bump.

Out: automatic repin of any kind; batch "repin all" (each instance is one decision); changes to the EOS repo.

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/graph_change/` (`ka/graph_change.py`; adapters' `validate_change`/`publish` region in
`ka/graph_adapter.py`; verified 2026-10-08, plan-10), touched by Phases 2–3.
HOW: ADDITIVE only — `GraphChangeService.repin(proposal_id, instance_id, *, by, preview=False)` and `repin_status(proposal_id)`
beside `apply`/`rollback`; `GraphAdapter.repin(...)` and `pinned_versions(domain_scope)` on the protocol and both adapters;
`RepinResult`. `apply`, `publish`, `emit_ops`, `validate_change` are not edited.
WHY: the pin move must be recorded on the proposal that created the version and audited with the proposal's identity; the adapter
owns the store handle. A module outside these files would have to reach into the adapter's private store and the proposal's
`impact_summary` — a second publication path, which §5 forbids.
Regression risk: none to existing paths (additive); a wrong `by` check could let a policy id move a pin (pinned by N2).
Characterization gap: nothing pins "no KA code path moves a pin" or "`apply` leaves `pinned_instances` reported and unchanged".
Re-verify: approve a process nugget → proposal → apply → the graph-change page lists pinned instances; `test_plan05_publication.py`,
`test_plan05_eos_publication.py`, `test_plan06_profile.py::test_N6`, `test_plan10::test_N5` UNMODIFIED. Bump the Verified date.

## Assumptions

- `RepinResult(instance_id, substructure_id, from_version, to_version, applied, blocking_edges: list[str], added_nodes, removed_nodes,
  note)`. EOS adapter: `store.repin(iid, sid, new_version, apply=apply)`; `RepinBlocked` → `applied=False`, `blocking_edges` filled,
  no exception; `NotPinned` → `ChangeError`. In-memory adapter: pins are implicit (downward propagation at apply), so
  `pinned_versions` returns the descendants at the proposal's new version and `repin` returns `applied=True, note="already current"`.
- `GraphChangeService.repin`: the proposal must be APPLIED with `new_version`; `by` must not start with `ka.` and must not be a
  research agent id (the service passes `governance.research_agent_ids`); preview never writes; on apply: `impact_summary["repin_required"]`
  loses the instance, `impact_summary["repinned"]` gains `{instance_id, from, to, by, at}`, audit `graph.instance.repinned`, event
  `graph.instance.repinned`. `repin_status` returns one row per instance the domain has (live `pinned_versions`) with `pinned`,
  `target`, `current` (pinned == target) and the repinned record if any.
- Dashboard queue `instances_awaiting_repin` = count over APPLIED proposals of `repin_required` entries.

## Phases

### Phase 1 - Characterization (protocol steps 1–4)
- `test_plan12_repin.py::test_P1_characterization_*`: after `apply`, `pinned_instances` / `repin_required` are reported and no method
  on `GraphChangeService` or the adapters is named `repin`; the in-memory descendants carry the new props by propagation. EOS half
  (`test_plan12_eos_repin.py::test_P1_characterization_*`): after KA publishes a promotion, `store.pinned_by(sid)` still shows the
  old version for every instance. Run green on the unchanged tree; own commit.
- **Protected-code touched:** none (tests only).

### Phase 2 - Adapter and service (protocol steps 5–7)
- `ka/graph_adapter.py`, `ka/graph_change.py`, `ka/events.py`, `ka/service.py` (agent ids into the service; dashboard queue).
- **Protected-code touched:** ⚠️ `ka/graph_change/` — additive, as declared.

### Phase 3 - API and console
- `GET /graph-changes/{id}/repins`, `POST /graph-changes/{id}/repin` (`instance_id`, `by`, `preview`; 409 on refusal).
  Console: table on the change page (instance · pinned → target · Preview · Repin · repinned by/at); Dashboard tile.
- **Protected-code touched:** none

### Phase 4 - Flow, docs, protected bump
- `e2e/plan12_repin_flow.py` (reference adapter: approve a domain nugget → apply → the change page lists Merchant A/B/C "already
  current" rows → Repin one → repinned record, audit). Architecture §5 → ✅ built. `docs/protected.md`.
- **Protected-code touched:** none

## Code blocks (B1..B6)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/graph_adapter.py` | `RepinResult`, protocol methods, both adapters' `repin`/`pinned_versions` |
| B2 | `ka/graph_change.py` | `repin`, `repin_status` |
| B3 | `ka/events.py` | `graph.instance.repinned` |
| B4 | `ka/service.py` | agent ids to the service; dashboard queue |
| B5 | `ka/api.py` | two routes |
| B6 | `ka/console/app.js` | repin table; Dashboard tile |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | characterization tests (in-process + EOS), own commit | `ka/tests/test_plan12_repin.py`, `ka/tests/test_plan12_eos_repin.py` | 1 |
| D2 | `RepinResult`; `GraphAdapter.repin`, `pinned_versions`; in-memory implementations | `ka/graph_adapter.py` | 2 |
| D3 | EOS adapter `repin` → `store.repin`; `pinned_versions` → `store.pinned_by` | `ka/graph_adapter.py` | 2 |
| D4 | `GraphChangeService.repin` (named person, preview/apply, audit, event, impact_summary bookkeeping); `repin_status` | `ka/graph_change.py` | 2 |
| D5 | event name; dashboard queue `instances_awaiting_repin` | `ka/events.py`, `ka/service.py` | 2 |
| D6 | routes `GET …/repins`, `POST …/repin` | `ka/api.py` | 3 |
| D7 | console table + Dashboard tile | `ka/console/app.js` | 3 |
| D8 | live flow; architecture §5 ✅; protected.md bump | `e2e/plan12_repin_flow.py`, docs | 4 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P7)
- **P1** — characterization (pre-change): pins reported, never moved; no `repin` on the service or adapters; EOS `pinned_by` unchanged after a KA promotion.
- **P2** — in-memory: `repin_status` lists every descendant with `current=True`; `repin` returns applied + "already current"; bookkeeping records it.
- **P3** — EOS (interpreter): preview returns the diff and writes nothing; apply moves exactly that instance's pin; `pinned_by` shows one on the new version, others on the old.
- **P4** — the proposal's `repin_required` shrinks and `repinned` grows; audit `graph.instance.repinned` with before/after versions; event emitted.
- **P5** — routes: `GET …/repins` rows; `POST …/repin` preview then apply; unknown proposal 404.
- **P6** — Dashboard queue counts instances awaiting repin across APPLIED proposals and drops after a repin.
- **P7** — PT4 end-to-end under the EOS interpreter (promotion → apply → status → named repin → store state + audit); live console flow on the reference adapter.

## Negative Test Cases (N1..N5)
- **N1** — regression gate: covering tests for `ka/graph_change/` pass UNMODIFIED; `apply` still never moves a pin.
- **N2** — `by` of `ka.policy.auto` / a research agent id is refused (409); nothing moves.
- **N3** — a proposal that is not APPLIED, or has no `new_version`, is refused; an instance not pinned to the domain is refused.
- **N4** — EOS `RepinBlocked` → `applied=False` with the blocking edges listed; the pin is unchanged; no audit of a move.
- **N5** — a repin of an instance already on the target version is a no-op diff, recorded as current, no event.

## Plan totals

**Research points covered: 1 of 9 · Deliverables: 8 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 1 of 7 (1 turns green here).**

## Implementation Notes
- Protected order: Phase 1's commit lands before any edit to `ka/graph_change.py` / `ka/graph_adapter.py`.
- The EOS test runs under the enterprise-os interpreter like `test_plan05_eos_publication.py`; the in-process suite skips it.
- Written against `4c718c2` (plan-11 upload).
