"""plan-03 live flow — a note stated as an assertion becomes a bound candidate; the nugget page shows the assertion card.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan03_binding_flow.py
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
    r = post("/sources/note", {"text": "Merchant underwriting is a decision process.", "owner": "ops", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring",
                               "assertion": {"subject_kind": "process", "subject_name": "Merchant underwriting", "predicate": "typed_as", "object_value": "decision"}})
    ref = r["candidates"][0]["ref"]
    results = [("note with assertion yields one candidate", len(r["candidates"]) == 1)]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:8011/console/#/nugget/{ref.replace(':', '%3A')}"); pg.wait_for_timeout(1200)
        text = pg.inner_text("#main")
        results.append(("assertion card shows subject, predicate and type", "Process assertion" in text and "typed_as" in text and "process_type" in text))
        results.append(("binding pill says bound", pg.locator(".card h3 .pill.bound").count() == 1))
        pg.screenshot(path=str(SHOTS / "plan03-assertion.png"))
        pg.goto("http://localhost:8011/console/#/nuggets"); pg.wait_for_timeout(1000)
        results.append(("subject column on the nuggets tab", "merchant_underwriting" in pg.inner_text("#main")))
        pg.goto("http://localhost:8011/console/#/dashboard"); pg.wait_for_timeout(1000)
        results.append(("dashboard shows the loaded grammar", "EOS grammar" in pg.inner_text("#main")))
        pg.screenshot(path=str(SHOTS / "plan03-dashboard.png"))
        results.append(("no JavaScript errors", not errs))
        b.close()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
