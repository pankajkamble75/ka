# Plan 08 - Managed connectors: the contract, a local-folder connector, incremental sync that keeps history

Created: 2026-10-08 18:45 UTC

## Problem Description

`IngestionService.connect()` records a payload a caller already fetched (`ka/ingestion.py:84-87`); nothing enumerates a
source system, notices what changed, or stops when access is revoked. research-01 R10 (note REQ-002) asks for a
provider-agnostic `Connector` contract — authorize, enumerate, fetch, get_permissions, checkpoint, sync_incremental, revoke —
with the local folder as the first implementation (it exercises enumeration, checkpoints and incremental sync with no
credentials) and the cloud/enterprise providers left to Q6.

Desired outcome: a reviewer registers a folder as a connection (scope, authority, visibility), syncs it manually, and sees
new / modified / moved / deleted / permission-changed documents reconciled without losing history: a new file is a new
`Source`; a changed file is a new `SourceVersion` of the same source and is re-extracted; a moved file keeps its source and
updates its location; a deleted file marks the source revoked (its versions stay); a revoked connection refuses to sync.
Dropping a changed SOP into the folder surfaces the contradiction with the earlier version in the Conflicts view (PT8).
No secret is ever stored in a source or nugget; a connection names a `secret_ref` (an environment variable) for providers
that need one.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Raw content immutable; same location+owner with a new checksum → new `SourceVersion` | `knowledge-acquisition.md` §2 | ✅ built | **constrained by it** — sync feeds `IngestionService.connect`, so versioning is the existing rule |
| One governance pipeline; content channel's door is `extract_from_source` | `knowledge-acquisition.md` §4 | ✅ built | **constrained by it** — synced versions are extracted through the same door |
| Visibility: a nugget's visibility is the narrowest of its sources; agents respect clearance | `knowledge-acquisition.md` §10 | ✅ built | **constrained by it** — a connection's visibility is stamped on every source it syncs |
| Q4 — retention of derived knowledge after revocation | `questions/knowledge-acquisition.md` Q4 | ❓ open | this plan does NOT need it: a deleted/revoked source is marked, its versions and derived nuggets are kept and FLAGGED ("source revoked"); retiring them is Q4 |
| Q6 — first cloud and enterprise providers | `questions/knowledge-acquisition.md` Q6 | ❓ open | this plan does NOT need it: the contract and the local folder ship; a provider is a new class behind the same contract |
| Security: upload cap, URL guard | `knowledge-acquisition.md` §10 | ✅ built | **constrained by it** — the folder connector refuses files over `KA_MAX_UPLOAD_MB` and paths outside its root |

**Open questions in the sections this plan touches:** Q4, Q6 — neither blocking (see rows).

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R9, R12 | ✅ shipped | plans 02–07 |
| R10 connectors: contract, local folder first; providers decision | ✅ in scope | Phases 1–4; providers parked Q6 |
| R11 gap routing | ⏭️ deferred | plan-09 |
| R13 / R14 | ⏭️ deferred | Q8 / Q9 parked |
| R15 outbox; R16 benchmark half | ⏭️ deferred | plan-09 |

**Covered here: 1 of 16** (R10). Deferred: 4. Shipped earlier: 10. Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT8 dropping a changed SOP into the watched local folder produces a new `SourceVersion` of the same source, re-runs extraction, and surfaces the contradiction with the prior version's effective dates in the Knowledge nuggets Conflicts view | R10 | **GREEN** — this plan |

## Scope

In: `ka/connectors/__init__.py` (contract, items, registry of connector kinds), `ka/connectors/local_folder.py`,
`ka/connectors/sync.py` (the sync service: reconcile new/modified/moved/deleted/permission-changed; revoke), `ka/model.py`
(`Connection`, `Source.revoked_at`, `Source.connection_id`), `ka/repository.py` (`connections`), `ka/config.py`
(`KA_CONNECTOR_ROOTS` allow-list of folders), `ka/api.py` (five routes), console (Add-knowledge "Connect a folder" card,
connections list with Sync/Revoke, Dashboard counts; sources show "revoked"), `needs_attention` gains
`revoked_sources_with_active_knowledge`, tests, live flow, docs.

Out: cloud/enterprise providers (Q6); scheduled sync (a future plan; manual + API only); retiring derived knowledge on
revocation (Q4); OAuth/consent flows; malware scanning.

## Protected-code impact (summary)

✅ No protected code touched by any phase — new package, ingestion/model/repository/config/api/console additions; `ka/governance.py`,
`ka/graph_change.py`, `ka/runtime_guard.py` and their shared dependencies are not edited. (`extract_from_source` is CALLED by sync,
not changed.)

## Assumptions

- Contract (`ka/connectors/__init__.py`): `ConnectorItem(locator, name, modified_at, size, checksum, visibility, principals,
  deleted=False)`; `Connector` protocol with `kind`, `authorize(connection) -> None` (raises `ConnectorError` when the
  connection cannot be used), `enumerate(connection, cursor=None) -> tuple[list[ConnectorItem], cursor|None]`,
  `fetch(connection, item) -> bytes`, `get_permissions(connection, item) -> dict`, `checkpoint(connection) -> dict`,
  `sync_incremental(connection, checkpoint) -> SyncDelta(new, modified, moved, deleted, permission_changed, checkpoint)`,
  `revoke(connection) -> None`. `CONNECTOR_KINDS = {"local_folder": LocalFolderConnector}`.
- `Connection(id, kind, name, config, owner, scope, authority, visibility, secret_ref, status active|revoked, checkpoint,
  created_at, last_sync_at, last_delta, stats)`. `config` for the folder: `{root, include: ["**/*.md", "**/*.pdf", …]}`. The
  root must be under one of `KA_CONNECTOR_ROOTS` (comma-separated; default `<storage>/inbox`), resolved without symlink escape.
- Local-folder checkpoint = `{locator: {"mtime", "size", "checksum"}}`; delta: locator not in checkpoint → new; same locator,
  different checksum → modified; checksum present under another locator that disappeared → moved; locator in checkpoint but
  absent → deleted; a sidecar `<name>.visibility` file (`PERSONAL|TEAM|DOMAIN|INSTANCE|ENTERPRISE`) overrides the connection's
  visibility; a change in it → permission_changed.
- Sync reconciliation (`SyncService.sync(connection_id, *, by)`): new → `ingestion.connect(connector=kind, locator=…, payload, …)`
  + `extract_from_source`; modified → the same call (the dedupe-by-location rule makes it a new version) + extraction; moved →
  `Source.original_location` updated, no new version (same checksum); deleted → `Source.revoked_at` set, audit `source.revoked`,
  versions untouched; permission_changed → `Source.visibility` updated, audit `source.permission_changed`, derived nuggets
  flagged `analysis["source_visibility_changed"]` (narrowing retroactively is Q4). Every file over `KA_MAX_UPLOAD_MB` is skipped
  with a reason. The delta and counts are stored on the connection and returned.
- `revoke(connection_id, by)`: status `revoked`, audit; `sync` on a revoked connection → `ConnectorError` (409 at the API).
- `needs_attention["revoked_sources_with_active_knowledge"]` lists sources with `revoked_at` that still have ACTIVE nuggets.
- Secrets: `secret_ref` is the NAME of an environment variable; the value is never read into any stored object. The folder
  connector needs none.

## Phases

### Phase 1 - Contract, model, local folder

- `ka/connectors/__init__.py`: `ConnectorItem`, `SyncDelta`, `ConnectorError`, `Connector` protocol, `CONNECTOR_KINDS`, `get_connector(kind)`.
- `ka/connectors/local_folder.py`: `LocalFolderConnector` per the assumptions (root containment, include globs, sidecar visibility).
- `ka/model.py`: `Connection`; `Source.connection_id`, `Source.revoked_at`. `ka/repository.py`: `connections`. `ka/config.py`: `KA_CONNECTOR_ROOTS`.
- **Protected-code touched:** none

### Phase 2 - Sync service

- `ka/connectors/sync.py`: `SyncService(repo, ingestion, governance, auditor, bus)` with `create(kind, name, config, *, owner, scope,
  authority, visibility, secret_ref=None) -> Connection` (authorize first), `sync(connection_id, *, by) -> SyncReport`, `revoke`.
  `ka/service.py`: `self.connectors = SyncService(...)`; `needs_attention` extension.
- `ka/events.py`: names `source.synced`, `source.revoked`, `source.permission_changed`.
- **Protected-code touched:** none

### Phase 3 - API and console

- `ka/api.py`: `POST /connectors`, `GET /connectors`, `GET /connectors/{id}`, `POST /connectors/{id}/sync`, `POST /connectors/{id}/revoke`
  (409 on a revoked connection; 400 on a root outside `KA_CONNECTOR_ROOTS`).
- `ka/console/app.js`: Add-knowledge card "Connect a folder" (root, include, scope, authority, visibility) + connections list with
  last sync counts, Sync and Revoke; source page shows `revoked` and the connection; Dashboard tile "Connections".
- **Protected-code touched:** none

### Phase 4 - Flow and docs

- `e2e/plan08_connector_flow.py`: create a folder under the inbox root with the SOP, connect, sync, change the risk threshold in
  the file, sync again, open Knowledge nuggets → Conflicts: the contradiction is listed.
- `docs/architecture/knowledge-acquisition.md` §2 (connectors paragraph); README; `.env.example`.
- **Protected-code touched:** none

## Code blocks (B1..B8)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/connectors/__init__.py` | contract, items, delta, kinds |
| B2 | `ka/connectors/local_folder.py` | the folder connector |
| B3 | `ka/connectors/sync.py` | create / sync / revoke reconciliation |
| B4 | `ka/model.py` | `Connection`; `Source.connection_id/revoked_at` |
| B5 | `ka/repository.py` | `connections` collection |
| B6 | `ka/config.py`, `ka/events.py` | `KA_CONNECTOR_ROOTS`; three event names (one block each) |
| B7 | `ka/service.py` | wiring; `needs_attention` extension |
| B8 | `ka/api.py`, `ka/console/app.js` | routes; cards and lists (one block each) |

## Deliverables (D1..D10)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `Connector` protocol, `ConnectorItem`, `SyncDelta`, `ConnectorError`, `CONNECTOR_KINDS` | `ka/connectors/__init__.py` | 1 |
| D2 | `LocalFolderConnector` (authorize with root containment, enumerate, fetch, get_permissions, checkpoint, sync_incremental, revoke) | `ka/connectors/local_folder.py` | 1 |
| D3 | `Connection`; `Source.connection_id`, `Source.revoked_at` | `ka/model.py` | 1 |
| D4 | `connections` collection; `KA_CONNECTOR_ROOTS` | `ka/repository.py`, `ka/config.py` | 1 |
| D5 | `SyncService.create / sync / revoke` with the five reconciliations | `ka/connectors/sync.py` | 2 |
| D6 | event names `source.synced`, `source.revoked`, `source.permission_changed` | `ka/events.py` | 2 |
| D7 | `needs_attention["revoked_sources_with_active_knowledge"]` | `ka/service.py` | 2 |
| D8 | five connector routes | `ka/api.py` | 3 |
| D9 | console card, list, source/dashboard surfaces | `ka/console/app.js` | 3 |
| D10 | live flow; architecture §2 paragraph | `e2e/plan08_connector_flow.py`, docs | 4 |

**Total deliverables: 10.**

## Positive Test Cases (P1..P10)

- **P1** — `LocalFolderConnector.enumerate` lists only files matching `include` under the root, with checksum, size, mtime and the connection's visibility; a sidecar `.visibility` file overrides it.
- **P2** — first `sync`: every file becomes a `Source` with `connection_id`, `original_location = <kind>://<locator>`, the connection's scope/authority/visibility; candidates are extracted; `stats.new == n`.
- **P3** — unchanged second sync: delta empty, no new versions, `stats` all zero, `last_sync_at` advanced.
- **P4** — a modified file: the same `Source` gets version 2 (checksum changed), is re-extracted, version 1's text is untouched.
- **P5** — a moved file (same bytes, new path): the source keeps its id, `original_location` updated, no new version.
- **P6** — a deleted file: `Source.revoked_at` set, versions intact, audit `source.revoked`, event emitted; with an ACTIVE nugget derived from it, `needs_attention["revoked_sources_with_active_knowledge"]` lists it.
- **P7** — a sidecar visibility change ENTERPRISE → TEAM: `Source.visibility` updated, audit `source.permission_changed`, derived nuggets flagged `analysis.source_visibility_changed`.
- **P8** — PT8: the SOP is synced and its rule approved; the file's threshold changes from 80 to 70; the second sync yields a candidate that CONTRADICTS the active version, `conflict_open`, listed by `search(filter="Conflicting")` and under `needs_attention["conflicts"]` with both effective dates.
- **P9** — routes: create → list → get → sync → revoke → sync again is 409.
- **P10** — console live flow: connect, sync twice, the Conflicts view lists the contradiction (`e2e/plan08_connector_flow.py`).

## Negative Test Cases (N1..N6)

- **N1** — a root outside `KA_CONNECTOR_ROOTS`, or a symlink escaping it, is refused at `create` (`ConnectorError` / 400); no connection stored.
- **N2** — a file over `KA_MAX_UPLOAD_MB` is skipped with a reason in the report; the sync still completes.
- **N3** — `sync` on a revoked connection raises `ConnectorError` (409); nothing is enumerated.
- **N4** — an unknown connector kind at `create` → `ConnectorError` (400).
- **N5** — a `secret_ref` names an environment variable; the value is never present in the stored connection, source metadata or audit.
- **N6** — a file that fails extraction (binary junk named `.pdf`) is recorded as a FAILED version and does not abort the sync.

## Plan totals

**Research points covered: 1 of 16 · Deliverables: 10 · Positive cases: 10 · Negative cases: 6 · Test cases total: 16 ·
Product tests served: 1 of 8 (1 turns green here).**

## Implementation Notes

- **Re-check this plan against the tree before implementing.** Written after plan-07 landed (`02e2ce0`); confirm
  `IngestionService.connect` still takes a prefetched payload and `_find_existing` keys on `original_location` + owner.
- Tests use `tmp_path` folders under a `KA_CONNECTOR_ROOTS` override; no network.
- The live flow writes under `<storage>/inbox/` (the default connector root) so it works on the running server.
