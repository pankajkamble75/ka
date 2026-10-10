"""plan-19 live flow (PT1 over real HTTP) — the wire-level fake Data Platform runs on 127.0.0.1:8099, a second KA server runs on 8012 with
KA_STORAGE_BACKEND=data_platform pointing at it, and the console pastes a source: the version card says `bytes · data_platform ·
available`, the bytes are in the fake, and nothing is written under the temporary storage's blobs/.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan19_dp_flow.py
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
KA = "http://127.0.0.1:8012"
API = KA + "/api/knowledge-acquisition"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    fake = FakeDataPlatform(token="flow-token")
    srv = fake.serve("127.0.0.1", 8099)
    store = Path(tempfile.mkdtemp(prefix="ka-dp-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8012", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_STORAGE_BACKEND": "data_platform", "KA_DP_API": "ka-subset", "KA_DP_BASE_URL": "http://127.0.0.1:8099", "KA_DP_SERVICE_TOKEN": "flow-token", "KA_RESEARCH_INTERNET": "0",
           "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": ""}
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
        results.append(("the second server runs the data_platform backend", st["backend"] == "data_platform" and not st["note"]))
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + "/console/#/add"); pg.wait_for_timeout(1200)
            pg.fill("#pa-title", "DP flow policy"); pg.fill("#pa-text", "Store DP refunds above $650 require manager approval.")
            pg.select_option("#pa-scope", "DOMAIN|merchant-acquiring")
            pg.click('button[data-act="paste"]'); pg.wait_for_timeout(2000)
            srcs = json.load(urllib.request.urlopen(API + "/sources"))["sources"]
            results.append(("the paste landed as a source", bool(srcs)))
            sid = srcs[0]["id"]
            d = json.load(urllib.request.urlopen(API + f"/sources/{sid}"))
            b = d["bindings"][0] if d["bindings"] else {}
            results.append(("the binding is available on the data_platform backend with DP ids", b.get("backend") == "data_platform" and b.get("status") == "available" and bool(b.get("dp_asset_id"))))
            results.append(("the bytes are in the fake Data Platform", b.get("dp_asset_id") in fake.assets))
            results.append(("nothing was written under the temporary blobs/", not (store / "blobs").exists() or not list((store / "blobs").glob("*"))))
            pg.goto(KA + f"/console/#/source/{sid}"); pg.wait_for_timeout(1200)
            txt = pg.inner_text("#main")
            results.append(("the version card says bytes · data_platform · available", "bytes · data_platform · available" in txt))
            pg.screenshot(path=str(SHOTS / "plan19-dp-binding.png"))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate(); srv.shutdown()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
