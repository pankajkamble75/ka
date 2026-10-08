"""plan-12 live flow (reference adapter) — approve a domain assertion, approve and apply its graph change, and the graph-change
page lists the pinned instances with their state; a named Repin records the decision. The store half of PT4 is proved under the
Enterprise OS interpreter (`ka/tests/test_plan12_eos_repin.py`).

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan12_repin_flow.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
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
    sop = f"# Repin process {tag}\n\nRepin process {tag} is performed by the Repin team.\n\n1. Collect\n2. Decide\n"
    r = post("/sources/paste", {"text": sop, "title": f"repin sop {tag}", "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring",
                                "authority": "Approved Enterprise Policy", "markdown": True})
    cands = [c for c in r["candidates"] if c.get("predicate") in ("decomposes_into", "performed_by")]
    results = [("domain assertions extracted", bool(cands))]
    ref = cands[0]["ref"]
    post(f"/nugget/{ref}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
    props = [p for p in get("/graph-changes")["proposals"] if ref in p["knowledge_change_ids"]]
    results.append(("a graph change proposal exists", bool(props)))
    pid = props[0]["id"]
    if props[0]["status"] in ("READY", "PROPOSED"):
        post(f"/graph-changes/{pid}/approve", {"by": "Pankaj Kamble", "reason": "flow"})
        post(f"/graph-changes/{pid}/apply", {"by": "Pankaj Kamble"})
    st = get(f"/graph-changes/{pid}/repins")
    results.append(("repin status lists the pinned instances", len(st["repins"]) >= 1))
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1100}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:8011/console/#/change/{pid}"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("the change page shows the instances-pinned table", "Instances pinned to this domain" in txt and "merchant-a" in txt))
        pg.screenshot(path=str(SHOTS / "plan12-repins.png"), full_page=True)
        br.close()
        results.append(("no JavaScript errors", not errs))
    rr = post(f"/graph-changes/{pid}/repin", {"instance_id": st["repins"][0]["instance_id"], "by": "Pankaj Kamble"})
    results.append(("a named repin is accepted and reports its state", rr["result"]["applied"] is True and ("note" in rr["result"])))
    try:
        post(f"/graph-changes/{pid}/repin", {"instance_id": st["repins"][0]["instance_id"], "by": "ka.policy.auto"})
        results.append(("a policy id cannot repin", False))
    except urllib.error.HTTPError as e:
        results.append(("a policy id cannot repin", e.code == 409))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
