---
name: show
description: One derived, tabular view of where every piece of work is — which RESEARCH is open (docs/trackers/RESEARCH-TRACKER.md), which PLANS are live on the VPS (docs/trackers/VPS-TRACKER.md), which QUESTIONS are open and WHICH STAGE each blocks (research-stage questions block vps-upload from turning research into plans; implementation-stage ones were parked by a vps-download run), and what is deferred to PENDING-TRACKER.md with its priority and type. Rendered from the files by tracking/tests/test_status_table.py, never hand-written. Use when the user says "show", invokes /show, or asks "what is open", "where are we", "show me the state". Also run AUTOMATICALLY at the end of every vps-upload run, after every plan a vps-download run implements, and at the end of every vps-download run — because those are the three moments work MOVES between the ledgers.
---

# Show

**Five tables, one question each, all derived from the files — and each of the three trackers opens
with its STANDING.**

## It OPENS with `## TRACKER STATUS` — THREE tables, one per tracker

**The author, 2026-09-19: *"it will show me the status of only the question tracker in tabular format,
then for the VPS tracker in tabular format and then for the research tracker… it's not one table but 3
tables."*** They were being rendered — but each standing sat buried inside its own detail section, with
open rows and completion tables around it, so the three never read as a set.

They now come FIRST, together, in their own section, each with its name and total in the heading:

```
#### QUESTIONS-TRACKER.md — 192 entries
*what is waiting on a human*

| State | Count | Live? |
|---|---:|---|
| `ANSWERED` | 183 | terminal |
| `OPEN` | 3 | **live** |
```

**The detail sections keep everything else.** This section answers *"how does each tracker stand"* and
nothing else; tables 1-5 below answer *"what is open, and what should I do"*.

`test_every_tracker_reports_its_STANDING_not_only_its_open_rows` asserts the section exists, that each
heading carries its total, and that there are **exactly three** standing tables.

Each names EVERY state in that file, not only the open rows — *"the status… in tabular format"*:

```
**VPS-TRACKER.md** — 155 entries

| State | Count | Live? |
|---|---:|---|
| `CLOSED` | 155 | terminal |
```

**Every column carries a header, and that is a rendering requirement rather than a style choice.** The
first version wrote `| State | Count | |` — a blank third header — which some markdown renderers drop
entirely, printing raw pipes instead of a table. Three tracker standings therefore looked like they
were not being rendered at all. `test_every_rendered_table_has_a_HEADER_FOR_EVERY_COLUMN` fails on a
blank header cell.

**`live` is marked PER TRACKER**, because the three spell it differently: a `DEFERRED` question is
waiting on the author, while a `DEFERRED` research row is terminal. One shared list would be wrong for
at least one of them — the mistake the registry's own vocabulary table exists to prevent.

**Suppression is a MARK, not a state.** It is shown in the table and labelled as already counted, so it
is never added twice.

**Why the standing and the open rows are both needed.** The open rows are the WORKLIST; the standing is
the STATE OF THE FILE. Without it a tracker with nothing open rendered as a sentence of prose, and a
reader could not tell an empty QUEUE from an empty FILE — nor see that 155 entries had been worked to
reach it.

| # | table | source | answers |
|---|---|---|---|
| 0 | *(the registry)* | `docs/trackers/TRACKER.md` | **which trackers exist at all** — start here if you are not sure what to read |
| 1 | **RESEARCH** | `docs/trackers/RESEARCH-TRACKER.md` — **Active AND Closed** | the ledger's standing, **per-research completion**, and which research still has open points |
| 2 | **PLANS** | `docs/trackers/VPS-TRACKER.md` | which plans are live on the VPS, **and the most recently worked entries even when none are** |
| 3 | **QUESTIONS** | `docs/trackers/QUESTIONS-TRACKER.md` | what is blocking, **and at which stage** |
| 4 | **PENDING** | `docs/trackers/PENDING-TRACKER.md` | what was deferred to later |

> ### Why the skill is `show` but the renderer is still `test_status_table.py`
>
> **Renamed 2026-09-19: the skill was `status` and clashed with Claude Code's own `/status`.** The
> RENDERER keeps its name deliberately — nothing clashes there, it is imported by eight files and by
> `test_plan719_code_tracker`, and renaming a module to match a slash-command would spend real risk on
> cosmetics. `render_status()` still renders status tables; only the way you INVOKE it changed.

## How to run it

```
/root/.venvs/enterprise-os/bin/python -c "
from tracking.tests.test_status_table import render_status
print(render_status())"
```

**Paste the output verbatim.** Do not re-type it, do not summarise the tables away, and **do not
hand-write a status table** — this repository has twice had a renderer drift from its sources, and the
guards in that module exist because a count is not evidence that the parse worked.

After pasting, add **at most three lines** of your own: what changed since the last status if you know,
and the single thing most worth doing next. The tables carry the detail.

## Table 1 shows COMPLETION, not only what is open

**The author, 2026-09-19: *"status should also show status of research tracker."*** It already listed
research with open rows — but a research whose every row is terminal VANISHED from it. **research-191
was delivered end to end on 2026-09-19 and was invisible in `/show` the same day**, which reads as if
the work never happened.

So table 1 carries three things, in order: the ledger's STANDING by state, the **completion table** for
recent research, and then the open rows.

| Research | Rows | Live | Uploaded | Resolved | Declined | |
|---|---:|---:|---:|---:|---:|---|
| research-191 | 6 | 0 | 5 | 1 | 0 | ✅ delivered |
| research-190 | 7 | 3 | 2 | 2 | 0 | **in flight** |

**It reads Active AND Closed**, because a finished research lives entirely in `## Closed`. And it filters
to `research-NN` **by shape, not by sort**: the `From` column is free text carrying plan pairs, note
names and backlog ids, and a sort by trailing number once put `plan-299 + plan-293` at the top of a
table headed *"Recent research"*.

## `OPEN` is a STATE, and the worklist must not borrow the word

**The author, 2026-09-19:** *"R7 is already converted into plan and pushed to the vps tracker, then why
is it showing up as an open row?"* Two answers were owed, and only one was a defect:

| | |
|---|---|
| **listing it was RIGHT** | a written, queued plan is not built code. The row goes terminal at `UPLOADED`; dropping it at `PLANNED` would have hidden **two of the three** live rows |
| **calling it *open* was WRONG** | it reads `PLANNED`. The table borrowed a state name to mean *unfinished* — the same overload as `Status` meaning both *answered* and *waiting*, which this renderer had already been made to fix once |

So the heading reads **UNFINISHED**, names the states it summarises (*"1×`OPEN`, 2×`PLANNED`"*), and the
table carries a **State** column, because the distinction should be checkable rather than inferred.
`test_the_worklist_does_NOT_call_every_live_row_OPEN` fails on the word and on a missing state.

## A view that shows only what is OPEN erases what is FINISHED

**The author found this same defect three times, in three places, before it had a name:**

| where | what was invisible |
|---|---|
| the tracker standings | a tracker with nothing open rendered as prose — an empty QUEUE read like an empty FILE |
| table 1's research list | **research-191, delivered end to end that same day** |
| table 2's VPS queue | **the four entries closed that morning** — the queue said only *"empty"* |
| table 3's questions | **the 15 rulings taken that day** — a reader had to open the file to learn them |

**And the reverse gap, found the same way.** Table 1 showed *how much* was left per research but never
*what to do about each row*. A `DECIDE` row needs a person; a `FIX` with no plan needs an entry; both
read as **"1 open row"** in a tally. Table 1 therefore carries **the open rows and what each needs**,
derived from the row's KIND — guarded by `test_every_OPEN_row_says_WHAT_IT_NEEDS`, which also fails if
a `DECIDE` row does not name the author as its owner.

Each standing also states its **terminal share** (*"1458 of 1462 terminal (99.7%) · 4 live"*): 4 open
alone reads as a young ledger rather than a nearly-finished one.

**The fourth fix found a defect the other three could not.** Adding *"most recently answered"* to table
3 made the sequence read `Q193, Q192, Q191, Q189` — a hole where `Q190` should be. **`Q190` (the TEST
TRACKER) had been implemented and cited by name in `testrecorder.py`, `code-lineage.md`, `implement`,
two plans, a research report and four trackers — and never written into the registry.** A ruling cited
everywhere and registered nowhere dies with the comments carrying it, which is the exact failure the
registry exists to prevent. Registered late, with the lateness recorded in the entry, and
`test_the_question_registry_has_NO_GAPS_in_its_numbering` now fails on any hole.

Each fix is the same shape: render the FINISHED alongside the open. Table 2 therefore carries **Most
recently worked** — newest first, closed entries included — whether or not anything is live, guarded by
`test_an_EMPTY_vps_queue_still_shows_WHAT_EMPTIED_IT`.

## `Status` means ANSWERED-OR-NOT — the author's ruling, 2026-09-19

**It used to mean two things.** `Q15`/`Q16` read *"OPEN — nobody has answered"*, while `Q6` read
`DEFERRED (moved to PENDING-TRACKER.md)` — a ROUTING decision. All three had been parked without an
answer, and the author caught it: *"my understanding is that Q15 and Q16 were deferred, so why are they
examples of open?"* They were. `Q6` was the anomaly.

**Three fields now, three different questions:**

| field | answers | and it does NOT mean |
|---|---|---|
| **`Status`** | has a human ANSWERED? | that anyone is waiting |
| **`Asking`** | may it be asked again? | that it was answered |
| **`Routed`** | where did it go? | that it was answered |

**So table 3 counts ASKABLE, not merely unanswered** — unanswered, not suppressed, not routed.

**The stage counts are over askable questions only** (the author, 2026-09-19). The line used to read
*"3 at the RESEARCH stage blocking `vps-upload`"* directly above *"0 actually waiting"* — a
contradiction on its face. **A question nobody may ask blocks nothing, however real its stage would be
if it were asked.** The unaskable ones are still listed, each with its reason, so *unanswered* stays
visible without reading as *waiting*.

**`Stage` and `Blocks` are different columns for the same reason.** `Stage` says where a question
WOULD block if it were asked; `Blocks` says what it is blocking TODAY. For a suppressed or routed
question those differ, and `test_the_BLOCKS_column_agrees_with_the_ASKABLE_summary` fails if a row
claims to block something the summary says is blocking nothing.

**And `Status` is not `Asking`.** An entry is routinely `Status: OPEN` (nobody answered) **and**
`Asking: SUPPRESSED` (do not ask again) — `Q15` and `Q16` are both, and `Q16`'s suppression carries a
condition (*"until the frame is re-shot"*). Collapsing the two tells every guard that reads `Status` a
human answered when none did, which is the failure of 2026-09-06 and why
`test_plan389_acceptance::test_N9` reads `Status: OPEN` to keep research-99 undelivered. *(historical — Q6/Q15/Q16 closed 2026-09-29; N9 now pins that DT7 is WITHDRAWN, never ACCEPTED)*

## The STAGE column is the point of table 3

The author, 2026-09-19: *"it will tell me whether the question is open at the research stage ie it is
blocking the skill from converting research into plan or these are questions discovered during
implementation stage."*

| stage | raised by | blocks | answered where |
|---|---|---|---|
| **RESEARCH** | `vps-upload` Phase 3 | **the decomposition** — no plan can be written past it | the ask loop, with the author present |
| **IMPLEMENTATION** | `vps-download` §4 | nothing immediately — the run parked it and carried on | the end of the unblock loop (`Q179`), or the next `/vps-upload` |

**The two have different urgency and that is why they are separated.** A research-stage question is
holding up work that is otherwise ready to build. An implementation-stage one is a finding from a run
that already finished.

**`UNKNOWN` is a missing field, not a soft guess.** The renderer reads an explicit `**Stage:**` field
first and only derives when one is absent; when nothing in the entry decides it, it says `UNKNOWN` and
names the fix. **Never relabel an `UNKNOWN` by eye** — add the field to the entry instead, and the next
render is right for everyone. A wrong label is acted on; an `UNKNOWN` is investigated.

**A SUPPRESSED question is still OPEN.** Suppression governs *asking*, `Status` governs whether anyone
answered. The table marks them; do not read the mark as closure.

## Run it AUTOMATICALLY at these three moments — the author, 2026-09-19

These are the moments work **moves between ledgers**, which is exactly when a stale mental model forms:

| moment | why there |
|---|---|
| **end of every `/vps-upload` run** | the research just decomposed: points left the tracker's live view for the VPS queue — or for `PENDING-TRACKER.md` if deferred. The status is the proof of where each one went |
| **after EVERY plan a `/vps-download` run implements** | one entry just closed and its tracker row just moved to `UPLOADED`. Per-plan, not per-queue: a six-entry queue that only reports at the end hides five transitions |
| **end of every `/vps-download` run** | the queue is worked; this is the closing picture, beside the run's own OPEN/BLOCKED tables |

**It is cheap** — it parses four files and runs in well under a second, so there is no batching argument
for skipping it. **It writes nothing**, so it can never interfere with a run in flight.

**It does not replace either skill's own report.** `vps-download` §Report says what THAT RUN did;
`/show` says where the WHOLE SYSTEM now stands. Both, in that order.

## What `/show` will not do

- **It writes to no file.** Every other renderer here regenerates a section between markers; this one
  returns a string. That is deliberate: `test_tracker_row_shape::_rows` finds a section by splitting on
  its heading, so a generated block carrying `## Active` above the real section hands that guard the
  wrong rows (measured 2026-09-18). A renderer that cannot write cannot cause it, and
  `test_status_writes_nothing` pins that.
- **It does not reconcile disagreements, it REPORTS them** — but it reports the RIGHT comparison.
  The Backlog mirror is checked by **IDENTITY, never by count**: does every mirrored ID still appear in
  `PENDING-TRACKER.md`, and does any ID appear twice?

  **A count comparison there is a unit mismatch.** `/show` made one for a day — *"36 rows against 34
  topics, one of them is stale"* — and neither was: the mirror is per-ID, the source is per-TOPIC, and
  one topic bundles several IDs (*"NI-4 / NI-5 / NI-6 · Boundary and modularity audit"*). **The counts
  SHOULD differ.** Reporting that as drift sent a reader looking for a problem that did not exist.

  The one real defect the identity check found was an **ID collision**: two different backlog items both
  labelled `NI-9`, the second of which is `NI-10`.
- **It does not judge.** An empty VPS queue is rendered with the reason it is not "no open work"
  (`Q186`: the tracker is COMPLETE, the VPS queue is a SUBSET) — but the skill never concludes that the
  tree is finished. Only the tables say what they say.

## When the render looks wrong

**Trust the files, not the render.** The module's own guards check the parse against the sources
(`test_the_render_names_every_live_vps_entry` fails if a live entry is dropped), so a surprising number
is usually a real change — but if you believe the render, verify against the file before reporting it:

```
.venv/bin/python -m pytest -q tracking/tests/test_status_table.py
```

Five guards, under a second. **A renderer that reports "0 OPEN" against a file full of open rows is the
exact failure this repo has already had** — that is why `render_outstanding`'s header must be checked
before committing, and why these guards exist.
