"""plan-20 live flow (PT6 over real HTTP) — the fake Data Platform fails the first two calls; a paste through the console lands as a
`pending` version; the outbox worker (2 s interval) retries and the version becomes `available` by itself; the Dashboard shows the
outbox counts going to zero pending.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan20_outbox_flow.py
"""
from __future__ import annotations

import json
import os
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
KA = "http://127.0.0.1:8013"
API = KA + "/api/knowledge-acquisition"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    fake = FakeDataPlatform(token="flow-token")
    srv = fake.serve("127.0.0.1", 8098)
    store = Path(tempfile.mkdtemp(prefix="ka-outbox-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8013", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_STORAGE_BACKEND": "data_platform", "KA_DP_BASE_URL": "http://127.0.0.1:8098", "KA_DP_SERVICE_TOKEN": "flow-token", "KA_RESEARCH_INTERNET": "0",
           "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_DP_OUTBOX_INTERVAL": "2", "KA_DP_BACKOFF_BASE": "1"}
    proc = subprocess.Popen(["/root/ka/.venv/bin/python", "-m", "ka", "serve"], cwd="/root/ka", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(API + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.5)
        req = urllib.request.Request(API + "/scopes", data=json.dumps({"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req)
        st = json.load(urllib.request.urlopen(API + "/physical/status"))
        results.append(("DP-backed server with the outbox worker running", st["backend"] == "data_platform" and st["worker_running"]))
        fake.fail_next(2)
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + "/console/#/add"); pg.wait_for_timeout(1200)
            pg.fill("#pa-title", "Outbox flow policy"); pg.fill("#pa-text", "Store outbox refunds above $750 require manager approval.")
            pg.select_option("#pa-scope", "DOMAIN|merchant-acquiring")
            pg.click('button[data-act="paste"]'); pg.wait_for_timeout(1500)
            sid = json.load(urllib.request.urlopen(API + "/sources"))["sources"][0]["id"]
            d = json.load(urllib.request.urlopen(API + f"/sources/{sid}"))
            results.append(("the version is pending while DP is down", d["bindings"][0]["status"] == "pending"))
            pg.goto(KA + f"/console/#/source/{sid}"); pg.wait_for_timeout(1000)
            results.append(("the version card shows bytes · data_platform · pending", "bytes · data_platform · pending" in pg.inner_text("#main")))
            pg.screenshot(path=str(SHOTS / "plan20-pending.png"))
            deadline = time.time() + 40
            status = "pending"
            while time.time() < deadline and status == "pending":
                time.sleep(2)
                status = json.load(urllib.request.urlopen(API + f"/sources/{sid}"))["bindings"][0]["status"]
            results.append(("the worker made it available by itself", status == "available"))
            pg.goto(KA + f"/console/#/source/{sid}"); pg.reload(); pg.wait_for_timeout(1200)      # same hash: a reload is what re-renders
            results.append(("the version card now says available", "bytes · data_platform · available" in pg.inner_text("#main")))
            pg.goto(KA + "/console/#/dashboard"); pg.wait_for_timeout(1200)
            txt = pg.inner_text("#main")
            results.append(("the Dashboard shows the outbox with 0 pending and 1 done", "outbox 0 pending" in txt and "1 done" in txt))
            pg.screenshot(path=str(SHOTS / "plan20-dashboard.png"))
            br.close()
            results.append(("no JavaScript errors", not errs))
        results.append(("exactly one asset version in the fake", sum(len(a["versions"]) for a in fake.assets.values()) == 1))
    finally:
        proc.terminate(); srv.shutdown()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
