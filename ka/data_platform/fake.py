# [block plan-19]
"""`FakeDataPlatform` — the DP v1 subset KA needs, implemented at the WIRE level (paths, headers, status codes, the error envelope) so
the same fixtures can be run by the real Data Platform. State is in memory. `as_http()` plugs it straight into `DataPlatformClient`;
`serve()` runs it on a real local HTTP port for the live flow. It models: idempotent uploads (409 on a key reused with different bytes),
422 on a wrong SHA, ACLs (tenant match; a PERSONAL asset is readable by its owner only), derived assets, events, and `fail_next` outages.
This is a fake of the API, not a mock of a cloud SDK."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import uuid
from typing import Any

_UPLOAD_CONTENT = re.compile(r"^/v1/assets/uploads/([^/]+)/content$")
_UPLOAD_COMMIT = re.compile(r"^/v1/assets/uploads/([^/]+)/commit$")
_CONTENT = re.compile(r"^/v1/assets/([^/]+)/versions/([^/]+)/content$")
_VERSION = re.compile(r"^/v1/assets/([^/]+)/versions/([^/]+)$")


def _envelope(status: int, code: str, message: str, retryable: bool = False) -> tuple[int, dict[str, str], bytes]:
    body = {"code": code, "message": message, "correlation_id": f"corr-{uuid.uuid4().hex[:8]}", "retryable": retryable}
    return status, {"Content-Type": "application/json"}, json.dumps(body).encode()


def _ok(obj: Any, status: int = 200) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode()


class FakeDataPlatform:
    def __init__(self, *, token: str | None = None):
        self.token = token                      # None: accept any bearer; set: require it
        self.uploads: dict[str, dict[str, Any]] = {}
        self.assets: dict[str, dict[str, Any]] = {}        # asset_id → {tenant, owner, visibility, type, versions: {vid: {sha, bytes, content_type}}}
        self.by_key: dict[str, tuple[str, str, str]] = {}  # idempotency key → (asset_id, version_id, sha)
        self.events: list[dict[str, Any]] = []
        self.denials: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self._fail: list[int] = []
        self._lock = threading.Lock()

    # ---- test controls -----------------------------------------------------------------------------------------

    def fail_next(self, n: int = 1, status: int = 503) -> None:
        self._fail += [status] * n

    def revoke(self, asset_id: str) -> None:
        self._event("data.asset.access_revoked.v1", asset_id)

    def delete(self, asset_id: str) -> None:
        self.assets.pop(asset_id, None)
        self._event("data.asset.deleted.v1", asset_id)

    def quarantine(self, asset_id: str) -> None:
        self._event("data.asset.quarantined.v1", asset_id)

    def _event(self, type_: str, asset_id: str, version_id: str | None = None) -> None:
        self.events.append({"event_id": f"evt-{uuid.uuid4().hex[:8]}", "seq": len(self.events) + 1, "type": type_, "asset_id": asset_id,
                            "asset_version_id": version_id, "at": "2026-10-09T00:00:00Z"})

    # ---- the wire ----------------------------------------------------------------------------------------------

    def handle(self, method: str, path: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], bytes]:
        h = {k.lower(): v for k, v in (headers or {}).items()}
        path_only, _, query = path.partition("?")
        with self._lock:
            self.calls.append((method, path_only))
            if self._fail:
                status = self._fail.pop(0)
                return _envelope(status, "unavailable" if status >= 500 else "rate_limited", "the Data Platform is unavailable", retryable=True)
            if self.token is not None and h.get("authorization") != f"Bearer {self.token}":
                return _envelope(401, "unauthenticated", "a valid service token is required")
            tenant = h.get("x-ka-tenant") or ""
            if method == "POST" and path_only == "/v1/assets/uploads":
                req = json.loads(body or b"{}")
                key = h.get("idempotency-key") or ""
                if not key:
                    return _envelope(422, "schema_invalid", "Idempotency-Key is required")
                uid = f"up-{uuid.uuid4().hex[:8]}"
                self.uploads[uid] = {"key": key, "tenant": req.get("tenant_id") or tenant, "owner": req.get("owner") or "", "visibility": req.get("visibility") or "ENTERPRISE",
                                     "type": req.get("asset_type") or "source_document", "content_type": req.get("content_type") or "application/octet-stream", "bytes": None}
                return _ok({"upload_id": uid}, 201)
            m = _UPLOAD_CONTENT.match(path_only)
            if m and method == "PUT":
                up = self.uploads.get(m.group(1))
                if up is None:
                    return _envelope(404, "not_found", "unknown upload")
                if len(body or b"") > 25 * 1024 * 1024:
                    return _envelope(413, "too_large", "upload exceeds the limit")
                up["bytes"] = body or b""
                return 204, {}, b""
            m = _UPLOAD_COMMIT.match(path_only)
            if m and method == "POST":
                up = self.uploads.get(m.group(1))
                if up is None:
                    return _envelope(404, "not_found", "unknown upload")
                if up["bytes"] is None:
                    return _envelope(422, "schema_invalid", "no content uploaded")
                sha = hashlib.sha256(up["bytes"]).hexdigest()
                want = (json.loads(body or b"{}").get("sha256") or "").lower()
                if want != sha:
                    return _envelope(422, "checksum_mismatch", f"content sha {sha[:12]}… does not match committed sha {want[:12]}…")
                prior = self.by_key.get(up["key"])
                if prior is not None:
                    if prior[2] != sha:
                        return _envelope(409, "idempotency_conflict", "Idempotency-Key reused with different content")
                    aid, vid, _ = prior
                    return _ok({"asset_id": aid, "asset_version_id": vid, "sha256": sha, "state": "available", "replayed": True})
                aid = f"asset_{uuid.uuid4().hex[:8]}"
                vid = f"av_{uuid.uuid4().hex[:8]}"
                self.assets[aid] = {"tenant": up["tenant"], "owner": up["owner"], "visibility": up["visibility"], "type": up["type"],
                                    "versions": {vid: {"sha": sha, "bytes": up["bytes"], "content_type": up["content_type"]}}}
                self.by_key[up["key"]] = (aid, vid, sha)
                self._event("data.asset.committed.v1", aid, vid)
                return _ok({"asset_id": aid, "asset_version_id": vid, "sha256": sha, "state": "available"})
            m = _CONTENT.match(path_only)
            if m and method == "GET":
                a = self.assets.get(m.group(1))
                v = (a or {}).get("versions", {}).get(m.group(2))
                if a is None or v is None:
                    return _envelope(404, "not_found", "unknown asset version")
                owner = h.get("x-ka-owner") or ""
                if a["tenant"] != tenant or (a["visibility"] == "PERSONAL" and owner != a["owner"]):
                    self.denials.append({"asset_id": m.group(1), "owner": owner, "tenant": tenant})
                    return _envelope(403, "policy_denied", "the caller may not read this asset")
                return 200, {"Content-Type": v["content_type"]}, v["bytes"]
            m = _VERSION.match(path_only)
            if m and method == "GET":
                a = self.assets.get(m.group(1))
                v = (a or {}).get("versions", {}).get(m.group(2))
                if a is None or v is None:
                    return _envelope(404, "not_found", "unknown asset version")
                return _ok({"asset_id": m.group(1), "asset_version_id": m.group(2), "sha256": v["sha"], "state": "available", "asset_type": a["type"]})
            if method == "POST" and path_only == "/v1/assets/derived":
                req = json.loads(body or b"{}")
                key = h.get("idempotency-key") or ""
                payload = base64.b64decode(req.get("payload_b64") or "")
                sha = hashlib.sha256(payload).hexdigest()
                prior = self.by_key.get(key) if key else None
                if prior is not None and prior[2] == sha:
                    return _ok({"asset_id": prior[0], "asset_version_id": prior[1], "sha256": sha, "state": "available", "replayed": True})
                aid = f"asset_{uuid.uuid4().hex[:8]}"
                vid = f"av_{uuid.uuid4().hex[:8]}"
                self.assets[aid] = {"tenant": req.get("tenant_id") or tenant, "owner": "", "visibility": "ENTERPRISE", "type": req.get("asset_type") or "derived",
                                    "parent": (req.get("parent_asset_id"), req.get("parent_asset_version_id")), "provenance": req.get("provenance") or {},
                                    "versions": {vid: {"sha": sha, "bytes": payload, "content_type": "application/json"}}}
                if key:
                    self.by_key[key] = (aid, vid, sha)
                self._event("data.asset.committed.v1", aid, vid)
                return _ok({"asset_id": aid, "asset_version_id": vid, "sha256": sha, "state": "available"})
            if method == "GET" and path_only == "/v1/events":
                q = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
                after = int(q.get("after", "0") or 0); limit = int(q.get("limit", "200") or 200)
                evs = [e for e in self.events if e["seq"] > after][:limit]
                return _ok({"events": evs, "next_after": evs[-1]["seq"] if evs else after})
            return _envelope(404, "not_found", f"no route {method} {path_only}")

    def as_http(self):
        def http(method, url, headers, body):
            path = url.split("//", 1)[-1].split("/", 1)[1] if "//" in url else url
            return self.handle(method, "/" + path, headers, body)
        return http

    def serve(self, host: str = "127.0.0.1", port: int = 8099):
        """A real HTTP server around `handle`, for the live flow. Returns the server; call `.shutdown()` to stop."""
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        fake = self

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else None
                status, hdrs, out = fake.handle(self.command, self.path, dict(self.headers.items()), body)
                self.send_response(status)
                for k, v in hdrs.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
            do_GET = do_POST = do_PUT = _do
            def log_message(self, *a): pass
        srv = ThreadingHTTPServer((host, port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
# [/block plan-19]
