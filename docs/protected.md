# Protected code

Modules listed here carry an architectural invariant and may only be changed through an implementation
plan that names the invariant, with a test that pins it.

| Module | Invariant | Covering tests | Re-verify flow | Verified |
|---|---|---|---|---|
| `ka/governance/` (`ka/governance.py`, shared: `GovernanceDecision` in `ka/model.py`) | §46 Inv. 3 — governed Knowledge Nugget versions are immutable; a semantic change creates a new version. | `test_plan01_phase2_governance.py`, `test_plan01_phase6_propagation.py`, `test_plan01_api_console.py`, `test_plan02_security_visibility.py`, `test_plan03_assertions_binding.py` | console: Apply a PERSONAL candidate to a domain → refused with the from→to reason; tick "widen visibility" → applied, decision shows `visibility_change`. plan-03: a note with an assertion → nugget detail shows the assertion card and binding | 2026-10-08 (plan-03: assertion fields + binding at birth in `ingest_candidate`; characterization dd06520; covering suites passed unmodified; live flow e2e/plan03_binding_flow.py) |
| `ka/graph_change/` (`ka/graph_change.py`) | §46 Inv. 2 — no semantic graph mutation without governed knowledge lineage. | `test_plan01_phase3_graph_lineage.py`, `test_plan01_phase6_propagation.py` | approve a nugget → proposal READY → approve → apply → element carries `knowledge_lineage` | 2026-10-08 (plan-01) |
| `ka/runtime_guard.py` | §46 Inv. 1 — runtime answering never falls back to Knowledge Acquisition retrieval. | `test_plan01_phase4_corrections.py::test_N1` | `POST /runtime/graph-gap` returns GRAPH GAP DETECTED; no route returns knowledge for a question | 2026-10-08 (plan-01) |
