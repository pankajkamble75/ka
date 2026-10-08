# [block plan-08]
"""Managed connectors (research-01 R10, note REQ-002): a provider-agnostic contract for enumerating a source system,
fetching its documents, reading their permissions, and syncing incrementally from a checkpoint — with revocation.

The only exit is `IngestionService.connect()`, so provenance, checksums and versioning are the existing rules. Secrets never
enter a stored object: a `Connection.secret_ref` NAMES an environment variable; providers that need one read it at call time.
The local folder is the first connector (Q6 decides the cloud and enterprise ones).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ConnectorError(RuntimeError):
    pass


@dataclass
class ConnectorItem:
    locator: str
    name: str
    modified_at: str
    size: int
    checksum: str
    visibility: str | None = None          # overrides the connection's visibility when the provider knows better
    principals: list[str] = field(default_factory=list)
    deleted: bool = False


@dataclass
class SyncDelta:
    new: list[ConnectorItem] = field(default_factory=list)
    modified: list[ConnectorItem] = field(default_factory=list)
    moved: list[tuple[str, ConnectorItem]] = field(default_factory=list)      # (old_locator, item)
    deleted: list[str] = field(default_factory=list)                          # locators
    permission_changed: list[ConnectorItem] = field(default_factory=list)
    checkpoint: dict[str, Any] = field(default_factory=dict)

    def empty(self) -> bool:
        return not (self.new or self.modified or self.moved or self.deleted or self.permission_changed)


class Connector(Protocol):
    kind: str

    def authorize(self, connection) -> None: ...
    def enumerate(self, connection, cursor: str | None = None) -> tuple[list[ConnectorItem], str | None]: ...
    def fetch(self, connection, item: ConnectorItem) -> bytes: ...
    def get_permissions(self, connection, item: ConnectorItem) -> dict[str, Any]: ...
    def checkpoint(self, connection) -> dict[str, Any]: ...
    def sync_incremental(self, connection, checkpoint: dict[str, Any]) -> SyncDelta: ...
    def revoke(self, connection) -> None: ...


def get_connector(kind: str) -> Connector:
    from ka.connectors.local_folder import LocalFolderConnector
    kinds: dict[str, type] = {"local_folder": LocalFolderConnector}
    if kind not in kinds:
        raise ConnectorError(f"unknown connector kind {kind!r}; known: {', '.join(kinds)}")
    return kinds[kind]()


CONNECTOR_KINDS = ("local_folder",)
# [/block plan-08]
