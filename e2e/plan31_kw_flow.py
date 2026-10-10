"""plan-31 live flow (PT1, PT6, PT8 over real HTTP) — a fake Knowledge Worker served over HTTP (approval mode); a KA server with KA_KW_URL,
KA_GRAMMAR_URL and NO Enterprise OS root: the grammar loads from KW, a candidate is acquired, reviewed and approved through /v1, and
knowledge.publish stays running until KW approves, then succeeds with KW's proposal id.

    .venv/bin/python e2e/plan31_kw_flow.py
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
from ka.knowledge_worker.fake import FakeKnowledgeWorker  # noqa: E402

BASE = "http://127.0.0.1:8024/api/knowledge-acquisition"
AX, KW = "flow-agentx-token", "flow-kw-token"
CALLER = {"service_id": "agentx", "user": "alice", "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.review", "knowledge.publish"]}


def call(method, path, body=None, token=AX):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def invoke(cap, inp):
    return call("POST", f"/v1/capabilities/{cap}/invoke", {"schema_version": "1", "input": inp, "caller": CALLER})[1]


def poll(op, until=("succeeded", "failed", "awaiting_input"), timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        _, st = call("GET", f"/v1/operations/{op}")
        if st["status"] in until:
            return st
        time.sleep(0.1)
    return st


def main() -> int:
    fake = FakeKnowledgeWorker(token=KW, mode="approval", grammar={"version": "grammar/v2", "nodes": []},
                               process_types={"version": "process-types/v2", "types": []})
    fake.add_substructure("merchant-acquiring")
    srv = fake.serve()
    kw = f"http://127.0.0.1:{srv.server_address[1]}"
    store = Path(tempfile.mkdtemp(prefix="ka-kw-flow-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("KA_")}
    env.update({"KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8024", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open", "KA_AGENTX_TOKEN": AX,
                "KA_KW_URL": kw, "KA_KW_TOKEN": KW, "KA_GRAMMAR_URL": kw + "/v1/graph-model", "KA_ENTERPRISE_OS_ROOT": "", "KA_RESEARCH_INTERNET": "0",
                "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": "", "KA_STORAGE_BACKEND": "local"})
    proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(Path(__file__).resolve().parents[1]), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(BASE + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        _, h = call("GET", "/healthz", token=None)
        results.append(("KA runs with no Enterprise OS root, graph mode kw", h["checks"]["graph"] == "kw" and h["status"] in ("ok", "degraded")))
        results.append(("the grammar loaded from Knowledge Worker", h["checks"]["grammar"] == "ok"))
        _, g = call("GET", "/grammar", token=None)
        results.append(("its snapshot carries KW's digests", g.get("grammar_digest") == fake.file_digests()[0]))
        call("POST", "/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"}, token=None)
        acq = poll(invoke("knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                                "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}})["operation_id"], until=("succeeded", "failed"))
        ref = acq["result"]["candidates"][0]
        st = poll(invoke("knowledge.review", {"item_id": ref})["operation_id"])
        call("POST", f"/v1/operations/{st['operation_id']}/input", {"interaction_id": st["interaction"]["interaction_id"],
                                                                     "values": {"outcome": "APPROVE", "reason": "ok"}, "submitted_by": "alice"})
        pub = invoke("knowledge.publish", {"item_id": ref})
        time.sleep(1.5)
        _, mid = call("GET", f"/v1/operations/{pub['operation_id']}")
        results.append(("publish waits while KW holds the change", mid["status"] == "running" and mid["message"] == "awaiting Knowledge Worker"))
        kwid = mid["references"].get("kw_proposal_id")
        req = fake.requests[-1] if fake.requests else {}
        results.append(("KW received lineage on every op and KA's key", kwid and req.get("idempotency_key", "").startswith("ka:GCP-")
                        and all((o.get("node") or o.get("edge") or {}).get("props", {}).get("knowledge_lineage") for o in req.get("ops", []) if not o["op"].startswith("remove"))))
        fake.approve(kwid)
        done = poll(pub["operation_id"], until=("succeeded", "failed"))
        results.append(("after KW applies, publish succeeds", done["status"] == "succeeded" and done["result"]["status"] == "APPLIED"))
        results.append(("one KW proposal (apply replayed the key)", len(fake.proposals) == 1))
    finally:
        proc.terminate(); srv.shutdown()
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
