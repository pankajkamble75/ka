# Plan 17 - Missions run in the background; the mission page polls a RUNNING state (Q14)

Created: 2026-10-09 07:20 UTC

## Problem Description

`POST /research/missions` creates the mission and runs every agent before answering (`ka/api.py:622-627`; `run_mission` at
`ka/research.py:325-352`). The first live mission with the real model took 508 s: the console's Start research button sat silent, and a
client that times out loses the response while the server keeps working. The author decided (Q14, 2026-10-09): background run plus
poll — the mission is created and returned at once in RUNNING, a worker thread runs the agents, the mission page polls until COMPLETED
or FAILED and shows progress; `wait=true` keeps the synchronous path for scripts and tests.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q14 background run + poll; `wait=true` stays synchronous | `knowledge-acquisition.md` §6 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| Mission lifecycle REQUESTED → RUNNING → COMPLETED / FAILED (§16) | `knowledge-acquisition.md` §6 | ✅ built | **constrained by it** — the worker moves the same states; nothing new in the vocabulary |
| One agent failing must not lose the others (plan-01) | `ka/research.py:336-339` | ✅ built | **constrained by it** — unchanged inside the worker |
| Protected code | `docs/protected.md` | — | **not touched** — research, api, model, console |

**Open questions in the sections this plan touches:** Q13 — unrelated.

## Research coverage

No research report — the author's Q14 decision, opened on the tracker as `research-01 R18`. **Product-test check:** research-01 PT10
(appended): "starting a mission returns within a second with status RUNNING; the mission page shows progress and ends COMPLETED without
the client waiting on the request".

## Scope

In: `ka/research.py` (`start_mission`, `_execute`, progress), `ka/model.py` (`ResearchRun.progress`), `ka/api.py` (`wait` on create and
run; 409 when already RUNNING), `ka/console/app.js` (navigate at once; poll every 2 s while RUNNING; progress line), tests, live flow,
the flows/tests that relied on the synchronous response (`wait: true`), docs.

Out: a persistent job queue; cancelling a running mission (CANCELLED exists in the vocabulary but is a separate decision); parallel agents.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- `ResearchOrchestrator.run_mission(id)` keeps its synchronous contract and now wraps `_execute(run, mission)`.
  `start_mission(id) -> ResearchRun` creates the run (RUNNING) and the mission state, starts a daemon `threading.Thread` on `_execute`,
  keeps the thread in `self._threads[mission_id]` (tests join it), returns the run at once. A mission already RUNNING is refused
  (`ResearchError`, 409).
- `ResearchRun.progress = {"agents_total", "agents_done", "current_agent", "candidates_so_far", "started_at", "updated_at"}` saved after
  each agent so `GET /research/missions/{id}` shows it mid-run.
- `MissionIn.wait: bool = False` (background is the default per the decision); `POST /research/missions/{id}/run?wait=`. The response
  carries the run in both cases (RUNNING or finished). Tests and flows that need the finished run pass `wait: true`.
- Console: Start research → `location.hash = #/mission/<id>`; `missionView` re-renders every 2 s while the mission is RUNNING and shows
  "running · agent k/n (name) · candidates so far · elapsed".

## Phases

### Phase 1 - Orchestrator and model
- `ka/research.py`, `ka/model.py`.
- **Protected-code touched:** none

### Phase 2 - API, console, callers
- `ka/api.py`; `ka/console/app.js`; `wait: true` where a test or flow needs the finished run.
- **Protected-code touched:** none

### Phase 3 - Tests, flow, docs
- `ka/tests/test_plan17_background_missions.py`; `e2e/plan17_background_mission_flow.py`; architecture §6/§8 → ✅; research-01 PT10.
- **Protected-code touched:** none

## Code blocks (B1..B4)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/research.py` | `start_mission`, `_execute`, progress |
| B2 | `ka/model.py` | `ResearchRun.progress` |
| B3 | `ka/api.py` | `wait`, 409 |
| B4 | `ka/console/app.js` | navigate + poll + progress |

## Deliverables (D1..D5)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `start_mission` (thread, RUNNING at once, refuses a running mission), `_execute`, `run_mission` unchanged in contract | `ka/research.py` | 1 |
| D2 | `ResearchRun.progress` updated per agent | `ka/model.py`, `ka/research.py` | 1 |
| D3 | `wait` on both routes; 409 on a RUNNING mission | `ka/api.py` | 2 |
| D4 | console: navigate at once, poll every 2 s, progress line | `ka/console/app.js` | 2 |
| D5 | live flow; architecture ✅; research-01 PT10 | `e2e/plan17_background_mission_flow.py`, docs | 3 |

**Total deliverables: 5.**

## Positive Test Cases (P1..P5)
- **P1** — `start_mission` returns within a second with run and mission RUNNING; after the thread joins both are COMPLETED and candidates exist.
- **P2** — progress advances per agent (agents_done 0→n, current_agent set) and is readable from the repository mid-run (a slow stub agent).
- **P3** — `POST /research/missions` returns RUNNING at once by default; `GET /research/missions/{id}` shows COMPLETED after the join; the same with `/run`.
- **P4** — `wait: true` returns the finished run as before (the plan-07/13 flows and tests keep working with it).
- **P5** — PT10 live: Start research in the console lands on the mission page within a second showing "running"; the page ends COMPLETED with candidates without the client waiting on the request.

## Negative Test Cases (N1..N3)
- **N1** — an agent raising inside the worker → the mission ends FAILED with the error on the run; nothing propagates out of the thread.
- **N2** — starting a mission that is already RUNNING is refused (409); the running one is untouched.
- **N3** — a client that disconnects does not affect the worker: the mission still completes (the response is not awaited).

## Plan totals

**Research points covered: 1 of 1 (research-01 R18, opened by this plan) · Deliverables: 5 · Positive cases: 5 · Negative cases: 3 ·
Test cases total: 8 · Product tests served: 1 of 10 (PT10 turns green here).**

## Implementation Notes
- Written against `7e0ec38`. No protected code. Restart the live server after upload.
