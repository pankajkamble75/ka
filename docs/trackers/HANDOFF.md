# Handoff — 2026-10-17

Tree is clean and pushed; branch `fix/instance-correction-scope` matches its remote at the handoff commit (on top of plan-36 `5d89fe7`).
**`main` is at `d1d36b1` (plan-35) and does not yet contain plan-36** — it lives on PR #3.

## The one-paragraph version

KA (Knowledge Acquisition, the `ka/` package) was validated for the NEXOS IT MVP mission: does governed knowledge reach Enterprise OS
navigation, process interpretation and mapping discovery without breaking versioning, scope or lineage? Seven real defects were found,
reproduced and fixed (plan-36). They are on PR **https://github.com/pankajkamble75/ka/pull/3**, not merged. **Next action: review and
merge PR #3 into `main`. Then decide whether to write the protected-code plan for the two remaining governance risks (see §8).**

## 3. Where the work stands

| Item | State |
|---|---|
| plan-34 (NEXOS integration v1) | UPLOADED `e360f89` |
| plan-35 (bind to WireGuard + loopback only) | UPLOADED `d1d36b1` — live service on `10.77.0.2:8011` / `127.0.0.1:8011` |
| plan-36 (NEXOS knowledge validation, D1–D7) | IMPLEMENTED on PR #3, **not merged**; `/verify` not run |
| Tests (run now, on this branch) | `pytest -q` → **529 passed, 5 skipped** (47 s); ruff: 380 findings, pre-existing style classes (E501 etc.; main has 374, branch adds 6 long lines), no new F-class |

Session commits:
- `5d89fe7` plan-36: instance corrections become overrides; KW idempotency key; no physical mappings from documents; recovery fixes.
- handoff commit: this file + tracker rows for plans 34/35/36.

### 3a. Tracker state (`/show`)

`/show` could not be rendered. Its renderer, `tracking.tests.test_status_table.render_status`, is in the enterprise-os checkout and
not in this repository (`tracking/` does not exist here), and the tracker tests named by `/bye` (`knowledge_worker/tests/`) don't
exist either. Instead, here is the state from `docs/trackers/RESEARCH-TRACKER.md`:

- **Active:** 7 rows. Six are DECIDED decision rows from research-01 and research-04, with nothing left to build. One is plan-36,
  IMPLEMENTED on PR #3.
- **Closed:** everything else is UPLOADED, including plans 34 and 35.
- **Fixed by this `/bye`:** plans 34, 35 and 36 had no tracker rows. They were added from the tree (the SHAs above).
- **Older drift, left as is:** this file was last written on 2026-10-08 (plan-01). Every handoff after that went to
  `docs/user-notes/nexos-integration-v1/CHATGPT-HANDOFF.md` or `docs/checkpoints/CHECKPOINTS.md`.

## 4. What exists now that did not

- **Corrections at two levels** (`ka/corrections.py`): a correction scoped narrower than the knowledge it corrects, such as one merchant
  correcting a domain rule, becomes a NEW nugget at that scope, linked by `SPECIALIZES`. It is recorded in
  `KnowledgeCorrection.override_of` and in the audit as `level: override`. A correction at the knowledge's own scope is still a revision.
  `ka/graph_impact.py` marks broader-scope elements "review only" for a narrower version.
- **No physical data mappings from documents:** `grammar.DATA_LAYER_KINDS` and `assertable_kinds()`. The extractor drops these kinds and
  discloses each drop in `extraction_report`. The binder leaves them `unresolved` and checks an edge's `from` kind.
- **Knowledge Worker key:** `kw_request` keys on the proposal's own lineage entry (`ka:<own proposal id>`).
- **Data Platform provenance** carries `governance_decision_id` and `graph_change_refs`.
- **Recovery:** a torn JSONL line is skipped and the next append starts a fresh line (`ka/json_io.py`). `Collection` keeps unknown fields
  across `put`, so rolling the service back no longer erases them.
- Assessment: `docs/user-notes/nexos-knowledge-validation/contract-assessment.md`. Plan: `docs/implementation-plans/plan-36.md`.

## 5. Things that will bite you

- **A torn line used to silence the whole event log.** `EventBus.emit` swallows sink errors ("event sink failed"), so a broken
  `events.jsonl` made `/v1/events` go quiet without failing anything. This is fixed, but the same swallowing pattern still hides other
  sink failures.
- **Lineage order matters.** `_merged_lineage` puts other nuggets' entries first, so the proposal's own entry is the **last** one.
  Anything that takes "the" entry must take the last.
- **The fake Knowledge Worker used to be laxer than the real one** (no lineage check on `set_props`). It is fixed, but when the fake
  and the real KW disagree, trust the real KW and `docs/contracts/knowledge-worker-v1-ka.md`.
- **Protected code:** `governance.py`, `graph_change.py` and `runtime_guard.py` (`docs/protected.md`) need their own plan with a
  characterization test. Plan-36 deliberately left them alone.
- **Never run `e2e/plan10_governance_flow.py` against the live 8011.**
- `/verify` expects a live-browser click-through and a push to `main`. It doesn't fit a PR branch, so it was skipped and tests and lint
  were run directly.

## 6. Environment

- Host `srv1886827`. The live KA service is `enterprise-os-ka` (systemd), bound to `10.77.0.2:8011` and `127.0.0.1:8011`. Neither it nor the
  live `ka_storage/` was touched this session.
- Suite: `.venv/bin/python -m pytest -q` (about 1–2 minutes), `.venv/bin/ruff check ka`. It runs on the stub LLM and the in-memory graph.
- Nothing was deployed (no GCP, no VPS change).

## 7. Reading order

1. `docs/user-notes/nexos-knowledge-validation/contract-assessment.md`: the verdict for each requirement, D1–D7, and the remaining risks.
2. `docs/implementation-plans/plan-36.md`: which code block changed in which file.
3. `docs/architecture/knowledge-acquisition.md` §7 and §11: the correction-level and Data Platform provenance notes.

## 8. Decisions and open questions

- **Decided but not built:** Q15, connector ownership (architecture §R8, line ~352). There is nothing to build yet; unchanged this session.
- **Answered this session:** none.
- **Raised and still open.** Not yet in the questions registry, so `/questions` won't ask them until they get a Q id:
  1. Should `GovernanceService.ingest_candidate` refuse a revision scoped narrower than the knowledge it revises? Today
     `propose_revision(scope=INSTANCE)` and AgentX `knowledge.revise` can still retire a domain nugget at the knowledge level. Fixing this
     needs a protected-code plan.
  2. Should `ingest_candidate` refuse `physical_source` (data-layer) subjects? A direct API candidate is now left unbound, but would still
     compile a graph node if a person approved it. Same protected-code plan.
  3. Lower priority, from the assessment: one corrupt object file stops its whole collection from loading (fails closed, no startup
     integrity check); the lineage registry and shadow graph are written non-atomically; the derived-artefact key is per status; Data
     Platform assets are parented on the source document.
- **Divergences:** none known between the tree and a decided question.
