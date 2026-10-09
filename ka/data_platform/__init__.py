# [block plan-19]
"""The Data Platform boundary (research-03 R11 and R2's HTTP half): a typed client for the DP v1 subset KA needs — uploads, content,
commit, derived assets, events — with the error envelope modelled and the service token read from the environment at call time.
No cloud SDK; HTTP only. The wire shapes are the executable fixtures under `ka/tests/fixtures/dp_contract/`, which
`ka/data_platform/fake.py` implements and which the real Data Platform can run as its acceptance tests."""
from __future__ import annotations

import base64
import json
from typing import Any, Callable

from ka import config

Http = Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, str], bytes]]

RETRYABLE = {429, 500, 502, 503, 504}


class DataPlatformError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, correlation_id: str | None = None, retryable: bool | None = None):
        super().__init__(f"{code} ({status}): {message}")
        self.status, self.code, self.message, self.correlation_id = status, code, message, correlation_id
        self.retryable = (status in RETRYABLE) if retryable is None else bool(retryable)


class ConfigurationError(ImportError):
    """Raised when the DP backend is requested without a base URL — an ImportError subclass so `select_physical_store` fails closed."""


def _default_http(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], bytes]:
    import httpx
    r = httpx.request(method, url, headers=headers, content=body, timeout=float(config.get("KA_DP_TIMEOUT")))
    return r.status_code, dict(r.headers), r.content


class DataPlatformClient:
    def __init__(self, base_url: str, *, http: Http | None = None, tenant_id: str | None = None, token_env: str = "KA_DP_SERVICE_TOKEN"):
        self.base_url = base_url.rstrip("/")
        self.http = http or _default_http
        self.tenant_id = tenant_id or config.get("KA_TENANT_ID") or "default"
        self.token_env = token_env

    # ---- plumbing --------------------------------------------------------------------------------------------

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        token = config.get(self.token_env) or ""
        h = {"Accept": "application/json", "X-KA-Tenant": self.tenant_id}
        if token:
            h["Authorization"] = f"Bearer {token}"
        h.update(extra or {})
        return h

    def _call(self, method: str, path: str, *, headers: dict[str, str] | None = None, body: bytes | None = None, json_body: dict | None = None):
        h = self._headers(headers)
        if json_body is not None:
            body = json.dumps(json_body).encode()
            h["Content-Type"] = "application/json"
        status, rh, raw = self.http(method, f"{self.base_url}{path}", h, body)
        if status >= 400:
            try:
                env = json.loads(raw or b"{}")
            except ValueError:
                env = {}
            raise DataPlatformError(status, env.get("code") or f"http_{status}", env.get("message") or (raw[:200].decode(errors="replace") if raw else ""),
                                    env.get("correlation_id"), env.get("retryable"))
        return status, rh, raw

    def _json(self, *a, **kw) -> dict[str, Any]:
        _s, _h, raw = self._call(*a, **kw)
        return json.loads(raw or b"{}")

    # ---- the subset --------------------------------------------------------------------------------------------

    def create_upload(self, *, asset_type: str, content_type: str, idempotency_key: str, owner: str | None, visibility: str) -> str:
        d = self._json("POST", "/v1/assets/uploads", headers={"Idempotency-Key": idempotency_key},
                       json_body={"asset_type": asset_type, "tenant_id": self.tenant_id, "content_type": content_type, "owner": owner or "", "visibility": visibility})
        return d["upload_id"]

    def upload_content(self, upload_id: str, data: bytes) -> None:
        self._call("PUT", f"/v1/assets/uploads/{upload_id}/content", headers={"Content-Type": "application/octet-stream"}, body=data)

    def commit(self, upload_id: str, *, sha256: str) -> dict[str, Any]:
        return self._json("POST", f"/v1/assets/uploads/{upload_id}/commit", json_body={"sha256": sha256})

    def get_content(self, asset_id: str, asset_version_id: str, *, owner: str | None = None) -> bytes:
        _s, _h, raw = self._call("GET", f"/v1/assets/{asset_id}/versions/{asset_version_id}/content", headers={"X-KA-Owner": owner or ""})
        return raw

    def exists(self, asset_id: str, asset_version_id: str) -> bool:
        try:
            self._call("GET", f"/v1/assets/{asset_id}/versions/{asset_version_id}", headers={})
            return True
        except DataPlatformError as e:
            if e.status == 404:
                return False
            raise

    def put_derived(self, *, asset_type: str, payload: bytes, parent_asset_id: str | None, parent_asset_version_id: str | None,
                    provenance: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        return self._json("POST", "/v1/assets/derived", headers={"Idempotency-Key": idempotency_key},
                          json_body={"asset_type": asset_type, "tenant_id": self.tenant_id, "parent_asset_id": parent_asset_id,
                                     "parent_asset_version_id": parent_asset_version_id, "provenance": provenance,
                                     "payload_b64": base64.b64encode(payload).decode()})

    def events(self, *, after: int = 0, limit: int = 200) -> dict[str, Any]:
        return self._json("GET", f"/v1/events?after={int(after)}&limit={int(limit)}")
# [/block plan-19]
