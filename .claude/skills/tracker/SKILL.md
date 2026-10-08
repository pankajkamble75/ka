---
name: tracker
description: The delivery pipeline's shared work ledger at docs/trackers/RESEARCH-TRACKER.md — one row per research point and per plan, carrying its state from OPEN through UPLOADED. Every pipeline skill writes to it; ship reads it to prove nothing was dropped. Use when the user says "tracker", asks what is outstanding / in flight / left to do, or asks whether a research report or plan set is finished. Also invoked by create-research-report, create-implementation-plan, implement, verify and upload to record their own transitions.
---

# Tracker

The pipeline's **current state of open work**, in one file: `docs/trackers/RESEARCH-TRACKER.md`.

Named `tracker` deliberately — not `todo`. It is not a task list the model keeps in its head for one turn;
it is a committed artifact that outlives the session, and the thing `ship` checks before it can claim a
report is finished.

## Why it exists

Research-11 sat at "3 of 4 built" for days without anyone noticing, because the outstanding point lived
only in a conversation. The numbered ledgers fixed the *reporting*; they did not give the work a **home**.
A plan file that exists with no implementation reads as done to anyone skimming the directory, and a
research point deferred "to its own plan" is invisible until someone asks.

## The FIVE trackers and the REGISTRY — `Q186`, extended by `Q188` (2026-09-19)

**Every tracker lives in `docs/trackers/`, and `TRACKER.md` is now the REGISTRY of them, not one of
them.** Point a skill at the registry and it can find every ledger and pull status across all of them.

| file | the question | unit | lifespan |
|---|---|---|---|
| **`TRACKER.md`** | **which trackers exist?** The registry. **Holds references, never state** | a tracker | permanent |
| **`RESEARCH-TRACKER.md`** | what work exists, what was implemented **and when**, with the SHA — the LINEAGE machine. *(This file was `TRACKER.md` until `Q188`; it was RENAMED, so `git log --follow` reaches every row)* | a research point | **permanent**; Active → Closed |
| **`QUESTIONS-TRACKER.md`** | what decision waits on the author, and **which stage it blocks** | a question | permanent; OPEN → ANSWERED |
| **`VPS-TRACKER.md`** | what was handed to the VPS, and what came back | one PLAN per entry (`Q181`) | **transient**; archived |
| **`PENDING-TRACKER.md`** | what we intend to do LATER, **at what priority and of what type** (`Q189`) | a topic | until promoted |
| **`HANDOFF.md`** | where everything stood when the last session ended | the session | overwritten each `/bye` |

**THE RESEARCH TRACKER IS COMPLETE; THE VPS TRACKER IS A SUBSET.** Every research point is in the
research tracker. Only the slice that is decided, planned and **unattended-buildable** ever reaches the
VPS tracker — `vps-upload` holds back anything still needing the author (`Q183`). **So "not in the VPS
tracker" never means "not tracked", and a clean VPS queue never means there is no open work.**

**The lineage claim belongs to the research tracker alone.** A VPS entry is archived once its notes are
read; the research row keeps the SHA and the date forever. If you want to know *when* something was
implemented, only one of these files can tell you.

**Do not read them one at a time — run `/show`**, which renders all of them together with guards that
check the parse against the sources.

### What the REGISTRY must never become (`Q188`)

- **Not a sixth ledger.** The moment a work item gets a row in `TRACKER.md`, the same fact lives in two
  files. This repo has that measured: the Backlog mirror stood at **36 rows against 34 topics** on
  2026-09-19. **The registry holds references, never state.**
- **Not a status page.** Counts belong to `/show`, which derives them. A number typed into the
  registry is wrong the next time anything moves.
- **Not where a new tracker gets forgotten.** Adding a tracker means adding its registry row in the same
  commit. An unregistered tracker is one `/show` will not find.

### The DEFER direction — `Q186`

Work moves INTO the pipeline by promotion (`pending.md` → a research note → Active rows). **It moves OUT
the same way**: a row the author decides not to do now goes terminal as **`DEFERRED`** *and* gets a
**`pending.md` topic**, with each citing the other.

| | |
|---|---|
| **the row** | leaves Active, filed in Closed as `DEFERRED`, Note names the `pending.md` topic |
| **the topic** | added to `pending.md`, naming the research and the row it came from |
| **the Backlog mirror** | gains the row, as for any other pending topic |

**Why both, and not just one.** A deferred row that only leaves Active loses the intent — nobody knows
it was a decision rather than an oversight. A `pending.md` topic with no closed row loses the lineage —
nobody can tell it was once researched and costed. **`DEFERRED` is still counted under Outstanding**, which
is the mechanism that stops a parked item becoming a forgotten one.

**This is also where a HELD-BACK plan lands when the author defers it** — `vps-upload` `Q183` holds back a
slice that cannot run unattended, and the author's three answers are: decide it (→ plan → VPS), defer it
(→ here), or reject it (→ `REJECTED`).

## What it is NOT

- **Not `docs/trackers/VPS-TRACKER.md`.** That is a delivery queue between two machines — transient, plan-shaped,
  and covering only the unattended subset. This is the permanent record of everything.
- **Not `docs/checkpoints/CHECKPOINTS.md`.** Checkpoints are append-only narrative history — *what landed,
  when, and why*. The tracker is mutable current state — *what is still open*. A row leaves the tracker's
  active table when it reaches a terminal state; a checkpoint entry is never edited.
- **Not a second source of truth for whether code exists.** The tree is. See "The tracker can lie".
- **Active/Closed are not a backlog of ideas.** Only work that has entered the pipeline — a research
  point, or a plan. Unstarted ideas live in the **Backlog** section, which is a different table with
  different rules; see below. Mixing the two is the specific thing that section exists to prevent.

## The file

`docs/trackers/RESEARCH-TRACKER.md`. **Three tables**: `Active` and `Closed` (ship work), and `Backlog` (a mirror of
`docs/trackers/PENDING-TRACKER.md`, which is NOT ship work — see "The Backlog is separate").

```markdown
# Tracker

Current state of pipeline work. Rows leave ACTIVE when they reach a terminal state.
Written by create-research-report, create-implementation-plan, implement, verify and upload.

## Active

| Item | From | Plan | State | Since | Note |
|---|---|---|---|---|---|
| R4 Proposal-to-Change tab | research-11 | plan-82 | PLANNED | 2026-08-02 | run 3 of 4 |
| R1 catch-all allowlist | research-12 | plan-83 | OPEN | 2026-08-02 | latent, not live |

## Closed

| Item | From | Plan | State | Closed | Evidence |
|---|---|---|---|---|---|
| R3 post-promotion verification | research-12 | plan-80 | UPLOADED | 2026-08-02 | `2ded61c` |
```

**States**, and only these:

| State | Meaning | Terminal? |
|---|---|---|
| `OPEN` | a research point exists; no plan covers it yet | no |
| `PLANNED` | a plan covers it; not built | no |
| `IMPLEMENTED` | built, tests written | no |
| `VERIFIED` | verify passed, gate run | no |
| `UPLOADED` | pushed; carries the SHA | **yes** |
| `HALTED` | stopped deliberately; the Note says why | **yes** |
| `DEFERRED` | out of scope here; the Note names where it goes | **yes** |
| `REJECTED` | researched and declined; the Note says why | **yes** |

A terminal row moves to **Closed**. Everything else stays in **Active** — that is the point.

## Who writes what

| Skill | Writes |
|---|---|
| `create-research-report` | one `OPEN` row per research point (R1..Rn), `From` = the report |
| `create-research-report` · the author | a batch tag on each row and the report's rows in `## Batches` (§Batches) |
| `vps-upload` | takes the lowest `READY` batch only; sets it `QUEUED` (§Batches) |
| `create-implementation-plan` | sets each covered point to `PLANNED` with its plan; adds `DEFERRED` / `REJECTED` rows with reasons; adds one row per plan in the set |
| `implement` | the plan's row → `IMPLEMENTED`, Note carries the ledger (`7/7 deliverables, 20/20 cases`) |
| `verify` | → `VERIFIED`, Note carries the gate result |
| `upload` | → `UPLOADED` with the SHA; moves the row to Closed |
| `ship` | writes nothing; **reads** it to check the set is clean |

**Write the transition when it happens, not at the end.** A row that jumps `OPEN` → `UPLOADED` records
nothing useful, and a session that dies mid-plan leaves no trace of how far it got.

## Batches — `/vps-upload` takes ONE batch at a time

**Ruled by the author 2026-09-26.** A research's open points are queued to the VPS in **numbered batches**, not all
at once, so each upload is a reviewable unit with its own gate and the full suite runs once per batch (`vps-download`
§1a).

- **Where they live:** the tracker's `## Batches` section — one table row per batch: *Batch · Research points ·
  Depends on · Gate to close it · State* — **and** a tag at the start of every row's Note, after the class and
  severity marker: `**Batch 2.**`, `**Batch — demo gate.**`, or `**Batch — constraint**` for a `decide` row that
  every batch obeys. The table is what a reader scans; the tag keeps each row self-describing.
- **Who assigns them:** the batch order follows the author's ruled build order for that research (e.g. `Q271`:
  test net first, demo first, refactor last). `create-research-report` proposes batches when it writes the report's
  rows; the author's answer, or `vps-upload` Phase 2, confirms them. **A batch is never invented silently** — the
  order is either ruled or proposed and named.
- **Batch states:** `READY` (the next to upload) · `WAITING — <what>` (a batch, a gate or a measurement) · `QUEUED`
  (its plans are entries in `VPS-TRACKER.md`) · `DONE` (every row terminal and the gate passed). **Exactly one
  batch is `READY` at a time.**
- **`vps-upload` takes the lowest `READY` batch and only that batch** — it decomposes, asks, writes plans and
  queues entries for those rows alone, then sets the batch `QUEUED`. Rows outside the batch stay `OPEN`.
- **Closing:** when every row in a batch is terminal and its gate has passed, the batch becomes `DONE` and the next
  one `READY` — written in the same commit that closes the batch's last row.
- **A batch's rows keep their own states.** The batch is a grouping over the rows, never a replacement for them;
  `## Active` and `## Closed` stay the ledger.

## The Backlog is separate, and stays separate

`docs/trackers/PENDING-TRACKER.md` is the user's own scratchpad — designed-but-unstarted work, written freely and
by hand. The tracker mirrors it in a **`## Backlog`** table so that "what is pending" has one answer
instead of two. Added 2026-08-03 at the user's explicit instruction, which included the constraint:

> *"Pending.md can be scratch pad. But free to track in tracker. But please dont mix it with the ship
> tasks which the tracker is already used. Both should be separate."*

So:

- **No pipeline skill writes Backlog rows.** `create-research-report`, `create-implementation-plan`,
  `implement`, `verify` and `upload` touch **Active/Closed only**.
- **`OPEN` in Backlog means *recorded, not started*.** It carries none of the pipeline meaning `OPEN` has
  in Active, and it must never be read as one. The only other states a Backlog row takes are
  `PROMOTED → research-NN` (it became ship work), `SHIP WORK` (it already was, and an Active row owns its
  state), and `RESOLVED` (done directly, without a plan — legitimate for genuinely small items; the row
  must then say what was done and what was deliberately left).
- **`ship`'s clean check reads Active/Closed only.** A full Backlog does not make a run dirty. Reading it
  as dirty would make every ship run fail forever, which is exactly why the tables are separate.
- **Promotion is the only bridge.** To act on a Backlog item, write a research note about it; it then gets
  ordinary Active rows and the Backlog row is marked `PROMOTED → research-NN`. **Never let both tables
  claim the same item in an un-annotated way** — if an item is already ship work, the Backlog row says so
  and defers to the Active row for its state (NI-2 is the worked example).
- **`pending.md` stays authoritative for its own content.** The Backlog table is a mirror, not a
  replacement — do not edit the user's note to match the table. If they diverge, the note wins and the row
  gets corrected.

## The clean check — what `ship` enforces

**A set is CLEAN when every row from its report is in a terminal state.** Before a ship run reports
success, read the tracker and confirm it. If any row is still `OPEN`, `PLANNED`, `IMPLEMENTED` or
`VERIFIED`, the run is **not finished** — say which rows and why, and either continue the loop or report
the set as partial. That is the check that would have caught research-11.

**Scope the check to `Active`/`Closed`.** Backlog rows are permanently `OPEN` by design and are not part
of any set — counting them would make every run report NOT CLEAN forever.

Report it as a count, matching the pipeline's other ledgers:

```
Tracker: research-12 — 3 rows, 3 terminal (2 UPLOADED, 1 DEFERRED → plan-83). CLEAN.
Tracker: research-11 — 4 rows, 2 terminal, 2 ACTIVE (R3 HALTED, R4 PLANNED). NOT CLEAN.
```

## The tracker can lie — treat it as a claim, not evidence

It is written by the same agent doing the work. A row saying `IMPLEMENTED` proves only that something
wrote that word.

- **`verify` recounts from the artifacts**, never from the tracker. That rule already exists and this
  changes nothing about it.
- **`ship` cross-checks before trusting a terminal row**: an `UPLOADED` row must have a SHA that exists
  (`git cat-file -e`), and a `PLANNED` row must have a plan file that exists.
- **When the tracker and the tree disagree, the tree wins.** Correct the row, and say in the report that it
  was wrong — a tracker quietly fixed is a tracker nobody can trust.

This is the same reason `implement`'s ledger is reconciled rather than believed: it claimed "9 of 9" for
plan-80 when D9 did not exist.

## Research status — `Q236`, generated

`RESEARCH-TRACKER.md` carries a generated `## Research status` section: one row per research with its
`Class`, `Severity` and **OPEN / PARTIAL / CLOSED** — OPEN while every point is still on this tracker,
CLOSED once every point has moved (to the VPS tracker, the parking lot, the pending tracker, or a terminal
state), PARTIAL in between. **Any transition that moves a row, or a VPS entry that names a plan, changes
it — regenerate in the same commit, never hand-edit:**

    .venv/bin/python -c "from tracking.tests.test_research_status import write_research_status as w; print(w())"

`tracking/tests/test_research_status.py::test_P1` fails when it is stale.

## Required behavior

1. **Read before writing.** The file may have been edited by a previous session or by hand.
2. **One row per item**, keyed by `Item` + `From`. Update in place; never add a duplicate row for a state
   change.
3. **Every non-terminal row needs a `Since` date**, so a stalled row is visible as stalled.
4. **Every terminal row needs evidence** — a SHA for `UPLOADED`, a reason for `HALTED` / `REJECTED`, a
   destination plan for `DEFERRED`. A terminal state with an empty Note is not terminal.
5. **Create the file if missing**, with both headings and no rows.
6. **Never delete a row.** Move it to Closed. The history of what was deferred and why is the useful part.
7. **Do not commit from here** — the tracker rides along in whatever `upload` is already committing.

## Reporting

When invoked directly ("tracker", "what's outstanding"), print the Active table and one summary line per
source report. Keep it short; the file is the detail.
