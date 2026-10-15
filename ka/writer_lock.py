"""SCRIPT #025: the exclusive-writer lease for KA's store (NEXOS MVP spec, shared with KW and DP).

At most one process writes `<store_root>` at a time — across Cloud Run revision overlap, the seed job and restarts.

* The lease is ONE file, `<store_root>/.writer.lock`, created only by an atomic exclusive create (tmp + `os.link`, falling
  back to `O_CREAT|O_EXCL`). It holds {owner_id, host, pid, revision, acquired_at}. Nothing ever renames or replaces over it,
  and there is NO automatic stale takeover: a SIGKILLed holder leaves the file and successors wait, then exit (fail safe).
* The service acquires in the background (`start_service`). Until it holds the lease it is in STANDBY: the readiness probe
  answers 200 {"status": "standby"}, every other route 503 + Retry-After, and no store state (no `KnowledgeAcquisition`, no
  collection cache) is loaded. After `KA_LOCK_WAIT_SECONDS` it gives up and SIGTERMs itself (non-zero exit).
* Every write (`guard(path)`, called by ka.json_io and the few raw writers) re-reads the lock and compares owner_id. A mismatch
  is ownership loss: the write is refused, the process turns terminal "lost" (all routes 503) and SIGTERMs itself.
* Shutdown stops writes first, then removes the lock only if it is still ours.
* Break-glass: `knowledge-acquisition break-writer-lock --owner-id <id>` removes the lock only if its owner_id matches.

`KA_WRITER_LOCK=off` disables all of it (local development and the in-process test suite, which never registers a lease).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCK_NAME = ".writer.lock"

# lease states
STANDBY, ACTIVE, STOPPING, RELEASED, LOST, FAILED = "standby", "active", "stopping", "released", "lost", "failed"


class WriterLockError(RuntimeError):
    """A write was refused because this process does not (or no longer) hold the store's writer lease."""


class LockHeld(WriterLockError):
    def __init__(self, path: Path, holder: dict[str, Any] | None):
        self.holder = holder or {}
        super().__init__(f"the writer lock {path} is held by owner_id={self.holder.get('owner_id', '?')} "
                         f"(host={self.holder.get('host', '?')}, pid={self.holder.get('pid', '?')}, "
                         f"revision={self.holder.get('revision') or '-'}, since {self.holder.get('acquired_at', '?')})")


def enabled() -> bool:
    from ka import config
    return (config.get("KA_WRITER_LOCK") or "on").strip().lower() not in {"off", "0", "false", "no"}


def lock_path(root: Path | str) -> Path:
    return Path(root) / LOCK_NAME


def read_lock(root: Path | str) -> dict[str, Any] | None:
    """The lock's content; None when there is no lock. An unreadable/garbled lock reads as {} (held, owner unknown)."""
    p = lock_path(root)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _create_exclusive(path: Path, payload: bytes) -> bool:
    """Atomically create `path` with `payload`; False if it already exists. Never replaces an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(tmp, path)                                   # complete content appears at once, or EEXIST
        return True
    except FileExistsError:
        return False
    except OSError:                                          # no hard links on this filesystem: exclusive create + write
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


class WriterLease:
    def __init__(self, root: Path | str, *, role: str = "service", exit_on_loss: bool = False):
        self.root = Path(root).resolve()
        self.path = lock_path(self.root)
        self.role = role
        self.exit_on_loss = exit_on_loss
        self.owner_id = uuid.uuid4().hex
        self.state = STANDBY
        self.reason = ""
        self._mu = threading.RLock()

    # ---- acquire / release ------------------------------------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        return {"owner_id": self.owner_id, "host": socket.gethostname(), "pid": os.getpid(), "role": self.role,
                "revision": os.environ.get("K_REVISION") or os.environ.get("CLOUD_RUN_EXECUTION") or None,
                "acquired_at": datetime.now(timezone.utc).isoformat()}

    def try_acquire(self) -> bool:
        with self._mu:
            if self.state == ACTIVE:
                return True
            if self.state != STANDBY:
                return False
            payload = (json.dumps(self.record(), sort_keys=True) + "\n").encode()
            if _create_exclusive(self.path, payload):
                self.state = ACTIVE
                return True
            return False

    def acquire(self, wait_seconds: float, poll_seconds: float = 3.0, stop: threading.Event | None = None) -> bool:
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            if self.try_acquire():
                return True
            left = deadline - time.monotonic()
            if left <= 0 or (stop is not None and stop.is_set()):
                return False
            if stop is not None:
                stop.wait(min(poll_seconds, left))
            else:
                time.sleep(min(poll_seconds, left))

    def release(self) -> bool:
        """Stop writes, then remove the lock only if it is still ours. True if a lock was removed."""
        with self._mu:
            was = self.state
            if was in (ACTIVE, STANDBY):
                self.state = STOPPING
            if was != ACTIVE:
                if self.state == STOPPING:
                    self.state = RELEASED
                return False
            removed = False
            cur = read_lock(self.root)
            if cur and cur.get("owner_id") == self.owner_id:
                try:
                    os.unlink(self.path)
                    removed = True
                except FileNotFoundError:
                    pass
            self.state = RELEASED
            return removed

    # ---- the fencing check -------------------------------------------------------------------------------------------

    def verify(self, what: str = "write") -> None:
        """Raise unless this process holds the lease right now (re-reads the lock file; called before every write)."""
        st = self.state
        if st != ACTIVE:
            why = f" ({self.reason})" if self.reason else ""
            raise WriterLockError(f"{what} refused: KA's writer lease on {self.root} is {st}{why}")
        cur = read_lock(self.root)
        if cur is None or cur.get("owner_id") != self.owner_id:
            seen = "missing" if cur is None else f"owner_id={cur.get('owner_id', 'unreadable')}"
            self.lose(f"lock file is {seen}, expected owner_id={self.owner_id}")
            raise WriterLockError(f"{what} refused: KA lost its writer lease on {self.root} ({seen})")

    def lose(self, reason: str) -> None:
        with self._mu:
            if self.state in (LOST, RELEASED):
                return
            self.state, self.reason = LOST, reason
        print(f"knowledge-acquisition: WRITER LEASE LOST on {self.root}: {reason}; refusing all writes and exiting", flush=True)
        if self.exit_on_loss:
            os.kill(os.getpid(), signal.SIGTERM)


# ---- process-wide registry: the fence every writer consults ----------------------------------------------------------

_leases: dict[Path, WriterLease] = {}
_reg_mu = threading.Lock()


def register(lease: WriterLease) -> WriterLease:
    with _reg_mu:
        _leases[lease.root] = lease
    return lease


def unregister(lease: WriterLease) -> None:
    with _reg_mu:
        if _leases.get(lease.root) is lease:
            del _leases[lease.root]


def lease_for(path: Path | str) -> WriterLease | None:
    if not _leases:
        return None
    p = Path(os.path.abspath(path))
    try:
        p = p.resolve()
    except OSError:
        pass
    for root, lease in list(_leases.items()):
        if p == root or root in p.parents:
            return lease
    return None


def guard(path: Path | str, what: str = "write") -> None:
    """Called before every mutation of a file under a registered store root. No-op when no lease covers `path`."""
    lease = lease_for(path)
    if lease is not None:
        lease.verify(f"{what} {path}")


# ---- the service lifecycle -----------------------------------------------------------------------------------------

_service: WriterLease | None = None
_stop = threading.Event()


def service_lease() -> WriterLease | None:
    return _service


def service_state() -> str:
    """'active' when no service lease is configured (lock off, tests, an in-process app)."""
    return _service.state if _service is not None else ACTIVE


def configure_service(root: Path | str) -> WriterLease | None:
    """`serve`: register the service's lease in STANDBY (writes refused) before the app loads anything."""
    global _service
    if not enabled():
        return None
    _service = register(WriterLease(root, role="service", exit_on_loss=True))
    _stop.clear()
    return _service


def start_service() -> None:
    """App startup: acquire in the background; on timeout turn FAILED and SIGTERM self (the server exits non-zero)."""
    lease = _service
    if lease is None or lease.state != STANDBY:
        return
    from ka import config

    def run() -> None:
        wait = float(config.get("KA_LOCK_WAIT_SECONDS"))
        poll = float(config.get("KA_LOCK_POLL_SECONDS"))
        if lease.acquire(wait, poll, stop=_stop):
            print(f"knowledge-acquisition: writer lease acquired on {lease.root} (owner_id={lease.owner_id})", flush=True)
            return
        if _stop.is_set():
            return
        holder = read_lock(lease.root)
        with lease._mu:
            lease.state, lease.reason = FAILED, f"lock still held after {wait:g}s by {(holder or {}).get('owner_id', '?')}"
        print(f"knowledge-acquisition: {LockHeld(lease.path, holder)}; gave up after {wait:g}s (KA_LOCK_WAIT_SECONDS). "
              f"If that writer is gone, see `knowledge-acquisition break-writer-lock --owner-id <id>`. Exiting.", flush=True)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=run, name="ka-writer-lease", daemon=True).start()


def stop_service() -> None:
    """App shutdown / atexit: stop writes, then remove the lock if it is ours."""
    _stop.set()
    lease = _service
    if lease is not None and lease.release():
        print(f"knowledge-acquisition: writer lease released on {lease.root}", flush=True)


def exit_code() -> int:
    return 1 if _service is not None and _service.state in (LOST, FAILED) else 0


# ---- one-shot jobs (seed-demo, demo) -------------------------------------------------------------------------------

class one_shot:
    """`with one_shot(root, wait): ...` — acquire with a short wait or raise LockHeld; always release on exit."""

    def __init__(self, root: Path | str, wait_seconds: float, role: str = "job"):
        self.lease = WriterLease(root, role=role)
        self.wait = wait_seconds

    def __enter__(self) -> WriterLease | None:
        if not enabled():
            return None
        if not self.lease.acquire(self.wait, poll_seconds=min(1.0, max(self.wait, 0.05))):
            raise LockHeld(self.lease.path, read_lock(self.lease.root))
        register(self.lease)
        return self.lease

    def __exit__(self, *exc) -> None:
        if enabled():
            self.lease.release()
            unregister(self.lease)


# ---- break-glass -----------------------------------------------------------------------------------------------------

def break_lock(root: Path | str, owner_id: str) -> tuple[bool, str]:
    """Remove the lock only if its owner_id equals `owner_id`. The operator confirms the old writer is gone first."""
    cur = read_lock(root)
    p = lock_path(root)
    if cur is None:
        return False, f"no writer lock at {p}"
    if not owner_id or cur.get("owner_id") != owner_id:
        return False, f"refused: {p} is owned by owner_id={cur.get('owner_id', 'unreadable')}, not {owner_id!r}"
    os.unlink(p)
    return True, f"removed {p} (was {json.dumps(cur, sort_keys=True)})"
