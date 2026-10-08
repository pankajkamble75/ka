---
name: implement
description: Implement an existing implementation plan from docs/implementation-plans/plan-NN.md, phase by phase, following the protected-code protocol where the plan flags it. Use when the user says "implement", invokes /implement, says "implement plan-NN", or asks to build a plan that has already been written. It implements only — verification and upload are the separate verify and upload skills.
---

# Implement

Build what a plan says to build. The user runs this by saying **implement** (or `/implement`), usually with
a plan number.

This skill turns an approved plan into working code. It is deliberately narrow: it does **not** write the
plan (that is `create-implementation-plan`), does **not** run the closing verification gate (that is
`verify`), and does **not** push (that is `upload`, which `verify` runs as its last step).

## 0. Identify the plan

- Use the plan the user names (`plan-64`, "the snapshots plan", a path).
- With no argument, take the highest-numbered `docs/implementation-plans/plan-NN.md` with no matching
  implementation in the tree — and **say which one you picked** before starting.
- **Read the WHOLE plan first**: Problem, Research coverage, Scope, Protected-code impact, Assumptions,
  every Phase, Deliverables, both test case lists, Plan totals, and Implementation Notes. The test cases
  are requirements, not documentation.
- **Write down the plan's numbers before you start**: `m` deliverables (D1..Dm), `i` positive cases
  (P1..Pi), `j` negative cases (N1..Nj), from `## Plan totals`. Everything below is reported against them.
  If the plan has no such totals it predates this rule — count the items yourself and say so.
- If no plan exists for the work, stop and say so. Writing the plan yourself is a different skill, and the
  ordering matters — `plan-60` exists in this repo precisely to record a change made without one.
- **If this plan is one of a SET** (its Research coverage says `Covered here: X of N` and names sibling
  plans), say so up front — *"plan-85, the second of three from research-14"* — and **re-check it against
  the tree before building**. It was written before its predecessors landed; if anything it assumes has
  since changed, that is §4, not something to work around. Implement **this plan only**: the caller runs
  the others, each with its own verify and upload, so each lands as its own commit.

## 1. Work the phases in order

- Implement each phase as written: same design, same file targets, same names. The plan already made the
  design decisions; re-litigating them mid-build is how a plan and its code drift apart.
- Keep the plan's **Scope** honest. Something the plan lists as out-of-scope stays out, even when it looks
  like a one-line win while you are already in the file.
- Write code that reads like the code around it — match the surrounding comment density, naming, and idiom.
- After each phase, run the tests that phase affects. Do not save all testing for the end; a failure is
  cheapest to diagnose next to the change that caused it.
- **Run TARGETED suites while building, never the full one.** A full backend run is 20-25 minutes and it
  keeps **reading source for all of them** — this repository has many tests that read source deliberately
  (traceability and extraction audits, lint guards, boundary scanners, the ownership guard). Editing under
  one makes it read a half-written tree. Measured 2026-09-05: a run was launched, `goal_nav.py` was edited
  while it ran, and `test_plan525_extraction::test_C2` failed — it passed **16 of 16** in isolation.
  Nothing was wrong with the code, but 24 minutes produced no usable evidence, in the most expensive
  shape there is: a red result indistinguishable from a regression until someone chases it.
  **The full run belongs to `verify`, on a still tree.** If you want one here, commit first.

## 2. Protected code — the protocol is not optional

For any phase the plan flags against `docs/protected.md`, follow all seven steps **in order**:

1. **Declare** — name the exact files/functions and why no non-protected path achieves it (the plan should
   already say this; if it does not, that is a gap to raise, not to paper over).
2. **Characterize FIRST** — write tests pinning what the code does **today** at the exact seam, and run
   them against **unchanged** code. Two valid outcomes: they pass (documenting current behaviour) or they
   fail for exactly the reason the change will fix. Either way you must **run them before editing** and
   report what you saw. A characterization test you never ran against the old code proves nothing.
3. **Add positive AND negative coverage** around the protected contract, before the change.
4. **Land characterization as its OWN commit**, green against unchanged code, before the commit that makes
   the change. This is what lets a later reader tell the before-photo from the after-photo.
5. **Make the change.**
6. **The area's existing covering tests must pass UNMODIFIED.** If a protected test needs an assertion
   edited to go green, **stop and escalate** — that is a regression, not a test to update.
7. **Re-verify live** against a running backend, and **bump the area's `Verified:` date** in
   `docs/protected.md` in the same commit as the change, with an honest note of what was re-verified.

For a phase the plan flags as touching **no** protected code, confirm that by diff before you believe it —
then say so.

## 3. Tests belong to implementation, not to verification

Write the tests the plan lists as you build, not afterwards. `verify` exists to *close gaps*; handing it a
plan with no tests written makes it do this skill's job.

**Every numbered case gets a test.** The plan lists P1..Pi and N1..Nj; each maps to a real test that can
pass or fail, and you must be able to name which test covers which case. A case with no test is not
"covered by the suite generally" — it is missing, and saying so is the correct outcome.

- A behaviour change ships with a test verified to **fail first**.
- Negative cases matter most: invalid input, failure isolation, cancellation, budget/opt-out paths, and
  every guarantee the changed code makes to its callers.
- **Never weaken an assertion to get green.** If an existing test breaks, first work out whether the code
  or the test is wrong. A test double that no longer mirrors a module's surface is a legitimate fix (adding
  a missing mock export changes no assertion); an assertion edited to match new behaviour on protected code
  is an escalation.

## 3b. WRITE THE CODE BLOCKS the plan declared — `plan-720`, the author, 2026-09-19

*"create implementation writes the code. Every code which is written should be marked with blocks."*

For each row of the plan's `## Code blocks` table, wrap the code you write in that file with a matched
pair naming this plan:

```python
# [block plan-NN]
...the coherent change this plan makes to this file...
# [/block plan-NN]
```

`//` for `.ts`/`.tsx`. The grammar and its three rules — matched pairs, matching ids, no nesting — are
in `knowledge_worker/tests/_codeblocks.py`'s docstring, and `test_plan718_code_blocks.py` enforces them.

**ONE BLOCK PER PLAN PER FILE.** Never per function.

**TEST FILES ARE NOT MARKED.** A test's owner is already derived from its filename (`Q190`'s
`owner_of`), so marking it again is the duplication that ruling rejected — and
`test_plan718_code_blocks.py` treats a sentinel under a `tests/` directory as an error.

**A sentinel inside a docstring or string literal is TEXT, not a block.** The scanner skips string
spans; it learned that by matching its own documentation on the day it was written.

**If the build touches a file the plan did NOT declare, that is a FINDING — report it (§6), do not add
a block silently.** The mismatch is the signal that the plan's scope moved during the build, which is
exactly what a reader of the plan needs to know.

> **And the lesson this set was built on:** when a guard rejects your new file, **MOVE THE FILE — do
> not widen the guard.** `Q190` cost a run to learn it twice, and `plan-718` met it a third time. The
> tempting fix is always to bump a census or add to an allowlist; a third home existed every time.

## 4. When the plan turns out to be wrong

Plans are written before the code is read in full, so some are wrong in places. When a phase rests on
something the code contradicts:

- **Stop at that phase.** Do not improvise a different design silently — the plan is the agreed artifact,
  and a build that quietly diverges from it leaves no trace of the decision.
- Report what the plan assumed, what the code actually does (with `path:line`), and the options.
- Small, obviously-correct corrections (a renamed helper, a moved import) are fine to make and mention.
  A changed design, a changed contract, or a changed scope is not.

## 4b. A question that arises DURING the build is WRITTEN DOWN, not carried in your head

**Ruled by the author 2026-09-13**, and it is the rule most often skipped: *"if during the course of coding
or implementation new questions come up, we should put the new question in that same relevant section."*

**Implementation is where the sharpest architectural questions appear** — the plan is specific enough that
the gaps in it become visible, and this is the moment they are cheapest to see. They used to land in a plan
document nobody reads again, or in a commit message, or nowhere.

When the build raises a question the author has to answer:

1. **Write it into `docs/questions/<topic>.md`** — the section it belongs to, **beside the answers it
   relates to**, under that section's `❓ Open` block. Use
   `docs/architecture/architecture-index-lookup.md` to find which topic it belongs to; if none does, say so
   and name the section it would create.
2. **Register it in `docs/trackers/QUESTIONS-TRACKER.md`** in the `questions` entry format, so `/questions` will
   actually ask it. A question written only into a topic document is one nobody surfaces.
3. **Keep building everything that does not depend on it.** A parked question does not stop the phase — it
   stops the part that needs the answer, which is named in the report.

**Do NOT answer it yourself and carry on.** That is the difference between this and §4: a plan detail you
can settle from the code is yours to settle; a question about **what the product should do** is the
author's, and guessing it produces architecture nobody agreed to.

**What it must NOT be recorded as.** Not a `TODO` in the source, not a line in the commit message, not a
note in the plan document. Those are all places the next reader does not look. The loop is
[`docs/questions/how-a-question-becomes-architecture.md`](../../../docs/questions/how-a-question-becomes-architecture.md).

## 5. Committing

- **Characterization commits are made here** — protected work requires that separation (§2.4).
- **Leave the main change in the working tree.** `verify` runs `upload` as its final step, and `upload`
  writes the checkpoint note describing everything that landed. Committing the change here too would split
  one piece of work across two checkpoints for no gain.
- Never push from this skill.

## 6. Report

Short and factual:

- **Which plan**, and which phases are DONE vs deliberately not started.
- **The coverage ledger — REQUIRED, and it must reconcile.** Three lines, with the plan's numbers on the
  left and yours on the right:

  ```
  Deliverables:    m of m built        (any not built: D4 — why)
  Positive cases:  i of i tested       (name the test for each, or which are missing)
  Negative cases:  j of j tested       (same)
  ```

  **The counts must match the plan's `## Plan totals`.** If they do not, that is the report's headline, not
  a footnote — say which items are short and why. A plan that promised 9 deliverables and got 7 is a
  partial implementation honestly reported; the same thing reported as "done" is a defect.
  **Never inflate a count by mapping two cases to one test** — if one test genuinely covers P3 and P4, say
  so explicitly rather than counting it twice.
- **What was built** — the concrete files and what changed in each.
- **Test results** — real suite names and counts, for what you ran. Never claim green without running.
- **Protected code** — areas touched, the characterization commit SHA, whether existing covering tests
  passed unmodified, whether the `Verified:` date was bumped. Or "none touched", confirmed by diff.
- **Deviations from the plan** — anything you did differently, and why. Silence here when there were
  deviations is the failure mode this section exists to prevent.
- **What is left for `verify`** — known gaps, untested paths, anything deferred.

## Rules

- **A question the build raises about what the PRODUCT should do goes into `docs/questions/` and the
  registry, in the same pass** (§4b) — never into a `TODO`, a commit message, or your own head.

- **The plan is the specification.** Follow it; do not expand it, narrow it, or redesign it mid-build.
- **Build every deliverable and test every numbered case**, or report the shortfall by number. Partial is
  acceptable; unreported partial is not.
- **Protected code follows the seven steps**, and characterization lands in its own commit.
- **Never fabricate a result** — not a test count, not a live check.
- **Never weaken a protected test.** Escalate instead.
- **Do not verify or upload from here.** Those are `verify` and `upload`; running them here would duplicate
  a gate whose whole value is being independent of the build.
- **Update the tracker** (`docs/trackers/RESEARCH-TRACKER.md`): this plan's row → `IMPLEMENTED`, with the reconciled
  ledger in the Note (`7/7 deliverables, 20/20 cases`). Write it when the build finishes, not at the end of
  the session — a run that dies mid-plan should still show how far it got. Record what is TRUE, not what
  was planned: if the ledger is short, the row says so.
