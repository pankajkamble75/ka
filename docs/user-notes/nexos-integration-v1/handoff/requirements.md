# Knowledge Acquisition — NEXOS Integration Requirements v1

**BLOCKING PRECONDITION:** The reviewed `pankajkamble75/knowledge-acquisition` main branch has only a scaffold README; **the active KA implementation is not verified**. A second repository `knowledge-acquisition-2` exists. Do not invent or overwrite a working KA. Identify its actual source/branch/VPS location, pin SHA, document what is implemented, then proceed.

## Ownership
Governed knowledge acquisition, sources, versioned nuggets, human-readable wiki, conflict resolution, review/approval, search, provenance and approved publication. DP owns physical documents/connectors; KW owns graph updates; AgentX owns user intent, approvals UI and execution orchestration.

## Implementation
1. Produce `source-audit.md` with actual source, modules, endpoints, tests, runtime and known gaps. If active KA cannot be found, stop at contract/mock and report BLOCKED.
2. Adopt `agentx-services/v1` with health, capability discovery, invoke, status, input, cancel, typed errors and idempotency; reuse existing APIs through adapter rather than rewriting governance.
3. Register knowledge.search, acquire, review, revise, publish and conflict resolution as **only actually available** capabilities. Long research/acquisition must return durable operation IDs.
4. Use DP for source assets and original bytes; publish governed references and lineage to KW through its graph-change proposal API.
5. Surface KA work in AgentX Growth and Human Tasks. Preserve specialist nugget/wiki UI if present; AgentX links/embeds, not duplicates.
6. Test acquisition → human review → approved publication → KW proposal → visible process knowledge improvement. Test rejected changes, conflicting versions, duplicate event and missing DP.

## Acceptance
Active source and independent service verified; no fake completion. KA can serve governed knowledge through AgentX with full provenance, or is explicitly blocked pending source identification. Only this repo modified.
