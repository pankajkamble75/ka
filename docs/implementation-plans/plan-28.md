# Plan 28 - Review and publication: side-by-side review, decisions through governance, publication as a recorded digest, graph proposals shown never advanced; the regression gate (research-04 R8, R14)

Created: 2026-10-10 00:40 UTC

## Problem Description

A submitted draft now produces governance operations (plan-27), but nothing lets a reviewer see the draft against the article, decide the
produced candidates in one place, and publish. research-04 §7 decides: a review screen with the current article and the draft side by
side, the classified operations, each produced candidate's status and conflict analysis; decisions are `decide` calls; the proposal is
resolved when every produced ref has a decision; publication applies the draft's layout (authored pages) and records a `WikiPublication`
with the current digest — nothing else, because the facts are whatever is ACTIVE; graph proposals arising from approvals are shown and
never advanced here (Q3, Invariant 2); a second publish with nothing changed is a no-op that says so (PT11). R14 pins that the existing
console and API are unchanged by the wiki (PT10).

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §8a The article is a projection; publication records a digest; staleness is a digest comparison (Q19) | `knowledge-acquisition.md` §8a | ✅ built (read side) | **completes it** — the publication write path |
| Q3 / Invariant 2: graph changes are separate proposals approved by a named person | `knowledge-acquisition.md` §5 | ✅ built | **obeyed** — shown, linked, never advanced |
| §4 decisions through `decide`; no second approval path | `knowledge-acquisition.md` §4; `docs/protected.md` | ✅ built | **obeyed** — the review screen calls the existing decide route; governance untouched |
| §8a Where it sits: `#/wiki/:key/review/:proposal` (Q17) | `knowledge-acquisition.md` §8a | ✅ built (tab) | **adds the review route** |
| R14 gate | research-04 §9 | — | **builds it** |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R14)

Source: [research-04](../research/research-04.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1, R7, R10, R11, R12 | ✅ decided (R7 built by plan-27) | — |
| R2, R3, R4, R9, R13 | ✅ shipped | plan-25 |
| R5 | ✅ shipped | plan-26 |
| R6 | ✅ shipped | plan-27 |
| R8 review and publication | ✅ in scope | Phases 1–2 |
| R14 regression gate | ✅ in scope | Phase 3 |

**Covered here: 2 of 14** — the last two open rows; the set closes with this plan.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT4 approval updates the nuggets and the article reflects it; graph changes take the separate route | R8 | **GREEN** |
| PT10 every existing route, tab and suite unchanged | R14 | **GREEN** |
| PT11 publish records a digest; a second publish with nothing changed is a no-op that says so | R8 | **GREEN** |

## Scope

In: `ka/wiki.py` (`proposal_review`, `resolve_proposal`, `publish`, `reject_proposal`, `list_proposals`), `ka/api.py`
(`GET /wiki/proposals`, `GET /wiki/proposals/{id}/review`, `POST /wiki/proposals/{id}/publish`, `POST /wiki/proposals/{id}/reject`,
`POST /wiki/pages/{key}/publish`), `ka/console/app.js` (review view; proposals list on the index; Publish on a stale article),
`ka/events.py` (`wiki.published`, `wiki.proposal.rejected`), `ka/tests/test_plan28_review_publish.py`, `ka/tests/test_plan28_regression_gate.py`,
`e2e/plan28_review_flow.py`, docs.

Out: any governance change; graph proposal decisions (the existing graph-change page); notifications.

## Protected-code impact (summary)

✅ No protected code touched by any phase — decisions go through the existing `POST /nugget/{ref}/decide`.

## Assumptions

- `proposal_review(id)` returns: the proposal, the current article blocks and the draft blocks (both as plan-25 blocks), the operations,
  and for each produced ref: status, statement, the nugget's open conflicts (`analysis.findings` with CONTRADICTS), its graph proposals
  (`repo.proposals` where `knowledge_change_ids` contains the ref, id + status), decision id; plus `resolved` (no produced ref is
  PENDING_REVIEW/CONFLICT/ANALYZED) and `publishable` (resolved and the draft is SUBMITTED).
- `resolve_proposal(id)` recomputes `state`: SUBMITTED → RESOLVED when resolved; it is called by the review route on read.
- `publish(key, *, by, proposal_id=None)`: when a proposal is given it must be resolved; for an authored page the draft's blocks become
  the layout (`layout_rev += 1`); for derived pages the layout is unchanged (the article is computed); then if a `WikiPublication` with
  the same digest and layout_rev already exists → `{"published": False, "reason": "already published", ...}`; else a `WikiPublication` is
  recorded, the draft → CLOSED, the proposal → PUBLISHED, `wiki.published` emitted, audited. A derived page's `WikiPage` record is created
  on first publication (so the publication has a page to belong to; reading still writes nothing).
- `reject_proposal(id, by, reason)`: proposal → REJECTED, draft → CLOSED; produced refs are left to governance (a reviewer may still decide
  them on the nugget page); audited.
- The review screen's decide buttons post to the existing decide route with APPROVE / REJECT and a reason; ACCEPT_NEW is offered when the
  candidate is in CONFLICT with a partner.
- R14 gate: `test_plan28_regression_gate.py` extracts every `@router.<method>("<path>")` from `git show 83fe82c:ka/api.py` (the last
  pre-wiki commit) and asserts each is still registered on the current app with the same method; extracts `TAB_LABELS` entries 1–6 and the
  pre-wiki routes array from `git show 83fe82c:ka/console/app.js` and asserts they are present verbatim; and asserts no pre-wiki test file
  differs from 83fe82c except the two documented relaxations (plan-20/24 unused-variable cleanups, plan-19 N3) — listed explicitly.

## Phases

### Phase 1 - Review, resolution, publication (service + routes)
- `ka/wiki.py`, `ka/api.py`, `ka/events.py`.
- **Protected-code touched:** none

### Phase 2 - Console
- `#/wiki/:key/review/:proposal`; proposals list on the index; Publish on the article when stale or never published.
- **Protected-code touched:** none

### Phase 3 - Gate, tests, flow, docs
- `test_plan28_regression_gate.py`, `test_plan28_review_publish.py`, `e2e/plan28_review_flow.py`; architecture §8a → ✅ built; README.
- **Protected-code touched:** none

## Code blocks (B1..B4)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/wiki.py` | review, resolve, publish, reject, list |
| B2 | `ka/api.py` | five routes |
| B3 | `ka/console/app.js` | review view, proposals list, Publish |
| B4 | `ka/events.py` | two names |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `proposal_review(id)` with side-by-side blocks, operations, produced refs' status/conflicts/graph proposals, `resolved`, `publishable` | `ka/wiki.py` | 1 |
| D2 | `resolve_proposal`, `publish` (idempotent, records `WikiPublication`, applies authored layout), `reject_proposal`, `list_proposals` | `ka/wiki.py` | 1 |
| D3 | routes (five); events | `ka/api.py`, `ka/events.py` | 1 |
| D4 | console review view with decide buttons through the existing decide route; proposals list; Publish | `ka/console/app.js` | 2 |
| D5 | regression gate test (routes, tabs, pre-wiki tests) | `ka/tests/test_plan28_regression_gate.py` | 3 |
| D6 | review/publish tests | `ka/tests/test_plan28_review_publish.py` | 3 |
| D7 | live flow; architecture §8a ✅ built; README | `e2e/plan28_review_flow.py`, docs | 3 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P7)
- **P1** — review of a proposal with one revision and one candidate: side-by-side blocks, operations, produced refs with status PENDING_REVIEW, `resolved` false.
- **P2** — PT4: APPROVE both through the decide route → `resolved` true, the article's blocks carry the new statement and ref, the superseded ref is gone; graph proposals created by approval are listed with their ids and status and are NOT applied by anything here.
- **P3** — publish after resolution → `WikiPublication` recorded with the current digest and manifest, draft CLOSED, proposal PUBLISHED, `stale` false, `wiki.published` emitted.
- **P4** — PT11: a second publish with nothing changed → `{"published": False, "reason": "already published"}` and no second record; after another approval the page is stale and publish records a new digest.
- **P5** — an authored page's proposal: publish applies the draft blocks as the layout (`layout_rev` 1) and the article renders them.
- **P6** — editorial-only proposal (no produced refs) is `resolved` at once and publishable; reject_proposal closes the draft and marks the proposal REJECTED.
- **P7** — live flow: submit a change → open the review page from the article's drafts list → side-by-side visible → Approve the revision → "resolved" → Publish → the article shows "published"; a second Publish says already published; no JS errors.

## Negative Test Cases (N1..N4)
- **N1** — publishing an unresolved proposal → 409 naming the pending refs; nothing recorded.
- **N2** — PT10: every pre-wiki API route and console tab/route from 83fe82c is present verbatim; pre-wiki test files are byte-identical to 83fe82c except the three documented relaxations.
- **N3** — unknown proposal → 404; publish by a research agent id → refused (decisions already refuse agents; publication records `by` and refuses the agent ids too).
- **N4** — publication never writes a nugget, a decision or a graph proposal (byte-compare those collections before/after).

## Plan totals

**Research points covered: 2 of 14 · Deliverables: 7 · Positive cases: 7 · Negative cases: 4 · Test cases total: 11 ·
Product tests served: 3 of 12 (PT4, PT10, PT11 turn green here; the set's twelve are then all green).**

## Implementation Notes
- Written against `6061660` (plan-27). No protected code. Re-checked: plan-27's `WikiEditProposal.operations/produced_refs` are this plan's inputs.
