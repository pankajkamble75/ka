---
name: questions
description: Walk the parked decisions one at a time — and the skill ANOTHER skill invokes when it needs a decision from the author, most often vps-upload step 8 — lead with the ARCHITECTURAL SNAPSHOT from docs/questions/, then the question in plain language, then the options with a recommendation and always a skip. Records each answer BOTH on docs/trackers/QUESTIONS-TRACKER.md and in the docs/questions/ section it belongs to, and moves the tracker row it came from. Use when the user says "questions", invokes /questions, or asks what decisions are waiting on them.
---

# Questions

The other half of autonomous shipping. The ship loop pushes as far as it can in parallel and PARKS
anything that needs the author; this skill is how the author answers those parked items — **one
question at a time, explanation first, choices only after the author says they are ready**.

The user runs this by saying **questions** (or `/questions`).

## The registry

Parked questions live in ONE place: `docs/trackers/QUESTIONS-TRACKER.md`. An autonomous run that parks a
decision REGISTERS it there (the ship skill's parking rule); a decision that was only mentioned in a
chat message or a checkpoint note is not parked, it is lost. Each entry carries:

```markdown
## Q<N> — <short title>
- **Class:** PRODUCT | TEST INFRASTRUCTURE          <!-- REQUIRED, `Q231` -->
- **Severity:** CRITICAL | MAJOR | MINOR            <!-- REQUIRED, `Q231`. TEST INFRASTRUCTURE is
     MINOR by default, never CRITICAL, and MAJOR only on NAMED evidence it hides a product defect. -->
- **Status:** OPEN | ANSWERED (<date>: <the decision, one line>) | SKIPPED (<date> — will be asked again)
  <!-- STATUS MEANS ANSWERED-OR-NOT AND NOTHING ELSE (the author, 2026-09-19). Never put a routing
       word here — DEFERRED, PARKED, PENDING, MOVED. Routing goes in `Routed:` below, and `Status`
       stays OPEN, because routing is not answering. Guarded by
       test_status_table::test_STATUS_means_ANSWERED_or_not_and_nothing_else. -->
- **Routed:** <`PENDING-TRACKER.md`, <date> — the author's words; not re-asked until pulled back> | omit when it has not been routed
- **From:** <the tracker row / plan / gate that parked it>
- **Scenario:** <2-4 sentences of plain language. Self-contained: the reader has NOT followed the
  work. Gloss every codename ("AT7 — the acceptance gate that wants three clean rehearsals").>
- **Decision required:** <one sentence.>
- **Big picture:** <what each direction means downstream — what gets unlocked, what stays blocked,
  what it costs. Short.>
- **Options:**
  1. <option> (Recommended) — <why, in one line>
  2. <option> — <trade-off>
  3. Skip for now
- **Cost:** <money/time if any; "none" otherwise>
```

> ### ⚠️ EVERY QUESTION DECLARES **CLASS** AND **SEVERITY** — `Q231`, the author, 2026-09-22
>
> *"Going forward every question you ask me me or every research note you want to create needs to say if
> it us a product issue , a test infrastructure and the severity has to be critical , major and minor.
> We seem to be overly focus on minor issues"*
>
> **Two required fields on every entry, and they come FIRST in the §1 snapshot** — before the
> architecture, before the scenario:
>
> | field | values |
> |---|---|
> | **`Class`** | `PRODUCT` — it changes what a user sees, gets or can do · `TEST INFRASTRUCTURE` — it changes only how this repo checks itself |
> | **`Severity`** | `CRITICAL` — shipped code is giving a user a wrong answer, losing data or blocking them, NOW · `MAJOR` — shipped behaviour is wrong or a claimed capability is unreachable · `MINOR` — no user-visible effect |
>
> **`TEST INFRASTRUCTURE` is `MINOR` by default and is NEVER `CRITICAL`.** It reaches `MAJOR` only on
> **named evidence** that it is HIDING a product defect — a suite that does not run, an assertion that
> cannot fail, a guard measuring a corpus that cannot receive the evidence. *"This could mask
> something"* is not evidence; a named instance is.
>
> **A `MINOR` question is NOT asked while a `CRITICAL` or `MAJOR` one is unasked.** §0 orders the queue
> by severity and says the ordering out loud, including how many of each it holds.
>
>
> **⚠️ AND THE ORDERING — the author, same day:** *"Also note always prioritize cimritical then major
> then minor."* **It governs what work is CHOSEN, not only what is asked.** A `MINOR` item is not
> started while a `CRITICAL` or `MAJOR` one is unstarted. **Tie-break inside a severity: `PRODUCT`
> before `TEST INFRASTRUCTURE`.** A BLOCKER is not candidate work — it rides at the severity of the
> **specific named work** it unblocks, and that work must itself be next in the order; *"this `MINOR`
> thing is a blocker"* without naming what it blocks is refused.
>
> **Why the field and not the judgement:** §0 already said *"ordered by impact"* and that did not
> prevent it, because impact was rated by the same pass proposing the work. Measured 2026-09-21/22 —
> eight `TEST INFRASTRUCTURE` plans written while a `PRODUCT`/`MAJOR` defect sat five days.
> [`work-classification.md`](../../../docs/architecture/work-classification.md)

### THREE fields, three different questions — `Status`, `Asking`, `Routed`

They are routinely all three at once, and collapsing any two loses information a guard depends on.

| field | answers | example |
|---|---|---|
| **`Status`** | **has a human ANSWERED the substance?** | `Q15`: *"OPEN — nobody has answered DT7"* |
| **`Asking`** | may it be asked again? | `Q16`: *"SUPPRESSED until the frame is re-shot"* |
| **`Routed`** | where did it GO? | `Q6`: *"`PENDING-TRACKER.md`, 2026-08-22"* |

*(The three examples are historical — Q6/Q15/Q16 closed 2026-09-29 as not relevant; the rule stands.)*

**Why this is a rule and not a preference.** `Status` was overloaded until 2026-09-19: `Q15`/`Q16` used
it honestly for *unanswered*, while `Q6` used it to record a routing decision (`DEFERRED — moved to
pending`). All three had been parked by the author WITHOUT AN ANSWER, yet read as different states —
and the author found the inconsistency by asking why two parked questions were labelled differently.

**`test_plan389_acceptance::test_N9` reads `Status: OPEN` to keep research-99 undelivered**, on the
stated invariant *"a run must not record a judgement nobody made."* A `Status` that can also mean
"routed somewhere" is a `Status` that guard can no longer trust. *(historical — Q6/Q15/Q16 closed 2026-09-29; N9 now pins that DT7 is WITHDRAWN, never ACCEPTED)*

**And none of the three means *waiting on the author*.** A suppressed question cannot be asked; a routed
one has been triaged. `/show` reports that separately — before this split it showed three questions
blocking the author when **zero** actually were.

## `docs/questions/` — where an answer LIVES after it is given

**`docs/trackers/QUESTIONS-TRACKER.md` is the asking QUEUE. `docs/questions/` is the DECISION RECORD.** They are
different jobs and a question touches both. The registry says *what is waiting*; the `docs/questions/` section
says *what was decided, why, and what it constrains* — permanently, after the question has left the queue.

Ruled by the author 2026-09-13, and the reason is concrete: 18 requirements, 5 decisions and 22 follow-up
questions were answered in one sitting and the whole record sat in `docs/trackers/` with no path into the
architecture. **The reasoning behind an answer is longer and more useful than the answer**, and it was
being thrown away every time.

**The loop is defined in [`docs/questions/how-a-question-becomes-architecture.md`](../../../docs/questions/how-a-question-becomes-architecture.md)** — read it
before running this skill. Four rules:

1. **A question is added to the SECTION it belongs to** — a topic document under `docs/questions/` —
   beside the answers it relates to, not to a new file and not only to the registry.
2. **An answer is recorded beside its question**, with the reasoning.
3. **A question that arises DURING coding or implementation goes to the same place.** This is the rule most
   often skipped, and implementation is where the sharpest questions appear.
4. **After every VPS tracker implementation, CONSOLIDATE** — the Q&A becomes an architectural decision
   stated in its own right, with the Q&A kept below it in a `<details>` ledger, never deleted.

**A new section file is created only when a question fits none of the existing ones.** The default is to
add to one that exists.


## Two ways this skill is entered

**1. The author asks** — *"questions"*, `/questions`. Walk the whole queue, §0 onward.

**2. ANOTHER SKILL needs a decision** — most often `vps-upload` step 8, which asks the author before
committing an entry that cannot run unattended. Ruled by the author 2026-09-13: **that ask runs through
this skill rather than being improvised.**

The difference is only where the question comes from, and it changes exactly two things:

- **Skip §0's gather.** The question is handed to you; there is no queue to announce. Register it in
  `docs/trackers/QUESTIONS-TRACKER.md` as you record the answer, not before.
- **Ask only what the calling skill needs**, then return to it. Do not walk the rest of the queue —
  the author asked for a VPS upload, not a question session.

**Everything else is identical, and that is the point.** The snapshot still comes first (§1), the options
still carry a recommendation and a Skip (§2), and **the answer is still recorded in `docs/questions/` and
written into `docs/architecture/` in the same pass (§3)**. An answer given during an upload is exactly as
architectural as one given in a question session — same author, same decision, and the only difference is
which skill was running when it was asked.

## Required behavior

### 0. Gather

*(Skipped when another skill handed you the question — see §Two ways this skill is entered.)*

- Read `docs/trackers/QUESTIONS-TRACKER.md` and collect every entry with `Status: OPEN` or `SKIPPED`.
- **Skip any entry carrying `- **Asking:** SUPPRESSED`**, and say how many you skipped rather than
  listing them. `Status` and `Asking` answer different questions and must not be collapsed into one
  field: `Status: OPEN` means **nobody has answered** — guards read it to keep a research undelivered
  (`test_plan389_acceptance::test_N9` does exactly this for DT7) — while `Asking: SUPPRESSED` means
  **the author declined to be asked again**. An entry is routinely both. Overwriting `Status` to
  record a suppression tells every guard that reads it a human answered when none did, which is the
  failure Q15/Q16 produced on 2026-09-06. *(historical — Q6/Q15/Q16 closed 2026-09-29; N9 now pins that DT7 is WITHDRAWN, never ACCEPTED)*
- **Sweep for unregistered parked items** — tracker Active rows of kind *(decide)* addressed to the
  author, and any "parked for the author" item in recent checkpoint notes — and REGISTER each as a
  new entry before proceeding. The sweep is what makes the registry trustworthy: an item parked
  sloppily still gets asked.
- If nothing is open: say so, show the answered/skipped tally, and stop.
- **Sweep `docs/questions/` for `❓ Open here` items too.** A question recorded in a section
  during implementation is a parked question — it just did not go through the registry. Register
  each one and ask it like any other; the section is where its answer goes back.
- Otherwise announce the queue in one line each ("3 questions: Demo 2's promotion, buying the clean
  rehearsals, …"), **ordered by SEVERITY — `CRITICAL`, then `MAJOR`, then `MINOR`, `PRODUCT` first
  inside a severity** (`Q231`). **Say the counts of each**, and do not ask a `MINOR` one while a
  `CRITICAL` or `MAJOR` is unasked.

### 1. Explain — SNAPSHOT FIRST — then STOP and wait

For the current question, present exactly four things, succinctly:

0. **`Class` and `Severity`** — **one line, before everything else** (`Q231`). *"`PRODUCT` / `MAJOR`"*.
   If it is `TEST INFRASTRUCTURE` and not `MINOR`, name the evidence in the same line.
1. **The architectural snapshot** — **this comes first after that, always.**

   **Pull it through the index.** `docs/architecture/architecture-index-lookup.md` lists every architecture document and what
   it owns — **read the index, pick the document(s) this question touches, read those**. That is what the
   index is for, and it is cheaper and more reliable than grepping the folder. Then check
   `docs/questions/` for the section holding the Q&A behind those decisions.

   Give the author, in a few lines: **what the architecture already decides here**, **which answers this
   question sits beside**, and **what depends on it**. Then say where it lives, as links to both.

   **Why first.** The author asked for this specifically (2026-09-13): *"when I say questions what you will
   give me is that architectural snapshot along with the question and your recommendation."* A question
   without the surrounding architecture is a question the author has to rebuild context for — and rebuilding
   it from memory is how the same thing gets decided twice, differently. **If no section covers it, say so
   in one line and name the section it would create** — that is itself information the author needs.
2. **The scenario** — what led here, in plain language a reader who stepped away for a week can
   follow. No codenames without a gloss, no plan numbers as load-bearing context.
3. **The decision required** — one sentence.
4. **The big picture** — what each direction means: what gets unlocked, what stays parked, what it
   costs. Not the options themselves; the consequences.

**Carry the recommendation into the snapshot turn.** The author asked for the snapshot *"along with the
question and your recommendation"* — so name which way you lean and why, in one line, before the options
appear. The options still wait for §2; what does not wait is the author knowing where you stand.

Then **end the turn**: *"Say **ready** for the choices, or ask me anything about this first."*

- **Do NOT present the options yet.** The wait is the point — the author reads at their own pace,
  and any question they ask first is answered before choices are on the table.
- If the author asks something, answer it (with evidence from the tree where it helps) and wait
  again. Only "ready" (or an equivalent go-ahead, or the author simply answering the decision
  directly) advances to the choices.

### 2. Choices — with a recommendation, and always with Skip

When the author is ready, present the options with the **AskUserQuestion** tool:

- The recommended option FIRST, its label ending in **"(Recommended)"**, its description saying why
  in one line.
- Every other real option with its trade-off in the description.
- **Always include "Skip this question"** as an explicit option — skipping is a legitimate outcome,
  not a failure. (The tool adds "Other" by itself; do not add one.)
- One question per tool call — never batch two decisions into one prompt.

### 3. Record, then advance

After the author chooses:

- **Update the registry entry**: `ANSWERED (<date>: <decision>)`, or `SKIPPED (<date> — will be
  asked again)`. A skipped question stays in next run's queue.
- **RECORD IT IN THE `docs/questions/` SECTION — this is not optional, and it is the step that will be
  skipped if it is not insisted on.** Write the question, the answer **verbatim where the author gave one
  in their own words**, and the reasoning, into the section it belongs to — beside the related answers,
  never in a new file for one question. A one-line `ANSWERED` stamp on the registry is a record that a
  decision happened; it is not a record of the decision.

- **THEN UPDATE THE ARCHITECTURE DOCUMENT — in the same pass, not later.** An answered question is a
  decision, and a decision belongs in `docs/architecture/`:

  - **the document exists** → update it with the decision, stated as a rule the product keeps. Not *"the
    author chose option 2"*; what option 2 **is**.
  - **no document covers it** → **create one**, named for what it owns, and **add its row to
    `docs/architecture/architecture-index-lookup.md`'s index**. An unindexed document is one the next snapshot will not find,
    which defeats the whole retrieval path in §1.

  **Say the honest state in the same sentence** — `⏳ DECIDED <date>, not built` is the usual one at this
  point, and it is a perfectly good state. `✅ built` comes later, with the plan or VPS entry and
  `path:line`. **Do not wait for implementation to write the decision down**: a decision that is made is
  architecture whether or not code exists yet, and the document saying so plainly is what stops it being
  decided again, differently.
- **Update the tracker row** the question came from, if one exists (a *(decide)* row whose answer is
  now on record moves per the tracker skill's rules — decided is DECIDED on the row, with the date).
- **Say what the answer unlocked** in one line ("this un-parks R11's boundary work — plan-able now"),
  then move to the next question. Do not start the unlocked work mid-walkthrough.

### 4. Close

When the queue is empty:

- A short summary table: question → outcome (answered with what / skipped).
- Commit and push the registry + tracker updates (the upload skill's checkpoint discipline applies).
- List the work the session's answers unlocked, and offer — as an offer, not an action — to run
  `ship` over it.

### 5. Close the loop when the implementation lands

**Triggered by a VPS tracker entry completing, not by this walkthrough.** The decision was already written
into `docs/architecture/` at §3. What implementation adds is **evidence**, and the document has to absorb
it:

- **Move the state** — `⏳ DECIDED, not built` becomes `✅ built`, with the plan or VPS entry that built it
  and `path:line` for what now exists. A document still saying *not built* about shipped code is worse than
  no document.
- **Fold in what the build taught you.** If it found the answer right but incomplete, or hit a constraint
  nobody predicted, that belongs in the guideline — **implementation is evidence**, and this is the only
  moment it is cheap to write down.
- **Keep the Q&A ledger** in `docs/questions/`, in its `<details>` block. **Never delete it.** The reasoning
  is what answers the next question, and a guideline with no ledger behind it is an assertion nobody can
  check.

**An architecture document whose state never moved after its work shipped has failed this loop.** Check for
that when the queue is empty (§4), and say so.

## Rules

- **Explanation first, choices second, always.** Never show options in the same turn as the
  scenario; never skip the wait, even for a question that looks trivial.
- **One question at a time.** The loop's whole value is focus.
- **Skip is always on the menu**, and a skip is recorded, never treated as an answer.
- **Self-contained explanations.** The author reads these cold; every codename gets a gloss, every
  cost a number.
- **Never invent a recommendation.** If the parked entry carries one (the ship run usually records
  it), present that; if none exists and the evidence does not support one, say plainly that there is
  no recommendation and why.
- **Answers are recorded verbatim** on the registry — the entry is the durable decision record the
  next autonomous run reads.
- **The snapshot comes before the question, every time.** Not a summary of the question's background — the
  section's decisions as they stand, from `docs/questions/`.
- **Every answer lands in TWO places**: the registry (that it was answered) and the `docs/questions/`
  section (what was decided, and why). One without the other loses half of it.
- **An answered question updates `docs/architecture/` in the SAME pass** — the document if one exists, a new
  one plus its index row if none does. Never deferred to "when it is built": the state field carries that.
- **A new architecture document is INDEXED in `docs/architecture/architecture-index-lookup.md` the moment it is created.** An
  unindexed document cannot be found by the next snapshot, which is the whole retrieval path.
- **Never delete the Q&A ledger** in `docs/questions/` — the reasoning is what answers the next question.
- **Related questions live together.** A new question that touches an answered one goes beside it. Opening a
  new file per question rebuilds the scatter this loop replaced.
