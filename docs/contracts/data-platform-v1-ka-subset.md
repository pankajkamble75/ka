# Data Platform v1 — the subset Knowledge Acquisition needs (KA-maintained; research-03 R11)

> **Superseded 2026-10-10** by [`data-platform-v1-real.md`](data-platform-v1-real.md) (the real service). This document stays for `KA_DP_API=ka-subset` only.

Status: proposed by KA on 2026-10-09 as executable fixtures (`ka/tests/fixtures/dp_contract/*.json`), implemented at the wire level by
`ka/data_platform/fake.py` and consumed by `ka/data_platform/__init__.py::DataPlatformClient`. The Data Platform may adopt these as
acceptance tests or hand KA an OpenAPI to generate from (research-03 R14 of the open questions). Headers on every call:
`Authorization: Bearer <service token>`, `X-KA-Tenant: <tenant id>`.

| # | Call | Request | Response |
|---|---|---|---|
| 1 | `POST /v1/assets/uploads` | `Idempotency-Key: ka:<tenant>:<source>:<version>`; `{asset_type, tenant_id, content_type, owner, visibility}` | 201 `{upload_id}` |
| 2 | `PUT /v1/assets/uploads/{upload_id}/content` | raw bytes | 204 |
| 3 | `POST /v1/assets/uploads/{upload_id}/commit` | `{sha256}` | 200 `{asset_id, asset_version_id, sha256, state}`; a replay of the same key + same bytes returns the same ids |
| 4 | commit with a wrong sha | — | 422 `checksum_mismatch` |
| 5 | the same key with different bytes | — | 409 `idempotency_conflict` |
| 6 | `GET /v1/assets/{asset_id}/versions/{v}/content` | `X-KA-Owner: <owner>` | bytes, or 403 `policy_denied` (tenant mismatch, or PERSONAL and not the owner) |
| 7 | `POST /v1/assets/derived` | `Idempotency-Key`; `{asset_type, tenant_id, parent_asset_id, parent_asset_version_id, provenance, payload_b64}` | 200 asset version |
| 8 | `GET /v1/events?after=<seq>&limit=` | — | `{events: [{event_id, seq, type, asset_id, asset_version_id, at}], next_after}`; types `data.asset.committed.v1`, `data.asset.quarantined.v1`, `data.asset.access_revoked.v1`, `data.asset.deleted.v1`, `data.index.ready.v1`, `data.ingestion.completed.v1` |
| 9 | any call while unavailable | — | 503 `unavailable`, `retryable: true` (also 429 `rate_limited`) |
| 10 | any call without a valid token | — | 401 `unauthenticated` |

Error envelope: `{code, message, correlation_id, retryable}`. KA never imports a cloud SDK; everything above is plain HTTP.
