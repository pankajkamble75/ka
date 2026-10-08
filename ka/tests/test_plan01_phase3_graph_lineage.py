"""plan-01 Phase 3 — Graph Lineage (§15, §19–§22, §39, §40): every affected graph element can explain itself."""
from __future__ import annotations

import pytest

from ka.graph_adapter import LINEAGE_KEY
from ka.model import ElementChange
from ka.tests.conftest import D, approve_all, ingest_policy
from ka.vocab import GraphElementKind, ProposalStatus


def test_P1_activation_compiles_a_rule_into_the_domain_graph_with_lineage(ka):
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    els = ka.adapter.list_elements(D)
    assert len(els) == 1 and els[0].kind == GraphElementKind.RULE and els[0].props["value"] == "$500"
    assert els[0].lineage() == [{"nugget_id": v.canonical_id, "version": 1, "governance_decision_id": v.governance_decision_id,
                                 "graph_change_id": ka.repo.proposals.all()[0].id}]


def test_P2_graph_asks_why_and_knowledge_asks_where(ka):
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    el = ka.adapter.list_elements(D)[0]
    why = ka.lineage.explain_element(el.graph_id, el.element_id)
    assert why["explained"] and why["knowledge_lineage"][0]["ref"] == v.ref and why["knowledge_lineage"][0]["sources"][0]["title"] == "Policy"
    where = ka.lineage.where_used(v.ref)
    assert [(d.graph_id, d.element_id) for d in where] == [(el.graph_id, el.element_id)]
    assert ka.repo.require_version(v.ref).derived_graph_refs[0].element_id == el.element_id


def test_P3_a_revision_proposes_an_update_to_the_dependent_element_not_a_new_one(ka):
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    v2 = ka.governance.propose_revision(v1.canonical_id, statement="Refunds above $1,000 require manager approval.", by="u", reason="2027")
    approve_all(ka, [v2])
    els = ka.adapter.list_elements(D)
    assert len(els) == 1 and els[0].props["value"] == "$1,000"
    assert [ln["version"] for ln in els[0].lineage()] == [2]
    assert ka.lineage.where_used(v1.ref) == [] and len(ka.lineage.where_used(v2.ref)) == 1


def test_P4_proposal_carries_before_after_impact_and_validation(ka):
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    p = ka.repo.proposals.all()[0]
    assert p.status == ProposalStatus.APPLIED and p.knowledge_change_ids == [v.ref]
    assert p.before_state and p.proposed_after_state and all(r["ok"] for r in p.validation_results)
    assert p.impact_summary["is_new_knowledge"] is True and p.applied_at


def test_N1_a_graph_change_without_knowledge_lineage_is_refused(ka):
    from ka.graph_adapter import GraphValidationError
    bad = ElementChange(graph_id="merchant-acquiring", element_id="r.rogue", element_kind=GraphElementKind.RULE, operation="create",
                        after={"name": "rogue", "props": {"value": "1"}})
    results = ka.adapter.validate_change([bad])
    assert results[0]["ok"] is False and "Invariant 2" in results[0]["detail"]
    with pytest.raises(GraphValidationError):
        ka.adapter.apply_change([bad])


def test_N2_a_proposal_for_ungoverned_knowledge_fails_validation(ka_manual):
    ka = ka_manual
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]   # PENDING_REVIEW, not governed
    p = ka.graph_change.propose_for(cand)
    assert p.status == ProposalStatus.FAILED and any("not governed" in r["detail"] for r in p.validation_results)


def test_P5_manual_approval_path_proposed_ready_approved_applied(ka_manual):
    ka = ka_manual
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    p = ka.repo.proposals.all()[0]
    assert p.status == ProposalStatus.READY and ka.adapter.list_elements(D) == []    # graph untouched until applied
    ka.graph_change.approve(p.id, by="graph-owner")
    ex = ka.graph_change.apply(p.id, by="graph-owner")
    assert ex.status == "APPLIED" and ka.adapter.list_elements(D)[0].lineage()[0]["nugget_id"] == v.canonical_id


def test_P6_rollback_restores_the_element_and_lineage(ka_manual):
    ka = ka_manual
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    p1 = ka.repo.proposals.all()[0]
    ka.graph_change.approve(p1.id, by="g"); ka.graph_change.apply(p1.id, by="g")
    v2 = ka.governance.propose_revision(v1.canonical_id, statement="Refunds above $1,000 require manager approval.", by="u", reason="x")
    approve_all(ka, [v2])
    p2 = [p for p in ka.repo.proposals.all() if v2.ref in p.knowledge_change_ids][0]
    ka.graph_change.approve(p2.id, by="g"); ex = ka.graph_change.apply(p2.id, by="g")
    assert ka.adapter.list_elements(D)[0].props["value"] == "$1,000"
    ka.graph_change.rollback(ex.id, by="g", reason="bad threshold")
    el = ka.adapter.list_elements(D)[0]
    assert el.props["value"] == "$500" and el.lineage()[0]["version"] == 1
    assert ka.repo.proposals.require(p2.id).status == ProposalStatus.ROLLED_BACK
    assert [d.nugget_ref for d in ka.lineage.where_used(v1.ref)] == [v1.ref]


def test_P7_element_metadata_references_the_nugget_and_does_not_duplicate_it(ka):
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    el = ka.adapter.list_elements(D)[0]
    entry = el.props[LINEAGE_KEY][0]
    assert set(entry) == {"nugget_id", "version", "governance_decision_id", "graph_change_id"}
    assert "sources" not in entry and v.statement == el.description     # the statement is the compiled value, the nugget is referenced


def test_P8_events_carry_ids_not_content(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    names = [e["name"] for e in ka.repo.events()]
    for n in ("source.ingested", "knowledge.candidate.created", "knowledge.approved", "graph.impact.detected", "graph.change.proposed",
              "graph.change.approved", "graph.change.applied"):
        assert n in names
    assert all(len(str(v)) <= 200 for e in ka.repo.events() for v in e.values())
