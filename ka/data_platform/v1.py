# [block plan-32]
"""The REAL Data Platform `/v1` (research-05 R9; `pankajkamble75/dataplatform` `schemas/openapi.json`, its session 2026-10-10;
`docs/contracts/data-platform-v1-real.md`): stage `{tenant_id, sha256, size_bytes, mime_type, type, scope, tags, format, provenance}` →
`PUT content_url` → `POST commit_url {sha256}` with a REQUIRED `Idempotency-Key` → `POST /v1/knowledge-bindings`; derived assets through
`POST /v1/derived-assets`; reads at `/v1/assets/{id}/versions/{n|latest}[/content]`. Errors are DP's envelope `{code, message,
correlation_id, retryable, details}`. Auth: Bearer (static mode) or the principal headers `X-Principal-Id`, `X-Tenant-Id`, `X-Scopes`.
No events feed — KA does not poll on this API. stdlib-free of DP code: KA reads DP's reference client, never imports it."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ka import config
from ka.data_platform import ConfigurationError, DataPlatformClient, DataPlatformError
from ka.data_platform.store import DataPlatformPhysicalStore
from ka.physical import PhysicalRef

DP_TYPE = {"source_document": "document", "extracted_text": "extracted_text", "nugget_version": "nugget"}
SCOPES = ("PERSONAL", "TEAM", "DOMAIN", "INSTANCE", "ENTERPRISE")
TAG_FOR = {"DOMAIN": "domain_id", "INSTANCE": "instance_id", "TEAM": "team_id"}


class DataPlatformV1Client(DataPlatformClient):
    """The real API's wire. Reuses the plan-19 transport and error mapping; replaces the headers and the calls."""

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        token = config.get(self.token_env) or ""
        mode = (config.get("KA_DP_AUTH_MODE") or "auto").lower()
        h = {"Accept": "application/json", "X-Tenant-Id": self.tenant_id}
        if mode == "bearer" or (mode == "auto" and token):
            h["Authorization"] = f"Bearer {token}"
        else:
            h.update({"X-Principal-Id": config.get("KA_DP_PRINCIPAL") or "ka", "X-Scopes": "storage:read,storage:write"})
        h.update(extra or {})
        return h

    def _call(self, method, path, *, headers=None, body=None, json_body=None):
        if path.startswith("http://") or path.startswith("https://"):          # DP hands back absolute or relative content/commit URLs
            path = "/" + path.split("://", 1)[1].split("/", 1)[1]
        return super()._call(method, path, headers=headers, body=body, json_body=json_body)

    def stage(self, *, sha256: str, size_bytes: int, mime_type: str, asset_type: str, scope: str, tags: dict[str, str], fmt: str,
              asset_id: str | None = None) -> dict[str, Any]:
        body = {"tenant_id": self.tenant_id, "sha256": sha256, "size_bytes": size_bytes, "mime_type": mime_type, "type": asset_type,
                "scope": scope, "tags": tags, "format": fmt, "provenance": "supplied"}
        if asset_id:
            body["asset_id"] = asset_id
        return self._json("POST", "/v1/assets/uploads", json_body=body)

    def put_bytes(self, content_url: str, data: bytes) -> None:
        self._call("PUT", content_url, headers={"Content-Type": "application/octet-stream"}, body=data)

    def commit_at(self, commit_url: str, *, sha256: str, idempotency_key: str) -> dict[str, Any]:
        return self._json("POST", commit_url, headers={"Idempotency-Key": idempotency_key}, json_body={"sha256": sha256})

    def bind(self, *, ka_source_id: str, ka_source_version: int, dp_asset_version_id: str) -> dict[str, Any]:
        return self._json("POST", "/v1/knowledge-bindings", json_body={"tenant_id": self.tenant_id, "ka_source_id": ka_source_id,
                                                                       "ka_source_version": int(ka_source_version), "dp_asset_version_id": dp_asset_version_id})

    def read(self, asset_id: str, version: str | int = "latest") -> bytes:
        return self._call("GET", f"/v1/assets/{asset_id}/versions/{version}/content")[2]

    def version(self, asset_id: str, version: str | int) -> dict[str, Any]:
        return self._json("GET", f"/v1/assets/{asset_id}/versions/{version}")

    def derived(self, *, asset_type: str, payload: bytes, parent_asset_version_ids: list[str], metadata: dict[str, Any],
                mime_type: str = "application/json", idempotency_key: str | None = None) -> dict[str, Any]:
        return self._json("POST", "/v1/derived-assets", headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
                          json_body={"tenant_id": self.tenant_id, "type": asset_type, "mime_type": mime_type,
                                     "parent_asset_version_ids": parent_asset_version_ids, "content_base64": base64.b64encode(payload).decode(),
                                     "metadata": metadata, "evidence": []})

    def events(self, *, after: int = 0, limit: int = 200) -> dict[str, Any]:     # the real DP has no events feed (dropped 2026-10-10)
        return {"events": [], "next": after}


def wire_scope(visibility: str, tags: dict[str, str]) -> tuple[str, str | None]:
    """KA visibility → DP scope. A scope that needs a tag KA cannot supply is NARROWED to PERSONAL, never widened (§10)."""
    v = (visibility or "PERSONAL").upper()
    if v not in SCOPES:
        return "PERSONAL", f"unknown visibility {visibility!r} narrowed to PERSONAL"
    if v in TAG_FOR and not tags.get(TAG_FOR[v]):
        return "PERSONAL", f"{v} without {TAG_FOR[v]} narrowed to PERSONAL"
    return v, None


def _fmt(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lstrip(".").lower()
    return ext or "text"


class DataPlatformV1Store(DataPlatformPhysicalStore):
    """The plan-18 `PhysicalStore` port on the real API (a `DataPlatformPhysicalStore` on a different wire). `put` also records the KA ↔ DP
    knowledge binding."""
    name = "data_platform"

    def __init__(self, client: DataPlatformV1Client):
        self.client, self.notes = client, []

    @classmethod
    def from_config(cls, root: Path) -> "DataPlatformV1Store":
        base = (config.get("KA_DP_BASE_URL") or "").strip()
        if not base:
            raise ConfigurationError("KA_DP_BASE_URL unset")
        return cls(DataPlatformV1Client(base))

    def locator(self, asset_id: str, version: Any) -> str:
        return f"/v1/assets/{asset_id}/versions/{version}/content"

    def put(self, data, *, content_type, sha256, idempotency_key, owner, visibility, tenant_id, filename_hint=None, tags=None):
        tags = {k: str(v) for k, v in (tags or {}).items() if k in TAG_FOR.values() and v}
        scope, note = wire_scope(visibility, tags)
        if note:
            self.notes.append(note)
        parts = idempotency_key.split(":")                                   # ka:<tenant>:<source>:<version>[:<source_version_id>]
        commit_key = ":".join(parts[:4]) if len(parts) >= 4 else idempotency_key
        staged = self.client.stage(sha256=sha256, size_bytes=len(data), mime_type=content_type or "application/octet-stream",
                                   asset_type=DP_TYPE["source_document"], scope=scope, tags=tags, fmt=_fmt(filename_hint))
        self.client.put_bytes(staged["content_url"], data)
        d = self.client.commit_at(staged["commit_url"], sha256=sha256, idempotency_key=commit_key)
        if len(parts) >= 4 and parts[0] == "ka":
            try:
                self.client.bind(ka_source_id=parts[2], ka_source_version=int(parts[3]), dp_asset_version_id=d["asset_version_id"])
            except (DataPlatformError, ValueError) as e:                         # the bytes are committed; the binding is retried on the next write
                self.notes.append(f"knowledge binding for {parts[2]}:v{parts[3]} not recorded: {e}")
        return PhysicalRef(backend=self.name, asset_id=d["asset_id"], asset_version_id=d["asset_version_id"], sha256=d["sha256"], state="available",
                           locator=self.locator(d["asset_id"], d["version"]), content_type=content_type, byte_size=int(d.get("size_bytes") or len(data)))

    def get(self, ref: PhysicalRef, *, owner: str | None = None) -> bytes:
        if ref.locator and ref.locator.startswith("/v1/"):
            return self.client._call("GET", ref.locator)[2]
        return self.client.read(ref.asset_id, "latest")

    def put_derived(self, kind, payload, *, parent, provenance, idempotency_key):
        if parent is None or not parent.asset_version_id:
            raise DataPlatformError(422, "no_parent", "the Data Platform needs a parent asset version for a derived asset", retryable=False)
        out = self.client.derived(asset_type=DP_TYPE.get(kind, "derived"), payload=payload, parent_asset_version_ids=[parent.asset_version_id],
                                  metadata={k: v for k, v in provenance.items() if v is not None}, idempotency_key=idempotency_key)
        a, v = out["asset"], out["version"]
        return PhysicalRef(backend=self.name, asset_id=a["asset_id"], asset_version_id=v["asset_version_id"], sha256=v["sha256"], state="available",
                           locator=self.locator(a["asset_id"], v["version"]), content_type="application/json", byte_size=len(payload))

    def exists(self, ref: PhysicalRef) -> bool:
        try:
            version = ref.locator.split("/versions/")[1].split("/")[0] if ref.locator and "/versions/" in ref.locator else "latest"
            self.client.version(ref.asset_id, version)
            return True
        except DataPlatformError:
            return False
# [/block plan-32]
