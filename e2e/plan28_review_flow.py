"""plan-28 live flow (PT4, PT11 over real HTTP) — submit a change, open the review page from the article's drafts list, see both sides,
Approve the produced revision on the review page, Publish, see "published"; a second Publish says already published.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan28_review_flow.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
KA = "http://127.0.0.1:8020"
API = KA + "/api/knowledge-acquisition"


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    store = Path(tempfile.mkdtemp(prefix="ka-wiki-review-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8020", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_RESEARCH_INTERNET": "0", "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_STORAGE_BACKEND": "local"}
    proc = subprocess.Popen(["/root/ka/.venv/bin/python", "-m", "ka", "serve"], cwd="/root/ka", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(API + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.5)
        post("/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"})
        for text in ("Review refunds above $900 require manager approval.", "Review chargebacks must be answered within 30 days."):
            r = post("/sources/paste", {"text": text, "title": text[:20], "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
            for c in r["candidates"]:
                post(f"/nugget/{c['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
        key = "scope:DOMAIN|merchant-acquiring"; qkey = urllib.request.quote(key, safe="")
        d = post(f"/wiki/pages/{qkey}/drafts", {"by": "editor"})
        md = d["markdown"].replace("within 30 days", "within 60 days")
        req = urllib.request.Request(API + f"/wiki/drafts/{d['draft']['id']}", data=json.dumps({"text": md, "expected_rev": 0, "by": "editor"}).encode(), headers={"Content-Type": "application/json"}, method="PUT")
        urllib.request.urlopen(req)
        s = post(f"/wiki/drafts/{d['draft']['id']}/submit", {"by": "editor"})
        pid = s["proposal_id"]
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1100}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + f"/console/#/wiki/{qkey}"); pg.wait_for_timeout(1500)
            results.append(("the article lists the submitted draft with a Review link", pg.locator(f'a:has-text("Review {pid}")').count() == 1))
            pg.click(f'a:has-text("Review {pid}")'); pg.wait_for_timeout(1500)
            txt = pg.inner_text("#main")
            results.append(("the review page shows both sides and one awaiting decision", "Current article" in txt and "Draft" in txt and "awaiting decision" in txt and "60 days" in txt))
            pg.screenshot(path=str(SHOTS / "plan28-review.png"), full_page=True)
            btn = pg.locator('button[data-act="wk-decide"][data-outcome="ACCEPT_NEW"]')
            (btn if btn.count() else pg.locator('button[data-act="wk-decide"][data-outcome="APPROVE"]')).first.click(); pg.wait_for_timeout(1500)
            txt = pg.inner_text("#main")
            results.append(("the decision resolves the proposal", "resolved" in txt))
            pg.click('button[data-act="wk-publish"]'); pg.wait_for_timeout(1500)
            results.append(("Publish records the digest and the proposal is PUBLISHED", "PUBLISHED" in pg.inner_text("#main") and "page published" in pg.inner_text("#main")))
            art = get(f"/wiki/pages/{qkey}")
            results.append(("the article reflects the approved revision and is published, not stale", "60 days" in " ".join(b["text"] for b in art["blocks"]) and art["published"] and not art["stale"]))
            again = post(f"/wiki/pages/{qkey}/publish", {"by": "reviewer"})
            results.append(("a second publish says already published", again["published"] is False and again["reason"] == "already published"))
            graph = [g for x in get(f"/wiki/proposals/{pid}/review")["produced"] for g in x["graph_changes"]]
            results.append(("graph proposals raised by the approval are listed and NOT applied by publication (Q3)", bool(graph) and all(g["status"] != "APPLIED" for g in graph)))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
