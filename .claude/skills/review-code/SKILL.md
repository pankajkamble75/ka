---
name: review-code
description: Whole-codebase health audit that reads every module and reports dead code, unused code, duplicate code, fake/stubbed LLM calls, fake/stubbed API calls, unoptimized code, and improper module structure — writing a dated research report under docs/research. Use when the user asks to "review the code", "audit the codebase", "find dead/unused/duplicate code", "find fake LLM/API calls", "find unoptimized code", or otherwise wants a full-repository quality/health review (NOT a diff review — for the current working diff use /code-review).
---

# Review Code — whole-codebase health audit

Produce a rigorous, evidence-backed audit of an **entire codebase** and write it as a research report.
This is a *repository-wide* review, distinct from `/code-review` (which reviews the working diff).

## When to use vs. not

- **Use** for: "review the code", "audit the whole codebase", "find dead/unused/duplicate code", "find
  fake LLM/API calls", "find unoptimized code / improper modules", a health/tech-debt sweep.
- **Don't use** for: reviewing the current uncommitted diff or a PR — that's `/code-review`.

## Required behavior

1. **Do not change code.** This skill produces a *report only* — no edits, no refactors, no deletions.
   If the user later wants fixes, that is a separate, explicit step.
2. **Cover everything.** Enumerate every folder and source file first, then read and understand each
   module's responsibility before judging it. Do not sample — the deliverable claims full coverage, so
   earn it (fan out with subagents for large repos — see Method).
3. **Verify before reporting.** Every finding must survive an adversarial check. A symbol is only "dead"
   if it is unreferenced *including* dynamic use (`getattr`, string dispatch, registries, entry points,
   plugin discovery, reflection, templates, test-only fixtures, public API re-exports). When unsure,
   mark it **PLAUSIBLE** rather than **CONFIRMED** — never assert a false positive.
4. **Write the report** under the repository's research directory (`docs/research/`, at the repo root),
   named `code-review-<YYYY-MM-DD>.md`. Use the local system date.

## Method (be exhaustive, not sampled)

1. **Enumerate.** `git ls-files` (or `find`), excluding vendored/build/`node_modules`/generated dirs.
   Build the folder + module map: for each top-level package, one line on what it does.
2. **Read + understand.** Read the code. For a large repo, fan out: one subagent per folder/module (or a
   pipeline over the module list), each returning structured findings for the categories below. Then
   dedupe and verify centrally. Do not report a finding a subagent surfaced without confirming it.
3. **Detect** each category with concrete heuristics (below).
4. **Verify** each candidate (adversarial pass — grep for every use, check registries/entry points).
5. **Synthesize** the report: rank most-severe first, group by category, cite `path:line`, give evidence
   and a concrete recommendation per finding. Note explicitly what was NOT covered, if anything.

## What to find (categories + detection heuristics)

- **Dead code** — unreachable or never-invoked. Unreferenced functions/classes/modules (grep every use,
  incl. dynamic dispatch + `__all__` re-exports + entry points); unreachable branches after `return`/
  `raise`; files never imported and never an entry point; commented-out code blocks left behind.
- **Contradicts a DECISION** — the category nothing else audits for, and the only one a reader of the code
  alone cannot detect. Read `docs/architecture/architecture-index-lookup.md`, follow it to the documents
  covering the areas you are auditing, and check the code against what each decision says. Three findings
  live here:
  - **code that does the opposite of a decided question** — cite the document, section and decision date
    beside the `path:line`, exactly as you would cite the code;
  - **a decision marked `✅ built` whose cited code is absent or does something else** — the document is
    claiming support the tree does not give, and every later question gets asked against it;
  - **a decision marked `⏳ decided, not built` that is in fact BUILT** — the cheaper direction of the same
    error, and it means agreed work is being counted as outstanding.

  **Report; never edit the architecture document to match the code.** Either the code is wrong or the
  decision has moved, and both are the author's to settle. The reasoning behind each decision is in
  `docs/questions/`, in the author's own words — read it before calling something a contradiction, because
  a decision often covers a case the one-line rule does not state.
- **Unused code** — imported/declared but never used. Unused imports and locals; parameters never read;
  config keys/env vars never consumed; routers/handlers defined but never mounted; feature flags with no
  reader.
- **Duplicate code** — the same logic in ≥2 places. Copy-pasted blocks, parallel implementations of one
  concern (e.g. multiple re-implementations of a retry/fallback/cost loop), near-identical helpers that
  should be one. Report each cluster once with all sites.
- **Fake / stubbed LLM calls** — placeholder model calls masquerading as real. A stub/mock provider (e.g.
  `StubLLMProvider`) wired into a **production** path (not tests); hardcoded/canned model "responses"
  returned in product code; `TODO`/`FIXME`/`pass`/`return ""` where an LLM call belongs; a call that
  never reaches a provider. (In tests, stubs are expected — flag only stubs on live paths.)
- **Fake / stubbed API calls** — endpoints or clients that don't do real work. `NotImplementedError`
  stubs reachable in production; hardcoded/canned HTTP responses; handlers returning placeholder data;
  clients that never issue a request; mock connectors selectable outside tests.
- **Unoptimized code** — avoidable cost. Accidental O(n²) (nested scans, membership tests on lists),
  repeated file/JSON reads or recompiles in a loop, unbounded loads of large data, missing/duplicated
  caching, N+1 patterns, blocking I/O on an async path, needless full-object copies in hot loops.
- **Improper modules ("no proper modules")** — structure/boundary problems. Files that don't belong in
  their package; inconsistent layout across peer modules; circular imports; god-modules doing too much;
  missing `__init__`/exports; leaky boundaries (a module importing across a declared seam); stale/renamed
  module references in code or docs.

## Report structure

```markdown
# Code Review — <repo name>

Date: <YYYY-MM-DD>
Scope: <N files across M packages> — <what was covered; note any exclusions>

## Executive summary
<3–6 sentences: overall health, the few highest-impact findings, headline counts per category.>

## Findings by category

For EACH of: **Contradicts a decision** · Dead code · Unused code · Duplicate code · Fake LLM calls ·
Fake API calls · Unoptimized code · Improper modules —

**Put *Contradicts a decision* first.** It is the category with the highest cost per finding — the others
make the code worse, this one makes the code *wrong about what it was asked to be* — and it is the one a
reader skimming the report most needs to see.

| # | Location (path:line) | Verdict | What & why | Recommendation |
|---|---|---|---|---|
| … | `pkg/mod.py:120` | CONFIRMED / PLAUSIBLE | one-line defect + evidence | concrete fix |

(Empty category → say "None found" explicitly — don't omit it.)

## Prioritized remediation
<Ranked list: highest value / lowest risk first, grouped into quick wins vs. larger refactors.>

## Coverage & method
<How the review was run (modules read, subagents used), and anything NOT fully covered.>
```

## Quality rules

- Evidence over assertion: every finding has a `path:line` and a reason someone can verify.
- No false positives: prefer PLAUSIBLE to a wrong CONFIRMED; account for dynamic/reflective use.
- Severity-ranked, deduped, actionable. Distinguish "test stub" (fine) from "stub on a live path" (bug).
- Report only — never modify code. Do not claim a fix was made.
- State the coverage honestly (which folders/modules were read; what was sampled or skipped and why).
