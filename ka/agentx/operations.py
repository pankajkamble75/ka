# [block plan-29]
"""Durable operations (research-05 R3): every AgentX invocation is an `Operation` record (one JSON per object), in AgentX's
`OperationState` shape. Sync capabilities run inline and return a terminal state; async ones run on a bounded daemon-thread pool (plan-17's
pattern) and are polled. The same idempotency key with the same input returns the existing operation — never executes twice; a different
input under the same key is a conflict. Cancellation is honoured while the operation has not started (and by handlers that check between
steps). A handler's exception becomes a `failed` operation with AgentX's error envelope."""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Callable, Optional

from ka.agentx.contract import TERMINAL, AgentXError, InvokeRequest, OperationState
from ka.governance import GovernanceError
from ka.model import Operation
from ka.timeutil import now_iso

Handler = Callable[["OperationContext"], dict[str, Any]]
MAX_WORKERS = 4


def request_hash(capability_id: str, inp: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"c": capability_id, "i": inp}, sort_keys=True, default=str).encode()).hexdigest()


class OperationContext:
    """What a handler sees: the operation, its input, the caller, and progress/cancel hooks."""

    def __init__(self, ops: "Operations", op: Operation):
        self.ops, self.op = ops, op

    @property
    def input(self) -> dict[str, Any]:
        return self.op.input

    @property
    def user(self) -> str:
        return self.op.user or self.op.caller_service or "agentx"

    def progress(self, fraction: float, message: Optional[str] = None, **references: Any) -> None:
        op = self.ops.repo.operations.require(self.op.id)
        op.progress, op.updated_at = max(0.0, min(1.0, float(fraction))), now_iso()
        if message is not None:
            op.message = message
        op.references.update({k: v for k, v in references.items() if v is not None})
        self.ops.repo.operations.put(op)
        self.op = op

    def cancelled(self) -> bool:
        return bool(self.ops.repo.operations.require(self.op.id).cancel_requested)

    # [block plan-30] research-05 R5: a capability that needs a person opens an interaction and returns; input resumes it
    def await_input(self, prompt: str, ui_schema: dict[str, Any], *, required_permission: Optional[str] = None, **references: Any) -> dict[str, Any]:
        op = self.ops.repo.operations.require(self.op.id)
        n = int(op.references.get("interactions", 0)) + 1
        op.interaction = {"interaction_id": f"{op.id}:{n}", "prompt": prompt, "ui_schema": ui_schema, "required_permission": required_permission}
        op.references.update({"interactions": n, **{k: v for k, v in references.items() if v is not None}})
        op.status, op.message = "awaiting_input", prompt
        self.ops._save(op)
        self.op = op
        return {}
    # [/block plan-30]


class Operations:
    def __init__(self, repo):
        self.repo = repo
        self._sem = threading.BoundedSemaphore(MAX_WORKERS)
        self._threads: dict[str, threading.Thread] = {}
        self.on_change: list[Callable[[Operation], None]] = []          # plan-30: callbacks through the outbox

    # ---- state ----------------------------------------------------------------------------------------------------

    @staticmethod
    def state(op: Operation) -> OperationState:
        return OperationState(operation_id=op.id, capability_id=op.capability_id, status=op.status, progress=op.progress, message=op.message or "",
                              result=op.result, error=op.error, interaction=op.interaction, references=op.references)

    def get(self, operation_id: str) -> Operation:
        op = self.repo.operations.get(operation_id)
        if op is None:
            raise AgentXError("not_found", f"no operation {operation_id!r}")
        return op

    def _save(self, op: Operation) -> Operation:
        op.updated_at = now_iso()
        self.repo.operations.put(op)
        for fn in list(self.on_change):
            try:
                fn(op)
            except Exception:  # noqa: BLE001 — a notification failure never changes the operation
                pass
        return op

    # ---- start ------------------------------------------------------------------------------------------------------

    def start(self, capability_id: str, version: str, req: InvokeRequest, handler: Handler, *, mode: str,
              idempotency_key: Optional[str] = None) -> Operation:
        key = idempotency_key or req.idempotency_key
        h = request_hash(capability_id, req.input)
        if key:
            prior = self.repo.operations.where(lambda o: o.idempotency_key == key and o.capability_id == capability_id)
            if prior:
                p = sorted(prior, key=lambda o: o.created_at)[0]
                if p.request_hash != h:
                    raise AgentXError("conflict", f"idempotency key {key!r} was used for a different input",
                                      details={"operation_id": p.id, "reason": "idempotency_conflict"})
                return p                                              # never execute twice
        op = Operation(capability_id=capability_id, capability_version=version, input=req.input, idempotency_key=key, request_hash=h,
                       request_id=req.request_id, correlation_id=req.correlation_id, caller_service=req.caller.service_id,
                       user=req.caller.user, permissions=list(req.caller.permissions), callback_url=req.callback_url)
        self._save(op)
        if mode == "sync":
            return self._run(op.id, handler)
        t = threading.Thread(target=self._run, args=(op.id, handler), name=f"ka-op-{op.id}", daemon=True)
        self._threads[op.id] = t
        t.start()
        return self.repo.operations.require(op.id)

    def _run(self, operation_id: str, handler: Handler) -> Operation:
        with self._sem:
            op = self.repo.operations.require(operation_id)
            if op.cancel_requested or op.status == "cancelled":
                op.status, op.message = "cancelled", "cancelled before it started"
                return self._save(op)
            op.status = "running"
            self._save(op)
            ctx = OperationContext(self, op)
            try:
                result = handler(ctx)
                op = self.repo.operations.require(operation_id)
                if op.status == "awaiting_input":                     # plan-30: an interaction was opened; the handler returned early
                    return op
                if op.cancel_requested:
                    op.status, op.message, op.result = "cancelled", "cancelled while running", result
                else:
                    op.status, op.progress, op.result = "succeeded", 1.0, result
            except AgentXError as e:
                op = self.repo.operations.require(operation_id)
                op.status, op.error = "failed", e.as_error()
            except (GovernanceError, ValueError, KeyError) as e:
                op = self.repo.operations.require(operation_id)
                op.status, op.error = "failed", AgentXError("bad_request", str(e) or type(e).__name__).as_error()
            except Exception as e:  # noqa: BLE001 — the operation records it; the service keeps running
                op = self.repo.operations.require(operation_id)
                op.status, op.error = "failed", AgentXError("internal", f"{type(e).__name__}: {e}"[:500]).as_error()
            return self._save(op)

    def join(self, operation_id: str, timeout: float = 30.0) -> Operation:
        t = self._threads.get(operation_id)
        if t is not None:
            t.join(timeout)
        return self.get(operation_id)

    # [block plan-30] research-05 R5: human input and the decided-elsewhere refresh
    def submit_input(self, operation_id: str, interaction_id: str, values: dict[str, Any], submitted_by: Optional[str],
                     resume: Callable[[Operation, dict[str, Any], str], dict[str, Any]]) -> Operation:
        op = self.get(operation_id)
        if op.status != "awaiting_input" or not op.interaction:
            raise AgentXError("conflict", f"operation {operation_id} is {op.status}, not awaiting input", details={"status": op.status})
        if interaction_id != op.interaction.get("interaction_id"):
            raise AgentXError("conflict", f"interaction {interaction_id!r} is not the open one", details={"open": op.interaction.get("interaction_id")})
        if not submitted_by:
            raise AgentXError("forbidden", "submitted_by is required: a decision is made by a named person")
        result = resume(op, values, submitted_by)                    # raises AgentXError on refusal; the operation stays awaiting input
        op = self.repo.operations.require(operation_id)
        op.status, op.progress, op.result, op.interaction = "succeeded", 1.0, result, None
        op.message = f"decided by {submitted_by}"
        return self._save(op)

    def refresh(self, op: Operation, check: Optional[Callable[[Operation], Optional[dict[str, Any]]]]) -> Operation:
        """An open interaction whose subject was decided elsewhere (the console) completes on the next poll."""
        if check is None or op.status != "awaiting_input":
            return op
        done = check(op)
        if done is None:
            return op
        op.status, op.progress, op.result, op.interaction, op.message = "succeeded", 1.0, done, None, "decided elsewhere"
        return self._save(op)
    # [/block plan-30]

    # ---- cancel ------------------------------------------------------------------------------------------------------

    def cancel(self, operation_id: str) -> Operation:
        op = self.get(operation_id)
        if op.status in TERMINAL:
            raise AgentXError("conflict", f"operation {operation_id} is already {op.status}", details={"reason": "not_cancellable", "status": op.status})
        op.cancel_requested = True
        if op.status in ("accepted", "awaiting_input"):
            op.status, op.message = "cancelled", "cancelled"
        else:
            op.message = "cancellation requested; the capability stops at its next step"
        return self._save(op)
# [/block plan-29]
