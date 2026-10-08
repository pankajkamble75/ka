"""plan-04 live flow — upload the synthetic underwriting SOP through the API, see process candidates with subjects on the
Knowledge nuggets tab and the extraction report on the source page.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan04_process_extraction_flow.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://localhost:8011/api/knowledge-acquisition"
SHOTS = Path(__file__).resolve().parent / "shots"
FIXTURE = Path(__file__).resolve().parent.parent / "ka" / "tests" / "fixtures" / "underwriting_sop.md"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    boundary = "----kaflow"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"owner\"\r\n\r\nops\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"scope_type\"\r\n\r\nDOMAIN\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"scope_id\"\r\n\r\nmerchant-acquiring\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"authority\"\r\n\r\nOperating Procedure\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"underwriting_sop.md\"\r\nContent-Type: text/markdown\r\n\r\n").encode() + FIXTURE.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API + "/sources/upload", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    r = json.load(urllib.request.urlopen(req))
    sid = r["source"]["id"]
    results = [("upload yields seven process assertions", r["extraction_report"]["assertions"] == 7)]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://localhost:8011/console/#/nuggets"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("nuggets tab shows the process subject and decomposes_into rows", "merchant_underwriting" in txt and "decomposes_into" in txt))
        pg.screenshot(path=str(SHOTS / "plan04-nuggets.png"))
        pg.goto(f"http://localhost:8011/console/#/source/{sid}"); pg.wait_for_timeout(1200)
        txt = pg.inner_text("#main")
        results.append(("source page shows the extraction report with spans", "Extraction report" in txt and "Process assertions" in txt and "s1 [" in txt))
        pg.screenshot(path=str(SHOTS / "plan04-source.png"))
        results.append(("no JavaScript errors", not errs))
        b.close()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
