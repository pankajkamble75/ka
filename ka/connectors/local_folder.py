# [block plan-08]
"""The local-folder connector: the first `Connector`, needing no credentials. It exercises enumeration, checkpoints and
incremental sync (new / modified / moved / deleted / permission-changed) over files under a root that must lie inside one
of `KA_CONNECTOR_ROOTS`. A sidecar `<name>.visibility` file (PERSONAL | TEAM | DOMAIN | INSTANCE | ENTERPRISE) overrides the
connection's visibility for that file.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ka import config
from ka.connectors import ConnectorError, ConnectorItem, SyncDelta
from ka.vocab import Visibility

DEFAULT_INCLUDE = ["**/*.md", "**/*.txt", "**/*.pdf", "**/*.docx", "**/*.pptx", "**/*.xlsx", "**/*.csv", "**/*.html"]


def allowed_roots() -> list[Path]:
    raw = config.get("KA_CONNECTOR_ROOTS") or ""
    roots = [Path(p.strip()).resolve() for p in raw.split(",") if p.strip()]
    if not roots:
        roots = [(config.storage_root() / "inbox").resolve()]
    return roots


class LocalFolderConnector:
    kind = "local_folder"

    # ---- contract -------------------------------------------------------------------------------------------

    def _root(self, connection) -> Path:
        raw = (connection.config or {}).get("root")
        if not raw:
            raise ConnectorError("local_folder needs config.root")
        root = Path(raw).resolve()                           # resolves symlinks, so an escaping link is caught below
        if not any(root == r or r in root.parents for r in allowed_roots()):
            raise ConnectorError(f"root {raw!r} is outside KA_CONNECTOR_ROOTS ({', '.join(str(r) for r in allowed_roots())})")
        return root

    def authorize(self, connection) -> None:
        root = self._root(connection)
        if not root.is_dir():
            raise ConnectorError(f"root {root} is not a directory")

    def enumerate(self, connection, cursor: str | None = None) -> tuple[list[ConnectorItem], str | None]:
        root = self._root(connection)
        include = (connection.config or {}).get("include") or DEFAULT_INCLUDE
        items: list[ConnectorItem] = []
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                p = Path(dirpath) / fn
                if p.is_symlink() or fn.endswith(".visibility"):
                    continue
                rel = p.relative_to(root).as_posix()
                if not any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(fn, pat.split("/")[-1]) for pat in include):
                    continue
                data = p.read_bytes()
                items.append(ConnectorItem(locator=rel, name=fn, modified_at=datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
                                           size=len(data), checksum=hashlib.sha256(data).hexdigest(),
                                           visibility=self._sidecar(p), principals=[connection.owner]))
        return items, None

    def fetch(self, connection, item: ConnectorItem) -> bytes:
        root = self._root(connection)
        p = (root / item.locator).resolve()
        if root not in p.parents:
            raise ConnectorError(f"{item.locator!r} escapes the connection root")
        return p.read_bytes()

    def get_permissions(self, connection, item: ConnectorItem) -> dict[str, Any]:
        return {"visibility": item.visibility or connection.visibility.value, "principals": list(item.principals)}

    def checkpoint(self, connection) -> dict[str, Any]:
        items, _ = self.enumerate(connection)
        return {i.locator: {"mtime": i.modified_at, "size": i.size, "checksum": i.checksum, "visibility": i.visibility} for i in items}

    def sync_incremental(self, connection, checkpoint: dict[str, Any]) -> SyncDelta:
        items, _ = self.enumerate(connection)
        now = {i.locator: i for i in items}
        delta = SyncDelta()
        prior_by_checksum = {v["checksum"]: loc for loc, v in (checkpoint or {}).items()}
        for loc, item in now.items():
            prior = (checkpoint or {}).get(loc)
            if prior is None:
                old = prior_by_checksum.get(item.checksum)
                if old and old not in now:
                    delta.moved.append((old, item))
                else:
                    delta.new.append(item)
            else:
                if prior["checksum"] != item.checksum:
                    delta.modified.append(item)
                if (prior.get("visibility") or None) != (item.visibility or None):
                    delta.permission_changed.append(item)
        moved_from = {old for old, _ in delta.moved}
        for loc in (checkpoint or {}):
            if loc not in now and loc not in moved_from:
                delta.deleted.append(loc)
        delta.checkpoint = {i.locator: {"mtime": i.modified_at, "size": i.size, "checksum": i.checksum, "visibility": i.visibility} for i in items}
        return delta

    def revoke(self, connection) -> None:
        return None                                           # nothing to tear down for a folder

    # ---- helpers --------------------------------------------------------------------------------------------

    @staticmethod
    def _sidecar(p: Path) -> str | None:
        side = p.with_name(p.name + ".visibility")
        if side.exists():
            v = side.read_text(encoding="utf-8").strip().upper()
            if v in Visibility.__members__:
                return v
        return None
# [/block plan-08]
