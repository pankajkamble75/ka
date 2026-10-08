---
name: report
description: Tabular status reports over the delivery ledger. "report current" — what is being implemented now, its research, and how many of that research's plans are done or waiting on a decision. "report all" — every active item, the research and plan it belongs to, and what is done against what is not. "report plan" — one plan in detail, covering its research, whether it is implemented, and its measured test results including positive, negative and product tests. Use when the user says "report current", "report all", "report plan", or asks for a status table over research, plans or tests.
---

# Report

Three tabular reports over `docs/trackers/RESEARCH-TRACKER.md`, `docs/implementation-plans/` and the test suites.

**Every number is MEASURED, never quoted.** The tracker is a claim written by the same agent that did the
work; a plan's `## Plan totals` is what the plan *intended*. Neither is evidence. Where the two disagree
with the tree, **the tree wins and the report says so**.

**Output is a table.** Prose belongs under it, not instead of it.

---

## The three commands

| the user says | the report answers |
|---|---|
| **`report current`** | what is being implemented right now, whose research it is, and how that research stands |
| **`report all`** | every active item, what research and plan it belongs to, done against not done |
| **`report plan`** | one plan in full, including **measured** test results |

---

## Reading the ledger — the traps, learned the hard way

Anything parsing `TRACKER.md` hits these. They cost four wrong counts in one session:

- **Two ledgers, different row shapes.** Ship rows (Active/Closed) have **6 columns / 8 cells**; backlog
  rows (`## Backlog`, mirroring `docs/trackers/PENDING-TRACKER.md`) have **5 columns / 7 cells**. Counting the
  backlog with the ship shape reports 1 pending when it is 32.
- **The state column moves.** Ship rows: `| Item | From | Plan | State | Since | Note |` — state is cell 4.
  Backlog rows: `| # | Topic | Band | State | Note |` — **also cell 4, but cell 3 is a band, not a plan.**
- **Escaped pipes are real.** A note may contain `` `run \| null` ``, which markdown renders literally.
  `str.split("|")` does not know that. Split on **unescaped** pipes: `re.split(r"(?<!\\)\|", line)`.
- **26 rows carry an UNESCAPED pipe** and split into 9 or 11 cells. They are still rows with a state in
  cell 4 — count with `>= 8`, not `== 8`, or you lose them.
- **`## Outstanding` echoes every row** with fewer columns, ABOVE `## Active`. A naive
  `next(l for l in lines if l.startswith(f"| {name}"))` finds the echo first. **Scope every row lookup to
  the section you mean.**
- **`## Backlog` is never ship work.** `ship` does not read it. Mixing the ledgers once made the
  outstanding total read 60 when the ship figure was 31.

**Never edit the tracker from this skill.** Reporting is read-only; `tracker` owns writes.

---

## `report current`

**What is being implemented now**, and how its research stands.

### Finding "current" — in this order, and say which rule fired

1. A tracker row in `IMPLEMENTED` or `VERIFIED` — work started and not landed.
2. Otherwise, the **highest-numbered plan file** whose row is not yet `UPLOADED`.
3. Otherwise, the plan named in the most recent `plan-NN` commit.
4. Otherwise: **nothing is in flight** — say that plainly and report the last thing that landed instead.

### The table

```
CURRENT — plan-263 (rule 2: highest plan not yet UPLOADED)

| research   | plans | done | waiting on a decision | in flight | not started |
|------------|-------|------|-----------------------|-----------|-------------|
| research-77|   5   |  2   |          1            |     1     |      1      |
```

- **plans** — plans allocated to that research, from its rows' Plan column plus any named in its set line.
- **done** — rows reading `UPLOADED`, `REJECTED`, `RESOLVED` or `SUPERSEDED`.
- **waiting on a decision** — rows whose kind is `*(decide)*` **and** whose state is not terminal, plus any
  row whose note says it is blocked on the author. **This column is the point of the report**: it separates
  *nobody has built it* from *nobody has answered it*, and only the second is waiting on a person.
- **in flight** — `IMPLEMENTED` or `VERIFIED`.
- **not started** — `OPEN` with a plan number, or `OPEN` with none.

Under the table, one line naming **what the current plan is for** and **what closes it**.

---

## `report all`

**Everything active, and what it belongs to.** This is the whole-ledger view.

### The table

```
ALL ACTIVE — 1 ship row, 32 backlog topics

| research      | point | plan     | state | done | not done |
|---------------|-------|----------|-------|------|----------|
| research-68/69| —     | —        | OPEN  | 28 rows under it, all terminal | a live J5 run |
```

- **Derive the research from the row's `From` column**, not from the item text. A row whose `From` names no
  research (found by a live run, or by measurement) shows `—` and says where it came from instead.
- **A row with no plan is not an error.** Umbrella rows and `decide` points often have none — say *"none,
  by design"* and give the reason from the note rather than leaving a blank that reads as an omission.
- **Include the backlog as its own block**, clearly separated and labelled *not ship work*. Never merge it
  into the ship count.
- End with the four category totals — ACTIVE / DEFERRED / PENDING / CLOSED — taken from the tracker's own
  `## Categories` index, and **say if they disagree with your count**.

---

## `report plan`

**One plan, in full.** Defaults to the current plan (same rules as `report current`); takes a number when
the user gives one.

### The tests are RUN, not read

This is the section that makes the report worth anything. A plan's `## Plan totals` says what it *meant* to
test. **Run the suites and report what actually happened.**

```bash
# the plan's own module, and whatever it names as covering tests
pytest <the plan's test module> -q -p no:randomly
```

- **Positive and negative cases** — count the tests that exist for `P1..Pi` and `N1..Nj`, and compare with
  the plan's stated totals. **A mismatch is the headline, not a footnote.**
- **One test may cover two cases** — say so; never count it twice to make the arithmetic work.
- **Product tests** (see `verify` §2b) belong to the **research**, not the plan. Report:
  - whether the research defines any at all — *"none defined"* is a real and common answer;
  - for each, PASS / FAIL / NOT RUN, and the research point it proves;
  - **for a failure, what would make it pass.** A product test may legitimately be red until the last plan
    of a set lands, and that is expected — but it must be visible.

### The table

```
plan-262 — research-75 R9

| field                | value |
|----------------------|-------|
| research             | research-75 (9 points, CLEAN) |
| research point       | R9 — decide whether the parent row closes |
| implementation plan  | plan-262 |
| implemented          | YES — 6db55076 (characterization), a576991c (change) |
| state on the tracker | UPLOADED |
| deliverables         | 5 of 5 |
| positive cases       | 6 of 6 |
| negative cases       | 6 of 6 |
| tests run            | 13 passed, 0 failed, 1 skipped |
| product tests        | none defined by research-75 |
```

Then one line on **what it changed** and one on **anything left open**.

---

## Rules

- **Measure, never quote.** Counts come from the tree and from running tests. A number copied out of a plan
  is that plan's intention.
- **The tree wins.** Where the tracker and the tree disagree, report the tree and say the row is wrong —
  do not fix it here; `tracker` owns writes.
- **Tabular first.** Every command's answer is a table. Explanation goes under it.
- **Never fabricate a test result.** *"Not run"* is a legitimate cell; an invented green is a defect.
- **Say which rule picked "current".** A report whose subject was guessed is a report about the wrong plan.
- **Distinguish *not built* from *waiting on a person*.** They look identical on a ledger and are not the
  same problem — one needs a plan, the other needs an answer.
- **A red product test means the research is not delivered**, however many rows read `UPLOADED`. Say it on
  the same line as the totals.
- **Read-only.** This skill writes nothing — not the tracker, not a plan, not a checkpoint.
