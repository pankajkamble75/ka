# Plan 19 - The Data Platform contract KA needs: executable fixtures, a wire-level fake, and the HTTP physical store (research-03 R11 + R2's DP half)

Created: 2026-10-09 11:40 UTC

## Problem Description

The Data Platform API does not exist anywhere yet (research-03 §What the code does today). plan-18 put the port and the binding in
place with the local store; `KA_STORAGE_BACKEND=data_platform` fails closed to local with a note. research-03 §11 decides what
unblocks both repositories: KA publishes the DP v1 subset it needs as executable fixtures, a `FakeDataPlatform` that implements exactly
that subset at the wire level (HTTP shapes, status codes, the error envelope), and `DataPlatformPhysicalStore` — the HTTP implementation
of the port that talks to DP v1 with no cloud SDK.

Desired outcome: with `KA_STORAGE_BACKEND=data_platform` and a base URL pointing at the fake served over real HTTP, ingesting a note
through the console returns the same response shape, writes no file under `<storage>/blobs`, and the version's binding is `available`
with DP asset ids and the matching SHA-256 (PT1); a changed document makes a new asset version and leaves the first untouched (PT2);
identical bytes from two owners are two sources and two bindings (PT3); a denied read is a 403 the fake records (PT5's physical half);
the suite runs against the fake with no network and no module under `ka/` imports a Google Cloud SDK (PT8).

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §11 the port and the binding; `data_platform` fails closed until the HTTP store exists | `knowledge-acquisition.md` §11 (plan-18) | ✅ built | **completes it** — the HTTP store arrives; `select_physical_store` honours `data_platform` when `KA_DP_BASE_URL` is set |
| research-03 §3: idempotency key `ka:<tenant>:<source>:<version>`; KA dedupes logically, DP may dedupe bytes | `research-03.md` §3 | ⏳ decided | **builds it** — the key is the upload's `Idempotency-Key`; the fake enforces 409 on a key reused with different bytes |
| No credential in a stored object; secrets read at call time | `knowledge-acquisition.md` §10 | ✅ built | **constrained by it** — the DP service token is read from `KA_DP_SERVICE_TOKEN` when a request is made; never in a binding, log or payload |
| research-03 R10 interim: `KA_TENANT_ID`; service identity as the DP principal | Q16 (open, interim) | ⏳ interim | **constrained by it** — every DP call carries `tenant_id` and the service token; `owner` travels as `X-KA-Owner` so the fake can model ACLs |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** Q16 — interim; does not block.

## Research coverage (R1..R14)

Source: [research-03](../research/research-03.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 | ✅ decided | tracker |
| R2 port + local store | ✅ shipped (plan-18); **the DP HTTP store half lands here** | Phase 2 |
| R3 binding | ✅ shipped (plan-18) | — |
| R4 outbox | ⏭️ deferred | plan-20 — here a failed upload yields a `failed` binding and no retry |
| R5, R9 | ⏭️ deferred | plan-21 — the fake already serves the six event shapes so plan-21 has something to read |
| R6, R7 | ⏭️ deferred | plan-22 |
| R8, R10 | ⏭️ parked | Q15, Q16 |
| R11 fixtures + fake | ✅ in scope | Phases 1, 3 |
| R12, R13, R14 | ⏭️ deferred | plan-23 |

**Covered here: 1 of 14 new (R11) plus R2's DP half.** Deferred: 9; parked: 2.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 DP backend: same response, bytes in the fake, no blob, binding available with the SHA | R2, R3 | **GREEN** (against the fake over HTTP) |
| PT2 changed document → new asset version; v1 untouched | R2, R3 | **GREEN** |
| PT3 identical bytes, two owners → two sources, two bindings, neither readable as the other | R3, R10 | **GREEN** |
| PT5 PERSONAL content denied through the DP read path | R7, R10 | **physical half GREEN** — the nugget half is plan-22 |
| PT8 contract suite runs against the fake with no network; no GCP SDK under `ka/` | R11 | **GREEN** |

## Scope

In: `ka/data_platform/__init__.py` (errors, `DataPlatformClient`), `ka/data_platform/store.py` (`DataPlatformPhysicalStore`),
`ka/data_platform/fake.py` (`FakeDataPlatform` — wire-level, plus `serve()` for a real local HTTP server), `ka/config.py`
(`KA_DP_BASE_URL`, `KA_DP_SERVICE_TOKEN`, `KA_DP_TIMEOUT`, `KA_DP_RETRIES`), `ka/physical.py` (selection honours `data_platform`),
`docs/contracts/data-platform-v1-ka-subset.md` + `ka/tests/fixtures/dp_contract/*.json` (the subset as fixtures), tests, a live flow that
starts the fake over HTTP and a second KA server on the DP backend, `.env.example`, architecture §11.

Out: retries/outbox (plan-20 — one attempt here); consuming inbound events (plan-21); derived publication of nuggets (plan-22);
DP search; any GCP SDK.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- Wire subset (DP v1 as KA needs it), all under `KA_DP_BASE_URL`, `Authorization: Bearer <KA_DP_SERVICE_TOKEN>`, `X-KA-Tenant`:
  `POST /v1/assets/uploads` (`Idempotency-Key`, body `{asset_type, tenant_id, content_type, owner, visibility}`) → `{upload_id}`;
  `PUT /v1/assets/uploads/{upload_id}/content` (bytes) → 204; `POST /v1/assets/uploads/{upload_id}/commit` (`{sha256}`) →
  `{asset_id, asset_version_id, sha256, state}`; `GET /v1/assets/{asset_id}/versions/{asset_version_id}/content` (`X-KA-Owner`) → bytes or
  403; `POST /v1/assets/derived` (`Idempotency-Key`, `{asset_type, parent_asset_id, parent_asset_version_id, provenance, payload_b64}`) →
  asset version; `GET /v1/events?after=<seq>` → `{events:[{event_id, seq, type, asset_id, asset_version_id, at}], next_after}`.
  Errors: `{code, message, correlation_id, retryable}` with 401/403/409/413/422/429/5xx.
- `FakeDataPlatform.handle(method, path, headers, body) -> (status, headers, body)`; state in memory; idempotent uploads by key (same key +
  same sha → same asset version; different sha → 409 `idempotency_conflict`); commit with a wrong sha → 422; ACL: a `visibility=PERSONAL`
  asset is readable only by its owner (`X-KA-Owner`), tenant mismatch → 403; `fail_next(n, status=503)` for outage tests;
  `revoke(asset_id)` / `delete(asset_id)` append events. `serve(host, port)` runs it on `http.server` for the live flow.
- `DataPlatformClient(base_url, http=None, token_env="KA_DP_SERVICE_TOKEN", timeout, retries=1)`; the default `http` is httpx; the fake is
  injected as `http=fake.as_http()` in unit tests and reached over real HTTP in the flow.
- `DataPlatformPhysicalStore.put` → create upload (key `ka:<tenant>:<source>:<version>`), put content, commit; `get` → content with
  `X-KA-Owner`; `put_derived` → derived; `exists` → `GET …/content` HEAD-like (200/404). `from_config(root)` raises `ImportError`-shaped
  `ConfigurationError` when the base URL is unset so `select_physical_store` fails closed with the note "KA_DP_BASE_URL unset".
- Fixtures are JSON files the fake is checked against (request → expected response) so DP can run the same files.

## Phases

### Phase 1 - Contract: errors, client, fake, fixtures, contract document
- `ka/data_platform/__init__.py`, `ka/data_platform/fake.py`, `ka/tests/fixtures/dp_contract/`, `docs/contracts/data-platform-v1-ka-subset.md`.
- **Protected-code touched:** none

### Phase 2 - The HTTP store and selection
- `ka/data_platform/store.py`; `ka/physical.py` selection; `ka/config.py`.
- **Protected-code touched:** none

### Phase 3 - Tests, live flow, docs
- `ka/tests/test_plan19_data_platform.py`; `e2e/plan19_dp_flow.py` (fake over HTTP on 127.0.0.1:8099 + a second KA server on 8012 with
  the DP backend; the console pastes a source and the version card says `bytes · data_platform · available`); `.env.example`;
  architecture §11.
- **Protected-code touched:** none

## Code blocks (B1..B6)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/data_platform/__init__.py` | errors + client |
| B2 | `ka/data_platform/store.py` | the HTTP physical store |
| B3 | `ka/data_platform/fake.py` | the wire-level fake + server |
| B4 | `ka/physical.py` | `data_platform` selection |
| B5 | `ka/config.py` | four settings |
| B6 | `ka/console/app.js` | none needed — the plan-18 pill already shows backend/status (declared as no change; see Deliverables) |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `DataPlatformError`, `DataPlatformClient` (uploads, content, commit, derived, events; envelope parsing; token at call time) | `ka/data_platform/__init__.py` | 1 |
| D2 | `FakeDataPlatform` (idempotency, 409/422/403, ACL by owner+visibility+tenant, `fail_next`, `revoke`/`delete` events, `as_http`, `serve`) | `ka/data_platform/fake.py` | 1 |
| D3 | contract fixtures + the contract document | `ka/tests/fixtures/dp_contract/`, `docs/contracts/data-platform-v1-ka-subset.md` | 1 |
| D4 | `DataPlatformPhysicalStore` + `from_config` | `ka/data_platform/store.py` | 2 |
| D5 | `select_physical_store` honours `data_platform` when configured; fails closed with "KA_DP_BASE_URL unset" otherwise | `ka/physical.py` | 2 |
| D6 | `KA_DP_BASE_URL`, `KA_DP_SERVICE_TOKEN`, `KA_DP_TIMEOUT`, `KA_DP_RETRIES` | `ka/config.py` | 2 |
| D7 | live flow (fake over HTTP + DP-backed KA server); `.env.example`; architecture §11 | `e2e/plan19_dp_flow.py`, docs | 3 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P8)
- **P1** — the fake answers every fixture exactly (request → response), so the files are an executable contract.
- **P2** — client round trip against the fake: upload → content → commit returns asset ids and the SHA; the token header is present on every call and read at call time.
- **P3** — PT1: ingest with the DP backend → same `/sources/upload` response shape, bytes in the fake, no file under `blobs/`, binding `available` with DP ids and the SHA.
- **P4** — PT2: a changed document → KA v2 and a second asset version; the first asset version's bytes are unchanged and readable.
- **P5** — PT3: identical bytes from two owners → two sources, two bindings; the fake records two assets (or one with two versions by owner) and neither owner can read the other's PERSONAL asset.
- **P6** — `reextract` on the DP backend reads the bytes through `GET …/content`.
- **P7** — `put_derived` stores a JSON artefact with provenance and returns an asset version (plan-22 will use it).
- **P8** — PT8: the live flow runs the fake over real HTTP with a DP-backed KA server, pastes through the console, and the version card says `bytes · data_platform · available`; and no module under `ka/` imports `google.`.

## Negative Test Cases (N1..N6)
- **N1** — commit with a wrong SHA → 422 → the binding is `failed` with the envelope's code; no available version.
- **N2** — the same idempotency key with different bytes → 409 `idempotency_conflict`; with the same bytes → the same asset version (replay).
- **N3** — DP down (`fail_next`) → `failed` binding with `retryable=true` recorded in the reason; nothing raises out of ingestion; plan-20 will retry.
- **N4** — a read of a PERSONAL asset by another owner → 403 → `DataPlatformError(code="policy_denied")`; the fake records the denial.
- **N5** — `KA_STORAGE_BACKEND=data_platform` with no base URL → local with the note; with a base URL but no token → the first call fails `401` and the binding is `failed` (never silently local).
- **N6** — the service token never appears in any binding, source, audit, event or fixture file.

## Plan totals

**Research points covered: 1 of 14 (R11) + R2's DP half · Deliverables: 7 · Positive cases: 8 · Negative cases: 6 · Test cases total: 14 ·
Product tests served: 5 of 9 (PT1, PT2, PT3, PT8 turn green; PT5's physical half).**

## Implementation Notes
- Written against `cd26463` (plan-18). No protected code. The live service keeps `KA_STORAGE_BACKEND=local`; the flow uses a second server.
