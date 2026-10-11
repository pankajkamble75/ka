# [block plan-34]
"""NEXOS v1: real screenshots of KA's six specialist screens, exactly the URLs `GET /v1/screens` hands AgentX, taken from the RUNNING
service. Reads the manifest live (AgentX token from .env), opens each `launch_url` in headless Chromium, waits for the console to render,
and saves `docs/user-notes/nexos-integration-v1/screenshots/<id>.png` plus `index.md`.

Needs Playwright (this repository's .venv does not ship it):
    /root/.venvs/enterprise-os/bin/python tools/nexos_screenshots.py [--base http://127.0.0.1:8011]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "user-notes" / "nexos-integration-v1" / "screenshots"


def token() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("KA_AGENTX_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8011")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    req = urllib.request.Request(a.base + "/api/knowledge-acquisition/v1/screens", headers={"Authorization": f"Bearer {token()}"})
    screens = json.loads(urllib.request.urlopen(req, timeout=20).read())["screens"]
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        for s in screens:
            url = a.base + s["path"]                        # launch_url's host may be the public one; the screenshot is taken on loopback
            errors.clear()
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(1500)
            title = page.locator("h1").first.inner_text() if page.locator("h1").count() else ""
            f = OUT / f"{s['id']}.png"
            page.screenshot(path=str(f), full_page=False)
            rows.append((s, title, list(errors)))
            print(f"{s['id']:16} {url}  h1={title!r}  js_errors={len(errors)}")
        b.close()
    md = [f"# KA specialist screens — real screenshots ({stamp})", "",
          f"Taken by `tools/nexos_screenshots.py` from the RUNNING KA (`{a.base}`) at the paths `GET /v1/screens` returns. These are KA's "
          "existing console screens (preserved, not rebuilt); the data shown is the DEV store's real content.", "",
          "| id | title | path | page heading | JS errors | screenshot |", "|---|---|---|---|---|---|"]
    for s, title, errs in rows:
        md.append(f"| `{s['id']}` | {s['title']} | `{s['path']}` | {title} | {len(errs)} | ![{s['id']}]({s['id']}.png) |")
    (OUT / "index.md").write_text("\n".join(md) + "\n")
    return 0 if all(not e for _, _, e in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
# [/block plan-34]
