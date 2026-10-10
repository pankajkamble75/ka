# [block plan-32]
"""A faithful double of the REAL Data Platform `/v1` subset KA uses (research-05 R9), for tests and flows when the real service is not
running. It mirrors `pankajkamble75/dataplatform`'s shapes and codes: staging → `{upload_id, asset_id, target_version, state, content_url,
commit_url}`; commit needs `Idempotency-Key` (400 `invalid_request` without), checksum mismatch → 422 `invalid_contract`, an expired upload →
409 `conflict` `details.state=expired`; derived assets need a parent and return `{asset, version}`; bindings 201 (new) / 200 (existing);
auth by Bearer or the principal headers. The live flow runs against the real service; this double is checked against the same cases."""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any

SCOPE_TAG = {"DOMAIN": "domain_id", "INSTANCE": "instance_id", "TEAM": "team_id"}


class FakeDataPlatformV1:
    def __init__(self, *, token: str | None = None, tenant: str = "default"):
        self.token, self.tenant = token, tenant
        self.uploads: dict[str, dict[str, Any]] = {}
        self.assets: dict[str, dict[str, Any]] = {}             # asset_id → {type, scope, tags, versions: [ {asset_version_id, version, sha256, bytes} ]}
        self.by_version: dict[str, tuple[str, int]] = {}         # asset_version_id → (asset_id, index)
        self.commit_keys: dict[str, tuple[str, dict]] = {}       # Idempotency-Key → (sha, response)
        self.bindings: dict[tuple[str, int], dict[str, Any]] = {}
        self.derived_calls: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.fail_next: list[tuple[int, str]] = []               # (status, code) injected on the next call

    @staticmethod
    def _err(status: int, code: str, message: str, **details) -> tuple[int, dict[str, str], bytes]:
        return status, {}, json.dumps({"code": code, "message": message, "correlation_id": "fake", "retryable": status >= 500 or status == 429,
                                       "details": details}).encode()

    @staticmethod
    def _ok(status: int, body: Any) -> tuple[int, dict[str, str], bytes]:
        return status, {"Content-Type": "application/json"}, json.dumps(body).encode()

    def expire(self, upload_id: str) -> None:
        self.uploads[upload_id]["state"] = "expired"

    def http(self, method: str, url: str, headers: dict[str, str], body: bytes | None):
        h = {k.lower(): v for k, v in headers.items()}
        path = "/" + url.split("://", 1)[-1].split("/", 1)[-1]
        self.requests.append((method, path, h))
        if self.fail_next:
            s, c = self.fail_next.pop(0)
            return self._err(s, c, "injected")
        if self.token is not None:
            if h.get("authorization") != f"Bearer {self.token}":
                return self._err(401, "unauthenticated", "bearer token required")
        elif not h.get("x-principal-id") or not h.get("x-tenant-id"):
            return self._err(401, "unauthenticated", "X-Principal-Id and X-Tenant-Id are required")
        seg = path.strip("/").split("/")
        j = lambda: json.loads(body or b"{}")  # noqa: E731
        if method == "POST" and path == "/v1/assets/uploads":
            return self._stage(j())
        if method == "PUT" and len(seg) == 5 and seg[:3] == ["v1", "assets", "uploads"] and seg[4] == "content":
            up = self.uploads.get(seg[3])
            if up is None:
                return self._err(404, "not_found", "no upload")
            up["bytes"] = body or b""
            return 204, {}, b""
        if method == "POST" and len(seg) == 5 and seg[:3] == ["v1", "assets", "uploads"] and seg[4] == "commit":
            return self._commit(seg[3], j(), h.get("idempotency-key"))
        if method == "GET" and len(seg) >= 5 and seg[:2] == ["v1", "assets"] and seg[3] == "versions":
            a = self.assets.get(seg[2])
            if a is None:
                return self._err(404, "not_found", "no asset")
            vs = a["versions"]
            v = vs[-1] if seg[4] == "latest" else next((x for x in vs if str(x["version"]) == seg[4]), None)
            if v is None:
                return self._err(404, "not_found", "no version")
            if len(seg) == 6 and seg[5] == "content":
                return 200, {"Content-Type": "application/octet-stream"}, v["bytes"]
            return self._ok(200, {"asset": {"asset_id": seg[2], "type": a["type"], "scope": a["scope"]},
                                  "version": {k: v[k] for k in ("asset_id", "asset_version_id", "version", "sha256", "size_bytes")}})
        if method == "POST" and path == "/v1/derived-assets":
            return self._derived(j())
        if method == "POST" and path == "/v1/knowledge-bindings":
            b = j()
            if b.get("dp_asset_version_id") not in self.by_version:
                return self._err(404, "not_found", "no asset version")
            key = (b["ka_source_id"], int(b["ka_source_version"]))
            created = key not in self.bindings
            self.bindings.setdefault(key, {"binding_id": f"kb_{uuid.uuid4().hex[:10]}", **b})
            return self._ok(201 if created else 200, {"binding": self.bindings[key], "created": created})
        return self._err(404, "not_found", f"{method} {path}")

    def _new_version(self, asset_id: str, atype: str, scope: str, tags: dict, data: bytes) -> dict[str, Any]:
        a = self.assets.setdefault(asset_id, {"type": atype, "scope": scope, "tags": tags, "versions": []})
        v = {"asset_id": asset_id, "asset_version_id": f"av_{uuid.uuid4().hex[:12]}", "version": len(a["versions"]) + 1,
             "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "bytes": data}
        a["versions"].append(v)
        self.by_version[v["asset_version_id"]] = (asset_id, len(a["versions"]) - 1)
        return v

    def _stage(self, b: dict[str, Any]):
        missing = [k for k in ("tenant_id", "sha256", "size_bytes", "mime_type", "type", "scope") if k not in b]
        if missing:
            return self._err(400, "invalid_request", f"missing {missing}")
        if b["scope"] in SCOPE_TAG and not (b.get("tags") or {}).get(SCOPE_TAG[b["scope"]]):
            return self._err(422, "invalid_contract", f"{b['scope']} scope needs tags.{SCOPE_TAG[b['scope']]}")
        if b["type"] not in ("document", "structured", "semi_structured"):
            return self._err(400, "invalid_request", "upload type")
        uid = f"up_{uuid.uuid4().hex[:12]}"
        aid = b.get("asset_id") or f"asset_{uuid.uuid4().hex[:12]}"
        self.uploads[uid] = {**b, "asset_id": aid, "state": "staged", "bytes": None}
        return self._ok(201, {"upload_id": uid, "asset_id": aid, "target_version": len(self.assets.get(aid, {}).get("versions", [])) + 1,
                              "state": "staged", "content_url": f"/v1/assets/uploads/{uid}/content", "commit_url": f"/v1/assets/uploads/{uid}/commit"})

    def _commit(self, uid: str, b: dict[str, Any], key: str | None):
        if not key:
            return self._err(400, "invalid_request", "Idempotency-Key header is required")
        if key in self.commit_keys:
            sha, resp = self.commit_keys[key]
            if sha != b.get("sha256"):
                return self._err(409, "conflict", "Idempotency-Key reused with a different body")
            return self._ok(200, {**resp, "created": False})
        up = self.uploads.get(uid)
        if up is None:
            return self._err(404, "not_found", "no upload")
        if up["state"] == "expired":
            return self._err(409, "conflict", "upload expired", state="expired")
        data = up["bytes"] or b""
        if hashlib.sha256(data).hexdigest() != b.get("sha256") or b.get("sha256") != up["sha256"]:
            return self._err(422, "invalid_contract", "checksum mismatch")
        v = self._new_version(up["asset_id"], up["type"], up["scope"], up.get("tags") or {}, data)
        up["state"] = "committed"
        resp = {k: v[k] for k in ("asset_id", "asset_version_id", "version", "sha256", "size_bytes")}
        self.commit_keys[key] = (b["sha256"], resp)
        return self._ok(201, {**resp, "created": True})

    def _derived(self, b: dict[str, Any]):
        self.derived_calls.append(b)
        if b.get("type") not in ("extracted_text", "nugget", "derived"):
            return self._err(400, "invalid_request", "a derived asset is extracted_text, nugget or derived")
        parents = b.get("parent_asset_version_ids") or []
        if not parents:
            return self._err(400, "invalid_request", "a derived asset needs at least one parent asset version")
        if any(p not in self.by_version for p in parents):
            return self._err(404, "not_found", "no parent asset version")
        pa = self.assets[self.by_version[parents[0]][0]]
        v = self._new_version(f"asset_{uuid.uuid4().hex[:12]}", b["type"], pa["scope"], pa["tags"], base64.b64decode(b["content_base64"]))
        return self._ok(201, {"asset": {"asset_id": v["asset_id"], "type": b["type"], "scope": pa["scope"]},
                              "version": {k: v[k] for k in ("asset_id", "asset_version_id", "version", "sha256", "size_bytes")}})
# [/block plan-32]
