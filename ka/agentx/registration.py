# [block plan-30]
"""Push registration and operation callbacks to AgentX (research-05 R3, R4), both through the plan-20 outbox so a down AgentX costs a
retry, never a lost message: `agentx_register` PUTs the full capability list to `{KA_AGENTX_URL}/api/v1/services/{KA_SERVICE_ID}/capabilities`
(AgentX's push path; the list is the full set — a missing id is deregistration); `agentx_callback` POSTs an `OperationEvent {service_id,
operation}` to the `callback_url` an invocation carried. Bearer: `KA_AGENTX_TOKEN` (AgentX checks the same service token both ways).
Pull registration (`GET /v1/capabilities`) needs none of this."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Any

from ka import config
from ka.data_platform import DataPlatformError

TIMEOUT_S = 15.0


def _send(method: str, url: str, body: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json", "X-Service-Id": config.get("KA_SERVICE_ID"), "X-Schema-Version": "1"}
    token = config.get("KA_AGENTX_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            r.read()
    except urllib.error.HTTPError as e:
        text = (e.read() or b"")[:300].decode(errors="replace")
        if e.code in (408, 425, 429) or e.code >= 500:
            raise RuntimeError(f"HTTP {e.code}: {text}") from None              # retryable: the outbox backs off
        raise DataPlatformError(e.code, "agentx_refused", f"HTTP {e.code}: {text}", retryable=False) from None


def attach(ka) -> None:
    """Register the two outbox handlers on KA's outbox."""
    ka.outbox.handlers["agentx_register"] = lambda op: _send("PUT", op.payload["url"], op.payload["body"])
    ka.outbox.handlers["agentx_callback"] = lambda op: _send("POST", op.payload["url"], op.payload["body"])


def push_capabilities(ka, descriptors: list[dict[str, Any]]) -> dict[str, Any]:
    base = (config.get("KA_AGENTX_URL") or "").rstrip("/")
    if not base:
        return {"pushed": False, "reason": "KA_AGENTX_URL is not set; AgentX pulls GET /v1/capabilities"}
    body = {"capabilities": descriptors}
    key = "agentx-register:" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24]
    url = f"{base}/api/v1/services/{config.get('KA_SERVICE_ID')}/capabilities"
    op = ka.outbox.enqueue("agentx_register", key, {"url": url, "body": body}, by="ka.agentx")
    ka.outbox.process_once(by="ka.agentx")
    op = ka.repo.dp_outbox.require(op.id)
    return {"pushed": op.state == "done", "state": op.state, "outbox_op": op.id, "url": url, "error": op.last_error}


def callback(ka, operation) -> None:
    """Enqueue one OperationEvent for a status change of an operation that carried a callback_url."""
    if not operation.callback_url:
        return
    from ka.agentx.operations import Operations
    state = Operations.state(operation).model_dump(mode="json")
    seen = int(operation.references.get("_callbacks", 0))
    key = f"agentx-callback:{operation.id}:{operation.status}:{operation.progress:.2f}:{seen}"
    ka.outbox.enqueue("agentx_callback", key, {"url": operation.callback_url, "operation_id": operation.id,
                                               "body": {"service_id": config.get("KA_SERVICE_ID"), "operation": state}}, by="ka.agentx")
    ka.outbox.process_once(by="ka.agentx")
# [/block plan-30]
