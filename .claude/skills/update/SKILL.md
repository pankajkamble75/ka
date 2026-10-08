---
name: update
description: Status of every plan belonging to one research report — created / implemented / verified / uploaded — checked against the tree rather than read off the tracker, followed by the next steps and any missing tracker rows written. Use when the user says "update", invokes /update with a research number, or asks "where is research-NN", "what is the status of research-NN", "which plans of research-NN are done", "what is left on research-NN", or asks for a status table for a report or a plan set.
---

# Update

One report in, one table out: **which plans exist, how far each one got, and what to do next.**

This is the question that gets asked most often between sessions — *"where did research-50 actually get
to?"* — and answering it from memory or from the tracker alone has already been wrong here more than once.
This skill answers it from the **tree**.

## What it is NOT

- **Not a status report written from the tracker.** The tracker is a claim. Every column below is checked
  against an artifact, and a disagreement is the headline, not a footnote.
- **Not `ship`.** It builds nothing, implements nothing, verifies nothing. It reports and it repairs the
  ledger.
- **Not a deferral mechanism.** It may add missing rows and correct wrong ones. It may **never** mark
  anything `DEFERRED`, `REJECTED` or `HALTED`, and never writes to `docs/trackers/PENDING-TRACKER.md`. Those are the
  user's decisions — see the Rules.

## 0. Resolve the target

- **`research-NN`** — the normal case.
- **`plan-NN`** — resolve to the report the plan's `## Research coverage` section cites, and say which one
  you resolved to before reporting.
- **Nothing** — take the newest `docs/research/research-*.md` and **say which you picked**.
- If the named report does not exist, say so and stop. Do not guess at a neighbouring number.

Read the report's `## Research points` ledger and take **N**, its total. That is the denominator for
everything below.

## 1. Find every plan that belongs to the report

Two directions, because either alone misses rows:

- **Forward** — `grep -l "research-NN" docs/implementation-plans/plan-*.md`. A plan cites its source in
  `## Research coverage`.
- **Backward** — the tracker's `From` column for `research-NN`, in **both** `## Active` and `## Closed`.

**A plan in one list and not the other is a finding.** A plan that cites the report but has no tracker row
is invisible to `ship`'s clean check; a tracker row naming a plan file that does not exist is a ledger
lying about work that was never written.

Also collect the **research points with no plan at all** — those are the pending rows §4 writes.

## 2. Establish each column from the tree, not the tracker

Four columns, four independent checks. Cheap on purpose: this skill runs often and must stay fast.

| Column | ✅ when | How to check |
|---|---|---|
| **Created** | the plan file exists | `docs/implementation-plans/plan-NN.md` is present and has `## Plan totals` |
| **Implemented** | its deliverables exist in the tree | `pytest knowledge_worker/tests/test_plan_cases_are_traceable.py -k "[NN]"` — this repo's own guard for *plan written, nothing built*. Green ⇒ its numbered cases have tests. Then spot-check two or three D-row symbols by grep |
| **Verified** | a live gate exists **and** ran | the plan's own flow under `e2e/` (or the browser flow it names), plus a `VERIFIED` note in the tracker. **Gate file present but never run is not verified** |
| **Uploaded** | it is on `origin/main` | a commit naming the plan, and `git branch -r --contains <sha>` includes `origin/main`; plus an entry in `docs/checkpoints/CHECKPOINTS.md` |

**`test_plan_cases_are_traceable[NN]` is the single most useful signal in this skill.** It is *designed* to
be red for a plan that has been written and not implemented, so a red there is an answer rather than a
problem — say "expected red: not implemented", never "failing".

**Where a column cannot be established cheaply, say `?` and say why.** A `?` reported honestly is worth
more than a ✅ inferred from a tracker row, which is the exact thing this skill exists to stop.

## 3. The table

Print it first. It is what the user asked for and everything else is commentary.

```
research-50 — 7 research points, 3 plans

| Plan     | Covers      | Created | Implemented | Verified | Uploaded | Where it stands |
|----------|-------------|:-------:|:-----------:|:--------:|:--------:|-----------------|
| plan-162 | R1,R2,R3,R7 |    ✅    |      ✅      |    ✅     |    ✅     | `f3d13a3b`      |
| plan-163 | R4,R5       |    ✅    |      ✅      |    ✅     |    ✅     | `99706a7c`      |
| plan-164 | R6          |    ✅    |      ✅      |    ✅     |    ✅     | `abab23e1`      |

Research points: 7 of 7 accounted for. Report COMPLETE.
```

Rules for the table:

- **One row per plan**, in numeric order.
- **The `Covers` column must reconcile to N.** State it under the table as `X of N accounted for`, and
  **lead with the gap** when X < N — naming the unaccounted points by number.
- **`Where it stands`** carries the SHA when uploaded, and otherwise the single most useful fact: *"halted
  — see the tracker note"*, *"written, never started"*, *"6 of 9 deliverables"*.
- **A partly-done plan gets ✅ only in the columns it earned.** Rounding up is how a later session builds
  on a hole.

## 4. Write the missing tracker rows

This is the skill's only write, and it is deliberately narrow.

- **One `OPEN` row per research point that no plan covers**, `From` = the report, `Plan` = `—`, and a Note
  saying it is unplanned. This is the "pending plans" half of the job: a point with no plan is the leak the
  whole numbered pipeline exists to catch.
- **One row per plan that exists and has no tracker row**, at the state §2 actually established — not at
  `PLANNED` because that is the tidy answer.
- **Correct any row whose state disagrees with the tree**, and **say so in the report**. A row quietly
  fixed is a tracker nobody can trust. The tree wins, always.

Then, without exception:

1. **Regenerate the `## Outstanding` block.** It is generated from its sources and has its own drift test:
   ```
   python -c "from tracking.tests.test_plan124_outstanding import render_outstanding as r; print(r())"
   ```
   splice it in place of the existing block. **Do not hand-edit it.** Every session that has edited the
   tracker and skipped this has left a red test behind.
2. **Run the tracker's own tests**: `pytest knowledge_worker/tests/ -k "tracker or outstanding"`. They
   catch what reading cannot — a terminal row left in `## Active` instead of moved to `## Closed`, and a
   generated block that disagrees with its sources.
3. **Commit the tracker change** with a message naming the report and what moved. Do not push unless the
   user asked; say the commit is local.

**A terminal row belongs in `## Closed`.** Editing its State cell in place leaves `## Active` unable to
answer *"what is open?"*, which is the only question it exists for.

**Never write Backlog rows.** `## Backlog` mirrors the user's own `pending.md` and no pipeline skill
touches it.

## 5. Next steps — the part that makes this worth running

Under the table, **three lines at most**, concrete and ordered:

1. **The single next action**, named precisely: which plan, which phase, and the command or skill that
   starts it. Not *"continue the migration"* — *"`/ship plan-167`: ten protected files under the seven-step
   protocol"*.
2. **Anything blocking it**, named now rather than discovered later — a plan that is not written, a
   protected area needing its `Verified:` date, a gate that cannot run in this environment.
3. **What the report needs to be finished**, in numbers: *"1 of 7 outstanding — R5's protected half."*

**Where the next step is a plan that does not exist yet, say that plainly**, because a plan file's absence
is invisible in a directory listing while its siblings sit there looking complete. That is the specific
confusion this skill exists to remove.

**Do not propose where unplanned points "should go."** Listing them is the job; deciding is the user's.

## Rules

- **The tree wins.** Over the tracker, over the checkpoints, over the handoff, over what a commit message
  claims. Report every disagreement you find.
- **Never fabricate a column.** `?` with a reason beats a guess. This skill's whole value is that its table
  can be trusted without re-deriving it.
- **Expected reds are labelled as expected.** `test_plan_cases_are_traceable[NN]` is red by design for an
  unimplemented plan; reporting it as a failure sends someone to fix what is working.
- **Add and correct rows; never DEFER, REJECT or HALT one, and never write `pending.md`.** Those say work
  will not happen, and only the user decides that. If work is outstanding, it stays `OPEN` and the report
  says so.
- **Regenerate `## Outstanding` and run the tracker tests** after any tracker edit. Not optional; it has
  been skipped and it has left red tests behind.
- **Build nothing.** If the next step is to implement, say so and stop. `implement`, `verify`, `upload` and
  `ship` do the work.
- **One table, then three lines.** A status answer nobody reads to the end has failed at the one thing it
  was for.
