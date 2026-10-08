"""plan-05 live flow — a process assertion is approved in the console; the graph-change page shows the ops and the publication record.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan05_publication_flow.py
"""
from __future__ import annotations

import json
import sys
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
    r = post("/sources/note", {"text": "Merchant underwriting decomposes into: Analyze merchant risk", "owner": "ops", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring",
                               "assertion": {"subject_kind": "process", "subject_name": "Merchant underwriting", "predicate": "decomposes_into", "object_kind": "process", "object_name": "Analyze merchant risk"}})
    ref = r["candidates"][0]["ref"]
    a = post(f"/nugget/{ref}/apply", {"by": "Pankaj Kamble", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"})
    results = [("apply publishes the process nugget", a["applied"] and bool(a["proposals"]))]
    pid = a["proposals"][0]["id"]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:8011/console/#/change/{pid}"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("graph-change page shows the publication record with ops", "Publication" in txt and "add_edge" in txt and "Content key" in txt))
        results.append(("ops name the canonical process id and the contains edge", "p.merchant_underwriting" in txt and "contains:p.merchant_underwriting->p.merchant_underwriting.analyze_merchant_risk" in txt))
        pg.screenshot(path=str(SHOTS / "plan05-change.png"))
        results.append(("no JavaScript errors", not errs))
        b.close()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
