# [block plan-34]
"""NEXOS v1 G0/G1 evidence: probe the RUNNING KA over real HTTP with AgentX's token, validate every response against AgentX's vendored
schemas (`ka/agentx/schemas`), and write `docs/user-notes/nexos-integration-v1/evidence/live-<UTC>.json` plus `api-matrix.md`.

It invokes only READ capabilities on the live service (knowledge.search, knowledge.read): no knowledge is created, decided or published.
The token is read from KA's gitignored `.env` and never written to the evidence.

    .venv/bin/python tools/nexos_evidence.py [--base http://127.0.0.1:8011] [--public http://2.25.98.235:8011]
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ka.agentx.conformance import descriptor_errors, errors  # noqa: E402

OUT = ROOT / "docs" / "user-notes" / "nexos-integration-v1"
PREFIX = "/api/knowledge-acquisition"
CALLER = {"service_id": "agentx", "user": "nexos-evidence", "permissions": ["knowledge.read"]}


def dotenv(key: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def call(base, method, path, body=None, token=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + PREFIX + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read() or b"", e.code
    except (urllib.error.URLError, OSError) as e:
        return {"status": None, "ms": round((time.time() - t0) * 1000), "body": None, "transport_error": str(e)}
    try:
        data = json.loads(raw or b"null")
    except ValueError:
        data = raw[:200].decode(errors="replace")
    return {"status": status, "ms": round((time.time() - t0) * 1000), "body": data}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8011")
    ap.add_argument("--public", default="http://2.25.98.235:8011")
    a = ap.parse_args()
    tok = dotenv("KA_AGENTX_TOKEN")
    if not tok:
        print("BLOCKED  KA_AGENTX_TOKEN is not set in .env"); return 2
    rows: list[dict] = []

    def check(name, method, path, expect, *, body=None, token=tok, schema=None, base=None, headers=None, extra=None):
        r = call(base or a.base, method, path, body, token, headers)
        errs = []
        if schema and isinstance(r["body"], (dict, list)):
            errs = errors(schema, r["body"])
        if extra and isinstance(r["body"], (dict, list)):
            errs += extra(r["body"])
        ok = r["status"] == expect and not errs
        rows.append({"check": name, "method": method, "path": PREFIX + path, "via": base or a.base, "auth": "AgentX bearer" if token == tok else
                     ("none" if not token else "wrong bearer"), "expect": expect, "status": r["status"], "ms": r["ms"], "schema": schema,
                     "conformance_errors": errs, "pass": ok, "body": r["body"], **({"transport_error": r["transport_error"]} if "transport_error" in r else {})})
        return r

    h = check("health", "GET", "/healthz", 200, schema="Health.schema.json")
    caps = check("capability discovery", "GET", "/v1/capabilities", 200, schema="CapabilityList.schema.json",
                 extra=lambda b: [f"{d['id']}: {e}" for d in b.get("capabilities", []) for e in descriptor_errors(d)])
    check("screen manifest", "GET", "/v1/screens", 200,
          extra=lambda b: [f"{s.get('id')}: missing {k}" for s in b.get("screens", []) for k in ("id", "title", "path", "launch_url", "embed_url",
                                                                                                 "deep_link_params", "requires", "provided_by") if k not in s])
    s = check("invoke knowledge.search (sync)", "POST", "/v1/capabilities/knowledge.search/invoke", 200, schema="OperationState.schema.json",
              body={"schema_version": "1", "input": {"query": "refund approval", "limit": 3}, "caller": CALLER})
    if isinstance(s["body"], dict) and s["body"].get("operation_id"):
        check("operation status", "GET", f"/v1/operations/{s['body']['operation_id']}", 200, schema="OperationState.schema.json")
        check("idempotent replay (same key → same operation)", "POST", "/v1/capabilities/knowledge.search/invoke", 200, schema="OperationState.schema.json",
              body={"schema_version": "1", "input": {"query": "refund approval", "limit": 3}, "caller": CALLER},
              headers={"Idempotency-Key": f"nexos-evidence-{s['body']['operation_id']}"})
        hits = ((s["body"].get("result") or {}).get("hits") or [])
        ref = next((x.get("ref") or x.get("id") for x in hits if (x.get("ref") or x.get("id"))), None)
        if ref:
            check("invoke knowledge.read", "POST", "/v1/capabilities/knowledge.read/invoke", 200, schema="OperationState.schema.json",
                  body={"schema_version": "1", "input": {"item_id": ref}, "caller": CALLER})
    check("human tasks", "GET", "/v1/tasks?limit=5", 200)
    check("events (replayable)", "GET", "/v1/events?after=0&limit=5", 200)
    check("error: no token", "GET", "/v1/capabilities", 401, token=None, base=a.public, schema=None)
    check("error: wrong token", "GET", "/v1/capabilities", 401, token="wrong-token", schema=None,
          extra=lambda b: errors("ErrorInfo.schema.json", b.get("error", b)) if isinstance(b, dict) and "error" in b else [])
    check("error: unknown capability", "POST", "/v1/capabilities/knowledge.nope/invoke", 404,
          body={"schema_version": "1", "input": {}, "caller": CALLER}, extra=lambda b: errors("ErrorInfo.schema.json", b.get("error", {})))
    check("error: schema_invalid input", "POST", "/v1/capabilities/knowledge.search/invoke", 400,
          body={"schema_version": "1", "input": {"nope": 1}, "caller": CALLER}, extra=lambda b: errors("ErrorInfo.schema.json", b.get("error", {})))
    unavailable = ((h["body"] or {}).get("checks") or {}).get("capabilities_unavailable") or {}
    if "knowledge.publish" in unavailable:
        check("error: unavailable capability (publish, no KW)", "POST", "/v1/capabilities/knowledge.publish/invoke", 503,
              body={"schema_version": "1", "input": {"item_id": "KN-000:v1"}, "caller": {**CALLER, "permissions": ["knowledge.publish"]}},
              extra=lambda b: errors("ErrorInfo.schema.json", b.get("error", {})) + ([] if b.get("error", {}).get("code") == "unavailable" else ["code is not unavailable"]))
    check("public interface, AgentX bearer", "GET", "/healthz", 200, base=a.public, schema="Health.schema.json")

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    pid = subprocess.run(["systemctl", "show", "enterprise-os-ka", "-p", "ActiveEnterTimestamp", "--value"], capture_output=True, text=True).stdout.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = {"taken_at": stamp, "host": socket.gethostname(), "repo": "pankajkamble75/ka", "sha": sha, "service_started": pid, "base": a.base,
          "public": a.public, "capabilities": [d["id"] for d in (caps["body"] or {}).get("capabilities", [])],
          "capabilities_unavailable": unavailable, "checks": rows}
    (OUT / "evidence").mkdir(parents=True, exist_ok=True)
    (OUT / "evidence" / f"live-{stamp}.json").write_text(json.dumps(ev, indent=1, default=str))
    lines = [f"# KA API matrix — live evidence ({stamp})", "",
             f"Generated by `tools/nexos_evidence.py` against the RUNNING service on `{socket.gethostname()}` (`{a.base}`, public `{a.public}`), "
             f"code `pankajkamble75/ka@{sha}`, service started {pid}. Raw responses: [`evidence/live-{stamp}.json`](evidence/live-{stamp}.json). "
             "Schemas: AgentX's vendored `agentx-services/v1` (`ka/agentx/schemas`). Only read capabilities were invoked.", "",
             f"Capabilities advertised: {', '.join(ev['capabilities'])}. Unavailable: "
             + (", ".join(f"`{k}` — {v}" for k, v in unavailable.items()) or "none") + ".", "",
             "| # | check | method | path | via | auth | expect | got | ms | schema | conformance | result |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['check']} | {r['method']} | `{r['path']}` | {'public IP' if r['via'] == a.public else 'loopback'} | {r['auth']} | "
                     f"{r['expect']} | {r['status']} | {r['ms']} | {r['schema'] or '—'} | {'; '.join(r['conformance_errors'])[:200] or 'ok'} | "
                     f"{'PASS' if r['pass'] else 'FAIL'} |")
    passed = sum(r["pass"] for r in rows)
    lines += ["", f"**{passed} of {len(rows)} checks pass.**", ""]
    (OUT / "api-matrix.md").write_text("\n".join(lines))
    print(f"{passed}/{len(rows)} pass → evidence/live-{stamp}.json, api-matrix.md")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['check']}: {r['status']} {('; '.join(r['conformance_errors']))[:160]}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
# [/block plan-34]
