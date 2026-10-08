---
name: startup
description: Read the session handoff at docs/trackers/HANDOFF.md AND the tracker at docs/trackers/RESEARCH-TRACKER.md, check their claims against the tree, report where the work actually stands, and ask whether to resume from that point. Use whenever the user says "startup", invokes /startup, or opens a session with "where were we", "what was I doing", "resume", "pick up where we left off", "catch me up", or "start from the handoff". Also use when a session begins on a new machine and the user asks what state the repo is in.
---

# Startup

Pick up a session someone else — or a past you — left behind.

The handoff at `docs/trackers/HANDOFF.md` is written at the end of a working session, by an agent with full
context, for an agent with none. This skill reads it, **checks it**, and hands the user a decision rather
than an assumption.

## Why this is not just "read the file"

**A handoff is a claim, not evidence.** It was true when written and the tree has moved since — a plan got
implemented, a blocker got removed, someone pushed from another machine. This repository has already been
bitten by exactly that: one handoff warned that a guard blocked the next plan, and by the time anyone read
it that guard had been rewritten and the blocker was gone. A skill that recited the file would have sent the
reader to solve a problem that no longer existed.

So: read it, then **verify the handful of claims that decide what happens next**, and say plainly where the
document and the tree disagree.

## The three sources, and which wins

A session's state is written down in three places, and they disagree more often than anyone expects.
**Read all three, and know the precedence:**

```
the TREE        what is actually there          — wins over everything
the TRACKER     docs/trackers/RESEARCH-TRACKER.md         — the authoritative LEDGER of what is open
the HANDOFF     docs/trackers/HANDOFF.md         — a NARRATIVE summary, written at one moment
```

- **The tracker answers *"what is open?"***, row by row, with a state per research point and plan. It is
  structured, it is tested, and every pipeline stage writes to it.
- **The handoff answers *"what was I doing, and what should I do next?"*** It is prose, it is a snapshot,
  and it is the one most likely to have gone stale.
- **Where the handoff and the tracker disagree, the tracker is closer to the truth — and where the tracker
  and the tree disagree, the tree wins.** Say so out loud when it happens; a reader who trusts the wrong
  one goes and does the wrong work.

## 1. Read the handoff

- `docs/trackers/HANDOFF.md` is the location. It is **not** `pending.md` — that is the parked backlog, a
  different document with a different job. If both look relevant, read the handoff for *"what was I doing"*
  and `pending.md` only for *"what else is waiting"*.
- **If there is no handoff**, say so plainly and do not invent one. Offer the alternatives that do exist:
  `docs/trackers/RESEARCH-TRACKER.md` §Active answers *"what is open"*, and `git log --oneline -10` answers *"what
  happened last"*. Then ask what the user wants to do.
- **If the handoff is undated or very old**, say so with its date. An eight-week-old handoff is a historical
  document, not a starting point.

## 2. Read the tracker — the ledger the handoff summarises

`docs/trackers/RESEARCH-TRACKER.md`, **§Active**. This is not optional and it is not the same question the handoff
answers:

- **Every non-terminal row**, with its state (`OPEN`, `PLANNED`, `IMPLEMENTED`, `VERIFIED`) and its plan.
  That is the real worklist; the handoff's "next action" is one opinion about which row to pick up.
- **Rows the handoff does not mention at all.** A handoff written mid-programme naturally talks about the
  programme; the tracker also carries everything *else* that is open. A reader who only got the handoff
  would not know those exist.
- **The `## Outstanding` block** — generated, and its own test fails if it disagrees with its sources.

**Run the tracker's own tests**: `pytest knowledge_worker/tests/ -k "tracker or outstanding"`. They are
fast, and they answer a question no amount of reading can: whether the ledger is internally consistent.
A tracker whose generated block disagrees with its rows is a defect, and finding it now beats trusting it
for an hour first.

## 3. Check the claims — the four that matter

Do not re-verify the whole document. Check the ones where a wrong answer sends someone the wrong way:

| Claim | How to check |
|---|---|
| the commit it says the tree is at | `git log --oneline -1`, `git status -sb` |
| the working tree is clean / pushed | `git status --short`; is `main` ahead of `origin/main`? |
| "plan-NN is next / not started" | **the tracker row** *and* whether an implementation exists in the tree |
| the test state it reports | run the cheapest suite that covers the claim — do **not** claim green without running |

**Report any disagreement as the first thing the user reads**, not as a footnote — a stale handoff quietly
followed is worse than no handoff, because it carries authority it has not earned.

Keep this proportionate. The tracker read, four checks and a test run — not an audit. The point is to know
whether the documents can be trusted, not to re-derive them.

## 3b. Read what has been DECIDED but not built

The tracker says what is *open*; it does not say what has been **agreed**. Those are different, and the
gap between them is the cheapest work in the repo — fully decided, fully unstarted, needing no ruling from
anyone.

- Read `docs/architecture/architecture-index-lookup.md`, follow it to the documents the handoff and tracker
  touch, and **collect every section marked `⏳ DECIDED, not built`**.
- Collect every `❓ Open` item in the matching `docs/questions/` sections, and cross-check them against
  `docs/trackers/QUESTIONS-TRACKER.md` — **an open item in a topic document with no registry entry will never be
  asked**, and registering it is one line.
- Where a document says `✅ built`, **spot-check one**: if the code it cites is not there, the document is
  claiming something the tree does not support, and that is worth knowing at the start of a session rather
  than the end.

**Do not start any of it.** This step reports; §5 asks.

## 4. Report where things actually stand

Short, and in this order:

1. **One line: can the handoff be trusted?** — *"Accurate as written"*, or *"Stale in one place: …"*.
2. **The LIVE state of every tracker — run `/show` and paste it verbatim.**

   ```
   /root/.venvs/enterprise-os/bin/python -c "
   from tracking.tests.test_status_table import render_status
   print(render_status())"
   ```

   **The handoff carries a SNAPSHOT of this; `/show` carries the truth.** `/bye` pastes the same four
   tables as they stood when the session ended, so comparing them is free and it is the fastest check
   this skill has: **where the handoff's copy and the live render disagree, something moved after the
   handoff was written** — usually a commit from another machine or a VPS run. Say so in one line, and
   trust the live render.

3. **Where the work stands** — the state table, taken from the **research tracker** and corrected where the tree
   disagrees. If the handoff's table and the tracker's rows differ, show the tracker's and say the handoff
   is behind.
4. **Anything open that the handoff never mentions** — one line. This is the tracker earning its place: a
   handoff talks about the programme it was written during, and a reader who only got the handoff would not
   know the rest exists.
5. **Decided but not built** (§3b) — one line each, with the document and section. **Say the count even
   when it is zero.** This is agreed work needing no decision from anyone, and it is invisible in every
   other ledger.
6. **Open questions with no registry entry** (§3b) — if any, name them; they would otherwise never be
   asked.
6. **The next action it names**, in one sentence.
7. **Anything that would block that action**, named now rather than discovered later — a missing runtime, a
   red gate, an environment difference from the machine the handoff was written on.

Do not restate the whole handoff. The user can read it; what they need from you is whether it is still true
and what it implies right now.

## 5. Ask — do not assume

**Always ask before starting work.** A handoff naming a next action is a recommendation from a past
session, not an instruction from the person in front of you. They may have opened this session for something
else entirely.

Use `AskUserQuestion`, and make the options concrete rather than yes/no:

- **resume the named next action** (say which plan or task, so the choice is informed);
- **review first** — read the artifacts the handoff points at before committing to anything;
- **something else** — they had a different reason for being here.

Where the handoff's next action is blocked, **say so in the option itself** rather than offering it as
though it were available.

## Rules

- **Read the handoff before saying anything about it.** Its filename is not a summary.
- **Verify before reporting.** Four checks, and the tree wins every disagreement.
- **Never start the work in this skill.** It reports and asks; `implement`, `ship` and the rest do the work.
  Beginning a plan because the handoff suggested it is exactly the assumption this skill exists to prevent.
- **Never fabricate a test result** to fill in the handoff's claim. Run it or say it was not run.
- **A missing handoff is a fine outcome**, reported plainly. Reconstructing one from git history and
  presenting it as a handoff would manufacture confidence nobody earned.
