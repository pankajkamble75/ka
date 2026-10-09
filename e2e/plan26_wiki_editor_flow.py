"""plan-26 live flow (PT9 and PT3's "unchanged" half over real HTTP) — open a scope article, Edit, change a paragraph, Save (rev 0 → 1),
Preview, Diff (one update), Submit; the article is unchanged; a second tab's stale save is refused with 409.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan26_wiki_editor_flow.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
KA = "http://127.0.0.1:8018"
API = KA + "/api/knowledge-acquisition"


def post(path, body, method="POST"):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method=method)
    return json.load(urllib.request.urlopen(req))


def get(path):
    return json.load(urllib.request.urlopen(API + path))


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    store = Path(tempfile.mkdtemp(prefix="ka-wiki-edit-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8018", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
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
        for text in ("Editor refunds above $900 require manager approval.", "Editor chargebacks must be answered within 30 days."):
            r = post("/sources/paste", {"text": text, "title": text[:20], "owner": "flow", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
            for c in r["candidates"]:
                post(f"/nugget/{c['ref']}/decide", {"outcome": "APPROVE", "by": "flow", "reason": "ok"})
        key = "scope:DOMAIN|merchant-acquiring"
        qkey = urllib.request.quote(key, safe="")
        art0 = get(f"/wiki/pages/{qkey}")["blocks"]
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(KA + f"/console/#/wiki/{qkey}"); pg.wait_for_timeout(1200)
            pg.click('button[data-act="wk-edit"]'); pg.wait_for_timeout(1500)
            results.append(("Edit opens the editor with the article's Markdown and block ids", pg.locator("#wk-md").count() == 1 and "<!-- b" in pg.input_value("#wk-md")))
            md = pg.input_value("#wk-md").replace("$900", "$950")
            pg.fill("#wk-md", md); pg.click('button[data-act="wk-save"]'); pg.wait_for_timeout(1500)
            results.append(("Save moves the draft to rev 1", "rev 1" in pg.inner_text("#main")))
            pg.click('button[data-act="wk-preview"]'); pg.wait_for_timeout(800)
            results.append(("Preview shows the edited paragraph with its citation", "$950" in pg.inner_text("#wk-out") and pg.locator("#wk-out sup.cite").count() >= 1))
            pg.click('button[data-act="wk-diff"]'); pg.wait_for_timeout(800)
            results.append(("Diff shows exactly one update", pg.locator("#wk-out table tr").count() == 2 and "update" in pg.inner_text("#wk-out")))
            pg.screenshot(path=str(SHOTS / "plan26-editor-diff.png"), full_page=True)
            did = pg.evaluate("location.hash").split("draft=")[1]
            try:
                post(f"/wiki/drafts/{did}", {"text": md, "expected_rev": 0, "by": "other"}, method="PUT"); stale_ok = False
            except urllib.error.HTTPError as e:
                stale_ok = e.code == 409 and json.loads(e.read())["detail"]["rev"] == 1
            results.append(("a stale save from elsewhere is refused with 409 and the current rev", stale_ok))
            pg.click('button[data-act="wk-submit"]'); pg.wait_for_timeout(1500)
            results.append(("Submit moves the draft to SUBMITTED", "SUBMITTED" in pg.inner_text("#main")))
            results.append(("the article itself is unchanged", get(f"/wiki/pages/{qkey}")["blocks"] == art0))
            pg.goto(KA + f"/console/#/wiki/{qkey}"); pg.wait_for_timeout(1200)
            results.append(("the article page lists the submitted draft", "Drafts on this page" in pg.inner_text("#main") and "SUBMITTED" in pg.inner_text("#main")))
            br.close()
            results.append(("no JavaScript errors", not errs))
    finally:
        proc.terminate()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
