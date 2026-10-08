---
name: create-research-report
description: Read the user's own research note, review the codebase and README, then write an independent numbered research report (research-XX.md) under docs/research. Use when the user asks to "create a research report", "review my research", "research this", "write your research on my note", or hands over a research document under docs/research and wants an evidence-backed second opinion. This produces research, NOT an implementation plan — for phased plans use create-implementation-plan.
---

# Create Research Report

The user writes a research note describing **what they think the solution should be and how we should
think about the problem**. This skill takes that note, grounds it in the actual codebase, and produces an
**independent** research report — agreeing, disagreeing, or proposing an alternative, with evidence.

## What this is NOT

- **Not an implementation plan.** No phases, no step-by-step build order, no task breakdown. If the
  research concludes and the user wants a build sequence, that is the separate
  `create-implementation-plan` skill. Say so; do not blend the two.
- **Not a rewrite of the user's note.** The deliverable is *your* research. Restating their document back
  to them with better formatting is a failure.
- **Not code changes.** This skill produces a document only — no edits, no refactors.

## Required behavior

1. **Locate the user's note or user research first.** It is the input; without it there is nothing to
   react to.

   **Both kinds live under `docs/user-research/`** — plan-730 (research-192 `R1`, `Q199`):

   | folder | what it holds |
   |---|---|
   | `docs/user-research/notes/` | a note — an observation, a directive, a story, a design instinct |
   | `docs/user-research/user-research-notes/` | the author's own research — a worked argument, not just an observation |

   **`docs/notes/` is still read**, and is the LEGACY location: two notes written before the folder
   existed stay there because a research report cites one by path. `USER-RESEARCH-TRACKER.md` lists
   every document across all three, with the research that cites it **derived** from this report's own
   `Source note:` header (`Q190`).

   **Both kinds become a research report the same way.** There is no separate treatment: a note and the
   author's own research are both grounded in the code, both get a verdict, and both end with the
   numbered `R`-ledger (`Q192`).
   - If the user names or links a file, use it.
   - If they gestured at it ("my research", an IDE selection, "the one I just wrote"), resolve it to the
     most likely file under `docs/research/` — newest by mtime, or the one currently selected/untracked —
     and **state which file you picked** before proceeding.
   - If no such note exists, ask for it. Do not invent one, and do not proceed from the chat message
     alone unless the user explicitly says the chat message *is* the research.
2. **Read the README.** `README.md` at the repo root (plus any module README the note touches). The
   report must be consistent with how the system describes itself.
3. **Review the code before writing a word of the report.** This is mandatory and comes before drafting.
   - Read every module the user's note names or implies.
   - Verify each factual claim in their note against the code. A claim like "X already does Y" is either
     confirmed with `path:line` or contradicted with `path:line`.
   - Read the surrounding architecture docs the note depends on (`docs/architecture/`, `docs/protected.md`,
     related prior reports in `docs/research/`) so the report does not re-litigate settled decisions.
   - **Go through the architecture LOOKUP, not by guessing at filenames.**
     `docs/architecture/architecture-index-lookup.md` lists every architecture document and what it owns —
     read it, pick the documents this note touches, read those. Then read the Q&A behind them in
     `docs/questions/`, which carries **the author's own words** on why each decision went the way it did.
   - **CITE what you find, the same way you cite code.** A decision already made is as much a fact about
     the system as a line of source is:
     - *"this is settled — `docs/architecture/agent-x-orchestration.md` §3, decided 2026-09-13"*
     - *"the author ruled on this at `Q102`"*

     **A report that re-argues a decided question has failed**, and the lookup is what makes that cheap to
     avoid. Equally, **a report may disagree with a decided question** — but it must say it is doing so,
     name the decision and its date, and give the evidence. Silent divergence is the failure; open
     disagreement is the skill's job.
   - **Where the architecture is SILENT, say so.** A question the architecture has never answered is a
     finding worth its own research point (`decide`), and it is how the architecture grows.
   - Fan out with subagents when the surface is large; verify what they return before citing it.
4. **Cite evidence.** Every claim about the current system carries a `path:line` reference. Every claim
   about what *should* happen is labelled as a proposal, not as fact.
5. **Say plainly whether you agree.** The report must take a position. Three allowed verdicts:
   - **Aligned** — the user's direction is right; the research deepens and grounds it.
   - **Aligned with corrections** — the direction holds, but specific claims or mechanisms are wrong;
     name them.
   - **Not aligned** — the direction is wrong or solves the wrong problem; say why, in evidence, and
     present your alternative in full. Disagreeing is expected and welcome — do it respectfully and
     concretely, never vaguely.
6. **When you disagree, deliver the alternative.** A rejection with no alternate research is not a
   deliverable. Give the alternative the same depth as the section it replaces.
7. **Write the file** under `docs/research/` with the next available number (see Naming).
8. **Report back in chat** with the closing summary (see Closing summary).

## Naming

- Directory: `docs/research/` (absolute: `C:\Pankaj\development\enterprise-os-070626\docs\research`).
  Research reports **always** live here — never elsewhere, never in a subfolder.
- File name: `research-XX.md` — the literal word `research`, a hyphen, then the number.
- Next number: scan `docs/research/research-*.md`, extract the numeric suffix (`research-1.md`,
  `research-01.md`, `research-001.md` all count), take the highest, add one. Pad to at least two digits
  (`research-01.md`, `research-09.md`, `research-10.md`).
- If no numbered report exists yet, start at `research-01.md`. Older dated reports
  (`something-2026-07-30.md`) are **not** part of the sequence — ignore them when numbering, but do read
  the relevant ones as prior art.

## Report structure

```markdown
# Research XX - <Descriptive Title>

Created: <YYYY-MM-DD HH:MM local time>
Source note: [<user's research file name>](<relative link, e.g. docs/research/foo-2026-07-30.md>)
Class: <PRODUCT | TEST INFRASTRUCTURE>
Severity: <CRITICAL | MAJOR | MINOR>
Verdict: <Aligned | Aligned with corrections | Not aligned>

## What this research is about

<2-4 paragraphs. The question being researched, in your own words — not a paraphrase of the note's
title. State the problem the user is actually trying to solve, including the part they left implicit.>

## Why it matters

<What breaks, stays broken, or gets more expensive if this is not resolved. Concrete: which flows,
which artifacts, which users. Tie it to real code — `path:line` — not to abstractions.>

## What the code does today

<The grounded baseline, from the code review pass. What already exists toward the user's direction, what
is partially there, and what is absent. Every line cited `path:line`. This section is what makes the
report trustworthy — it is the difference between research and opinion.>

## Architecture this research obeys

<REQUIRED — research-192 `R2`. Step 3 above already tells you to READ these through
`docs/architecture/architecture-index-lookup.md`; **this section is where you RECORD them.** One row per
architecture document this research is constrained by or extends.>

| decision | where | bearing on this |
|---|---|---|
| <the rule, in one line> | `<topic>.md` §N | <constrains R3 / this research extends it / silent — see R5> |

**The same three columns the PLAN template uses**, deliberately: a reader moving between the two stages
should not be re-learning a shape, and `research-192 R3` compares the two sets directly under `Q200`'s
union rule.

**Where the architecture is SILENT, say so here too.** A row reading *"no document owns this"* is a
finding, not a blank — it is how the architecture grows, and step 3 already asks for it in prose.

> ### ⚠️ THE BEARING COLUMN IS READ BY A GUARD — say BUILDS or say CONSTRAINS (`Q222`, 2026-09-21)
>
> **`Q200`'s union rule compares only the documents this research BUILDS or EXTENDS.** A row you are
> merely CONSTRAINED BY — you obey the document and change nothing in it — is out of the comparison, and
> the bearing cell is where that is decided. `tracking/_codelineage.py::research_architecture` reads this
> cell, so write it for a reader AND for the guard:
>
> | you mean | write a phrase containing |
> |---|---|
> | **this research builds or extends it** — counted | *builds it* · *extends it* · *completes it* · *proposes a new row* |
> | **this research is constrained by it** — excluded | *constrains …* · *obeyed* · *`R4` obeys it* · *not touched* · *adjacent* · *the precedent* · *silent* |
>
> **A cell naming neither is COUNTED**, deliberately — a rule that silently stopped firing would be worse
> than one that occasionally over-reports. But it is a worse row: it tells the next reader nothing about
> whether you touched that document. **Measured 2026-09-21**: four rows of research-196 were descriptive
> rather than declarative (*"the principle this research says was applied incompletely"*), and
> `test_plan748_bearing.py::test_D1` pins that count so it is visible when it rises.
>
> **Why this, and not a score.** research-101 `R8` is the precedent: plan-396 proposed a 0.45 relevance
> floor, and its own verify measured the true positive at **0.29** — BELOW the walkover it was meant to
> separate from. A threshold over text cannot split these two populations; the verbs can, because you are
> already writing them.

**Why the RECORD and not just the reading.** Measured 2026-09-20: **1 of 195** reports named its
architecture documents, so `plan ⊆ research` could not be checked even in principle — one side of the
comparison did not exist. The reading was happening; the edge was not.


## Reading of the source note

<Summarize the user's proposal fairly and briefly — enough that a reader who has not read it can follow.
Then, claim by claim:>

| Claim in the note | Verdict | Evidence |
|---|---|---|
| <claim> | Confirmed / Partly true / Contradicted | `path:line` + one line of explanation |

## The research

<The substance. Structure it however the problem demands — a model, a set of options with trade-offs, a
decomposition, an invariant analysis, a comparison of designs. Depth over breadth. This is the section
the report exists for; it should be the longest.>

<Where the note is right, extend it: what it implies that the note did not follow through on. Where it is
incomplete, complete it. Where the note assumes something the code contradicts, work the problem again
from what the code actually does.>

## Where I differ (if anywhere)

<Omit only when in full agreement. Otherwise: what you disagree with, why, and the evidence. Be direct
and specific — "the note routes deletes through Lineage, but Lineage has no write path today
(`path:line`), so this needs X first" beats "this may be difficult".>

## Alternate research (only if Not aligned, or a materially better option exists)

<The alternative, developed to the same depth. State what it buys, what it costs, and under what
conditions the note's approach would beat it.>

## Open questions

- <Genuine unknowns that change the conclusion, and what evidence would settle each.>

## What this does not cover

<Explicit non-goals and anything deliberately left to an implementation plan. Name the plan skill:
implementation phasing belongs in `create-implementation-plan`, not here.>

## Research points (N)

<REQUIRED and LAST. The numbered ledger the next stage reconciles against. See "Research points" below.>

| # | Research point | Kind | Class | Severity | Where argued |
|---|---|---|---|---|---|
| R1 | <one discrete, actionable conclusion> | build \| fix \| decide \| investigate | PRODUCT \| TEST INFRA | CRITICAL \| MAJOR \| MINOR | §<section> |
| R2 | … | | | | |

**Total research points: N.** <One line: how many are `build`, how many `decide`, how many
`investigate`.>

**Class and severity split — REQUIRED (`Q231`).** <One line: how many `PRODUCT` vs `TEST
INFRASTRUCTURE`, and how many `CRITICAL` / `MAJOR` / `MINOR`.> **If every row is `TEST INFRASTRUCTURE`
and `MINOR`, say so plainly in that line** — it is the single most useful sentence the report can carry,
and it is the one this rule exists to force into view.

> ### ⚠️ CLASS AND SEVERITY ARE REQUIRED — `Q231`, the author, 2026-09-22
>
> *"every research note you want to create needs to say if it us a product issue , a test
> infrastructure and the severity has to be critical , major and minor. We seem to be overly focus on
> minor issues"*
>
> **The header carries the report's own class and severity; the `R`-ledger carries one of each PER ROW**
> — because a report is routinely mixed, and the mix is the information. A `PRODUCT`/`MAJOR` row buried
> in six `TEST INFRASTRUCTURE`/`MINOR` ones is exactly what this makes visible.
>
> | class | means |
> |---|---|
> | **`PRODUCT`** | it changes what a user of Enterprise OS sees, gets, or can do |
> | **`TEST INFRASTRUCTURE`** | it changes only how this repository checks itself |
>
> | severity | means |
> |---|---|
> | **`CRITICAL`** | shipped code is giving a user a wrong answer, losing their data, or blocking them — **now** |
> | **`MAJOR`** | shipped behaviour is wrong, or a claimed capability is unreachable |
> | **`MINOR`** | no user-visible effect — throughput, hygiene, record-keeping |
>
> **`TEST INFRASTRUCTURE` is `MINOR` by default and NEVER `CRITICAL`.** It reaches `MAJOR` only on
> **named evidence** that it is HIDING a product defect — a suite that does not run, an assertion that
> cannot fail, a guard measuring a corpus that cannot receive the evidence. A worry is not evidence.
>
>
> **⚠️ AND THE ORDERING — the author, same day:** *"Also note always prioritize cimritical then major
> then minor."* **It governs what work is CHOSEN, not only what is asked.** A `MINOR` item is not
> started while a `CRITICAL` or `MAJOR` one is unstarted. **Tie-break inside a severity: `PRODUCT`
> before `TEST INFRASTRUCTURE`.** A BLOCKER is not candidate work — it rides at the severity of the
> **specific named work** it unblocks, and that work must itself be next in the order; *"this `MINOR`
> thing is a blocker"* without naming what it blocks is refused.
>
> **Order the `R`-ledger by severity too** — `CRITICAL` rows first, `PRODUCT` before `TEST
> INFRASTRUCTURE` inside a severity. A reader should not have to sort it themselves to find what matters.
>
> **Measured 2026-09-21/22, and it is why this is a required field:** research-197 produced eight plans,
> all `TEST INFRASTRUCTURE` and six `MINOR`, while a `PRODUCT`/`MAJOR` defect sat deferred for five
> days. [`work-classification.md`](../../../docs/architecture/work-classification.md)

## Product tests (P)

<REQUIRED. What must be TRUE OF THE PRODUCT once this research is delivered — not what any one plan
builds. See "Product tests" below.>

| # | Product test | Proves | Runnable today? |
|---|---|---|---|
| PT1 | <a capability, stated so it can pass or fail> | R3, R7 | no — needs plan-NN |
| PT2 | … | | |

**Total product tests: P.** <One line: how many can run today, and what the rest are waiting on.>
```

## Research points — the ledger this report owes the next stage

Every report ends with a **numbered ledger of its own conclusions**. This exists because a report's
recommendations are otherwise scattered through prose, and the plan that follows can silently cover three
of them and leave four — which is exactly how work gets lost between stages.

**What counts as one research point.** A discrete conclusion a later stage can act on or explicitly
decline. The unit matters: one point that says "fix the learning loop" is useless, and fifteen points that
each restate a sentence are noise. The test is *"could a plan cover this one and not that one?"* — if two
things always move together, they are one point; if they could be scoped apart, they are two.

- **Only conclusions that survive the report.** A claim you investigated and rejected is not a point.
- **Include the ones you argue AGAINST doing** — as `decide`, with the recommendation. A reader must be
  able to see that "do not build X" was a conclusion, not an omission.
- **Open questions are points too**, as `investigate`. They are the cheapest thing to lose.
- **Number them R1..Rn and never renumber.** If a later report supersedes this one, it cites `R3` and the
  reference must still resolve.
- **State the total explicitly.** `Total research points: N` is the number the plan stage reconciles.

Say the count in the closing chat summary too, so it is visible without opening the file.

### Name WHICH CLAIMS of the source this report covered — `Q199`

**Say, in one line under the `R`-ledger, which of the source document's claims this report addressed and
which it did not.** For example: *"covers 14 of the note's 17 statements; the three on onboarding are
out of scope and named in §What this does not cover."*

**Why this and not numbered claims in the note itself.** `Q199`, 2026-09-20: the user-research tracker's
unit is a FILE, because numbering every claim taxes the AUTHOR's writing rather than the machine's — the
2026-09-20 specification carried 17 and they were counted by hand. **This line is where claims get
counted only when a report actually reconciles against them**, which is what makes the file-level unit
an upgrade path rather than a ceiling: when note volume justifies numbering, it tightens THIS field
instead of requiring a rewrite.

**It is a coverage statement, not a summary.** *"Covers the note"* says nothing. A count and a named
exclusion can be checked against the source.

**Then write them to the tracker.** Add one `OPEN` row per research point to `docs/trackers/RESEARCH-TRACKER.md`
(`From` = this report), per the `tracker` skill. That is what stops a point existing only in a report
nobody re-reads — and it is the file `ship` checks before claiming a set is finished.

## Product tests — what must be TRUE when this is delivered

**A different question from the plan's positive and negative cases, and the reason this section exists.**

```text
positive / negative   does THIS PLAN's change work?     written by the PLAN,   scoped to deliverables
product tests         does the PRODUCT do what this     written HERE,          scoped to a capability
                      research says it should?
```

**The failure this closes.** A set of plans can each pass every one of its own cases while the capability
the research asked for still does not work. The worked example is in this repository: every plan under
research-69 passed its cases, and the coding journey **J5 was unreachable by construction for the life of
the loop** — the router waited for a value the transform could not emit, and **nothing failed**. A product
test saying *"a question whose gap is in the software reaches `commission_coding`"* would have been red for
months. No plan owned the gap, so no plan's cases could see it.

- **Write them as capabilities, not as code.** *"A connector build routes through AX-CODE and returns a
  BuildResult"* — not *"`_subsystem_for` returns `ArtifactSubsystem`"*. The second is a P case.
- **Name which research points each proves.** A product test that proves nothing numbered is either a
  missing research point or not a product test.
- **Say whether it can run TODAY.** Most cannot: they become true on the last plan of the set. Recording
  *"no — needs plan-NN"* is what lets `verify` report a red product test as expected rather than as a
  defect.
- **A product test that would pass BEFORE any plan lands is measuring nothing.** Rewrite it or drop it.
- **Prefer one that can actually be executed.** A live journey, a route, a real call. Where the only honest
  form is manual or paid, say so and name the cost — `verify` will report it as NOT RUN rather than
  pretend.

**The `## Product tests` section is APPEND-ONLY.** Ruled by the author 2026-09-08 (`Q64`). It is not
frozen when the report is written: when a later run opens a research point mid-flight — which is ordinary,
and is how R8-R12 of research-164 arrived — the capability that point delivers gets its product test
**added to this section**, in the report that owns it. Existing entries are never removed; a removed entry
erases the record that a capability was ever checkable, and `test_product_test_lifecycle_plan568::test_P2`
fails on it.

**`verify` runs these for the whole research, not per plan**, and reports a summary. The research is not
delivered while one is red, however green the plan ledger looks.

## Closing summary (in chat, after the file is written)

End the turn with a short summary — not a wall of text:

1. **Verdict** — aligned / aligned with corrections / not aligned, in one sentence.
2. **The two or three findings that drove that verdict**, each with its `path:line` anchor.
3. **The link** to the new report, as a markdown link: `[research-XX.md](docs/research/research-XX.md)`.
4. **`Research points: N`** and **`Product tests: P`** — both totals. For the points, how they decompose
   (e.g. "4 build, 2 decide, 1 investigate"); for the product tests, how many can run today and what the
   rest are waiting on. Say plainly that **one plan will not cover all N** unless N is small, and roughly
   how many plans it implies — this is the number the next stage reconciles against, and stating it here is
   what stops a reader assuming a single `/ship` delivers everything. The product-test figure is what tells
   them whether the capability is checkable yet.
5. If not aligned, one sentence naming the alternative.
6. One line noting that phasing/implementation is a separate step via `create-implementation-plan`, if
   the user is likely to want it next.

## Quality rules

- Read the code **before** drafting. A report written from the note plus intuition is the failure mode
  this skill exists to prevent.
- Never assert an unverified claim as fact. Mark uncertain findings **PLAUSIBLE** and say what would
  confirm them.
- No phases, no task lists, no "Phase 1 / Phase 2" — that is the implementation plan's job.
- Do not soften a real disagreement into agreement. The user asked for an independent view; agreeing by
  default makes the report worthless.
- Equally, do not manufacture disagreement to look rigorous. If the note is right, say it is right and
  spend the report making it sharper.
- Cite `path:line` throughout; a report with no code references has not done the review.
- Do not modify code, and do not create files other than the one report.
