# Plan 27 - Reconciliation: a submitted draft becomes governance operations through the one pipeline; a person can request retirement (research-04 R6; builds R7 / Q18)

Created: 2026-10-09 23:40 UTC

## Problem Description

plan-26 lets a person edit an article and submit a draft; nothing yet turns the submission into knowledge. research-04 §5 and §6 and the
author's Q18 answer decide how: the block diff's inserted and updated blocks go through the existing extractor (FEEDBACK channel, the
page's scope, Q10's tiers); each extracted statement is compared with the nuggets the block cites and with the page's selection
(`ConflictDetector`'s similarity), and classified EDITORIAL_ONLY / LINK_EXISTING / ADD_CANDIDATE / PROPOSE_REVISION / PROPOSE_RETIREMENT /
NEEDS_EVIDENCE / UNRESOLVED; submission creates candidates through `ingest_candidate` and revisions through `propose_revision`; deleting
prose produces nothing; an explicit retirement request becomes a same-statement revision carrying a review reason, and REJECT on it
retires the prior exactly as plan-10's revoked-source re-review does. Desired outcome (PT3's candidate half, PT5, PT6, PT7).

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §8a Edits are governance proposals through the one pipeline; deleting prose retires nothing | `knowledge-acquisition.md` §8a | ⏳ decided | **builds it** |
| §4 Human retirement (Q18): a revision carries `review_reason`; REJECT retires the prior as the revoked-source case does | `knowledge-acquisition.md` §4 | ⏳ decided | **builds it** — protected change under the seven-step protocol; state → ✅ on upload |
| Q10 trust tiers; FEEDBACK channel for human-originated knowledge | `knowledge-acquisition.md` §3; `ka/vocab.py:155` | ✅ built | **obeyed** — the extractor is called as `extract_from_source` calls it; the draft is a FEEDBACK source |
| Q11 duplicates auto-resolve as Keep Existing | `knowledge-acquisition.md` §4 | ✅ built | **relied on** — LINK_EXISTING is this outcome; an accidental ADD of a duplicate is harmless |
| Invariant 3; `docs/protected.md` governance row | `knowledge-acquisition.md` §4 | ✅ built | **touched** — Phase 2 only, see below |
| No wiki identity (R11) | §8a, §10 | ✅ decided | **obeyed** — `by` is the typed name |

**Open questions in the sections this plan touches:** none (Q18 answered 2026-10-09).

## Research coverage (R1..R14)

Source: [research-04](../research/research-04.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1, R10, R11, R12 | ✅ decided | — |
| R2, R3, R4, R9, R13 | ✅ shipped | plan-25 |
| R5 | ✅ shipped | plan-26 |
| R6 reconciliation | ✅ in scope | Phases 1, 3 |
| R7 retirement | ✅ decided (Q18) — **BUILT here** | Phase 2 |
| R8 review/publication, R14 gate | ⏭️ deferred | plan-28 |

**Covered here: 1 of 14** (+1 decided row built). Deferred: 2.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT3 editing one paragraph to add an activity creates a candidate; article, ACTIVE nuggets, graph unchanged until approval | R5, R6 | **GREEN** |
| PT5 formatting/heading-only changes produce no candidate or revision | R6 | **GREEN** |
| PT6 deleting a paragraph retires nothing; an explicit retirement request reaches a reviewer and REJECT retires | R6, R7 | **GREEN** |
| PT7 a three-citation paragraph with one changed claim → one revision, two citations untouched | R6 | **GREEN** |

## Scope

In: `ka/wiki_reconcile.py` (new: `Reconciler.classify`, `Reconciler.submit`), `ka/model.py` (`WikiDraft.requests`, `WikiDraft.proposal_id`),
`ka/wiki.py` (`submit_draft` hands the draft to the reconciler; `add_request`), `ka/governance.py` (**protected**: REJECT retires when the
revision carries `retirement_requested`, not only `source_revoked`; new `request_retirement`), `docs/protected.md` (Verified date),
`ka/api.py` (`POST /wiki/drafts/{id}/reconcile`, `POST /wiki/drafts/{id}/requests`, `GET /wiki/proposals/{id}`), `ka/console/app.js`
(Reconcile preview, retirement request form, produced refs after submit), tests, flow, docs.

Out: the review screen and publication (plan-28); any change to `_activate`, duplicates, MERGE or CHANGE_SCOPE; LLM claim extraction
beyond what the configured provider already does.

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/governance/` (verified 2026-10-08), touched by Phase 2.
HOW: in `decide`, the REJECT branch's retirement condition `v.analysis.get("source_revoked")` becomes
`v.analysis.get("source_revoked") or v.analysis.get("retirement_requested")`, with the retirement comment and OBSOLETES explanation
worded from whichever reason is present; a new method `request_retirement(canonical_id, *, by, why) -> KnowledgeNuggetVersion` creates a
same-statement revision through `propose_revision` (reason "retirement requested by <by>: <why>") and stamps
`analysis["retirement_requested"] = {"by", "why", "prior_ref", "at"}`, skipping a canonical id already under review — the shape of
`reopen_for_revocation`. Nothing else in the file changes.
WHY: the retirement decision must stay inside `decide` — it is the one place a prior version is made OBSOLETE and the graph retirement is
proposed (plan-10); a path outside governance would be a second retirement mechanism, which Q18 rejected.
Regression risk: every REJECT decision passes the changed condition; an ordinary REJECT (no reason stamped) must still retire nothing.
Characterization gap: plan-10 `test_N3` pins "ordinary reject retires nothing" and `test_P7` pins the revoked-source retirement; nothing
pins that `request_retirement` does not exist or that a stamped reason other than `source_revoked` is ignored today — the characterization
commit adds exactly those.
Re-verify: `e2e/plan10_governance_flow.py` plus this plan's flow; covering suites listed in `docs/protected.md` pass UNMODIFIED
(plan-10 `test_N1` byte-compares them against 48d4685). Bump the Verified date in the same commit as the change.

Avoidances elsewhere are not protection-driven: the reconciler lives in its own module because it is wiki logic, not governance.

## Assumptions

- Statement extraction per changed block uses `governance.extractor.extract(title=<page title>, sections=[(block_id, text)], text=text)`
  with citations stripped; the stub/heuristic extractor yields sentences.
- Classification per extracted statement, in order: identical or `similarity ≥ KA_DUPLICATE_THRESHOLD` to a cited nugget → LINK_EXISTING;
  `subject_similarity ≥ 0.5` to a cited nugget → PROPOSE_REVISION of that canonical id; otherwise compared with the page's selection — a
  duplicate → LINK_EXISTING; else ADD_CANDIDATE when the block cites at least one nugget or the page has a scope, NEEDS_EVIDENCE when the
  block cites nothing and the statement carries an absolute claim (a number or "must/never/always") with no page scope; a changed
  paragraph of six or more words from which nothing extracts → UNRESOLVED. Headings, moves, deletes → EDITORIAL_ONLY (deletes carry the
  note "deleting prose retires nothing; request retirement explicitly").
- Candidate scope: the page's scope for scope pages; otherwise the targeted or first cited nugget's scope; otherwise the first selected
  version's scope; none → UNRESOLVED.
- Provenance of a submission: one FEEDBACK `Source` per submitted draft (`record_derived`, type NOTE, authority USER_KNOWLEDGE, visibility
  = page ceiling, title "Wiki draft <id> — <page title>"), text = the changed blocks; one `Evidence` per produced statement with its offsets
  in that text; revisions carry the prior's subject/predicate/object explicitly.
- Retirement requests: `POST /wiki/drafts/{id}/requests {ref, why, by}` appends to `WikiDraft.requests`; classify maps each to
  PROPOSE_RETIREMENT; submit calls `request_retirement`; the review and REJECT happen on the nugget page (plan-28's review screen groups them).
- `submit_draft` (plan-26) now also runs the reconciler and stores `proposal_id` on the draft; the `WikiEditProposal` records diff,
  operations, produced refs; its `state` is SUBMITTED until plan-28 resolves it.

## Phases

### Phase 1 - The reconciler (classification and submission)
- `ka/wiki_reconcile.py`, `ka/model.py`, `ka/wiki.py`, `ka/api.py`, `ka/service.py`.
- **Protected-code touched:** none

### Phase 2 - Human retirement (protected)
1. Declare — above. 2. Characterize FIRST: `test_plan27_characterization_governance.py` pins today's seam (ordinary REJECT retires
   nothing; a stamped `retirement_requested` is ignored today; no `request_retirement`), run green against unchanged code, committed alone.
3. Positive/negative coverage before the change — same file (the revoked-source retirement still works; agents cannot request).
4. Change `ka/governance.py` as declared. 5. Covering suites pass unmodified (plan-10 `test_N1`). 6. Re-verify live (plan-10 flow + this
   plan's flow). 7. Bump `Verified:` in `docs/protected.md` in the same commit.
- **Protected-code touched:** ⚠️ `ka/governance.py` (`decide` REJECT branch; `request_retirement`)

### Phase 3 - Console, tests, flow, docs
- Reconcile preview table and retirement request form in the editor; produced refs after submit. `ka/tests/test_plan27_wiki_reconcile.py`;
  `e2e/plan27_reconcile_flow.py`; architecture §4/§8a states.
- **Protected-code touched:** none

## Code blocks (B1..B6)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/wiki_reconcile.py` | the reconciler |
| B2 | `ka/model.py` | `WikiDraft.requests`, `proposal_id` |
| B3 | `ka/wiki.py`, `ka/api.py`, `ka/service.py` | hand-off, routes, wiring (one block each) |
| B4 | `ka/governance.py` | the retirement condition and `request_retirement` |
| B5 | `ka/console/app.js` | reconcile preview, request form, produced refs |
| B6 | `docs/protected.md` | Verified date |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `Reconciler.classify(draft) -> {diff, operations, summary}` with the seven classes | `ka/wiki_reconcile.py` | 1 |
| D2 | `Reconciler.submit(draft, by) -> WikiEditProposal`: FEEDBACK source + evidence; `ingest_candidate` / `propose_revision` / `request_retirement`; produced refs recorded | `ka/wiki_reconcile.py` | 1 |
| D3 | `WikiDraft.requests`, `proposal_id`; `WikiService.add_request`; `submit_draft` runs the reconciler | `ka/model.py`, `ka/wiki.py` | 1 |
| D4 | routes `POST …/reconcile`, `POST …/requests`, `GET /wiki/proposals/{id}` | `ka/api.py` | 1 |
| D5 | characterization tests (green against unchanged governance, own commit) | `ka/tests/test_plan27_characterization_governance.py` | 2 |
| D6 | `request_retirement`; REJECT retires on `retirement_requested`; Verified date bumped | `ka/governance.py`, `docs/protected.md` | 2 |
| D7 | console: Reconcile preview, retirement request form, produced refs | `ka/console/app.js` | 3 |
| D8 | live flow; architecture states | `e2e/plan27_reconcile_flow.py`, docs | 3 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P8)
- **P1** — characterization: today an ordinary REJECT retires nothing; a revision stamped `retirement_requested` and rejected still retires nothing; `GovernanceService` has no `request_retirement`. (Green against the unchanged file, committed alone.)
- **P2** — PT7: a paragraph citing three nuggets with one sentence changed → one PROPOSE_REVISION of that nugget, two LINK_EXISTING; submit produces exactly one candidate version.
- **P3** — PT3: a new sentence inserted in a cited paragraph → ADD_CANDIDATE; submit creates a PENDING_REVIEW candidate (FEEDBACK channel, page scope, evidence from the draft source); ACTIVE nuggets, the article and graph proposals are unchanged.
- **P4** — PT5: heading rename, block move, bold added → every operation EDITORIAL_ONLY; submit produces no refs.
- **P5** — PT6a: deleting a cited paragraph → EDITORIAL_ONLY with the retirement note; the cited nugget stays ACTIVE after submit.
- **P6** — PT6b: a retirement request on a cited ref → PROPOSE_RETIREMENT; submit creates a same-statement revision with `retirement_requested`; REJECT on it makes the prior OBSOLETE and raises the graph retirement proposal (as plan-10 P7); APPROVE keeps the knowledge.
- **P7** — the revoked-source path still works after the change (reopen → REJECT → OBSOLETE) and plan-10's covering tests pass unmodified.
- **P8** — live flow: edit a paragraph (one changed claim), Reconcile shows the classes, Submit shows the produced revision link; the nugget page shows the pending revision; REJECT of a retirement request retires the prior on the console.

## Negative Test Cases (N1..N5)
- **N1** — a new absolute claim in an uncited block on a page without scope → NEEDS_EVIDENCE; submit creates nothing for it and the operation stays on the proposal marked for the reviewer.
- **N2** — a changed paragraph from which nothing extracts → UNRESOLVED; nothing created.
- **N3** — `request_retirement` by a research agent id → refused (§17); on a canonical id already under review → skipped with a reason; on an unknown id → error.
- **N4** — an ordinary REJECT (no reason stamped) still retires nothing after the change; the plan-10 covering suites are byte-identical to 48d4685 (`test_N1` gate).
- **N5** — submitting the same draft twice does not create a second proposal or duplicate candidates (409 on the second submit).

## Plan totals

**Research points covered: 1 of 14 (+R7 built) · Deliverables: 8 · Positive cases: 8 · Negative cases: 5 · Test cases total: 13 ·
Product tests served: 4 of 12 (PT3, PT5, PT6, PT7 turn green here).**

## Implementation Notes
- Written against `26f2be7` (plan-26). Protected governance touched in Phase 2 only, after the characterization commit.
