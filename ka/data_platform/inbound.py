# [block plan-21]
"""Inbound Data Platform events (research-03 R5): KA polls `GET /v1/events?after=<seq>` with a durable cursor, handles each event once
(by `event_id`), and answers each type as §5 decides — `committed` flips a pending binding to available; `access_revoked`, `quarantined`
and `deleted` go through the ONE revocation rule (`SyncService.revoke_source`, R9) so derived knowledge returns to review exactly as
after a deleted connector file; `index.ready` and `ingestion.completed` are recorded. Unknown types and unknown assets are recorded
and ignored. The cursor is the acknowledgement — the contract has no ack call."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ka.data_platform import DataPlatformClient, DataPlatformError
from ka.timeutil import now_iso

HANDLED_KEEP = 5000


class InboundEvents:
    def __init__(self, repo, bus, auditor, connectors, *, cursor_path: Path | None = None):
        self.repo, self.bus, self.auditor, self.connectors = repo, bus, auditor, connectors
        self.path = cursor_path or (repo.root / "dp_inbound.json")
        self.state = self._load()
        self.last_error: str | None = None

    # ---- cursor -------------------------------------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"after": 0, "handled": [], "last_poll_at": None, "unmatched": 0, "received": 0}
        except (OSError, ValueError):
            return {"after": 0, "handled": [], "last_poll_at": None, "unmatched": 0, "received": 0}

    def _save(self) -> None:
        self.state["handled"] = self.state["handled"][-HANDLED_KEEP:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state), encoding="utf-8")

    def status(self) -> dict[str, Any]:
        return {"after": self.state.get("after", 0), "handled": len(self.state.get("handled", [])), "received": self.state.get("received", 0),
                "unmatched": self.state.get("unmatched", 0), "last_poll_at": self.state.get("last_poll_at"), "last_error": self.last_error}

    # ---- polling ----------------------------------------------------------------------------------------------------

    def poll(self, client: DataPlatformClient, *, by: str = "data-platform") -> dict[str, int]:
        counts = {"received": 0, "handled": 0, "duplicate": 0, "unmatched": 0, "ignored": 0}
        try:
            page = client.events(after=int(self.state.get("after", 0)))
        except (DataPlatformError, Exception) as e:  # noqa: BLE001 — a failed poll leaves the cursor where it was
            self.last_error = f"{type(e).__name__}: {e}"[:300]
            return counts
        self.last_error = None
        for ev in page.get("events", []):
            counts["received"] += 1
            self.state["received"] = self.state.get("received", 0) + 1
            eid = ev.get("event_id")
            if not eid or eid in self.state["handled"]:
                counts["duplicate"] += 1
                continue
            outcome = self.handle(ev, by=by)
            counts[outcome] = counts.get(outcome, 0) + 1
            self.state["handled"].append(eid)
            self.bus.emit("physical.event.received", dp_event_id=eid, type=ev.get("type", ""), asset_id=ev.get("asset_id") or "")
        self.state["after"] = int(page.get("next_after", self.state.get("after", 0)))
        self.state["last_poll_at"] = now_iso()
        self._save()
        return counts

    # ---- handlers ------------------------------------------------------------------------------------------------------

    def _binding_for_asset(self, asset_id: str | None, version_id: str | None):
        if not asset_id:
            return None
        hits = self.repo.physical_bindings.where(lambda b: b.dp_asset_id == asset_id and (not version_id or b.dp_asset_version_id == version_id))
        return hits[0] if hits else None

    def handle(self, ev: dict[str, Any], *, by: str = "data-platform") -> str:
        t = ev.get("type", "")
        b = self._binding_for_asset(ev.get("asset_id"), ev.get("asset_version_id"))
        if t == "data.asset.committed.v1":
            if b is None:
                self.state["unmatched"] = self.state.get("unmatched", 0) + 1
                return "unmatched"
            if b.status == "pending":
                b.status, b.reason, b.last_synced_at = "available", None, now_iso()
                self.repo.physical_bindings.put(b)
                self.bus.emit("physical.binding.available", binding_id=b.id, source_version_id=b.source_version_id)
            return "handled"
        if t in ("data.asset.access_revoked.v1", "data.asset.quarantined.v1", "data.asset.deleted.v1"):
            if b is None:
                self.state["unmatched"] = self.state.get("unmatched", 0) + 1
                return "unmatched"
            reason = t.split(".")[2].replace("_", " ")                         # access revoked | quarantined | deleted
            b.status, b.reason, b.last_synced_at = "revoked", f"{reason} at the Data Platform ({ev.get('event_id')})", now_iso()
            self.repo.physical_bindings.put(b)
            self.bus.emit("physical.binding.revoked", binding_id=b.id, source_version_id=b.source_version_id, reason=reason)
            src = self.repo.sources.get(b.ka_source_id)
            if src is not None:
                self.connectors.revoke_source(src, by=by, reason=f"{reason} at the Data Platform")
            return "handled"
        if t == "data.index.ready.v1":
            if b is not None and ev.get("derived_asset_id"):
                b.extracted_text_asset_id = ev["derived_asset_id"]
                self.repo.physical_bindings.put(b)
            return "handled"
        if t == "data.ingestion.completed.v1":
            return "handled"
        return "ignored"
# [/block plan-21]
