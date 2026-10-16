# NEXOS IT MVP — governed knowledge and mapping-correction propagation: contract assessment

Date: 2026-10-16 · Repository: `ka/` (Knowledge Acquisition) · Branch: `fix/instance-correction-scope` · Plan record: [plan-36](../../implementation-plans/plan-36.md)

Scope: how governed knowledge feeds Enterprise OS semantic navigation, process interpretation and mapping discovery. The
assessment covers KA and its two peer contracts, Knowledge Worker (`docs/contracts/knowledge-worker-v1-ka.md`) and the Data Platform
(`docs/contracts/data-platform-v1-real.md`). It ran in-process against the stub LLM, the in-memory graph and the wire-level KW/DP fakes.
The Data Platform's real receiver (`/root/dataplatform`) was read, not called. No live server, no live `ka_storage/`, no GCP.

Tests: `ka/tests/test_plan36_nexos_correction_levels.py`, `test_plan36_nexos_recovery.py`, `test_plan36_nexos_publication_contracts.py`
(17 tests). Full suite: **529 passed, 5 skipped** (baseline 512 passed, 5 skipped); no existing test was modified. Every defect test below fails
on `main` (d1d36b1) and passes on the branch.

## Verdict per requirement

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| R1 | Knowledge records remain versioned and traceable | **PASS** | Invariant 3 holds: semantic fields are immutable on governed versions (`ka/versioning.py`); every `nuggets.put` caller writes lifecycle fields only. History, decisions and `explain_element` survive a restart byte-for-byte (`recovery::test_P1`). |
| R2 | Domain-level and instance-level corrections are distinguished | **DEFECT → fixed** | D1 below. |
| R3 | Governed knowledge does not falsely establish a physical data mapping | **DEFECT → fixed (document path)** | D3 below. `realized_by` / `computed_by` were already never emitted (not in `PREDICATE_TABLE`). |
| R4 | Changes propagate through documented contracts without silently altering recorded answers or lineage | **DEFECTS → fixed**; recorded answers PASS | D2, D4, D5 below. Prior proposals and executions are unchanged on disk after a revision and after a rollback. AgentX `GET /v1/operations/{id}` returns the stored result after supersession. Derived artefacts are one per status and never overwritten. `WikiPublication` digests are unchanged; an article is a live projection and reports `stale` (documented, Q19). |
| R5 | Existing KA content survives service revisions and recovery | **DEFECTS → fixed**; restart PASS | D6, D7 below. |

## Defects found and fixed

| | Defect | Reproduction (before) | Fix | Pinned by |
|---|---|---|---|---|
| **D1** | **An instance correction of inherited domain knowledge revised the domain nugget.** `CorrectionService.submit` always passed `canonical_id=original.canonical_id`. The scope engine suggested `INSTANCE:merchant-a`, but the candidate became `KN-001:v2`. Approving it superseded the domain version for every instance and wrote `$750` to the **domain** element. Merchant A kept `$500`. | `correction_levels::test_P1,P2,P3,P4` | A correction scoped narrower than the knowledge it corrects becomes a **new nugget** at that scope, linked by `SPECIALIZES` to the original. It is recorded as `KnowledgeCorrection.override_of` and as `level: override` in the audit. Approval updates only the instance's realized copy (the existing §9 override path). Corrections at the knowledge's own scope remain revisions. | `ka/corrections.py`, `ka/model.py` |
| **D1b** | Defence in depth: any narrower-scope version (e.g. `propose_revision(scope=INSTANCE)`) proposed updates to the broader-scope element it found through lineage. | `correction_levels::test_N2` | `GraphImpactService.analyze` marks elements of a broader scope `review only` for a narrower version. | `ka/graph_impact.py` |
| **D2** | **KW idempotency key taken from another proposal.** `kw_request` keyed on the *first* lineage entry. `_merged_lineage` puts other nuggets' entries first, so the second assertion about a process was sent as `ka:<first proposal>`. KW answered `CONFLICT`, and only one assertion per element ever published. On the AgentX path KW applied the change but KA marked it FAILED, so the shadow graph and lineage diverged from KW. | `publication_contracts::test_P1,N1` | Key on the proposal's own entry (the last). The contract doc now states the rule. | `ka/graph_adapter.py::kw_request` (helper; the protected `publish` / `validate_change` are unchanged) |
| **D3** | **Document text could put a `physical_source` node on the graph.** A process-pass assertion with `subject_kind: physical_source` ("the refund ledger table REFUND_TXN…") published `ps.refund_ledger` at instance **and domain** scope, against EOS's three-tier rule. It carried no marker separating it from a Data-Platform-verified source. The binder also never checked an edge's `from` kind, so `consumes` from a physical source bound. | `publication_contracts::test_P2,N2,N3` | `grammar.DATA_LAYER_KINDS` / `GrammarRegistry.assertable_kinds()`: the extractor neither offers nor accepts data-layer kinds as subject or object, and discloses each drop in `extraction_report`. The binder leaves any assertion touching one `unresolved`, and an edge from a disallowed source kind `proposed`. | `ka/grammar.py`, `ka/process_extraction.py`, `ka/binding.py` |
| **D4** | **DP provenance lacked the lineage join ids** promised by architecture §11. Only `ref` was sent, so `governance_decision_id` and `graph_change_refs` existed only inside the content bytes. | `publication_contracts::test_P3` | Both are sent as scalar metadata. DP keeps scalars only (`dataplatform core/knowledge.py:138`), so the refs are comma-joined. | `ka/derived.py` |
| **D5** | **KW contract doc ≠ code.** The doc said lineage entries carry `nugget_version` / `nugget_ref` and ops `update_node` / `update_edge`. The code sends `{nugget_id, version, governance_decision_id, graph_change_id}` and `set_props`, which the real KW accepts as an alias. The fake KW skipped the lineage check on `set_props`, which the real KW enforces. | doc review | Doc corrected to the wire format; the fake now checks lineage on `set_props` too. | `docs/contracts/knowledge-worker-v1-ka.md`, `ka/knowledge_worker/fake.py` |
| **D6** | **A torn last line in `events.jsonl` silenced the event log.** A crash mid-append left a partial line. On restart, every `append_event` raised inside `_last_seq`, and `EventBus.emit` swallowed it ("event sink failed"). Every later event was lost, including the feed AgentX/EOS read through `/v1/events`. `audit.jsonl` failed the same way, and the next audit record was glued onto the torn line. | `recovery::test_P2,P3` | `read_jsonl` skips an unreadable line with a warning. `append_jsonl` starts on a fresh line when the file does not end in `\n`. | `ka/json_io.py` |
| **D7** | **Rolling back the service erased fields written by a newer revision.** Pydantic drops unknown fields on load, and the next lifecycle write (comment, lineage, status) rewrote the file without them. | `recovery::test_P4,N1` | `Collection` keeps a stored object's unknown fields and writes them back on `put`. | `ka/repository.py` |

## Remaining risks (not fixed here; for decision)

1. **`propose_revision(scope=<narrower>)` still supersedes the broader nugget in knowledge.** D1b keeps the graph correct, but the revision API
   (`ka/api.py:476`) and AgentX `knowledge.revise` can still turn a domain nugget into an instance one. Closing it means refusing narrower-scope
   revisions in `GovernanceService.ingest_candidate`, which is protected code (Inv. 3). It needs its own plan with a characterization test.
2. **A direct API/AgentX candidate with `subject.kind=physical_source` is refused by binding but still compiles a node** through
   `graph_change.emit_ops` (protected) once a person approves it. Knowledge Worker's own validator refuses it at domain scope. Recommended:
   refuse data-layer subject kinds in `ingest_candidate` under the same protected-code plan as item 1.
3. **One corrupt object file stops its whole collection loading** (`Collection._load`). This fails closed, which is safer than serving a store
   with governed versions silently missing. Recommended: a startup integrity check that names the bad file. `write_json` does not `fsync`.
4. **Lineage registry and shadow graph are written separately.** A crash between them can leave them out of step (not reproduced).
5. **Derived-artefact key is per status.** A second ACTIVE of the same version (revoke → re-approve) reuses the first artefact, so the new
   decision id is not published to DP.
6. **DP derived assets parent on the source document version, not on the prior nugget asset.** Supersession is inside the payload only.

## Coordination

- **Knowledge Worker:** D2 changes what KA sends. Every proposal now arrives under `ka:<own id>`; nothing else in the wire format changed.
  KW needs no change. The corrected contract doc is the reference.
- **Data Platform:** D4 adds two scalar metadata keys to `POST /v1/derived-assets`. The DP receiver already accepts and stores scalar metadata;
  no DP change needed.
- **Enterprise OS:** D3 means KA no longer offers document-derived physical sources. Physical sources and `realized_by` stay with the
  instance data graph and the Data Platform, as `data_graph.py`'s three-tier rule requires.

Not done: no deployment (GCP or VPS), no live-server run, no change to protected methods.
