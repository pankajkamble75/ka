# [block plan-31]
"""KA's Knowledge Worker client (research-05 R7; contract `docs/contracts/knowledge-worker-v1-ka.md`): stdlib HTTP, KW's v1 envelope, typed
errors. `http` is injectable (tests pass the fake's in-process transport)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from ka import config

Transport = Callable[[str, str, dict[str, str], Optional[bytes]], tuple[int, bytes]]


class KnowledgeWorkerError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False, detail: Any = None):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.retryable, self.detail = status, code, message, retryable, detail


def _urllib(method: str, url: str, headers: dict[str, str], body: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=float(config.get("KA_DP_TIMEOUT"))) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""


class KnowledgeWorkerClient:
    def __init__(self, base_url: str, *, token: Optional[str] = None, http: Optional[Transport] = None):
        self.base_url, self.token, self.http = base_url.rstrip("/"), token, http or _urllib

    @classmethod
    def from_config(cls) -> Optional["KnowledgeWorkerClient"]:
        url = config.get("KA_KW_URL")
        return cls(url, token=config.get("KA_KW_TOKEN") or None) if url else None

    def _call(self, method: str, path: str, body: Any = None, *, correlation_id: Optional[str] = None, envelope: bool = True) -> Any:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        try:
            status, raw = self.http(method, self.base_url + path, headers, json.dumps(body).encode() if body is not None else None)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise KnowledgeWorkerError(503, "UNAVAILABLE", f"{type(e).__name__}: {e}", retryable=True) from None
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise KnowledgeWorkerError(status, "PROTOCOL", f"non-JSON response ({status})") from None
        if not envelope:
            if status >= 300:
                err = data.get("error") if isinstance(data, dict) else None
                raise KnowledgeWorkerError(status, (err or {}).get("code", "ERROR"), (err or {}).get("message", f"HTTP {status}"))
            return data
        if status >= 300 or data.get("status") == "error":
            err = data.get("error") or {}
            raise KnowledgeWorkerError(status, err.get("code") or "ERROR", err.get("message") or f"HTTP {status}",
                                       retryable=bool(err.get("retryable", status >= 500)), detail=err.get("detail"))
        return data.get("result") or {}

    def propose(self, *, target: dict[str, Any], ops: list[dict[str, Any]], reason: str, actor: str, knowledge_refs: list[dict[str, Any]],
                idempotency_key: str, correlation_id: Optional[str] = None) -> dict[str, Any]:
        return self._call("POST", "/v1/graph-changes", {"target": target, "ops": ops, "reason": reason, "actor": actor,
                                                        "knowledge_refs": knowledge_refs, "idempotency_key": idempotency_key},
                          correlation_id=correlation_id or idempotency_key)

    def get(self, proposal_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/graph-changes/{proposal_id}")

    def graph_versions(self) -> dict[str, Any]:
        """KW's real shape (KW session, 2026-10-10), enveloped: {domains: {id: {latest, versions[{version, digest, …}], pinned_by}},
        instances: {id: {graph_digest, pins}}, library, import}."""
        return self._call("GET", "/v1/graph-versions")

    def graph_model(self) -> dict[str, Any]:
        return self._call("GET", "/v1/graph-model", envelope=False)
# [/block plan-31]
