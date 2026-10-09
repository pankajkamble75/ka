"""plan-22 live flow (PT4 over real HTTP) — a DP-backed KA server (2 s worker tick) pastes and approves a policy; the fake Data Platform
holds a `nugget_version` derived asset whose payload names the source asset version and the evidence span; the nugget page shows the
physical copies; "view bytes" serves the pasted text through DP.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan22_derived_flow.py
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
KA = "http://127.0.0.1:8015"
API = KA + "/api/knowledge-acquisition"


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    fake = FakeDataPlatform(token="flow-token")
    srv = fake.serve("127.0.0.1", 8096)
    store = Path(tempfile.mkdtemp(prefix="ka-derived-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8015", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_STORAGE_BACKEND": "data_platform", "KA_DP_BASE_URL": "http://127.0.0.1:8096", "KA_DP_SERVICE_TOKEN": "flow-token", "KA_RESEARCH_INTERNET": "0",
           "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_DP_OUTBOX_INTERVAL": "2"}
    proc = subprocess.Popen(["/root/ka/.venv/bin/python", "-m", "ka", "serve"], cwd="/root/ka", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(API + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.5)
        post("/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"})
        text = "Store derived refunds above $900 require manager approval."
        r = post("/sources/paste", {"text": text, "title": "derived policy", "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring",
                                    "authority": "Approved Enterprise Policy"})
        sid, ref = r["source"]["id"], r["candidates"][0]["ref"]
        post(f"/nugget/{ref}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
        deadline = time.time() + 30
        derived = []
        while time.time() < deadline:
            derived = get(f"/nugget/{ref}/derived")["derived"]
            if len([a for a in derived if a["state"] == "available"]) >= 2:
                break
            time.sleep(2)
        results.append(("CANDIDATE and ACTIVE artefacts delivered by the worker", {a["status"] for a in derived if a["state"] == "available"} >= {"CANDIDATE", "ACTIVE"}))
        b = get(f"/sources/{sid}")["bindings"][0]
        active = [a for a in derived if a["status"] == "ACTIVE"][0]
        asset = fake.assets.get(active["dp_asset_id"])
        payload = json.loads(asset["versions"][active["dp_asset_version_id"]]["bytes"]) if asset else {}
        results.append(("the DP payload names the source asset version", payload.get("sources", [{}])[0].get("dp_asset_version_id") == b["dp_asset_version_id"]))
        ev = (payload.get("evidence") or [{}])[0]
        results.append(("… the evidence span and the governance decision id", bool(ev.get("span_id")) and ev.get("start") is not None and bool(payload.get("governance_decision_id"))))
        results.append(("the derived asset's parent is the source asset", asset is not None and asset["parent"][0] == b["dp_asset_id"]))
        body = urllib.request.urlopen(API + f"/sources/{sid}/versions/1/content").read().decode()
        results.append(("view bytes serves the pasted text through DP", body == text))
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1100}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + f"/console/#/nugget/{ref}"); pg.wait_for_timeout(1500)
            txt = pg.inner_text("#main")
            results.append(("the nugget page shows the physical copies with asset ids", "Physical copies" in txt and active["dp_asset_id"] in txt and "data_platform" in txt))
            pg.screenshot(path=str(SHOTS / "plan22-derived.png"), full_page=True)
            pg.goto(KA + f"/console/#/source/{sid}"); pg.wait_for_timeout(1200)
            results.append(("the version card carries the view-bytes link", pg.locator('a:has-text("view bytes")').count() == 1))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate(); srv.shutdown()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
