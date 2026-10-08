# Plan 16 - The Enterprise Content agent reuses governed knowledge instead of re-extracting every source with the model

Created: 2026-10-09 05:40 UTC

## Problem Description

`EnterpriseContentAgent.research` (`ka/research.py:131-165`) runs the pass-one model extractor over the current text of EVERY source
on the mission's scope chain, on every mission. With the stub model that was instant; with the author's Anthropic key in place
(2026-10-09) a mission over the live store (45 domain sources) makes 45 model calls of up to 4,000 output tokens and 120 s each,
so the synchronous `POST /research/missions` outlives every client timeout and burns tokens re-deriving knowledge the pipeline
already extracted and governed when those sources were ingested. The architecture (§6) already states the rule: "reuse ACTIVE
knowledge on the scope chain; open a mission only for the gap".

Desired outcome: the agent surfaces the governed knowledge that already answers the question (no model call), re-extracts only
sources that have never produced knowledge, capped and most-relevant first, and a real mission on the live store completes in
well under a minute of model time.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Research reuses ACTIVE knowledge on the scope chain; a mission is for the gap | `knowledge-acquisition.md` §6 | ✅ decided (plan-01), only partly built | **completes it** — reuse becomes the agent's first job; re-extraction is the exception |
| Visibility: an agent reads only sources (and knowledge) within the mission's permitted visibility (§42) | `knowledge-acquisition.md` §10 | ✅ built | **constrained by it** — the same clearance filter applies to reused nuggets |
| Agents never decide; candidates go through governance | `knowledge-acquisition.md` §4, §6 | ✅ built | **constrained by it** — reused knowledge is recorded on the run, not re-proposed as a candidate |
| Protected code | `docs/protected.md` | — | **not touched** — `ka/research.py` and `ka/model.py` (a run field) only |

**Open questions in the sections this plan touches:** Q13 — unrelated.

## Research coverage

No research report — problem statement supplied directly (an operational defect exposed when the author supplied the model key;
the rule it enforces is research-01's own §6 reading, already decided). Opened on the tracker as `research-01 R17` so the ship ledger
carries it. **Product-test check:** none of PT1–PT8 runs a mission against a populated store with a real model — a product test
"a mission over a store with 40+ sources completes with bounded model calls" is appended to research-01 as PT9.

## Scope

In: `ka/research.py` (the agent), `ka/model.py` (`ResearchRun.reused_refs`), `ka/config.py` (`KA_RESEARCH_MAX_SOURCES`), the mission page's
run card (one line), tests, docs. Out: the other agents; asynchronous mission execution (a separate question).

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- Reuse: ACTIVE and PENDING_REVIEW/CONFLICT versions whose scope is on the chain, within the permitted visibility (same rule as sources),
  whose normalised statement shares at least one non-trivial token with the objective + questions; ranked by overlap; refs recorded in
  `ResearchRun.reused_refs`; their sources appended to `sources_examined`. No model call.
- Re-extraction: only sources on the chain, within visibility, with non-empty text and NO nugget version referencing them (never
  extracted, or extraction yielded nothing), excluding RESEARCH-channel sources; ranked by section overlap; at most `KA_RESEARCH_MAX_SOURCES`
  (default 3); relevant sections only. This is where the model is spent.
- The plan-01 tests that count model calls and evidence (`phase5 ::test_P2`) ingest sources WITHOUT extraction (`extract=False`-style
  paths or raw `ingestion.*` calls), so they remain re-extraction cases — verified in Phase 1 before coding; if not, that is a correction
  to record, not a reason to weaken them.

## Phases

### Phase 1 - Agent, field, setting
- `ka/research.py`, `ka/model.py`, `ka/config.py`.
- **Protected-code touched:** none

### Phase 2 - Surface, tests, docs
- Run card: "reused N governed nuggets · re-extracted M sources". `ka/tests/test_plan16_research_reuse.py`. Architecture §6 sentence.
  Live check: a real mission on the live store completes (recorded in the checkpoint with its call count and cost).
- **Protected-code touched:** none

## Code blocks (B1..B4)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/research.py` | the agent's reuse-first body |
| B2 | `ka/model.py` | `ResearchRun.reused_refs` |
| B3 | `ka/config.py` | `KA_RESEARCH_MAX_SOURCES` |
| B4 | `ka/console/app.js` | run card line |

## Deliverables (D1..D4)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | reuse-first `EnterpriseContentAgent.research` with the capped re-extraction | `ka/research.py` | 1 |
| D2 | `ResearchRun.reused_refs` | `ka/model.py` | 1 |
| D3 | `KA_RESEARCH_MAX_SOURCES` | `ka/config.py` | 1 |
| D4 | run card line; architecture §6 sentence; research-01 PT9 appended | `ka/console/app.js`, docs | 2 |

**Total deliverables: 4.**

## Positive Test Cases (P1..P4)
- **P1** — a mission whose words match ACTIVE nuggets records their refs in `reused_refs`, their sources in `sources_examined`, and makes no model call for them.
- **P2** — a source with no derived knowledge on the chain is re-extracted with the model (the plan-01 `phase5 ::test_P2` path still holds); sources that already have nuggets are not.
- **P3** — the cap: with six never-extracted sources and `KA_RESEARCH_MAX_SOURCES=2`, exactly the two most relevant are extracted; the run notes the cap.
- **P4** — PT9: a store with 40 extracted sources and a real-shaped provider stub → the mission makes at most `KA_RESEARCH_MAX_SOURCES` extraction calls and completes.

## Negative Test Cases (N1..N3)
- **N1** — reused knowledge respects the permitted visibility exactly as sources do (plan-01 `phase5 ::test_P3` unchanged and a reuse twin).
- **N2** — RESEARCH-channel sources are never re-extracted, even with no derived knowledge.
- **N3** — cap 0: no extraction call, reuse still recorded, the run completes.

## Plan totals

**Research points covered: 1 of 1 (research-01 R17, opened by this plan) · Deliverables: 4 · Positive cases: 4 · Negative cases: 3 ·
Test cases total: 7 · Product tests served: 1 of 9 (PT9 turns green here).**

## Implementation Notes
- Written against `e7aa821`. Restart the live server after the change; the stuck 45-call run dies with it.
