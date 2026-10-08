---
name: create-implementation-plan
description: Create numbered implementation plan documents for requested problem statements. Use when the user asks to create, write, draft, or generate an implementation plan, planning document, phased implementation plan, or plan-only artifact. The skill must create the plan under docs/implementation-plans and must not implement code changes for the requested problem.
---

# Create Implementation Plan

## Required Behavior

When asked to create an implementation plan:

0. **Decide how many plans the work needs, FIRST.** A research report with N points does not mean one plan.
   Split where the work genuinely splits — different files, no shared code, no ordering constraint — and
   write **one plan per independently-scopable piece**. See "Planning a set" below. Announce the set and its
   numbers before writing any of them.
1. Create only plan documents. Do not implement the plan, modify product code, run migrations, or change behavior for the problem being planned.
1b. **Read the ARCHITECTURE the plan must obey, and build against it.**
   `docs/architecture/architecture-index-lookup.md` lists every architecture document and what it owns —
   read it, follow it to the documents this plan touches, and read those. The Q&A behind each is in
   `docs/questions/`, in the author's own words.

   **A decision already made is a CONSTRAINT on the plan, not an option for it.** Where a document says
   how something is to work, the plan follows it and **cites it** — *"per `agent-x-orchestration.md` §7,
   the connector is Agent_X's"* — so a reader can see the plan is executing a decision rather than
   inventing one. A plan that contradicts a decided question, silently, is the failure this step prevents.

   **Two things worth checking while you are there.** A decision marked `⏳ decided, not built` that this
   plan builds should have its state moved to `✅ built` when the work lands — name that in the plan's
   deliverables. And a question marked `❓ open` in a section this plan touches is a **stop**: if the plan
   needs that answer, it cannot be written yet; say so and park it rather than guessing.
2. Write the plan under `docs/implementation-plans` (create the directory if it does not exist).
3. Name the file with the next available plan number:
   - Use files matching `plan-*.md` in `docs/implementation-plans`.
   - Extract numeric suffixes such as `plan-01.md`, `plan-1.md`, or `plan-001.md`.
   - Choose the next integer after the highest existing plan number.
   - Format new files as `plan-XX.md` with at least two digits, for example `plan-01.md`, `plan-02.md`, `plan-10.md`.
4. Include the creation date and time using the local system time available in the environment.
5. Base the plan on the problem statement in the user's request. If the request does not contain a clear problem statement, ask for it before creating the file.
6. **Protected-code assessment (required — run it LAST, after the whole plan is drafted).** Once every phase is written, do a dedicated assessment pass over the complete plan and cross-reference every file/area it will touch (across all phases) against the protected registry at `docs/protected.md`. A protected area is flagged when the plan **either** edits a file under that area's protected paths **or** edits one of that area's listed *shared dependencies* (a shared component, helper, model field, or route the area consumes — these break protected behaviour without the protected file itself changing). Then record the result in TWO places:
   - **Per phase** — add a `Protected-code touched:` line to EVERY phase, naming the protected area(s) that phase affects (or `none`).
   - **Summary** — fill the top-level `## Protected-code impact` section, rolling up every flagged area across the plan (which phase(s) touch it, the regression risk, and the re-verify flow + tests).
   If `docs/protected.md` is absent, say so and treat nothing as protected. This pass is what lets the reader scope re-testing: untouched protected areas need no re-test; touched ones name exactly which flow to re-run.
7. **Protected code MAY be modified.** Being protected is *not* a reason to route around a change or defer a phase. It is a reason to change it under discipline. When a phase edits protected code, that phase MUST spell out the protocol in §"Protected-code change protocol" below, and the plan MUST include the extra test cases it requires. A plan that avoids a protected file by choosing a worse design has made the wrong trade — say plainly why the alternative is better *on the merits*, or edit the protected file.

## Protected-code change protocol

Any phase that edits protected code follows these steps **in order**, and the plan states them explicitly for
that phase. Do not skip a step; do not reorder tests after the change.

1. **Declare — how and why.** Name the exact file(s) and function(s), state precisely *what* changes in them,
   and state *why no non-protected path achieves the requirement*. If a non-protected alternative exists but
   is worse, say why it is worse. "It was easier" is not a reason; "the seam is inside the pipeline and has
   no public entry" is.
2. **Characterize the current behaviour FIRST.** Write tests that pin what the code does **today** at the
   exact seam being changed, and get them green **before** editing anything. If the current behaviour is
   unknown or unproven, discovering it is the phase's first deliverable. Check whether the existing suite
   actually pins the seam — a test that asserts a file *exists* but never its *content* does not pin content.
3. **Add MORE positive and negative tests around the protected contract**, beyond characterization, and land
   them **before** the change. Negative cases matter most here: failure isolation, cancellation, budget
   limits, opt-out paths, and anything the protected code guarantees to callers.
4. **Make the change** per the requirement.
5. **The area's EXISTING covering tests must pass UNMODIFIED.** This is the exit criterion. A protected test
   that needs its assertion edited to go green is a regression to escalate, not a test to update. Say this
   in the plan as a named negative test case.

   **What "UNMODIFIED" governs — `Q170`, the author, 2026-09-18.** It governs a test's **ASSERTIONS**.
   **Re-pointing how a test INJECTS its input** — a fixture, a call argument, an injection seam that a
   RULED decision has relocated — **is not editing an assertion**, and is not the regression this criterion
   exists to catch. A diff that moves only the call line, leaving every assertion byte-identical, is
   auditable as such and is allowed.

   ⚠️ **This is not permission to edit covering tests.** What the test CLAIMS may not move; only how it is
   driven. And the case that settled it argues for care in the opposite direction from the obvious one:
   when `Q168` moved a seam, one of the five affected cases —
   `test_plan213_affordable_replay::test_P2_an_ample_budget_drops_NOTHING` — **kept passing for the wrong
   reason**, because the un-threaded default happened to satisfy what it asserted. **Refusing the
   re-point would have preserved a case that had stopped measuring anything.** Reasoning:
   [`docs/questions/agent-x-coding-lifecycle.md`](../../../docs/questions/agent-x-coding-lifecycle.md) — `Q170`.
6. **Re-verify live** — run the area's documented re-verify flow from `docs/protected.md` against a running
   backend.
7. **Bump the `Verified:` date** for that area in `docs/protected.md` **in the same commit** as the change,
   noting what was re-verified. `docs/protected.md` requires this: a stale date is worse than no date.

Sequencing guidance: put protected-code phases **late** in the plan where dependencies allow, so that when a
regression appears in that area it is unambiguously attributable to that phase. Prefer landing the
characterization + new tests as their own commit (green against unchanged code) before the commit that makes
the change.

## Plan Structure

Use this structure:

```markdown
# Plan XX - <Short Title>

Created: <YYYY-MM-DD HH:MM local time>

## Problem Description

<Describe the problem statement and desired outcome.>

## Architecture and decisions this plan obeys

<REQUIRED. From `docs/architecture/architecture-index-lookup.md` — see step 1b. One row per decision the
plan executes or is constrained by, so a reader can see the plan is carrying out decisions rather than
inventing them.>

| decision | where | state | what this plan does about it |
|---|---|---|---|
| <the rule, in one line> | `<topic>.md` §N | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| <the rule> | `<topic>.md` §N | ✅ built | **constrained by it** — cited at Phase 2 |

**Open questions in the sections this plan touches:** <`Q103` — *the compute failure branch* — this plan
does NOT need it answered> | <none> | <**BLOCKING: `Q104` must be answered before Phase 3 can be written**>

<The reasoning behind each decision is in `docs/questions/<topic>.md`, in the author's own words. Read it
before disagreeing with one — and if the plan must diverge, say so openly with the decision's date, never
silently.>

## Research coverage (R1..Rn)

<REQUIRED when the plan derives from a research report; omit only when there is none, and say so.
EVERY research point gets a row — none may be silently absent. See "Research coverage" below.>

Source: [research-NN](../research/research-NN.md) — **N research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 <short title> | ✅ in scope | Phase 2 |
| R2 <short title> | ⏭️ deferred | its own plan — <reason on the merits> |
| R3 <short title> | ❌ rejected | <why this plan declines it> |

**Covered here: X of N.** Deferred: Y (each with a reason above). Rejected: Z.

### Product tests this plan serves

<REQUIRED when the research defines any. A product test asks whether the PRODUCT does what the research
said — it belongs to the research, not to this plan, and usually becomes true only when the LAST plan of
the set lands. List the ones this plan moves toward, and say plainly whether this plan is the one that
turns them green.>

| Product test | Proves | After this plan |
|---|---|---|
| PT1 <capability> | R3, R7 | still RED — needs plan-NN |
| PT2 <capability> | R5 | **GREEN** — this plan is what makes it true |

**A plan that turns no product test green is not thereby wrong** — most plans are one step of several. But
if NO plan in the set ever turns a given test green, the set does not deliver the capability, and that is a
gap to name now rather than discover at the end.

## Scope

<State what is included and, when useful, what is explicitly out of scope.>

## Protected-code impact (summary)

<Filled LAST, after all phases are written; rolls up the per-phase "Protected-code touched" lines,
checked against `docs/protected.md`. One of:>
<- "✅ No protected code touched by any phase — <why: only new files / only non-protected areas>."
   (then re-testing of protected areas is not required for this plan), OR>
<- One "⚠️ TOUCHES PROTECTED" block per affected area:>
<  ⚠️ TOUCHES PROTECTED — <area name> (verified <date>), touched by Phase(s) <n>.
   HOW: <the exact file(s)/function(s) and what changes in them>.
   WHY: <why no non-protected path achieves the requirement; if an alternative exists, why it is worse>.
   Regression risk: <what could break, and how widely — e.g. "runs on every build, not just the new path">.
   Characterization gap: <what the existing tests do NOT currently pin at this seam>.
   Re-verify: <that area's flow> (<its covering tests>). Bump its Verified date in the same commit.>

<If any area is flagged, also state which avoidances elsewhere in the plan were NOT protection-driven and
therefore stand on their own merits — so a reader can tell a deliberate design choice from a dodge.>

## Assumptions

- <Assumption 1>
- <Assumption 2>

## Phases

### Phase 1 - <Name>

- <Concrete planning step>
- <Expected output or decision>
- **Protected-code touched:** <none | ⚠️ <area>(s) from docs/protected.md — which file/shared-dependency + why>

### Phase 2 - <Name>

- <Concrete planning step>
- <Expected output or decision>
- **Protected-code touched:** <none | ⚠️ <area>(s) from docs/protected.md — which file/shared-dependency + why>

<A phase that DOES touch protected code additionally spells out the seven protocol steps for itself:
declare (how + why), characterize first, add coverage, change, existing tests pass unmodified, re-verify
live, bump the Verified date.>

## Code blocks (B1..Bk)

<REQUIRED when the plan writes CODE; `none — docs only` when it does not. One row per intended block:
the file, and one line on what the block contains. `plan-720`, the author's note 2026-09-19.>

| # | File | What the block contains |
|---|---|---|
| B1 | `path/to/module.py` | <the coherent change this plan makes to this file> |

**ONE BLOCK PER PLAN PER FILE.** The author's words: *"dont go very granular."* Not per function, not
per region — research-191 `R4` turns that instinct into a reason: an architecture citation is a single
LINE, and a coarse block is a range wide enough that a citation written months earlier still lands
inside it. Per-function blocks amplify the drift `test_architecture_citations::test_P5` documents.

**A declared block IS a deliverable** — a file plus a marker a grep can find — so `implement` writes it
and `verify` reconciles it, using the machinery that already reports on D1..Dm.

**Declared, not guessed.** A plan that will touch three files declares three blocks, and that number is
checkable before a line is written. If the build ends up touching a file the plan did not declare, that
is a FINDING to report (`implement`), not a block to add quietly — the mismatch is the signal that
scope moved during the build.

## Deliverables (D1..Dm)

<REQUIRED and numbered. The checklist `implement` reports against, item by item. One row per thing that
must EXIST in the tree when the plan is done — a function, a field, a route, a component, a flow. Not
activities ("update the tests"), artifacts.>

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | <the concrete thing that must exist> | `path` | 1 |
| D2 | … | | |

**Total deliverables: m.**

## Positive Test Cases (P1..Pi)

<Numbered. Each is a case, not a suite.>

- **P1** — <Expected successful behavior or validation case>
- **P2** — <For each protected-touching phase: the characterization cases that pin CURRENT behaviour
  before the change, then the new positive cases covering the protected contract.>

## Negative Test Cases (N1..Nj)

- **N1** — <Expected failure, invalid input, regression, or guardrail case>
- **N2** — <For each protected-touching phase: negative cases for the guarantees the protected code makes
  to its callers (failure isolation, cancellation, budget, opt-out), PLUS a named regression-gate case:
  "every covering test listed in docs/protected.md for <area> passes UNMODIFIED".>

## Plan totals

<REQUIRED and LAST. The contract `implement` and `verify` reconcile against — one line, so a later reader
can check the arithmetic without reading the plan.>

**Research points covered: X of N · Deliverables: m · Positive cases: i · Negative cases: j ·
Test cases total: i+j · Product tests served: s of P (t turn green here).**

## Implementation Notes

- <Important sequencing, dependencies, risks, or verification notes.>
```

## Planning a set — when one report needs several plans

A research report's points are often unrelated work: a new service, a derived field on a model, a
two-line guard in a subscriber. They share no code and no ordering. **Write one plan per piece**, in a
contiguous block of numbers, and make the set itself accountable:

- **Split where the work splits.** Two points belong in one plan only if they touch the same code and
  would be verified by the same evidence. Otherwise a single plan gets one protected-code assessment
  spanning three areas, one test ledger mixing three concerns, and a halt in any part stalling the rest.
- **Allocate the numbers up front** — `plan-84`, `plan-85`, `plan-86` — so each plan can name its
  siblings and say which point goes where.
- **The SET must cover every research point.** Each plan says `Covered here: X of N`; across the set those
  must account for all N as covered, deferred-with-a-named-plan, or rejected-with-a-reason. A point that
  appears in no plan's table is the leak this convention exists to stop.
- **State the set before writing it**, in numbers:

  > *research-14 has 5 points → 3 plans. plan-84 covers R1+R2 (same module), plan-85 covers R3,
  > plan-86 covers R4. R5 is rejected — reason in plan-84.*

- **Order them by dependency, then by cost.** A later plan may rest on an earlier one's output; say so in
  its Assumptions.
- **Update the tracker.** Move each covered point `OPEN` → `PLANNED` with its plan number, and add a
  `DEFERRED` or `REJECTED` row (with its reason) for every point the set does not cover. After this stage
  no point from the report may still be `OPEN` without a deliberate note saying why.

### The set is planned; it is not all built at once

Each plan in the set is implemented, verified and uploaded **on its own**, in order — one checkpoint per
plan, so each is separately revertible and the history reads plan by plan.

**A plan written three deep, before its predecessors are built, is more likely to be wrong.** plan-81 is
the example: its design was corrected during implementation because investigating the real corpus
contradicted the brief. So every plan after the first carries this instruction in its Implementation
Notes, and the reader must honour it:

> **Re-check this plan against the tree before implementing.** It was written before plan-NN landed; if
> anything it assumes has since changed, stop and say so rather than building against a stale premise.

That is the cost of planning ahead, and it is worth paying for the accountability the set buys — but only
if the re-check actually happens.

## Research coverage — reconciling against the report

When the plan derives from a research report, the report ends with a numbered ledger (`R1..Rn`) and a
total. **Every one of those N points gets a row in `## Research coverage`** — marked in scope, deferred, or
rejected, and a deferral or rejection needs a reason on the merits. Nothing may be absent.

This is the check that catches the failure this section exists for: a plan that quietly covers three points
of seven, ships, and leaves four that nobody notices are missing until much later.

- **Deferring is fine; silence is not.** A plan that covers 2 of 7 is often correct — small plans verify
  better. Say `Covered here: 2 of 7` and name where the other five go.
- **If the plan covers all N, say `X of N` with X = N.** The reader should not have to count.
- **No research report?** Say so in that section (`No research report — problem statement supplied
  directly`) rather than deleting the heading, so its absence is visible.

## Numbering the deliverables and test cases

`implement` reports against these item by item, and `verify` re-checks them. That only works if they are
countable:

- **A deliverable is a thing that will EXIST**, not work that will happen. "D3 — `chain_for_proposal()` in
  `learning_campaign/chain.py`" is checkable by grep; "D3 — refactor the reader" is not.
- **A test case is one case**, not a file. `P4` and `N7` each map to one test that can pass or fail.
- **Give every test case a number**, including the protected-code characterization and regression-gate
  cases. Those are the ones most often described in prose and then not written.
- **State the totals in one line.** `verify` compares its own count of what exists against these numbers,
  so they must be arithmetic, not adjectives.

## Quality Rules

- **Product tests are the RESEARCH's, not the plan's.** Carry the ones this plan serves, say whether it
  turns them green, and never rewrite one to fit what the plan happens to build — a product test
  bent to match a deliverable has become a positive case and stopped measuring the capability.
- **The numbered sections are mandatory**: `## Research coverage` (when a report exists), `## Deliverables`,
  numbered `P`/`N` test cases, and `## Plan totals`. A plan without them cannot be reconciled by the stages
  that follow, which is the whole point of numbering them.
- **Never drop a research point without a row.** Deferred and rejected are legitimate outcomes; absent is
  not.
- Keep the plan actionable and phased.
- Include enough detail that a future implementation pass can follow it without rediscovering the problem.
- **Include both positive and negative test cases, even for non-code work — and this is now GUARDED.**
  `test_plan_cases_are_traceable::test_every_plan_declares_BOTH_kinds_of_case` fails on a plan that
  declares one kind and not the other. The frozen exception list is historical and may only shrink;
  **adding a new plan to it is not the fix.**

  **Negatives are the half that goes missing, and the reason is structural.** A positive case is the
  thing you were already trying to do, so momentum writes it. A negative case is a guarantee the change
  makes to its callers — failure isolation, cancellation, a budget, an opt-out, a malformed input — and
  nobody discovers those by building the happy path. Measured 2026-09-19: **629 of 705 plans declare
  both; 76 do not**, and all but two are from before cases were numbered.
- Prefer concrete file paths, modules, commands, APIs, and acceptance checks when they can be inferred from the repository.
- The protected-code assessment is mandatory and appears in BOTH places: a `Protected-code touched:` line on every phase, and the rolled-up `## Protected-code impact (summary)` section — both checked against `docs/protected.md`, filled LAST after the plan is drafted, never omitted or left blank. The whole point is to scope re-testing: a plan that touches no protected area lets the reader skip re-testing those areas; a plan that touches one names exactly which phase, which flow, and which tests to re-verify.
- Protected code may be modified. Never defer a phase, pick a worse design, or narrow a requirement *because* a file is protected — flag it and follow the protocol instead. Equally, permission is not licence: where a non-protected path is genuinely better, keep it and say why, so the reader can distinguish a design choice from a dodge.
- Every protected-touching phase states HOW and WHY it touches the file, adds positive AND negative tests around the protected contract **before** the change, and names the regression gate: the area's existing covering tests pass unmodified.
- Never plan to edit an existing protected test's assertions to make a change pass. If a protected test would need editing, the plan flags it as an open regression question to escalate, not as a task.
- Do not claim implementation is complete.
- Do not create unrelated files.
