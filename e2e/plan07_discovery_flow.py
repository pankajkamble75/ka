"""plan-07 live flow — with the fixture provider and the Internet gate OFF (no network), a mission's page shows the discovery
table: queries, selected results with publisher, and "gate off" skips. The fetch path is proved by the unit tests.

    KA_SEARCH_PROVIDER=fixture KA_SEARCH_FIXTURE=/root/ka/e2e/search_fixture_live.json  (server env; example.com hosts resolve, nothing is fetched)
    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan07_discovery_flow.py
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
    prov = json.load(urllib.request.urlopen(API + "/research/providers"))
    results = [("server runs the fixture provider", prov["search_provider"] == "fixture")]
    r = post("/research/missions", {"wait": True, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "Visa dispute processing rules",
                                    "questions": ["What is the dispute response window?"], "by": "ops"})
    mid = r["mission"]["mission_id"]
    disc = r["run"]["discovery"]
    results.append(("run recorded queries and selected results", len(disc["queries"]) == 2 and len(disc["selected"]) >= 1))
    results.append(("gate off: selections recorded as skipped, nothing fetched", disc["fetched"] == [] and any(x["reason"].startswith("gate off") for x in disc["skipped"])))
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:8011/console/#/mission/{mid}"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("mission page shows the discovery table", "Discovery" in txt and "Example Rules Co" in txt and "skipped" in txt))
        pg.screenshot(path=str(SHOTS / "plan07-discovery.png"))
        b.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
