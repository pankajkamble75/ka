"""plan-01 Phase 6 — Intelligent Propagation (§8, §9, §21, §25, §26): overrides survive domain changes."""
from __future__ import annotations

from ka.tests.conftest import A, B, C, D, approve_all, ingest_policy
from ka.vocab import InheritanceState, NuggetStatus, ProposalStatus, RelationshipType


def _domain_rule_realized(ka):
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    for inst in (A, B, C):
        ka.adapter.realize(D, inst)
    return v


def test_P1_domain_change_propagates_to_inherited_instances_and_preserves_overrides(ka_manual):
    ka = ka_manual
    v1 = _domain_rule_realized(ka)
    p = ka.repo.proposals.all()[0]; ka.graph_change.approve(p.id, by="g"); ka.graph_change.apply(p.id, by="g")
    for inst in (A, B, C):
        ka.adapter.realize(D, inst)
    # Merchant C overrides to $750 via its own governed nugget.
    c = ingest_policy(ka, C, "Merchant C refunds above $750 require manager approval.")[0]
    approve_all(ka, [c])
    pc = [x for x in ka.repo.proposals.all() if c.ref in x.knowledge_change_ids][0]
    ka.graph_change.approve(pc.id, by="g"); ka.graph_change.apply(pc.id, by="g")
    assert ka.adapter.calculate_inheritance(C)["merchant-acquiring/" + ka.adapter.list_elements(D)[0].element_id] == InheritanceState.OVERRIDDEN

    # Domain moves to $1,500.
    v2 = ka.governance.propose_revision(v1.canonical_id, statement="Refunds above $1,500 require manager approval.", by="u", reason="2027")
    approve_all(ka, [v2])
    p2 = [x for x in ka.repo.proposals.all() if v2.ref in x.knowledge_change_ids][0]
    effects = {e.scope.scope_id: (e.inheritance_state, e.action) for e in p2.inheritance_effects}
    assert effects["merchant-a"] == (InheritanceState.INHERITED, "proposed update")
    assert effects["merchant-b"] == (InheritanceState.INHERITED, "proposed update")
    assert effects["merchant-c"] == (InheritanceState.OVERRIDDEN, "review only")
    assert p2.requires_approval and p2.status == ProposalStatus.READY and p2.impact_summary["overridden_descendants"] == 1
    ka.graph_change.approve(p2.id, by="g"); ka.graph_change.apply(p2.id, by="g")
    rid = ka.adapter.list_elements(D)[0].element_id
    assert ka.adapter.get_graph_element("merchant-a", f"merchant-acquiring/{rid}").props["value"] == "$1,500"
    assert ka.adapter.get_graph_element("merchant-b", f"merchant-acquiring/{rid}").props["value"] == "$1,500"
    assert ka.adapter.get_graph_element("merchant-c", f"merchant-acquiring/{rid}").props["value"] == "$750"     # override preserved
    # lineage: A and B now depend on v2; C still on its own nugget
    assert any(d.graph_id == "merchant-a" for d in ka.lineage.where_used(v2.ref))
    assert not any(d.graph_id == "merchant-c" for d in ka.lineage.where_used(v2.ref))


def test_P2_instance_override_updates_the_realized_copy_in_place(ka):
    _domain_rule_realized(ka)
    c = approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval."))[0]
    els = ka.adapter.list_elements(A)
    assert len(els) == 1 and els[0].props["value"] == "$1,000"
    assert [ln["nugget_id"] for ln in els[0].lineage()] == ["KN-001", c.canonical_id]
    assert ka.adapter.calculate_inheritance(A)[els[0].element_id] == InheritanceState.OVERRIDDEN
    assert ka.adapter.list_elements(B)[0].props["value"] == "$500"


def test_P3_inheritance_states_cover_extended_and_removed(ka):
    from ka.graph_adapter import GraphElement
    _domain_rule_realized(ka)
    rid = ka.adapter.list_elements(D)[0].element_id
    ka.adapter.put_element(GraphElement(graph_id="merchant-b", element_id="r.local_only", kind="rule", name="Local", scope=B))
    del ka.adapter.graphs["merchant-c"][f"merchant-acquiring/{rid}"]
    assert ka.adapter.calculate_inheritance(B)["r.local_only"] == InheritanceState.LOCALLY_EXTENDED
    assert ka.adapter.calculate_inheritance(C)[f"merchant-acquiring/{rid}"] == InheritanceState.LOCALLY_REMOVED


def test_P4_repeated_instance_knowledge_is_proposed_for_promotion_never_promoted_automatically(ka):
    for inst, name in ((A, "A"), (B, "B"), (C, "C")):
        approve_all(ka, ingest_policy(ka, inst, "Weekend refunds require two approvals."))
    props = ka.promotion.detect(D)
    assert len(props) == 1 and sorted(props[0].instance_ids) == ["merchant-a", "merchant-b", "merchant-c"] and props[0].status == "PROPOSED"
    assert ka.repo.active_nuggets(D) == []                      # nothing promoted yet
    assert ka.promotion.detect(D) == props                      # idempotent
    p = ka.promotion.decide(props[0].id, approve=True, by="governance-lead", reason="pattern confirmed")
    cand = ka.repo.require_version(p.candidate_ref)
    assert cand.scope.key() == D.key() and cand.status == NuggetStatus.PENDING_REVIEW
    assert len([r for r in ka.repo.relationships_for(cand.ref) if r.relationship_type == RelationshipType.MERGES]) == 3
    approve_all(ka, [cand])
    assert ka.repo.active_nuggets(D)[0].statement == "Weekend refunds require two approvals."


def test_N1_promotion_needs_the_configured_minimum_of_instances(ka):
    approve_all(ka, ingest_policy(ka, A, "Weekend refunds require two approvals."))
    approve_all(ka, ingest_policy(ka, B, "Weekend refunds require two approvals."))
    assert ka.promotion.detect(D) == []


def test_P5_instance_dashboard_distinguishes_inherited_specific_overrides(ka):
    _domain_rule_realized(ka)
    approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval."))
    approve_all(ka, ingest_policy(ka, A, "Merchant A must close on Sundays."))
    dash = ka.instance_dashboard(A)
    assert dash["counts"]["overrides"] == 1 and dash["counts"]["instance_specific"] == 1 and dash["counts"]["inherited"] == 0
    dash_b = ka.instance_dashboard(B)
    assert dash_b["counts"]["inherited"] == 1
