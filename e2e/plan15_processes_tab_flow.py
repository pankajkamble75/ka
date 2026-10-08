"""plan-15 live flow (PT7) — the Processes tab lists process subjects, opens a profile, the crumb returns to the tab, and
Browse by scope's Processes mode still renders.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan15_processes_tab_flow.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://localhost:8011/api/knowledge-acquisition"
SHOTS = Path(__file__).resolve().parent / "shots"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    procs = json.load(urllib.request.urlopen(API + "/processes"))["processes"]
    results = [("the server knows at least one process subject", bool(procs))]
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/processes"); pg.wait_for_timeout(1500)
        nav = pg.inner_text("#nav")
        results.append(("the nav shows six entries with Processes fourth", all(x in nav for x in ["1 · Add knowledge", "2 · Knowledge nuggets", "3 · Browse by scope", "4 · Processes", "5 · Dashboard", "6 · Images"])))
        txt = pg.inner_text("#main")
        results.append(("the Processes tab lists process subjects", "Processes" in txt and any(pr["name"] in txt or pr["key"] in txt for pr in procs)))
        pg.screenshot(path=str(SHOTS / "plan15-processes-tab.png"))
        link = pg.query_selector('#main a[href^="#/subject/"]')
        results.append(("a profile link exists", link is not None))
        if link:
            link.click(); pg.wait_for_timeout(1500)
            crumbs = pg.inner_text("#main .crumbs")
            results.append(("the profile crumb returns to the Processes tab", "Processes" in crumbs))
            results.append(("the Processes nav entry stays active on the profile page", "active" in (pg.get_attribute('#nav a[href="#/processes"]', "class") or "")))
            pg.screenshot(path=str(SHOTS / "plan15-profile.png"))
        pg.goto("http://localhost:8011/console/#/browse?mode=processes"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("Browse by scope's Processes mode still renders", "Processes" in txt))
        br.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
