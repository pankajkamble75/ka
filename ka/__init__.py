"""Knowledge Acquisition — the learning and governance subsystem of Enterprise OS.

Knowledge is acquired and governed first, compiled into the graph second, and consumed through graph
navigation at runtime (spec §1). This package is upstream of the graph: it never answers runtime
questions (§43, Invariant 1).

Module map (spec §36 — logical services, one deployable):

    ka.ingestion      knowledge-ingestion     raw sources in, immutable (§4.1)
    ka.extraction     knowledge-extraction    source → candidate nuggets (§11)
    ka.repository     knowledge-repository    the JSON-backed object store (§37)
    ka.governance     knowledge-governance    the one pipeline every channel converges on (§11, §12)
    ka.conflict       knowledge-conflict      duplicate / support / conflict / extension (§10)
    ka.versioning     knowledge-versioning    immutable versions, supersession, temporal queries (§14)
    ka.lineage        knowledge-lineage       source → nugget → graph, both directions (§15, §16)
    ka.scope          knowledge-scope         lowest valid scope, inheritance states (§7–§9, §24)
    ka.research       research-orchestrator + research-agents (§16, §17)
    ka.graph_impact   graph-impact            dependency-driven impact analysis (§20, §21)
    ka.graph_change   graph-change            proposals, validation, apply, rollback (§22, §39)
    ka.search         knowledge-search        structured + lexical search (§35)
    ka.api            knowledge-ui-api        FastAPI routers for the Knowledge Console (§27–§34)
    ka.console        the Knowledge Console frontend (static HTML/JS)
"""

__version__ = "0.1.0"
