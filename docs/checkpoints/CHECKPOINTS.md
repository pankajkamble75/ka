# Checkpoints

Dated notes written by `upload` before each push. Newest first.

## 2026-10-08 18:40 UTC — plan-07: discovery before fetching — provider seam, allow-list and robots budget, provenance on every page (research-01 R9)

**What changed**

- *Discovery* `ka/discovery.py` (new): `SearchResult`, `SearchProvider` protocol, `NullSearchProvider`, `FixtureSearchProvider` (JSON
  file; exact query then token overlap), `select_provider` (unknown value fails closed to `none`), `canonical_url` (fragments and
  tracking parameters dropped, host lowercased), `RobotsCache` (per host, through plan-02's `safe_fetch` resolved at call time;
  unreachable = allowed, recorded), `DiscoveryAgent` (queries from objective + questions; dedupe → allow-list → URL guard → robots →
  overlap ranking → per-mission budget; every skip with its reason; gate off = no network at all, selections recorded as skipped).
- *Research* `ka/research.py`: `AgentContext.discovered`; discovery first in the coordinator; the Internet agent fetches the selection
  (plus explicit URLs) with provenance metadata. `ka/ingestion.py::link(metadata=)` stamps `retrieved_at`. `ka/model.py`:
  `ResearchRun.discovery`. `ka/config.py`: six settings. `ka/service.py`: provider + gate on the dashboard (one line).
- *API/console* `ka/api.py`: `GET /research/providers`. `ka/console/app.js`: discovery table on the mission page; Dashboard line.
- *Docs/tests*: architecture §6 paragraph; `.env.example`; `plan-07.md`; `ka/tests/fixtures/search_fixture.json`;
  `ka/tests/test_plan07_discovery.py` (15 cases, network patched); `e2e/plan07_discovery_flow.py` + `e2e/search_fixture_live.json`.

**Why**

research-01 R9: a general research question produced only model recollections; URLs had to be named up front. Discovery turns the
question into search, selects responsibly (allow-list, robots, budget, URL safety) and hands fetching to the guarded agent, so an
internet-sourced candidate carries a canonical URL, publisher, retrieval time and the query that found it — and a model answer never
poses as one (authority `LLM_GENERATED` vs `INTERNET_RESEARCH`). The provider itself stays the author's decision (Q5).

**Verification**

- `pytest ka/tests` (in-process) → 165 passed; EOS path (unchanged areas) → 7 passed; ruff F clean. Verify recount: 9/9 deliverables,
  9/9 positive, 7/7 negative; blocks 7/7, plus one unmarked one-line field in `ka/service.py` (finding).
- No protected code touched (diff confirmed).
- Live: server with the fixture provider and the gate OFF; `e2e/plan07_discovery_flow.py` 5/5 PASS; screenshot verified (mission page
  with the discovery table: provider, queries, publisher, skips).
- Product tests (research-01): **PT7 PASS** (this plan, with the fixture provider and patched fetches); PT1–PT6 PASS; PT8 FAIL (plan-08).

**Follow-ups / risks**

- PT7 is green with the fixture provider; against a real provider it waits on Q5 and a key.
- Robots are honoured only when the gate is on (a gate-off run makes no network calls by design).

**Decisions and questions**

- Plan `plan-07`; research point R9 → UPLOADED.
- BUILT: `knowledge-acquisition.md` §6 "Discovery" paragraph. RAISED: none new; Q5 remains parked.

## 2026-10-08 17:50 UTC — plan-06: the process profile — composed, evidence-linked, with coverage and the unknowns (research-01 R12)

**What changed**

- *Profile* `ka/profile.py` (new): `ProfileField`, `Activity`, `ProcessProfile`; `ProfileService.profile(key)` composes ACTIVE assertions
  by predicate (description, type with binding status, activities in document order, actors/inputs/outputs/entities/rules/events/states/
  related), every field with nugget ref, evidence spans and `published_as`; PENDING/CONFLICT listed apart; identical ACTIVE assertions
  compose once (`also`, `counts.duplicates`); `coverage(profile)` against the bound type's required/recommended slots from EOS's slot grammar
  (never filled in); `list_processes(scope)` lists subjects with ≥1 ACTIVE assertion in the scope chain.
- *Service/API* `ka/service.py`: `profiles`, `process_profile`. `ka/api.py`: `GET /processes`, `GET /processes/{key}` (404 for unknown or
  non-process subjects).
- *Console* `ka/console/app.js`: `processProfileView` (description, type pill, coverage table, ordered activities with links to child profiles,
  field cards, pending, published-as), `processesList`, "Processes" mode in Browse by scope, subject page delegates for process subjects.
- *Protected correction* `ka/graph_change.py::apply`: retires only prior versions of the SAME canonical id on a shared element, so an element
  composed from several assertions keeps every nugget's dependency (Invariants 4/5). Characterization `00fd176` (defect pinned) → fix →
  covering suites unmodified → `docs/protected.md` bumped.
- *Docs/tests*: architecture §8 paragraph; README row; `plan-06.md` with both corrections; Q11 parked (questions document + registry);
  `ka/tests/test_plan06_profile.py` (14 cases); `e2e/plan06_profile_flow.py`.

**Why**

research-01 R12 / note REQ-012 "Processes": a reviewer needs to see what KA knows about a process as a profile with its gaps, not as a
list of rows. The profile is a query over governed versions, never a stored object; it is the surface where PT1's claims are visible.

**Verification**

- `pytest ka/tests` (in-process) → 150 passed; EOS-path suite (EOS interpreter) → 7 passed after the lineage correction; ruff F clean.
  Verify recount: 7/7 deliverables, 8/8 positive, 7/7 negative; blocks 4/4 plus the declared protected correction.
- Live: `e2e/plan06_profile_flow.py` 6/6 PASS; screenshots verified (Processes list; profile with coverage).
- Product tests (research-01): PT1–PT6 PASS; PT7 FAIL (plan-07), PT8 FAIL (plan-08).

**Follow-ups / risks**

- Duplicate ACTIVE assertions are composed once in the profile but still exist as governed versions (Q11).
- Activity order is nugget creation order; on a store where activities were published by several documents the order is the union's.

**Decisions and questions**

- Plan `plan-06`; research point R12 → UPLOADED.
- BUILT: `knowledge-acquisition.md` §8 "The process profile" paragraph.
- RAISED: Q11 — approving a candidate flagged `duplicate_of` an ACTIVE nugget — recorded in `docs/questions/knowledge-acquisition.md`
  and `QUESTIONS-TRACKER.md`. Q8 (tab shape) remains parked; the profile lives inside Browse by scope.

## 2026-10-08 16:45 UTC — plan-05: publish through EOS — ChangeOps by canonical identity, idempotent (research-01 R1, R2 last clause, R7 KA half)

**What changed**

- *Compiler → emitter (protected)* `ka/graph_change.py`: `element_id_for` (subject kind prefix + canonical key; child process
  `p.<parent>.<child>`), `emit_ops` (ops on the canonical element; `process_type` and edges only from `bound` bindings; object nodes
  created with lineage; edge ids with a realized endpoint write `/` as `~`), `to_change_ops` (EOS `ChangeOp` dicts),
  `idempotency_key_for` (refs + element ids; a live match is returned by `propose_for`), `apply` publishes through `adapter.publish`
  and records `eos_proposal_id / eos_status / new_version / pinned_instances` (repin reported, never done — Q2), refusal and
  `stale_base` → FAILED with the code; `rollback` publishes `inverse_changes`; auto-approved proposals under EOS wait unless
  `KA_EOS_AUTO_ACTOR` names a person. Statement-only nuggets keep plan-01's compilation (`_statement_changes`).
- *Adapters* `ka/graph_adapter.py`: `PublishRefused`, `PublishResult`; protocol `publish / base_version / resolve_element_id /
  edge_target_kind / needs_named_actor`; in-memory publish = validate + apply (rollback applies the inverse without the lineage
  gate); `EnterpriseOSGraphAdapter.publish` through `proposals.py` (INSTANCE → `propose_instance_change` → `approve` → `apply`;
  DOMAIN → `propose_promotion(base_version)` → `request_approval` → `approve` → `apply`), `process_type` omitted under an untyped
  structure with a note; `apply_change` / `rollback_change` retired (`NotImplementedError`).
- *Model/config* `ka/model.py`: `ElementChange.op/edge`; `GraphChangeProposal` publication fields. `ka/config.py`: `KA_EOS_AUTO_ACTOR`.
- *Console* `ka/console/app.js`: Publication card on the graph-change page (content key, EOS proposal + status, base → new version,
  pinned instances with "repin required (Q2)", notes, ops).
- *Docs/tests*: architecture §5 rewritten; `docs/protected.md` row names `publish` and the EOS test; `plan-05.md` (with the survey
  correction note); `ka/tests/test_plan05_publication.py` (14 cases; characterization `60ed811`), `ka/tests/test_plan05_eos_publication.py`
  (7 cases, EOS interpreter, temp typed store, HOTL human); `e2e/plan05_publication_flow.py`.

**Why**

research-01 §1 and §Why-it-matters 1: KA minted graph ids from title slugs and wrote into EOS directly, bypassing the proposal
lifecycle EOS already runs. Now identity is the subject's canonical key, publication is EOS's own propose → approve → apply under
the approver's name, a stale base is a refusal KA records, and a retry returns the live proposal.

**Verification**

- `pytest ka/tests` (in-process) → 136 passed; EOS-path suite from the EOS interpreter → 7 passed; read-only adapter tests → 3 passed;
  ruff F clean. Verify recount: 10/10 deliverables, 12/12 positive, 9/9 negative; blocks 5/5, none undeclared.
- Protected: characterization `60ed811` before the change; covering suites byte-identical; Verified date bumped. P7a rewritten
  post-change as the contrast (pre-change photo in 60ed811).
- Live: `e2e/plan05_publication_flow.py` 4/4 PASS; screenshot verified.
- Product tests (research-01): **PT2, PT3, PT4 PASS** (this plan), PT1 (plan-04), PT5, PT6 (plan-02) PASS; PT7 FAIL (plan-07), PT8 FAIL (plan-08).

**Follow-ups / risks**

- Domain publications leave instances pinned to the old version; nothing repins (Q2). The proposal lists them.
- Under HOTL `auto`, EOS applies at propose time with actor `hotl:auto`; KA still records the KA approver. The EOS tests run `human`.
- Statement-only nuggets still compile to slug ids (`r.<slug(title)>`); out of R2's scope, noted in the plan.

**Decisions and questions**

- Plan `plan-05`; research points R1, R7 (KA half) → UPLOADED; R2's last clause (canonical-key ids) delivered as plan-03 promised.
- BUILT: `knowledge-acquisition.md` §5 "Compilation, impact, publication" — rewritten with paths.
- Deviations from plan recorded: idempotency key = refs + element ids (op bodies vary with graph state); `~` for realized endpoints in
  edge ids; in-memory rollback bypasses the lineage gate. RAISED: none new. Q2 and Q7 remain parked.

## 2026-10-08 15:50 UTC — plan-04: the second extraction pass reads processes, on addressable evidence (research-01 R3, R16 layout half)

**What changed**

- *Layout extras* `ka/extraction.py`: `Span`, `spans_for` (text = sections joined by a blank line; `text[start:end]` is the
  section), `TextExtraction.spans`, `EXTRACTION_VERSION = "ka-extract/2"`; Word tables and spreadsheets as one section per row
  (`table N row M`, `sheet X row M`); `ocr_pdf` / `ocr_image` hooks behind `KA_OCR` (`ka/config.py`; `pyproject.toml` extra `ocr`).
  `ka/model.py`: `Evidence.span_id/start/end`, `SourceVersion.extraction_version/extraction_report`. `ka/ingestion.py`: `reextract`
  (new version from the stored bytes with the current extractor; same checksum).
- *Process pass* `ka/process_extraction.py` (new): `ProcessExtractor` — model prompt carrying the closed lists (EOS node kinds,
  `PREDICATES`, loaded type names, slots), out-of-list output dropped and disclosed; heuristic over headings + numbered lists
  emitting `description`, `decomposes_into`, `performed_by` and never a type; `render_statement`.
- *Governance (protected)* `ka/governance.py::extract_from_source(process_pass=True)`: runs the pass after the statement pass,
  evidence with spans, candidates with assertions (`binding_method="evidenced"`), `extraction_report` on the version.
  `ka/service.py` wires the extractor.
- *API/console* `ka/api.py`: `POST /sources/{id}/reextract`, `extraction_report` in ingestion responses, evidence in `GET /sources/{id}`.
  `ka/console/app.js`: extraction report card with spans and a Re-extract button on the source page; span ids on nugget evidence.
  `ka/console/styles.css`: the main pane scrolls horizontally (the subject column widened the nuggets table — verify finding).
- *Docs/tests*: architecture §2 rows and §5a paragraph; `docs/protected.md` Verified bump; Q10 (prompt-injection defences) parked in
  `docs/questions/knowledge-acquisition.md` + registry; `docs/implementation-plans/plan-04.md`; fixture `ka/tests/fixtures/underwriting_sop.md`;
  `ka/tests/test_plan04_process_extraction.py` (18 cases incl. PT1; characterization `f94b0f3`); `e2e/plan04_process_extraction_flow.py`.

**Why**

research-01 R3: KA extracted sentences, not processes; EOS's graph is process-typed. The pass turns a SOP's heading, lead
sentence, actor and numbered steps into assertions plan-03 can bind, on evidence that resolves to exact characters of the stored
text (R16), and never fills what the document does not say.

**Verification**

- `pytest ka/tests` (in-process) → 122 passed; ruff F clean. Verify recount: 11/11 deliverables, 11/11 positive, 8/8 negative;
  blocks 8/8, plus three unmarked one-line edits (service.py, pyproject.toml — plan-noted; styles.css — verify finding).
- Protected: characterization `f94b0f3` before the change; covering suites byte-identical; Verified date bumped. P8 was rewritten
  post-change to reach the pre-change behaviour through `process_pass=False` (noted in the test's docstring).
- Live: `e2e/plan04_process_extraction_flow.py` 4/4 PASS, screenshots verified (nuggets tab with subject rows; source page report).
- Product tests (research-01): **PT1 PASS** (this plan), PT5, PT6 PASS; PT2–PT4 FAIL (plan-05), PT7 (plan-07), PT8 (plan-08).

**Follow-ups / risks**

- The heuristic's child-process names come from the item's first clause; a document with long unpunctuated steps gets long names.
- OCR is a hook; no OCR ran in this environment (libraries not installed). Q10 defences are parked, not built.

**Decisions and questions**

- Plan `plan-04`; research points R3 and R16 (layout half) → UPLOADED. R16's benchmark half stays OPEN for plan-09.
- BUILT: `knowledge-acquisition.md` §5a "The second extraction pass" paragraph; §2 `SourceVersion`/`Evidence` rows.
- RAISED: Q10 — prompt-injection defences for document text sent to the extraction model — in the questions document and
  `QUESTIONS-TRACKER.md`.

## 2026-10-08 15:20 UTC — plan-03: process assertions on nuggets and the EOS grammar registry (research-01 R2, R8 KA half)

**What changed**

- *Grammar* `ka/grammar.py` (new): `GrammarRegistry` reads EOS `grammar.json` + `process_types.json` from `KA_GRAMMAR_DIR`
  (default `<KA_ENTERPRISE_OS_ROOT>/knowledge_worker/graph_model`), snapshots version strings and sha256 digests to
  `ka_storage/grammar_snapshot.json`, flags a same-version digest change as stale, `refresh(force=True)` accepts it; descriptor and
  lookups (`type_grammar`, `slot_for_edge`, `edge_spec`). `KA_GRAMMAR_DIR` declared in `ka/config.py`.
- *Model* `ka/model.py`: `Subject`, `ObjectRef`, `GrammarBinding`, `SubjectRecord`; `KnowledgeNuggetVersion.subject/predicate/object`.
  `ka/vocab.py`: `PREDICATES` (13), `BindingStatus`. `ka/repository.py`: `bindings`, `subjects` collections and queries.
  `ka/versioning.py`: `SEMANTIC_FIELDS` now includes the three assertion fields (immutable with the version).
- *Identity* `ka/identity.py` (new): `canonical_key`, `SubjectRegistry.resolve` (exact key → alias → token containment / similarity
  within kind → new). *Binder* `ka/binding.py` (new): `PREDICATE_TABLE` (predicate → EOS edge + slot), `Binder.bind` with statuses
  bound / proposed / unresolved / not_applicable / stale, `rebind_all` (refuses on a stale registry).
- *Governance (protected)* `ka/governance.py`: `CandidateInput.subject/predicate/object/binding_method`; `ingest_candidate` validates
  the predicate and subject kind, resolves subjects, stores the assertion and binds at birth; `propose_revision` passes assertions through.
- *Service/API/console*: `ka/service.py` wires registry, subject registry, binder; detail carries assertion, binding, history, grammar.
  `ka/api.py`: `GET /grammar`, `POST /grammar/refresh`, `POST /grammar/rebind-all`, `GET /nugget/{ref}/binding`, `POST /nugget/{ref}/rebind`,
  `GET /subjects`, `GET /subjects/{key}`; `AssertionIn` on `POST /sources/note` and `propose-revision`. `ka/console/app.js`: assertion
  card with binding pill and Rebind, subject page `#/subject/<key>`, subject column on Knowledge nuggets, EOS grammar card on the Dashboard.
- *Docs/tests*: architecture §5a and object rows; `docs/protected.md` Verified bump; `docs/implementation-plans/plan-03.md`;
  `ka/tests/fixtures/grammar/` (real shape, trimmed); `ka/tests/test_plan03_assertions_binding.py` (20 cases; characterization `dd06520`);
  `e2e/plan03_binding_flow.py`; conftest points tests at the fixture grammar.

**Why**

research-01 §2: KA's nuggets said nothing EOS could place on its typed graph, and KA had no notion of the grammar EOS governs. This
plan gives every nugget an optional assertion in EOS terms and a binding that is a *lookup against EOS's own files*, recomputable per
grammar release without touching governed versions, and fails closed when the files drift. It is the model plan-04 (extraction) fills
and plan-05 (publication) compiles.

**Verification**

- `pytest ka/tests` (in-process) → 104 passed; ruff F clean. Verify recount: 12/12 deliverables, 12/12 positive, 9/9 negative; code blocks
  12 declared / 12 found / 0 undeclared.
- Protected: characterization `dd06520` before the change; covering suites byte-identical; Verified date bumped.
- Live on :8011 with `KA_ENTERPRISE_OS_ROOT` set: grammar loaded (`grammar/v2`, `process-types/v2`, 10 types, not stale);
  `e2e/plan03_binding_flow.py` 6/6 PASS, screenshots verified.
- Product tests (research-01): PT5, PT6 PASS (plan-02); PT1–PT4, PT7, PT8 FAIL awaiting plans 04–08.

**Follow-ups / risks**

- Subject resolution uses token containment and similarity; a wrong merge of two distinct processes is possible on short names — the
  subject page shows aliases so a reviewer can see it. Splitting a wrongly merged subject is not built.
- The registry reads files from the checkout; the EOS endpoint with a digest (Q7) would replace the file read, not the registry.

**Decisions and questions**

- Plan `plan-03`; research points R2 (fields, bindings, canonical keys — id derivation deferred to plan-05) and R8 (KA half) → UPLOADED.
- BUILT: `knowledge-acquisition.md` §5a "Process assertions and grammar binding" (new section, with paths).
- RAISED: none new. Q7 (EOS grammar endpoint) and Q8 (console shape) remain parked.

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
