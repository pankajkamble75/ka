"""`python -m ka` — run the Knowledge Console backend, or small CLI tasks.

    python -m ka serve            start on KA_BACKEND_PORT (default 8011)
    python -m ka demo [DIR]       seed a storage dir with the §47 example and print the lineage
    python -m ka env              list the declared settings and whether each is set
"""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "serve"
    if cmd == "serve":
        import uvicorn

        from ka import config
        uvicorn.run("ka.api:app", host="0.0.0.0", port=config.get("KA_BACKEND_PORT"), log_level="info")
        return 0
    if cmd == "env":
        from ka import config
        for name, s in sorted(config.SETTINGS.items()):
            state = "set" if os.environ.get(name) else "default"
            print(f"{name:34} {state:8} {s.owner:18} {s.doc}")
        return 0
    if cmd == "demo":
        from ka.demo import seed
        path = argv[1] if len(argv) > 1 else None
        ka = seed(path)
        print(f"storage: {ka.repo.root}")
        for n in ka.repo.nuggets.all():
            print(f"  {n.ref:12} {n.status.value:14} {n.scope.key():34} {n.statement}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
