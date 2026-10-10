"""plan-29 live flow (PT2, PT3 over real HTTP) — a KA server with KA_AGENTX_TOKEN on temp storage; a minimal AgentX client (this script)
pulls /v1/capabilities, checks each descriptor against AgentX's vendored schemas, invokes knowledge.acquire, polls to succeeded, approves
the candidates through KA's console route (review over /v1 is plan-30), searches and reads with provenance, and checks idempotency.

    .venv/bin/python e2e/plan29_agentx_flow.py
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ka.agentx import conformance as X  # noqa: E402

BASE = "http://127.0.0.1:8022/api/knowledge-acquisition"
TOKEN = "flow-agentx-token"
CALLER = {"service_id": "agentx", "user": "pankaj", "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.revise", "knowledge.review", "knowledge.publish"]}


def call(method, path, body=None, *, token=TOKEN, headers=None):
    h = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def invoke(cap, inp, key=None):
    return call("POST", f"/v1/capabilities/{cap}/invoke", {"schema_version": "1", "request_id": f"r-{time.time()}", "idempotency_key": key or f"k-{time.time()}",
                                                           "correlation_id": "flow-1", "capability_version": "1.0.0", "input": inp, "caller": CALLER},
                headers={"Idempotency-Key": key} if key else None)


def poll(op_id):
    for _ in range(200):
        _, st = call("GET", f"/v1/operations/{op_id}")
        if st["status"] in ("succeeded", "failed", "cancelled", "timed_out"):
            return st
        time.sleep(0.1)
    return st


def main() -> int:
    store = Path(tempfile.mkdtemp(prefix="ka-agentx-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8022", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_AGENTX_TOKEN": TOKEN, "KA_RESEARCH_INTERNET": "0", "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_STORAGE_BACKEND": "local",
           "KA_ENTERPRISE_OS_ROOT": ""}
    proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(Path(__file__).resolve().parents[1]), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(BASE + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        call("POST", "/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"}, token=None)
        code, health = call("GET", "/healthz")
        results.append(("healthz is AgentX-shaped", code == 200 and X.errors("Health.schema.json", health) == [] and health["service_id"] == "knowledge-acquisition"))
        code, _ = call("GET", "/v1/capabilities", token="wrong")
        results.append(("a wrong bearer is refused 401", code == 401))
        _, caps = call("GET", "/v1/capabilities")
        bad = {d["id"]: X.descriptor_errors(d) for d in caps["capabilities"] if X.descriptor_errors(d)}
        results.append(("every descriptor conforms to AgentX's schemas", X.errors("CapabilityList.schema.json", caps) == [] and not bad))
        code, st = invoke("knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                                "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}, key="flow-acq-1")
        results.append(("acquire answers 202 with an operation id", code == 202 and st["operation_id"].startswith("AXO-")))
        done = poll(st["operation_id"])
        results.append(("the operation reaches succeeded with candidates", done["status"] == "succeeded" and done["result"]["candidates"]))
        _, again = invoke("knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                                "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}, key="flow-acq-1")
        results.append(("the same idempotency key returns the same operation", again["operation_id"] == st["operation_id"]))
        for ref in done["result"]["candidates"]:
            call("POST", f"/nugget/{ref}/decide", {"outcome": "APPROVE", "by": "pankaj", "reason": "ok"}, token=None)
        _, s = invoke("knowledge.search", {"query": "refunds approval"})
        hits = s["result"]["hits"]
        results.append(("search returns the governed nugget with provenance", any(h["kind"] == "nugget" and h["provenance"]["decision_id"] for h in hits)))
        _, r = invoke("knowledge.read", {"item_id": done["result"]["candidates"][0]})
        results.append(("read returns the provenance chain", r["status"] == "succeeded" and r["result"]["provenance"]["evidence"] and r["result"]["provenance"]["decisions"]))
        _, kw = call("POST", "/v1/knowledge/search", {"query": "refunds", "domain_id": "merchant-acquiring", "limit": 5})
        results.append(("Knowledge Worker's search shape is served", kw["results"] and kw["version"]))
        results.append(("every state and error conforms", X.errors("OperationState.schema.json", done) == [] and X.errors("OperationState.schema.json", r) == []))
    finally:
        proc.terminate()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
