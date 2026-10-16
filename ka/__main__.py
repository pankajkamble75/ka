"""`python -m ka` — run the Knowledge Console backend, or small CLI tasks.

    python -m ka serve            start on KA_BACKEND_HOST (default 0.0.0.0; comma list allowed) : KA_BACKEND_PORT (default 8011)
    python -m ka demo [DIR]       seed a storage dir with the §47 example and print the lineage
    python -m ka env              list the declared settings and whether each is set
    python -m ka seed-demo copper-kettle [DIR]
                                  seed SYNTHETIC governed demo knowledge (idempotent) into DIR (default KA_STORAGE_ROOT);
                                  exits 3 without writing if another process holds DIR/.writer.lock
    python -m ka writer-lock-status [--storage DIR]
                                  show who holds the store's writer lock (SCRIPT #025)
    python -m ka break-writer-lock --owner-id ID [--storage DIR]
                                  BREAK-GLASS: remove the writer lock iff its owner_id is ID; first confirm that writer is gone
"""
from __future__ import annotations

import os
import sys


# [block plan-35]
def bind_hosts(raw: str | None) -> list[str]:
    """`KA_BACKEND_HOST` as a list: "10.77.0.2,127.0.0.1" → both; empty → 0.0.0.0 (the previous behaviour)."""
    hosts = [h.strip() for h in (raw or "").split(",") if h.strip()]
    return list(dict.fromkeys(hosts)) or ["0.0.0.0"]


def _listen(host: str, port: int):
    import socket
    fam = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(2048)
    s.set_inheritable(True)
    return s
# [/block plan-35]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "serve"
    if cmd == "serve":
        import atexit

        import uvicorn

        from ka import config, writer_lock
        # SCRIPT #025: register the store's writer lease in STANDBY before the app can open the store; the app's startup
        # handler acquires it in the background (KA_LOCK_WAIT_SECONDS), its shutdown handler releases it.
        if writer_lock.configure_service(config.storage_root()) is not None:
            atexit.register(writer_lock.stop_service)
        # [block plan-35] NEXOS v1: listen only where configured (e.g. the WireGuard address plus loopback), never implicitly public
        hosts = bind_hosts(config.get("KA_BACKEND_HOST"))
        port = int(config.get("KA_BACKEND_PORT"))
        if len(hosts) == 1:
            uvicorn.run("ka.api:app", host=hosts[0], port=port, log_level="info")
            return writer_lock.exit_code()
        server = uvicorn.Server(uvicorn.Config("ka.api:app", port=port, log_level="info"))
        server.run(sockets=[_listen(h, port) for h in hosts])
        # [/block plan-35]
        return writer_lock.exit_code()
    if cmd == "env":
        from ka import config
        for name, s in sorted(config.SETTINGS.items()):
            state = "set" if os.environ.get(name) else "default"
            print(f"{name:34} {state:8} {s.owner:18} {s.doc}")
        return 0
    if cmd == "demo":
        from pathlib import Path

        from ka import config, writer_lock
        from ka.demo import seed
        path = argv[1] if len(argv) > 1 else None
        try:
            root = Path(path) if path else config.storage_root()
            with writer_lock.one_shot(root, float(config.get("KA_SEED_LOCK_WAIT_SECONDS")), role="demo"):
                ka = seed(path)
                print(f"storage: {ka.repo.root}")
                for n in ka.repo.nuggets.all():
                    print(f"  {n.ref:12} {n.status.value:14} {n.scope.key():34} {n.statement}")
        except writer_lock.LockHeld as e:
            print(f"knowledge-acquisition demo: refused, {e}. Stop the writer (or wait for it) and re-run.", file=sys.stderr)
            return 3
        return 0
    # [block s025] SCRIPT #025 break-glass: remove a writer lock left by a dead writer (operator confirms it is gone first)
    if cmd in ("break-writer-lock", "writer-lock-status"):
        import argparse
        import json

        from ka import config, writer_lock
        ap = argparse.ArgumentParser(prog=f"knowledge-acquisition {cmd}")
        if cmd == "break-writer-lock":
            ap.add_argument("--owner-id", required=True, help="owner_id recorded in the lock (see writer-lock-status)")
        ap.add_argument("--storage", default=None, help="store root (default KA_STORAGE_ROOT)")
        ns = ap.parse_args(argv[1:])
        root = ns.storage or config.storage_root()
        if cmd == "writer-lock-status":
            cur = writer_lock.read_lock(root)
            print(json.dumps({"lock": str(writer_lock.lock_path(root)), "held": cur is not None, "holder": cur}, indent=2))
            return 0
        ok, msg = writer_lock.break_lock(root, ns.owner_id)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    # [/block s025]
    # [block plan-36] NEXOS Cloud Run MVP: synthetic demo knowledge through KA's own governed flow
    if cmd == "seed-demo":
        import json

        from ka.demo_copper_kettle import seed as seed_demo
        if len(argv) < 2:
            print("usage: knowledge-acquisition seed-demo copper-kettle [STORAGE_DIR]")
            return 2
        from ka import writer_lock
        try:
            print(json.dumps(seed_demo(argv[1], argv[2] if len(argv) > 2 else None), indent=2))
        except writer_lock.LockHeld as e:          # SCRIPT #025: the live service (or another job) is the writer — touch nothing
            print(f"knowledge-acquisition seed-demo: refused, {e}. The KA service must be stopped (scaled to zero / no live "
                  f"revision) before seeding; nothing was written.", file=sys.stderr)
            return 3
        return 0
    # [/block plan-36]
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
