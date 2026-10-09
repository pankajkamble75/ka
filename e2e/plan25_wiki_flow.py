"""plan-25 live flow (PT1 over real HTTP) — a KA server on temp storage; two policies are pasted and approved; the Wiki tab lists the
scope; the scope article renders every statement with a numbered citation; clicking a citation opens the nugget page; the evidence
sidebar shows the span; the index search finds the article; model prose (stub) is labelled synthesized.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan25_wiki_flow.py
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
KA = "http://127.0.0.1:8017"
API = KA + "/api/knowledge-acquisition"


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    store = Path(tempfile.mkdtemp(prefix="ka-wiki-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8017", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
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
        for text in ("Wiki refunds above $900 require manager approval.", "Wiki chargebacks must be answered within 30 days."):
            r = post("/sources/paste", {"text": text, "title": text[:20], "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
            for c in r["candidates"]:
                post(f"/nugget/{c['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
                refs.append(c["ref"])
        key = "scope:DOMAIN|merchant-acquiring"
        a = get(f"/wiki/pages/{urllib.request.quote(key, safe='')}")
        results.append(("the scope article carries every approved statement with its citation", set(a["refs"]) == set(refs) and all(f"[[{r}]]" in " ".join(b["text"] for b in a["blocks"]) for r in refs)))
        results.append(("reading stored nothing: never published, no page record", a["published"] is False and a["stored_page"] is False))
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + "/console/#/wiki"); pg.wait_for_timeout(1200)
            results.append(("tab 7 · Wiki is in the sidebar and tabs 1–6 are still there", all(pg.locator(f'#nav a:has-text("{t}")').count() == 1 for t in ("1 · Add knowledge", "2 · Knowledge nuggets", "3 · Browse by scope", "4 · Processes", "5 · Dashboard", "6 · Images", "7 · Wiki"))))
            results.append(("the index lists the scope under By scope", "Merchant Acquiring" in pg.inner_text("#main")))
            pg.fill("#wk-q", "chargebacks"); pg.click('button[data-act="wk-search"]'); pg.wait_for_timeout(1200)
            results.append(("search finds the article", "Results for" in pg.inner_text("#main") and "Merchant Acquiring" in pg.inner_text("#main")))
            pg.goto(KA + f"/console/#/wiki/{urllib.request.quote(key, safe='')}"); pg.wait_for_timeout(1500)
            txt = pg.inner_text("#main")
            results.append(("the article renders with numbered citations and the evidence sidebar", "[1]" in txt and "[2]" in txt and "Evidence" in txt and "s1 [" in txt))
            pg.screenshot(path=str(SHOTS / "plan25-wiki-article.png"), full_page=True)
            pg.click("sup.cite a >> nth=0"); pg.wait_for_timeout(1200)
            results.append(("a citation opens the nugget page", location_ok := pg.evaluate("location.hash").startswith("#/nugget/")))
            pg.goto(KA + f"/console/#/wiki/{urllib.request.quote(key, safe='')}?prose=llm"); pg.wait_for_timeout(1500)
            txt = pg.inner_text("#main")
            results.append(("model prose with the stub: labelled, or honestly noted as producing no cited sentence", "synthesized" in txt or "synthesis produced no cited sentence" in txt))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
