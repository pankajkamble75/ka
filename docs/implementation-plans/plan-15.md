# Plan 15 - Processes as a top-level console tab (Q8)

Created: 2026-10-09 03:05 UTC

## Problem Description

The console's navigation is four tabs plus Images (`ka/console/app.js:89-105`); the process profile view (plan-06) lives as a
mode inside Browse by scope (`#/browse?mode=processes`, `ka/console/app.js:286-310`). The author decided (Q8, 2026-10-08): add a
fifth top-level tab, Processes, pointing at the existing process profile view; nothing else moves; the note's five-page layout is
declined. Desired outcome: PT7 of research-02 passes — the console shows a Processes tab that lists process subjects and opens a
profile, and Browse by scope's Processes mode still works.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q8 Processes as a fifth tab; four tabs + Images stay; five-page layout declined | `knowledge-acquisition.md` §8 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| Console shape ruled 2026-10-08: Add knowledge · Knowledge nuggets · Browse by scope · Dashboard + Images | `knowledge-acquisition.md` §8 | ✅ built | **constrained by it** — the existing tabs keep their numbers' order; Processes is inserted as 4, Dashboard becomes 5, Images 6 |
| Process profile view (R12) | `knowledge-acquisition.md` §8 (plan-06) | ✅ built | **relied on** — the tab renders `processesList` and the profile page unchanged |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R9)

Source: [research-02](../research/research-02.md) — **9 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R6 | ✅ shipped | plans 10–14 |
| R7 Processes tab | ✅ in scope | Phase 1 |
| R8, R9 | ⏭️ deferred | author decisions Q12, Q13 |

**Covered here: 1 of 9.** Deferred: 2. Shipped earlier: 6.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT7 the console shows a Processes tab that lists process subjects and opens a profile, and Browse by scope's Processes mode still works | R7 | **GREEN** — this plan |

## Scope

In: `ka/console/app.js` (nav entry `4 · Processes` → `#/processes`; route; `tabOf` mapping so detail pages return to the tab; the
profile breadcrumb points at the tab), `README.md` and architecture §8 (tab list), live flow, a test that pins the nav and route.
Out: any re-homing of Sources, Review or Publications; backend changes.

## Protected-code impact (summary)

✅ No protected code touched by any phase — console and docs only.

## Assumptions

- `#/processes` renders the existing `processesList` with its scope selector; `#/processes?scope=…` filters; the subject/profile page's
  crumb points to `#/processes`; `#/browse?mode=processes` keeps working. `tabOf` maps `#/subject/…` detail pages to `#/processes`.

## Phases

### Phase 1 - Tab, route, crumbs, docs
- `ka/console/app.js`; README; architecture §8 → ✅ built; `e2e/plan15_processes_tab_flow.py`; `ka/tests/test_plan15_processes_tab.py`.
- **Protected-code touched:** none

## Code blocks (B1..B1)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/console/app.js` | nav entry, route, tabOf mapping, crumb |

## Deliverables (D1..D4)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | nav entry `4 · Processes` (Dashboard 5, Images 6) and route `#/processes` | `ka/console/app.js` | 1 |
| D2 | `tabOf` maps subject/profile pages back to the Processes tab; profile crumb points at it | `ka/console/app.js` | 1 |
| D3 | README + architecture §8 tab list; Q8 → ✅ built | docs | 1 |
| D4 | live flow | `e2e/plan15_processes_tab_flow.py` | 1 |

**Total deliverables: 4.**

## Positive Test Cases (P1..P3)
- **P1** — the console source declares the Processes nav entry and the `#/processes` route, and keeps `#/browse` with `mode=processes`.
- **P2** — PT7 live: the tab lists process subjects, opens a profile, the breadcrumb returns to the tab, and Browse by scope's Processes mode still renders.
- **P3** — detail pages reached from the tab return to it (back link text names Processes).

## Negative Test Cases (N1..N2)
- **N1** — the four original tabs and Images still exist in the nav, in order; no tab was removed or renamed.
- **N2** — `#/processes?scope=<unknown>` renders an empty state, not an error.

## Plan totals

**Research points covered: 1 of 9 · Deliverables: 4 · Positive cases: 3 · Negative cases: 2 · Test cases total: 5 ·
Product tests served: 1 of 7 (1 turns green here).**

## Implementation Notes
- Written against `77d2291`. Console only.
