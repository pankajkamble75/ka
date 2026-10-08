# CLAUDE.md

Project instructions for Claude Code in this repository (the Knowledge Acquisition subsystem of Enterprise OS).

## What this repository is

`ka/` implements `knowledge-acquisition-requirements.md`. Read `docs/architecture/knowledge-acquisition.md` before
changing anything: it maps every spec section to a module and names the twelve invariants (§46) and the test that pins each.

## Rules that are not optional

- **Invariant 1.** No code path may read nuggets, sources or evidence to answer a runtime question. Discovery/Research
  mode uses `ka.search` explicitly and says so. `ka/runtime_guard.py` is protected code (`docs/protected.md`).
- **Invariant 2.** Every `ElementChange` carries `props.knowledge_lineage`. Adapters refuse otherwise. Do not add a bypass.
- **Invariant 3.** Never edit a governed `KnowledgeNuggetVersion`'s semantic fields. Create a new version via
  `GovernanceService.propose_revision` / `ingest_candidate(canonical_id=…)`.
- **One governance pipeline.** Research, uploads, corrections and promotions all call `GovernanceService.ingest_candidate`.
  Do not add a second approval path.
- The LLM recommends; a person (or the authority policy, §13) decides. Research agent ids cannot be `decided_by`.

## Conventions (inherited from enterprise-os-070626)

- Tests: `ka/tests/test_plan<NN>_<phase>_<topic>.py`, functions `test_P<n>_<sentence>` (positive) / `test_N<n>_<sentence>` (negative).
  Cite by prefix (`phase3 ::test_N1`). The suite runs with the stub LLM and the in-memory graph; `test_plan01_enterprise_os_adapter.py`
  is read-only and skips when the checkout is unreachable.
- Run: `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check ka`.
- Settings are declared in `ka/config.py`; `config.get("UNDECLARED")` raises on purpose.
- Storage is one JSON file per object under `ka_storage/`; never hand-edit a governed version file.
- Delivery pipeline skills live in `.claude/skills/` (plan → implement → verify → upload; tracker, startup, bye, …) and expect
  `docs/implementation-plans/plan-NN.md`, `docs/research/`, `docs/trackers/`.

## Parallelism

When a task splits into independent pieces, fan out to subagents; verify what comes back before acting on it; one writer per file.
