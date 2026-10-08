# Checkpoints

Dated notes written by `upload` before each push. Newest first.

## 2026-10-09 03:30 UTC — plan-15: Processes as a top-level console tab (research-02 R7, Q8)

**What changed** — `ka/console/app.js`: nav entry `4 · Processes` → `#/processes` (Dashboard 5, Images 6), `TAB_LABELS` so detail pages
return to the tab, `processesView` (scope filter + the plan-06 `processesList`), the profile crumb points at the tab; Browse by scope's
Processes mode is untouched. `README.md` tab list; architecture §8 Q8 → ✅ built; ledger. `ka/tests/test_plan15_processes_tab.py`
(4 source/route cases); `e2e/plan15_processes_tab_flow.py` (PT7).

**Why** — the author's Q8 decision: process knowledge earns a top-level entry and nothing else moves.

**Verification** — in-process 258 passed, 2 skipped (live PT5/PT6 gated on the author's credentials; exit code checked before this
commit); ruff F clean; no protected code. Verify recount 4/4 D, 3/3 P (P2 is the live flow), 2/2 N; block 1/1. Live flow 8/8 PASS
(six nav entries with Processes fourth; the tab lists five process subjects; profile opens; crumb and nav return to the tab; Browse mode
renders); screenshot verified. Product tests (research-02): PT1–PT4, PT7 PASS; PT5, PT6 fixture-driven PASS, live NOT RUN (Q12, Q13).

**Follow-ups / risks** — none.

**Decisions and questions** — BUILT: Q8 (architecture §8 ✅). RAISED: none. Plan `plan-15`; research-02 R7 → UPLOADED. R13 of research-01
(the console-shape decision) is now built through this plan.

## 2026-10-09 02:50 UTC — plan-14: the Microsoft 365 / SharePoint connector behind the plan-08 contract (research-02 R6, Q6)

**What changed**

- `ka/connectors/m365.py` (new): `M365Connector` — client-credentials token from the secret the connection's `secret_ref` names (memory
  only), drive delta with paged `@odata.nextLink` and the `@odata.deltaLink` as the checkpoint, items keyed by Graph id with the
  drive-relative path as the name (so a move changes the name), content fetch, permissions → visibility (anonymous/organization link
  or an "Everyone" group → ENTERPRISE, a group → TEAM, named users → PERSONAL, never above the connection's ceiling), a full permission
  sweep every `KA_M365_PERMISSION_SWEEP_EVERY` syncs, `revoke` drops the token. Graph 401/403 → `ConnectorError`.
- `ka/connectors/__init__.py`: `m365` registered. `ka/config.py`: the sweep setting. `ka/console/app.js`: "Connect Microsoft 365 /
  SharePoint" card (tenant, client, drive, secret variable name, include globs, scope, authority, visibility ceiling) with the refusal
  reason shown inline.
- Fixture `ka/tests/fixtures/m365_graph_fixture.json` (token, two delta pages, an incremental delta with modified/deleted/moved, content,
  permissions incl. a sweep narrowing); `ka/tests/test_plan14_m365_connector.py` (12 cases; the live PT6 SKIPS without the registration);
  `e2e/plan14_m365_flow.py` (kinds list, card, refusal without the secret variable, API 400, nothing stored). `.env.example`;
  architecture §2 Q6 → ✅ built; the Q6 row restored in the ledger's Decided table.
- `ka/tests/test_plan08_connectors.py::test_P9`: the exact kinds-list assertion `== ["local_folder"]` relaxed to membership — Q6 added a
  kind; plan-08 is not a protected area.

**Why** — the author's Q6 decision. The registration is Q13 and the author's.

**Verification** — CORRECTED in the follow-up commit: the run before e41815c was 253 passed, 1 FAILED, 2 skipped — the failure was
plan-10's regression gate `test_N1`, which byte-compares plan-08's test file and saw the documented kinds relaxation; the pipe hid pytest's
exit code from the commit chain. The gate now allows exactly that one change; after the fix: 254 passed, 2 skipped (the two live product
tests gated on the author's credentials); ruff F clean; no protected code and `SyncService` untouched (diff confirmed). Verify recount 7/7 D, 7/7 P, 5/5 N; blocks 4/4 files. Live flow 6/6 PASS;
screenshot verified. Product tests (research-02): PT1–PT4 PASS; PT5, PT6 fixture-driven PASS, live NOT RUN (Q12, Q13); PT7 awaiting plan-15.

**Follow-ups / risks** — the permission mapping is a heuristic over Graph permission shapes; the sweep interval trades Graph calls
for freshness. Delegated (per-user) OAuth is out of scope.

**Decisions and questions** — BUILT: Q6 (architecture §2 ✅). OPEN: Q13 unchanged (names `test_P7_PT6_live…`). Plan `plan-14`;
research-02 R6 → UPLOADED.

## 2026-10-09 02:05 UTC — plan-13: Brave behind the discovery seam, key in the environment, monthly cap (research-02 R5, Q5)

**What changed**

- `ka/discovery.py`: `BraveSearchProvider` (injectable `fetch_json`; maps `web.results[]` → url/title/snippet/publisher/published_at;
  any transport or shape failure → `[]` with `last_note`), `SearchMeter` (`<storage>/search_usage.json`, per calendar month),
  `select_provider` handles `brave` and fails closed to `none` with the Q12 note when `KA_SEARCH_API_KEY` is unset, `provider_status()`
  (requested provider, key PRESENCE, used/cap, month — never the key); the run's discovery notes carry the provider's `last_note`.
- `ka/config.py`: `KA_SEARCH_API_KEY` (read at call time), `KA_SEARCH_MONTHLY_CAP` (1000). `ka/api.py` providers route and
  `ka/service.py` dashboard carry the status fields; `ka/console/app.js` Dashboard line shows requested vs effective provider, key
  presence and searches this month / cap.
- Fixture `ka/tests/fixtures/brave_response.json`; `ka/tests/test_plan13_search_provider.py` (13 cases incl. the live PT5 that
  SKIPS without the key); `e2e/plan13_search_provider_flow.py` (server with `brave` requested and no key: fail-closed path end to end);
  `.env.example`; architecture §6 Q5 → ✅ built; ledger.

**Why** — the author's Q5 decision; Brave per research-02 §5. The key itself is Q12 and is the author's.

**Verification** — in-process suite 243 passed, 1 skipped (PT5 live: needs KA_SEARCH_API_KEY); ruff F clean; no protected code (diff
confirmed). Verify recount 7/7 D, 7/7 P (+P7b), 5/5 N; blocks 4/4 files found (the plan's B3 api.py block is an inline comment inside
plan-07's route block rather than a separate block — declared, found as a marked line; noted). Live flow 6/6 PASS; screenshot verified
(Dashboard: "requested brave — KA_SEARCH_API_KEY missing, Q12; failing closed · searches this month 0 / 1000"). Product tests
(research-02): PT1–PT4 PASS; PT5 fixture-driven PASS, live NOT RUN (Q12); PT6, PT7 awaiting plans 14–15.

**Follow-ups / risks** — set `KA_SEARCH_API_KEY` on the server once Brave is confirmed (Q12); the cap is a count of queries, not of
spend — Brave's free tier (2k/month) sits above the default cap of 1000.

**Decisions and questions** — BUILT: Q5 (architecture §6 ✅). OPEN: Q12 unchanged (now names `test_P7b_PT5_live…` as the test it unblocks).
Plan `plan-13`; research-02 R5 → UPLOADED.

## 2026-10-09 01:05 UTC — plan-12: repin after a domain write — explicit, per instance, by a named person (research-02 R4, Q2)

**What changed**

- *Adapters (PROTECTED, additive)* `ka/graph_adapter.py`: `RepinResult`; `GraphAdapter.pinned_versions(domain)` and
  `repin(instance, domain, new_version, actor, apply)`. EOS adapter: `store.pinned_by` / `store.repin(..., apply=)`, `RepinBlocked` → an
  unapplied result with the blocking edges, `NotPinned` → refused. Reference adapter: pins are implicit (downward propagation at
  apply), so every descendant reports current and a repin is a recorded no-op.
- *Service (PROTECTED, additive)* `ka/graph_change.py`: `repin_status(proposal_id)`, `repin(proposal_id, instance_id, by, preview,
  agent_ids)` — only an APPLIED proposal; `by` may not be a `ka.*` policy id or a research agent; preview writes nothing; a move
  updates `impact_summary.repin_required` / `repinned`, audits `graph.instance.repinned` with before/after versions and emits the event;
  `awaiting_repin()` rows for the Dashboard. `apply`, `publish`, `emit_ops` untouched.
- `ka/events.py` name; `ka/service.py` needs-attention `instances_awaiting_repin`; `ka/api.py` `GET /graph-changes/{id}/repins`,
  `POST /graph-changes/{id}/repin`; `ka/console/app.js` "Instances pinned to this domain" table with Preview/Repin and the Dashboard list.
- Tests: `test_plan12_repin.py` (reference adapter + routes, 10 cases) and `test_plan12_eos_repin.py` (EOS interpreter: preview/apply,
  PT4 status → named repin → store state + audit, blocked repin). `e2e/plan12_repin_flow.py`. Architecture §5 Q2 → ✅ built; ledger;
  `docs/protected.md` graph_change row re-verified.

**Why** — the author's Q2 decision: approved knowledge must be able to reach instances without any pin moving unseen.

**Verification** — protected protocol: characterization 4bcf9d9 first (pins reported, nothing moves) in both interpreters; covering
suites UNMODIFIED. In-process 231 passed; EOS interpreter 11 passed (plan-12 + plan-05); ruff F clean. Verify recount 8/8 D, 7/7 P,
5/5 N; blocks 6/6 files. Live flow 7/7 PASS on the reference adapter (a policy id refused with 409); screenshot verified. Product tests
(research-02): PT1–PT4 PASS; PT5–PT7 awaiting plans 13–15.

**Follow-ups / risks** — the live server runs the reference adapter, so the console shows "current" rows; the EOS store half is proved
at the seam under the EOS interpreter. No "repin all": each instance is one decision by design.

**Decisions and questions** — BUILT: Q2. RAISED: none. Plan `plan-12`; research-02 R4 → UPLOADED.

## 2026-10-08 23:55 UTC — plan-11 complete: fenced prompts and the heuristic-only binding cap, verified (research-02 R3, Q10)

**What changed** (on top of d79ce37, the work-in-progress commit)

- `ka/binding.py::rebind_all` passes `method="approved"` for ACTIVE/APPROVED versions so a grammar release does not re-cap knowledge a
  person approved. `ka/service.py::_rebind_on_approval` re-binds only a binding that was capped (no duplicate records for enterprise sources).
- `ka/tests/test_plan11_injection.py` (11 cases: fence, the four prompts at the model seam, the cap, the approval lift, PT3 with an
  "obedient" model and a page carrying its own `</document>`, ordering of the re-bind before the proposal, `rebind_all`).
- `e2e/plan11_injection_flow.py`: paste a markdown SOP with authority Internet Research → the assertion binds proposed with the reason,
  the nugget page shows the pill, approval re-binds it bound.
- Architecture §3 Q10 → ✅ built with the file list; the questions ledger's Q4/Q10/Q11 rows now read ✅ built.

**Why** — the author's Q10 decision; finishing the plan the previous commit left unverified.

**Verification** — in-process suite 221 passed; EOS path 7 passed; ruff F clean. Verify recount: 6/6 deliverables, 6/6 positive,
5/5 negative; blocks 8/8 files found (the plan's B7 row names two files), none undeclared. No protected code touched (diff confirmed
against the plan-10 upload). Live flow 5/5 PASS; screenshot verified. Product tests (research-02, 7 defined): PT1, PT2, PT3 PASS;
PT4–PT7 FAIL/NOT RUN awaiting plans 12–15.

**Follow-ups / risks** — the verifier model call remains declined; the fence is a convention the model is told about, not a hard boundary,
which is why the binding cap exists alongside it.

**Decisions and questions** — BUILT: Q10 (architecture §3 ✅). RAISED: none. Plan `plan-11`; research-02 R3 → UPLOADED.

## 2026-10-08 23:20 UTC — plan-11 work in progress: fenced prompts and the heuristic-only binding cap (research-02 R3, Q10) — committed at the author's request, NOT verified

**What changed**

- `ka/prompting.py` (new): `UNTRUSTED_NOTICE` and `fence(text, label)` (a closing tag inside the text is broken with a zero-width space).
- The four document-reading prompts carry the notice and fence the content: `ka/extraction.py` (pass one), `ka/process_extraction.py`
  (pass two), `ka/research.py` (fetched page text, `<page>`), `ka/conflict.py` (both statements of the explain prompt).
- `ka/binding.py`: `HEURISTIC_ONLY = {INTERNET_RESEARCH, LLM_GENERATED}`; `Binder.bind` computes then caps a BOUND typed assertion from such
  a source at `proposed` with the reason "heuristic-only source (Q10) …" unless `method="approved"`. `ka/service.py`: a
  `knowledge.approved` subscriber registered BEFORE the graph-proposal subscriber re-binds only capped bindings with `method="approved"`.
- `ka/console/app.js`: "heuristic-only source · binds on approval" pill on the Process assertion card.
- `docs/implementation-plans/plan-11.md`; tracker R3 → PLANNED.

**Why** — the author's Q10 decision (2026-10-08). The author asked to commit and push mid-build.

**Verification** — in-process suite 210 passed (the touched suites plan-03/04/06/07 pass unmodified); ruff F clean. **plan-11's own
test file (11 cases), live flow, architecture state and verify/upload have NOT been done** — the tracker row stays PLANNED, not
IMPLEMENTED. Deliverables present: D1–D5 of 6; D6 (flow, docs) missing; 0 of 11 cases written.

**Follow-ups / risks** — finish plan-11: `ka/tests/test_plan11_injection.py`, `e2e/plan11_injection_flow.py`, architecture §3 → ✅,
verify, upload. Then plans 12–15.

**Decisions and questions** — BUILT (partially, unverified): Q10. RAISED: none. Plan `plan-11`; research-02 R3 still PLANNED.

## 2026-10-08 22:40 UTC — plan-10: duplicates resolve as Keep Existing + evidence; revocation becomes a re-review (research-02 R1, R2; Q11, Q4)

**What changed**

- *Governance (PROTECTED)* `ka/governance.py`: inside `decide`, a candidate flagged `duplicate_of` an ACTIVE nugget in the SAME scope never
  becomes a second ACTIVE version — APPROVE is rewritten to an automatic KEEP_EXISTING decision (reason names Q11), the candidate is
  REJECTED with `analysis.resolved_as="duplicate"` and `conflict_open=False`, and `attach_provenance` appends its source and evidence
  refs to the existing nugget (provenance, not `SEMANTIC_FIELDS`; audited before/after). Explicit KEEP_EXISTING attaches too. The
  analysis now sets `duplicate_of` for an exact same-scope duplicate even when the candidate also contradicts other nuggets. New
  `reopen_for_revocation(source_id, by)`: each ACTIVE nugget derived from a revoked source gets a same-statement revision
  (`propose_revision`, channel FEEDBACK) with `analysis.source_revoked` and `remaining_sources`. REJECT of such a revision retires the
  prior version (OBSOLETE, `effective_to`, OBSOLETES relationship) and calls `on_retire`.
- *Publication (PROTECTED, additive)* `ka/graph_change.py::propose_retirement(v, by)`: removal ops for elements whose active lineage is
  only `v`'s canonical id; shared elements untouched; goes through validate → approve → apply. `ka/service.py` wires `on_retire`.
- *Connectors* `ka/connectors/sync.py`: on `deleted`, after flagging, `governance.reopen_for_revocation`; refs in `SyncReport.reviews`
  and `Connection.last_delta["reviews"]` (`counts()` unchanged). `ka/service.py`: needs-attention `revoked_source_reviews`; nugget rows
  carry `resolved_as`, `duplicate_of`, `source_revoked`, `remaining_sources`.
- *Console* `ka/console/app.js`: "duplicate of KN-x" and "source revoked · n remaining sources" badges on both row renderers; Dashboard
  table "Re-reviews from revoked sources" with Approve/Reject.
- *Docs/tests* `plan-10.md` (with the build corrections); `ka/tests/test_plan10_governance_decisions.py` (14 cases);
  `e2e/plan10_governance_flow.py`; architecture Q11/Q4 → ✅ built; `docs/protected.md` rows re-verified.

**Why** — the author's decisions Q11 and Q4 (2026-10-08): one governed fact per claim, and revocation as a governance event rather
than a silent flag.

**Verification**

- Protected protocol: characterization committed first (48d4685) and green against the unchanged files; `ka/governance/` and
  `ka/graph_change/` covering suites pass UNMODIFIED **except `test_plan06_profile.py::test_N7`**, whose assertions pinned "duplicate
  ACTIVE assertions (Q11)" — the behaviour the author ruled out — and were rewritten to the decided behaviour (recorded in
  `docs/protected.md` and in `test_plan10::test_N1`). Not a regression; a ruled decision superseding a pinned open question.
- Corrections during the build: duplicates are same-scope only (`test_plan01_phase6::test_P4` showed sibling-instance repeats are
  promotion's business); exact duplicates are flagged under conflict (the live store surfaced it).
- `pytest ka/tests` (in-process) → 210 passed; EOS path → 7 passed; ruff F clean. Verify recount 8/8 D, 8/8 P, 6/6 N; blocks 5/5,
  none undeclared.
- Live: `e2e/plan10_governance_flow.py` 8/8 PASS (duplicate → automatic Keep Existing, both documents on one nugget, history badge;
  deleted connector file → re-review on the Dashboard → Reject → prior OBSOLETE → retirement proposal); screenshots verified.
- Product tests (research-02, 7 defined): **PT1 PASS, PT2 PASS**; PT3–PT7 FAIL/NOT RUN awaiting plans 11–15.

**Follow-ups / risks** — a permission NARROWING that drops a source below its nuggets' scope requirement is still only flagged
(plan-08); it is the undecided second half of Q4 and is listed as out of scope in the plan.

**Decisions and questions** — BUILT: Q11, Q4 (architecture §2, §4, §10 now ✅ built with `path:line`). RAISED: none. Plan `plan-10`;
research-02 R1, R2 → UPLOADED.

## 2026-10-08 21:10 UTC — question session: Q1–Q11 answered by the author

**What changed**

- `docs/trackers/QUESTIONS-TRACKER.md`: Class and Severity columns added (Q231); all eleven rows ANSWERED with the decision verbatim.
- `docs/questions/knowledge-acquisition.md`: every question moved from ❓ Open to ✅ Decided with its reasoning; the original Q&A kept
  in `<details>` ledgers; the Open block is empty.
- `docs/architecture/knowledge-acquisition.md`: each decision written as a rule with its state — Q1 (token access) and Q3 (auto-apply
  off) ✅ built; Q9 (no re-pin) ✅ current state; Q2, Q4, Q5, Q6, Q8, Q10, Q11 ⏳ DECIDED, not built; Q7 ⏳ DECIDED, not built, EOS repo.
- `docs/trackers/RESEARCH-TRACKER.md`: R13 and R14 → DECIDED; R11's note records the Q7 decision.

**Why** — the ship run parked eleven author decisions; the `questions` skill walked them one at a time, severity first (7 MAJOR, 4 MINOR).

**Verification** — docs only; no code changed; no tests run.

**Follow-ups / risks** — the unlocked work (listed in the session report) needs plans: Q11 duplicates, Q10 injection defences, Q2 repin,
Q4 re-review on revocation, Q5 search provider, Q6 M365 connector, Q8 Processes tab; Q7 is an Enterprise OS research.

**Decisions and questions** — ANSWERED: Q1–Q11 (all in `docs/questions/knowledge-acquisition.md` ✅ Decided and in the architecture).
RAISED: none. Plan: none (question session).

## 2026-10-08 20:20 UTC — plan-09: the gap request contract (KA half), events as an outbox, the store benchmark (research-01 R11, R15, R16)

**What changed**

- *Gap requests (R11, KA half; PROTECTED)* `ka/model.py`: `KnowledgeAcquisitionRequest` gains `principal`, `intent`, `missing_semantics`,
  `correlation_id`, `dedupe_key`, `updated_at`, `fulfilled_by`, `cancelled_reason`, `deduplicated_count`; status lifecycle OPEN →
  IN_RESEARCH → FULFILLED | CANCELLED. `ka/runtime_guard.py`: `graph_gap_detected` validates the intent, dedupes against live
  requests (same scope + normalised question, or the correlation id) and returns `GapOutcome.deduplicated`; `open_mission` →
  IN_RESEARCH; new `get`, `requests`, `cancel`, `fulfil`, `fulfil_from_approval`; `open_requests` counts both live states;
  `retrieve_for_answer` untouched. `ka/service.py`: a `knowledge.approved` subscriber fulfils the request whose mission produced the
  approved ref. `ka/api.py`: `GapIn` fields; `GET /runtime/requests[?status]`, `GET /runtime/requests/{id}`, `POST …/cancel` (409 when
  terminal). `ka/console/app.js`: needs-attention gap table with principal · intent, status, mission link, Cancel.
- *Outbox (R15)* `ka/repository.py`: `append_event` stamps `seq` + `version: ka-events/1` (counter resumed from the file);
  `events(after=, limit=, tail=)` serves pre-plan records with their line number; `GET /events?after=&limit=&tail=` returns
  `next_after` and `version`.
- *Benchmark (R16 half)* `tools/bench_store.py`; results and reading in `docs/research/benchmarks/store-bench-2026-10-08.md`
  (10k: cold load 0.50 s, search 279 ms; 100k: 8.47 s, 3682 ms, 126 MB).
- *Docs/tests*: architecture §2 (store size), §9 (outbox, request lifecycle); `docs/protected.md` runtime-guard row re-verified;
  `plan-09.md`; `ka/tests/test_plan09_gap_requests.py` (15 cases); `e2e/plan09_gap_requests_flow.py`.

**Why**

research-01 §6 and §8: the KA side of the gap contract is cheap and makes scenario A10 possible whichever way Q7 goes; the event
log was already durable and ordered and only lacked a cursor; and nobody should argue about a store migration without the numbers.

**Verification**

- Protected protocol for `ka/runtime_guard.py`: characterization committed first (67df074, green against the unchanged file); the
  covering test `test_plan01_phase4_corrections.py::test_N1` passes UNMODIFIED (diff empty); Verified date bumped in `docs/protected.md`;
  P1's identical-question case was the behaviour this plan changes — rewritten to distinct questions with the reason in its docstring.
- `pytest ka/tests` (in-process) → 196 passed; EOS path → 7 passed; ruff F clean (style rules E501 etc. are pre-existing noise, 117 on
  the committed tree). Verify recount: 9/9 deliverables, 9/9 positive, 6/6 negative; blocks 7/7 files found, none undeclared.
- Live: `e2e/plan09_gap_requests_flow.py` 7/7 PASS (gap twice → one request; dashboard shows principal/intent/status and "raised 2×";
  Cancel; `GET /events?after=` resumes exactly); screenshots verified.
- Product tests (research-01, 8 defined): PT1–PT8 PASS (none names R11/R15/R16).

**Follow-ups / risks**

- Search at 100k is linear (3.7 s); an index or migration is a decision for the author with these numbers in hand.
- Nothing in EOS calls the gap contract yet (Q7).

**Decisions and questions**

- Plan `plan-09`; research points R11 (KA half), R15, R16 (benchmark half) → UPLOADED. R11's EOS half, R13, R14 remain parked (Q7, Q8, Q9).
- BUILT: `knowledge-acquisition.md` §9 paragraphs (outbox; request lifecycle), §2 store-size note. RAISED: none new.

## 2026-10-08 19:25 UTC — plan-08: managed connectors — the contract, a local-folder connector, incremental sync that keeps history (research-01 R10)

**What changed**

- *Connectors* `ka/connectors/__init__.py` (new): `Connector` protocol (authorize / enumerate / fetch / get_permissions / checkpoint /
  sync_incremental / revoke), `ConnectorItem`, `SyncDelta`, `ConnectorError`, `get_connector`, `CONNECTOR_KINDS`.
  `ka/connectors/local_folder.py` (new): root containment under `KA_CONNECTOR_ROOTS` (symlinks resolved), include globs, sidecar
  `<name>.visibility`, checkpoint by locator → checksum, delta new/modified/moved/deleted/permission-changed.
  `ka/connectors/sync.py` (new): `SyncService.create / sync / revoke`; reconciliation through `IngestionService.connect` (so a changed
  file is a new `SourceVersion` of the same source and is re-extracted through governance); moved keeps the source; deleted sets
  `Source.revoked_at` and flags derived nuggets; permission change updates `Source.visibility` and flags; upload cap and fetch /
  extraction failures are skipped with reasons; a revoked connection refuses to sync.
- *Model/store* `ka/model.py`: `Connection`, `Source.connection_id`, `Source.revoked_at`; `ka/repository.py`: `connections`;
  `ka/ids.py`: `CON` prefix (one line, undeclared by the plan — finding); `ka/config.py`: `KA_CONNECTOR_ROOTS`; `ka/events.py`:
  `source.synced / source.revoked / source.permission_changed`; `ka/service.py`: wiring, `needs_attention` gains
  `revoked_sources_with_active_knowledge`, dashboard `connections`.
- *API/console* `ka/api.py`: `POST/GET /connectors`, `GET /connectors/{id}`, `POST …/sync` (409 when revoked), `POST …/revoke`.
  `ka/console/app.js`: "Connect a folder" card, connections list with Sync/Revoke, source page shows connection and revocation,
  Dashboard tile and needs-attention table.
- *Docs/tests*: architecture §2 paragraph; README; `.env.example`; `plan-08.md`; `ka/tests/test_plan08_connectors.py` (16 cases);
  `e2e/plan08_connector_flow.py`.

**Why**

research-01 R10 (note REQ-002): `connect()` only recorded a payload a caller had fetched; nothing enumerated a source system,
noticed change, or honoured revocation. The folder is the first connector because it exercises every part of the contract with no
credentials; the cloud and enterprise providers are the author's decision (Q6). History is never lost: versions and derived
knowledge survive deletion and are flagged, because retiring them is Q4.

**Verification**

- `pytest ka/tests` (in-process) → 181 passed; ruff F clean. Verify recount: 10/10 deliverables, 10/10 positive, 6/6 negative; blocks
  10/10 files found, one undeclared one-line edit (`ka/ids.py`).
- No protected code touched (diff confirmed).
- Live: `e2e/plan08_connector_flow.py` 5/5 PASS on the running server (connect via the console, sync, change the file, sync again,
  Conflicts view lists the contradiction); screenshots verified.
- Product tests (research-01, 8 defined): **PT1–PT8 all PASS** — PT8 turned green here.

**Follow-ups / risks**

- Providers beyond the folder (Q6) and retention after revocation (Q4) remain parked; scheduled sync is not built (manual + API).
- The folder connector hashes every file on each sync (fine for inboxes; a 100k-file tree wants the mtime short-cut).

**Decisions and questions**

- Plan `plan-08`; research point R10 → UPLOADED.
- BUILT: `knowledge-acquisition.md` §2 "Managed connectors" paragraph. RAISED: none new; Q4 and Q6 remain parked.

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
