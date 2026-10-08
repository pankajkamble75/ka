# [block plan-14]
"""The Microsoft 365 / SharePoint connector (research-02 R6; Q6, decided 2026-10-08): one Microsoft Graph app registration
(client credentials) covering OneDrive, SharePoint and Teams files, behind the plan-08 `Connector` contract.

- the client secret is NAMED by `Connection.secret_ref` and read from the environment at token time; tokens live in memory only;
- the drive's `@odata.deltaLink` is the checkpoint, so `sync_incremental` is one call (plus pages);
- permissions map onto KA visibility, narrowest-wins, with the connection's visibility as the ceiling;
- the registration itself (tenant, client id, secret variable) is the author's — Q13.
"""
from __future__ import annotations

import fnmatch
import json
import os
import time
from typing import Any, Callable
from urllib.parse import urlencode

from ka import config
from ka.connectors import ConnectorError, ConnectorItem, SyncDelta
from ka.vocab import Visibility

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
_WIDTH = {Visibility.PERSONAL: 0, Visibility.TEAM: 1, Visibility.INSTANCE: 2, Visibility.DOMAIN: 3, Visibility.ENTERPRISE: 4}

Http = Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, str], bytes]]


def _default_http(method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[int, dict[str, str], bytes]:
    import httpx
    r = httpx.request(method, url, headers=headers, content=data, timeout=30.0, follow_redirects=True)
    return r.status_code, dict(r.headers), r.content


def narrowest(a: Visibility, b: Visibility) -> Visibility:
    return a if _WIDTH[a] <= _WIDTH[b] else b


def visibility_from_permissions(perms: list[dict[str, Any]], ceiling: Visibility) -> Visibility:
    """Tenant-wide or anonymous links, or an 'Everyone' group → ENTERPRISE; any group → TEAM; only named users → PERSONAL;
    nothing readable → the ceiling. The result never exceeds the ceiling."""
    if not perms:
        return ceiling
    widest = Visibility.PERSONAL
    for p in perms:
        link = p.get("link") or {}
        g = (p.get("grantedToV2") or {}).get("group") or (p.get("grantedToV2") or {}).get("siteGroup")
        if link.get("scope") in {"anonymous", "organization"} or (g and "everyone" in (g.get("displayName") or "").lower()):
            widest = Visibility.ENTERPRISE
        elif g:
            widest = widest if _WIDTH[widest] > _WIDTH[Visibility.TEAM] else Visibility.TEAM
    return narrowest(widest, ceiling)


class M365Connector:
    kind = "m365"

    def __init__(self, http: Http | None = None):
        self.http = http or _default_http
        self._tokens: dict[str, tuple[str, float]] = {}          # connection id → (token, expiry); memory only

    # ---- auth --------------------------------------------------------------------------------------------

    def _cfg(self, connection) -> dict[str, str]:
        cfg = connection.config or {}
        missing = [k for k in ("tenant_id", "client_id", "drive_id") if not cfg.get(k)]
        if missing:
            raise ConnectorError(f"m365 needs config {', '.join(missing)}")
        if not connection.secret_ref:
            raise ConnectorError("m365 needs secret_ref: the NAME of the environment variable holding the client secret (Q13)")
        if not os.environ.get(connection.secret_ref):
            raise ConnectorError(f"m365: environment variable {connection.secret_ref!r} is unset (Q13 — the app registration is the author's)")
        return cfg

    def _token(self, connection) -> str:
        cfg = self._cfg(connection)
        tok = self._tokens.get(connection.id)
        if tok and tok[1] > time.time() + 30:
            return tok[0]
        body = urlencode({"client_id": cfg["client_id"], "client_secret": os.environ[connection.secret_ref],
                          "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}).encode()
        status, _h, raw = self.http("POST", f"{LOGIN}/{cfg['tenant_id']}/oauth2/v2.0/token", {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if status != 200:
            raise ConnectorError(f"m365 token request failed ({status})")
        data = json.loads(raw or b"{}")
        token = data.get("access_token")
        if not token:
            raise ConnectorError("m365 token response carried no access_token")
        self._tokens[connection.id] = (token, time.time() + float(data.get("expires_in", 3600)))
        return token

    def _get(self, connection, url: str) -> tuple[int, dict[str, str], bytes]:
        status, headers, raw = self.http("GET", url, {"Authorization": f"Bearer {self._token(connection)}", "Accept": "application/json"}, None)
        if status in (401, 403):
            raise ConnectorError(f"m365: Graph refused the request ({status}); check the app's permissions (Files.Read.All, Sites.Read.All)")
        if status >= 400:
            raise ConnectorError(f"m365: Graph error {status} for {url.split('?')[0]}")
        return status, headers, raw

    def _get_json(self, connection, url: str) -> dict[str, Any]:
        _s, _h, raw = self._get(connection, url)
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise ConnectorError("m365: Graph returned a body that is not JSON")

    # ---- contract -------------------------------------------------------------------------------------------

    def authorize(self, connection) -> None:
        self._token(connection)

    def _item(self, connection, raw: dict[str, Any]) -> ConnectorItem | None:
        if "folder" in raw:
            return None
        path = (raw.get("parentReference") or {}).get("path") or ""
        rel_dir = path.split("root:", 1)[1].strip("/") if "root:" in path else ""
        name = f"{rel_dir}/{raw.get('name', raw['id'])}".strip("/")
        hashes = ((raw.get("file") or {}).get("hashes") or {})
        return ConnectorItem(locator=raw["id"], name=name, modified_at=raw.get("lastModifiedDateTime") or "", size=int(raw.get("size") or 0),
                             checksum=hashes.get("quickXorHash") or hashes.get("sha256Hash") or (raw.get("eTag") or "").strip('"'),
                             visibility=None, principals=[], deleted="deleted" in raw)

    def _delta(self, connection, url: str) -> tuple[list[dict[str, Any]], str | None]:
        rows: list[dict[str, Any]] = []
        delta_link = None
        while url:
            data = self._get_json(connection, url)
            rows += [r for r in data.get("value", []) if isinstance(r, dict) and r.get("id")]
            delta_link = data.get("@odata.deltaLink") or delta_link
            url = data.get("@odata.nextLink")
        return rows, delta_link

    def _included(self, connection, item: ConnectorItem) -> bool:
        include = (connection.config or {}).get("include")
        return not include or any(fnmatch.fnmatch(item.name, pat) or fnmatch.fnmatch(item.name.rsplit("/", 1)[-1], pat.split("/")[-1]) for pat in include)

    def enumerate(self, connection, cursor: str | None = None) -> tuple[list[ConnectorItem], str | None]:
        cfg = self._cfg(connection)
        rows, delta_link = self._delta(connection, cursor or f"{GRAPH}/drives/{cfg['drive_id']}/root/delta")
        items = [i for i in (self._item(connection, r) for r in rows) if i is not None and (i.deleted or self._included(connection, i))]
        return items, delta_link

    def fetch(self, connection, item: ConnectorItem) -> bytes:
        cfg = self._cfg(connection)
        _s, _h, raw = self._get(connection, f"{GRAPH}/drives/{cfg['drive_id']}/items/{item.locator}/content")
        return raw

    def get_permissions(self, connection, item: ConnectorItem) -> dict[str, Any]:
        cfg = self._cfg(connection)
        try:
            data = self._get_json(connection, f"{GRAPH}/drives/{cfg['drive_id']}/items/{item.locator}/permissions")
        except ConnectorError:
            return {"visibility": connection.visibility.value, "principals": [], "note": "permissions unreadable; connection ceiling applied"}
        perms = [p for p in data.get("value", []) if isinstance(p, dict)]
        principals = []
        for p in perms:
            who = (p.get("grantedToV2") or {})
            for k in ("user", "group", "siteGroup", "application"):
                if who.get(k):
                    principals.append(f"{k}:{who[k].get('displayName') or who[k].get('id')}")
            if p.get("link"):
                principals.append(f"link:{(p['link'] or {}).get('scope')}")
        return {"visibility": visibility_from_permissions(perms, connection.visibility).value, "principals": principals}

    def checkpoint(self, connection) -> dict[str, Any]:
        items, delta_link = self.enumerate(connection)
        return {"delta_link": delta_link, "syncs": 0,
                "items": {i.locator: {"checksum": i.checksum, "name": i.name, "visibility": None} for i in items if not i.deleted}}

    def sync_incremental(self, connection, checkpoint: dict[str, Any]) -> SyncDelta:
        cp = checkpoint or {}
        known: dict[str, dict[str, Any]] = dict(cp.get("items") or {})
        syncs = int(cp.get("syncs") or 0) + 1
        sweep = syncs % max(1, int(config.get("KA_M365_PERMISSION_SWEEP_EVERY"))) == 0
        items, delta_link = self.enumerate(connection, cursor=cp.get("delta_link"))
        delta = SyncDelta()
        for item in items:
            prior = known.get(item.locator)
            if item.deleted:
                if prior is not None:
                    delta.deleted.append(item.locator)
                    known.pop(item.locator, None)
                continue
            perm = self.get_permissions(connection, item)
            item.visibility, item.principals = perm["visibility"], perm["principals"]
            if prior is None:
                delta.new.append(item)
            else:
                if prior.get("checksum") != item.checksum:
                    delta.modified.append(item)
                elif prior.get("name") != item.name:
                    delta.moved.append((item.locator, item))
                if prior.get("visibility") and prior["visibility"] != item.visibility:
                    delta.permission_changed.append(item)
            known[item.locator] = {"checksum": item.checksum, "name": item.name, "visibility": item.visibility}
        if sweep:
            seen = {i.locator for i in items}
            for loc, prior in list(known.items()):
                if loc in seen:
                    continue
                probe = ConnectorItem(locator=loc, name=prior.get("name", loc), modified_at="", size=0, checksum=prior.get("checksum", ""))
                perm = self.get_permissions(connection, probe)
                if prior.get("visibility") and perm["visibility"] != prior["visibility"]:
                    probe.visibility, probe.principals = perm["visibility"], perm["principals"]
                    delta.permission_changed.append(probe)
                known[loc] = {**prior, "visibility": perm["visibility"]}
        delta.checkpoint = {"delta_link": delta_link or cp.get("delta_link"), "syncs": syncs, "items": known}
        return delta

    def revoke(self, connection) -> None:
        self._tokens.pop(connection.id, None)
# [/block plan-14]
