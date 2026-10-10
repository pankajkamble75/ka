"""plan-21 live flow (PT7 over real HTTP) — a DP-backed KA server (2 s worker tick) ingests and approves a policy; the fake Data Platform
revokes the asset; within seconds the source shows revoked at the Data Platform and the Dashboard lists the re-review.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan21_inbound_flow.py
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
KA = "http://127.0.0.1:8014"
API = KA + "/api/knowledge-acquisition"


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    fake = FakeDataPlatform(token="flow-token")
    srv = fake.serve("127.0.0.1", 8097)
    store = Path(tempfile.mkdtemp(prefix="ka-inbound-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8014", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_STORAGE_BACKEND": "data_platform", "KA_DP_API": "ka-subset", "KA_DP_BASE_URL": "http://127.0.0.1:8097", "KA_DP_SERVICE_TOKEN": "flow-token", "KA_RESEARCH_INTERNET": "0",
           "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_DP_OUTBOX_INTERVAL": "2", "KA_DP_INBOUND_INTERVAL": "2"}
    proc = subprocess.Popen(["/root/ka/.venv/bin/python", "-m", "ka", "serve"], cwd="/root/ka", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(API + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.5)
        post("/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"})
        r = post("/sources/paste", {"text": "Store inbound refunds above $800 require manager approval.", "title": "inbound policy", "owner": "flow",
                                    "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
        sid = r["source"]["id"]
        for c in r["candidates"]:
            post(f"/nugget/{c['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
        b = get(f"/sources/{sid}")["bindings"][0]
        results.append(("the source is available on the DP backend with an approved nugget", b["status"] == "available" and bool(r["candidates"])))
        fake.revoke(b["dp_asset_id"])
        deadline = time.time() + 30
        status = "available"
        while time.time() < deadline and status != "revoked":
            time.sleep(2)
            status = get(f"/sources/{sid}")["bindings"][0]["status"]
        results.append(("the worker picked up the revocation by itself", status == "revoked"))
        src = get(f"/sources/{sid}")["source"]
        results.append(("the source is marked revoked", bool(src["revoked_at"])))
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + f"/console/#/source/{sid}"); pg.wait_for_timeout(1200)
            txt = pg.inner_text("#main")
            results.append(("the source page shows revoked at source and the binding reason", "revoked at source" in txt and "access revoked at the Data Platform" in txt))
            pg.screenshot(path=str(SHOTS / "plan21-revoked.png"))
            pg.goto(KA + "/console/#/dashboard"); pg.wait_for_timeout(1200)
            txt = pg.inner_text("#main")
            results.append(("the Dashboard lists the re-review and the inbound cursor", "Re-reviews from revoked sources" in txt and "inbound events: cursor" in txt))
            pg.screenshot(path=str(SHOTS / "plan21-dashboard.png"))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate(); srv.shutdown()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
