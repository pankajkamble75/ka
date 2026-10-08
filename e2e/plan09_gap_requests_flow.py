"""plan-09 live flow — the runtime raises a gap (with principal, intent, missing semantics, correlation id) twice; the second is
deduplicated; the Dashboard's needs-attention table shows it with principal · intent and status; Cancel moves it to CANCELLED;
`GET /events?after=` resumes exactly from the sequence the first page returned.

    cd /root/enterprise-os-070626 && .venv/bin/python /root/ka/e2e/plan09_gap_requests_flow.py
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
    tag = f"flow-{int(time.time())}"
    before = get("/events?tail=1&limit=1")["next_after"]
    body = {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "question": f"Who approves chargebacks ({tag})?", "gap_description": "no actor on chargeback",
            "principal": "eos:console", "intent": "grow_existing", "missing_semantics": ["actor", "decision"], "correlation_id": tag}
    a = post("/runtime/graph-gap", body)
    b = post("/runtime/graph-gap", body)
    results = [("gap recorded with the signal", a["signal"] == "GRAPH GAP DETECTED" and a["deduplicated"] is False),
               ("the same gap again is deduplicated to the same request", b["request_id"] == a["request_id"] and b["deduplicated"] is True)]
    page = get(f"/events?after={before}")
    results.append(("events after the recorded seq include exactly one new gap event for this request",
                    sum(1 for e in page["events"] if e["name"] == "graph.gap.detected" and e.get("request_id") == a["request_id"]) == 1
                    and all(e["seq"] > before for e in page["events"]) and page["version"] == "ka-events/1"))
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: d.accept("flow: not needed"))
        pg.goto("http://localhost:8011/console/#/dashboard"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#main")
        results.append(("dashboard shows the gap with principal, intent and status", tag in txt and "eos:console" in txt and "grow_existing" in txt and "OPEN" in txt and "raised 2×" in txt))
        pg.screenshot(path=str(SHOTS / "plan09-gap-open.png"))
        pg.click(f'button[data-act="cancel-gap"][data-id="{a["request_id"]}"]'); pg.wait_for_timeout(1500)
        r = get(f"/runtime/requests/{a['request_id']}")["request"]
        results.append(("Cancel moves the request to CANCELLED with the reason", r["status"] == "CANCELLED" and "not needed" in (r["cancelled_reason"] or "")))
        txt = pg.inner_text("#main")
        results.append(("the cancelled request leaves the needs-attention table", tag not in txt))
        pg.screenshot(path=str(SHOTS / "plan09-gap-cancelled.png"))
        br.close()
        results.append(("no JavaScript errors", not errs))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
