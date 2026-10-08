"""plan-01 Phase 4 — Enterprise Console Corrections (§3.3, §23, §24): knowledge first, graph second."""
from __future__ import annotations

from ka.model import Scope
from ka.tests.conftest import A, D, approve_all, ingest_policy
from ka.vocab import AcquisitionChannel, CorrectionStatus, DecisionOutcome, NuggetStatus, ScopeType


def test_P1_correct_this_resolves_lineage_and_creates_a_candidate_revision(ka):
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    el = ka.adapter.list_elements(D)[0]
    before = el.props["value"]
    c = ka.corrections.submit(graph_id=el.graph_id, element_id=el.element_id, what_is_incorrect="Refund approval threshold",
                              correct_value="Refunds above $750 require manager approval.", reason="Policy update", by="ops")
    assert c.status == CorrectionStatus.GOVERNED and c.resolved_lineage == [v1.ref]
    cand = ka.repo.require_version(c.candidate_ref)
    assert cand.canonical_id == v1.canonical_id and cand.version == 2 and cand.status == NuggetStatus.PENDING_REVIEW
    assert cand.channel == AcquisitionChannel.FEEDBACK and cand.correction_refs == [c.id]
    assert ka.adapter.list_elements(D)[0].props["value"] == before      # graph NOT edited by the correction
    assert any(e["name"] == "correction.submitted" for e in ka.repo.events())


def test_P2_approving_the_correction_changes_the_graph_through_a_proposal(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    el = ka.adapter.list_elements(D)[0]
    c = ka.corrections.submit(graph_id=el.graph_id, element_id=el.element_id, what_is_incorrect="threshold",
                              correct_value="Refunds above $750 require manager approval.", reason="update", by="ops")
    ka.governance.decide(c.candidate_ref, DecisionOutcome.APPROVE, by="reviewer", reason="confirmed")
    el = ka.adapter.list_elements(D)[0]
    assert el.props["value"] == "$750" and el.lineage()[0]["version"] == 2
    assert ka.lineage.explain_element(el.graph_id, el.element_id)["knowledge_lineage"][0]["corrections"][0]["id"] == c.id


def test_P3_scope_is_suggested_at_the_lowest_valid_level_and_user_can_override(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    ka.adapter.realize(D, A)
    el = [e for e in ka.adapter.list_elements(A)][0]
    c = ka.corrections.submit(graph_id=el.graph_id, element_id=el.element_id, what_is_incorrect="threshold",
                              correct_value="Our store requires manager approval for refunds above $750.", reason="local rule", by="ops")
    assert c.suggested_scope.scope_type == ScopeType.INSTANCE and c.suggested_scope.scope_id == "merchant-a"
    c2 = ka.corrections.submit(graph_id=el.graph_id, element_id=el.element_id, what_is_incorrect="threshold",
                               correct_value="Refunds above $750 require manager approval.", reason="everyone", by="ops",
                               user_scope=Scope(scope_type=ScopeType.DOMAIN, scope_id="merchant-acquiring"))
    assert c2.suggested_scope.scope_type == ScopeType.DOMAIN and "approval required" in c2.scope_rationale


def test_P4_correction_evidence_becomes_sources_and_evidence(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    el = ka.adapter.list_elements(D)[0]
    c = ka.corrections.submit(graph_id=el.graph_id, element_id=el.element_id, what_is_incorrect="threshold",
                              correct_value="Refunds above $750 require manager approval.", reason="memo", by="ops",
                              note="See finance memo.", upload=("memo.md", b"# Memo\nRefunds above $750 require manager approval."))
    assert len(c.source_refs) == 2 and len(c.evidence_refs) == 2
    assert {ka.repo.sources.get(s).source_type.value for s in c.source_refs} == {"correction", "markdown"}


def test_P5_a_human_correction_is_never_auto_resolved_by_authority(ka):
    from ka.vocab import AuthorityType
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval.", authority=AuthorityType.REGULATION))
    el = ka.adapter.list_elements(D)[0]
    c = ka.corrections.submit(graph_id=el.graph_id, element_id=el.element_id, what_is_incorrect="threshold",
                              correct_value="Refunds above $750 require manager approval.", reason="x", by="ops")
    assert ka.repo.require_version(c.candidate_ref).status == NuggetStatus.PENDING_REVIEW
    assert c in ka.corrections.pending(D)


def test_N1_the_runtime_cannot_pull_knowledge_as_an_answer_fallback(ka):
    import pytest
    from ka.runtime_guard import GRAPH_GAP_DETECTED, RuntimeKnowledgeAccessError
    with pytest.raises(RuntimeKnowledgeAccessError):
        ka.runtime_guard.retrieve_for_answer("what approval for $750 refund?")
    out = ka.runtime_guard.graph_gap_detected(scope=A, question="What approval is required for a $750 refund?",
                                              gap_description="no refund approval rule in Merchant A graph", open_mission=True)
    assert out.signal == GRAPH_GAP_DETECTED and out.mission_id and ka.repo.requests.require(out.request_id).mission_id == out.mission_id
    assert ka.repo.missions.require(out.mission_id).trigger == "graph_gap"
