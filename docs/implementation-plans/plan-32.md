# Plan 32 - The real Data Platform /v1: a client and store for the actual API, knowledge bindings, a faithful fake, inbound polling off (research-05 R9)

Created: 2026-10-10 17:00 UTC

## Problem Description

KA's Data Platform side (plans 18–23) was built against KA's own contract and fake (`docs/contracts/data-platform-v1-ka-subset.md`). The real
Data Platform (`pankajkamble75/dataplatform`, `/root/dataplatform`, base `http://127.0.0.1:8100`, `schemas/openapi.json`) differs (its session,
2026-10-10; research-05 §9): staging body `{tenant_id, sha256, size_bytes, mime_type, type, scope, tags, asset_id?, provenance?, format?}` →
`{upload_id, asset_id, target_version, state, content_url, commit_url}` with no key; `PUT content_url`; `POST commit_url {sha256}` with a REQUIRED
`Idempotency-Key` → `{asset_id, asset_version_id, version, sha256, size_bytes, created}`; errors `{code, message, correlation_id, retryable,
details}` (`invalid_contract` 422, `conflict` 409 incl. `details.state=expired`, `policy_denied` 403); `POST /v1/derived-assets {tenant_id, type:
extracted_text|nugget|derived, mime_type, parent_asset_version_ids[], content_base64, scope?, metadata?, evidence[]}` → `{asset, version}`;
`POST /v1/knowledge-bindings {tenant_id, ka_source_id, ka_source_version, dp_asset_version_id}`; read `GET /v1/assets/{id}/versions/{n|latest}/content`;
auth: loopback headers `X-Principal-Id, X-Tenant-Id, X-Scopes` or `Bearer` in static mode; **no events feed** (dropped by its session).

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §11 port, binding, outbox, derived artefacts (plans 18–23) | `knowledge-acquisition.md` §11 | ✅ built | **constrained by it** — only the wire changes; the port, binding states, outbox and publisher stay |
| Visibility never widens | `knowledge-acquisition.md` §10 | ✅ built | **obeyed** — a DOMAIN/INSTANCE/TEAM visibility without its tag is narrowed to PERSONAL, never widened |
| KA never imports DP code | research-05 acceptance | — | **obeyed** — stdlib HTTP; DP's reference client is read, not imported |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R12)

| Research point | This plan | Where / why |
|---|---|---|
| R2–R5, R7, R8, R10 | ✅ shipped | plans 29–31 |
| R9 real DP | ✅ in scope | Phases 1–3 |
| R1, R6, R11, R12 | ⏭️ plan-33 | |

**Covered here: 1 of 12.**

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT9 upload commits, a knowledge binding is created, a nugget version lands as a `nugget` derived asset, against the real DP | R9 | **GREEN** |

## Scope

In: `ka/data_platform/v1.py` (new: `DataPlatformV1Client`, `DataPlatformV1Store`), `ka/data_platform/fake_v1.py` (new: faithful double),
`ka/data_platform/store.py` (`from_config` picks the API by `KA_DP_API`), `ka/service.py` (inbound polling only on `ka-subset`), `ka/config.py`
(`KA_DP_API`, `KA_DP_AUTH_MODE`, `KA_DP_PRINCIPAL`), `docs/contracts/data-platform-v1-real.md`, tests, live flow against the REAL DP (own data
root, own port, stopped afterwards — as agreed with its session).

Out: the DP's AgentX capabilities (`data.assets.*`, its own business); DP search for KA (not needed).

## Protected-code impact (summary)

✅ No protected code touched.

## Assumptions

- `KA_DP_API`: `v1` (default — the real API) | `ka-subset` (KA's 2026-10-09 contract; the plans 19–23 tests construct its client
  explicitly and keep testing KA's logic against it).
- Auth: `KA_DP_AUTH_MODE` `auto` (Bearer when `KA_DP_SERVICE_TOKEN` is set, else headers) | `bearer` | `headers`; headers mode sends
  `X-Principal-Id: <KA_DP_PRINCIPAL, default "ka">`, `X-Tenant-Id`, `X-Scopes: storage:read,storage:write`.
- Types: `source_document → document`, `extracted_text → extracted_text`, `nugget_version → nugget`; provenance `supplied`; `format` from the
  filename extension or `text`.
- The commit's `Idempotency-Key` is KA's binding key `ka:<tenant>:<source>:<version>`; the store parses `<source>` and `<version>` from it for
  `POST /v1/knowledge-bindings`. A binding failure is recorded on the ref (`state` stays `available`; the binding call is retried by the next
  write of that version) and never loses the bytes.
- `PhysicalRef.locator = "/v1/assets/{asset_id}/versions/{version}/content"`; `get` uses the locator (or `latest`); `exists` is `GET
  /v1/assets/{id}/versions/{n}`.
- Derived: `put_derived("nugget_version", payload, parent)` → `type: nugget`, `mime_type: application/json`, `parent_asset_version_ids:
  [parent.asset_version_id]` (empty when the nugget has no DP parent), `metadata: provenance`, `evidence: []`; response `{asset, version}`.
- Errors: the DP envelope → `DataPlatformError(status, code, message, correlation_id, retryable)`; `retryable` from the body when present.
- Inbound polling (plan-21) is registered only when `KA_DP_API=ka-subset`.

## Phases

### Phase 1 - Client, store, fake
- `ka/data_platform/v1.py`, `ka/data_platform/fake_v1.py`.

### Phase 2 - Selection and wiring
- `ka/data_platform/store.py`, `ka/service.py`, `ka/config.py`, `docs/contracts/data-platform-v1-real.md`.

### Phase 3 - Tests and the live check against the real DP
- `ka/tests/test_plan32_dp_real.py`; `e2e/plan32_dp_real_flow.py`.

## Code blocks (B1..B4)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/data_platform/v1.py` | client + store |
| B2 | `ka/data_platform/fake_v1.py` | faithful double |
| B3 | `ka/data_platform/store.py`, `ka/service.py` | selection; polling gate (one block each) |
| B4 | `ka/config.py` | settings |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `DataPlatformV1Client` (stage, content, commit, read, version, derived, knowledge-binding) with both auth modes and the DP error envelope | `ka/data_platform/v1.py` | 1 |
| D2 | `DataPlatformV1Store` (the `PhysicalStore` port: put + binding, get, put_derived, exists) | `ka/data_platform/v1.py` | 1 |
| D3 | `FakeDataPlatformV1` (faithful: shapes, codes, idempotent commit, expiry, scope tags, policy) | `ka/data_platform/fake_v1.py` | 1 |
| D4 | `KA_DP_API` selection; polling only on `ka-subset` | `ka/data_platform/store.py`, `ka/service.py` | 2 |
| D5 | settings | `ka/config.py` | 2 |
| D6 | `docs/contracts/data-platform-v1-real.md` (the real API as KA uses it; the ka-subset contract marked superseded) | docs | 2 |
| D7 | live flow against the real DP service | `e2e/plan32_dp_real_flow.py` | 3 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P6)
- **P1** — an upload through ingestion on `KA_DP_API=v1` (fake) stages with the real body, PUTs to `content_url`, commits at `commit_url` with the key, creates a knowledge binding, and the version is `available` with DP ids and a `/v1/…/content` locator.
- **P2** — reextract and "view bytes" read the bytes back through the real read path.
- **P3** — PT9 (fake): approving a nugget publishes a `nugget` derived asset with the source version as parent.
- **P4** — the same version committed twice (idempotency key) returns the same ids; the binding call is idempotent.
- **P5** — auth: bearer mode sends only `Authorization`; headers mode sends `X-Principal-Id`, `X-Tenant-Id`, `X-Scopes`.
- **P6** — PT9 (real): the live flow against the real DP service — upload, binding, read-back, nugget derived asset.

## Negative Test Cases (N1..N5)
- **N1** — a checksum mismatch → `invalid_contract` 422 → binding `failed` (not available); the outbox does not retry it.
- **N2** — a 409 `conflict` (expired upload) → non-retryable failure with the code; a 503 → retryable (`pending`, outbox).
- **N3** — DOMAIN visibility without a domain tag is narrowed to PERSONAL on the wire (never widened) and the note is recorded.
- **N4** — on `KA_DP_API=v1` no inbound polling tick is registered.
- **N5** — the plans 18–23 tests (ka-subset client) pass unmodified.

## Plan totals

**Research points covered: 1 of 12 · Deliverables: 7 · Positive cases: 6 · Negative cases: 5 · Test cases total: 11 ·
Product tests served: 1 of 9 (PT9 turns green here).**

## Implementation Notes
- Written against `7427778` (plan-31).
