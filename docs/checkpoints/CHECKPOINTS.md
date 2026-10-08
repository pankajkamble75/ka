# Checkpoints

Dated notes written by `upload` before each push. Newest first.

## 2026-10-08 14:55 UTC — plan-02: access containment, upload/URL safety, visibility protection (research-01 R4 step 1, R5, R6)

**What changed**

- *Security*: new `ka/security.py` — `require_access` dependency (`KA_ACCESS_POLICY` loopback | token | open; loopback peers pass;
  non-loopback peers need `Authorization: Bearer <KA_ACCESS_TOKEN>`; fail closed), `is_safe_url` / `safe_fetch` (loopback, link-local,
  private, reserved, multicast refused; redirects re-checked per hop; `KA_URL_ALLOWLIST`). Settings declared in `ka/config.py`.
- *API* `ka/api.py`: router-level `dependencies=[Depends(require_access)]`; `_read_capped` → 413 over `KA_MAX_UPLOAD_MB` on both upload
  routes; `widen_visibility` on decide / apply / promotion bodies; 409 on refused promotion.
- *Ingestion* `ka/ingestion.py`: `link()` fetches only through `safe_fetch`; a blocked URL is recorded as a FAILED source
  (`blocked: …`) with an audit record, never fetched. `ka/research.py`: the Internet agent skips unsafe URLs and records why.
- *Governance (protected)* `ka/governance.py`: CHANGE_SCOPE refuses to widen visibility unless `widen_visibility=True`, then records
  `GovernanceDecision.visibility_change` (`ka/model.py`). `ka/promotion.py::decide` applies the same rule. `ka/vocab.py`:
  `required_visibility`, `widens_visibility`.
- *Console* `ka/console/app.js`: access-token field under "You", bearer header on every call, 401 toast, "widen visibility" checkbox on
  Apply and re-scope forms.
- *Docs*: architecture §10 step 1 recorded as built; `docs/protected.md` now carries covering tests, re-verify flow and a Verified
  column; README token note; `.env.example`; `docs/questions/knowledge-acquisition.md` (Q1–Q9 parked by ship); `tools/set_status.py`
  (derived set-status table); `e2e/plan02_access_visibility_flow.py` (live flow, shots under `e2e/shots/`, git-ignored).
- *Plan and tests*: `docs/implementation-plans/plan-02.md`; `ka/tests/test_plan02_security_visibility.py` (17 cases; characterization
  landed first as `91325a4`).

**Why**

research-01 found KA unauthenticated on every route, with an uncapped upload body and an unguarded URL fetch, and found that a
re-scope or promotion could silently widen who sees personal knowledge. Plan-02 is the first of the research-01 set; it is the
security floor the later plans (connectors, discovery, EOS publication) build on.

**Verification**

- `pytest ka/tests` (in-process) → 84 passed; `test_plan01_enterprise_os_adapter.py` against the live store → 3 passed; ruff F clean.
- Verify recount: 10/10 deliverables, 9/9 positive, 9/9 negative (N7 regression gate: covering suites byte-identical since 91325a4).
- Code blocks: 8 declared, 10 found (`ka/model.py`, `ka/vocab.py` marked but not declared — scope moved during build; reported).
- Live: public-address probe 401 → 200 with token; loopback 200 without; blocked link to 169.254.169.254; console flow
  `e2e/plan02_access_visibility_flow.py` 4/4 PASS with screenshots.
- Product tests (research-01): PT5 PASS, PT6 PASS; PT1–PT4, PT7, PT8 FAIL awaiting plans 03–08.

**Follow-ups / risks**

- `KA_ACCESS_POLICY=token` default: a deployment behind a reverse proxy sees every peer as loopback — documented in `ka/security.py`.
- This host's `.env` received a generated `KA_ACCESS_TOKEN`; the author must paste it under "You → Access token" once.
- Step 2 of R4 (identity provider, tenant model, retention) is Q4, parked.

**Decisions and questions**

- Plan `plan-02`; research points R4 (step 1), R5, R6 of research-01 → UPLOADED.
- BUILT: `knowledge-acquisition.md` §10 "Security" step 1 — moved from deferred to built with paths (`ka/security.py`,
  `ka/api.py::_read_capped`, `ka/governance.py` CHANGE_SCOPE branch, `ka/promotion.py::decide`).
- Q1 (access policy): recommended option built as the configurable default; the question stays open for the author to confirm.
- RAISED by the ship run and registered (QUESTIONS-TRACKER Q4–Q9; `docs/questions/knowledge-acquisition.md` ❓ Open): Q4 IdP/tenant/
  retention, Q5 search provider, Q6 connectors, Q7 EOS gap routing + grammar endpoint + base key, Q8 console shape, Q9 EOS frontend re-pin.

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
