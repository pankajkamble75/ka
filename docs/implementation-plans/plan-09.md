# Plan 09 - The gap request contract (KA half), events as an outbox, and the store benchmark

Created: 2026-10-08 19:40 UTC

## Problem Description

Three research-01 points remain that live entirely inside KA:

- **R11 (KA half).** `GapIn` / `KnowledgeAcquisitionRequest` carry scope, question and a gap description only
  (`ka/api.py:199`, `ka/model.py:444`); every call creates a new request, nothing can be cancelled, and nothing records when a
  request was fulfilled. The note's REQ-010 asks for principal, grammar intent, missing semantics and a correlation id, plus
  dedupe, cancel and status. Whether EOS *calls* this contract is the author's decision (Q7) and is NOT built here.
- **R15.** `events.jsonl` is already an ordered, durable, append-only log, but records carry no sequence number or schema
  version and `GET /events` returns the tail only — a consumer cannot resume at-least-once from where it stopped.
- **R16 (benchmark half).** Nobody has measured the JSON-per-object store at 10k and 100k nuggets; a migration must not be
  proposed, nor dismissed, without the numbers.

Desired outcome: a gap request has a principal, an intent, the missing semantics, a correlation id and a lifecycle
(OPEN → IN_RESEARCH → FULFILLED | CANCELLED); the same gap raised twice while open returns the same request; the console shows
and cancels them. Every event has `seq` and `version`, and `GET /events?after=<seq>` resumes exactly. A benchmark tool exists,
has been run at 10k and 100k, and its numbers are recorded.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Invariant 1: runtime answering never falls back to KA retrieval; a gap becomes a request | `knowledge-acquisition.md` §9 (§43), `docs/protected.md` row `ka/runtime_guard.py` | ✅ built | **extends it under the protected protocol** — the door stays shut; only the request record grows |
| Events carry ids, never content (§38) | `knowledge-acquisition.md` §8 | ✅ built | **constrained by it** — `seq`/`version` are metadata; payload rule untouched |
| Q7 — does EOS route `found_new`/`grow_existing` through a KA request | `questions/knowledge-acquisition.md` Q7 | ❓ open | this plan does NOT need it: the KA contract is built so either answer can use it; the EOS caller is not written |
| Store: one JSON document per object (§36) | `knowledge-acquisition.md` §2 | ✅ built | **measured, not changed** — R16's benchmark is evidence for a later decision |

**Open questions in the sections this plan touches:** Q7 — not blocking (the KA half stands alone).

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R10, R12 | ✅ shipped | plans 02–08 |
| R11 gap request contract (KA half) | ✅ in scope | Phases 1–2; the EOS caller is Q7 (parked) |
| R13 / R14 | ⏭️ parked | Q8 / Q9 — author decisions, no plan |
| R15 events as an outbox | ✅ in scope | Phase 3 |
| R16 benchmark half | ✅ in scope | Phase 4 (layout half shipped in plan-04) |

**Covered here: 3 of 16** (R11 KA half, R15, R16 benchmark half). Parked: 2. Shipped earlier: 11.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| (none of PT1–PT8 names R11, R15 or R16; all eight are GREEN after plan-08) | — | no change |

## Scope

In: `ka/model.py` (`KnowledgeAcquisitionRequest` fields), `ka/runtime_guard.py` (dedupe, cancel, fulfil, status — PROTECTED),
`ka/service.py` (fulfilment subscriber), `ka/repository.py` (seq/version stamping, `events(after=, limit=)`), `ka/api.py`
(`GapIn` fields; `GET /runtime/requests`, `GET /runtime/requests/{id}`, `POST /runtime/requests/{id}/cancel`; `GET /events?after=`),
`ka/console/app.js` (gap table with principal/intent/status and Cancel), `tools/bench_store.py`, benchmark results in
`docs/research/benchmarks/store-bench-2026-10-08.md` and a paragraph in the architecture document, tests, live flow.

Out: the EOS caller (Q7); a broker; any store migration; retry/ack semantics beyond `after=` (at-least-once is the consumer's
to remember).

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/runtime_guard.py` (verified 2026-10-08, plan-01), touched by Phase 2.
HOW: `RuntimeGuard.graph_gap_detected` gains `principal`, `intent`, `missing_semantics`, `correlation_id` and a dedupe step
(an OPEN/IN_RESEARCH request with the same `dedupe_key` is returned instead of a new one; `GapOutcome.deduplicated`);
new methods `cancel`, `fulfil`, `get`, `requests(status=)`. `retrieve_for_answer` is NOT changed.
WHY: the request record is created only inside this file (`ka/runtime_guard.py:35-47`); there is no non-protected path that
can dedupe or change its status without duplicating the guard's write.
Regression risk: the §43 signal path runs on every gap; a dedupe bug could swallow a distinct gap.
Characterization gap: `test_plan01_phase4_corrections.py::test_N1` pins the shut door and the mission trigger; nothing pins
"every call creates a new request" or the `OPEN` status, which is exactly what changes.
Re-verify: `POST /runtime/graph-gap` returns GRAPH GAP DETECTED; no route returns knowledge for a question (plus the new
request routes). Covering test passes UNMODIFIED. Bump the Verified date in the same commit.

No other protected area is touched (`ka/governance.py`, `ka/graph_change.py`, adapters: no edits).

## Assumptions

- `KnowledgeAcquisitionRequest` gains `principal: str = "runtime"`, `intent: str = "answer"` (`found_new | grow_existing | answer |
  other`), `missing_semantics: list[str]`, `correlation_id: str | None`, `dedupe_key: str`, `status` values
  `OPEN | IN_RESEARCH | FULFILLED | CANCELLED`, `updated_at`, `fulfilled_by: list[str]` (nugget refs), `cancelled_reason`.
- `dedupe_key = sha1(scope.key() + "|" + normalised question)[:16]`, or `correlation_id` when given. Dedupe considers only
  OPEN / IN_RESEARCH requests; a FULFILLED or CANCELLED one does not block a new request.
- `open_mission=True` → status `IN_RESEARCH`. Fulfilment: `KnowledgeAcquisition` subscribes to `knowledge.approved`; when the
  approved version's mission (via `ResearchMission.candidate_refs`) is a request's mission, the request becomes `FULFILLED`
  with that ref appended. `cancel` works from OPEN or IN_RESEARCH only (409 otherwise).
- Outbox: `Repository.append_event` stamps `seq` (monotonic int, starting after the last stamped record in the file) and
  `version = "ka-events/1"`. Pre-existing records without `seq` are served with `seq` = their 1-based line number, so
  `after=` is total over the file. `events(after: int | None = None, limit: int | None = None)`; `GET /events?after=&limit=`
  → `{"events": [...], "next_after": <last seq or the given after>, "version": "ka-events/1"}`; default `limit` 200 ascending
  (the old route returned the tail; the console's audit page reads `events` with no `after`, so it now gets the oldest 200 —
  the console is changed to pass `after=-200`? No: it passes `limit=200&tail=1`; a `tail` flag keeps the old behaviour).
- Benchmark `tools/bench_store.py N`: fills a temp repository with N nugget versions across 20 scopes (plus one source each
  per 100 nuggets), then times: cold load of the collection, `nuggets_by_status`, `active_nuggets(scope)`, `search.search`
  (one query), one `put` and one `get`; prints a Markdown table; `--out` appends to the results file. Run at 10k and 100k.

## Phases

### Phase 1 - Request model and characterization (protected protocol steps 1–4)

- `ka/model.py`: the new `KnowledgeAcquisitionRequest` fields (defaults keep old records valid).
- Characterization tests (`ka/tests/test_plan09_gap_requests.py::test_P1_characterization_*`): pin today's behaviour at the seam —
  two identical gaps create two requests, status is `OPEN`, `open_mission` sets the mission trigger, the door raises. Run green
  against UNCHANGED `ka/runtime_guard.py`; land in their own commit.
- **Protected-code touched:** none in this phase (characterization only).

### Phase 2 - The guard (protected protocol steps 5–7)

- `ka/runtime_guard.py`: dedupe, lifecycle, `cancel`, `fulfil`, `get`, `requests`. `ka/service.py`: fulfilment subscriber.
- `ka/api.py`: `GapIn` fields; three request routes. `ka/console/app.js`: gap table + Cancel.
- Covering test `test_plan01_phase4_corrections.py::test_N1` passes UNMODIFIED; live re-verify; `docs/protected.md` Verified bump.
- **Protected-code touched:** ⚠️ `ka/runtime_guard.py` — as declared above.

### Phase 3 - Events as an outbox

- `ka/repository.py`: `seq`/`version` stamping, `events(after=, limit=, tail=)`. `ka/api.py`: `GET /events?after=&limit=&tail=`.
  Console audit page passes `tail=1`.
- **Protected-code touched:** none

### Phase 4 - Benchmark and docs

- `tools/bench_store.py`; run at 10k and 100k; `docs/research/benchmarks/store-bench-2026-10-08.md`; architecture §2 paragraph
  (store) and §8 (outbox) and §9 (request lifecycle); `e2e/plan09_gap_requests_flow.py`.
- **Protected-code touched:** none

## Code blocks (B1..B7)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/model.py` | request fields |
| B2 | `ka/runtime_guard.py` | dedupe + lifecycle (protected) |
| B3 | `ka/service.py` | fulfilment subscriber |
| B4 | `ka/repository.py` | outbox stamping and `events(after=)` |
| B5 | `ka/api.py` | `GapIn` fields, request routes, events route |
| B6 | `ka/console/app.js` | gap table + Cancel; audit tail |
| B7 | `tools/bench_store.py` | the benchmark |

## Deliverables (D1..D9)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `KnowledgeAcquisitionRequest` fields: principal, intent, missing_semantics, correlation_id, dedupe_key, status lifecycle, updated_at, fulfilled_by, cancelled_reason | `ka/model.py` | 1 |
| D2 | characterization tests pinning the pre-change guard, in their own commit | `ka/tests/test_plan09_gap_requests.py` | 1 |
| D3 | `RuntimeGuard.graph_gap_detected` with dedupe; `cancel`, `fulfil`, `get`, `requests` | `ka/runtime_guard.py` | 2 |
| D4 | fulfilment subscriber on `knowledge.approved` | `ka/service.py` | 2 |
| D5 | `GapIn` fields; `GET /runtime/requests`, `GET /runtime/requests/{id}`, `POST /runtime/requests/{id}/cancel` | `ka/api.py` | 2 |
| D6 | console gap table (principal, intent, status, Cancel) | `ka/console/app.js` | 2 |
| D7 | `seq`/`version` on every event record; `Repository.events(after=, limit=, tail=)`; `GET /events?after=` with `next_after` | `ka/repository.py`, `ka/api.py` | 3 |
| D8 | `tools/bench_store.py` and the recorded 10k/100k results | `tools/`, `docs/research/benchmarks/` | 4 |
| D9 | live flow; architecture paragraphs; protected.md Verified bump | `e2e/plan09_gap_requests_flow.py`, docs | 4 |

**Total deliverables: 9.**

## Positive Test Cases (P1..P9)

- **P1** — characterization (pre-change): two identical gaps create two OPEN requests; `open_mission` sets trigger `graph_gap`; the door raises.
- **P2** — a gap with principal, intent `found_new`, missing semantics and a correlation id is stored with all of them; `dedupe_key` equals the correlation id.
- **P3** — the same gap raised twice while OPEN returns the same request id with `deduplicated=True`; a different question creates a new one.
- **P4** — `open_mission=True` → status `IN_RESEARCH`; approving a candidate from that mission marks the request `FULFILLED` with the ref.
- **P5** — `cancel` from OPEN records reason, status and `updated_at`; after cancel the same gap creates a NEW request.
- **P6** — routes: `POST /runtime/graph-gap` (new fields) → `GET /runtime/requests?status=OPEN` lists it → `GET /runtime/requests/{id}` → cancel → 200; cancel again → 409; unknown id → 404.
- **P7** — every appended event carries `seq` (strictly increasing) and `version`; `events(after=n)` returns exactly those with `seq > n`; `GET /events?after=` returns `next_after` usable for exact resumption.
- **P8** — a pre-existing events file without `seq` is served with line-number seqs and new records continue after it.
- **P9** — `tools/bench_store.py 1000` runs and prints the table; the 10k/100k results file exists with both rows (the live run is recorded, not re-run in tests).

## Negative Test Cases (N1..N6)

- **N1** — regression gate: `test_plan01_phase4_corrections.py::test_N1` passes UNMODIFIED after the change (and the door still raises).
- **N2** — dedupe never swallows a distinct gap: same question in a different scope → a new request; FULFILLED/CANCELLED requests do not dedupe.
- **N3** — `cancel` of a FULFILLED or CANCELLED request raises `ValueError` (409 at the route); an unknown intent value is rejected (422).
- **N4** — a `knowledge.approved` event for a nugget with no mission leaves every request untouched; a failing subscriber cannot break approval.
- **N5** — `after` beyond the end returns an empty list with `next_after == after`; a negative `limit` is 422.
- **N6** — the `seq` stamp is not affected by `EventBus.history` (in-memory) and the payload content rule (§38) still rejects long strings.

## Plan totals

**Research points covered: 3 of 16 · Deliverables: 9 · Positive cases: 9 · Negative cases: 6 · Test cases total: 15 ·
Product tests served: 0 of 8 (all eight already green).**

## Implementation Notes

- **Re-check against the tree before implementing** — written after plan-08 landed (`5037296`).
- Protected protocol order: Phase 1's characterization commit lands BEFORE any edit to `ka/runtime_guard.py`.
- The 100k benchmark may take minutes; run it detached and record the real numbers — never estimate them.
