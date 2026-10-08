"""§43 Runtime Guardrail (Invariant 1).

The Enterprise Console answers from the Graph. If the graph cannot answer, the runtime calls
`graph_gap_detected(...)` which records a Knowledge Acquisition Request (and optionally a Research
Mission) so the GRAPH improves for the next question. Nothing here returns knowledge to the caller:
`RuntimeKnowledgeAccessError` is raised if a runtime path tries to read nuggets/sources through this door.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ka.events import EventBus
from ka.model import KnowledgeAcquisitionRequest, Scope
from ka.repository import Repository
from ka.research import ResearchOrchestrator
from ka.timeutil import now_iso

GRAPH_GAP_DETECTED = "GRAPH GAP DETECTED"
# [block plan-09] research-01 R11 (KA half): intents, lifecycle and the dedupe key
INTENTS = ("found_new", "grow_existing", "answer", "other")
LIVE = ("OPEN", "IN_RESEARCH")


def dedupe_key(scope: Scope, question: str, correlation_id: str | None) -> str:
    if correlation_id:
        return correlation_id
    norm = re.sub(r"\s+", " ", question.strip().lower())
    return hashlib.sha1(f"{scope.key()}|{norm}".encode()).hexdigest()[:16]
# [/block plan-09]


class RuntimeKnowledgeAccessError(PermissionError):
    """Raised when normal runtime answering tries to retrieve raw Knowledge Acquisition content."""


@dataclass
class GapOutcome:
    signal: str
    request_id: str
    mission_id: str | None
    deduplicated: bool = False      # plan-09


class RuntimeGuard:
    def __init__(self, repo: Repository, bus: EventBus, research: ResearchOrchestrator | None = None):
        self.repo, self.bus, self.research = repo, bus, research

    def graph_gap_detected(self, *, scope: Scope, question: str, gap_description: str, requested_by: str = "runtime",
                           open_mission: bool = False, principal: str | None = None, intent: str = "answer",
                           missing_semantics: list[str] | None = None, correlation_id: str | None = None) -> GapOutcome:
        # [block plan-09] the same gap raised while a request for it is live returns that request (idempotent for the caller)
        if intent not in INTENTS:
            raise ValueError(f"unknown intent {intent!r}; one of {', '.join(INTENTS)}")
        key = dedupe_key(scope, question, correlation_id)
        live = self.repo.requests.where(lambda r: r.dedupe_key == key and r.status in LIVE)
        if live:
            req = live[0]
            req.deduplicated_count += 1
            req.updated_at = now_iso()
            self.repo.requests.put(req)
            return GapOutcome(GRAPH_GAP_DETECTED, req.id, req.mission_id, deduplicated=True)
        req = KnowledgeAcquisitionRequest(scope=scope, question=question, gap_description=gap_description, requested_by=requested_by,
                                          principal=principal or requested_by, intent=intent, missing_semantics=list(missing_semantics or []),
                                          correlation_id=correlation_id, dedupe_key=key)
        # [/block plan-09]
        mission_id = None
        if open_mission and self.research is not None:
            m = self.research.create_mission(scope=scope, objective=f"Close graph gap: {gap_description}", by=requested_by,
                                             questions=[question], trigger="graph_gap")
            mission_id = m.mission_id
            req.mission_id = mission_id
            req.status = "IN_RESEARCH"
        self.repo.requests.put(req)
        self.bus.emit("graph.gap.detected", request_id=req.id, scope=scope.key(), mission_id=mission_id or "")
        return GapOutcome(GRAPH_GAP_DETECTED, req.id, mission_id)

    # ---- lifecycle (plan-09; the door above is untouched) ------------------------------------------------

    def get(self, request_id: str) -> KnowledgeAcquisitionRequest:
        return self.repo.requests.require(request_id)

    def requests(self, status: str | None = None) -> list[KnowledgeAcquisitionRequest]:
        rs = self.repo.requests.all() if status is None else self.repo.requests.where(lambda r: r.status == status)
        return sorted(rs, key=lambda r: r.created_at)

    def cancel(self, request_id: str, *, by: str, reason: str = "") -> KnowledgeAcquisitionRequest:
        req = self.repo.requests.require(request_id)
        if req.status not in LIVE:
            raise ValueError(f"request {request_id} is {req.status}; only OPEN or IN_RESEARCH can be cancelled")
        req.status, req.cancelled_reason, req.updated_at = "CANCELLED", f"{by}: {reason}" if reason else by, now_iso()
        self.repo.requests.put(req)
        return req

    def fulfil(self, request_id: str, *, refs: list[str]) -> KnowledgeAcquisitionRequest:
        req = self.repo.requests.require(request_id)
        if req.status in LIVE:
            req.status = "FULFILLED"
        req.fulfilled_by = sorted(set(req.fulfilled_by) | set(refs))
        req.updated_at = now_iso()
        self.repo.requests.put(req)
        return req

    def fulfil_from_approval(self, ref: str) -> list[KnowledgeAcquisitionRequest]:
        """A request whose mission produced `ref` is fulfilled when `ref` is approved (wired by the service)."""
        out = []
        for m in self.repo.missions.where(lambda m: ref in m.candidate_refs):
            for req in self.repo.requests.where(lambda r: r.mission_id == m.mission_id and r.status in LIVE):
                out.append(self.fulfil(req.id, refs=[ref]))
        return out

    def retrieve_for_answer(self, *_, **__):
        """The door that stays shut. Explicit Research/Discovery mode uses ka.search directly and says so."""
        raise RuntimeKnowledgeAccessError(
            "Normal runtime answering must navigate the Graph; Knowledge Acquisition retrieval is not a fallback (§43, Invariant 1)")

    def open_requests(self) -> list[KnowledgeAcquisitionRequest]:
        return self.repo.requests.where(lambda r: r.status in LIVE)      # plan-09: IN_RESEARCH is still open work
