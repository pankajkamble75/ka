"""Live-keys check (paid, bounded): AgentX's `knowledge.acquire` with `kind: research` against the REAL Anthropic key and the REAL Brave
search key from KA's gitignored `.env` (never printed). KA runs on port 8028 with throwaway storage; the live service and its data are not
touched. Budget: KA_DISCOVERY_BUDGET=2 fetches, KA_RESEARCH_MAX_SOURCES=1. A person then reviews the first candidate through /v1.

    .venv/bin/python e2e/live_keys_research_flow.py
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

ROOT = Path(__file__).resolve().parents[1]
KA = "http://127.0.0.1:8028/api/knowledge-acquisition"
AX = "live-keys-agentx-token"
CALLER = {"service_id": "agentx", "user": "alice", "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.review", "knowledge.publish"]}


def call(method, path, body=None, token=AX):
    req = urllib.request.Request(KA + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def poll(op, until=("succeeded", "failed", "awaiting_input"), timeout=600):
    end, st = time.time() + timeout, {}
    while time.time() < end:
        _, st = call("GET", f"/v1/operations/{op}")
        if st.get("status") in until:
            return st
        time.sleep(1)
    return st


def find(o, k):
    """The first scalar value under key `k` anywhere in a JSON response."""
    if isinstance(o, dict):
        if k in o and not isinstance(o[k], (dict, list)):
            return o[k]
        return next((x for x in (find(v, k) for v in o.values()) if x is not None), None)
    if isinstance(o, list):
        return next((x for x in (find(v, k) for v in o) if x is not None), None)
    return None


def main() -> int:
    dotenv = {l.split("=", 1)[0]: l.split("=", 1)[1].strip().strip('"') for l in (ROOT / ".env").read_text().splitlines() if "=" in l and not l.startswith("#")}
    for k in ("ANTHROPIC_API_KEY", "KA_SEARCH_API_KEY"):
        if not dotenv.get(k):
            print(f"BLOCKED  {k} is not set in .env"); return 2
    env = {k: v for k, v in os.environ.items() if not k.startswith("KA_")}
    env.update({"KA_STORAGE_ROOT": tempfile.mkdtemp(prefix="ka-live-keys-"), "KA_BACKEND_PORT": "8028", "KA_ACCESS_POLICY": "open", "KA_AGENTX_TOKEN": AX,
                "KA_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": dotenv["ANTHROPIC_API_KEY"], "KA_SEARCH_PROVIDER": dotenv.get("KA_SEARCH_PROVIDER", "brave"),
                "KA_SEARCH_API_KEY": dotenv["KA_SEARCH_API_KEY"], "KA_RESEARCH_INTERNET": "1", "KA_DISCOVERY_BUDGET": "2", "KA_RESEARCH_MAX_SOURCES": "1",
                "KA_ENTERPRISE_OS_ROOT": "", "KA_STORAGE_BACKEND": "local"})
    proc = subprocess.Popen([sys.executable, "-m", "ka", "serve"], cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r: list[tuple[str, bool]] = []
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(KA + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        _, h = call("GET", "/healthz", token=None)
        r.append(("provider is Anthropic (real key)", h["checks"].get("provider") == "anthropic"))
        call("POST", "/scopes", {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "name": "Merchant Acquiring"}, token=None)
        t0 = time.time()
        s, op = call("POST", "/v1/capabilities/knowledge.acquire/invoke", {"schema_version": "1", "caller": CALLER, "input": {
            "kind": "research", "name": "Chargeback time limits", "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"},
            "question": "What is the time limit for a cardholder to file a chargeback under Visa and Mastercard rules?"}})
        st = poll(op["operation_id"], until=("succeeded", "failed"))
        res = st.get("result") or {}
        print(f"   mission {res.get('mission_id')} finished {st.get('status')} in {time.time() - t0:.0f}s; error={st.get('error')}")
        r.append(("research operation accepted (202) and succeeded", s == 202 and st.get("status") == "succeeded"))
        _, srcs = call("GET", "/sources", token=None)
        urls = [x.get("original_location") for x in srcs.get("sources", []) if x.get("source_type") == "url" and x.get("original_location")]
        print("   web sources fetched:", urls or "none")
        r.append(("Brave search found and fetched web sources", bool(urls)))
        cands = res.get("candidates") or []
        print(f"   {len(cands)} candidates; first three:")
        for ref in cands[:3]:
            _, n = call("GET", f"/nugget/{ref}", token=None)
            print(f"   - {ref}: {str(find(n, 'statement'))[:200]}  [{find(n, 'status')} · {find(n, 'authority_type')}]")
        r.append(("Claude extracted at least one candidate from them", bool(cands)))
        if cands:
            _, rv = call("POST", "/v1/capabilities/knowledge.review/invoke", {"schema_version": "1", "caller": CALLER, "input": {"item_id": cands[0]}})
            w = poll(rv["operation_id"], timeout=60)
            r.append(("the research candidate waits for a person (not auto-approved)", w.get("status") == "awaiting_input"))
    finally:
        proc.terminate()
    for name, ok in r:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if r and all(ok for _, ok in r) else 1


if __name__ == "__main__":
    sys.exit(main())
