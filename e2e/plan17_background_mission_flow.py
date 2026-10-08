"""plan-17 live flow (PT10) — Start research in the console lands on the mission page within a second showing "Running"; the page
polls and ends COMPLETED with candidates without the client waiting on the request.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan17_background_mission_flow.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    results = []
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/add"); pg.wait_for_timeout(1200)
        pg.select_option("#rm-scope", "DOMAIN|merchant-acquiring")
        pg.fill("#rm-obj", "Visa dispute response time limits for merchants (plan-17 flow)")
        pg.fill("#rm-q", "How many days does a merchant have to respond to a Visa dispute?")
        t0 = time.time()
        pg.click('button[data-act="mission"]')
        pg.wait_for_url("**/#/mission/**", timeout=5000)
        landed = time.time() - t0
        pg.wait_for_timeout(800)
        txt = pg.inner_text("#main")
        results.append(("the console lands on the mission page within a second or two", landed < 3.0))
        results.append(("the page shows the run as Running with progress", "Running" in txt and "agent" in txt))
        pg.screenshot(path=str(SHOTS / "plan17-running.png"))
        deadline = time.time() + 900
        status = ""
        while time.time() < deadline:
            txt = pg.inner_text("#main")
            if "COMPLETED" in txt or "FAILED" in txt:
                status = "COMPLETED" if "COMPLETED" in txt else "FAILED"
                break
            pg.wait_for_timeout(3000)
        results.append(("the page ends COMPLETED by itself", status == "COMPLETED"))
        results.append(("candidates are listed", "Candidate nuggets" in txt and "Not run yet" not in txt))
        pg.screenshot(path=str(SHOTS / "plan17-completed.png"))
        br.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
