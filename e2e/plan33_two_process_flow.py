"""plan-33 two-process run (research-05 R12; PT1–PT8 together over real HTTP) — KA (`python -m ka serve`) with NO Enterprise OS root, a
fake AgentX (receives push registration and operation callbacks) and the plan-31 fake Knowledge Worker, all three over HTTP. AgentX's journey:
registration → acquire (callback) → review by a named person (an anonymous answer refused) → publish through Knowledge Worker → the v1
event feed, replayed. Governance is unchanged: the approval is `decide` with the person's name.

    .venv/bin/python e2e/plan33_two_process_flow.py
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
from ka.knowledge_worker.fake import FakeKnowledgeWorker  # noqa: E402

KA = "http://127.0.0.1:8027/api/knowledge-acquisition"
AX, KW = "two-proc-agentx-token", "two-proc-kw-token"
CALLER = {"service_id": "agentx", "user": "alice", "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.review", "knowledge.publish"]}


class FakeAgentX:
    def __init__(self):
        self.calls: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _rec(self):
                n = int(self.headers.get("Content-Length") or 0)
                outer.calls.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"),
                                    "body": json.loads(self.rfile.read(n) or b"{}")})
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
            do_PUT = do_POST = _rec

            def log_message(self, *a):
                pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


def call(method, path, body=None, token=AX):
    req = urllib.request.Request(KA + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def invoke(cap, inp, **extra):
    return call("POST", f"/v1/capabilities/{cap}/invoke", {"schema_version": "1", "input": inp, "caller": CALLER, **extra})


def poll(op, until=("succeeded", "failed", "awaiting_input"), timeout=20):
    end = time.time() + timeout
    st = {}
    while time.time() < end:
        _, st = call("GET", f"/v1/operations/{op}")
        if st.get("status") in until:
            return st
        time.sleep(0.1)
    return st


def main() -> int:
    kw = FakeKnowledgeWorker(token=KW, grammar={"version": "grammar/v3", "nodes": []}, process_types={"version": "process-types/v3", "types": []})
    kw.add_substructure("merchant-acquiring")
    kw_srv = kw.serve()
    kw_url = f"http://127.0.0.1:{kw_srv.server_address[1]}"
    ax = FakeAgentX()
    store = Path(tempfile.mkdtemp(prefix="ka-two-proc-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("KA_")}
    env.update({"KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8027", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open",
                "KA_AGENTX_TOKEN": AX, "KA_AGENTX_URL": ax.url, "KA_KW_URL": kw_url, "KA_KW_TOKEN": KW, "KA_GRAMMAR_URL": kw_url + "/v1/graph-model",
                "KA_ENTERPRISE_OS_ROOT": "", "KA_RESEARCH_INTERNET": "0", "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_STORAGE_BACKEND": "local"})
    proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(Path(__file__).resolve().parents[1]), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r: list[tuple[str, bool]] = []
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(KA + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        _, h = call("GET", "/healthz", token=None)
        r.append(("PT1 KA up with no Enterprise OS root (graph kw, grammar from KW)", h.get("status") == "ok" and h["checks"]["graph"] == "kw"
                  and h["checks"]["grammar"] == "ok"))
        for _ in range(40):
            if any(c["method"] == "PUT" for c in ax.calls):
                break
            time.sleep(0.25)
        put = next((c for c in ax.calls if c["method"] == "PUT"), None)
        r.append(("PT1 KA pushed seven capabilities to AgentX with its token", bool(put) and put["path"].endswith("/services/knowledge-acquisition/capabilities")
                  and len(put["body"]["capabilities"]) == 7 and put["auth"] == f"Bearer {AX}"))
        s, _ = call("GET", "/v1/capabilities", token="wrong")
        r.append(("a wrong token is refused", s == 401))
        call("POST", "/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"}, token=None)
        s, op = invoke("knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                             "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}, callback_url=ax.url + "/callbacks")
        acq = poll(op["operation_id"], until=("succeeded", "failed"))
        ref = (acq.get("result") or {}).get("candidates", [None])[0]
        r.append(("PT2 acquire: 202 with an operation id, then succeeded with a candidate", s == 202 and acq["status"] == "succeeded" and bool(ref)))
        time.sleep(0.5)
        r.append(("callbacks reached AgentX", any(c["path"] == "/callbacks" and c["body"]["operation"]["status"] == "succeeded" for c in ax.calls)))
        _, rv = invoke("knowledge.review", {"item_id": ref})
        st = poll(rv["operation_id"])
        r.append(("PT4 review waits for a person with a form", st["status"] == "awaiting_input" and st["interaction"]["ui_schema"]
                  and st["interaction"]["required_permission"] == "knowledge.review"))
        iid = st["interaction"]["interaction_id"]
        s, _ = call("POST", f"/v1/operations/{rv['operation_id']}/input", {"interaction_id": iid, "values": {"outcome": "APPROVE", "reason": "x"}})
        r.append(("an answer with no named person is refused", s == 403))
        _, done = call("POST", f"/v1/operations/{rv['operation_id']}/input",
                       {"interaction_id": iid, "values": {"outcome": "APPROVE", "reason": "matches the SOP"}, "submitted_by": "alice"})
        done = poll(rv["operation_id"], until=("succeeded", "failed"))
        _, nug = call("GET", f"/nugget/{ref}", token=None)
        decided_by = json.dumps(nug)
        r.append(("PT4 approval went through decide by alice; the nugget is ACTIVE", done["status"] == "succeeded" and '"ACTIVE"' in decided_by
                  and "alice" in decided_by))
        _, pub = invoke("knowledge.publish", {"item_id": ref})
        p = poll(pub["operation_id"], until=("succeeded", "failed"))
        req = kw.requests[-1] if kw.requests else {}
        r.append(("PT6 publish succeeded after KW applied, lineage on every op", p["status"] == "succeeded" and req.get("idempotency_key", "").startswith("ka:")
                  and all((o.get("node") or o.get("edge") or {}).get("props", {}).get("knowledge_lineage") for o in req.get("ops", []) if not o["op"].startswith("remove"))))
        _, ev = call("GET", "/v1/events?after=0&limit=1000")
        types = [e["type"] for e in ev["events"]]
        want = {"knowledge.acquisition.completed", "knowledge.review.required", "knowledge.publication.approved", "knowledge.publication.completed"}
        r.append(("PT7 the event feed has the note's events with ids, schema and provenance", want <= set(types)
                  and all(e["event_id"] and e["schema_version"] == "ka.v1" and e["provenance"]["source_event"] for e in ev["events"])))
        mid = ev["events"][1]["seq"]
        _, again = call("GET", f"/v1/events?after={mid}&limit=1000")
        r.append(("PT7 replay by after= returns the same event ids", [e["event_id"] for e in again["events"]] == [e["event_id"] for e in ev["events"] if e["seq"] > mid]))
    finally:
        proc.terminate(); kw_srv.shutdown(); ax.srv.shutdown()
    for name, ok in r:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if r and all(ok for _, ok in r) else 1


if __name__ == "__main__":
    sys.exit(main())
