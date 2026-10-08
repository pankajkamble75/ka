"""plan-02 live flow — run against a KA server on :8011 (loopback, so no token is needed for the API calls):
a PERSONAL note's candidate is applied to a domain WITHOUT the widen checkbox (refused, reason in the toast) and WITH it
(applied; the decision records the visibility change). Screenshots land in e2e/shots/.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan02_access_visibility_flow.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
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
    r = post("/sources/note", {"text": "Our store must close on Sundays for stocktake.", "title": "Alice note", "owner": "alice",
                               "scope_type": "INSTANCE", "scope_id": "merchant-b"})
    ref = r["candidates"][0]["ref"]
    results = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1360, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/nuggets")
        pg.wait_for_timeout(1000)
        sel = f"tr:has(a[href='#/nugget/{ref.replace(':', '%3A')}'])"
        pg.locator(sel).locator("select.apply-scope").select_option("DOMAIN|merchant-acquiring")
        pg.locator(sel).locator("button[data-act='apply']").click()
        pg.wait_for_timeout(1200)
        t1 = pg.inner_text("#toast")
        pg.screenshot(path=str(SHOTS / "plan02-refused.png"))
        results.append(("apply without widen is refused with PERSONAL → DOMAIN", "PERSONAL → DOMAIN" in t1))
        pg.locator(sel).locator("input.widen").check()
        pg.locator(sel).locator("button[data-act='apply']").click()
        pg.wait_for_timeout(1500)
        t2 = pg.inner_text("#toast")
        pg.screenshot(path=str(SHOTS / "plan02-applied.png"))
        results.append(("apply with widen is applied at the domain", t2.startswith("Applied") and "DOMAIN:merchant-acquiring" in t2))
        results.append(("no JavaScript errors", not errs))
        b.close()
    d = json.load(urllib.request.urlopen(API + "/nugget/" + urllib.parse.quote(ref)))
    results.append(("decision records visibility_change PERSONAL→DOMAIN",
                    any(g.get("visibility_change") == {"from": "PERSONAL", "to": "DOMAIN"} for g in d["governance"])))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
