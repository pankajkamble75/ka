---
name: bye
description: End a working session cleanly — reconcile the tracker at docs/trackers/RESEARCH-TRACKER.md, write the handoff at docs/trackers/HANDOFF.md from verified evidence, commit everything, push to main, and confirm it is safe to walk away. Use whenever the user says "bye", invokes /bye, or signals the session is ending — "that's it for today", "wrapping up", "I'm done", "signing off", "end of session", "write the handoff", "closing the laptop", or when they say they are moving to another machine.
---

# Bye

Close a session so the next one — on another machine, or weeks later, with no context — can pick it up.

The output is `docs/trackers/HANDOFF.md`, and it is the **same document `/startup` reads**. These two skills
are a pair: this one makes the claims, that one checks them. Write nothing here you would not want checked.

## The contract with `/startup`

`/startup` verifies exactly four things before it trusts the handoff. **Get those four right, from
evidence, or the next session starts by discovering you were wrong:**

| The claim | Get it from |
|---|---|
| the commit the tree is at | `git log --oneline -1` |
| the tree is clean and pushed | `git status -sb` — after the push, not before |
| what is next, and whether it has started | `docs/trackers/RESEARCH-TRACKER.md` §Active + whether the implementation exists |
| the test state | **run the suite.** Do not quote a number from memory or from earlier in the session |

## The handoff summarises the tracker — it does not replace it

Two documents, two jobs, and getting them the wrong way round is the most common way a handoff misleads:

```
the TRACKER   docs/trackers/RESEARCH-TRACKER.md   the authoritative LEDGER — every open row, its state, its plan
the HANDOFF   docs/trackers/HANDOFF.md   a NARRATIVE — what was being done, and what to do next
```

**The handoff's state table is DERIVED from the tracker, never written from memory.** If they disagree, the
handoff is the one that is wrong — and `/startup` will find that out, because it reads both.

**Leave the tracker correct before writing the handoff.** A session that implemented a plan and never moved
its row has left the ledger lying, and no amount of good prose in the handoff fixes it. See the `tracker`
skill for the state transitions.

## 1. Gather the evidence — before writing a word

- `git status --short` and `git log --oneline -10`.
- **`docs/trackers/RESEARCH-TRACKER.md` §Active** — every non-terminal row, its state, its plan. This is the state
  table; the handoff narrates it.
  - **Does it match what actually happened this session?** A plan implemented but still `PLANNED`, or a row
    still `OPEN` for work that shipped, gets corrected **now**. Where the tracker and the tree disagree,
    the tree wins — fix the row and say so in the handoff rather than fixing it silently.
  - **Run the tracker's own tests**: `pytest knowledge_worker/tests/ -k "tracker or outstanding"`. They
    catch what reading cannot — a terminal row left in `## Active` instead of moved to `## Closed`, or a
    generated `## Outstanding` block that disagrees with its sources. Both have happened here.
- **Run the tests.** The cheapest suites that cover what changed. A long suite belongs in the background;
  wait for it rather than guessing, because this number is the one the next session trusts most.
- If anything is red, find out whether it is *expected* red — this repo has cases that are correctly red,
  such as `test_plan_cases_are_traceable[NN]` for a plan written and not implemented. **An expected red
  reported as a failure sends someone to fix what is working.**

## 2. Write the handoff

Replace the file. It is a *resume-here*, not a log — a growing history is a document nobody reads to the
end. Whatever from the previous handoff is still true gets re-stated; what is stale goes.

Structure, in this order, because it is the order someone needs it:

1. **Dateline + the commit** — `Tree is clean and pushed; main matches origin/main at <sha>.`
2. **The one-paragraph version** — what the work is, where it got to, and **the next action in one
   sentence**. Someone should be able to stop reading here and know what to do.
3. **Where the work stands** — a small state table, plus the session's commits with one line each.

   **3a. THE STATE OF EVERY TRACKER — paste `/show` here, verbatim** (the author, 2026-09-19).

   ```
   /root/.venvs/enterprise-os/bin/python -c "
   from tracking.tests.test_status_table import render_status
   print(render_status())"
   ```

   **This is the section the author asked for by name**, and the reason is specific: *"i do a bye
   sometimes which updates the handoff and i clear the cache."* After a `/bye` the next session starts
   with **no memory of this one** — the handoff is the only carrier. A handoff describing the work in
   flight but not the state of the five trackers hands the next session a story with no ledger behind
   it, and `/startup` then has to re-derive what `/show` already renders in under a second.

   **Paste it; do not summarise it.** Four tables, all derived, with their own guards. A hand-written
   count in a handoff is wrong by the next commit and cannot be checked against anything.
4. **What exists now that did not** — the shape of what was built, not a changelog.
5. **The things that will bite you.** *This is the most valuable section and it is the one that gets
   skipped.* Every trap that cost real time: the guard that fired for a surprising reason, the tool that
   reported success without persisting, the test that is red on purpose. Say what happened and what to do
   instead. A gotcha you had to learn twice belongs here in full.
6. **Environment** — anything the next machine may differ on: missing runtimes, suite durations, whether a
   gate can run at all.
7. **Reading order** — the two or three files to open, in sequence, and what each answers.
8. **Decisions and open questions** — **the section that carries the architecture across the session
   boundary**, and it says `none` or it is filled, never absent:
   - **decided but NOT built** — every section in `docs/architecture/` this session left at
     `⏳ DECIDED, not built`, with the document and section. **This is the most valuable line in the
     handoff after the next action**, because it is work that is fully agreed and fully unstarted, and
     nothing else in the repo says so;
   - **answered this session** — the questions the author settled, and the document each now lives in.
     If any answer is not in its architecture document yet, **put it there before writing the handoff**;
   - **raised and still open** — questions the work turned up, with their registry ids, so `/questions`
     will actually ask them;
   - **divergences** — anywhere the tree and a decided question disagree, per `verify` §5b or
     `vps-download` §6b. A divergence that survives a session boundary unnamed is one nobody will find.

   Find the documents through `docs/architecture/architecture-index-lookup.md`.

**Write it for someone with no context.** Not "continue the refactor" — name the plan, the file, and the
question it is trying to answer. Assume they have never seen this repository.

**Be honest about partial work.** A plan at 6 of 9 deliverables is *6 of 9*, with the three named. Rounding
up is how a later session believes something is done and builds on a hole.

## 3. Commit and push

```bash
git add -A
git commit -F - <<'EOF'
handoff: <what state this leaves the work in>
...
EOF
git push origin main
```

- Commit **everything** — the handoff and any work still in the tree. Leaving a change behind on a laptop
  the user is about to close is the one failure this skill exists to prevent.
- Then **verify the push landed**: `git status -sb` shows no divergence, and `git log --oneline -1` matches.
  A push that failed silently leaves the next session on a machine with nothing to pull.
- **If the handoff claimed the tree is clean and pushed, that claim must be true after this step** — if the
  push is rejected or the tree is still dirty, fix the handoff before finishing, not after.
- Reach for the `upload` skill instead when the session's work warrants a full dated checkpoint note under
  `docs/checkpoints/`; say which you did.

## 4. Say it is safe to stop

Close with the state in one or two lines — the commit, the test result, and the next action — and then, only
once the push is verified:

> **Safe to close the laptop.**

Do not say that if anything is unpushed, unrun, or unresolved. Say what is outstanding instead.

## Rules

- **The handoff names the DECISIONS, not only the work.** A section left `⏳ decided, not built`, a
  question answered, a question raised, a divergence found — each crosses the session boundary or is lost.
  The loop is
  [`docs/questions/how-a-question-becomes-architecture.md`](../../../docs/questions/how-a-question-becomes-architecture.md).

- **Evidence, not memory.** Every number in the handoff comes from a command run in this session, now.
  Quoting a test count from earlier is how a handoff becomes wrong the moment it is written.
- **Leave the tracker correct, then summarise it.** The ledger is the state; the handoff narrates it. A row
  that still says `PLANNED` for work that shipped makes the ledger lie, and good prose does not fix it —
  `/startup` reads both and will find the disagreement.
- **Never fabricate a test result** to make the closing tidy. "Suite not run" is a legitimate handoff line;
  an invented green is not.
- **Expected reds are labelled as expected**, with the reason. Otherwise the next session fixes what is
  working.
- **Replace the handoff, do not append.** One resume-here, always current.
- **Push before declaring it safe to stop**, and verify the push.
- **The gotchas section is the point.** State, commits and tests can be re-derived from the repository; what
  cost you an hour cannot.
