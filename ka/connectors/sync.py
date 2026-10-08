# [block plan-08]
"""Sync reconciliation (research-01 R10): a delta from a connector becomes sources and versions through the ONE ingestion
door, never losing history —

    new                 → Source (+ extraction through governance)
    modified            → new SourceVersion of the same Source (+ extraction); old versions untouched
    moved               → the Source keeps its id; original_location updated; no new version (same bytes)
    deleted             → Source.revoked_at set, versions kept, derived nuggets kept and FLAGGED (retiring them is Q4)
    permission_changed  → Source.visibility updated; derived nuggets flagged (narrowing retroactively is Q4)

A revoked connection refuses to sync. Files over the upload cap are skipped with a reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ka import config
from ka.audit import Auditor
from ka.connectors import ConnectorError, ConnectorItem, get_connector
from ka.events import EventBus
from ka.governance import GovernanceService
from ka.ingestion import IngestionService
from ka.model import Connection, Scope, Source
from ka.repository import Repository
from ka.timeutil import now_iso
from ka.vocab import AuthorityType, NuggetStatus, Visibility


@dataclass
class SyncReport:
    connection_id: str
    new: int = 0
    modified: int = 0
    moved: int = 0
    deleted: int = 0
    permission_changed: int = 0
    skipped: list[dict[str, Any]] = field(default_factory=list)
    candidates: int = 0
    source_ids: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {"new": self.new, "modified": self.modified, "moved": self.moved, "deleted": self.deleted,
                "permission_changed": self.permission_changed, "skipped": len(self.skipped), "candidates": self.candidates}


class SyncService:
    def __init__(self, repo: Repository, ingestion: IngestionService, governance: GovernanceService, auditor: Auditor, bus: EventBus):
        self.repo, self.ingestion, self.governance, self.auditor, self.bus = repo, ingestion, governance, auditor, bus

    # ---- connections --------------------------------------------------------------------------------------

    def create(self, kind: str, name: str, config_: dict[str, Any], *, owner: str, scope: Scope,
               authority: AuthorityType = AuthorityType.PROJECT_DOCUMENTATION, visibility: Visibility = Visibility.ENTERPRISE,
               secret_ref: str | None = None) -> Connection:
        connector = get_connector(kind)
        conn = Connection(kind=kind, name=name, config=dict(config_), owner=owner, scope=scope, authority=authority,
                          visibility=visibility, secret_ref=secret_ref)
        connector.authorize(conn)                       # raises ConnectorError before anything is stored
        self.repo.connections.put(conn)
        self.auditor.record(who=owner, what="connector.created", why=f"{kind} {name}", scope=scope, affected=[conn.id])
        return conn

    def revoke(self, connection_id: str, *, by: str, reason: str = "") -> Connection:
        conn = self.repo.connections.require(connection_id)
        get_connector(conn.kind).revoke(conn)
        conn.status, conn.revoked_at = "revoked", now_iso()
        self.repo.connections.put(conn)
        self.auditor.record(who=by, what="connector.revoked", why=reason, scope=conn.scope, affected=[conn.id])
        return conn

    # ---- sync -------------------------------------------------------------------------------------------------

    def sync(self, connection_id: str, *, by: str) -> SyncReport:
        conn = self.repo.connections.require(connection_id)
        if conn.status != "active":
            raise ConnectorError(f"connection {conn.id} is {conn.status}; it cannot sync")
        connector = get_connector(conn.kind)
        connector.authorize(conn)
        delta = connector.sync_incremental(conn, conn.checkpoint)
        report = SyncReport(connection_id=conn.id)
        cap = config.get("KA_MAX_UPLOAD_MB") * 1024 * 1024

        def ingest(item: ConnectorItem, what: str) -> None:
            if item.size > cap:
                report.skipped.append({"locator": item.locator, "reason": f"over KA_MAX_UPLOAD_MB ({config.get('KA_MAX_UPLOAD_MB')} MB)"})
                return
            try:
                payload = connector.fetch(conn, item)
            except Exception as e:  # noqa: BLE001 — one unreadable file must not abort the sync
                report.skipped.append({"locator": item.locator, "reason": f"fetch failed: {type(e).__name__}: {e}"})
                return
            vis = Visibility(item.visibility) if item.visibility else conn.visibility
            got = self.ingestion.connect(connector=conn.kind, locator=f"{conn.id}/{item.locator}", payload=payload, owner=conn.owner,
                                         scope=conn.scope, title=item.name, authority=conn.authority, visibility=vis,
                                         media_type="application/octet-stream")
            src = got.source
            src.connection_id = conn.id
            src.metadata.update({"connector": conn.kind, "connection_id": conn.id, "locator": item.locator, "modified_at": item.modified_at,
                                 "synced_at": now_iso()})
            src.original_filename = item.name
            self.repo.sources.put(src)
            report.source_ids.append(src.id)
            self.bus.emit("source.synced", source_id=src.id, connection_id=conn.id, change=what)
            if got.extraction.text.strip() and (what == "new" or got.is_new_version):
                try:
                    cands = self.governance.extract_from_source(src, got.version, got.extraction, actor=by)
                    report.candidates += len(cands)
                except Exception as e:  # noqa: BLE001
                    report.skipped.append({"locator": item.locator, "reason": f"extraction failed: {type(e).__name__}: {e}"})

        for item in delta.new:
            ingest(item, "new")
            report.new += 1
        for item in delta.modified:
            ingest(item, "modified")
            report.modified += 1
        for old, item in delta.moved:
            src = self._source_for(conn, old)
            if src is not None:
                src.original_location = f"{conn.kind}://{conn.id}/{item.locator}"
                src.original_filename = item.name
                src.metadata["locator"] = item.locator
                self.repo.sources.put(src)
                self.auditor.record(who=by, what="source.moved", why=f"{old} → {item.locator}", source=src.id, scope=conn.scope, affected=[src.id])
                report.source_ids.append(src.id)
            report.moved += 1
        for loc in delta.deleted:
            src = self._source_for(conn, loc)
            if src is not None and not src.revoked_at:
                src.revoked_at = now_iso()
                self.repo.sources.put(src)
                self._flag_derived(src, "source_revoked")
                self.bus.emit("source.revoked", source_id=src.id, connection_id=conn.id)
                self.auditor.record(who=by, what="source.revoked", why="deleted at the connector", source=src.id, scope=conn.scope, affected=[src.id])
            report.deleted += 1
        for item in delta.permission_changed:
            src = self._source_for(conn, item.locator)
            if src is not None:
                before = src.visibility.value
                src.visibility = Visibility(item.visibility) if item.visibility else conn.visibility
                self.repo.sources.put(src)
                self._flag_derived(src, "source_visibility_changed", {"from": before, "to": src.visibility.value})
                self.bus.emit("source.permission_changed", source_id=src.id, connection_id=conn.id)
                self.auditor.record(who=by, what="source.permission_changed", why=f"{before} → {src.visibility.value}", source=src.id, scope=conn.scope,
                                    before={"visibility": before}, after={"visibility": src.visibility.value}, affected=[src.id])
            report.permission_changed += 1

        conn.checkpoint, conn.last_sync_at = delta.checkpoint, now_iso()
        conn.last_delta = {"new": [i.locator for i in delta.new], "modified": [i.locator for i in delta.modified],
                           "moved": [[o, i.locator] for o, i in delta.moved], "deleted": list(delta.deleted),
                           "permission_changed": [i.locator for i in delta.permission_changed], "skipped": report.skipped}
        conn.stats = report.counts()
        self.repo.connections.put(conn)
        self.auditor.record(who=by, what="connector.synced", why=str(report.counts()), scope=conn.scope, affected=[conn.id] + report.source_ids)
        return report

    # ---- helpers ------------------------------------------------------------------------------------------

    def _source_for(self, conn: Connection, locator: str) -> Source | None:
        hits = self.repo.sources.where(lambda s: s.connection_id == conn.id and s.metadata.get("locator") == locator)
        return hits[0] if hits else None

    def _flag_derived(self, src: Source, flag: str, detail: dict | None = None) -> int:
        n = 0
        for v in self.repo.nuggets.where(lambda n_: src.id in n_.source_refs):
            v.analysis[flag] = detail or {"at": now_iso()}
            self.repo.nuggets.put(v)                      # analysis is bookkeeping, not semantics (Inv. 3 untouched)
            n += 1
        return n

    def revoked_with_active_knowledge(self) -> list[dict[str, Any]]:
        out = []
        for src in self.repo.sources.where(lambda s: s.revoked_at is not None):
            active = [v for v in self.repo.nuggets.where(lambda n: src.id in n.source_refs) if v.status == NuggetStatus.ACTIVE]
            if active:
                out.append({"source_id": src.id, "title": src.title, "revoked_at": src.revoked_at, "connection_id": src.connection_id,
                            "active_nuggets": [v.ref for v in active], "note": "derived knowledge kept and flagged; retiring it is Q4"})
        return out
# [/block plan-08]
