# [block plan-19]
"""`DataPlatformPhysicalStore` — the HTTP implementation of the plan-18 port (research-03 R2's Data Platform half)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ka import config
from ka.data_platform import ConfigurationError, DataPlatformClient, DataPlatformError
from ka.physical import ASSET_FAMILIES, PhysicalRef


class DataPlatformPhysicalStore:
    name = "data_platform"

    def __init__(self, client: DataPlatformClient):
        self.client = client

    @classmethod
    def from_config(cls, root: Path) -> "DataPlatformPhysicalStore":
        base = (config.get("KA_DP_BASE_URL") or "").strip()
        if not base:
            raise ConfigurationError("KA_DP_BASE_URL unset")
        return cls(DataPlatformClient(base))

    def put(self, data, *, content_type, sha256, idempotency_key, owner, visibility, tenant_id, filename_hint=None):
        key = idempotency_key.rsplit(":", 1)[0] if idempotency_key.count(":") >= 4 else idempotency_key   # ka:<tenant>:<source>:<version>
        upload_id = self.client.create_upload(asset_type=ASSET_FAMILIES["source"], content_type=content_type, idempotency_key=key, owner=owner, visibility=visibility)
        self.client.upload_content(upload_id, data)
        d = self.client.commit(upload_id, sha256=sha256)
        return PhysicalRef(backend=self.name, asset_id=d["asset_id"], asset_version_id=d["asset_version_id"], sha256=d["sha256"],
                           state=d.get("state", "available"), locator=f"{self.client.base_url}/v1/assets/{d['asset_id']}/versions/{d['asset_version_id']}/content",
                           content_type=content_type, byte_size=len(data))

    def get(self, ref: PhysicalRef, *, owner: str | None = None) -> bytes:
        return self.client.get_content(ref.asset_id, ref.asset_version_id, owner=owner)

    def put_derived(self, kind, payload, *, parent, provenance, idempotency_key):
        d = self.client.put_derived(asset_type=kind, payload=payload, parent_asset_id=parent.asset_id if parent else None,
                                    parent_asset_version_id=parent.asset_version_id if parent else None, provenance=provenance, idempotency_key=idempotency_key)
        return PhysicalRef(backend=self.name, asset_id=d["asset_id"], asset_version_id=d["asset_version_id"], sha256=d["sha256"], state=d.get("state", "available"),
                           content_type="application/json", byte_size=len(payload))

    def exists(self, ref: PhysicalRef) -> bool:
        try:
            return self.client.exists(ref.asset_id, ref.asset_version_id)
        except DataPlatformError:
            return False


def describe(store: Any) -> dict[str, Any]:
    return {"backend": getattr(store, "name", "?"), "base_url": getattr(getattr(store, "client", None), "base_url", None)}
# [/block plan-19]
