# plan-01 — Knowledge Acquisition subsystem (spec §44 Phases 1–6)

**Problem statement.** Build the Knowledge Acquisition subsystem of `knowledge-acquisition-requirements.md` as a standalone Python
package (`ka`) that integrates with enterprise-os-070626's v2 graph through an adapter, in the six phases of §44.

**Status.** IMPLEMENTED 2026-10-08. 66 tests (63 in-process + 3 read-only against the live enterprise-os store). See
`docs/architecture/knowledge-acquisition.md` for the design and `README.md` for the invariant → test table.

## Phases and acceptance

| Phase | Scope (§44) | Built | Success criterion → test |
|---|---|---|---|
| 1 Knowledge Foundation | ingestion (notes, PDF/Word/text, URL), nugget model, source→nugget lineage, versioning, scopes, console, search | `ingestion`, `extraction`, `model`, `repository`, `versioning`, `scope`, `search`, `api`, `console` | users add sources and inspect nuggets by domain/instance → `test_plan01_phase1_foundation.py`, `test_plan01_api_console.py::test_P2/P3` |
| 2 Governance | duplicate/contradiction detection, relationships, approval, conflict resolution, effective dates, authority, comments, immutable versions | `conflict`, `governance`, `versioning`, `config.AuthorityPolicy` | new content cannot silently overwrite → `test_plan01_phase2_governance.py` |
| 3 Graph Lineage | nugget↔graph, dependency registry, impact analysis, Graph Change Proposals, lineage visualisation | `lineage`, `graph_adapter`, `graph_impact`, `graph_change`, console lineage panel | every affected element explains its nugget → `test_plan01_phase3_graph_lineage.py` |
| 4 Console Corrections | Correct this, capture, lineage resolution, scope recommendation, governance, propagation | `corrections`, `runtime_guard`, `POST /corrections`, `GET /lineage/explain` | correction flows through KA before the graph → `test_plan01_phase4_corrections.py` |
| 5 Research Agents | missions, runs, internet/LLM/company research, synthesis, candidates, research lineage | `research` | a domain requests research and receives governed candidates without agents touching the graph → `test_plan01_phase5_research.py` |
| 6 Intelligent Propagation | inheritance-aware propagation, override protection, parent-domain propagation, pattern detection, promotion, incremental recompilation, rollback | `graph_change._changes_from`, `graph_impact`, `promotion`, `graph_change.rollback` | domain change propagates without destroying overrides → `test_plan01_phase6_propagation.py` |

## Protected code (docs/protected.md)

`ka/governance.py` + `ka/versioning.py` (Inv. 3), `ka/graph_change.py` + adapters' `validate_change` (Inv. 2), `ka/runtime_guard.py` (Inv. 1).

## Known gaps / parked questions

1. Authentication at the API edge (§42 enforcement) — the model carries visibility and permissions; nobody checks a caller's identity yet.
2. enterprise-os domain writes create a new substructure version; instances must be repinned with the store's `repin` — not automated.
3. Image extraction (§3.1 "where extraction is available") — recorded as UNAVAILABLE; no OCR/vision wired.
4. Scheduled research (§3.2 "future implementation") — not built.
5. The Enterprise Console UI button "Correct this" lives in the enterprise-os console frontend; this repo provides the endpoint and a form.
