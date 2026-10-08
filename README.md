# Enterprise OS — Knowledge Acquisition (`ka`)

> **Knowledge Acquisition is the learning and governance subsystem of Enterprise OS. It acquires knowledge from
> enterprise and personal content, autonomous research, and operational human feedback; converts that
> information into versioned, scoped, governed Knowledge Nuggets; maintains complete source and Graph lineage;
> and propagates approved knowledge changes into Structure, Domain, and Instance graphs.**
>
> **The Graph is the compiled operational representation of governed enterprise knowledge.**

```text
ACQUIRE → GOVERN → KNOW → COMPILE → GRAPH → OPERATE → OBSERVE / CORRECT ──→ ACQUIRE
```

The specification this package implements is [`knowledge-acquisition-requirements.md`](knowledge-acquisition-requirements.md).
How the code realises it, section by section, is in [`docs/architecture/knowledge-acquisition.md`](docs/architecture/knowledge-acquisition.md).

## Quick start

```bash
uv venv .venv && uv pip install -p .venv/bin/python -e ".[dev,extract]"
.venv/bin/python -m pytest -q                       # 66 tests, stub LLM, in-memory graph
.venv/bin/python -m ka demo                         # seed ka_storage/ with the §47 Merchant Acquiring example
.venv/bin/python -m ka serve                        # Knowledge Console on http://localhost:8011/console/
```

From a browser on another machine the API needs a bearer token: set `KA_ACCESS_TOKEN` in `.env` and paste it under
"You → Access token" in the console (`KA_ACCESS_POLICY=token`, the default; `loopback` or `open` change that).

Set `ANTHROPIC_API_KEY` (see `.env.example`) to use the real extractor, research agents and conflict explanations.
Without it the package runs on a deterministic heuristic extractor and a stub provider — the governance pipeline is identical.

## What is in the box

| Spec §36 service | Module | What it does |
|---|---|---|
| knowledge-ingestion | `ka/ingestion.py` | Upload / Paste / Write / Link / Connect → immutable `Source` + `SourceVersion`; raw bytes kept under `blobs/` |
| knowledge-extraction | `ka/extraction.py` | PDF / Word / PowerPoint / spreadsheet / Markdown / HTML text; text → candidate statements (LLM or heuristic) |
| knowledge-repository | `ka/repository.py` | One JSON document per object under `ka_storage/<collection>/`; `audit.jsonl`, `events.jsonl` |
| knowledge-governance | `ka/governance.py` | The ONE pipeline (§11): candidate → analyzed → pending review → decision → immutable ACTIVE version |
| knowledge-conflict | `ka/conflict.py` | DUPLICATES / SUPPORTS / EXTENDS / REFINES / CONTRADICTS / CONTEXTUALIZES / SPECIALIZES …; LLM explains, never decides |
| knowledge-versioning | `ka/versioning.py` | §12 status machine; governed versions are immutable; temporal queries |
| knowledge-lineage | `ka/lineage.py` | Graph → "why does this exist?" and Knowledge → "where is this used?" |
| knowledge-scope | `ka/scope.py` | Structure / Parent Domain / Domain / Instance registry; Scope Decision Engine (lowest valid scope) |
| research-orchestrator, research-agents | `ka/research.py` | Coordinator → Domain / Enterprise Content / Standards / Internet / LLM agents → Synthesis → candidates |
| graph-impact | `ka/graph_impact.py` | Dependency-driven impact: affected elements, descendants INHERITED vs OVERRIDDEN |
| graph-change | `ka/graph_change.py` | Graph Change Proposals: propose → validate → approve → apply → rollback; downward propagation that preserves overrides |
| knowledge-search | `ka/search.py` | Structured + lexical search with the §35 filters |
| knowledge-ui-api | `ka/api.py` | FastAPI at `/api/knowledge-acquisition/*`; serves the Knowledge Console at `/console/` |
| — | `ka/graph_adapter.py` | §39 adapter protocol; in-memory reference adapter; `EnterpriseOSGraphAdapter` over `knowledge_worker.graph_store.GraphStore` |
| — | `ka/corrections.py` | §23 "Correct this": lineage resolution → scope suggestion → candidate → governance → graph proposal |
| — | `ka/promotion.py` | §25 upward promotion proposals (never automatic) and §30 instance knowledge states |
| — | `ka/profile.py` | the process profile: a composed, evidence-linked view with coverage against the EOS type grammar (plan-06) |
| — | `ka/runtime_guard.py` | §43: `GRAPH GAP DETECTED` → Knowledge Acquisition Request / Research Mission; retrieval door stays shut |
| — | `ka/console/` | The Knowledge Console: Structure → Domains → Instances; Needs Attention; conflict resolution; research; lineage |

## The two seams the Enterprise Console uses

```http
POST /api/knowledge-acquisition/corrections          "Correct this" on a graph-backed answer (§23)
GET  /api/knowledge-acquisition/lineage/explain?graph_id=…&element_id=…     "Why?" (§47)
POST /api/knowledge-acquisition/runtime/graph-gap     GRAPH GAP DETECTED → acquisition request (§43)
```

Nothing in this API answers runtime questions. Invariant 1 is enforced by `ka.runtime_guard`.

## Integrating with an enterprise-os checkout

```bash
export KA_ENTERPRISE_OS_ROOT=/root/enterprise-os-070626
export KW_STORAGE_ROOT=/root/enterprise-os-dev-data/storage
PYTHONPATH=$KA_ENTERPRISE_OS_ROOT .venv/bin/python -m ka serve
curl -X POST localhost:8011/api/knowledge-acquisition/scopes/sync-from-graph   # domains + pinned instances → scope registry
```

The adapter maps DOMAIN → substructure, INSTANCE → instance, writes lineage to `props.knowledge_lineage` (§40),
refuses any element change without lineage (Invariant 2), and derives §9 inheritance states from `props.realizes`.
Domain writes create a new substructure version; repinning instances is the store's own `repin`.

## Invariants (§46) and where each is pinned

| # | Invariant | Enforced in | Test |
|---|---|---|---|
| 1 | Runtime answers come from the Graph, never KA retrieval | `runtime_guard.RuntimeGuard.retrieve_for_answer` raises | phase4 `::test_N1` |
| 2 | No semantic graph mutation without governed lineage | `graph_adapter.*.validate_change`, `graph_change.validate` | phase3 `::test_N1`, `::test_N2` |
| 3 | Versions immutable; history never overwritten | `versioning.VersioningService.save` | phase1 `::test_P6` |
| 4 | Every graph element names its nugget versions | `props.knowledge_lineage`, `lineage.explain_element` | phase3 `::test_P2`, `::test_P7` |
| 5 | Every nugget knows its dependent elements | `GraphDependency` registry, `lineage.where_used` | phase3 `::test_P2` |
| 6 | Console corrections are knowledge first, graph second | `corrections.CorrectionService.submit` | phase4 `::test_P1` |
| 7 | Knowledge always has explicit scope | `KnowledgeNuggetVersion.scope_type/scope_id` required | phase1 `::test_N1` |
| 8 | Lowest valid scope | `scope.ScopeDecisionEngine` | phase4 `::test_P3` |
| 9 | Downward propagation preserves overrides | `graph_change._changes_from`, `graph_impact` | phase6 `::test_P1` |
| 10 | Promotion proposed, never automatic | `promotion.PromotionService` | phase6 `::test_P4` |
| 11 | Research creates candidates only | `research.*`, `governance.decide` refuses agent ids | phase5 `::test_P1`, phase2 `::test_N2` |
| 12 | Raw content distinct from governed knowledge | `Source`/`SourceVersion` vs `KnowledgeNuggetVersion` | phase1 `::test_P2` |

## Layout

```text
ka/                     the package (see table above)
ka/tests/               test_plan01_phase{1..6}_*.py, test_plan01_api_console.py, test_plan01_enterprise_os_adapter.py
ka/console/             index.html, app.js, styles.css — the Knowledge Console
docs/architecture/      how the code realises the spec
docs/implementation-plans/plan-01.md
docs/trackers/          RESEARCH-TRACKER, QUESTIONS-TRACKER, PENDING-TRACKER, HANDOFF
.claude/skills/         the delivery-pipeline skills copied from enterprise-os-070626
```
