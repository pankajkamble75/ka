"""plan-14 live flow — the fail-closed path a user can reach without the app registration (Q13): the connectors route lists
`m365` as a kind, the Add-knowledge page shows the Microsoft 365 card, and creating a connection whose secret variable is unset
is refused with the reason. The real library sync is product test PT6 and is NOT RUN until the author registers the app.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan14_m365_flow.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://localhost:8011/api/knowledge-acquisition"
SHOTS = Path(__file__).resolve().parent / "shots"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    kinds = json.load(urllib.request.urlopen(API + "/connectors"))["kinds"]
    results = [("the connectors route lists m365", "m365" in kinds)]
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1200}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/add"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("the Add page shows the Microsoft 365 card", "Connect Microsoft 365 / SharePoint" in txt))
        pg.fill("#ms-name", "Finance SharePoint"); pg.fill("#ms-tenant", "TENANT"); pg.fill("#ms-client", "CLIENT"); pg.fill("#ms-drive", "DRIVE"); pg.fill("#ms-secret", "KA_FLOW_UNSET_SECRET")
        pg.select_option("#ms-scope", "DOMAIN|merchant-acquiring")
        pg.click('button[data-act="connect-m365"]'); pg.wait_for_timeout(1500)
        res = pg.inner_text("#ms-result")
        results.append(("creating without the secret variable is refused with the reason", "Not connected" in res and "KA_FLOW_UNSET_SECRET" in res))
        pg.screenshot(path=str(SHOTS / "plan14-m365-card.png"), full_page=True)
        br.close()
        results.append(("no JavaScript errors", not errs))
    try:
        req = urllib.request.Request(API + "/connectors", data=json.dumps({"kind": "m365", "name": "x", "config": {"tenant_id": "T", "client_id": "C", "drive_id": "D"}, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "secret_ref": "KA_FLOW_UNSET_SECRET"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req); results.append(("the API refuses too", False))
    except urllib.error.HTTPError as e:
        results.append(("the API refuses too (400)", e.code == 400))
    conns = json.load(urllib.request.urlopen(API + "/connectors"))["connections"]
    results.append(("nothing was stored", not any(c["kind"] == "m365" for c in conns)))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
