"""plan-36 — NEXOS IT MVP validation: domain-level vs instance-level corrections (§9, §23, §24; Inv. 3, 6, 9).

An instance correcting knowledge it inherits from its domain is an override — a new nugget at the instance that SPECIALIZES
the domain version. It must not supersede the domain version, must not publish to the domain graph, and must not reach
sibling instances. A correction at the knowledge's own scope stays a revision (the next version of the same nugget).
"""
from __future__ import annotations

from ka.model import Scope
from ka.tests.conftest import A, B, D, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus, RelationshipType, ScopeType

RULE = "Refunds above $500 require manager approval."


def _domain_rule_realized(ka):
    v1 = approve_all(ka, ingest_policy(ka, D, RULE))[0]
    ka.adapter.realize(D, A)
    ka.adapter.realize(D, B)
    dom = ka.adapter.list_elements(D)[0]
    return v1, dom, ka.adapter.list_elements(A)[0], ka.adapter.list_elements(B)[0]


def _value(ka, el):
    return ka.adapter.get_graph_element(el.graph_id, el.element_id).props["value"]


def test_P1_an_instance_correction_of_domain_knowledge_is_an_override_not_a_revision(ka):
    v1, dom, a_el, _ = _domain_rule_realized(ka)
    c = ka.corrections.submit(graph_id=a_el.graph_id, element_id=a_el.element_id, what_is_incorrect="threshold",
                              correct_value="Our store requires manager approval for refunds above $750.", reason="local rule", by="ops")
    cand = ka.repo.require_version(c.candidate_ref)
    assert c.resolved_lineage == [v1.ref] and c.override_of == v1.ref
    assert cand.canonical_id != v1.canonical_id and cand.scope == A and cand.correction_refs == [c.id]
    assert any(r.from_ref == cand.ref and r.to_ref == v1.ref and r.relationship_type == RelationshipType.SPECIALIZES
               for r in ka.repo.relationships_for(cand.ref))


def test_P2_approving_an_instance_override_leaves_the_domain_and_siblings_untouched(ka):
    v1, dom, a_el, b_el = _domain_rule_realized(ka)
    c = ka.corrections.submit(graph_id=a_el.graph_id, element_id=a_el.element_id, what_is_incorrect="threshold",
                              correct_value="Our store requires manager approval for refunds above $750.", reason="local rule", by="ops")
    ka.governance.decide(c.candidate_ref, DecisionOutcome.APPROVE, by="reviewer", reason="confirmed for merchant-a")
    stored = ka.repo.require_version(v1.ref)
    assert stored.status == NuggetStatus.ACTIVE and stored.superseded_by is None
    assert ka.repo.active_version(v1.canonical_id).ref == v1.ref
    assert _value(ka, dom) == "$500" and _value(ka, b_el) == "$500"          # domain and sibling keep the domain rule
    assert _value(ka, a_el) == "$750"                                        # the instance's realized copy carries the override
    lineage = {(x["nugget_id"], x["version"]) for x in ka.adapter.get_graph_element(a_el.graph_id, a_el.element_id).lineage()}
    assert (v1.canonical_id, 1) in lineage and (ka.repo.require_version(c.candidate_ref).canonical_id, 1) in lineage
    assert [d.element_id for d in ka.lineage.where_used(v1.ref)] == [dom.element_id]   # domain dependency not retired


def test_P3_a_domain_correction_is_a_revision_and_preserves_an_existing_instance_override(ka):
    v1, dom, a_el, b_el = _domain_rule_realized(ka)
    o = ka.corrections.submit(graph_id=a_el.graph_id, element_id=a_el.element_id, what_is_incorrect="threshold",
                              correct_value="Our store requires manager approval for refunds above $750.", reason="local", by="ops")
    ka.governance.decide(o.candidate_ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    c = ka.corrections.submit(graph_id=dom.graph_id, element_id=dom.element_id, what_is_incorrect="threshold",
                              correct_value="Refunds above $600 require manager approval.", reason="policy update", by="ops")
    cand = ka.repo.require_version(c.candidate_ref)
    assert c.override_of is None and cand.canonical_id == v1.canonical_id and cand.version == 2 and cand.scope == D
    ka.governance.decide(c.candidate_ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    prop = next(p for p in ka.repo.proposals.all() if p.knowledge_change_ids == [cand.ref])
    assert prop.requires_approval and (A.scope_id, a_el.element_id) not in {(x.graph_id, x.element_id) for x in prop.changes}
    ka.graph_change.approve(prop.id, by="architect", reason="override reviewed")       # an override below → a person approves (§21)
    ka.graph_change.apply(prop.id, by="architect")
    assert ka.repo.require_version(v1.ref).status == NuggetStatus.SUPERSEDED and ka.repo.require_version(v1.ref).superseded_by == cand.ref
    assert _value(ka, dom) == "$600" and _value(ka, b_el) == "$600"          # inherited sibling follows the domain
    assert _value(ka, a_el) == "$750"                                        # the override survives (Inv. 9)


def test_P4_the_override_correction_is_traceable_from_the_instance_element(ka):
    v1, _, a_el, _ = _domain_rule_realized(ka)
    c = ka.corrections.submit(graph_id=a_el.graph_id, element_id=a_el.element_id, what_is_incorrect="threshold",
                              correct_value="Our store requires manager approval for refunds above $750.", reason="local", by="ops")
    ka.governance.decide(c.candidate_ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    chain = ka.lineage.explain_element(a_el.graph_id, a_el.element_id)["knowledge_lineage"]
    assert any(link["ref"] == c.candidate_ref and link["corrections"][0]["id"] == c.id for link in chain)
    audit = [r for r in ka.repo.audit() if r.what == "correction.submitted" and c.id in r.affected_objects]
    assert audit and audit[0].after == {"level": "override", "override_of": v1.ref}


def test_N1_a_user_choosing_the_domain_scope_from_an_instance_element_gets_a_revision(ka):
    v1, _, a_el, _ = _domain_rule_realized(ka)
    c = ka.corrections.submit(graph_id=a_el.graph_id, element_id=a_el.element_id, what_is_incorrect="threshold",
                              correct_value="Refunds above $750 require manager approval.", reason="everyone", by="ops",
                              user_scope=Scope(scope_type=ScopeType.DOMAIN, scope_id=D.scope_id))
    cand = ka.repo.require_version(c.candidate_ref)
    assert c.suggested_scope == D and c.override_of is None and cand.canonical_id == v1.canonical_id and cand.version == 2


def test_N2_a_narrower_scope_version_never_publishes_to_the_broader_scope_element(ka):
    """Defence in depth for any path that revises domain knowledge at an instance scope (`propose_revision(scope=…)`)."""
    v1, dom, a_el, b_el = _domain_rule_realized(ka)
    rev = ka.governance.propose_revision(v1.canonical_id, statement="Refunds above $900 require manager approval.", by="ops",
                                         reason="instance-scoped revision", scope=A)
    ka.governance.decide(rev.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    assert _value(ka, dom) == "$500" and _value(ka, b_el) == "$500"
    report = ka.impact.analyze(ka.repo.require_version(rev.ref))
    assert all(a.action == "review only" for a in report.affected if a.element.scope == D)
