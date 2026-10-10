# The Data Platform `/v1` as KA uses it (the real service)

**Status:** in use, 2026-10-10 (research-05 R9, plan-32). Source of truth: `pankajkamble75/dataplatform` `schemas/openapi.json` and its
reference client `src/data_platform/integrations/ka/client.py` (read, never imported). This **supersedes**
[`data-platform-v1-ka-subset.md`](data-platform-v1-ka-subset.md), KA's own 2026-10-09 proposal, which stays only behind `KA_DP_API=ka-subset`.

## Settings

| setting | meaning |
|---|---|
| `KA_STORAGE_BACKEND=data_platform`, `KA_DP_BASE_URL` | e.g. `http://127.0.0.1:8100` |
| `KA_DP_API` | `v1` (default, this document) · `ka-subset` (superseded) |
| `KA_DP_AUTH_MODE` | `auto` (Bearer `KA_DP_SERVICE_TOKEN` when set, else headers) · `bearer` · `headers` |
| `KA_DP_PRINCIPAL`, `KA_TENANT_ID` | `X-Principal-Id` / `X-Tenant-Id` in headers mode (loopback test principal); `X-Scopes: storage:read,storage:write` |

## Calls

| step | call | KA's use |
|---|---|---|
| stage | `POST /v1/assets/uploads {tenant_id, sha256, size_bytes, mime_type, type: document, scope, tags, format, provenance: supplied}` → `{upload_id, asset_id, target_version, state, content_url, commit_url}` | every source version with bytes |
| bytes | `PUT {content_url}` (octet-stream) → 204 | |
| commit | `POST {commit_url} {sha256}` + **`Idempotency-Key: ka:<tenant>:<source>:<version>`** → `{asset_id, asset_version_id, version, sha256, size_bytes, created}` | a repeat returns the same ids |
| bind | `POST /v1/knowledge-bindings {tenant_id, ka_source_id, ka_source_version, dp_asset_version_id}` → 201 new / 200 existing | after every commit |
| read | `GET /v1/assets/{id}/versions/{n\|latest}/content`; metadata at `…/versions/{n}` | reextract, "view bytes"; `PhysicalRef.locator = /v1/assets/{id}/versions/{n}/content` |
| derived | `POST /v1/derived-assets {tenant_id, type: nugget, mime_type: application/json, parent_asset_version_ids: [source's], content_base64, metadata, evidence: []}` → `{asset, version}` | every nugget version event (plan-22); scope = the narrowest parent's |

## Errors

DP's envelope `{code, message, correlation_id, retryable, details}`. KA maps: 422 `invalid_contract` (checksum mismatch) and 409 `conflict`
(including `details.state=expired`) → the version is `failed`, not retried; 429/5xx → `pending`, retried by the outbox (plan-20); 401/403 →
failed with the code.

## Differences KA absorbs

- **Visibility → scope.** `DOMAIN`, `INSTANCE`, `TEAM` need a `domain_id` / `instance_id` / `team_id` tag. Where KA cannot supply it, the
  scope is **narrowed to `PERSONAL`** (never widened, §10) and a note is recorded on the store.
- **Types.** `source_document → document`, `extracted_text → extracted_text`, `nugget_version → nugget`.
- **No events feed.** The DP dropped it; KA does not poll inbound events on this API (plan-21's poller runs only on `ka-subset`). Revocation
  reaches KA through its own sources (connectors), not the DP.
- **Derived assets have no idempotency key on the DP.** KA sends `Idempotency-Key` anyway; a retry after a lost response can create a second
  derived version. KA's outbox marks the op done on the first 201, so this needs a lost response to happen.
- **A derived asset needs a parent.** A nugget whose source has no DP asset version (e.g. bytes written before the DP backend was on) fails
  with `no_parent`, not retried; plan-23's backfill gives old sources a DP asset first.

## Live check

`e2e/plan32_dp_real_flow.py` starts the real service from `/root/dataplatform` on port 8110 with a fresh data root under `/tmp` (outside both
repositories), loopback headers, and stops it at the end — the Data Platform session's conditions.
