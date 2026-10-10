# Source inventory: where the active Knowledge Acquisition lives (research-05 R1)

**Decided by the author, 2026-10-10:** the active KA implementation is **`pankajkamble75/ka`** (this repository). This decision came from
the AgentX integration requirements (`docs/user-research/notes/AgentX-Integration-Technical-Requirements.md`, copied from
`pankajkamble75/knowledge-acquisition@5cab618a`). The `knowledge-acquisition` repository holds the requirements notes, not the
implementation. Enterprise OS (`enterprise-os-070626`) is the system KA was extracted beside; it is **not changed** by this work.

Inventory taken at `519c4ae` (plan-32), 2026-10-10. The project history runs from `7d9504c` (plan-01, 2026-10-08) through plans 01–33.

## What is here

| area | where | what |
|---|---|---|
| Service entry | `ka/__main__.py`, `ka/api.py` (`create_app`), `ka/service.py` (`KnowledgeAcquisition`) | `python -m ka serve` on `KA_BACKEND_PORT` (8011), prefix `/api/knowledge-acquisition` |
| Console routes | `ka/api.py`: 102 routes | sources, nuggets, decisions, conflicts, research missions, corrections, promotions, graph changes, wiki, physical storage, events, audit |
| AgentX surface | `ka/agentx/` (plans 29–30, 33): 16 routes under `/v1` + `/healthz` | capabilities, invoke, operations, input, tasks, register, events, plus the note's aliases. See `docs/integration/openapi-v1.json` |
| Stores | `ka/repository.py`: one JSON file per object under `KA_STORAGE_ROOT` (`ka_storage/`), plus `events.jsonl` and `audit.jsonl` | 25 collections: sources, source_versions, evidence, nuggets, relationships, decisions, corrections, missions, runs, dependencies, proposals, executions, promotions, requests, connections, physical_bindings, dp_outbox, derived_artefacts, operations, wiki_pages, wiki_drafts, wiki_proposals, wiki_publications, bindings, subjects |
| Bytes | `ka/physical.py` (port), `ka/data_platform/` | local blobs, or the Data Platform (`KA_STORAGE_BACKEND=data_platform`, real `/v1` since plan-32) |
| Nugget lifecycle | `ka/vocab.py` `NuggetStatus`, `ka/governance.py` (protected) | INGESTED → EXTRACTED → CANDIDATE → ANALYZED → PENDING_REVIEW → APPROVED → ACTIVE; or REJECTED, SUPERSEDED, OBSOLETE, CONFLICT. Versions are immutable: a change is a new version through `ingest_candidate` |
| Governance | `ka/governance.py` (`decide`, `ingest_candidate`, `propose_revision`) | the only approval path; research agents cannot decide (Invariant 1 and §13) |
| Wiki | `ka/wiki.py`, `ka/wiki_markdown.py`, `ka/wiki_reconcile.py`, console tab in `ka/console/app.js` | articles computed from governed nuggets (Q19); edits become proposals through governance |
| Connectors | `ka/connectors/` (`local_folder.py`, `m365.py`, `sync.py`) | managed sources (plan-08); revocation and permission sync |
| Research | `ka/research.py`, `ka/discovery.py`, `ka/search.py` | missions; Discovery mode uses `ka.search` explicitly (Invariant 1) |
| Graph publication | `ka/graph_change.py` (protected), `ka/graph_adapter.py` | governed graph change proposals; the adapter is Knowledge Worker over HTTP (plan-31), in-memory, or the legacy eos-local import |
| Grammar | `ka/grammar.py` | snapshot by version and digest; from `KA_GRAMMAR_URL` (KW over HTTP), `KA_GRAMMAR_DIR`, or the EOS checkout |
| Settings | `ka/config.py`: 50 declared `KA_*` settings | `python -m ka env` lists them; `config.get` of an undeclared name raises |
| Tests | `ka/tests/` (473 passing on 2026-10-10), `e2e/` live flows | stub LLM, in-memory graph |

## Ownership and dependencies

```
                    ┌──────────── AgentX (orchestrator; :8765) ────────────┐
                    │ pulls GET /v1/capabilities · invokes · polls         │
                    │ renders interactions · receives callbacks · events   │
                    └───────────────┬──────────────────────────────────────┘
                                    │ HTTP, bearer KA_AGENTX_TOKEN
                    ┌───────────────▼───────────────┐
                    │  Knowledge Acquisition (:8011)│  owns: sources, nuggets, versions, evidence,
                    │  pankajkamble75/ka            │  governance decisions, wiki, provenance, lineage
                    └──────┬─────────────────┬──────┘
   HTTP KA_KW_URL/TOKEN    │                 │  HTTP KA_DP_BASE_URL (+ token or principal headers)
   POST /v1/graph-changes  │                 │  uploads · commits · knowledge-bindings · derived assets
   GET /v1/graph-model     │                 │
        ┌──────────────────▼───┐       ┌─────▼─────────────────┐
        │ Knowledge Worker     │       │ Data Platform (:8100) │
        │ (:8101) owns graphs; │       │ owns bytes, assets,   │
        │ decides graph updates│       │ lineage of assets     │
        └──────────────────────┘       └───────────────────────┘
        KW → KA: POST /runtime/graph-gap · POST /v1/knowledge/search
```

| KA depends on | for | how | when absent |
|---|---|---|---|
| AgentX | orchestration, user-facing tasks | AgentX calls KA; KA pushes registration and callbacks through its outbox | KA runs alone; the console works |
| Knowledge Worker | publishing graph changes; the grammar | HTTP (`docs/contracts/knowledge-worker-v1-ka.md`) | graph mode `memory`; grammar unloaded (unresolved bindings) |
| Data Platform | durable bytes, derived assets | HTTP (`docs/contracts/data-platform-v1-real.md`) | local blobs |
| Enterprise OS | nothing by default | `KA_GRAPH_MODE=eos-local` (deprecated) imports `knowledge_worker.graph_store` from a checkout | not needed |
| LLM provider | extraction, research | `KA_LLM_PROVIDER` | the stub provider |

**What KA never does.** It never reads nuggets to answer a runtime question (Invariant 1): runtime answers come from Knowledge Worker's
graph. `knowledge.search` is an explicit discovery read, and it says so. KA never writes another service's store directly, and it never lets
an agent approve.
