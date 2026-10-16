# Plan 36 - NEXOS IT MVP: governed knowledge and mapping-correction propagation (validation + defect fixes)

Created: 2026-10-16 UTC

## Problem Description

NEXOS mission: validate that governed knowledge informs Enterprise OS navigation, process interpretation and mapping discovery without
breaking versioning or traceability. Domain-level and instance-level corrections must stay distinct. Knowledge must never establish a
physical data mapping. Changes must propagate through the documented Knowledge Worker / Data Platform contracts without silently altering
recorded answers or lineage. Content must survive service revisions and recovery. Deliver regression tests, a contract assessment, and a PR
only for real defects. No deployment.

The assessment found seven defects (D1–D7). Each was reproduced before it was fixed. Findings, evidence and remaining risks:
[`docs/user-notes/nexos-knowledge-validation/contract-assessment.md`](../user-notes/nexos-knowledge-validation/contract-assessment.md).

## Architecture and decisions this plan obeys

| decision | where | what this plan does about it |
|---|---|---|
| §9 / Inv. 9 — local overrides survive higher-level change; Inv. 8 lowest valid scope | spec §46 | **builds it** for corrections (D1) |
| Inv. 3 — governed versions immutable; one governance pipeline | spec §46, CLAUDE.md | **obeyed**: overrides go through `ingest_candidate`; no second path |
| EOS three-tier rule — physical sources only in instance data graphs | EOS `knowledge_worker/graph_model/data_graph.py` | **obeyed** (D3) |
| KW contract `ka:<proposal id>` | `docs/contracts/knowledge-worker-v1-ka.md` | **builds it** correctly (D2), doc corrected (D5) |
| Architecture §11 — DP provenance joins on lineage ids | `docs/architecture/knowledge-acquisition.md` | **builds it** (D4) |

**Protected-code impact:** none to protected methods. `ka/graph_adapter.py::KnowledgeWorkerHTTPAdapter.kw_request` (a helper beside the
protected `publish` / `validate_change`) changed which lineage entry names the key. The governance-level guards for the two remaining risks
need a separate protected-code plan.

## Code blocks

| # | File | What changed |
|---|---|---|
| B1 | `ka/corrections.py`, `ka/model.py` | narrower-scope correction → new override nugget + `SPECIALIZES`; `KnowledgeCorrection.override_of`; audit `level` |
| B2 | `ka/graph_impact.py` | a broader-scope element is `review only` for a narrower version |
| B3 | `ka/graph_adapter.py` | `kw_request` keys on the proposal's own (last) lineage entry |
| B4 | `ka/grammar.py`, `ka/process_extraction.py`, `ka/binding.py` | `DATA_LAYER_KINDS`, `assertable_kinds()`; extractor drops and discloses; binder refuses data-layer kinds and checks an edge's `from` kind |
| B5 | `ka/derived.py` | DP provenance adds `governance_decision_id`, `graph_change_refs` |
| B6 | `ka/json_io.py` | torn JSONL line skipped on read; append starts on a fresh line |
| B7 | `ka/repository.py` | unknown fields preserved across `put` |
| B8 | `ka/knowledge_worker/fake.py`, `docs/contracts/knowledge-worker-v1-ka.md` | fake checks lineage on `set_props`; doc matches the wire format |

## Tests

`ka/tests/test_plan36_nexos_correction_levels.py` (P1–P4, N1–N2), `test_plan36_nexos_recovery.py` (P1–P4, N1),
`test_plan36_nexos_publication_contracts.py` (P1–P3, N1–N3). Each defect test fails on d1d36b1 and passes here. Existing suites unmodified.
