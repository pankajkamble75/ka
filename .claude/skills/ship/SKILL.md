---
name: ship
description: Run the full delivery chain unattended — research the user's note, write the implementation plan, implement it, verify it, and upload. Use when the user says "ship", invokes /ship, or asks to run the whole pipeline / research-to-upload / end-to-end without stopping. For a single stage, call that stage's own skill instead (create-research-report, create-implementation-plan, implement, verify, upload) — this skill exists only to chain them.
---

# Ship

Run the whole delivery chain in one go, **unattended**: research → plan → implement → verify → upload.

The user runs this by saying **ship** (or `/ship`). Every stage remains independently runnable by its own
skill — this one only chains them. Reach for it when the work is well understood and the user wants it
carried through without being asked questions along the way.

## SET MODE — "ship research-NN": one plan after another until the set is terminal

When the user names a RESEARCH rather than a note ("ship research-94", "ship the set", "keep shipping
until it's done"), run the chain as a LOOP over that research's ledger:

1. **Render the set table** (`render_set_status(NN)` — `knowledge_worker/tests/test_set_status_table.py`).
   It is the loop's own termination condition: every row terminal → the set is shipped, stop and report.
2. **Pick the next row** in dependency order: an OPEN row whose plan exists → implement it; an OPEN row
   with no plan → `create-implementation-plan` first (respect the research's own sequencing notes —
   "lands first", "precondition", "deferred until"). Never pick a row whose named precondition row is
   not yet terminal.
3. **Run the ordinary chain for that one plan** — implement → verify → upload (upload renders the table
   again; that render is the loop's progress report, shown after EVERY plan, per the author's rule).
4. **Loop.**

One plan per iteration, one commit rhythm per plan, the full suite green before each push — set mode
changes the DRIVING, never the per-plan discipline.

**Halt — do not route around — on any of these:**
- a `decide` row that genuinely needs the author (park it, SKIP its dependents, continue independent rows;
  if nothing independent remains, stop and report what is parked);
- a paid gate beyond the stated per-plan figure, or cumulative live spend beyond what the user authorized
  for the set — state figures before every paid run, exactly as the plan skills already demand;
- a suite that stays red after an honest fix attempt, a protected-code surprise, or a plan whose
  re-check-against-the-tree finds a stale premise;
- any situation the per-stage skills themselves define as a halt.

Parked decisions do not stop the loop when independent rows remain — the author's standing instruction
shape is "park it and complete as much as possible in parallel."

**Parking is REGISTERING — in BOTH places.** A parked decision is written to:

- **`docs/trackers/QUESTIONS-TRACKER.md`**, in the entry format the `questions` skill defines (scenario in plain
  language, the decision required, the big picture per direction, options with a recommendation, the
  cost) — **at the moment it is parked**, not at the end of the run. That registry is how the author
  later answers everything in one sitting (`/questions` walks it one question at a time);
- **`docs/questions/<topic>.md`**, in that topic's `❓ Open` block, beside the answers it relates to —
  found through `docs/architecture/architecture-index-lookup.md`. The registry says *a decision is
  waiting*; the topic document says *what it sits beside and what depends on it*, which is what makes
  the question answerable when it is finally asked.

A decision parked only in a chat message or a checkpoint note is a decision lost.

**And the architecture is INPUT to a ship run, not only output.** Before writing a plan, read the
lookup and follow it to the documents the work touches: a decided question is a **constraint** the plan
executes and cites, not a design choice to re-make. An `❓ open` question the plan would need answered
is a halt, not a guess. The loop is
[`docs/questions/how-a-question-becomes-architecture.md`](../../../docs/questions/how-a-question-becomes-architecture.md).

## The final report includes the set's standing

The last stage's upload already renders the DERIVED set-status table (see the `upload` skill, step 6 —
`render_set_status` in `knowledge_worker/tests/test_set_status_table.py`). Ship's final report repeats
that table so the reader sees, in one place, what the whole research now looks like after this chain's
plan landed — and whether sibling plans remain before the set closes.

## The chain

```
the user's research note (docs/research/<their-note>.md)
   │
   ▼  create-research-report     → docs/research/research-NN.md   (verdict: aligned / corrections / not aligned)
   ▼  create-implementation-plan → docs/implementation-plans/plan-NN.md
   ▼  implement                  (builds the plan; protected code: characterize FIRST, in its own commit)
   ▼  verify                     (closes gaps, runs the suites, ends by running upload)
   └─ upload is verify's LAST STEP — do not run it twice
```

Four skills, one chain. Every stage is a real skill invoked by name — there is no step this skill performs
inline.

Invoke each stage through the **Skill tool**, by name, in this order. Do not re-implement a stage inline:
the stage skills carry rules this one must not duplicate or drift from.

## Unattended means no questions, not no judgement

Unattended removes the *approval* stops, not the *safety* stops. Never use `AskUserQuestion` during a ship
run. Where a stage would normally ask, **make the reasonable choice, state it, and carry on** — then list
every such choice in the final report under "Assumptions I made".

But a chain that cannot ask is a chain that must be willing to stop. **Halt immediately and report** on any
of these — do not route around them, and do not proceed to a later stage:

1. **No research note to work from.** `create-research-report` reads the user's note; it may not be
   invented. If the argument names no file and no plausible note exists, stop and ask for one.
2. **The research verdict is "Not aligned."** This is the one place unattended must defer. The report is
   saying the user's direction is wrong and proposing a different one — implementing that alternative
   without a word would deliver code the user never asked for. Stop, present the verdict and the proposed
   alternative, and let them choose. ("Aligned" and "Aligned with corrections" both continue: corrections
   sharpen the direction rather than replace it.)
3. **A protected test would need its assertions edited** to go green. That is a regression to escalate, per
   `docs/protected.md` — never an edit to make.
4. **Tests are red and the cause is not fixable** within the plan's scope, or the failure is a genuine
   regression rather than a pre-existing one.
5. **A destructive or outward-facing action beyond the plan's scope** would be required — deleting data,
   force-pushing, removing a remote branch, hitting a paid external API in a loop.
6. **The plan turns out to be wrong** once implementation starts (a phase rests on something the code
   contradicts). Stop with what you learned rather than improvising a different design silently.
7. **A required gate cannot run in this environment.** The case that produced `plan-65`: `verify` §5 needs
   a live Chromium click-through, and on a machine with no Playwright — or for a plan with no flow
   exercising it — there is nothing to run. Unattended you cannot install a browser runtime on someone's
   machine, and you must not substitute an unrelated flow's green table for evidence about this plan. Halt,
   name the missing prereq and the exact command (`python -m playwright install chromium`), and say which
   gate is blocked. See `verify` §5, which distinguishes "no flow for this plan" (write one) from "no
   runnable environment" (halt). **A gate that did not execute has not passed** — never let this one slide
   through to the upload.

On a halt: say which stage stopped it, why, what artifacts already exist, and what the options are. A
partial chain honestly reported is a success; a chain that pushed past a stop sign is not.

## Stage rules

**1. Research.** Resolve the user's note from the argument (a path, a name, or "the newest note under
`docs/research/`") and **say which file you picked** before starting. Then invoke `create-research-report`.
Read the verdict it returns — that is the gate in §2 above. Also read its **`Research points: N`** total:
that is the number every later stage reconciles against.

**SAY THE SCOPE UP FRONT, AND OPEN THE TRACKER ROWS.** As soon as N is known, do two things before building
anything:

1. **Write one `OPEN` tracker row per research point** (§6). That is the run's worklist, and it exists from
   here on whether or not the run completes.

   **Every row a run opens MID-FLIGHT must also answer: which product test would have caught this?**
   Ruled by the author 2026-09-08 (`Q64`). Put the answer in the row's note as a marked clause —
   `**Product-test check:** <the test that would have caught it>` — or, when none would,
   `**Product-test check:** none — <why>`. A stated *none* is a real answer and is often the right one;
   silence is not. `test_product_test_lifecycle_plan568` enforces this on rows dated from 2026-09-09.

   **Why it is worth the friction.** research-164's own ledger says 7 research points while its tracker
   carries 12 rows: R8-R12 were opened mid-run **by running its four product tests**, and nothing carried
   them back into the report's product-test section — so two delivered capabilities ended up with nothing
   that could fail if they broke. **A defect found by running a product test is the strongest evidence
   available that a DIFFERENT product test is missing**, and this is where that evidence gets captured
   instead of lost.
2. **State the shape of the whole delivery** — how many plans the N points imply and the order:

> *research-11 has 4 research points → 3 plans. plan-84 covers R1+R2 (same module), plan-85 covers R3,
> plan-86 covers R4. All three are this run's target; the report is not shipped until all four rows read
> `UPLOADED`.*

**The target is the whole report, not the first plan.** A user who says "ship this research report"
reasonably expects the report delivered; the run works the set (§3-5) and reports `NOT COMPLETE` if it
cannot finish, rather than covering a subset and calling it done. Burying the scope in a line halfway
through a long report is how a chain that behaved correctly still leaves someone surprised — and it has
happened.

**2. Plan.** Invoke `create-implementation-plan`, passing the problem statement **as the research report
established it**, not as the original note framed it. Where the research corrected the note, the plan
follows the research. The plan must be written **before** any code is touched — that ordering is the whole
point of having a plan, and skipping it is the specific mistake `plan-60` exists to record.

Pass the research report's ledger through: the plan must carry a `## Research coverage` row for **every**
R1..Rn, and end with `## Plan totals` (`X of N` points, `m` deliverables, `i`+`j` test cases). Check those
sections exist before moving on — the later stages have nothing to reconcile without them.

**3-5. Build the set, ONE PLAN AT A TIME, all the way through.**

**`ship research-NN` means SHIP EVERY PLAN OF research-NN, one after the other.** One research report with
many implementation plans is the ordinary case, not a variant — the skill was first written when a report
meant a plan, and that assumption is gone. A run that stops after the first plan has not shipped the report.

When the report needs several plans, this is a **loop, not a single pass**. For each plan in order:

```
for each plan in the set:
    write(plan) if it does not exist yet     ← create-implementation-plan
    implement(plan) → verify(plan) → upload  ← one checkpoint per plan
```

**Write each plan JUST BEFORE you implement it, not all of them up front.** Stage 2 announces the *shape*
of the set — how many plans, which points each covers, in what order — and that announcement is binding.
It does not require the documents to exist yet. `create-implementation-plan` is explicit about why: *"a plan
written three deep, before its predecessors are built, is more likely to be wrong"*, and every plan after
the first carries a re-check instruction for exactly that reason. Writing plan-254 before plan-248 has
landed produces a document that must be rewritten anyway.

So the loop writes, builds, verifies and uploads one plan at a time, and the next plan is written against a
tree that already contains its predecessors.

**Every plan in the set gets all four.** A run that implements three plans and uploads once has produced
one unrevertable commit spanning three unrelated changes; a run that implements one and stops has silently
dropped two. Neither is acceptable — and the second is the failure that prompted this rule.

**A plan that needs correcting mid-set is CORRECTED AND CONTINUED, not halted.** This is the distinction
that matters most in a long set, and getting it wrong stalls a run that should have kept going:

| what happened | what to do |
|---|---|
| characterization measured something the plan guessed wrong, and the plan's *answer* changes shape | **rewrite the affected phases, say so, and carry on** |
| a later phase needs a case the plan did not list | **add it, renumber the totals, carry on** |
| the plan's *premise* is contradicted — the thing it exists to change does not work the way it says | **halt** (§2.6) |
| the work would need a destructive or outward-facing action the plan never scoped | **halt** (§2.5) |

Only the last two are stops. A plan being *wrong in a detail it could not have known* is the normal cost of
planning ahead — it is why `create-implementation-plan` requires the re-check — and the correct response is
to fix the plan, record what moved it, and continue the loop. Halting there converts an ordinary correction
into an abandoned run.

- **3. Implement.** Invoke `implement` with the plan number. That skill owns the build: phases in order,
  the seven-step protected-code protocol where the plan flags it, characterization landing in its own
  commit, and the plan's test cases written as it goes. Do not re-specify those rules here or perform the
  build inline — `implement` carries them, and duplicating them is how the two drift apart.

  **Before implementing any plan after the first, re-check it against the tree.** If it was written before
  its predecessors landed and something it assumes has changed, **rewrite the affected phases and continue**
  — see the correction table above. Escalate to §2.6 only when the plan's *premise* is contradicted, not
  when a detail moved. Writing each plan immediately before implementing it makes this rare by construction.

  Watch the returned report for **a "the plan turned out to be wrong" stop** (`implement` §4): surface it
  and halt rather than improvising a design the plan never agreed.

- **4. Verify.** Invoke `verify` with the plan number. It completes pending plan items, writes missing
  negative tests, fixes failures, checks the protected protocol, runs the live gate, and **runs `upload` as
  its final step**.

- **5. Upload.** Already done by `verify` — **once per plan**, so each lands as its own commit and
  checkpoint. Only invoke `upload` separately if `verify` halted before reaching it and the work still
  needs to land — say so if you do.

**On a halt mid-set:** stop the loop. Report which plans are shipped, which is halted and why, and which
are **written but not started** — a plan file that exists with no implementation is easy to mistake for
done. Do not skip a halted plan to continue with the next one; the order was chosen for a reason.

**6. The REPORT is the unit of completion, and the tracker is how that is proved.**

A research report is shipped when **every one of its research points has been built and landed** — not when
one plan from it has. The chain's target is a report whose every row is `UPLOADED`.

**The tracker is created at stage 1 and worked down from there.** As soon as `create-research-report`
returns `N`, there is **one `OPEN` row per research point**; as plans are written those rows gain their plan
number and move `PLANNED → IMPLEMENTED → VERIFIED → UPLOADED`. The tracker is not a report written at the
end — it is the run's worklist, and the run is over when the list is empty.

```
research-NN has N points
   → N OPEN rows                          (stage 1)
   → each row gains a plan number         (stage 2)
   → each plan: implement → verify → upload, and its rows go UPLOADED   (stages 3-5)
   → DONE when every row is UPLOADED
```

**What counts as DONE:**

| row state | counts as done? |
|---|---|
| `UPLOADED` | **yes** — the only ordinary way a point completes |
| `REJECTED` | **yes**, when a plan states the reason on the merits |
| `DEFERRED` | **only when the USER deferred it** — see below |
| `OPEN`, `PLANNED`, `IMPLEMENTED`, `VERIFIED`, `HALTED` | **no** — the run is not finished |

**DEFERRAL IS THE USER'S DECISION, NEVER THE RUN'S.** A ship run may not defer its own leftovers to make
the tracker look clean, and may not move them to `docs/trackers/PENDING-TRACKER.md`. `pending.md` is reached **only**
by an explicit user decision to park something. If work remains and the run cannot continue, the correct
outcome is **`NOT COMPLETE`, reported with what is left and why** — an honest partial delivery, which the
user may then choose to defer. A run that parks its own remainder has converted unfinished work into the
appearance of finished work, which is the exact failure this section exists to prevent.

**Keep going until DONE or a stop condition.** When stage 2 produces several plans, the run works the whole
set (§3-5), not the first plan. Stopping after one plan with the rest still `OPEN` is `NOT COMPLETE`, and
must be reported as such rather than as a successful run that "covered R1 and R2".

**Cross-check before believing any of it.** The tracker is written by the same agent doing the work, so a
row claiming `UPLOADED` proves only that something wrote the word:

- confirm each SHA exists (`git cat-file -e <sha>`), and that a `PLANNED` row has a real plan file;
- **run the tracker's own tests** — `pytest knowledge_worker/tests/ -k "tracker or outstanding"`. They
  enforce invariants prose cannot: that terminal rows have **moved to `## Closed`** rather than just having
  their State cell edited, and that the generated `## Outstanding` block agrees with its sources. A row
  edited in place leaves `## Active` unable to answer *"what is open?"*, which is the only question it
  exists for;
- **where the tracker and the tree disagree, the tree wins** — correct the row and say so in the report. A
  row corrected in silence is a tracker nobody can trust.

Report it as a line, alongside the other ledgers:

```
Tracker: research-14 — 5 rows: 4 UPLOADED, 1 REJECTED (reason in plan-84). DONE.
Tracker: research-48 — 12 rows: 5 UPLOADED, 7 OPEN. NOT COMPLETE — R6..R12 need plans.
```

A run that ends `NOT COMPLETE` is a partial delivery honestly reported, and is fine. A run that ends not
complete and says nothing — or that reaches "clean" by deferring what it did not finish — is not.

## Entry points

The argument decides where the chain starts, so a re-run does not redo finished work:

- **`research-NN`** → **ship every plan of that report, one after the other**, per §3-5's loop. Rows already
  on the tracker are the worklist; plans that do not exist yet are written as the loop reaches them. This is
  the ordinary case for a report with more than one plan, and it needs no confirmation — the user asking to
  ship a report IS the authorisation to ship all of it;
- **a research-note path or name** → start at stage 1 (the normal case);
- **`plan-NN`** → the plan exists; start at stage 3 by invoking `implement` (which is also runnable on its
  own as `/implement plan-NN` when you do not want verify+upload to follow);
- **nothing** → resolve the newest note under `docs/research/` that has no corresponding research report
  yet, name it, and start at stage 1. If that is ambiguous, ask — this is the §2.1 stop.

## Report

One report at the end, not a running commentary per stage:

- **The ledger, first.** The numbers as they passed between stages, so the reader can check the arithmetic
  in one glance:

  ```
  Research points   N total   →  N accounted for across the set
  plan-84   R1,R2   7 deliverables   18 cases   SHIPPED  <sha>
  plan-85   R3      4 deliverables   12 cases   SHIPPED  <sha>
  plan-86   R4      3 deliverables    9 cases   HALTED — <why>
  R5                                            rejected — reason in plan-84
  ```

  One row per plan, with its own SHA — there is one commit per plan, so there is one SHA per plan. If any
  column does not reconcile, or any point is unaccounted for, that is the first line of the report, not a
  footnote.
- **DONE or NOT COMPLETE**, as the first word after the ledger. `DONE` means every research point reads
  `UPLOADED` or `REJECTED`. Anything else is `NOT COMPLETE`, and the reason belongs on the same line.
- **What shipped** — one sentence.
- **What this run did NOT cover, by number** — the research points still outstanding, each still `OPEN` on
  the tracker and each named here. **Do not propose where they "go"** — they stay on the worklist until they
  are built or the user defers them. A ship report that lists only what was built lets the remainder
  disappear.
- **Artifacts** — links to the research report, the plan, and the commits (characterization commit + change
  commit), plus the pushed SHA on `origin/main`.
- **Verdict** the research reached, and whether the plan followed it or the user's original framing.
- **Test results** — real suite names and counts, backend and frontend. Never claim green without running.
- **The PRODUCT-TEST summary** — every product test the research defines, the point it serves, and
  PASS / FAIL / NOT RUN. It is per RESEARCH, not per plan, so it belongs in the closing report even
  when the run shipped one plan. **A research set with a red product test is NOT delivered**, however
  many rows read `UPLOADED` — say so on the same line as the verdict.
- **Protected code** — areas touched, protocol satisfied, `Verified:` dates bumped. Or "none touched".
- **Assumptions I made** — every choice taken in place of a question. This is the price of unattended mode;
  it must be paid in full, not summarised away.
- **Anything left open** — known gaps and follow-ups, plus anything the **user** has deferred. Work this run
  simply did not reach is not "left open" here; it is `NOT COMPLETE` above, still `OPEN` on the tracker.

## Rules

- **Chain, don't reimplement.** Every stage runs through its own skill via the Skill tool. If a stage skill
  changes, this one inherits the change automatically — that only holds if it is genuinely delegating.
- **Never `AskUserQuestion` during a ship run.** Choose, state, and record instead. The stop conditions in
  §2 are for halting, not for asking a question mid-flight and waiting.
- **Never fabricate a result.** Not a test count, not a screenshot, not a verification. A red result
  reported honestly is the correct outcome.
- **State the scope before building, in numbers, and open the tracker rows there.** "N research points, N
  rows opened, X plans" belongs at the start of the run, not in the closing report.
- **The report is the unit of completion, and a green ledger is not the same as a working capability.**
  A run is DONE when every research point reads `UPLOADED` (or
  `REJECTED` with a reason on the merits). One plan shipped out of three is `NOT COMPLETE`.
- **`ship research-NN` ships EVERY plan of research-NN.** One report, many plans is the ordinary case. Write
  each plan just before implementing it, then implement → verify → upload it, then move to the next. Do not
  ask between plans; the request to ship the report authorised the whole set.
- **Correct a plan mid-set; do not halt over it.** A measurement that contradicts a detail the plan guessed
  is ordinary — rewrite the affected phases, say what moved, continue. Halt only when the plan's premise is
  contradicted or a destructive/outward-facing action would be needed.
- **NEVER defer your own leftovers, and never write them to `pending.md`.** Deferral is the user's decision.
  Unfinished work is reported as unfinished — `NOT COMPLETE`, with what remains and why. Manufacturing a
  clean tracker by parking the remainder is the failure §6 exists to prevent.
- **Carry the ledger forward.** Each stage's totals are the next stage's contract; a stage that cannot
  reconcile says so rather than passing the gap on.
- **The tracker is the run's exit criterion, and it is a claim, not evidence.** Check it before reporting
  success; cross-check it against the tree, and **run the tracker's own tests** — passing the one test you
  happened to pick is not verification.
- **Never weaken a protected test** to make the chain complete.
- **The plan comes before the code.** Always.
- **One upload.** It belongs to `verify`; a second run just writes a redundant checkpoint.
