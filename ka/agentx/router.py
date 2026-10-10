# [block plan-29]
"""The `/v1` surface AgentX calls (research-05 R2, R3, R10), mounted under KA's prefix so AgentX's `base_url` is
`http://<host>:8011/api/knowledge-acquisition`: `GET /v1/capabilities`, `POST /v1/capabilities/{id}/invoke`, `GET /v1/operations/{id}`,
`POST /v1/operations/{id}/cancel`, plus the requirements note's own paths as thin aliases that build an `InvokeRequest` and call the same
code. Auth: `KA_AGENTX_TOKEN` (bearer) when set, else the console's containment. Errors use AgentX's envelope."""
from __future__ import annotations

import hmac
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from ka import __version__, config
from ka.agentx.capabilities import Capability, registry
from ka.agentx.contract import SCHEMA_VERSION, AgentXError, Caller, InvokeRequest
from ka.agentx.operations import Operations
from ka.security import require_access

V1 = "/v1"


def require_agentx(request: Request) -> None:
    expected = config.get("KA_AGENTX_TOKEN") or ""
    if not expected:
        require_access(request)                                    # no AgentX token configured: the console's containment applies
        return
    header = request.headers.get("authorization", "")
    presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not presented or not hmac.compare_digest(presented, expected):
        raise AgentXError("unauthorized", "a bearer token for AgentX is required (KA_AGENTX_TOKEN)")


def build_router(get_ka) -> APIRouter:
    router = APIRouter(prefix=V1, tags=["agentx-v1"], dependencies=[Depends(require_agentx)])

    def caps(ka) -> dict[str, Capability]:
        reg = getattr(ka, "_agentx_caps", None)
        if reg is None:
            reg = ka._agentx_caps = registry(ka)
            extend = getattr(ka, "agentx_extend", None)                # plan-30 adds review / resolve_conflict / publish
            if extend is not None:
                reg.update(extend(ka))
        return reg

    def ops(ka) -> Operations:
        o = getattr(ka, "_agentx_ops", None)
        if o is None:
            o = ka._agentx_ops = Operations(ka.repo)
        return o

    def invoke(ka, capability_id: str, req: InvokeRequest, idem: Optional[str] = None) -> tuple[int, dict[str, Any]]:
        cap = caps(ka).get(capability_id)
        if cap is None:
            raise AgentXError("not_found", f"no capability {capability_id!r}", details={"capabilities": sorted(caps(ka))})
        if req.capability_version and req.capability_version.split(".")[0] != cap.version.split(".")[0]:
            raise AgentXError("stale_version", f"{capability_id} is {cap.version}; the request was planned on {req.capability_version}")
        if req.schema_version != SCHEMA_VERSION:
            raise AgentXError("protocol", f"schema_version {req.schema_version!r} is not supported (KA speaks {SCHEMA_VERSION!r})")
        missing = [p for p in cap.permissions if p not in req.caller.permissions]
        if missing:
            raise AgentXError("forbidden", f"the caller lacks {', '.join(missing)}", details={"required": cap.permissions})
        cap.parse(req.input)                                         # schema_invalid before anything is recorded
        op = ops(ka).start(cap.id, cap.version, req, cap.handler, mode=cap.mode, idempotency_key=idem)
        state = Operations.state(op).model_dump(mode="json")
        return (200 if cap.mode == "sync" else 202), state

    @router.get("/capabilities")
    def list_capabilities(ka=Depends(get_ka)) -> dict[str, Any]:
        return {"service_id": config.get("KA_SERVICE_ID"), "schema_version": SCHEMA_VERSION,
                "capabilities": [c.descriptor() for c in caps(ka).values()]}

    @router.post("/capabilities/{capability_id}/invoke")
    def invoke_route(capability_id: str, req: InvokeRequest, ka=Depends(get_ka),
                     idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
                     x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
                     x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")):
        req.request_id = req.request_id or x_request_id
        req.correlation_id = req.correlation_id or x_correlation_id
        status, body = invoke(ka, capability_id, req, idempotency_key or req.idempotency_key)
        return JSONResponse(body, status_code=status)

    @router.get("/operations/{operation_id}")
    def get_operation(operation_id: str, ka=Depends(get_ka)) -> dict[str, Any]:
        return Operations.state(ops(ka).get(operation_id)).model_dump(mode="json")

    @router.post("/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str, ka=Depends(get_ka)) -> dict[str, Any]:
        return Operations.state(ops(ka).cancel(operation_id)).model_dump(mode="json")

    # ---- the requirements note's own paths, as aliases of the same code --------------------------------------------------------

    def _req(body: dict[str, Any], key: Optional[str]) -> InvokeRequest:
        caller = body.pop("caller", None) or {"service_id": "agentx", "permissions": ["knowledge.acquire", "knowledge.read", "knowledge.revise",
                                                                                         "knowledge.review", "knowledge.publish"]}
        return InvokeRequest(input=body, caller=Caller(**caller), idempotency_key=key)

    @router.post("/acquisitions")
    def acquisitions(body: dict[str, Any], ka=Depends(get_ka), idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
        status, state = invoke(ka, "knowledge.acquire", _req(dict(body), idempotency_key), idempotency_key)
        return JSONResponse(state, status_code=status)

    @router.get("/acquisitions/{operation_id}")
    def acquisition(operation_id: str, ka=Depends(get_ka)) -> dict[str, Any]:
        return get_operation(operation_id, ka)

    @router.get("/knowledge/search")
    def knowledge_search_get(query: str, kind: str = "all", limit: int = 20, instance_id: Optional[str] = None,
                             domain_id: Optional[str] = None, ka=Depends(get_ka)) -> dict[str, Any]:
        inp = {k: v for k, v in {"query": query, "kind": kind, "limit": limit, "instance_id": instance_id, "domain_id": domain_id}.items() if v is not None}
        return invoke(ka, "knowledge.search", _req(inp, None))[1]

    @router.post("/knowledge/search")
    def knowledge_search_post(body: dict[str, Any], ka=Depends(get_ka)) -> dict[str, Any]:
        """Knowledge Worker's preview adapter shape: {query, instance_id?, domain_id?, limit} → {results[], version}."""
        body = dict(body)
        body.pop("caller", None)
        state = invoke(ka, "knowledge.search", _req(body, None))[1]
        return {"results": (state.get("result") or {}).get("hits", []), "version": __version__, "operation_id": state["operation_id"]}

    @router.get("/knowledge/{item_id}")
    def knowledge_read(item_id: str, ka=Depends(get_ka)) -> dict[str, Any]:
        return invoke(ka, "knowledge.read", _req({"item_id": item_id}, None))[1]

    @router.post("/knowledge/{item_id}/revisions")
    def knowledge_revise(item_id: str, body: dict[str, Any], ka=Depends(get_ka),
                         idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        b = dict(body)
        caller = b.pop("caller", None)
        req = _req({"item_id": item_id, **b}, idempotency_key)
        if caller:
            req.caller = Caller(**caller)
        return invoke(ka, "knowledge.revise", req, idempotency_key)[1]

    router.ka_ops = ops                                              # tests and plan-30 reach the store through the router
    router.ka_caps = caps
    return router


def agentx_error_handler(request: Request, exc: AgentXError) -> JSONResponse:
    return JSONResponse(exc.envelope(), status_code=exc.status)


def health_payload(ka) -> dict[str, Any]:
    checks = {"storage": "ok" if ka.repo.root.exists() else "down", "provider": getattr(ka.provider, "name", "?"),
              "grammar": "ok" if ka.grammar.loaded else "not_loaded"}
    status = "ok" if checks["storage"] == "ok" else "down"
    if status == "ok" and checks["grammar"] != "ok":
        status = "degraded"
    return {"status": status, "service_id": config.get("KA_SERVICE_ID"), "version": __version__, "checks": checks}
# [/block plan-29]
