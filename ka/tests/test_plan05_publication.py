"""plan-05 (research-01 R1, R2 last clause, R7 KA half) — ChangeOps by canonical identity, publication through the adapter,
idempotency. In-memory adapter cases here; the EOS-path cases are in test_plan05_eos_publication.py (EOS interpreter only).

Characterization cases (P6, P7a, P8) ran green against the pre-plan-05 graph_change code before Phase 2 changed it.
"""
from __future__ import annotations

from ka.governance import CandidateInput
from ka.identity import canonical_key
from ka.model import ObjectRef, Subject
from ka.tests.conftest import D, approve_all, ingest_policy


def _assert(ka, statement, subject_name, predicate, obj=None, kind="process", scope=D, title=None):
    got = ka.ingestion.write_note(text=statement, owner="u", scope=scope)
    return ka.governance.ingest_candidate(CandidateInput(
        title=title or statement[:60], statement=statement, scope=scope, source_ids=[got.source.id], evidence_ids=[],
        subject=Subject(kind=kind, canonical_key=canonical_key(subject_name), name=subject_name), predicate=predicate,
        object=obj, binding_method="evidenced", created_by="u"))


# ---------------------------------------------------------------- Phase 2 characterization (pre-change behaviour)

def test_P6_a_rule_nugget_compiles_to_a_title_slug_id(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    assert [e.element_id for e in ka.adapter.list_elements(D)] == ["r.refunds_above_500_require_manager_approval"]


def test_P7a_two_nuggets_about_one_subject_made_two_elements_before_plan05(ka):
    """Characterization. At commit 60ed811 (pre-change) this asserted TWO elements with slug ids; the before-photo lives there.
    After Phase 2 the same input yields ONE canonical element — asserted here so the suite stays green and the contrast is recorded."""
    a = _assert(ka, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"), title="Underwriting type")
    b = _assert(ka, "Merchant underwriting: evaluates applications.", "Merchant underwriting", "description", ObjectRef(value="evaluates applications"), title="Underwriting purpose")
    approve_all(ka, [a, b])
    ids = sorted(e.element_id for e in ka.adapter.list_elements(D))
    assert ids == ["p.merchant_underwriting"]


def test_P8_apply_registers_a_dependency_per_element_and_rollback_restores_before(ka_manual):
    ka = ka_manual
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    p1 = ka.repo.proposals.all()[0]
    ka.graph_change.approve(p1.id, by="Pankaj Kamble"); ex1 = ka.graph_change.apply(p1.id, by="Pankaj Kamble")
    assert len(ka.lineage.where_used(v1.ref)) == 1 and ex1.status == "APPLIED"
    v2 = ka.governance.propose_revision(v1.canonical_id, statement="Refunds above $1,000 require manager approval.", by="u", reason="x")
    approve_all(ka, [v2])
    p2 = [p for p in ka.repo.proposals.all() if v2.ref in p.knowledge_change_ids][0]
    ka.graph_change.approve(p2.id, by="Pankaj Kamble"); ex2 = ka.graph_change.apply(p2.id, by="Pankaj Kamble")
    assert ka.adapter.list_elements(D)[0].props["value"] == "$1,000"
    ka.graph_change.rollback(ex2.id, by="Pankaj Kamble")
    assert ka.adapter.list_elements(D)[0].props["value"] == "$500" and [d.nugget_ref for d in ka.lineage.where_used(v1.ref)] == [v1.ref]


# ---------------------------------------------------------------- post-change: emission by canonical identity (in-memory)

import pytest  # noqa: E402

from ka import config  # noqa: E402
from ka.graph_adapter import LINEAGE_KEY, PublishRefused  # noqa: E402
from ka.graph_change import element_id_for, idempotency_key_for, to_change_ops  # noqa: E402
from ka.model import ElementChange  # noqa: E402
from ka.vocab import GraphElementKind, ProposalStatus  # noqa: E402


def test_P1_typed_as_compiles_to_a_canonical_node_and_a_second_title_updates_it(ka):
    a = _assert(ka, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"), title="Underwriting type")
    approve_all(ka, [a])
    els = {e.element_id: e for e in ka.adapter.list_elements(D)}
    assert list(els) == ["p.merchant_underwriting"] and els["p.merchant_underwriting"].props["process_type"] == "decision"
    assert els["p.merchant_underwriting"].props[LINEAGE_KEY][0]["nugget_id"] == a.canonical_id
    b = _assert(ka, "Merchant underwriting: evaluates applications.", "Merchant underwriting", "description", ObjectRef(value="evaluates applications"), title="Underwriting purpose")
    approve_all(ka, [b])
    els = {e.element_id: e for e in ka.adapter.list_elements(D)}
    assert list(els) == ["p.merchant_underwriting"] and els["p.merchant_underwriting"].description == "evaluates applications"
    assert {ln["nugget_id"] for ln in els["p.merchant_underwriting"].props[LINEAGE_KEY]} == {a.canonical_id, b.canonical_id}
    p = [p for p in ka.repo.proposals.all() if b.ref in p.knowledge_change_ids][0]
    assert p.ops[0]["op"] == "set_props" and p.ops[0]["id"] == "p.merchant_underwriting"


def test_P7b_two_nuggets_about_one_subject_now_make_one_element(ka):
    test_P1_typed_as_compiles_to_a_canonical_node_and_a_second_title_updates_it(ka)


def test_P2_decomposes_into_makes_a_child_process_and_a_contains_edge(ka):
    v = _assert(ka, "Merchant underwriting decomposes into: Collect application", "Merchant underwriting", "decomposes_into",
                ObjectRef(kind="process", value="Collect application"))
    approve_all(ka, [v])
    ids = sorted(e.element_id for e in ka.adapter.list_elements(D))
    assert ids == ["contains:p.merchant_underwriting->p.merchant_underwriting.collect_application", "p.merchant_underwriting", "p.merchant_underwriting.collect_application"]
    edge = ka.adapter.get_graph_element("merchant-acquiring", ids[0])
    assert edge.kind == GraphElementKind.EDGE and edge.source == "p.merchant_underwriting" and edge.props[LINEAGE_KEY]


def test_P3_performed_by_and_consumes_make_actor_and_entity_nodes_with_edges(ka):
    a = _assert(ka, "Merchant underwriting is performed by: Underwriting team", "Merchant underwriting", "performed_by", ObjectRef(kind="actor", value="Underwriting team"))
    b = _assert(ka, "Merchant underwriting consumes: merchant application", "Merchant underwriting", "consumes", ObjectRef(kind="entity", value="merchant application"))
    approve_all(ka, [a, b])
    ids = {e.element_id for e in ka.adapter.list_elements(D)}
    assert {"ac.underwriting_team", "e.merchant_application", "performed_by:p.merchant_underwriting->ac.underwriting_team",
            "consumes:p.merchant_underwriting->e.merchant_application"} <= ids


def test_P4_the_same_knowledge_proposed_twice_returns_the_live_proposal(ka):
    v = approve_all(ka, [_assert(ka, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"))])[0]
    first = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids]
    again = ka.graph_change.propose_for(v)
    assert len(first) == 1 and again.id == first[0].id and again.idempotency_key == first[0].idempotency_key
    assert len([p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids]) == 1


def test_P5_to_change_ops_renders_the_eos_shape():
    changes = [
        ElementChange(graph_id="d", element_id="p.x", element_kind=GraphElementKind.PROCESS, operation="create", op="add_node",
                      after={"kind": "process", "name": "X", "description": "d", "props": {LINEAGE_KEY: [{"nugget_id": "KN-1", "version": 1}]}}),
        ElementChange(graph_id="d", element_id="p.y", element_kind=GraphElementKind.PROCESS, operation="update", op="set_props", after={"props": {"a": 1}}),
        ElementChange(graph_id="d", element_id="contains:p.x->p.y", element_kind=GraphElementKind.EDGE, operation="create", op="add_edge",
                      edge={"kind": "contains", "source": "p.x", "target": "p.y"}, after={"props": {LINEAGE_KEY: []}}),
    ]
    ops = to_change_ops(changes)
    assert ops[0] == {"op": "add_node", "node": {"id": "p.x", "kind": "process", "name": "X", "description": "d", "props": {LINEAGE_KEY: [{"nugget_id": "KN-1", "version": 1}]}}}
    assert ops[1] == {"op": "set_props", "id": "p.y", "props": {"a": 1}}
    assert ops[2]["op"] == "add_edge" and ops[2]["edge"]["kind"] == "contains" and ops[2]["edge"]["id"] == "contains:p.x->p.y"
    assert idempotency_key_for(["KN-1:v1"], ops) == idempotency_key_for(["KN-1:v1"], ops) and len(idempotency_key_for([], [])) == 64
    assert element_id_for(Subject(kind="actor", canonical_key="ops_team", name="Ops")) == "ac.ops_team"


def test_N2_ops_without_lineage_are_refused_before_any_publish(ka):
    from ka.graph_adapter import GraphValidationError
    bad = [ElementChange(graph_id="merchant-acquiring", element_id="p.rogue", element_kind=GraphElementKind.PROCESS, operation="create", op="add_node",
                         after={"kind": "process", "name": "rogue", "props": {}})]
    assert ka.adapter.validate_change(bad)[0]["ok"] is False
    with pytest.raises((PublishRefused, GraphValidationError)):
        ka.adapter.publish(D, bad, actor="Pankaj Kamble", reason="x", base_version=None)
    assert ka.adapter.list_elements(D) == []


def test_N4_a_change_without_lineage_is_refused_on_ops_too(ka):
    test_N2_ops_without_lineage_are_refused_before_any_publish(ka)


def test_N5_a_proposed_or_unresolved_binding_yields_no_type_and_no_edge(ka):
    v = _assert(ka, "Merchant underwriting is a frobnication process.", "Merchant underwriting", "typed_as", ObjectRef(value="frobnication"))
    w = _assert(ka, "Merchant underwriting frobs: widget", "Merchant underwriting", "related_to", ObjectRef(kind="entity", value="widget"))
    approve_all(ka, [v, w])
    els = {e.element_id: e for e in ka.adapter.list_elements(D)}
    assert list(els) == ["p.merchant_underwriting"] and "process_type" not in els["p.merchant_underwriting"].props
    assert els["p.merchant_underwriting"].props["statement"] and els["p.merchant_underwriting"].props[LINEAGE_KEY]


def test_N6_in_memory_auto_approval_applies_without_an_actor_setting(ka):
    with config.scoped(KA_EOS_AUTO_ACTOR=""):
        approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    assert ka.repo.proposals.all()[0].status == ProposalStatus.APPLIED and ka.adapter.list_elements(D)


def test_N8_the_eos_adapter_no_longer_writes_directly():
    from ka.graph_adapter import EnterpriseOSGraphAdapter
    with pytest.raises(NotImplementedError, match="publish"):
        EnterpriseOSGraphAdapter(store=object()).apply_change([])
    with pytest.raises(NotImplementedError, match="publish"):
        EnterpriseOSGraphAdapter(store=object()).rollback_change([])
