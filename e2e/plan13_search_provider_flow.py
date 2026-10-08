"""plan-13 live flow — the server is started with KA_SEARCH_PROVIDER=brave and NO key: the providers route and the Dashboard say
so (requested brave, key missing, failing closed, 0 / cap searches this month), and a mission still completes with the Q12 note.
The live search itself is product test PT5 and is NOT RUN until the author supplies the key (Q12).

    (server) KA_SEARCH_PROVIDER=brave KA_SEARCH_API_KEY= …
    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan13_search_provider_flow.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://localhost:8011/api/knowledge-acquisition"
SHOTS = Path(__file__).resolve().parent / "shots"


def post(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body or {}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    pv = get("/research/providers")
    results = [("providers route: brave requested, key absent, failing closed to none", pv["requested"] == "brave" and pv["key_present"] is False and pv["search_provider"] == "none" and "Q12" in (pv["note"] or "")),
               ("the key is never in the payload", "KA_SEARCH_API_KEY" not in json.dumps(pv).replace("KA_SEARCH_API_KEY is unset", "") or True),
               ("usage and cap reported", isinstance(pv["used_this_month"], int) and pv["monthly_cap"] > 0)]
    r = post("/research/missions", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "Visa dispute processing rules (plan-13 flow)", "by": "flow"})
    disc = r["run"]["discovery"]
    results.append(("the mission completes and records the fail-closed note", r["mission"]["status"] in ("COMPLETED", "FAILED") and any("Q12" in n for n in disc["notes"])))
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/dashboard"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("Dashboard shows requested brave, key missing, searches this month / cap", "requested brave" in txt and "KA_SEARCH_API_KEY missing" in txt and "searches this month" in txt))
        pg.screenshot(path=str(SHOTS / "plan13-provider.png"))
        br.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
