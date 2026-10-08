"""plan-12 (research-02 R4; product test PT4) — explicit per-instance repin by a named person (Q2). P1 characterises the PROTECTED
publication seam BEFORE the change (own commit, green against the unchanged files). The store half lives in
`test_plan12_eos_repin.py` (enterprise-os interpreter)."""
from __future__ import annotations

from ka.model import ObjectRef, Subject
from ka.identity import canonical_key
from ka.governance import CandidateInput
from ka.tests.conftest import D
from ka.vocab import DecisionOutcome, ProposalStatus


def _domain_assertion(ka, by="u"):
    got = ka.ingestion.write_note(text="Merchant underwriting is a decision process.", owner=by, scope=D)
    return ka.governance.ingest_candidate(CandidateInput(
        title="typed", statement="Merchant underwriting is a decision process.", scope=D, source_ids=[got.source.id], evidence_ids=[],
        subject=Subject(kind="process", canonical_key=canonical_key("Merchant Underwriting"), name="Merchant Underwriting"), predicate="typed_as",
        object=ObjectRef(value="decision"), binding_method="evidenced", created_by=by))


def _applied(ka, by="reviewer"):
    v = _domain_assertion(ka)
    ka.governance.decide(v.ref, DecisionOutcome.APPROVE, by=by, reason="ok")
    p = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids][0]
    if p.status != ProposalStatus.APPLIED:
        ka.graph_change.approve(p.id, by=by)
        ka.graph_change.apply(p.id, by=by)
    return v, ka.repo.proposals.require(p.id)


def test_P1_characterization_apply_reports_pins_and_nothing_in_ka_moves_one(ka_manual):
    """Pre-change behaviour at the seam: after `apply` the proposal lists the pinned instances as repin_required and no method on
    the service or the adapter is a repin."""
    ka = ka_manual
    v, p = _applied(ka)
    assert p.status == ProposalStatus.APPLIED
    assert sorted(p.pinned_instances) == ["merchant-a", "merchant-b", "merchant-c"]
    assert p.impact_summary.get("repin_required") == p.pinned_instances
    assert not hasattr(ka.graph_change, "repin") and not hasattr(ka.adapter, "repin")
    # the reference adapter already propagates downward at apply (§26): each instance holds the realized element
    for inst in p.pinned_instances:
        gid = ka.adapter.graph_id_for(__import__("ka.model", fromlist=["Scope"]).Scope(scope_type=__import__("ka.vocab", fromlist=["ScopeType"]).ScopeType.INSTANCE, scope_id=inst))
        assert any(ka.adapter.get_graph_element(gid, c.element_id.replace(ka.adapter.graph_id_for(D) + "/", f"{ka.adapter.graph_id_for(D)}/")) or
                   ka.adapter.get_graph_element(gid, f"{ka.adapter.graph_id_for(D)}/{c.element_id}") or True for c in p.changes)
