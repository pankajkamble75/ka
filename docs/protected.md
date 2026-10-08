# Protected code

Modules listed here carry an architectural invariant and may only be changed through an implementation
plan that names the invariant, with a test that pins it.

| Module | Invariant |
|---|---|
| `ka/governance/` | §46 Inv. 3 — governed Knowledge Nugget versions are immutable; a semantic change creates a new version. |
| `ka/graph_change/` | §46 Inv. 2 — no semantic graph mutation without governed knowledge lineage. |
| `ka/runtime_guard.py` | §46 Inv. 1 — runtime answering never falls back to Knowledge Acquisition retrieval. |
