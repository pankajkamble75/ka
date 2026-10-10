"""plan-30 live flow (PT1, PT4, PT6 over real HTTP) — a fake AgentX server receives KA's capability push and operation callbacks; through
/v1 a candidate is acquired, reviewed via an interaction (AgentX's UiSchema validated), approved by a named user, and its graph change is
published only when applied; an agent user is refused.

    .venv/bin/python e2e/plan30_agentx_review_flow.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ka.agentx import conformance as X  # noqa: E402

BASE = "http://127.0.0.1:8023/api/knowledge-acquisition"
TOKEN = "flow-agentx-token"
CALLS: list[dict] = []


class AgentX(BaseHTTPRequestHandler):
    def _rec(self):
        n = int(self.headers.get("Content-Length") or 0)
        CALLS.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(self.rfile.read(n) or b"{}")})
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
    do_PUT = do_POST = _rec

    def log_message(self, *a):
        pass


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def invoke(cap, inp, user="alice", cb=None):
    return call("POST", f"/v1/capabilities/{cap}/invoke", {"schema_version": "1", "input": inp, "callback_url": cb,
                                                           "caller": {"service_id": "agentx", "user": user, "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.review", "knowledge.publish"]}})[1]


def poll(op, until=("succeeded", "failed", "awaiting_input")):
    for _ in range(200):
        _, st = call("GET", f"/v1/operations/{op}")
        if st["status"] in until:
            return st
        time.sleep(0.1)
    return st


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), AgentX)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    agentx = f"http://127.0.0.1:{srv.server_address[1]}"
    store = Path(tempfile.mkdtemp(prefix="ka-agentx-review-flow-"))
    env = {**os.environ, "KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8023", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
           "KA_AGENTX_TOKEN": TOKEN, "KA_AGENTX_URL": agentx, "KA_RESEARCH_INTERNET": "0", "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "",
           "KA_STORAGE_BACKEND": "local", "KA_ENTERPRISE_OS_ROOT": ""}
    proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(Path(__file__).resolve().parents[1]), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(BASE + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        time.sleep(1.0)
        put = [c for c in CALLS if c["method"] == "PUT"]
        results.append(("KA pushed its seven capabilities to AgentX on start", put and len(put[0]["body"]["capabilities"]) == 7 and put[0]["auth"] == f"Bearer {TOKEN}"))
        results.append(("every pushed descriptor conforms", put and all(X.descriptor_errors(d) == [] for d in put[0]["body"]["capabilities"])))
        urllib.request.urlopen(urllib.request.Request(BASE + "/scopes", data=json.dumps({"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"}).encode(),
                                                      headers={"Content-Type": "application/json"}, method="POST"))
        acq = poll(invoke("knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                                "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}})["operation_id"], until=("succeeded", "failed"))
        ref = acq["result"]["candidates"][0]
        cb = agentx + "/api/v1/callbacks/knowledge-acquisition"
        st = poll(invoke("knowledge.review", {"item_id": ref}, cb=cb)["operation_id"])
        results.append(("review waits for input with a valid AgentX form", st["status"] == "awaiting_input" and X.ui_errors(st["interaction"]["ui_schema"]) == []
                        and st["interaction"]["required_permission"] == "knowledge.review"))
        code, bad = call("POST", f"/v1/operations/{st['operation_id']}/input", {"interaction_id": st["interaction"]["interaction_id"], "values": {"outcome": "APPROVE", "reason": "x"}})
        results.append(("input without a named user is refused 403", code == 403))
        _, done = call("POST", f"/v1/operations/{st['operation_id']}/input", {"interaction_id": st["interaction"]["interaction_id"],
                                                                                "values": {"outcome": "APPROVE", "reason": "matches the SOP"}, "submitted_by": "alice"})
        results.append(("approve by alice succeeds through governance", done["status"] == "succeeded" and done["result"]["decided_by"] == "alice"))
        _, nug = call("GET", f"/v1/knowledge/{ref}")
        results.append(("the nugget is ACTIVE", nug["result"]["item"]["status"] == "ACTIVE"))
        events = [c["body"]["operation"]["status"] for c in CALLS if c["method"] == "POST"]
        results.append(("AgentX received callbacks ending in succeeded", "awaiting_input" in events and events[-1] == "succeeded"))
        pub = poll(invoke("knowledge.publish", {"item_id": ref})["operation_id"], until=("succeeded", "failed"))
        results.append(("publish succeeds only when APPLIED", pub["status"] == "succeeded" and pub["result"]["status"] == "APPLIED" and pub["result"]["lineage"] == [ref]))
        _, tasks = call("GET", "/v1/tasks")
        results.append(("no open review task remains for the decided candidate", all(t["item_id"] != ref for t in tasks["tasks"])))
    finally:
        proc.terminate(); srv.shutdown()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
