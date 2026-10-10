# [block plan-29]
"""AgentX services contract, PROPOSED v1 (research-05 §1; the AgentX session, 2026-10-10 — `pankajkamble75/agentx`
`docs/contracts/agentx-services-v1.md`, generated from `agentx/contracts.py`). KA ADOPTS it rather than publishing a competing one: AgentX
pulls `GET {base}/v1/capabilities`, invokes `POST {base}/v1/capabilities/{id}/invoke` with an `InvokeRequest`, receives an `OperationState`,
polls `GET {base}/v1/operations/{id}`, and reads errors as `{"error": {code, message, retryable, details}}` with AgentX's error classes."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1"
ERROR_CLASSES = ("unavailable", "timeout", "bad_request", "schema_invalid", "unauthorized", "forbidden", "not_found", "conflict",
                 "stale_version", "rate_limited", "internal", "protocol", "unsupported", "cancelled")
HTTP_STATUS = {"unavailable": 503, "timeout": 504, "bad_request": 400, "schema_invalid": 400, "unauthorized": 401, "forbidden": 403,
               "not_found": 404, "conflict": 409, "stale_version": 409, "rate_limited": 429, "internal": 500, "protocol": 400,
               "unsupported": 400, "cancelled": 409}
RETRYABLE = {"unavailable", "timeout", "rate_limited"}
STATUSES = ("accepted", "running", "awaiting_input", "succeeded", "failed", "cancelled", "timed_out")
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}


class AgentXError(Exception):
    """An error in AgentX's envelope. `code` is one of AgentX's error classes."""

    def __init__(self, code: str, message: str, *, details: Optional[dict[str, Any]] = None, retryable: Optional[bool] = None):
        if code not in ERROR_CLASSES:
            code = "internal"
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}
        self.retryable = code in RETRYABLE if retryable is None else retryable

    @property
    def status(self) -> int:
        return HTTP_STATUS[self.code]

    def envelope(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable, "details": self.details}}

    def as_error(self) -> dict[str, Any]:
        return self.envelope()["error"]


class Caller(BaseModel):
    model_config = ConfigDict(extra="allow")
    service_id: str = "agentx"
    user: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str = SCHEMA_VERSION
    request_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    capability_version: Optional[str] = None
    input: dict[str, Any] = Field(default_factory=dict)
    caller: Caller = Field(default_factory=Caller)
    callback_url: Optional[str] = None


class Interaction(BaseModel):
    interaction_id: str
    prompt: str = ""
    ui_schema: dict[str, Any]
    required_permission: Optional[str] = None       # plan-30: AgentX lets only a holder answer (HumanInteraction, PROPOSED v1)


class OperationState(BaseModel):
    """What AgentX reads back — terminal for a sync capability, polled for an async one."""
    operation_id: str
    capability_id: str
    status: Literal["accepted", "running", "awaiting_input", "succeeded", "failed", "cancelled", "timed_out"]
    progress: float = 0.0
    message: str = ""                                # AgentX: a string, never null
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None
    interaction: Optional[Interaction] = None
    references: dict[str, Any] = Field(default_factory=dict)
# [/block plan-29]
