# Handoff — 2026-10-08

**Where the work stands.** plan-01 (the whole Knowledge Acquisition spec, §44 Phases 1–6) is IMPLEMENTED in `ka/`, not yet committed.
`git status` shows everything untracked; `upload` has not been run.

**Verified this session**
- `.venv/bin/python -m pytest -q` → 66 passed (63 in-process with stub LLM + in-memory graph; 3 read-only against the live
  enterprise-os store at `/root/enterprise-os-dev-data/storage/graph_v2`, which skip when unreachable).
- `.venv/bin/python -m ka demo && .venv/bin/python -m ka serve` → Knowledge Console at `/console/`; six pages screenshotted
  headlessly with zero JS errors.
- `ruff check ka` → only E501 long lines remain in src (tolerated per pyproject); no F-class errors.

**Open questions (not yet in QUESTIONS-TRACKER — add via `questions`)**
1. Authentication at the API edge (§42 enforcement).
2. enterprise-os domain writes create a new substructure version — who repins instances, and when?
3. Should `auto_approve_low_impact` default on for the standalone server?

**Next step.** Run `upload` to commit; then `verify` against plan-01 if a formal gate is wanted.
