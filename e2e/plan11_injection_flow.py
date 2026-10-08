"""plan-11 live flow — paste an SOP with authority "Internet Research": its process assertion binds `proposed` and the nugget page
shows "heuristic-only source · binds on approval"; approving the nugget re-binds it `bound`.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan11_injection_flow.py
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


def post(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body or {}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    tag = f"flow{int(time.time())}"
    sop = f"# Web onboarding {tag}\n\nWeb onboarding {tag} is performed by the Web team.\n\n1. Collect the form\n2. Verify the owner\n"
    r = post("/sources/paste", {"text": sop, "title": f"web sop {tag}", "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Internet Research", "markdown": True})
    cands = [c for c in r["candidates"] if c.get("predicate") in ("decomposes_into", "performed_by")]
    results = [("the pasted page produced process assertions", bool(cands))]
    ref = cands[0]["ref"]
    d = get(f"/nugget/{ref}")
    b = d.get("binding") or {}
    results.append(("the assertion binds proposed with the heuristic-only reason", b.get("binding_status") == "proposed" and any(x.startswith("heuristic-only source") for x in b.get("reasons", []))))
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:8011/console/#/nugget/{ref}"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("the nugget page shows the heuristic-only pill", "heuristic-only source" in txt and "proposed" in txt.lower()))
        pg.screenshot(path=str(SHOTS / "plan11-heuristic-only.png"))
        br.close()
        results.append(("no JavaScript errors", not errs))
    post(f"/nugget/{ref}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "checked"})
    b2 = get(f"/nugget/{ref}").get("binding") or {}
    results.append(("approval re-binds it bound", b2.get("binding_status") == "bound" and b2.get("method") == "approved"))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
