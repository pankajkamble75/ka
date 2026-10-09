"""plan-27 live flow (PT3, PT6, PT7 over real HTTP) — edit a scope article changing one claim in a two-citation paragraph; Reconcile shows
LINK_EXISTING + PROPOSE_REVISION; add a retirement request; Submit shows the produced revision and the retirement request; the nugget
page shows the pending revision; REJECT of the retirement request retires the prior on the console.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan27_reconcile_flow.py
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
KA = "http://127.0.0.1:8019"
API = KA + "/api/knowledge-acquisition"


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    store = Path(tempfile.mkdtemp(prefix="ka-wiki-rec-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8019", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
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
        refs = []
        for text in ("Reconcile refunds above $900 require manager approval.", "Reconcile chargebacks must be answered within 30 days."):
            r = post("/sources/paste", {"text": text, "title": text[:22], "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
            for c in r["candidates"]:
                post(f"/nugget/{c['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"}); refs.append(c["ref"])
        key = "scope:DOMAIN|merchant-acquiring"; qkey = urllib.request.quote(key, safe="")
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1100}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + f"/console/#/wiki/{qkey}/edit"); pg.wait_for_timeout(1800)
            md = pg.input_value("#wk-md").replace("within 30 days", "within 45 days")
            pg.fill("#wk-md", md); pg.click('button[data-act="wk-save"]'); pg.wait_for_timeout(1200)
            pg.click('button[data-act="wk-reconcile"]'); pg.wait_for_timeout(1000)
            txt = pg.inner_text("#wk-out")
            results.append(("Reconcile preview classifies the paragraph: one LINK_EXISTING, one PROPOSE_REVISION", "LINK_EXISTING" in txt and "PROPOSE_REVISION" in txt and "ADD_CANDIDATE" not in txt))
            pg.select_option("#wk-ret-ref", refs[0]); pg.fill("#wk-ret-why", "policy withdrawn"); pg.click('button[data-act="wk-request"]'); pg.wait_for_timeout(1200)
            results.append(("a retirement request is added to the draft", "Requested:" in pg.inner_text("#main") and refs[0] in pg.inner_text("#main")))
            pg.screenshot(path=str(SHOTS / "plan27-reconcile.png"), full_page=True)
            pg.click('button[data-act="wk-submit"]'); pg.wait_for_timeout(2000)
            txt = pg.inner_text("#main")
            results.append(("Submit shows the proposal with the produced revision and the retirement request", "Submitted" in txt and "retirement requested" in txt and "PROPOSE_REVISION" in txt))
            did = pg.evaluate("location.hash").split("draft=")[1]
            d = get(f"/wiki/drafts/{did}")["draft"]
            prop = get(f"/wiki/proposals/{d['proposal_id']}")
            produced = {x["canonical_id"]: x for x in prop["produced"]}
            results.append(("two produced versions: a revision of the chargeback nugget and the retirement revision", len(prop["produced"]) == 2 and any(x["retirement_requested"] for x in prop["produced"])))
            results.append(("ACTIVE nuggets and the article are unchanged until a decision", all(get(f"/nugget/{r}")["nugget"]["status"] == "ACTIVE" for r in refs) and all(f"[[{r}]]" in " ".join(b["text"] for b in get(f"/wiki/pages/{qkey}")["blocks"]) for r in refs)))
            ret = next(x for x in prop["produced"] if x["retirement_requested"])
            pg.goto(KA + f"/console/#/nugget/{urllib.request.quote(ret['ref'], safe='')}"); pg.wait_for_timeout(1500)
            results.append(("the retirement revision is pending on the nugget page", "PENDING_REVIEW" in pg.inner_text("#main") or "CONFLICT" in pg.inner_text("#main")))
            post(f"/nugget/{ret['ref']}/decide", {"outcome": "REJECT", "by": "reviewer", "reason": "agreed, retire"})
            prior = get(f"/nugget/{refs[0]}")["nugget"]
            results.append(("REJECT of the request retires the prior (OBSOLETE) and it leaves the article", prior["status"] == "OBSOLETE" and f"[[{refs[0]}]]" not in " ".join(b["text"] for b in get(f"/wiki/pages/{qkey}")["blocks"])))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
