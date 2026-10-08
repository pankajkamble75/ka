# Plan 10 - Governance decisions Q11 and Q4: duplicates resolve as Keep Existing + evidence; revocation becomes a re-review

Created: 2026-10-08 21:55 UTC

## Problem Description

Two author decisions from 2026-10-08 land in the same protected file, `ka/governance.py`, and share one characterization:

- **Duplicates (Q11, research-02 R1).** APPROVE on a candidate analysed as `duplicate_of` an ACTIVE nugget activates it
  (`ka/governance.py:318`), so one fact ends up with two ACTIVE versions; an explicit KEEP_EXISTING rejects the candidate and
  discards its evidence (`:319-322`). Decided: APPROVE auto-resolves as Keep Existing — the candidate closes (REJECTED,
  `analysis.resolved_as="duplicate"`) under an automatic KEEP_EXISTING decision, and its source and evidence refs are appended
  to the existing nugget (provenance fields, not semantic — `ka/versioning.py:17`). Explicit KEEP_EXISTING gains the same
  attachment.
- **Revocation (Q4, research-02 R2).** When a connector file is deleted, plan-08 marks the source revoked and flags derived
  nuggets (`ka/connectors/sync.py:126-135`); they stay ACTIVE. Decided: every ACTIVE nugget derived from the revoked source
  returns to review as a same-statement candidate revision carrying `source_revoked`; APPROVE keeps it on its remaining
  evidence (ordinary supersession); REJECT of such a candidate ALSO retires the prior ACTIVE version (OBSOLETE, `effective_to`)
  and raises a graph proposal removing the elements that depend only on it.

Desired outcome: PT1 and PT2 of research-02 pass; `test_plan01_phase2_governance.py` and every other covering suite for
`ka/governance/` pass unmodified; the needs-attention row for revoked sources points at the Pending queue.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q11 duplicates → Keep Existing + evidence | `knowledge-acquisition.md` §4 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| Q4 revocation → re-review as candidate revisions; REJECT retires | `knowledge-acquisition.md` §2, §10 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| Invariant 3: semantic fields immutable; `source_refs`/`evidence_refs` are provenance | `knowledge-acquisition.md` §4; `ka/versioning.py:17` | ✅ built | **constrained by it** — evidence is appended, statements never edited |
| One governance pipeline; a person or the §13 policy decides | `knowledge-acquisition.md` §4 | ✅ built | **constrained by it** — the automatic Keep Existing is a recorded decision with `automatic=True` |
| Invariant 2: every graph change carries lineage | `knowledge-acquisition.md` §5 | ✅ built | **constrained by it** — retirement ops carry the retired nugget's lineage |
| Candidate analysis excludes the same canonical id | `ka/governance.py:224` | ✅ built | **relied on** — a re-review revision is not flagged as a duplicate of itself |

**Open questions in the sections this plan touches:** Q12, Q13 (search key, M365 registration) — unrelated to this plan.

## Research coverage (R1..R9)

Source: [research-02](../research/research-02.md) — **9 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 duplicates | ✅ in scope | Phases 1–2 |
| R2 revocation re-review | ✅ in scope | Phases 1–3 |
| R3 injection defence | ⏭️ deferred | plan-11 — different files (`process_extraction.py`, `binding.py`) |
| R4 repin | ⏭️ deferred | plan-12 — publication, not governance |
| R5 search provider | ⏭️ deferred | plan-13 |
| R6 M365 connector | ⏭️ deferred | plan-14 |
| R7 Processes tab | ⏭️ deferred | plan-15 |
| R8 search vendor + key | ⏭️ deferred | author decision Q12; no plan |
| R9 M365 app registration | ⏭️ deferred | author decision Q13; no plan |

**Covered here: 2 of 9.** Deferred: 7 (five to named plans, two author decisions).

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 same SOP twice → one ACTIVE version naming both documents; second candidate closed as duplicate by automatic Keep Existing | R1 | **GREEN** — this plan |
| PT2 deleting a connected file → same-statement revision in Pending flagged source revoked; REJECT retires prior + graph removal proposal; APPROVE keeps it | R2 | **GREEN** — this plan |

## Scope

In: `ka/governance.py` (duplicate branch in `decide`; `attach_provenance`; `reopen_for_revocation`; REJECT-retires branch),
`ka/graph_change.py` (`propose_retirement`), `ka/connectors/sync.py` (call the re-review on `deleted`), `ka/service.py`
(needs-attention row), `ka/console/app.js` (history label "duplicate of …", Pending row badge "source revoked", Dashboard link),
`ka/vocab.py` (nothing new — verified), tests, live flow, docs, `docs/protected.md` Verified bump.

Out: narrowing of visibility as a re-review trigger (plan-08 flags it; a narrowing that drops below the nugget's scope requirement
is Q4's second half and is NOT decided — stays flagged); MERGE/BOTH_VALID semantics; the EOS repo.

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/governance/` (`ka/governance.py`; verified 2026-10-08, plan-04), touched by Phase 2.
HOW: `decide()` gains (a) a duplicate branch ahead of `_activate`: when `outcome == APPROVE` and `v.analysis.get("duplicate_of")`
names an ACTIVE version, the decision is rewritten to KEEP_EXISTING with `automatic=True`, the candidate → REJECTED with
`analysis["resolved_as"]="duplicate"`, and `attach_provenance(existing, v, by)` appends refs; (b) explicit KEEP_EXISTING with a
duplicate target also calls `attach_provenance`; (c) REJECT of a candidate carrying `analysis["source_revoked"]` additionally
retires the prior ACTIVE version of the same canonical id (OBSOLETE) and calls `graph_change.propose_retirement`. New methods
`attach_provenance(target_ref, from_version, by)` and `reopen_for_revocation(source_id, by)`.
WHY: the status transitions and decision records exist only inside `decide`/`_activate`; a wrapper outside the file would be a
second approval path, which §4 forbids.
Regression risk: `decide` runs on every approval; a wrong duplicate test could reject a legitimate candidate (mitigated: only when
the target is ACTIVE and the flag is present); a wrong retire test could obsolete an unrelated version (mitigated: only candidates
with `source_revoked`, same canonical id).
Characterization gap: no test pins "APPROVE on a duplicate_of candidate yields two ACTIVE versions" nor "KEEP_EXISTING leaves the
target's `source_refs` unchanged" nor "REJECT never touches the prior version".
Re-verify: console — Apply a PERSONAL candidate to a domain → refused; plus plan-10's flow. Covering tests
(`test_plan01_phase2_governance.py`, `phase6_propagation`, `api_console`, `plan02`, `plan03`, `plan04`, `plan06`, `plan08`) pass
UNMODIFIED. Bump the Verified date in the same commit.

⚠️ TOUCHES PROTECTED — `ka/graph_change/` (`ka/graph_change.py`; verified 2026-10-08, plan-06), touched by Phase 3.
HOW: new method `GraphChangeService.propose_retirement(v, *, by)` beside `propose_for`: removal ops for elements whose lineage
depends ONLY on `v` (from `GraphDependency` rows), each carrying `v`'s lineage; the proposal goes through validate → approve →
apply like any other. `apply` and `emit_ops` are not edited.
WHY: proposals are created only in this service; emitting a removal from governance directly would bypass impact analysis.
Regression risk: none to existing paths (additive); a wrong "only" test could remove a shared element (mitigated: a dependency count
over ACTIVE nuggets, excluding `v`).
Characterization gap: `apply` with a remove op whose target has other dependents is pinned by plan-06's lineage tests; the new
method is additive.
Re-verify: approve a process nugget → proposal → apply; `test_plan05_publication.py`, `test_plan06_profile.py::test_N6` unmodified.

Not protection-driven: the sync-side trigger stays in `ka/connectors/sync.py` because that is where deletion is detected.

## Assumptions

- `GovernanceDecision` already has `automatic: bool` (§13) — confirmed `ka/model.py`; used for the auto Keep Existing.
- `attach_provenance` appends `source_refs`/`evidence_refs` (deduplicated) and re-puts the version; `Repository.put` enforces
  `SEMANTIC_FIELDS` only, so the write passes; audit `knowledge.provenance.attached` with before/after lists.
- `reopen_for_revocation(source_id, by)` → for each ACTIVE version with `source_id in source_refs`: `propose_revision(canonical_id,
  statement=same, by, reason="source revoked", source_ids=[refs minus source_id], evidence_ids=[evidence not from that source])`;
  the new version gets `analysis["source_revoked"]={"source_id", "revoked_at"}` and `analysis["remaining_sources"]=n`; returns refs.
  A canonical id that already has a PENDING_REVIEW revision is skipped (no second re-review).
- REJECT-retires: prior ACTIVE version → OBSOLETE via `versioning.transition` (sets `effective_to`), relationship OBSOLETES
  (candidate → prior), `graph_change.propose_retirement(prior, by=by)` — only when the adapter has lineage for it; otherwise noted.
- The in-memory adapter applies removals through the existing `publish`; EOS removals go through a proposal (unchanged machinery).

## Phases

### Phase 1 - Characterization (protected protocol steps 1–4)

- `ka/tests/test_plan10_governance_decisions.py::test_P1_characterization_*`: (a) APPROVE on a `duplicate_of` candidate → two ACTIVE
  versions; (b) explicit KEEP_EXISTING → target `source_refs` unchanged, candidate REJECTED; (c) REJECT of an ordinary candidate
  leaves every other version's status unchanged; (d) deleting a connected file leaves derived nuggets ACTIVE and flagged (plan-08).
  Run green against the UNCHANGED files; commit on its own.
- **Protected-code touched:** none (tests only).

### Phase 2 - Governance (protocol steps 5–7 for `ka/governance/`)

- `ka/governance.py`: duplicate branch; `attach_provenance`; `reopen_for_revocation`; REJECT-retires branch.
- Covering tests unmodified; `docs/protected.md` row bumped.
- **Protected-code touched:** ⚠️ `ka/governance/`.

### Phase 3 - Retirement proposal and the trigger

- `ka/graph_change.py::propose_retirement`. `ka/connectors/sync.py`: on `deleted`, after flagging, `governance.reopen_for_revocation`.
  `ka/service.py`: needs-attention `revoked_sources_with_active_knowledge` → `revoked_source_reviews` (candidate refs, link to Pending).
- **Protected-code touched:** ⚠️ `ka/graph_change/` (additive method).

### Phase 4 - Console, flow, docs

- `ka/console/app.js`: history rows show "duplicate of KN-x" when `resolved_as`; Pending rows show a "source revoked" badge and
  remaining-sources count; Dashboard row links to Pending. `e2e/plan10_governance_flow.py`: upload SOP twice → approve second →
  one ACTIVE, history shows duplicate; connect folder, approve, delete file, sync → Pending shows revoked badge → Reject → prior
  OBSOLETE and a proposal exists. Architecture §2/§4/§10 states → ✅ built. README.
- **Protected-code touched:** none

## Code blocks (B1..B5)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/governance.py` | duplicate branch, `attach_provenance`, `reopen_for_revocation`, REJECT-retires |
| B2 | `ka/graph_change.py` | `propose_retirement` |
| B3 | `ka/connectors/sync.py` | re-review trigger on deleted |
| B4 | `ka/service.py` | needs-attention row |
| B5 | `ka/console/app.js` | history label, Pending badge, Dashboard link |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | characterization tests, own commit | `ka/tests/test_plan10_governance_decisions.py` | 1 |
| D2 | duplicate branch in `decide` (APPROVE → automatic KEEP_EXISTING; candidate REJECTED, `resolved_as=duplicate`) | `ka/governance.py` | 2 |
| D3 | `attach_provenance(target_ref, from_version, by)` with audit | `ka/governance.py` | 2 |
| D4 | `reopen_for_revocation(source_id, by) -> list[str]` | `ka/governance.py` | 2 |
| D5 | REJECT-retires branch (prior → OBSOLETE, OBSOLETES relationship, retirement proposal) | `ka/governance.py` | 2 |
| D6 | `GraphChangeService.propose_retirement(v, *, by)` | `ka/graph_change.py` | 3 |
| D7 | sync trigger + needs-attention `revoked_source_reviews` | `ka/connectors/sync.py`, `ka/service.py` | 3 |
| D8 | console surfaces; live flow; architecture states ✅; protected.md bump | `ka/console/app.js`, `e2e/plan10_governance_flow.py`, docs | 4 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P8)

- **P1** — characterization (pre-change), four assertions as listed in Phase 1.
- **P2** — APPROVE on a `duplicate_of` ACTIVE candidate: exactly one ACTIVE version; candidate REJECTED with `resolved_as="duplicate"`; decision outcome KEEP_EXISTING, `automatic=True`, `related_refs=[existing]`; audit present.
- **P3** — the existing nugget's `source_refs` and `evidence_refs` now include the candidate's; its semantic fields are byte-identical (Invariant 3 check passes); its lineage rows are unchanged.
- **P4** — explicit KEEP_EXISTING on a duplicate attaches provenance the same way; APPROVE on a candidate whose duplicate target is SUPERSEDED falls through to ordinary activation.
- **P5** — `reopen_for_revocation` creates one PENDING_REVIEW revision per ACTIVE derived nugget, same statement, `source_revoked` set, `source_refs` minus the revoked source, channel FEEDBACK; the prior stays ACTIVE until decided; a second call creates nothing.
- **P6** — APPROVE of the revision supersedes the prior (ordinary activation); the knowledge continues on the remaining sources.
- **P7** — REJECT of the revision: prior → OBSOLETE with `effective_to`; OBSOLETES relationship; a graph change proposal exists whose ops remove only the elements that depend on no other ACTIVE nugget; the revision is REJECTED.
- **P8** — PT1 and PT2 end-to-end through the sync service and the API; the needs-attention row lists the revision refs; live flow `e2e/plan10_governance_flow.py`.

## Negative Test Cases (N1..N6)

- **N1** — regression gate: every covering test listed in `docs/protected.md` for `ka/governance/` and `ka/graph_change/` passes UNMODIFIED.
- **N2** — a candidate flagged `duplicate_of` a nugget that is NOT ACTIVE (rejected/superseded) is approved normally — no Keep Existing.
- **N3** — an ordinary REJECT (no `source_revoked`) never changes any other version's status and raises no proposal.
- **N4** — `reopen_for_revocation` ignores nuggets whose only link to the source is through a REJECTED/SUPERSEDED version; and a revision with ZERO remaining sources is still created with `remaining_sources=0` (the reviewer decides) and the Pending row says so.
- **N5** — `propose_retirement` never emits a remove for an element another ACTIVE nugget depends on; with no lineage it raises nothing and returns None (noted on the decision).
- **N6** — research agent ids cannot trigger the automatic Keep Existing path as `by` (same §17 guard); `attach_provenance` on a non-governed target raises.

## Plan totals

**Research points covered: 2 of 9 · Deliverables: 8 · Positive cases: 8 · Negative cases: 6 · Test cases total: 14 ·
Product tests served: 2 of 7 (2 turn green here).**

## Implementation Notes

- **Corrections during the build (ship: corrected and continued).** (1) The duplicate branch applies only when the duplicate
  target is in the candidate's OWN scope — `test_plan01_phase6_propagation::test_P4` showed that sibling-instance repeats are
  promotion's business (§25), not duplicates. (2) `test_plan06_profile::test_N7` pinned the pre-Q11 behaviour by name ("duplicate
  ACTIVE assertions (Q11)"); the author's Q11 decision superseded it, so its assertions were rewritten to the decided behaviour —
  recorded in `docs/protected.md` and the checkpoint, not done silently. (3) `SyncReport.counts()` is unchanged; re-review refs are
  `SyncReport.reviews` and `Connection.last_delta["reviews"]` so plan-08's exact-dict assertion stands.

- Protected order: Phase 1's commit lands before any edit to `ka/governance.py` or `ka/graph_change.py`.
- Written against the tree at `2bd86b0` (research-02); first plan of the set, no re-check needed.
