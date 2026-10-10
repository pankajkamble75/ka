"""plan-32 live flow (PT9) — KA against the REAL Data Platform service (`/root/dataplatform`, `start-dataplatform.sh`), started here on its
own port (8110) with its own fresh data root outside both repositories (`/tmp/ka-dp-root-*`), loopback principal headers, and STOPPED at the end —
the conditions the Data Platform session set. KA (port 8026, KA_DP_API=v1) acquires a text through AgentX's /v1, the bytes commit on the DP
with a knowledge binding, the bytes read back through KA, a person approves the candidate, and the nugget version lands on the DP as a
`nugget` derived asset whose parent is the source's asset version.

    .venv/bin/python e2e/plan32_dp_real_flow.py
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

DP_REPO = Path(os.environ.get("KA_FLOW_DP_REPO", "/root/dataplatform"))
DP = "http://127.0.0.1:8110"
KA = "http://127.0.0.1:8026/api/knowledge-acquisition"
AX = "flow-agentx-token"
DPH = {"X-Principal-Id": "ka", "X-Tenant-Id": "default", "X-Scopes": "storage:read,storage:write"}
CALLER = {"service_id": "agentx", "user": "alice", "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.review", "knowledge.publish"]}


def call(base, method, path, body=None, headers=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait(url, headers=None, n=120):
    for _ in range(n):
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=1)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    if not (DP_REPO / "start-dataplatform.sh").exists():
        print(f"BLOCKED  no Data Platform checkout at {DP_REPO}")
        return 2
    dp_env = {k: v for k, v in os.environ.items() if not k.startswith(("DATA_PLATFORM_", "KA_"))}
    dp_env.update({"DATA_PLATFORM_DATA_ROOT": tempfile.mkdtemp(prefix="ka-dp-root-")})     # a fresh root per run: no stale writer lock
    log = open(Path(tempfile.gettempdir()) / "ka-dp-real-flow.log", "wb")
    dp = subprocess.Popen(["bash", "start-dataplatform.sh", "--host", "127.0.0.1", "--port", "8110"], cwd=DP_REPO, env=dp_env,
                          stdout=log, stderr=subprocess.STDOUT)
    store = Path(tempfile.mkdtemp(prefix="ka-dp-real-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("KA_")}
    env.update({"KA_STORAGE_ROOT": str(store), "KA_BACKEND_PORT": "8026", "KA_LLM_PROVIDER": "stub", "KA_ACCESS_POLICY": "open", "KA_AGENTX_TOKEN": AX,
                "KA_STORAGE_BACKEND": "data_platform", "KA_DP_BASE_URL": DP, "KA_DP_API": "v1", "KA_DP_AUTH_MODE": "headers", "KA_DP_SERVICE_TOKEN": "",
                "KA_TENANT_ID": "default", "KA_ENTERPRISE_OS_ROOT": "", "KA_RESEARCH_INTERNET": "0", "KA_SEARCH_PROVIDER": "none", "ANTHROPIC_API_KEY": ""})
    ka = None
    results = []
    try:
        up = wait(DP + "/v1/health", DPH) and dp.poll() is None
        results.append(("the real Data Platform started (own root, port 8110)", up))
        if not up:
            raise SystemExit("the Data Platform did not start; see " + log.name)
        ka = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(Path(__file__).resolve().parents[1]), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait(KA + "/healthz")
        _, phys = call(KA, "GET", "/physical/status")
        results.append(("KA's physical store is the Data Platform", (phys or {}).get("backend") == "data_platform"))
        call(KA, "POST", "/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"})
        _, op = call(KA, "POST", "/v1/capabilities/knowledge.acquire/invoke",
                     {"schema_version": "1", "caller": CALLER, "input": {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                                                         "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}},
                     {"Authorization": f"Bearer {AX}"})
        st = op
        for _ in range(80):
            _, st = call(KA, "GET", f"/v1/operations/{op['operation_id']}", headers={"Authorization": f"Bearer {AX}"})
            if st["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        ref = (st.get("result") or {}).get("candidates", [None])[0]
        _, src = call(KA, "GET", f"/sources/{(st.get('result') or {}).get('source_id')}")
        pb = ((src or {}).get("bindings") or [{}])[-1]
        aid, avid = pb.get("dp_asset_id"), pb.get("dp_asset_version_id")
        results.append(("the bytes committed on the DP (available, DP ids)", bool(aid and avid) and pb.get("status") == "available"))
        s, raw = call(DP, "GET", f"/v1/assets/{aid}/versions/latest/content", headers=DPH)
        results.append(("the DP serves the same bytes", s == 200 and b"$500" in (raw if isinstance(raw, bytes) else json.dumps(raw).encode())))
        call(KA, "POST", f"/nugget/{ref}/decide", {"outcome": "APPROVE", "by": "alice", "reason": "flow"})
        arts = []
        for _ in range(60):
            call(KA, "POST", "/physical/outbox/run")
            _, d = call(KA, "GET", f"/nugget/{ref}/derived")
            arts = [a for a in (d or {}).get("derived", []) if a.get("state") == "available"]
            if arts:
                break
            time.sleep(0.25)
        results.append(("the nugget version is a DP derived asset", bool(arts)))
        if arts:
            s, v = call(DP, "GET", f"/v1/assets/{arts[-1]['dp_asset_id']}/versions/latest", headers=DPH)
            results.append(("of type nugget, scope from its parent", s == 200 and v["asset"]["type"] == "nugget"))
            parents = v["version"].get("parent_asset_versions") or []
            results.append(("whose parent is the source's asset version", avid in json.dumps(parents)))
    finally:
        if ka:
            ka.terminate()
        dp.terminate()
        try:
            dp.wait(timeout=10)
        except subprocess.TimeoutExpired:
            dp.kill()
    results.append(("the Data Platform was stopped", dp.poll() is not None))
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
