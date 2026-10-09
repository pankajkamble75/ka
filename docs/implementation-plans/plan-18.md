# Plan 18 - The PhysicalStore port beneath ingestion, the local store, and the binding record (research-03 R2, R3)

Created: 2026-10-09 10:10 UTC

## Problem Description

Every byte KA keeps is written inline by `IngestionService._ingest` into `<storage>/blobs/<version-id>.<ext>` and recorded as
`SourceVersion.stored_path` (`ka/ingestion.py:168-171`, `ka/model.py:89`); `reextract` reads that path back (`ka/ingestion.py:121-123`).
There is no seam a Data Platform could occupy, and no record that says where a version's bytes are, whether they are available,
or under which tenant. research-03 (§1, §2) decides the shape: a `PhysicalStore` port with `put / get / put_derived`, a
`LocalPhysicalStore` that reproduces today's behaviour and stays the default, a `PhysicalBinding` record keyed by
`(tenant, source, version)` whose `available` status gates the version, `SourceVersion` unchanged, selection by `KA_STORAGE_BACKEND`.

Desired outcome: ingestion through every channel goes through the port; each version has a binding; the local backend writes the
same files as before so nothing visible changes; the console shows where a version's bytes live; `data_platform` as a backend value
is recognised but fails closed to local with a note until plan-19 supplies the HTTP store.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Raw content immutable; same location + owner with a new checksum → new `SourceVersion`; bytes kept beside the JSON | `knowledge-acquisition.md` §2 | ✅ built | **extends it** — the bytes' home becomes a binding to a physical store; the logical rule and the local files are unchanged |
| research-03 R1: this repository is the canonical KA | `research-03.md` §What the code does today | ✅ decided 2026-10-09 | **constrained by it** — the port goes beneath `_ingest` here |
| research-03 R10 interim: `KA_TENANT_ID` as configuration until Q4 | `questions/knowledge-acquisition.md` Q16 (open, interim taken) | ⏳ interim | **constrained by it** — bindings carry `tenant_id` from configuration |
| Protected code | `docs/protected.md` | — | **not touched** — ingestion, model, repository, config, api, console |

**Open questions in the sections this plan touches:** Q16 — interim taken; does not block.

## Research coverage (R1..R14)

Source: [research-03](../research/research-03.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 canonical KA | ✅ decided | by the author's ship invocation; recorded on the tracker |
| R2 `PhysicalStore` port, local store, `KA_STORAGE_BACKEND` | ✅ in scope | Phases 1–2 (the DP HTTP store is plan-19; the images side door is plan-22) |
| R3 `PhysicalBinding` record; availability gate | ✅ in scope | Phases 1–3 |
| R4 outbox | ⏭️ deferred | plan-20 |
| R5, R9 inbound events, revocation reuse | ⏭️ deferred | plan-21 |
| R6 nugget derived artefacts; R7 content read / optional search | ⏭️ deferred | plan-22 |
| R8 connector ownership timing | ⏭️ parked | Q15 (author) |
| R10 tenant interim | ⏭️ parked | Q16 (author confirms); the interim is used here |
| R11 fixtures + fake | ⏭️ deferred | plan-19 |
| R12, R13, R14 | ⏭️ deferred | plan-23 |

**Covered here: 2 of 14.** Deferred: 10 to named plans; parked: 2 author decisions.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 DP backend: same response shape, bytes in the fake, no blob, binding available | R2, R3 | still RED — needs plan-19's store and fake |
| PT2 changed document → KA v2 and a new asset version; v1 untouched | R2, R3 | still RED — needs plan-19 |
| PT3 identical bytes, two owners → two sources, two bindings | R3, R10 | still RED — plan-19 (the local half holds after this plan) |
| PT9 backfill binds all 69 versions | R14 | still RED — plan-23 |

## Scope

In: `ka/physical.py` (new), `ka/model.py` (`PhysicalBinding`), `ka/repository.py` (`physical_bindings`, `binding_for_version`),
`ka/config.py` (`KA_STORAGE_BACKEND`, `KA_TENANT_ID`), `ka/ingestion.py` (`_ingest`, `reextract` through the port; a blocked link gets a
`failed` binding), `ka/service.py` (store selection; dashboard `physical`), `ka/api.py` (`GET /physical/status`; bindings on source
detail), `ka/console/app.js` (version card shows backend · status · sha; Dashboard line), tests, live flow, docs.

Out: the DP HTTP store, fake and fixtures (plan-19); the outbox (plan-20); images (plan-22); backfill of the 69 existing versions
(plan-23) — until then the console shows "legacy — no binding yet" for them.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- `PhysicalRef(backend, asset_id, asset_version_id, sha256, state, locator=None, content_type=None, byte_size=0)`.
  `PhysicalStore` Protocol: `name`, `put(data, *, content_type, sha256, idempotency_key, owner, visibility, tenant_id) -> PhysicalRef`,
  `get(ref) -> bytes`, `put_derived(kind, payload: bytes, *, parent, provenance, idempotency_key) -> PhysicalRef`, `exists(ref) -> bool`.
- `LocalPhysicalStore(root)`: `put` writes `blobs/<idempotency-safe name>` exactly where `_ingest` wrote before (`blobs/<version-id>.<ext>`;
  the caller passes the filename hint), `asset_id = version id`, `asset_version_id = "1"`, `state = "available"`, `locator = path`;
  `put_derived` writes `derived/<kind>/<key>.json`; `get` reads the locator.
- `PhysicalBinding(id, tenant_id, ka_source_id, ka_source_version, source_version_id, backend, dp_asset_id, dp_asset_version_id, sha256,
  extracted_text_asset_id, status in {pending, available, failed, revoked}, reason, owner, visibility, created_at, last_synced_at)`;
  unique on `(tenant_id, ka_source_id, ka_source_version)` — `Repository.bindings_for_version` returns the one row; a second `put_binding`
  for the same key with a different sha raises.
- `select_physical_store(repo)`: `local` → `LocalPhysicalStore`; `data_platform` → `LocalPhysicalStore` with the note
  "data_platform backend requested; HTTP store arrives with plan-19 — using local"; unknown → local with a note. The note is surfaced
  on `GET /physical/status` and the Dashboard.
- `_ingest`: after extraction, `ref = store.put(...)` when bytes exist, binding `available` (local is synchronous) with the sha; when no
  bytes (blocked link) binding `failed` with the block reason; `ver.stored_path = ref.locator` for the local backend (compat).
  `reextract` reads through `store.get(ref)` found via the binding, falling back to `stored_path` for legacy versions.
- Availability: `Repository.version_available(version_id)` = binding exists and is `available` (legacy versions with a `stored_path`
  that exists count as available).

## Phases

### Phase 1 - Port, local store, binding model, config
- `ka/physical.py`; `ka/model.py`; `ka/repository.py`; `ka/config.py`.
- **Protected-code touched:** none

### Phase 2 - Ingestion through the port
- `ka/ingestion.py` `_ingest` + `reextract`; `ka/service.py` wiring.
- **Protected-code touched:** none

### Phase 3 - Surfaces, tests, docs
- `ka/api.py`, `ka/console/app.js`; `ka/tests/test_plan18_physical_store.py`; `e2e/plan18_physical_flow.py`; `.env.example`; a first
  architecture §11 stub naming the port and the binding (plan-23 completes it).
- **Protected-code touched:** none

## Code blocks (B1..B7)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/physical.py` | ref, protocol, local store, selection |
| B2 | `ka/model.py` | `PhysicalBinding` |
| B3 | `ka/repository.py` | collection + helpers |
| B4 | `ka/config.py` | two settings |
| B5 | `ka/ingestion.py` | put through the port; bindings; reextract via get |
| B6 | `ka/service.py`, `ka/api.py` | store selection, dashboard, status route, bindings on detail (one block each) |
| B7 | `ka/console/app.js` | version card pill; Dashboard line |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `PhysicalRef`, `PhysicalStore`, `LocalPhysicalStore`, `select_physical_store` | `ka/physical.py` | 1 |
| D2 | `PhysicalBinding`; `physical_bindings`; `binding_for_version`, `put_binding` (unique key), `version_available` | `ka/model.py`, `ka/repository.py` | 1 |
| D3 | `KA_STORAGE_BACKEND`, `KA_TENANT_ID` | `ka/config.py` | 1 |
| D4 | `_ingest` writes through the port and records a binding (`available` / `failed`) | `ka/ingestion.py` | 2 |
| D5 | `reextract` reads through the port (legacy fallback to `stored_path`) | `ka/ingestion.py` | 2 |
| D6 | `GET /physical/status`; bindings on `GET /sources/{id}`; dashboard `physical` | `ka/api.py`, `ka/service.py` | 3 |
| D7 | console: version card "bytes · backend · status · sha"; Dashboard line | `ka/console/app.js` | 3 |
| D8 | live flow; `.env.example`; architecture §11 stub | `e2e/plan18_physical_flow.py`, docs | 3 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P7)
- **P1** — `LocalPhysicalStore.put` writes the blob at the same path `_ingest` used before and returns an `available` ref with the sha; `get` returns the bytes; `put_derived` writes under `derived/`.
- **P2** — an upload through `_ingest` produces one binding `(tenant, source, 1)` with backend `local`, status `available`, the sha, owner and visibility; `stored_path` is still set.
- **P3** — a changed document → version 2 gets its own binding; version 1's binding and blob are untouched.
- **P4** — research-derived and connector-synced sources get bindings too (every channel passes the funnel).
- **P5** — `reextract` reads the bytes through the port; a legacy version with only `stored_path` still re-extracts.
- **P6** — `GET /sources/{id}` lists bindings; `GET /physical/status` reports backend, tenant, note and counts by status; the dashboard carries `physical`.
- **P7** — live flow: the source page shows "bytes · local · available · sha…" on the version card and the Dashboard shows the physical store line.

## Negative Test Cases (N1..N5)
- **N1** — a blocked link (no bytes) gets a `failed` binding with the reason and writes no blob.
- **N2** — `KA_STORAGE_BACKEND=data_platform` before plan-19 selects local with the note; an unknown value selects local with a note; neither raises.
- **N3** — `put_binding` for an existing `(tenant, source, version)` with a different sha raises; with the same sha it is idempotent.
- **N4** — a version whose binding is `failed` is not `version_available`; `reextract` refuses it with the reason.
- **N5** — a legacy version (no binding) with an existing `stored_path` is available; with a missing file it is not.

## Plan totals

**Research points covered: 2 of 14 · Deliverables: 8 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 4 of 9 (0 turn green here).**

## Implementation Notes
- First plan of the set; written against `aaa2e3b`. No protected code. Restart the live service after upload.
