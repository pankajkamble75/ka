# Research 03 - Data Platform as KA's physical store: the real seams, the contract KA needs, and what must not move

Created: 2026-10-09 09:30 UTC
Source note: [KA-Data-Platform-Integration-Specification.md](../user-research/KA-Data-Platform-Integration-Specification.md)
Class: PRODUCT
Severity: MAJOR
Verdict: Aligned with corrections

## What this research is about

The author wants one place to own physical data for the whole Enterprise OS family: the Data Platform (DP), being built on GCP
and exposed only through versioned, cloud-neutral APIs. For Knowledge Acquisition (KA) that means source bytes, extracted text,
the physical copy of each governed nugget version, retrieval indexes and their provenance leave KA's own disk and live in DP,
while KA keeps what makes it KA: the logical `Source` / `SourceVersion` vocabulary, extraction, governance and approval,
evidence, process knowledge and the Enterprise OS mapping. KA must never touch GCS directly.

Two things the note leaves implicit are the real subject here. First, **which KA** — the note's code review inspected two
sibling repositories (`knowledge-acquisition`, `knowledge-acquisition-2`), neither of which is the KA that runs; the deployed KA
is this repository, with a different store and different seams, so every "replacement point" in the note has to be re-found.
Second, **what exists on the other side** — the DP API the note calls does not exist yet in any repository on this server, so
KA's work is a boundary built against a contract and a fake, feature-flagged behind the local store until DP can be called.

## Why it matters

- Today every byte KA holds is on the VPS disk beside the JSON objects: `IngestionService._ingest` writes the original into
  `<storage>/blobs/<version-id>.<ext>` and records `SourceVersion.stored_path` (`ka/ingestion.py:168-171`, model at
  `ka/model.py:89`). Pasted images go to `<storage>/images` (`ka/images.py:27`). Research-derived sources and connector payloads
  take the same path (`ka/ingestion.py:107-113`, `ka/connectors/sync.py:90-95`). Nothing in KA knows a tenant, and
  authorization is a single service token (`ka/security.py:43-56`). None of that is wrong for one VPS and one author; all of it is
  the thing the Data Platform exists to replace.
- Without a boundary, the two repositories will diverge in the one place they must agree: who holds the authoritative bytes and
  how a nugget's evidence resolves to them. The Enterprise OS side already has its own integration note and a decision that DP is
  separate future research (`enterprise-os-070626/docs/research/research-218.md` R11, deferred 2026-10-04).
- The note itself would send a coding agent to edit SQLite triggers and a `raw_bytes BLOB` column that this KA does not have. An
  agent following it literally would build the adapter in the wrong repository.

## What the code does today

### Which KA is canonical

| Candidate | What it is | Evidence |
|---|---|---|
| `/root/ka` → `github.com/pankajkamble75/ka` | the KA that runs: systemd unit, port 8011, 63 sources / 69 versions / 995 nugget versions in `ka_storage` | `git remote -v`; `deploy/enterprise-os-ka.service`; live inventory 2026-10-09 |
| `/root/projects/knowledge-acquisition` | an SDLC-Orchestrator-generated project (README: "Project created with SDLC Orchestrator"), SQLite `raw_source_versions.raw_bytes BLOB` as the note says | `knowledge_acquisition/knowledge_ingestion/repository.py:13-15`; no process, no unit, no port |
| `/root/projects/knowledge-acquisition-2` | the same, with the `SourceStore` Protocol the note calls "an excellent boundary" | `knowledge_acquisition/knowledge/interfaces.py:24-33`; not deployed |

**KA-01 is answered: the canonical KA is this repository.** The two siblings are generated artefacts and nothing runs them. Their
one reusable idea, a `SourceStore` port with `ingest(...) -> SourceVersion`, has a direct counterpart here: `IngestionService._ingest`
is the single funnel every channel passes through (`ka/ingestion.py:141-183`), so the boundary goes **inside** it, not around it.

### Where bytes are written and read

| Path | What happens | Cited |
|---|---|---|
| `_ingest` | SHA-256 over the bytes; dedupe by `(original_location, owner)` only (`_find_existing`), never by global checksum; new `SourceVersion` with `text`, `byte_size`, `stored_path`; blob written beside the JSON | `ka/ingestion.py:141-171`, `:185-190` |
| `reextract` | re-reads `stored_path` and runs the extractor as a NEW version with the same checksum | `ka/ingestion.py:118-137` |
| extraction | in-process over bytes (pypdf, python-docx, python-pptx, openpyxl, OCR), lazily imported | `ka/extraction.py:4-6`, `:125-140` |
| `link()` | fetches through the SSRF guard, bytes into `_ingest` | `ka/ingestion.py:60-80`; `ka/security.py:118` |
| connectors | `connector.fetch` → bytes → `ingestion.connect` → `_ingest` | `ka/connectors/sync.py:90-95` |
| research | `record_derived` writes the agents' text as a RESEARCH-channel source | `ka/ingestion.py:107-113` |
| images | base64 → `<storage>/images/NNNN.png` | `ka/images.py:27`, `:56` |
| nugget payload | one JSON file per `KnowledgeNuggetVersion`; immutability enforced on `SEMANTIC_FIELDS` at write | `ka/repository.py:42-60`; `ka/versioning.py:17` |
| evidence | `Evidence(source_id, source_version_id, locator, span_id, start, end, excerpt, visibility)` | `ka/model.py:98-113`; created at `ka/governance.py:105`, `:130` |
| events | append-only `events.jsonl` with `seq` + `version`, `GET /events?after=` (plan-09) | `ka/repository.py:236-262` |
| search | token scan over the nugget cache; 3.7 s at 100k (plan-09 benchmark) | `ka/search.py:33-45`; `docs/research/benchmarks/store-bench-2026-10-08.md` |
| access | one bearer token for non-loopback peers; no principal, no tenant | `ka/security.py:43-56` |
| lineage | every published element carries `props.knowledge_lineage` (nugget id, version, decision, change ids) | `ka/graph_change.py:171` |

Live inventory (2026-10-09): 69 source versions, 5.4 MB of blobs, 4 versions with no bytes (blocked links), 1,018 evidence records,
995 nugget versions, 4 images. No GCP SDK is imported anywhere in `ka/`.

### What the Data Platform side holds today

- No `openapi/data-platform-v1.yaml`, no `/v1/assets` route and no `data_platform` package exist on this server, in any
  repository (search 2026-10-09). The companion `Data-Platform-Technical-Specification` the note cites is not present either.
- Enterprise OS carries its own note, `docs/user-research/notes/Enterprise-OS-Data-Platform-Integration-Specification.md`
  (2026-10-08), and its data-layer architecture: Structure grammar → Universal Data Library → the Domain's logical Data Graph →
  the Instance's physical layer (`docs/architecture/data-layer.md` §3). research-218 R11 recorded the Data Platform as *separate
  future research* and deferred it (EOS `RESEARCH-TRACKER.md:121`).

So DP is, today, two notes and a deferred row. KA's integration is real work, but its first deliverable is a contract and a fake,
and nothing can cut over until DP answers.

## Architecture this research obeys

| decision | where | bearing on this |
|---|---|---|
| Raw content immutable; same location + owner with a new checksum → new `SourceVersion`; bytes kept beside the JSON | `knowledge-acquisition.md` §2 | **extends it** — the physical home becomes a DP asset version behind a binding; the logical rule is untouched (R2, R3) |
| One governance pipeline; the LLM recommends, a person decides; Invariant 3 | `knowledge-acquisition.md` §4; `docs/protected.md` | constrains R6 — the nugget copy in DP is a derived artefact written on events, never a second approval path |
| Invariant 2: every graph change carries lineage; publication through the store's lifecycle | `knowledge-acquisition.md` §5 | constrains R6 — DP lineage ids are added beside `knowledge_lineage`, not instead of it |
| Connectors behind the `Connector` contract; local folder and Microsoft 365 built; secrets by `secret_ref` | `knowledge-acquisition.md` §2 (plans 08, 14; Q6 decided 2026-10-08) | **this research disagrees openly** with the note's KA-DP-005 — see §Where I differ 2; R8 |
| Revocation is a governance event (Q4): derived knowledge returns to review | `knowledge-acquisition.md` §2, §10 (plan-10) | **extends it** — DP `access_revoked` / `deleted` events feed the same `reopen_for_revocation` (R9) |
| Events as an outbox: `seq`/`version`, `GET /events?after=` | `knowledge-acquisition.md` §9 (plan-09) | **extends it** — a second durable log for pending DP operations, same pattern (R4) |
| Security step 1: token mode; step 2 (identity provider, tenant model) is Q4, open | `knowledge-acquisition.md` §10 | constrains R10 — KA has no tenant today; the binding's `tenant_id` is configuration until Q4 |
| Content is data (Q10): fenced prompts, heuristic-only Internet sources | `knowledge-acquisition.md` §3 (plan-11) | not touched — extraction stays KA's, wherever the bytes live |
| Processes bind to core objects; the Instance's physical layer holds rows and `realized_by` maps | EOS `data-layer.md` §2–§3 | adjacent — KA's bytes are knowledge DOCUMENTS, not instance ROWS; both become DP assets of different types (R12) |
| Data Platform recorded as separate future research | EOS `research-218.md` R11 | the precedent — DP's own API is owned there, not here |
| No KA document owns a physical-storage boundary | — | **silent — proposes a new section** `knowledge-acquisition.md` §11 "Physical storage and the Data Platform" (R13) |

## Reading of the source note

The note asks for a provider-neutral `integrations/data_platform` boundary (contracts, client, a `SourceStore` adapter, nugget
persistence, an outbox, a fake), an ingestion sequence through DP uploads with idempotency keys, a logical-to-physical binding
record, nugget versions published to DP as derived assets, connectors owned by DP, authorized read and search through DP, a
bidirectional event model, API compatibility, and a staged migration ending with the retirement of KA's byte store.

| Claim in the note | Verdict | Evidence |
|---|---|---|
| KA computes SHA-256, extracts and creates version records in an ingestion service | Confirmed, in a different file | `ka/ingestion.py:143-171` |
| The main physical-storage replacement point is `raw_source_versions.raw_bytes BLOB` with a global `checksum UNIQUE` | Contradicted for this KA | this KA has no SQLite; bytes are files at `SourceVersion.stored_path` (`ka/model.py:89`), and checksum is NOT a unique key — dedupe is by location + owner (`ka/ingestion.py:185-190`) |
| An existing `SourceStore.ingest(...) -> SourceVersion` Protocol is the adapter boundary | Partly true | it exists in the undeployed sibling (`knowledge-acquisition-2/.../interfaces.py:24-33`); here the equivalent seam is `IngestionService._ingest` (`ka/ingestion.py:141`) |
| Nugget storage keeps approval/supersession invariants that must be preserved | Confirmed | `ka/versioning.py:17`, `ka/governance.py` (protected, `docs/protected.md`) |
| "Identify which repository is canonical before editing" | Confirmed — and answered | this repository; the siblings are generated and not deployed (§What the code does today) |
| Existing `url_source.py` should become a compatibility helper | Not applicable | this KA's URL path is `link()` plus discovery with SSRF guard, robots and budget (`ka/ingestion.py:60`, `ka/discovery.py`) |
| KA should not create independent production connector credentials | **Disagree in part** | Q6 (2026-10-08) decided an M365 connector in KA; plan-14 built it with `secret_ref` naming an environment variable — see §Where I differ 2 |
| Existing Visibility ranks do not establish membership or cross-tenant access | Confirmed | `ka/security.py:43-56` — one token, no principal; Q4 open |
| Outbox for cross-service consistency is new | Partly true | the event log is already an outbox (`ka/repository.py:236-262`); a pending-OPERATIONS log is new |
| Source hashes are not globally unique identities | Confirmed, already the rule | `ka/ingestion.py:185-190` |
| DP API endpoints exist | Not claimed by the note, and not true | no OpenAPI, route or package anywhere on the server |

## The research

### 1. The boundary goes inside `_ingest`, as a `PhysicalStore` port

Every byte KA keeps passes through `IngestionService._ingest` or two small side doors (`reextract`, images). That makes the right
seam a **`PhysicalStore` port** with exactly the operations KA performs on bytes:

- `put(bytes, *, content_type, sha256, idempotency_key, owner, visibility, tenant) -> PhysicalRef(asset_id, asset_version_id, sha256, state)`
- `get(ref) -> bytes` (for `reextract` and the console's "view source")
- `put_derived(kind, payload_json, *, parent_ref, provenance) -> PhysicalRef` (extracted text, nugget versions, evidence bundles)
- `revoke_listener` / `events(after)` for the DP → KA direction

Two implementations: `LocalPhysicalStore` (today's `blobs/` dir and the JSON files, unchanged behaviour, the default) and
`DataPlatformPhysicalStore` (HTTP to DP v1, no cloud SDK). A `FakeDataPlatform` implements the DP **wire contract** in memory for the
tests — a fake of the API, not of a cloud SDK, as the note asks. Selection by `KA_STORAGE_BACKEND=local|data_platform`.

The note's `DataPlatformSourceStore implements SourceStore` maps onto this one-to-one, except that in this KA the port is beneath
the ingestion funnel rather than wrapping it, which keeps every channel (upload, paste, note, link, connectors, research, corrections)
on one path without touching their call sites.

### 2. The binding is a separate record, and `stored_path` becomes one of its forms

The note's `SourceBinding` fields fit as a new collection `bindings_physical` keyed by `(tenant_id, ka_source_id, ka_source_version)`:
`dp_asset_id`, `dp_asset_version_id`, `sha256`, `extracted_text_asset_id`, `status` (`pending | available | failed | revoked`),
`last_synced_at`, plus `backend` (`local | data_platform`) so a local blob is a binding too. `SourceVersion` keeps `stored_path`
for the local backend and gains nothing — the note is right that the version record's constructor must not change (every test and
the console read it).

The rule the note states and this KA already keeps: **a `SourceVersion` is not available until its binding is `available`.** Today
that is trivially true because the blob write precedes `source_versions.put` (`ka/ingestion.py:167-172`). With DP it becomes a state:
`_ingest` writes the version with `extraction_status=PENDING` and a `pending` binding, the upload runs, and only the commit flips both.
Extraction can run immediately from the in-memory bytes (KA has them), so candidates are not delayed by the upload; what waits is
"available".

### 3. Idempotency and dedupe: KA's rule stands, DP's is additional

The note's idempotency key `ka:<tenant>:<source>:<version>` is exactly `(tenant, ka_source_id, ka_source_version)`, which is already
the natural key of a `SourceVersion` here. KA's dedupe by `(location, owner)` is a **logical** rule (two owners may hold the same
bytes as two sources) and stays. DP may deduplicate physical bytes by SHA-256 across those two bindings; KA never relies on it. This
is the note's own non-goal ("do not assume source hashes are globally unique source identities") made concrete.

### 4. The pending-operations outbox is a second log, not a change to the first

plan-09 made `events.jsonl` an outbox for consumers. The DP integration needs the other direction: operations KA owes DP (upload,
commit, derived-asset publication, revocation acknowledgement) that must survive a crash and a DP outage. Same pattern, separate
file: `dp_outbox.jsonl` with `op_id`, `kind`, `payload`, `attempts`, `next_at`, `state`, and a worker loop (the plan-17 thread pattern)
that retries with backoff and marks dead-letter after N attempts. Reconciliation is by `(asset_id, ka version)`; a crash between
upload and commit is recovered by re-reading DP's upload state through the idempotency key. No cross-service transaction is attempted.

### 5. KA's events map onto the note's names without renaming

KA's event vocabulary is a closed list guarded at emit (`ka/events.py:16-36`). The note's `ka.source.registered.v1`,
`ka.extraction.completed.v1`, `ka.nugget.candidate_created.v1 / approved.v1 / superseded.v1` are **wire names** on DP's bus; KA's
`source.ingested`, `source.updated`, `knowledge.candidate.created`, `knowledge.approved`, `knowledge.superseded` are the internal
names. The outbox worker translates when it publishes; the internal list does not change. In the other direction DP's
`data.asset.committed.v1` flips the binding to `available`; `data.asset.quarantined.v1` and `data.asset.access_revoked.v1` call
`governance.reopen_for_revocation` (plan-10) so derived knowledge returns to review; `data.asset.deleted.v1` marks the source
revoked exactly as a deleted connector file does today (`ka/connectors/sync.py:126-135`); `data.index.ready.v1` is informational
until KA uses DP search. Handlers are idempotent on `event_id`, recorded in the same `events.jsonl` with the inbound seq.

### 6. The nugget's physical copy is a derived artefact, written on events, never a second approval path

Governance is protected (`docs/protected.md`); the physical copy must not touch it. The pattern plan-11 established — a subscriber on
`knowledge.approved` registered in the service (`ka/service.py`) — carries this: on `knowledge.candidate.created`, `knowledge.approved`,
`knowledge.superseded` and the plan-10 retirements, the outbox enqueues `put_derived("nugget_version", payload)` where the payload is the
note's list: canonical id and version, interpretation (`knowledge_type`, subject/predicate/object, binding status and grammar digest),
status, authority, confidence, effective dates, evidence refs with span/offsets, source asset/version ids from the bindings,
`extraction_version`, model and prompt versions from the run, correlation ids (`governance_decision_id`, `graph_change_id`), scope and
visibility. The payload is immutable per `(canonical_id, version, status)` — a status change writes a new derived version, never an
overwrite, which matches both Invariant 3 and DP's immutable asset versions. KA's JSON files remain the domain repository; DP holds the
durable copy and the index.

### 7. Read and search through DP: later, and under KA's own filters

Reading content through DP is needed the moment bytes stop living locally (`reextract`, "view source", the connector's re-fetch).
Search through DP is **not** needed for correctness: KA's search is over governed nuggets and their statements, which KA holds. It
becomes valuable when DP indexes extracted text and KA wants full-text over sources — the plan-09 benchmark shows the local token scan
is the one slow path at 100k (3.7 s). When DP search is used, KA applies status / authority / scope filters on top, as the note says,
and DP applies physical ACLs first. The visibility rule stays KA's: a nugget is never wider than its narrowest source.

### 8. Connectors: the contract is the seam; ownership moves when DP can take it

The note says DP owns connector registration, secrets and execution, and KA should stop creating production connector
credentials. Two facts stand against doing that now: the author decided Microsoft 365 as KA's first provider on 2026-10-08 (Q6) and
plan-14 built it behind the plan-08 `Connector` contract with the secret named by `secret_ref`; and DP's connector registry does not
exist. The right shape is the one the contract already allows: a **`data_platform` connector kind** whose `enumerate` / `fetch` /
`sync_incremental` call DP's connector registry and `ingestion-jobs`, with DP holding the secret. When it exists, KA's local-folder
and M365 connectors become the compatibility path the note describes. Until then they are the only path, and retiring them would
remove a decided capability for an API that is not there. This is a `decide` for the author (R8), stated as open disagreement with
KA-DP-005's timing, not its destination.

### 9. Tenant and principal: a configuration constant until Q4

Every DP call carries `tenant_id` and a caller identity. KA has one service token and no tenant (`ka/security.py:43-56`); the identity
provider and tenant model are Q4's open half. The integration can proceed with `KA_TENANT_ID` as configuration and the service identity
as the DP principal, recording the KA `owner` and `visibility` on each binding so DP's ACLs can be derived later. The note's "resolve
validated user/tenant/purpose/scope" per request is Q4's work, in both repositories, and is named here so nobody reads this research as
having solved it.

### 10. Migration is small and should be rehearsed, not staged for months

69 versions and 5.4 MB. A backfill is one script: for each `SourceVersion` with `stored_path`, upload with idempotency key
`ka:<tenant>:<source>:<version>`, verify the returned SHA-256 equals the recorded one, write the binding `available`; the 4 versions
without bytes (blocked links) get bindings `failed` with the block reason, which the console already shows. Evidence and nuggets
need no migration — they reference `(source_id, source_version_id)`, which do not change — but each ACTIVE nugget version gets a
derived-asset publication through the outbox. The note's dual-record phase is right in spirit; here it is one flag flip with the
local backend kept as rollback: `KA_STORAGE_BACKEND=local` is never removed from the code, only from production configuration.

### 11. The contract KA needs from DP, as a test fixture

Because DP v1 does not exist, KA should publish the subset it needs as executable fixtures: upload → content → commit → asset
version; content read with 403 on denial; derived-asset put with provenance; the six inbound event shapes; the error envelope
(`code`, `message`, `correlation_id`, `retryable`; 401/403/409/413/422/429/5xx). The `FakeDataPlatform` implements exactly this
subset, and the same fixtures become DP's acceptance tests. This is the one deliverable that unblocks both repositories.

### 12. Two kinds of DP asset, and what KA is not

The Enterprise OS architecture puts the Instance's physical data — rows, `realized_by` field maps — on the Data Platform
(`data-layer.md` §3). KA's bytes are knowledge **documents**: SOPs, policies, pages, notes. Both are DP assets, of different
`asset_type`s (`source_document`, `extracted_text`, `nugget_version` for KA; tables and snapshots for EOS). KA must not become a
data-row store, and EOS must not read KA documents as data. The shared thing is the lineage id vocabulary, so a graph node's
`knowledge_lineage` and a DP asset's provenance can be joined.

## Where I differ

1. **The replacement point is wrong for this KA.** The note names SQLite triggers and a `raw_bytes BLOB` column that exist only in an
   undeployed generated project. In the deployed KA the seam is `IngestionService._ingest` and `SourceVersion.stored_path`
   (`ka/ingestion.py:141-171`, `ka/model.py:89`); `reextract` and images are the two side doors. KA-01's answer is this repository.
2. **Connector ownership (KA-DP-005), on timing not destination.** Q6 (2026-10-08) and plan-14 put a Microsoft 365 connector in KA with
   secrets by environment variable; DP's connector registry does not exist. Build the `data_platform` connector kind behind the
   existing contract and move ownership when DP can hold it; do not retire a decided capability for an API that is not there (R8).
3. **"Extract via authorized DP content read" is unnecessary at ingestion time.** KA has the bytes in hand when it uploads; extracting
   from them and publishing the text as a derived asset avoids a round trip and a failure mode. The DP read path is for later reads
   (`reextract`, viewing), not for first extraction.
4. **Search through DP is optional, not a requirement of the integration.** KA's search is over governed knowledge it holds; DP search
   is a performance and full-text improvement to take when DP indexes exist (§7).
5. **The migration plan is sized for a large estate.** Here it is 69 versions and 5.4 MB: one rehearsed backfill and a flag, with the
   local backend as the standing rollback (§10).

## Open questions

- **Who publishes DP v1 first?** This research proposes KA publishes the subset it needs as fixtures (R11); the author decides whether DP
  adopts them or hands KA an OpenAPI to generate from (R14).
- **Tenant and principal** — Q4 remains open; `KA_TENANT_ID` as configuration is the interim (R10).
- **Should the physical copy of a nugget version include the evidence excerpts verbatim?** They are quoted source text, so they
  inherit the source's visibility; putting them in the derived asset is convenient for DP indexing and raises the asset's sensitivity to
  the narrowest source. Recommendation: include, with visibility stamped (R6 carries it as an assumption to confirm).

## What this does not cover

DP's own design, storage, auth and search (DP's repository); the Enterprise OS side of the integration (its own note and research);
the identity provider and tenant model (Q4); EOS gap routing (Q7). Implementation phasing belongs to `create-implementation-plan`.

## Research points (14)

| # | Research point | Kind | Class | Severity | Where argued |
|---|---|---|---|---|---|
| R1 | The canonical KA is this repository; the two sibling projects are generated and undeployed; every DP seam is re-found here (`_ingest`, `stored_path`, `reextract`, images) | decide | PRODUCT | MAJOR | §What the code does today, §Where I differ 1 |
| R2 | A `PhysicalStore` port beneath `_ingest` with `put / get / put_derived`, a `LocalPhysicalStore` (today's behaviour, default) and a `DataPlatformPhysicalStore` (HTTP to DP v1, no cloud SDK), selected by `KA_STORAGE_BACKEND` | build | PRODUCT | MAJOR | §1 |
| R3 | A separate `PhysicalBinding` record keyed by `(tenant, source, version)` with `backend`, DP asset ids, sha256, text-asset id, `status`; "available" gates the version; `SourceVersion` unchanged | build | PRODUCT | MAJOR | §2 |
| R4 | A durable pending-operations outbox (`dp_outbox.jsonl`) with a retry worker, backoff and dead-letter; reconciliation by idempotency key `ka:<tenant>:<source>:<version>`; no cross-service transaction | build | PRODUCT | MAJOR | §3, §4 |
| R5 | Inbound DP events (`committed`, `quarantined`, `access_revoked`, `deleted`, `index.ready`, `ingestion.completed`) handled idempotently by `event_id`: bindings flip, revocation feeds plan-10's re-review, deletion marks the source revoked | build | PRODUCT | MAJOR | §5 |
| R6 | Nugget versions published to DP as immutable derived artefacts on `knowledge.*` events through a service subscriber (never inside governance), with the note's payload, evidence spans and lineage ids; a status change is a new derived version | build | PRODUCT | MAJOR | §6 |
| R7 | Content read through DP for `reextract` and "view source" when the backend is DP; DP search as an optional, later retrieval path under KA's own status/authority/scope filters | build | PRODUCT | MINOR | §7 |
| R8 | Decide connector ownership timing: keep KA's local-folder and M365 connectors as the only path until DP's connector registry exists; then add a `data_platform` connector kind behind the plan-08 contract and demote the others to compatibility (open disagreement with KA-DP-005's timing) | decide | PRODUCT | MAJOR | §8, §Where I differ 2 |
| R9 | DP revocation and deletion events reuse `reopen_for_revocation` and the plan-08 revocation path, so one rule governs connector deletions and DP revocations alike | build | PRODUCT | MAJOR | §5 |
| R10 | `KA_TENANT_ID` and the service identity as the DP principal until Q4 answers the identity provider and tenant model; `owner` and `visibility` recorded on every binding | decide | PRODUCT | MAJOR | §9 |
| R11 | KA publishes the DP v1 subset it needs as executable fixtures and a `FakeDataPlatform` that implements them: upload/content/commit, denied read, derived put, six events, error envelope | build | PRODUCT | MAJOR | §11 |
| R12 | Two DP asset families: KA's `source_document` / `extracted_text` / `nugget_version` beside EOS's instance data assets; shared lineage ids; KA never stores rows and EOS never reads documents as data | decide | PRODUCT | MINOR | §12 |
| R13 | A new architecture section (§11 "Physical storage and the Data Platform") owning the port, the binding, the outbox, the event mapping and the asset families; indexed | build | PRODUCT | MINOR | §Architecture |
| R14 | Backfill rehearsal: one script over 69 versions with SHA verification, `failed` bindings for the 4 byte-less versions, derived publication of ACTIVE nuggets; `KA_STORAGE_BACKEND=local` stays in code as the rollback | build | PRODUCT | MINOR | §10 |

**Total research points: 14.** 10 `build`, 4 `decide`, 0 `investigate`.

**Class and severity split:** 14 `PRODUCT`, 0 `TEST INFRASTRUCTURE`; 0 `CRITICAL`, 10 `MAJOR`, 4 `MINOR`.

**Coverage of the source note:** covers all seven KA design requirements (KA-DP-001..007), the API compatibility list, the contract
examples, all eight work packages (KA-01 answered here; KA-02..07 become R2–R11; KA-08 is R14), the migration plan and the acceptance
tests. Not covered: the joint contract deliverables that DP must author (OpenAPI, change log, runbook) — named in §What this does not cover.

## Product tests (9)

| # | Product test | Proves | Runnable today? |
|---|---|---|---|
| PT1 | With `KA_STORAGE_BACKEND=data_platform` against the fake, uploading a note and a PDF returns the same `/sources/upload` response shape as today, the bytes are in the fake's asset store, no file is written under `<storage>/blobs`, and the version's binding is `available` with the matching SHA-256 | R2, R3 | no — needs the port, store and binding plans |
| PT2 | Re-uploading a changed document creates KA version 2 and a new DP asset version; the first asset version is unchanged and still readable | R2, R3 | no |
| PT3 | Identical bytes from two owners produce two KA sources and two bindings; neither can read the other's through DP | R3, R10 | no |
| PT4 | An approved nugget resolves, through its DP derived artefact, to the source asset version, the evidence span and the governance and graph-change ids | R6 | no |
| PT5 | A PERSONAL source's content and its nuggets are denied through the DP read path to a caller without rights, and the fake records the denial | R7, R10 | no |
| PT6 | DP unavailable between upload and commit: the version stays unavailable, the outbox retries, the commit lands once, and no duplicate source, version or derived artefact exists afterwards | R4 | no |
| PT7 | A `data.asset.access_revoked.v1` event puts every ACTIVE nugget derived from that source back into review and a `deleted` event marks the source revoked, through the same path a deleted connector file takes | R5, R9 | no |
| PT8 | The whole contract suite runs against the fake with no network, and no module under `ka/` imports a Google Cloud SDK | R11 | no — the guard half could run today and would pass trivially; it counts only with the suite |
| PT9 | The backfill rehearsal binds all 69 versions (65 `available`, 4 `failed` with reasons) with SHA-256 verified, and the legacy suite stays green with the backend set to `local` | R14 | no |

**Total product tests: 9.** None runnable today; all wait on the plans that build R2–R6 and R11, and every live form waits on a DP endpoint that does not yet exist.
