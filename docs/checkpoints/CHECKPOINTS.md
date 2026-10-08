# Checkpoints

Dated notes written by `upload` before each push. Newest first.

## 2026-10-08 12:11 UTC — plan-01: Knowledge Acquisition subsystem, first upload

**What changed**

- *Package `ka/`* (new, 5.4k lines): `model.py`, `vocab.py`, `repository.py`, `events.py`, `audit.py`, `config.py`, `ids.py`,
  `timeutil.py`, `json_io.py` (objects, vocabularies, JSON store, §38 events, §41 audit, declared settings);
  `ingestion.py`, `extraction.py` (Upload/Paste/Write/Link/Connect; PDF/Word/PowerPoint/spreadsheet/Markdown/HTML extractors;
  LLM or heuristic candidate extraction); `governance.py`, `conflict.py`, `versioning.py`, `scope.py` (the one pipeline,
  §10 relationships, §12 status machine, §13 authority, §24 scope engine); `lineage.py`, `graph_adapter.py`, `graph_impact.py`,
  `graph_change.py` (§15/§20–§22/§39/§40; in-memory adapter with persistence, EnterpriseOSGraphAdapter over GraphStore);
  `research.py` (§16–§17 coordinator, five agents, synthesis); `corrections.py` (§23), `promotion.py` (§25/§30),
  `search.py` (§35), `runtime_guard.py` (§43), `images.py` (numbered screenshots for conversations); `service.py` (composition
  root, dashboards, apply-to-scope, engine status); `api.py` (FastAPI at /api/knowledge-acquisition), `__main__.py`, `demo.py`.
- *Knowledge Console* `ka/console/` (index.html, app.js, styles.css): five tabs — Add knowledge, Knowledge nuggets (Apply to scope),
  Browse by scope, Dashboard, Images — plus nugget / conflict / source / mission / graph-change detail pages.
- *Tests* `ka/tests/` (10 files, 67 in-process + 3 read-only against the enterprise-os store).
- *Docs*: `README.md`, `CLAUDE.md`, `.env.example`, `docs/architecture/knowledge-acquisition.md`, `docs/implementation-plans/plan-01.md`,
  `docs/protected.md`, trackers under `docs/trackers/`.
- *Skills*: `.claude/skills/` — create-implementation-plan, implement, verify, create-research-report, upload, review-code, tracker,
  startup, bye, update, report, show, ship, questions, permission-audit, copied from enterprise-os-070626; permission-log hook; settings.

**Why**

The author handed over `knowledge-acquisition-requirements.md` and asked for the code. Knowledge Acquisition is the learning and
governance subsystem upstream of the Enterprise OS graph: knowledge is acquired and governed first, compiled into the graph second,
and consumed through graph navigation at runtime. The console was then simplified to the four tabs the author described, and an
Images tab added so screenshots can be cited by number in conversation.

**Verification**

- `.venv/bin/python -m pytest -q` → 67 passed (in-process suite). The read-only enterprise-os adapter tests passed earlier this
  session (3 passed, 28s) when run from the enterprise-os interpreter; they skip in the plain suite when the store is unreachable.
- `ruff check --select F ka` → clean. E501 long lines tolerated per pyproject.
- Live server on :8011 with demo data; every tab and detail page rendered in headless Chromium with zero JS errors; a simulated
  paste on the Images tab stored image #1 (then deleted, so the author's first paste is #2).

**Follow-ups / risks**

- Enterprise OS integration is partial: adapter reads verified live, write/rollback paths tested only on the in-memory adapter;
  no "Correct this" button or "Why?" link added to the enterprise-os console frontend; Domain Builder (`founding/composer.py`) and
  the runtime gap path (`pipeline_v2/ask.py` → `act_on_gaps`) not rewired to KA.
- No authentication at the API edge (§42); image OCR and scheduled research not built; search is lexical, not embedding-based.
- Real Anthropic provider path not exercised (stub only this session).

**Decisions and questions**

- Plan: `plan-01` (all six §44 phases). Research points: none — the plan derives from the specification, not a research report,
  so no set-status table applies.
- Questions RAISED (recorded in `docs/trackers/QUESTIONS-TRACKER.md` as Q1–Q3; no `docs/questions/` topic file yet):
  Q1 API authentication (§42); Q2 who repins instances after a domain write; Q3 default for auto-applying low-impact proposals.
- Decisions BUILT: the twelve §46 invariants, each pinned to a test (table in `README.md`); architecture in
  `docs/architecture/knowledge-acquisition.md` §1–§11.
