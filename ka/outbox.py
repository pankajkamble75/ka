# [block plan-20]
"""The pending-operations outbox (research-03 R4): operations KA owes the Data Platform, durable on local disk, retried with backoff by a
worker thread, dead-lettered after `KA_DP_RETRIES`, reconciled by the idempotency key `ka:<tenant>:<source>:<version>` (a replay of a
committed upload returns the same asset ids — contract row 3). No cross-service transaction is attempted: a version whose bytes have
not been committed is `pending`, never `available`. Handlers are a registry so plan-21 (`ack_event`) and plan-22 (`put_derived`) can
add theirs."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ka import config
from ka.data_platform import DataPlatformError
from ka.model import PendingOp
from ka.timeutil import now_iso

NON_RETRYABLE = {400, 401, 403, 404, 409, 413, 422}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class Outbox:
    def __init__(self, repo, bus, auditor, physical):
        self.repo, self.bus, self.auditor, self.physical = repo, bus, auditor, physical
        self.handlers: dict[str, Callable[[PendingOp], None]] = {"upload_source": self._upload_source}
        self._lock = threading.Lock()

    # ---- queue -----------------------------------------------------------------------------------------------

    def enqueue(self, kind: str, idempotency_key: str, payload: dict[str, Any], *, by: str = "ka.outbox") -> PendingOp:
        live = self.repo.dp_outbox.where(lambda o: o.idempotency_key == idempotency_key and o.kind == kind and o.state in ("pending", "done"))
        if live:
            return live[0]                                           # one operation per key
        op = PendingOp(kind=kind, idempotency_key=idempotency_key, payload=payload, by=by, next_at=now_iso())
        return self.repo.dp_outbox.put(op)

    def due(self, now: str | None = None) -> list[PendingOp]:
        t = _parse(now or now_iso())
        return sorted((o for o in self.repo.dp_outbox.where(lambda o: o.state == "pending") if _parse(o.next_at) <= t), key=lambda o: o.created_at)

    def status(self) -> dict[str, Any]:
        ops = self.repo.dp_outbox.all()
        by = {}
        for o in ops:
            by[o.state] = by.get(o.state, 0) + 1
        dead = [{"id": o.id, "kind": o.kind, "key": o.idempotency_key, "attempts": o.attempts, "last_code": o.last_code, "last_error": o.last_error}
                for o in ops if o.state == "dead"]
        nxt = min((o.next_at for o in ops if o.state == "pending"), default=None)
        return {"total": len(ops), "by_state": by, "dead": dead, "next_due_at": nxt, "retries": int(config.get("KA_DP_RETRIES")),
                "interval_s": float(config.get("KA_DP_OUTBOX_INTERVAL"))}

    def retry(self, op_id: str, *, by: str) -> PendingOp:
        op = self.repo.dp_outbox.require(op_id)
        if op.state != "dead":
            raise ValueError(f"operation {op_id} is {op.state}; only a dead operation is retried")
        op.state, op.attempts, op.next_at, op.updated_at = "pending", 0, now_iso(), now_iso()
        op.last_error = f"retry requested by {by}"
        return self.repo.dp_outbox.put(op)

    # ---- processing ---------------------------------------------------------------------------------------------

    def process_once(self, *, by: str = "ka.outbox") -> dict[str, int]:
        done = failed = dead = 0
        with self._lock:
            for op in self.due():
                handler = self.handlers.get(op.kind)
                if handler is None:
                    self._dead(op, "unknown_kind", f"no handler for {op.kind!r}")
                    dead += 1
                    continue
                try:
                    handler(op)
                    op.state, op.updated_at = "done", now_iso()
                    self.repo.dp_outbox.put(op)
                    done += 1
                except DataPlatformError as e:
                    if e.status in NON_RETRYABLE or not e.retryable:
                        self._dead(op, e.code, str(e))
                        self._fail_binding(op, f"{e.code}: {e.message}")
                        dead += 1
                    else:
                        self._backoff(op, e.code, str(e))
                        if op.state == "dead":
                            dead += 1
                        failed += 1
                except Exception as e:  # noqa: BLE001 — a transport failure is retryable
                    self._backoff(op, type(e).__name__, str(e))
                    if op.state == "dead":
                        dead += 1
                    failed += 1
        return {"done": done, "retried": failed, "dead": dead}

    def _backoff(self, op: PendingOp, code: str, err: str) -> None:
        op.attempts += 1
        op.last_code, op.last_error, op.updated_at = code, err[:300], now_iso()
        if op.attempts >= int(config.get("KA_DP_RETRIES")):
            op.state = "dead"
            self.bus.emit("physical.outbox.dead", op_id=op.id, kind=op.kind, code=code)
        else:
            delay = float(config.get("KA_DP_BACKOFF_BASE")) * (2 ** (op.attempts - 1))
            op.next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.repo.dp_outbox.put(op)
        b = self.repo.physical_bindings.get(op.payload.get("binding_id") or "")
        if b is not None and b.status == "pending":
            b.reason = f"{code}: retry {op.attempts}/{config.get('KA_DP_RETRIES')}" + (" — dead-lettered" if op.state == "dead" else "")
            self.repo.physical_bindings.put(b)

    def _dead(self, op: PendingOp, code: str, err: str) -> None:
        op.state, op.last_code, op.last_error, op.updated_at = "dead", code, err[:300], now_iso()
        self.repo.dp_outbox.put(op)
        self.bus.emit("physical.outbox.dead", op_id=op.id, kind=op.kind, code=code)

    def _fail_binding(self, op: PendingOp, reason: str) -> None:
        b = self.repo.physical_bindings.get(op.payload.get("binding_id") or "")
        if b is not None:
            b.status, b.reason, b.last_synced_at = "failed", reason, now_iso()
            self.repo.physical_bindings.put(b)
            spool = op.payload.get("spool_path")
            if spool and Path(spool).exists():
                Path(spool).unlink()

    # ---- handlers -------------------------------------------------------------------------------------------------

    def _upload_source(self, op: PendingOp) -> None:
        p = op.payload
        b = self.repo.physical_bindings.require(p["binding_id"])
        spool = Path(p["spool_path"])
        if not spool.exists():
            raise DataPlatformError(422, "spool_missing", f"bytes for {b.source_version_id} are no longer on disk", retryable=False)
        data = spool.read_bytes()
        ref = self.physical.put(data, content_type=p.get("content_type") or "application/octet-stream", sha256=b.sha256,
                                idempotency_key=op.idempotency_key + f":{b.source_version_id}", owner=b.owner, visibility=b.visibility.value,
                                tenant_id=b.tenant_id, filename_hint=p.get("filename_hint"))
        if ref.sha256 != b.sha256:
            raise DataPlatformError(422, "checksum_mismatch", "the committed sha differs from the version's", retryable=False)
        b.status, b.reason, b.locator = ref.state, None, ref.locator
        b.dp_asset_id, b.dp_asset_version_id, b.last_synced_at = ref.asset_id, ref.asset_version_id, now_iso()
        self.repo.physical_bindings.put(b)
        spool.unlink(missing_ok=True)
        self.bus.emit("physical.binding.available", binding_id=b.id, source_version_id=b.source_version_id)
        self.auditor.record(who=op.by, what="physical.binding.available", why=f"outbox {op.kind} after {op.attempts} retries", source=b.ka_source_id,
                            affected=[b.id, b.source_version_id])

    # ---- reconciliation -----------------------------------------------------------------------------------------------

    def reconcile(self) -> dict[str, int]:
        requeued = failed = 0
        keyed = {o.idempotency_key for o in self.repo.dp_outbox.where(lambda o: o.state in ("pending", "dead"))}
        for b in self.repo.physical_bindings.where(lambda b: b.status == "pending" and b.backend == "data_platform"):
            key = f"ka:{b.tenant_id}:{b.ka_source_id}:{b.ka_source_version}"
            if key in keyed:
                continue
            spool = self.repo.root / "spool" / f"{b.source_version_id}.bin"
            if spool.exists():
                self.enqueue("upload_source", key, {"binding_id": b.id, "source_version_id": b.source_version_id, "spool_path": str(spool)})
                requeued += 1
            else:
                b.status, b.reason, b.last_synced_at = "failed", "bytes lost before the operation was queued", now_iso()
                self.repo.physical_bindings.put(b)
                failed += 1
        return {"requeued": requeued, "failed": failed}


class OutboxWorker:
    """A daemon thread that runs `process_once` every KA_DP_OUTBOX_INTERVAL seconds (plan-17's thread pattern)."""

    def __init__(self, outbox: Outbox):
        self.outbox = outbox
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.runs = 0

    def start(self) -> None:
        if self.thread is not None:
            return
        self.outbox.reconcile()
        self.thread = threading.Thread(target=self._loop, name="ka-dp-outbox", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.outbox.process_once()
            except Exception:  # noqa: BLE001 — the worker must survive anything
                pass
            self.runs += 1
            self._stop.wait(float(config.get("KA_DP_OUTBOX_INTERVAL")))
# [/block plan-20]
