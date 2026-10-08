"""plan-09 (research-01 R11 KA half, R15, R16 benchmark) — the gap request contract, events as an outbox, the store benchmark.
P1 characterises the PROTECTED runtime guard BEFORE the change (committed on its own, green against the unchanged file)."""
from __future__ import annotations

import pytest

from ka.runtime_guard import GRAPH_GAP_DETECTED, RuntimeKnowledgeAccessError
from ka.tests.conftest import A, D


def test_P1_characterization_every_gap_is_a_new_open_request_and_the_door_is_shut(ka):
    """Pre-change behaviour at the seam: no dedupe, status OPEN, mission trigger graph_gap, retrieval raises."""
    g = ka.runtime_guard
    a = g.graph_gap_detected(scope=A, question="What approval is required for a $750 refund?", gap_description="no rule")
    b = g.graph_gap_detected(scope=A, question="What approval is required for a $750 refund?", gap_description="no rule")
    assert a.signal == b.signal == GRAPH_GAP_DETECTED and a.request_id != b.request_id
    assert {r.status for r in ka.repo.requests.all()} == {"OPEN"} and len(g.open_requests()) == 2
    c = g.graph_gap_detected(scope=D, question="Who approves chargebacks?", gap_description="no rule", open_mission=True)
    assert c.mission_id and ka.repo.missions.require(c.mission_id).trigger == "graph_gap"
    assert ka.repo.requests.require(c.request_id).mission_id == c.mission_id
    with pytest.raises(RuntimeKnowledgeAccessError):
        g.retrieve_for_answer("what approval for $750 refund?")
    assert any(e["name"] == "graph.gap.detected" and e["request_id"] == a.request_id for e in ka.repo.events())
