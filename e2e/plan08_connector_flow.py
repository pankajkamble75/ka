"""plan-08 live flow — connect a folder under the server's connector root, sync, change the policy in the file, sync again,
and the Knowledge nuggets Conflicts view lists the contradiction (PT8 through the console).

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan08_connector_flow.py
Prereq: the server runs with its default connector root (<storage>/inbox) and the shared ka_storage at /root/ka/ka_storage.
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
STORAGE = Path("/root/ka/ka_storage")


def post(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body or {}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    roots = json.load(urllib.request.urlopen(API + "/connectors"))["roots"]
    tag = f"flow-{int(time.time())}"
    folder = Path(roots[0]) / tag
    folder.mkdir(parents=True)
    policy = f"Store {tag} refunds above $500 require manager approval.\n"
    (folder / "refunds.md").write_text(policy)
    results = []
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/add"); pg.wait_for_timeout(900)
        pg.fill("#cn-name", f"Ops {tag}"); pg.fill("#cn-root", str(folder))
        pg.select_option("#cn-scope", "DOMAIN|merchant-acquiring"); pg.select_option("#cn-auth", "Approved Enterprise Policy")
        pg.click('button[data-act="connect"]'); pg.wait_for_timeout(2500)
        txt = pg.inner_text("#main")
        results.append(("connection listed with a first sync", f"Ops {tag}" in txt and "new 1" in txt))
        pg.screenshot(path=str(SHOTS / "plan08-connected.png"))
        conns = json.load(urllib.request.urlopen(API + "/connectors"))["connections"]
        conn = next(c for c in conns if c["name"] == f"Ops {tag}")
        got = json.load(urllib.request.urlopen(API + f"/connectors/{conn['id']}"))
        src = got["sources"][0]
        # approve the first version's candidate so the changed file contradicts ACTIVE knowledge
        sd = json.load(urllib.request.urlopen(API + f"/sources/{src['id']}"))
        for n in sd["nuggets"]:
            post(f"/nugget/{n['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "flow"})
        (folder / "refunds.md").write_text(policy.replace("$500", "$1,000"))
        pg.click(f'button[data-act="sync-conn"][data-id="{conn["id"]}"]'); pg.wait_for_timeout(2500)
        txt = pg.inner_text("#main")
        results.append(("second sync reports one modified file", "modified 1" in txt))
        sd2 = json.load(urllib.request.urlopen(API + f"/sources/{src['id']}"))
        results.append(("same source now at content version 2", sd2["source"]["content_version"] == 2 and len(sd2["versions"]) == 2))
        pg.goto("http://localhost:8011/console/#/nuggets?view=conflicts"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("Conflicts view lists the changed policy", "$1,000 require manager approval" in txt and tag in txt))
        pg.screenshot(path=str(SHOTS / "plan08-conflicts.png"))
        b.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
