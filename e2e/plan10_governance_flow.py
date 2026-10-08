"""plan-10 live flow — PT1: the same policy twice, approve the second → one ACTIVE version, history shows "duplicate of";
PT2: a connected file is deleted → Dashboard lists the re-review; Reject → the prior is OBSOLETE and a retirement proposal exists.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan10_governance_flow.py
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
    results = []
    # PT1 — paste twice, approve both
    text = f"Store {tag} refunds above $900 require manager approval."
    a = post("/sources/paste", {"text": text, "title": f"SOP {tag} v1", "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
    ref_a = a["candidates"][0]["ref"]
    post(f"/nugget/{ref_a}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "first"})
    b = post("/sources/paste", {"text": text, "title": f"SOP {tag} copy", "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
    ref_b = b["candidates"][0]["ref"]
    d = post(f"/nugget/{ref_b}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "second"})
    results.append(("approving the duplicate resolves as automatic Keep Existing", d["decision"]["outcome"] == "KEEP_EXISTING" and d["decision"]["automatic"]))
    n = get(f"/nugget/{ref_a}")["nugget"]
    results.append(("the existing nugget now names both documents", len(n["source_refs"]) == 2 and n["status"] == "ACTIVE"))
    # PT2 — connector file deleted
    roots = get("/connectors")["roots"]
    folder = Path(roots[0]) / tag
    folder.mkdir(parents=True)
    (folder / "sop.md").write_text(f"Store {tag} chargebacks must be answered within 25 days.\n")
    c = post("/connectors", {"kind": "local_folder", "name": f"Ops {tag}", "config": {"root": str(folder)}, "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
    cid = c["connection"]["id"]
    post(f"/connectors/{cid}/sync?by=flow")
    src = get(f"/connectors/{cid}")["sources"][0]
    cands = get(f"/sources/{src['id']}")["nuggets"]
    for x in cands:
        post(f"/nugget/{x['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
    # the server keeps auto-apply OFF (Q3): a named person approves and applies the knowledge's graph proposal so lineage exists
    refs = {x["ref"] for x in cands}
    for p in get("/graph-changes")["proposals"]:
        if set(p["knowledge_change_ids"]) & refs and p["status"] in {"READY", "PROPOSED"}:
            post(f"/graph-changes/{p['id']}/approve", {"by": "flow", "reason": "flow"})
            post(f"/graph-changes/{p['id']}/apply", {"by": "flow"})
    (folder / "sop.md").unlink()
    rep = post(f"/connectors/{cid}/sync?by=flow")["report"]
    results.append(("deleting the file produced re-review revisions", len(rep["reviews"]) == len(cands) and rep["deleted"] == 1))
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/nuggets?view=history"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("history shows the second copy closed as a duplicate of the first", f"duplicate of {ref_a}" in txt))
        pg.screenshot(path=str(SHOTS / "plan10-duplicate.png"))
        pg.goto("http://localhost:8011/console/#/dashboard"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("dashboard lists the re-review from the revoked source", "Re-reviews from revoked sources" in txt and tag in txt))
        pg.screenshot(path=str(SHOTS / "plan10-revoked-review.png"))
        pg.click(f'button[data-act="decide"][data-ref="{rep["reviews"][0]}"][data-outcome="REJECT"]'); pg.wait_for_timeout(1500)
        br.close()
        results.append(("no JavaScript errors", not errs))
    prior = get(f"/nugget/{cands[0]['ref']}")["nugget"]
    results.append(("rejecting the re-review retired the prior version", prior["status"] == "OBSOLETE"))
    props = get("/graph-changes")["proposals"]
    results.append(("a retirement proposal exists for it", any(p.get("impact_summary", {}).get("retirement") and cands[0]["ref"] in p["knowledge_change_ids"] for p in props)))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
