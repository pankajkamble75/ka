# Knowledge Acquisition — AgentX Integration Technical Requirements

**Target repository:** `pankajkamble75/knowledge-acquisition`  
**Architecture:** AgentX is the unified user-facing orchestrator; KA owns governed knowledge acquisition, editing, provenance and publication.  
**Status:** Integration specification; do not change implementation until active KA source and branch are confirmed.

## 1. Source review and prerequisite
- The reviewed default branch of `knowledge-acquisition` currently exposes a project README, not an independently verifiable KA service. A second repository, `knowledge-acquisition-2`, also exists. Before implementation, identify the authoritative KA code, deployment and UI; record its commit and source paths. Do not silently replace an existing KA implementation with a scaffold.
- Preserve the governed nugget store and the human-readable wiki/document editing model. Nugget editing and wiki editing must synchronize through the governed knowledge lifecycle; avoid direct graph edits.

## 2. Target ownership
- KA owns ingest requests, source references, document versions, nuggets, human-readable wiki pages, review/approval, conflict resolution, provenance, semantic search and governed publication.
- AgentX owns user interaction, enterprise-wide navigation, execution graph, authorization orchestration, human-task dispatch and operation monitoring.
- Data Platform owns original file bytes, physical storage, source connectors and data retrieval; KA accesses them through the Data Platform API. KA retains knowledge semantics and governance, not duplicate physical storage.
- Knowledge Worker owns Process/Domain/Instance graphs and graph navigation. KA publishes governed knowledge and change events through a versioned interface; Knowledge Worker decides graph updates.

## 3. Required independent service
- Package and run KA independently of the original Enterprise OS, AgentX and Knowledge Worker source trees.
- Expose versioned JSON APIs with documented schemas, auth, tenant/instance/domain scope, request/correlation IDs, idempotency, operation status, typed errors and audit provenance.
- Proposed API (new contract, not existing endpoints): `GET /healthz`, `GET /v1/capabilities`, `POST /v1/acquisitions`, `GET /v1/acquisitions/{id}`, `GET /v1/knowledge/search`, `GET /v1/knowledge/{id}`, `POST /v1/knowledge/{id}/revisions`, `POST /v1/knowledge/{id}/review`, `POST /v1/publications`.
- Register capabilities with AgentX: `knowledge.acquire`, `knowledge.search`, `knowledge.read`, `knowledge.revise`, `knowledge.review`, `knowledge.publish`, `knowledge.resolve_conflict`.
- Each capability declares version, JSON Schema input/output, scopes, human approval policy, invocation method, progress/status retrieval, errors and optional UI schema.

## 4. AgentX integration and UI
- KA remains independently operable with its own administrative wiki/nugget editor if already implemented. AgentX provides the unified entry point and may embed or link to KA UI; no copying the entire KA UI into AgentX.
- AgentX submits acquisition/research/edit/review requests and receives durable operation IDs, progress, completion, errors and artifact references. Long tasks must not hold synchronous HTTP requests open.
- Human review requests return typed UI schemas and task IDs; AgentX renders and submits decisions back to KA. KA enforces approvals and owns versioned knowledge state.
- Emit durable events: `knowledge.acquisition.completed`, `knowledge.revision.proposed`, `knowledge.review.required`, `knowledge.publication.approved`, `knowledge.publication.completed`, `knowledge.conflict.detected`. Include event IDs, schema versions, provenance and idempotent delivery/replay.

## 5. Service contracts
- Data Platform: register/store/read source assets and documents via scoped IDs, not filesystem paths; persist checksums, lineage and retention. Avoid duplicate connectors.
- Knowledge Worker: send governed knowledge references, approved nuggets, revision/version identifiers and provenance for domain/instance graph construction; receive graph-update outcome and lineage.
- AgentX: publish a capability manifest and support authorized invocations, asynchronous status, callbacks or polling, cancellation where safe, and structured failures.
- Use an outbox or durable event log for publication/review notifications; do not claim success until the owning service confirms it.

## 6. Implementation steps
1. Identify and inventory the actual KA code/branch, existing routes, data stores, wiki UI, nugget lifecycle and connectors. Write `docs/integration/source-inventory.md`.
2. Create an ownership map and dependency audit. Keep KA domain logic; replace cross-repository imports and physical storage calls with adapters.
3. Implement/extend versioned API and capability manifest, with AgentX-compatible auth and error envelopes.
4. Implement operation tracking and human-task UI schema contract; preserve existing UI and approval workflows.
5. Implement Data Platform client and Knowledge Worker publication contract without direct private imports.
6. Add AgentX mock integration tests and real service integration tests; verify independent startup and unchanged knowledge governance.
7. Document deployment, settings, OpenAPI, examples and failure handling; commit changes only to this repository.

## 7. Acceptance
- KA runs independently and can register capabilities with AgentX.
- AgentX can initiate acquisition, retrieve/search governed knowledge, request and complete review, and monitor outcomes.
- Existing nugget/wiki semantics, versioning, conflict handling and provenance are preserved.
- Data Platform stores physical documents; Knowledge Worker receives only approved, versioned knowledge references/changes.
- No imports from AgentX/Knowledge Worker/Data Platform private code; no original Enterprise OS runtime dependency.
- No changes to PROD or the original Enterprise OS repository.
