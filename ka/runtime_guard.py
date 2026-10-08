"""§43 Runtime Guardrail (Invariant 1).

The Enterprise Console answers from the Graph. If the graph cannot answer, the runtime calls
`graph_gap_detected(...)` which records a Knowledge Acquisition Request (and optionally a Research
Mission) so the GRAPH improves for the next question. Nothing here returns knowledge to the caller:
`RuntimeKnowledgeAccessError` is raised if a runtime path tries to read nuggets/sources through this door.
"""
from __future__ import annotations

from dataclasses import dataclass

from ka.events import EventBus
from ka.model import KnowledgeAcquisitionRequest, Scope
from ka.repository import Repository
from ka.research import ResearchOrchestrator

GRAPH_GAP_DETECTED = "GRAPH GAP DETECTED"


class RuntimeKnowledgeAccessError(PermissionError):
    """Raised when normal runtime answering tries to retrieve raw Knowledge Acquisition content."""


@dataclass
class GapOutcome:
    signal: str
    request_id: str
    mission_id: str | None


class RuntimeGuard:
    def __init__(self, repo: Repository, bus: EventBus, research: ResearchOrchestrator | None = None):
        self.repo, self.bus, self.research = repo, bus, research

    def graph_gap_detected(self, *, scope: Scope, question: str, gap_description: str, requested_by: str = "runtime",
                           open_mission: bool = False) -> GapOutcome:
        req = KnowledgeAcquisitionRequest(scope=scope, question=question, gap_description=gap_description, requested_by=requested_by)
        mission_id = None
        if open_mission and self.research is not None:
            m = self.research.create_mission(scope=scope, objective=f"Close graph gap: {gap_description}", by=requested_by,
                                             questions=[question], trigger="graph_gap")
            mission_id = m.mission_id
            req.mission_id = mission_id
        self.repo.requests.put(req)
        self.bus.emit("graph.gap.detected", request_id=req.id, scope=scope.key(), mission_id=mission_id or "")
        return GapOutcome(GRAPH_GAP_DETECTED, req.id, mission_id)

    def retrieve_for_answer(self, *_, **__):
        """The door that stays shut. Explicit Research/Discovery mode uses ka.search directly and says so."""
        raise RuntimeKnowledgeAccessError(
            "Normal runtime answering must navigate the Graph; Knowledge Acquisition retrieval is not a fallback (§43, Invariant 1)")

    def open_requests(self) -> list[KnowledgeAcquisitionRequest]:
        return self.repo.requests.where(lambda r: r.status == "OPEN")
