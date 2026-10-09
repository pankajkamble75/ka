# [block plan-18]
"""The physical store port (research-03 R2): every byte KA keeps goes through `PhysicalStore.put`, is read back through `get`, and
derived artefacts (extracted text, nugget versions) go through `put_derived`. `LocalPhysicalStore` is today's behaviour — files
under `<storage>/blobs` and `<storage>/derived` — and the default. The Data Platform store (HTTP to DP v1, no cloud SDK) arrives with
plan-19; until then `KA_STORAGE_BACKEND=data_platform` fails closed to local with a note the console shows.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ka import config

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class PhysicalRef:
    backend: str
    asset_id: str
    asset_version_id: str
    sha256: str
    state: str = "available"            # pending | available | failed | revoked
    locator: str | None = None          # local path, or a DP content URL
    content_type: str | None = None
    byte_size: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "asset_id": self.asset_id, "asset_version_id": self.asset_version_id, "sha256": self.sha256,
                "state": self.state, "locator": self.locator, "content_type": self.content_type, "byte_size": self.byte_size}


class PhysicalStore(Protocol):
    name: str

    def put(self, data: bytes, *, content_type: str, sha256: str, idempotency_key: str, owner: str | None, visibility: str,
            tenant_id: str, filename_hint: str | None = None) -> PhysicalRef: ...
    def get(self, ref: PhysicalRef) -> bytes: ...
    def put_derived(self, kind: str, payload: bytes, *, parent: PhysicalRef | None, provenance: dict[str, Any], idempotency_key: str) -> PhysicalRef: ...
    def exists(self, ref: PhysicalRef) -> bool: ...


class LocalPhysicalStore:
    """Files beside the JSON objects — exactly where `_ingest` wrote before plan-18."""
    name = "local"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.blob_dir = self.root / "blobs"
        self.derived_dir = self.root / "derived"

    def put(self, data, *, content_type, sha256, idempotency_key, owner, visibility, tenant_id, filename_hint=None):
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename_hint).suffix if filename_hint else ".bin"
        asset_id = _SAFE.sub("_", idempotency_key.rsplit(":", 1)[-1])      # the caller's last key segment: the version id
        path = self.blob_dir / f"{asset_id}{suffix or '.bin'}"
        path.write_bytes(data)
        return PhysicalRef(backend=self.name, asset_id=asset_id, asset_version_id="1", sha256=sha256, state="available", locator=str(path),
                           content_type=content_type, byte_size=len(data))

    def get(self, ref):
        if not ref.locator or not Path(ref.locator).exists():
            raise FileNotFoundError(f"no local bytes at {ref.locator!r}")
        return Path(ref.locator).read_bytes()

    def put_derived(self, kind, payload, *, parent, provenance, idempotency_key):
        d = self.derived_dir / _SAFE.sub("_", kind)
        d.mkdir(parents=True, exist_ok=True)
        key = _SAFE.sub("_", idempotency_key)
        path = d / f"{key}.json"
        path.write_bytes(payload)
        return PhysicalRef(backend=self.name, asset_id=f"{kind}:{key}", asset_version_id="1", sha256=hashlib.sha256(payload).hexdigest(),
                           state="available", locator=str(path), content_type="application/json", byte_size=len(payload))

    def exists(self, ref):
        return bool(ref.locator) and Path(ref.locator).exists()


def select_physical_store(root: Path) -> tuple[PhysicalStore, str | None]:
    """The configured backend, failing closed to local with a note when the choice cannot be honoured."""
    choice = (config.get("KA_STORAGE_BACKEND") or "local").strip().lower()
    if choice == "local":
        return LocalPhysicalStore(root), None
    if choice == "data_platform":
        try:
            from ka.data_platform.store import DataPlatformPhysicalStore  # plan-19
            return DataPlatformPhysicalStore.from_config(root), None
        except ImportError as e:                                           # ConfigurationError is an ImportError: fail closed, say why
            return LocalPhysicalStore(root), f"data_platform backend requested but {e}; failing closed to local"
    return LocalPhysicalStore(root), f"unknown KA_STORAGE_BACKEND {choice!r}; failing closed to local"


# [block plan-23] research-03 R12: KA's three asset families on the Data Platform — documents, never rows
ASSET_FAMILIES = {"source": "source_document", "text": "extracted_text", "nugget": "nugget_version"}
# [/block plan-23]


def binding_key(tenant_id: str, source_id: str, version: int) -> str:
    return f"ka:{tenant_id}:{source_id}:{version}"
# [/block plan-18]
