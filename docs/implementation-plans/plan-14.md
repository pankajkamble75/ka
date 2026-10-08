# Plan 14 - The Microsoft 365 / SharePoint connector behind the plan-08 contract (Q6)

Created: 2026-10-09 02:15 UTC

## Problem Description

The connector contract (plan-08) has one implementation, the local folder (`ka/connectors/__init__.py:58`). The author decided
(Q6, 2026-10-08): the first provider after the folder is Microsoft 365 / SharePoint — one Microsoft Graph app registration covering
OneDrive, SharePoint and Teams files, a `Connector` class behind the contract, SharePoint permission lists mapped onto KA visibility,
the client secret named by `secret_ref` and read from the environment. The app registration (tenant, client id, secret variable) is
the author's (Q13 / R9); until then the connector is verified against a recorded Graph fixture and the live product test PT6 is NOT RUN.

Desired outcome: `kind="m365"` connections authorize with client credentials, enumerate a drive through the Graph delta API
(the `@odata.deltaLink` is the checkpoint), fetch content, map item permissions to visibility (tenant-wide → ENTERPRISE, a group →
TEAM, a single user → PERSONAL, the connection's visibility as the ceiling), detect new / modified / moved / deleted / permission-
changed items, and never store the secret. Everything flows through `SyncService` unchanged.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q6 Microsoft 365 / SharePoint first, behind the plan-08 contract | `knowledge-acquisition.md` §2 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| Connector contract and sync reconciliation (new/modified/moved/deleted/permission-changed; revocation re-review) | `knowledge-acquisition.md` §2 (plan-08, plan-10) | ✅ built | **constrained by it** — the connector produces items and a delta; `SyncService` is not edited |
| No credential in a stored object; `secret_ref` names a variable | `knowledge-acquisition.md` §2, §10 | ✅ built | **constrained by it** — the secret is read from `os.environ[secret_ref]` at token time; tokens live in memory only |
| Visibility is the narrowest of a nugget's sources; a source's visibility is a ceiling | `knowledge-acquisition.md` §10 | ✅ built | **constrained by it** — the permission mapping never widens past the connection's visibility |
| Q13 (R9) the app registration | `questions/knowledge-acquisition.md` Q13 | ❓ open | this plan does NOT need it to build; it blocks only the live PT6 |

**Open questions in the sections this plan touches:** Q13 — blocks the live test only.

## Research coverage (R1..R9)

Source: [research-02](../research/research-02.md) — **9 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R5 | ✅ shipped | plans 10–13 |
| R6 M365 connector | ✅ in scope | Phases 1–3 |
| R7 Processes tab | ⏭️ deferred | plan-15 |
| R8 | ⏭️ deferred | author decision Q12 |
| R9 M365 registration | ⏭️ deferred | author decision Q13 — the build does not wait on it |

**Covered here: 1 of 9.** Deferred: 3. Shipped earlier: 5.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT6 a SharePoint library synced through the connector produces sources whose visibility follows the library's sharing; a second sync after a file change produces version 2 of the same source | R6, R9 | still **NOT RUN** live (the registration is the author's, Q13); the fixture-driven equivalent is GREEN here |

## Scope

In: `ka/connectors/m365.py` (new), `ka/connectors/__init__.py` (kind registration), `ka/config.py` (`KA_M365_PERMISSION_SWEEP_EVERY`),
`ka/console/app.js` (a "Connect Microsoft 365 / SharePoint" card), fixture `ka/tests/fixtures/m365_graph_fixture.json`, tests, live flow
(the fail-closed path: no registration → create refused with a clear reason; kinds list shows m365), `.env.example`, docs.

Out: Google Workspace and file shares (same pattern, later); delegated (per-user) OAuth; Teams chat messages; SharePoint lists.

## Protected-code impact (summary)

✅ No protected code touched by any phase — a new connector module, a registration line, a setting, the console. `SyncService`,
governance and publication are unchanged.

## Assumptions

- `Connection.config` for `m365`: `{tenant_id, client_id, drive_id, include?: [globs]}`; `secret_ref` = the environment variable holding
  the client secret (required). `M365Connector(http=None)`: `http(method, url, headers, data) -> (status, headers, body_bytes)` is
  injectable; the default uses httpx. Token: client credentials against `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`,
  scope `https://graph.microsoft.com/.default`, cached in memory per connection until expiry; `revoke` drops it.
- Items: locator = Graph item `id` (stable across moves); `name` = the item's path relative to the drive root + file name, so a move
  changes `name`; `checksum` = `file.hashes.quickXorHash` or `eTag`; folders skipped; `deleted` facets → the `deleted` list.
- Delta: `GET /drives/{drive_id}/root/delta` first, then the stored `@odata.deltaLink`; `@odata.nextLink` pages followed. Permissions are
  read for new and modified items on every sync, and for every item every `KA_M365_PERMISSION_SWEEP_EVERY` syncs (default 10;
  the counter lives in the checkpoint) because a permission change does not bump an item's delta.
- Visibility mapping (narrowest-wins, ceiling = connection visibility): a `link.scope` of `anonymous`/`organization`, or a group whose
  display name contains "Everyone" → ENTERPRISE; any `grantedToV2.group` / `siteGroup` → TEAM; only `grantedToV2.user` → PERSONAL;
  no permissions readable → the connection's visibility.
- Checkpoint: `{"delta_link", "syncs", "items": {id: {checksum, name, visibility}}}`.

## Phases

### Phase 1 - The connector
- `ka/connectors/m365.py`; registration; setting.
- **Protected-code touched:** none

### Phase 2 - Console and docs
- Add-knowledge card for M365 (tenant, client id, drive id, secret variable name, scope, authority, visibility ceiling); `.env.example`;
  architecture §2 → ✅ built; Q13 stays open naming the live test.
- **Protected-code touched:** none

### Phase 3 - Tests and flow
- Fixture; `test_plan14_m365_connector.py`; `e2e/plan14_m365_flow.py` (kinds list shows m365; creating without the secret variable is
  refused with the reason; the card renders).
- **Protected-code touched:** none

## Code blocks (B1..B4)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/connectors/m365.py` | the connector |
| B2 | `ka/connectors/__init__.py` | kind registration |
| B3 | `ka/config.py` | sweep setting |
| B4 | `ka/console/app.js` | the M365 card and its action |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `M365Connector` — `authorize` (config + secret variable + token), `enumerate` (delta pages, folders skipped), `fetch`, `get_permissions` with the visibility mapping, `checkpoint`, `sync_incremental` (delta link, moved by name, permission sweep), `revoke` | `ka/connectors/m365.py` | 1 |
| D2 | `m365` in `get_connector` / `CONNECTOR_KINDS` | `ka/connectors/__init__.py` | 1 |
| D3 | `KA_M365_PERMISSION_SWEEP_EVERY` | `ka/config.py` | 1 |
| D4 | console card + `connect-m365` action | `ka/console/app.js` | 2 |
| D5 | recorded Graph fixture | `ka/tests/fixtures/m365_graph_fixture.json` | 3 |
| D6 | live flow (fail-closed path) | `e2e/plan14_m365_flow.py` | 3 |
| D7 | `.env.example`; architecture §2 ✅ built | docs | 2 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P7)
- **P1** — `authorize` reads the secret from the named variable, posts client credentials, caches the token; a second call makes no second token request.
- **P2** — `enumerate` maps the delta page: files become items with id locator, path name, checksum, modified_at, size; folders are skipped; a `deleted` facet marks the item deleted; `@odata.nextLink` pages are followed.
- **P3** — first `sync` through `SyncService`: sources carry visibility from the permission mapping (organization link → ENTERPRISE, group → TEAM, single user → PERSONAL) and never exceed the connection's ceiling.
- **P4** — second `sync` through the stored delta link: a changed item → version 2 of the same source; a deleted item → revoked (+ plan-10 re-review); a moved item → same source, new name; the checkpoint's `syncs` counter advances.
- **P5** — the permission sweep runs on every Nth sync and reports `permission_changed` for an item whose sharing narrowed.
- **P6** — PT6 fixture-driven: a library synced → visibilities follow sharing; a second sync after a change → version 2 of the same source.
- **P7** — the live PT6 is a test that SKIPS with the reason "needs the M365 app registration (Q13)".

## Negative Test Cases (N1..N5)
- **N1** — the client secret and the token never appear in the stored connection, any source, the audit log or the events.
- **N2** — `create` with the secret variable unset, or a missing `tenant_id` / `client_id` / `drive_id`, is refused with the reason; nothing stored (400 at the API).
- **N3** — a Graph 401/403 during sync raises `ConnectorError` (400 at the API); the connection stays active and its checkpoint is unchanged.
- **N4** — an item over `KA_MAX_UPLOAD_MB` (by metadata size) is skipped without a content request.
- **N5** — `revoke` drops the token; a later sync is refused (409) and no Graph call is made.

## Plan totals

**Research points covered: 1 of 9 · Deliverables: 7 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 1 of 7 (0 turn green live here; PT6's fixture-driven equivalent passes).**

## Implementation Notes
- Written against `685f59a` (plan-13 upload). No protected code.
