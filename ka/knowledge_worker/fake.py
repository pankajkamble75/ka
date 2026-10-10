# [block plan-31]
"""A wire-level Knowledge Worker for tests and live flows (research-05 R7): implements KA's intake contract
(`docs/contracts/knowledge-worker-v1-ka.md`) — `POST /v1/graph-changes`, `GET /v1/graph-changes/{id}`, `GET /v1/graph-model`,
`GET /v1/graph-versions`, `GET /healthz` — with KW's envelope, token scopes, base digests, idempotency and an approval mode. It keeps graphs
as a dict of element ids per target and NEVER imports Knowledge Worker code."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

GRAPH_CHANGE = re.compile(r"^/v1/graph-changes/([^/]+)$")


def _env(result: Any = None, *, correlation_id: str = "", error: Optional[dict] = None) -> dict[str, Any]:
    return {"contract_version": "1", "correlation_id": correlation_id, "status": "error" if error else "ok", "result": result, "error": error,
            "provenance": {"service": "knowledge-worker-fake"}}


class FakeKnowledgeWorker:
    def __init__(self, *, token: str = "kw-token", scopes: tuple[str, ...] = ("graph-changes:propose", "graphs:read"), mode: str = "auto",
                 grammar: Optional[dict] = None, process_types: Optional[dict] = None):
        self.token, self.scopes, self.mode = token, set(scopes), mode            # mode: auto (apply at once) | approval
        self.grammar = grammar or {"version": "grammar/v9", "nodes": []}
        self.process_types = process_types or {"version": "process-types/v9", "types": []}
        self.instances: dict[str, dict[str, Any]] = {}                          # id → {"elements": {id: op}, "rev": n}
        self.substructures: dict[str, dict[str, Any]] = {}                      # id → {"elements": {...}, "version": "1"}
        self.proposals: dict[str, dict[str, Any]] = {}
        self.by_key: dict[str, tuple[str, str]] = {}                             # idempotency_key → (proposal id, body hash)
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ---- graph state ------------------------------------------------------------------------------------------------
    def add_instance(self, iid: str) -> None:
        self.instances.setdefault(iid, {"elements": {}, "rev": 0})

    def add_substructure(self, sid: str, version: str = "1") -> None:
        self.substructures.setdefault(sid, {"elements": {}, "version": version})

    @staticmethod
    def _digest(g: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(g["elements"], sort_keys=True).encode()).hexdigest()

    def file_digests(self) -> tuple[str, str]:
        return (hashlib.sha256(json.dumps(self.grammar, sort_keys=True).encode()).hexdigest(),
                hashlib.sha256(json.dumps(self.process_types, sort_keys=True).encode()).hexdigest())

    def approve(self, proposal_id: str) -> None:
        with self._lock:
            p = self.proposals[proposal_id]
            if p["result"]["status"] == "awaiting_approval":
                self._apply(p)

    def _apply(self, p: dict[str, Any]) -> None:
        t = p["target"]
        g = self.instances[t["id"]] if t["kind"] == "instance" else self.substructures[t["id"]]
        for op in p["ops"]:
            el = op.get("node") or op.get("edge") or {}
            eid = el.get("id") or op.get("id")
            if op["op"].startswith("remove"):
                g["elements"].pop(eid, None)
            else:
                g["elements"][eid] = el
        if t["kind"] == "substructure":
            g["version"] = str(int(g["version"]) + 1)
            p["result"]["new_version"] = g["version"]
        p["result"].update(status="applied", applied_digest=self._digest(g))

    # ---- the wire ------------------------------------------------------------------------------------------------------
    def handle(self, method: str, path: str, headers: dict[str, str], body: Optional[bytes]) -> tuple[int, dict[str, Any]]:
        h = {k.lower(): v for k, v in headers.items()}
        cid = h.get("x-correlation-id", "")
        auth = h.get("authorization", "")
        if auth != f"Bearer {self.token}":
            return 401, _env(correlation_id=cid, error={"status": 401, "code": "UNAUTHORIZED", "message": "bad token", "retryable": False})
        path = path.split("?", 1)[0]
        if method == "GET" and path == "/healthz":
            return 200, {"status": "ok", "service_id": "knowledge-worker", "version": "fake"}
        if method == "GET" and path == "/v1/graph-model":
            if "graphs:read" not in self.scopes:
                return 403, {"error": {"code": "FORBIDDEN", "message": "graphs:read required"}}
            gd, td = self.file_digests()
            return 200, {"grammar": self.grammar, "process_types": self.process_types, "grammar_version": self.grammar["version"],
                         "type_table_version": self.process_types["version"], "grammar_digest": gd, "type_table_digest": td,
                         "source": "knowledge_worker/graph_model"}
        if method == "GET" and path == "/v1/graph-versions":
            return 200, {"substructures": {k: {"version": v["version"], "digest": self._digest(v)} for k, v in self.substructures.items()},
                         "instances": {k: {"digest": self._digest(v), "pins": {}} for k, v in self.instances.items()}}
        if "graph-changes:propose" not in self.scopes:
            return 403, _env(correlation_id=cid, error={"status": 403, "code": "FORBIDDEN", "message": "graph-changes:propose required", "retryable": False})
        m = GRAPH_CHANGE.match(path)
        if method == "GET" and m:
            p = self.proposals.get(m.group(1))
            if p is None:
                return 404, _env(correlation_id=cid, error={"status": 404, "code": "NOT_FOUND", "message": "no proposal", "retryable": False})
            return 200, _env(dict(p["result"]), correlation_id=cid)
        if method == "POST" and path == "/v1/graph-changes":
            return self._propose(json.loads(body or b"{}"), cid)
        return 404, _env(correlation_id=cid, error={"status": 404, "code": "NOT_FOUND", "message": f"{method} {path}", "retryable": False})

    def _propose(self, req: dict[str, Any], cid: str) -> tuple[int, dict[str, Any]]:
        self.requests.append(req)
        err = lambda s, code, msg, **kw: (s, _env(correlation_id=cid, error={"status": s, "code": code, "message": msg, "retryable": False, **kw}))  # noqa: E731
        t, ops, key = req.get("target") or {}, req.get("ops"), req.get("idempotency_key")
        if not isinstance(ops, list) or not key or t.get("kind") not in ("instance", "substructure") or not t.get("id"):
            return err(422, "INVALID_REQUEST", "target {kind, id}, ops[] and idempotency_key are required")
        for op in ops:
            el = op.get("node") or op.get("edge")
            if el is not None and not op.get("op", "").startswith("remove") and not (el.get("props") or {}).get("knowledge_lineage"):
                return err(422, "INVALID_REQUEST", f"{el.get('id')}: props.knowledge_lineage is required", detail={"element": el.get("id")})
        bh = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
        with self._lock:
            if key in self.by_key:
                pid, prior = self.by_key[key]
                if prior != bh:
                    return err(409, "CONFLICT", "idempotency_key reused with a different body")
                return 200, _env(dict(self.proposals[pid]["result"]), correlation_id=cid)
            store = self.instances if t["kind"] == "instance" else self.substructures
            if t["id"] not in store:
                return err(404, "UNKNOWN_INSTANCE", f"no {t['kind']} {t['id']!r}")
            g = store[t["id"]]
            if t["kind"] == "instance" and t.get("base_digest") and t["base_digest"] != self._digest(g):
                return err(409, "STALE_BASE", "base_digest is not the current instance digest")
            if t["kind"] == "substructure" and t.get("base_version") and str(t["base_version"]) != g["version"]:
                return err(409, "STALE_BASE", "base_version is not the latest")
            pid = f"prop-{uuid.uuid4().hex[:12]}"
            p = {"target": t, "ops": ops, "result": {"proposal_id": pid, "status": "awaiting_approval", "applied_digest": None, "new_version": None,
                                                    "pinned_instances": [], "lineage": sorted({r.get("nugget_ref") for r in req.get("knowledge_refs") or [] if r.get("nugget_ref")})}}
            self.proposals[pid] = p
            self.by_key[key] = (pid, bh)
            if self.mode == "auto":
                self._apply(p)
            return 200, _env(dict(p["result"]), correlation_id=cid)

    # ---- transports ---------------------------------------------------------------------------------------------------
    def as_http(self):
        def http(method, url, headers, body):
            path = "/" + url.split("://", 1)[-1].split("/", 1)[-1]
            status, data = self.handle(method, path, headers, body)
            return status, json.dumps(data).encode()
        return http

    def serve(self, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
        fake = self

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                status, data = fake.handle(self.command, self.path, dict(self.headers), self.rfile.read(n) if n else None)
                out = json.dumps(data).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
                self.end_headers(); self.wfile.write(out)
            do_GET = do_POST = _do

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer((host, port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
# [/block plan-31]
