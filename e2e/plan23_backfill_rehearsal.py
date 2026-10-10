"""plan-23 rehearsal (PT9 over real HTTP) — copy the LIVE `ka_storage/` to a temp dir (the live storage is never written), run the fake Data
Platform over HTTP, run `tools/backfill_physical.py --apply --publish-active` against the copy, report the measured counts, then start a
DP-backed KA server on the copy and check the Dashboard. Finally prove the rollback: the same copy served on the local backend.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan23_backfill_rehearsal.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, "/root/ka")
from playwright.sync_api import sync_playwright  # noqa: E402

from ka.data_platform.fake import FakeDataPlatform  # noqa: E402

SHOTS = Path(__file__).resolve().parent / "shots"
LIVE = Path("/root/ka/ka_storage")
PY = "/root/ka/.venv/bin/python"


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def wait(api):
    for _ in range(80):
        try:
            urllib.request.urlopen(api + "/healthz", timeout=1); return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    before = tree_digest(LIVE)
    copy = Path(tempfile.mkdtemp(prefix="ka-backfill-rehearsal-")) / "ka_storage"
    shutil.copytree(LIVE, copy, ignore=shutil.ignore_patterns("search_usage.json"))
    fake = FakeDataPlatform(token="flow-token")
    srv = fake.serve("127.0.0.1", 8095)
    env = {**os.environ, "KA_STORAGE_BACKEND": "data_platform", "KA_DP_API": "ka-subset", "KA_DP_BASE_URL": "http://127.0.0.1:8095", "KA_DP_SERVICE_TOKEN": "flow-token",
           "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open", "KA_RESEARCH_INTERNET": "0", "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "",
           "KA_DP_RETRIES": "3", "KA_DP_BACKOFF_BASE": "0", "KA_DP_OUTBOX_INTERVAL": "2"}
    results = []
    proc = None
    try:
        fix = json.loads(subprocess.run([PY, "tools/backfill_physical.py", "--storage", str(copy), "--repair-conflicts", "--apply"], capture_output=True, text=True, cwd="/root/ka", env=env).stdout)
        print("REPAIR", json.dumps({k: fix[k] for k in ("duplicate_keys", "renumbered")}))
        dry = json.loads(subprocess.run([PY, "tools/backfill_physical.py", "--storage", str(copy)], capture_output=True, text=True, cwd="/root/ka", env=env).stdout)
        run = subprocess.run([PY, "tools/backfill_physical.py", "--storage", str(copy), "--apply", "--publish-active"], capture_output=True, text=True, cwd="/root/ka", env=env)
        if not run.stdout.strip():
            print("TOOL FAILED\n" + run.stderr[-1500:])
            raise SystemExit(1)
        rep = json.loads(run.stdout)
        print("REPORT", json.dumps({k: rep[k] for k in ("versions", "skipped", "available", "failed", "sha_mismatch", "conflicts", "published", "outbox")}))
        for f in rep["failures"]:
            print("  failed:", f["source"], "v" + str(f["version"]), "—", f["reason"][:90])
        for c in rep["conflict_versions"]:
            print("  CONFLICT:", c["source"], "v" + str(c["version"]), c["source_version_id"], "—", c["reason"][:110])
        results.append(("dry run bound nothing and reported the work", dry["available"] == 0 and dry["would_bind"] == rep["available"] + rep["failed"] + rep["conflicts"]))
        results.append(("every version accounted for: available + failed + skipped + conflicts == versions", rep["available"] + rep["failed"] + rep["skipped"] + rep["conflicts"] == rep["versions"]))
        results.append(("plan-24 repair renumbered the duplicate on the copy; the backfill then reports 0 conflicts", fix["duplicate_keys"] >= 1 and rep["conflicts"] == 0))
        results.append(("no SHA mismatch", rep["sha_mismatch"] == 0))
        results.append(("every byte-less version failed with a reason", all(f["reason"] for f in rep["failures"])))
        results.append(("ACTIVE nuggets published and the outbox drained", rep["published"] > 0 and rep["outbox"].get("pending", 0) == 0 and rep["outbox"].get("dead", 0) == 0))
        results.append(("the fake holds one source_document per available version", sum(1 for a in fake.assets.values() if a["type"] == "source_document") == rep["available"]))
        proc = subprocess.Popen([PY, "-m", "ka", "serve"], cwd="/root/ka", env={**env, "KA_STORAGE_ROOT": str(copy), "KA_BACKEND_PORT": "8016"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        api = "http://127.0.0.1:8016/api/knowledge-acquisition"
        results.append(("DP-backed server starts on the backfilled copy", wait(api)))
        st = json.load(urllib.request.urlopen(api + "/physical/status"))
        results.append(("physical status: backend data_platform; only the conflict versions lack a binding", st["backend"] == "data_platform" and st["legacy_versions_without_binding"] == rep["conflicts"] and st["by_status"].get("available", 0) == rep["available"] + rep["skipped"]))
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 900}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://127.0.0.1:8016/console/#/dashboard"); pg.wait_for_timeout(1500)
            txt = pg.inner_text("#main")
            results.append(("the Dashboard shows the DP backend and the binding count", "data_platform" in txt and f"{st['bindings']} binding" in txt))
            pg.screenshot(path=str(SHOTS / "plan23-rehearsal-dashboard.png"))
            br.close()
            results.append(("no JavaScript errors", not errs))
        proc.terminate(); proc.wait(timeout=10); proc = None
        # rollback: the same copy on the local backend
        proc = subprocess.Popen([PY, "-m", "ka", "serve"], cwd="/root/ka", env={**env, "KA_STORAGE_BACKEND": "local", "KA_STORAGE_ROOT": str(copy), "KA_BACKEND_PORT": "8016"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        results.append(("rollback: the same copy serves on the local backend", wait(api) and json.load(urllib.request.urlopen(api + "/physical/status"))["backend"] == "local"))
        srcs = json.load(urllib.request.urlopen(api + "/sources"))["sources"]
        results.append(("… and lists every source", len(srcs) == len(list((copy / "sources").glob("*.json")))))
    finally:
        if proc is not None:
            proc.terminate()
        srv.shutdown()
    results.append(("the live ka_storage/ is byte-identical before and after", tree_digest(LIVE) == before))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
