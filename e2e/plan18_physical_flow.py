"""plan-18 live flow — a pasted source's page shows where its bytes live (backend · status · sha) and the Dashboard shows the
physical store line with the legacy count.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan18_physical_flow.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://localhost:8011/api/knowledge-acquisition"
SHOTS = Path(__file__).resolve().parent / "shots"


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    tag = f"flow{int(time.time())}"
    r = post("/sources/paste", {"text": f"Store {tag} refunds above $700 require manager approval.", "title": f"physical {tag}", "owner": "flow",
                                "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy", "extract": False})
    sid = r["source"]["id"]
    st = json.load(urllib.request.urlopen(API + "/physical/status"))
    results = [("status route: local backend, bindings counted", st["backend"] == "local" and st["bindings"] >= 1)]
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:8011/console/#/source/{sid}"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("the version card shows bytes · local · available", "bytes · local · available" in txt))
        pg.screenshot(path=str(SHOTS / "plan18-source-binding.png"))
        pg.goto("http://localhost:8011/console/#/dashboard"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("the Dashboard shows the physical store line", "Physical store" in txt and "binding" in txt))
        pg.screenshot(path=str(SHOTS / "plan18-dashboard.png"))
        br.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
