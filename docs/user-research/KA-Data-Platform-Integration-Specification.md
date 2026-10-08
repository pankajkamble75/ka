# KA → Data Platform Integration — Coding Agent Requirements
**Version:** 1.0 | **Date:** 2026-10-08 | **Status:** Proposed, read-only code review
**Audience:** Knowledge Acquisition coding agent
**Companion:** `Data-Platform-Technical-Specification.md`, section 21

## Objective and boundary
Change KA so **Data Platform is the sole managed physical data storage and connector control plane** for source bytes, extracted content, physical nugget payloads, retrieval indexes and associated provenance. KA retains source/nugget *logical* semantics, interpretation, governance/approval, evidence, process knowledge, and Enterprise OS mapping. KA **must never talk directly to GCS**. Data Platform is initially deployed on GCP but exposed to KA only through versioned, cloud-neutral APIs.

**Do not modify production code until contract review and implementation plan are approved.** This file is agent-ready requirements, not a claim that endpoints exist.

## What the code review found (main branches, 2026-10-08)
### Repo `pankajkamble75/knowledge-acquisition`
- `knowledge_acquisition/knowledge_ingestion/service.py`: `IngestionService.ingest_note`, `ingest_file`, `_ingest` calculate SHA-256, extract and create version records. Directly depends on repository connection/SQLite transaction.
- `knowledge_acquisition/knowledge_ingestion/repository.py`: `raw_source_versions.raw_bytes BLOB`, `extracted_text`, global `checksum UNIQUE`; immutable `SourceVersion` via SQLite triggers. This is the main physical-storage replacement point.
- `knowledge_acquisition/knowledge_ingestion/models.py`: stable logical `Source`/`SourceVersion` vocabulary.
- `knowledge_acquisition/knowledge_repository/nugget_store.py`: SQLite-backed nugget versioning with immutable governed state; **keep approval/supersession invariants**.
- `knowledge_acquisition/knowledge_repository/store.py`: generic local SQLite record store.
- `docs/architecture/source-store.md`: documents source dedup and versioning assumptions, including CrossSourceDuplicateError.

### Repo `pankajkamble75/knowledge-acquisition-2`
- `knowledge_acquisition/knowledge/interfaces.py`: existing `SourceStore` Protocol: `ingest(principal, kind, content, metadata, visibility) -> SourceVersion`. This is an excellent boundary for an adapter.
- `knowledge_acquisition/knowledge/records.py`: `SourceVersion(source_id, version, content_hash, extracted_text)` and `Evidence(source_id, source_version, excerpt, locator)`.
- `knowledge_acquisition/knowledge/fakes.py`: `InMemorySourceStore` and nugget fakes used by tests; retain them.
- `knowledge_acquisition/console/sources.py`: HTTP `POST /sources` -> `source_store.ingest` with base64/string support. Keep route and response compatibility.
- `knowledge_acquisition/console/server.py`: JSON `ThreadingHTTPServer` and `X-Principal-Id` local identity lookup (not sufficient by itself for production service authorization).
- `knowledge_acquisition/app.py`: composition root defaulting to `InMemorySourceStore`. Production should inject `DataPlatformSourceStore` explicitly.
- `knowledge_acquisition/knowledge/platform_ports.py`, `platform/access.py`: Principal, Visibility and access policies; map these to DP delegated authorization.

**Important:** Two sibling repositories were inspected. They are not automatically interchangeable or proven to be one active deployment. Identify which is canonical before editing. Do not blindly merge their classes.

## KA design requirements
### KA-DP-001 — New adapter and port
Create a provider-neutral KA boundary, e.g. `knowledge_acquisition/integrations/data_platform/`:
- `contracts.py`: typed `AssetRef`, `SourceBinding`, `DerivedArtifactRef`, `DataPlatformError`, `CapabilitySet`.
- `client.py`: `DataPlatformClient` Protocol / HTTP implementation to DP v1 OpenAPI. No GCP SDK.
- `source_store.py`: `DataPlatformSourceStore` implements existing `SourceStore` Protocol; preserve `SourceVersion` return and id/version/hash expectations.
- `nugget_persistence.py`: adapter for physical nugget representation and lineage, separate from KA approval logic.
- `outbox.py`: durable local pending operations + retry workers for cross-service consistency.
- `fakes.py`: deterministic fake implementing DP client contract, not a mock of external cloud SDKs.

### KA-DP-002 — Source ingestion sequence
1. Authenticate KA caller and resolve validated user/tenant/purpose/scope.
2. Validate source kind, quotas, filename/MIME and scope; allocate or identify KA logical source ID.
3. Call DP `POST /v1/assets/uploads` with idempotency key; stream bytes to upload; commit with SHA-256.
4. Receive opaque `asset_id`, `asset_version_id`, checksum, version metadata.
5. Persist a **KA-to-DP binding** for `(ka_source_id, ka_source_version)` -> DP asset version; avoid storing source bytes in KA production DB.
6. Extract text using KA's extraction service, initially via authorized DP content read; register extracted-text derived asset back to DP with provenance.
7. Publish a KA source-ingested event through durable outbox; return existing public `SourceVersion` shape.
8. On partial failure persist pending state and reconcile; no `SourceVersion` considered fully available before physical commit and binding.

### KA-DP-003 — Logical/physical binding record
Required fields:
```json
{
  "tenant_id": "tenant_demo",
  "ka_source_id": "src-17",
  "ka_source_version": 2,
  "dp_asset_id": "asset_abc",
  "dp_asset_version_id": "av_def",
  "sha256": "64_lowercase_hex_digest",
  "extracted_text_asset_id": "asset_text_17",
  "status": "available",
  "last_synced_at": "2026-10-08T00:00:00Z"
}
```
Unique `(tenant_id, ka_source_id, ka_source_version)`, immutable asset version target once committed. Bind separately from `SourceVersion` record to avoid breaking constructors/tests. Store mapping in DP registry as authoritative and optionally cache in KA with reconciled state.

### KA-DP-004 — Knowledge artifacts
KA generates and governs `NuggetDraft`, `NuggetVersion`, relationships and Evidence, keeping logical IDs. After governing state changes, publish immutable physical nugget-version JSON to DP as derived assets with:
- canonical nugget ID/version, interpretation type, process/activity/entity/event associations
- status, authority, confidence, effective dates, original evidence refs
- source asset/version IDs and evidence locators (page/section/offset where possible)
- transformation/prompt/model versions and correlation/lineage IDs
- effective scope and policy constraints
- no invented claims of verification: candidate/approved/superseded are KA business statuses.

Physical DP storage doesn't replace the KA domain repository or its approval transaction rules. Use outbox or periodic reconciliation to synchronize durable copies.

### KA-DP-005 — Connector ownership
KA calls DP connector registry and `ingestion-jobs`; DP manages secrets, schedules, source connection and bytes. KA can request source types (`url`, `file`, database, enterprise documents) and may supply extraction options, but must not create independent production source connector credentials or duplicate physical connectors. KA agent should mark existing `url_source.py` as compatibility/helper, with new production intake delegated to DP.

### KA-DP-006 — Retrieval and security
Read physical content via DP `GET /v1/assets/.../content` with explicit tenant/user authorization; search via DP `POST /v1/search` for source/derived indexes. KA applies knowledge-level filters (status/authority/scope) as additional constraints. DP must apply physical ACL checks **before** returning content/snippets/search hits. Recheck derived item permissions; effective scope is no broader than the narrowest contributing evidence. Existing KA Visibility ranks do not, alone, establish membership or cross-tenant access.

### KA-DP-007 — Event and failure model
Handle DP events `data.asset.committed.v1`, `data.asset.quarantined.v1`, `data.asset.access_revoked.v1`, `data.asset.deleted.v1`, `data.index.ready.v1`, `data.ingestion.completed.v1`. KA emits `ka.source.registered.v1`, `ka.extraction.completed.v1`, `ka.nugget.candidate_created.v1`, `ka.nugget.approved.v1`, `ka.nugget.superseded.v1`.
- Idempotent handlers keyed by event_id; durable retry/dead-letter; reconcile by DP asset ID and KA version.
- No attempt at cross-service ACID.
- A failed upload must not yield an `available` KA source.
- Deletion, revocation and source-policy tightening require downstream search and nugget visibility reevaluation.

## KA API compatibility requirements
- Keep `/sources` request/response compatible for small inputs, except well-documented errors. Enforce upload size; add streaming/staged workflow for larger files.
- Keep `SourceStore.ingest(...) -> SourceVersion` signature for existing consumers in KA-2.
- Keep `Evidence` references stable and add DP physical refs in a separate mapping.
- Avoid replacing KA's `SourceVersion` version numbering with global DP asset version numbering.
- Keep local fakes and stdlib-only domain tests; HTTP/network code lives in optional adapter package.
- Production configuration requires `DATA_PLATFORM_BASE_URL`, service identity, tenant, timeouts, retries and feature flags. No secret material in logs/config commits.

## Contract examples
Upload sequence:
```http
POST /v1/assets/uploads
Idempotency-Key: ka:tenant_demo:src-17:2
Authorization: Bearer <service-token>
Content-Type: application/json

{"asset_type":"source_document","tenant_id":"tenant_demo","content_type":"application/pdf"}
```
DP returns staging `upload_id`, then KA streams to `/v1/assets/uploads/{upload_id}/content` and commits SHA-256 via `/commit`.
Response sample:
```json
{"asset_id":"asset_abc","asset_version_id":"av_def","sha256":"64_lowercase_hex_digest","state":"available"}
```
Errors must be modeled as `401/403` identity/policy denied; `409` idempotency conflict; `413` too large; `422` checksum/schema invalid; `429` rate limited; `5xx` retryable as appropriate. Error envelope: `code`, `message`, `correlation_id`, `retryable`.

## Required implementation work packages
| Work package | Agent deliverable | Depends on |
|---|---|---|
| KA-01 | Identify canonical KA repo and map all physical writes/reads | none |
| KA-02 | Shared DP v1 schema/typed client + fake | DP OpenAPI v1 |
| KA-03 | DataPlatformSourceStore adapter preserving existing public port | KA-02 |
| KA-04 | SourceBinding persistence/outbox and retry/reconcile | KA-02 |
| KA-05 | Migrate extracted text, nuggets and evidence payloads to DP derived assets | KA-03, KA-04 |
| KA-06 | Replace URL/file acquisition with DP connector/ingestion APIs | DP connector APIs |
| KA-07 | Authorized search/read adapter + revocation handling | KA-02, DP search API |
| KA-08 | Migration/backfill scripts and full acceptance tests | KA-03..07 |

## Migration plan
1. Inventory current SQLite source/version/nugget record counts and verify SHA-256 invariants.
2. Add DP adapter behind existing interfaces; preserve local fake path.
3. Backfill legacy raw bytes to DP without mutating KA logical IDs/versions or source evidence.
4. Publish source and nugget mapping records; validate each transferred byte hash, visibility scope and evidence link.
5. Temporarily dual-record new logical mappings with an outbox (not dual authoritative byte stores); reconcile discrepancies.
6. Route new production ingestion to DP; verify reads, extraction, search and rollback plan.
7. Only after successful checks retire raw-byte BLOB persistence for production. Keep development fakes.

## Acceptance tests
- `POST /sources` ingests note/PDF through DP with unchanged KA SourceVersion response.
- All original bytes land in DP storage and no KA production raw byte BLOB remains authoritative.
- Source modification creates new KA version without overwriting prior DP immutable asset version.
- Identical bytes from different principals/tenants never cause unauthorized source identity collisions.
- Extracted text and approved nugget version resolve to source asset, evidence locator and lineage.
- Unauthorized PERSONAL/TEAM/INSTANCE requests denied across file reads, content search, and nugget results.
- DP unavailable midway: durable retry eventually reconciles; no duplicate source/nugget versions.
- Revocation/tightened policy removes unauthorized index visibility and prevents retrieval.
- Local fake supports all contract tests; GCP integration uses DP API only, no GCS SDK in KA.
- Legacy suite (including source immutability, governance approval and evidence versioning) remains green.

## Non-goals / risks
- Do not move knowledge reasoning, governance approvals or Enterprise OS graph semantics into DP.
- Do not assume source hashes are globally unique source identities: deduplicate physical bytes separately from owner/scope/version.
- Do not use a caller-provided `X-Principal-Id` header as sufficient production authentication.
- Do not assume that both KA repositories are equally active.
- Do not cut over before DP's storage/auth/derived-asset API exists and integration tests pass.

## Contract deliverables to publish jointly
1. DP-authored `openapi/data-platform-v1.yaml` and schemas.
2. KA-maintained adapter package and compatibility tests.
3. Shared fixtures for upload, commit, binding, extraction, derived artifact and deny scenarios.
4. State/event compatibility matrix and migration/backfill report.
5. Versioned change log and rollout/rollback runbook.
