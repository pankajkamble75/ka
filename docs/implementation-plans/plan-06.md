# Plan 06 - The process profile: a composed, evidence-linked view of what KA knows about a process

Created: 2026-10-08 16:55 UTC

## Problem Description

Plan-03 gave nuggets subjects and bindings; plan-04 fills them from documents; plan-05 publishes them. What nobody can see
yet is the **profile** of a process: its description, its type and whether it is bound, its activities in order, who
performs it, what it consumes and produces, which rules govern it, and — most importantly — what is *not known*, each
populated field pointing at the evidence span that supports it (note REQ-012 "Processes" page; research-01 §2 "a
query, not an object"; R12). Today a subject page lists assertions as rows (`ka/console/app.js::subjectView`), which is a
list, not a profile; it shows no gaps and no coverage against the type's required slots.

Desired outcome: for a process subject, one view that composes the ACTIVE (and, marked, pending) assertions by predicate
into the shape EOS's grammar expects — description, type (bound / proposed / unresolved / **not evidenced**), activities
(`decomposes_into` children, each a link to its own profile), actors, inputs, outputs, rules, events, states — with a
coverage line against the bound type's required/recommended slots ("input: evidenced · rule: not evidenced"), every field
clickable to its nugget and evidence, and the graph element it is published as. It lives inside tab 3 (Browse by scope)
as a "Processes" mode and on the subject page, so the tab count the author ruled on does not change while Q8 is parked.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| A process profile is a composed view of evidence-backed claims, not a giant nugget | `research-01.md` §2; `knowledge-acquisition.md` §5a | ✅ built (model) | **builds the view** — a query over ACTIVE/PENDING versions by subject, never a stored object |
| Binding statuses; EOS slot grammar per type (`required / recommended / optional`) | `knowledge-acquisition.md` §5a; EOS `process_types.json` | ✅ built | **constrained by it** — coverage is computed against `GrammarRegistry.type_grammar(bound_type)`; nothing is filled in |
| Console is four tabs plus Images; Q8 parks the Processes-tab question | `knowledge-acquisition.md` §8; `questions/knowledge-acquisition.md` Q8 | ❓ open | **obeyed** — the profile is a mode inside Browse by scope and the subject page; no new tab |
| Invariant 1: no runtime answering from KA | `knowledge-acquisition.md` §1 | ✅ built | **constrained by it** — the profile is a governance view of knowledge, not an answer endpoint; it reads only governed KA data |
| Lineage both ways (§15) | `knowledge-acquisition.md` §5 | ✅ built | **constrained by it** — the profile shows `where_used` per assertion |

**Open questions in the sections this plan touches:** Q8 — not needed (built inside existing surfaces); Q9 — not needed.

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1, R2, R3, R4, R5, R6, R7, R8 | ✅ shipped | plans 02–05 |
| R9 discovery | ⏭️ deferred | plan-07 |
| R10 connectors | ⏭️ deferred | plan-08 |
| R11 gap routing | ⏭️ deferred | plan-09 |
| R12 process profile view | ✅ in scope | Phases 1–3 |
| R13 console shape | ⏭️ deferred | Q8 parked; this plan needs no answer |
| R14 EOS frontend re-pin | ⏭️ deferred | Q9 parked |
| R15 outbox | ⏭️ deferred | plan-09 |
| R16 benchmark half | ⏭️ deferred | plan-09 |

**Covered here: 1 of 16** (R12). Deferred: 7. Shipped earlier: 8. Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 (already GREEN since plan-04) | R2, R3 | stays GREEN — the profile is where a reviewer *sees* what PT1 asserts |

No product test turns green here: R12 is a view over capabilities PT1–PT4 already prove. The plan carries its own P/N cases.

## Scope

In: `ka/profile.py` (new — the composition and coverage query), `ka/service.py` (`process_profile`), `ka/api.py`
(`GET /processes`, `GET /processes/{key}`), `ka/console/app.js` (Processes mode in Browse; subject page becomes the profile for
process subjects), tests, live flow, architecture §8.

Out: a new tab (Q8); editing from the profile beyond the existing nugget actions; the EOS-side panel (Q9).

## Protected-code impact (summary)

✅ No protected code touched by any phase — the plan adds a read-only query module, two read routes, service and console code;
`ka/governance.py`, `ka/graph_change.py`, `ka/runtime_guard.py` and their shared dependencies are not edited.

## Assumptions

- A **process profile** composes, for subject `(process, key)`: `description` (latest ACTIVE `description` assertion's object
  value, else the first ACTIVE statement about the subject), `type` (from the ACTIVE `typed_as` assertion's binding: the type and
  status; `not_evidenced` when none), `activities` (ACTIVE `decomposes_into` objects in nugget creation order — the order the
  document listed them — each with its child key, statement ref and evidence), `actors` (`performed_by`), `inputs` (`consumes`),
  `outputs` (`produces`), `entities` (`acts_on`), `rules` (`governed_by`), `events` (`emits`), `states` (`transitions_to`,
  `precondition`, `postcondition`), `related` (`related_to`). PENDING_REVIEW/CONFLICT assertions appear in a separate `pending`
  list, never merged into the profile.
- **Coverage**: when the type is `bound`, `GrammarRegistry.type_grammar(type)` gives slot → level; each slot maps to profile
  fields through `ka/binding.py::PREDICATE_TABLE` (slot ← predicate) plus `description` ↔ `goal` (prop fallback) and
  `decomposes_into` ↔ `action`; a slot is `evidenced` when at least one ACTIVE assertion fills it, else `not_evidenced`; the
  line reports required and recommended slots only. Without a bound type: "coverage needs a bound type".
- Every field carries `{ref, statement, evidence: [{source_title, locator, span_id}], published_as: [graph_id/element_id]}`.
- `GET /processes` lists process subjects with counts (assertions, activities, pending) and type status; `GET /processes/{key}`
  returns the profile. Both are read-only and sit behind the plan-02 access policy like every route.
- Console: Browse by scope gains a "Processes" mode button beside the scope filters; it lists process subjects (optionally
  filtered by the chosen scope: subjects with at least one ACTIVE assertion in that scope or its ancestors) and opens the profile
  at `#/subject/<key>`, which renders the profile for `process` subjects and the plain assertion table for other kinds.

## Phases

### Phase 1 - Profile query

- `ka/profile.py`: `ProfileField`, `Activity`, `ProcessProfile` (pydantic), `ProfileService(repo, grammar, lineage)` with
  `profile(key) -> ProcessProfile`, `coverage(profile) -> list[{slot, level, status, via}]`, `list_processes(scope=None)`.
- `ka/service.py`: `self.profiles = ProfileService(...)`; `process_profile(key)`.
- **Protected-code touched:** none

### Phase 2 - API

- `ka/api.py`: `GET /processes?scope_type=&scope_id=` and `GET /processes/{key}` (404 for a non-process or unknown subject).
- **Protected-code touched:** none

### Phase 3 - Console, flow, docs

- `ka/console/app.js`: `processProfileView(key)` (description, type pill with status, coverage line, activity list with links,
  actor/input/output/rule/event/state cards, pending assertions, published-as elements); `subjectView` delegates to it for
  process subjects; Browse by scope "Processes" mode listing.
- `e2e/plan06_profile_flow.py`: upload the fixture SOP, approve the process assertions, open the profile, assert description,
  five activities in order, actor, and a coverage line.
- `docs/architecture/knowledge-acquisition.md` §8: the profile; README one line.
- **Protected-code touched:** none

## Code blocks (B1..B4)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/profile.py` | profile models, composition, coverage, listing |
| B2 | `ka/service.py` | wiring and `process_profile` |
| B3 | `ka/api.py` | the two routes |
| B4 | `ka/console/app.js` | profile view, Browse "Processes" mode, subject-page delegation |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `ProcessProfile`, `ProfileField`, `Activity` models | `ka/profile.py` | 1 |
| D2 | `ProfileService.profile(key)` composing by predicate, ACTIVE only, pending separate | `ka/profile.py` | 1 |
| D3 | `ProfileService.coverage(profile)` against the bound type's slot grammar | `ka/profile.py` | 1 |
| D4 | `ProfileService.list_processes(scope)` | `ka/profile.py` | 1 |
| D5 | `GET /processes`, `GET /processes/{key}` | `ka/api.py` | 2 |
| D6 | `processProfileView`, Browse "Processes" mode, subject-page delegation | `ka/console/app.js` | 3 |
| D7 | architecture §8 paragraph; live flow | docs, `e2e/plan06_profile_flow.py` | 3 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P8)

- **P1** — after uploading the fixture SOP and approving its process assertions, `profile("merchant_underwriting")` has the SOP's description, five activities in document order with child keys `collect_application` … `communicate_decision`, and actor "Underwriting team".
- **P2** — every field carries a nugget ref and at least one evidence entry whose `span_id` is `s1`, and `published_as` names `p.merchant_underwriting` (in-memory adapter) after application.
- **P3** — with an ACTIVE bound `typed_as decision`, `coverage` reports `input: not_evidenced (required)`, `rule: not_evidenced (required)`, `action: evidenced (optional)`, `actor: evidenced (optional)` … exactly per the fixture grammar's `decision` slot levels.
- **P4** — without a typed_as assertion, `type.status == "not_evidenced"` and `coverage == []` with the note "coverage needs a bound type".
- **P5** — a PENDING_REVIEW assertion about the subject appears under `pending`, not in the profile fields.
- **P6** — `list_processes()` lists `merchant_underwriting` with `activities == 5`; `list_processes(scope=D)` includes it and `list_processes(scope=A)` includes it too (ancestor), while an unrelated scope does not.
- **P7** — `GET /processes/merchant_underwriting` returns the profile JSON; `GET /processes` lists it.
- **P8** — console live flow: the profile page shows the description, the five activities in order, the actor and the coverage line (`e2e/plan06_profile_flow.py`).

## Negative Test Cases (N1..N5)

- **N1** — a superseded `description` version does not appear: after a revision is approved, the profile shows the new description and the old ref is absent.
- **N2** — a REJECTED assertion contributes nothing, neither to fields nor to `pending`.
- **N3** — `GET /processes/no_such_key` → 404; `GET /processes/<an entity subject key>` → 404 with "not a process".
- **N4** — an activity whose child subject has no profile of its own renders without error and with `has_profile == False`.
- **N5** — the profile never invents: a type-less process has no `type.value`; no field is populated from a statement that lacks a subject.

## Plan totals

**Research points covered: 1 of 16 · Deliverables: 7 · Positive cases: 8 · Negative cases: 7 · Test cases total: 15 ·
Product tests served: 1 of 8 (0 turn green here).**

## Implementation Notes

- **Re-check this plan against the tree before implementing.** Written after plan-05 landed (`282b8f1`); confirm
  `Repository.nuggets_by_subject` and `GrammarRegistry.type_grammar` exist unchanged.
- No characterization commit is needed (no protected code).
- Activity order: nugget `created_at` order within the subject; the fixture's five steps are ingested in document order.
- **Correction during implementation (2026-10-08 17:20 UTC).** P2 exposed a lineage defect inherited from plan-01's `apply`
  (`ka/graph_change.py`): when a second nugget publishes onto an element another nugget already depends on, the loop
  `for old in dependencies_for_element: if old.nugget_ref != v.ref: retire` retires the OTHER nugget's dependency, so a node
  composed from several assertions (canonical identity, plan-05) keeps only the last one — Invariants 4/5 broken for composed
  elements. The fix retires only prior versions of the SAME canonical id. This touches protected `ka/graph_change/`, which this
  plan did not declare: the protocol is followed anyway — characterization N6 (the defect, pinned pre-fix) in its own commit,
  the fix, covering suites unmodified, Verified date bumped. Plan totals become 8 positive / 6 negative (N6 added).
- **Second correction (17:35 UTC).** On the shared demo store the profile showed 12 activities: repeated uploads approved as
  duplicates (`analysis.duplicate_of`) made duplicate ACTIVE assertions. The profile now composes identical ACTIVE assertions once
  (first wins; later refs on `also`; `counts.duplicates`) — N7 added. Whether governance should allow such approvals at all is the
  author's: parked as **Q11** (questions document + registry). Plan totals become 8 positive / 7 negative.
