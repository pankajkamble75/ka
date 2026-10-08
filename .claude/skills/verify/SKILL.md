---
name: verify
description: Post-implementation verification gate. Run after EVERY implementation. Confirms the implementation plan is fully implemented (completing anything pending), that positive AND negative tests exist, run, and pass (writing+running missing negative tests), that any protected code followed the before/after test protocol, that the live-browser click-through passes with verified screenshots, and that the upload skill was run (commit all + push to main). Use when the user says "verify", "confirm implementation", "run verification", or right after finishing an implementation plan.
---

# Verify

The gate that runs **after every implementation**. It does not just report — it **closes gaps**: it finishes
pending plan items, writes missing negative tests, fixes failing tests, enforces the protected-code protocol,
runs the live browser click-through, and makes sure the work was uploaded. Only when everything below is
green is an implementation "verified".

Never fabricate a result. If something cannot be made to pass, stop and report the exact failure — a red
result honestly reported is the correct outcome, a green result invented is a defect.

## 0. Identify the target plan

- The implementation plan under `docs/implementation-plans/plan-NN.md` that was just implemented. Use the one
  the user names; otherwise the highest-numbered plan whose work matches the recent commits / current diff.
- Read the WHOLE plan: its Phases, `Positive Test Cases`, `Negative Test Cases`, and
  `Protected-code impact` section. Everything below is checked against it. If you cannot identify the plan,
  ask which one before proceeding.

## 1. Plan completeness — recount independently, then implement anything pending

- **Recount from the artifacts; do not trust `implement`'s report.** The whole value of this stage is being
  an independent check. Take `m` / `i` / `j` from the plan's `## Plan totals` and establish YOUR OWN count
  of what exists.
- For every deliverable D1..Dm, confirm it actually exists in the code (read/grep the named file, function,
  route, contract). For every case P1..Pi and N1..Nj, find the test that covers it, by name.
- **Complete every PENDING item** following the plan (same design, same file targets). A protected-touching
  pending item follows §4. Do not mark the plan verified while anything the plan promised is missing.
- **Reconcile the research ledger too.** If the plan has a `## Research coverage` section, check that every
  R1..Rn still has a row and that the ones marked in-scope were actually built. A point that was silently
  dropped between the report and the plan is exactly the leak this pipeline numbers things to catch — say
  so, and say which plan is supposed to pick it up.
- **When this plan is one of a SET, verify THIS plan fully and report the set's state.** Do not mark a
  sibling verified because it shares a report — each gets its own pass, its own live gate and its own
  upload. But do say, in one line, which siblings are shipped, which are **written but not started**, and
  which are halted. A plan file that exists with no implementation reads as done to anyone skimming the
  directory, and that is the specific confusion this line prevents.

## 2. Positive AND negative tests exist, run, and pass

- Locate the tests backing the plan's `Positive Test Cases` and `Negative Test Cases`.
- **Positive tests:** confirm they exist and cover each listed case. Run them.
- **Negative tests:** confirm they exist and were run. **If there were no negative tests** (or they don't
  cover the plan's listed negative cases): **write the missing negative tests**, add them under the plan's
  `Negative Test Cases` section (as the concrete test names/paths) AND as real test code, then run them.
  Negative tests must cover the guardrails the change makes — invalid input, failure isolation, cancellation,
  budget/opt-out paths, and every guarantee the changed code makes to its callers.
- **Before starting a full-suite run, make the tree STILL — commit, or at least stop editing.** The run
  collects at start but keeps reading source for its whole 20-25 minutes, and a change landing underneath
  it yields a red result that looks exactly like a regression and means nothing. Measured 2026-09-05:
  `test_plan525_extraction::test_C2` failed that way and passed **16 of 16** in isolation; the run was
  discarded and re-run on a committed tree. **A run that straddled an edit has nothing to say** — never
  record its counts, and never chase its failures. The tell is that they do not reproduce in isolation.
- Run the full relevant suites (backend `pytest` for the touched areas + the plan's covering tests; frontend
  `vitest` + `tsc` if the plan touched the FE). Record suite names and pass/fail counts.
- **"Relevant" means the TOUCHED areas, not all 9,000+ tests.** Add the cheap guard sets — the tracker,
  reconciliation, research-index and product-test-lifecycle audits run in seconds and are the most
  frequent red in this repo. **Inside a VPS queue run the whole-suite gate belongs to the QUEUE, once,
  after its last entry** (`vps-download` §1a, ruled as `Q75`); do not start a 25-minute run per plan.
  Outside a queue, run it once before the session's final push.

**Every deliverable is tested through every method that reaches it.** A case-by-case map is not enough on
its own — for each deliverable D1..Dm, ask how the code can actually be entered, and confirm each entry
point is exercised:

- a **function** — called directly, and through whatever public surface wraps it;
- a **route** — the handler *and* the HTTP layer (status codes, the 404/422 path, not just the happy body);
- a **UI component** — every branch that renders it, including the fallback/degraded path. A field carried
  by a server path and a client-derived path needs BOTH tested; one of them is usually the one nobody runs;
- a **subscriber or hook** — invoked directly, and fired through the real dispatch;
- anything with **conditional behaviour** — each branch, plus the malformed-input path.

Where a deliverable has an entry point with no test, **write it in this pass**. Where one genuinely cannot
be reached in tests (a live model call, a browser-only API), say which and why rather than leaving the gap
implied.

## 2a. CODE BLOCKS — declared vs found

If the plan has a `## Code blocks` table, reconcile it the same way as the deliverables:

```
/root/.venvs/enterprise-os/bin/python -c "
from knowledge_worker.tests._codeblocks import scan
for b in scan(): print(b.plan, b.path, b.start_line, b.end_line)"
```

| outcome | what it means |
|---|---|
| declared and found | ✅ |
| **declared, NOT found** | the plan promised a marked region and the build did not write it — report as MISSING by number, exactly like a missing deliverable |
| **found, NOT declared** | the build marked a file the plan never named. **Report it**; it is the signal that scope moved during the build, and it is a finding rather than a tidy-up |

**⚠️ RUN THE GUARD, do not only eyeball the scan — 1.75 s:**

```
.venv/bin/python -m pytest -q knowledge_worker/tests/test_plan720_blocks_are_emitted.py
```

**Measured 2026-09-20, and it is why this line exists.** `implement` §3b already said *"every code which
is written should be marked with blocks"* and this section already said to reconcile the table — and a
queue still declared three blocks, wrote **none**, and closed all three entries reporting full
deliverable counts. **The miss survived both instructions and surfaced 39 minutes later at the
end-of-queue gate.** A reconciliation a human performs by reading is one a tired run performs by
assuming; the guard cannot be assumed.

**Both directions matter.** A declaration with no code and code with no declaration are different
defects, and a check that only looks one way sees half of them.

## 2b. PRODUCT tests — does the PRODUCT do what the research said it should?

**A new category, and it answers a different question from the other two.**

```text
positive / negative   does THIS PLAN's change work?        owned by the PLAN,     scoped to deliverables
product tests         does the PRODUCT do what the         owned by the RESEARCH, scoped to a capability
                      research said it should?
```

**Why this exists.** A set of plans can each pass every one of its own cases while the capability the
research asked for still does not work. This repository has the worked example: every plan under
research-69 passed its cases, and the coding journey **J5 was unreachable by construction for the life of
the loop** — `loop_next` could not emit `"coding"`, the router waited for a value nothing produced, and
**nothing failed**. A product test asking *"can a question reach `commission_coding`?"* would have been red
for months. P/N cases could not see it, because no single plan owned the gap.

### Where they come from

**The research report defines them** (`create-research-report` writes a `## Product tests` section), and
**each implementation plan carries the ones its points serve** in its `## Research coverage` table. So a
product test names the research point it proves, not the deliverable it exercises.

### Running them

- **Locate them from the RESEARCH report**, not only from the plan — a plan covering 2 of 9 points may
  serve a product test that also needs the other seven.
- **Read the CURRENT list, not the one the report shipped with.** The `## Product tests` section is
  **append-only** (author's ruling 2026-09-08, `Q64`): a capability delivered mid-set has its test appended
  to the report that owns it, so a report written with four tests may now hold six. Run what is there today.
- **Run every product test for the research the plan belongs to**, not just the ones this plan touches.
  That is the whole point: the capability is what is being checked, and the last plan of a set is where it
  becomes true.
- **A product test may legitimately FAIL until the last plan of the set lands.** That is expected and is
  **reported, never hidden** — see the summary below. A run that suppressed it would recreate exactly the
  silence this category exists to break.
- **A product test that passed BEFORE any plan landed is measuring nothing.** Say so; it is a defective
  test, not evidence.
- Where a product test cannot run in this environment (a live model call, a browser, a paid journey), name
  it and the exact prerequisite. **A gate that did not execute has not passed** — the same rule as §5.

### The summary — REQUIRED, and it is per RESEARCH, not per plan

```
Product tests — research-NN (7 defined)
  PT1  can a question reach commission_coding?      FAIL   R7 — needs plan-244 (not yet landed)
  PT2  a connector build routes through AX-CODE     PASS   R5
  PT3  every LLM call reaches the governed spine    PASS   R7, R8
  …
  4 PASS · 2 FAIL (both awaiting plan-NN) · 1 NOT RUN (no provider key)
```

Every line carries **the research point it serves** and, for a failure, **what would make it pass**. A
failing product test with no explanation is indistinguishable from a broken one.

**The research set is not delivered while a product test is red**, even when every plan's own cases pass.
Say that plainly in the report and on the tracker row rather than letting a green plan ledger imply a
working capability.

## 3. All tests must pass — fix failures

- Every test run in §2 must pass. **For any failing test, try to correct it:** fix the product code when the
  code is wrong; fix the test only when the test itself is wrong (never to paper over a real defect).
- Re-run after each fix until green. If a failure cannot be resolved, stop and report it with the exact
  output — do not weaken assertions to force green.
- Distinguish PRE-EXISTING failures (fail on the base commit too, unrelated to this plan) from regressions:
  verify against the base if unsure, and report pre-existing ones as such rather than "fixing" unrelated code.

## 4. Protected code — before/after test protocol

- From the plan's `Protected-code impact` section and `docs/protected.md`, list the protected areas this plan
  touched (a protected file OR one of its listed shared dependencies).
- For EACH protected-touching change, confirm the protocol was actually followed:
  1. **Characterization ran BEFORE the change** — tests that pinned the CURRENT behaviour at the seam, green
     against unchanged code, ideally in their own commit. If these are missing, **write them now**, and
     confirm (via git history or by reasoning about the change) that they characterize the pre-change state.
  2. **The area's existing covering tests pass UNMODIFIED after the change** — run every covering test listed
     in `docs/protected.md` for that area and confirm none needed its assertions edited. If a protected test
     would need editing to pass, that is a regression to **escalate**, not to edit.
  3. **The `Verified:` date in `docs/protected.md` was bumped** for that area, in the change's commit, with an
     honest re-verify note. If not bumped, bump it now with what was re-verified.
- The net requirement the user stated: there are tests that run BEFORE touching the protected code and the
  SAME tests run AFTER, and they all pass. Make that literally true.

## 5. Live browser click-through + screenshots

- Run the live end-to-end harness — **Chromium via Playwright hitting the real backend + Vite** (the project
  harness at `e2e/run.sh`; if the plan added its own flow, run that). Prereqs, once per environment:
  `pip install uvicorn playwright httpx python-multipart` and `( cd knowledge_worker/frontend && npm ci )`.
  Chromium comes from `/opt/pw-browsers` on the Linux image (do not run `playwright install` there); on a
  dev machine run `python -m playwright install chromium` once. See `e2e/README.md`.

- **A change with NO user-facing path is proved at the SEAM, and SAYS SO** — `Q150`, the author,
  2026-09-17. Where nothing a user can reach exercises the change — internal routing, a field a run
  records, a warning a cap now emits — prove it at the seam that produces the behaviour and write §5 as
  **"no flow exercises this; proved at `<seam>`"**, with the reasoning. **Never silently, and never by
  omitting the section.** A §5 that simply has no gate has skipped one, not used this rule.

  **This is narrow and does not touch the ordinary case.** plan-694's `PT1` and plan-695's `PT4` were both
  proved by live click-throughs at $0.13-0.32 because a user could reach them, and that remains the norm.
  It also does not license running an unrelated flow and recording a PASS — the prohibition below stands.
  Measured cause: three plans in one day changed behaviour no browser could reach, and one of them
  (plan-697) could only be reached live by re-creating a bug plan-694 had deliberately removed. Reasoning
  in [`docs/questions/verification-cadence.md`](../../../docs/questions/verification-cadence.md) `Q150`.

- **This gate cannot be skipped by being unable to run it.** The preamble's rule applies here in full:
  *if something cannot be made to pass, stop and report the exact failure.* Two distinct cases, with
  different correct responses — diagnose which one you are in before doing anything else:

  - **No flow exercises what this plan changed.** Do **not** run an unrelated flow and record a PASS.
    `e2e/run.sh` drives the plan-59 delete flow; a green table from it says nothing about the plan under
    verification, and is worse than a halt because it *looks* like evidence. **Write the missing flow** —
    model it on `e2e/browser_harness_mode_flow.py`, assert what the plan actually changed, and add it to
    `e2e/`. That is part of closing the gap, which is this skill's job.
  - **The environment cannot run a browser** (no `playwright` module, no Chromium). Name exactly what is
    missing and the command that fixes it. Then either it gets installed and the gate runs, or **§5 FAILS**
    — record it as a failure with the reason, and say so in the report and the checkpoint. Do not
    auto-install a browser runtime on someone's machine as a side effect of verifying.

  A gate that did not execute has not passed. Never write "click-through performed" for a run that did not
  happen, and never let an unrunnable §5 pass silently into §6.
- **Store the screenshots** (the harness writes them to `e2e/shots/`). Capture the key screens of the flow.
- **Verify the screenshots:** each expected screenshot exists and is non-empty, AND open/read them to confirm
  they show the expected UI state (e.g. the dialog/text the plan introduced). A missing, empty, or
  wrong-content screenshot is a failure — fix the flow or the product and re-run.
- Every assertion in the click-through must pass. Report the PASS/FAIL table.
- Running under an agent/CI shell: launch the harness **detached** (background) and poll its log — a
  foreground supervising shell can kill the long-lived servers. Never free ports with `pkill -f` (a broad
  match can hit the supervisor); kill by PID (`ss -ltnp 'sport = :5174'`).

## 5b. The ARCHITECTURE is part of what is verified

A plan that built a decided question leaves that decision's document behind unless something checks. Before
the upload:

- **Did this plan build a decision marked `⏳ DECIDED, not built`?** Its state moves to `✅ built` in
  `docs/architecture/<topic>.md`, with the plan number and `path:line` for what now exists. **A document
  still saying *not built* about shipped code is worse than no document**, because a reader trusts it.
- **Did the build raise a question?** Confirm `implement` §4b actually recorded it — in the topic's
  `❓ Open` block **and** `docs/trackers/QUESTIONS-TRACKER.md`. A question carried only in the implement report dies
  with the report.
- **Did the build contradict a decision?** That is not a verification detail to smooth over — name it in
  the report with the document and date. Either the code is wrong or the decision has moved, and both are
  the author's to settle.

Find the documents through `docs/architecture/architecture-index-lookup.md`; the reasoning behind each is
in `docs/questions/`. **This is a check, not a rewrite** — verification does not decide architecture, it
reports where the tree and the architecture disagree.

## 6. Ensure the work was uploaded

- The implemented + verified work must be committed and pushed. Confirm the `upload` skill was run: the
  working tree is clean and `main` is not ahead of `origin/main`.
- **If verification changed anything** (completed a pending item, added negative tests, fixed a failure,
  bumped a Verified date) OR the tree is dirty / ahead: **run the `upload` skill** now (it writes a detailed
  checkpoint note, `git add -A`, commits, and pushes to `main`). Verification is not done until the verified
  state is on `origin/main`.

## 7. Report

**Open with the reconciliation table — the numbers, independently counted.** It is the first thing the
reader needs and the last thing anyone writes if it is optional:

```
                      plan     found    note
Research points        N      X in scope   (R5, R6 deferred to plan-NN)
Deliverables           m        m         all present
Positive cases         i        i         P1..Pi mapped to tests
Negative cases         j        j         N3 written during verify
Product tests          p      q PASS      per RESEARCH, not per plan — 2 FAIL awaiting plan-NN
Entry points           —       k of k     every method reaching D1..Dm exercised
```

**The product-test row is per RESEARCH and may legitimately show failures** — a capability becomes true on
the last plan of a set, not the first. A red product test beside a green plan ledger is the honest state
and must be shown, not smoothed.

**A mismatch is the headline.** Do not bury `7 of 9` under a green table — lead with it, name the missing
items by number, and either close them in this pass or say plainly that the plan is not verified.

Then the rest:
- plan completeness (DONE vs items completed during verify);
- positive/negative test results (suite names + counts; note any negative tests written this pass);
- **the product-test summary** (§2b) — every test, the research point it serves, PASS/FAIL/NOT RUN,
  and for each failure what would make it pass. **Required whenever the research defines any.**
- protected-code status (areas, before/after protocol satisfied, Verified date bumped);
- **architecture status** (§5b) — decisions whose state moved to `✅ built`, questions the build raised and
  where they were recorded, and any place the tree and a decided question disagree;
- live click-through (PASS/FAIL table) + screenshots verified;
- upload status (commit hash on `origin/main`).
Keep it tight; the detail lives in the plan, the tests, `docs/protected.md`, and the checkpoint note.

## Rules

- **Run after every implementation.** This is the standard closing gate.
- **Count independently.** Reusing `implement`'s numbers makes this stage a formality; the point is that a
  second count can disagree.
- **Run the PRODUCT tests for the whole research, not just this plan's points.** A capability is what
  they measure, and it becomes true on the last plan of a set. A green plan ledger beside a red
  product test is the honest state — report it; the research is not delivered until it is green.
- **A product test that passed before any plan landed is measuring nothing.** Say so rather than
  counting it as evidence.
- **Never fabricate** test, screenshot, or verification results — including a count. An unreconciled
  ledger reported honestly is the correct outcome.
- **Never weaken a protected test** to make it pass — escalate instead.
- **Complete, don't just report:** pending plan items, missing negative tests, and fixable failures are
  addressed in this pass, not deferred.
- End by ensuring `upload` ran, so the verified state is on `main`.
- **Update the tracker**: this plan's row → `VERIFIED`, Note carrying the gate result. Recount from the
  artifacts as always — the tracker is a claim, never evidence. **If a row disagrees with the tree, correct
  it and say so in the report**; a tracker quietly fixed is a tracker nobody can trust.
