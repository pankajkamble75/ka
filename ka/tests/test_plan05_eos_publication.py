"""plan-05 EOS path (research-01 R1, R7; product tests PT2, PT3, PT4). Runs only from the enterprise-os interpreter against a
TEMPORARY GraphStore with the typed structure and KW_HOTL_MODE=human:

    KW_STORAGE_ROOT=/tmp/x KW_HOTL_MODE=human PYTHONPATH=/root/ka:/root/enterprise-os-070626 \\
      /root/enterprise-os-070626/.venv/bin/python -m pytest -q -o addopts="" ka/tests/test_plan05_eos_publication.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ka.llm import StubLLMProvider
from ka.model import ObjectRef, Scope, Subject
from ka.identity import canonical_key
from ka.governance import CandidateInput
from ka.service import KnowledgeAcquisition
from ka.vocab import DecisionOutcome, ProposalStatus, ScopeType

_ROOT = os.environ.get("KA_ENTERPRISE_OS_ROOT") or "/root/enterprise-os-070626"


def _eos():
    if not Path(_ROOT, "knowledge_worker").exists():
        pytest.skip("enterprise-os checkout not reachable")
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    try:
        import knowledge_worker.graph_store  # noqa: F401
    except Exception:
        pytest.skip("knowledge_worker not importable from this interpreter")


@pytest.fixture
def eos(tmp_path, monkeypatch):
    _eos()
    monkeypatch.setenv("KW_STORAGE_ROOT", str(tmp_path / "kw"))
    monkeypatch.setenv("KW_HOTL_MODE", "human")
    (tmp_path / "kw").mkdir()
    from knowledge_worker.graph_store import GraphStore
    from knowledge_worker.graph_model.model import Graph, Node, Edge
    from knowledge_worker.graph_model.structure import UNIVERSAL, typed_universal
    typed = typed_universal()
    store = GraphStore(root=tmp_path / "kw" / "graph_v2", structures={(UNIVERSAL.id, UNIVERSAL.version): UNIVERSAL, (typed.id, typed.version): typed})
    g = Graph(id="ka-dom", tier="substructure", structure_id=typed.id, structure_version=typed.version,
              nodes=[Node(id="p.merchant_underwriting", kind="process", name="Merchant underwriting", description="d", props={}),
                     Node(id="p.merchant_underwriting.collect_application", kind="process", name="Collect application", description="", props={})],
              edges=[Edge(id="contains:p.merchant_underwriting->p.merchant_underwriting.collect_application", kind="contains",
                          source="p.merchant_underwriting", target="p.merchant_underwriting.collect_application", props={})])
    v = store.put_substructure(g)
    store.create_instance("ka-inst", "KA instance", structure=typed)
    store.realize("ka-inst", "ka-dom", v)
    from ka.graph_adapter import EnterpriseOSGraphAdapter
    from ka import config
    ka = KnowledgeAcquisition(tmp_path / "ka", provider=StubLLMProvider(), adapter=EnterpriseOSGraphAdapter(store=store),
                              auto_approve_low_impact=False)
    D = Scope(scope_type=ScopeType.DOMAIN, scope_id="ka-dom"); I = Scope(scope_type=ScopeType.INSTANCE, scope_id="ka-inst")
    ka.register_scope(D); ka.register_scope(I, D)
    with config.scoped(KA_GRAMMAR_DIR=str(Path(_ROOT) / "knowledge_worker" / "graph_model")):
        ka.grammar.refresh(force=True)
    return ka, store, D, I


def _assert(ka, scope, statement, subject_name, predicate, obj=None, kind="process", aliases=()):
    got = ka.ingestion.write_note(text=statement, owner="u", scope=scope)
    return ka.governance.ingest_candidate(CandidateInput(
        title=statement[:60], statement=statement, scope=scope, source_ids=[got.source.id], evidence_ids=[],
        subject=Subject(kind=kind, canonical_key=canonical_key(subject_name), name=subject_name, aliases=list(aliases)), predicate=predicate,
        object=obj, binding_method="evidenced", created_by="u"))


def _ship(ka, v, by="Pankaj Kamble"):
    ka.governance.decide(v.ref, DecisionOutcome.APPROVE, by=by, reason="test")
    p = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids][0]
    assert p.status == ProposalStatus.READY, p.validation_results
    ka.graph_change.approve(p.id, by=by)
    ex = ka.graph_change.apply(p.id, by=by)
    return ka.repo.proposals.require(p.id), ex


def test_P9_PT2_domain_publication_is_a_promotion_that_leaves_pins_alone(eos):
    ka, store, D, I = eos
    v = _assert(ka, D, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"))
    assert ka.repo.binding_for(v.ref).binding_status.value == "bound"
    p, ex = _ship(ka, v)
    assert ex.status == "APPLIED" and p.status == ProposalStatus.APPLIED and p.eos_base_version == "1"
    assert p.eos_status == "applied" and p.new_version == "2" and p.pinned_instances == ["ka-inst"]
    assert [x.version for x in store.versions("ka-dom")] == ["1", "2"] and store.pinned_by("ka-dom") == {"ka-inst": "1"}
    node = store.get_substructure("ka-dom").node("p.merchant_underwriting")
    assert node.props["process_type"] == "decision" and node.props["knowledge_lineage"][0]["nugget_id"] == v.canonical_id
    assert p.impact_summary["repin_required"] == ["ka-inst"]


def test_P10_instance_publication_goes_through_propose_instance_change(eos):
    ka, store, D, I = eos
    v = _assert(ka, I, "Merchant underwriting is performed by: Underwriting team", "Merchant underwriting", "performed_by", ObjectRef(kind="actor", value="Underwriting team"))
    p, ex = _ship(ka, v)
    assert ex.status == "APPLIED" and p.eos_status == "applied" and p.eos_proposal_id.startswith("prop-")
    _, g = store.get_instance("ka-inst")
    ids = {n.id for n in g.nodes} | {e.id for e in g.edges}
    assert "ac.underwriting_team" in ids and "performed_by:ka-dom~p.merchant_underwriting->ac.underwriting_team" in ids
    el = ka.adapter.get_graph_element("ka-inst", "ka-dom/p.merchant_underwriting")
    assert el.props["knowledge_lineage"][0]["nugget_id"] == v.canonical_id and el.realizes() is not None


def test_P11_PT3_the_same_knowledge_twice_yields_one_proposal_and_one_node(eos):
    ka, store, D, I = eos
    v = _assert(ka, D, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"))
    p, _ = _ship(ka, v)
    again = ka.graph_change.propose_for(v)
    assert again.id == p.id
    w = _assert(ka, D, "Underwrite merchant applications: evaluates eligibility", "Underwrite merchant applications", "description", ObjectRef(value="evaluates eligibility"),
                aliases=["merchant underwriting"])      # a second document naming the same process by its alias
    assert w.subject.canonical_key == "merchant_underwriting"          # alias resolution → same subject
    p2, _ = _ship(ka, w)
    g = store.get_substructure("ka-dom")
    assert [n.id for n in g.nodes if n.id.startswith("p.merchant") and "." not in n.id[2:]] == ["p.merchant_underwriting"]
    from knowledge_worker.graph_store import proposals as P
    assert len(P.list_proposals(store=store)) == 2


def test_N1_PT4_a_stale_base_is_refused_and_the_graph_is_unchanged(eos):
    ka, store, D, I = eos
    v = _assert(ka, D, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"))
    ka.governance.decide(v.ref, DecisionOutcome.APPROVE, by="Pankaj Kamble", reason="t")
    p = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids][0]
    assert p.eos_base_version == "1"
    # someone else publishes version 2 under KA's feet
    from knowledge_worker.graph_store import proposals as P
    pr = P.propose_promotion("ka-dom", "1", ops=[{"op": "set_props", "id": "p.merchant_underwriting", "props": {"note": "x"}}], actor="Someone Else", reason="race", store=store)
    pr = P.request_approval(pr.id, store=store); pr = P.approve(pr.id, actor="Someone Else", store=store); P.apply(pr.id, store=store)
    ka.graph_change.approve(p.id, by="Pankaj Kamble")
    ex = ka.graph_change.apply(p.id, by="Pankaj Kamble")
    p = ka.repo.proposals.require(p.id)
    assert ex.status == "FAILED" and p.status == ProposalStatus.FAILED and p.validation_results[-1]["code"] == "stale_base"
    assert [x.version for x in store.versions("ka-dom")] == ["1", "2"] and "knowledge_lineage" not in store.get_substructure("ka-dom").node("p.merchant_underwriting").props


def test_N3_a_grammar_violating_op_is_refused_by_eos_and_nothing_is_applied(eos):
    ka, store, D, I = eos
    from ka.graph_adapter import PublishRefused
    from ka.model import ElementChange
    from ka.vocab import GraphElementKind
    bad = [ElementChange(graph_id="ka-dom", element_id="governed_by:p.merchant_underwriting->p.merchant_underwriting.collect_application", element_kind=GraphElementKind.EDGE,
                         operation="create", op="add_edge", edge={"kind": "governed_by", "source": "p.merchant_underwriting", "target": "p.merchant_underwriting.collect_application"},
                         after={"props": {"knowledge_lineage": [{"nugget_id": "KN-9", "version": 1}]}})]
    with pytest.raises(PublishRefused) as e:
        ka.adapter.publish(D, bad, actor="Pankaj Kamble", reason="bad", base_version="1")
    assert e.value.code == "invalid_change" and [x.version for x in store.versions("ka-dom")] == ["1"]


def test_N6_auto_approved_proposals_wait_for_a_named_actor_under_eos(eos):
    ka, store, D, I = eos
    from ka import config
    ka.graph_change.auto_approve_low_impact = True
    with config.scoped(KA_EOS_AUTO_ACTOR=""):
        v = _assert(ka, D, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"))
        ka.governance.decide(v.ref, DecisionOutcome.APPROVE, by="Pankaj Kamble", reason="t")
    p = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids][0]
    assert p.status == ProposalStatus.APPROVED and "awaiting a named approver" in p.impact_summary["note"]
    assert [x.version for x in store.versions("ka-dom")] == ["1"]
    with config.scoped(KA_EOS_AUTO_ACTOR="Pankaj Kamble"):
        w = _assert(ka, D, "Merchant underwriting: evaluates applications", "Merchant underwriting", "description", ObjectRef(value="evaluates applications"))
        ka.governance.decide(w.ref, DecisionOutcome.APPROVE, by="Pankaj Kamble", reason="t")
    q = [p for p in ka.repo.proposals.all() if w.ref in p.knowledge_change_ids][0]
    assert q.status == ProposalStatus.APPLIED and q.eos_status == "applied"


def test_N9_rollback_publishes_the_inverse_as_a_second_eos_proposal(eos):
    ka, store, D, I = eos
    v = _assert(ka, I, "Merchant underwriting is performed by: Underwriting team", "Merchant underwriting", "performed_by", ObjectRef(kind="actor", value="Underwriting team"))
    p, ex = _ship(ka, v)
    rb = ka.graph_change.rollback(ex.id, by="Pankaj Kamble", reason="undo")
    assert rb.status == "ROLLED_BACK" and ka.repo.proposals.require(p.id).status == ProposalStatus.ROLLED_BACK
    _, g = store.get_instance("ka-inst")
    assert "ac.underwriting_team" not in {n.id for n in g.nodes}
    from knowledge_worker.graph_store import proposals as P
    assert len(P.list_proposals(store=store)) == 2 and ka.repo.proposals.require(p.id).impact_summary["rollback_eos_proposal_id"].startswith("prop-")
