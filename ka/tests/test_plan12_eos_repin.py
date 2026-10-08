"""plan-12 EOS half (research-02 R4; PT4). Runs only from the enterprise-os interpreter against a TEMPORARY GraphStore:

    KW_STORAGE_ROOT=/tmp/x KW_HOTL_MODE=human PYTHONPATH=/root/ka:/root/enterprise-os-070626 \\
      /root/enterprise-os-070626/.venv/bin/python -m pytest -q -o addopts="" ka/tests/test_plan12_eos_repin.py
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
    for iid in ("ka-inst-a", "ka-inst-b"):
        store.create_instance(iid, f"KA instance {iid}", structure=typed)
        store.realize(iid, "ka-dom", v)
    from ka.graph_adapter import EnterpriseOSGraphAdapter
    from ka import config
    ka = KnowledgeAcquisition(tmp_path / "ka", provider=StubLLMProvider(), adapter=EnterpriseOSGraphAdapter(store=store), auto_approve_low_impact=False)
    D = Scope(scope_type=ScopeType.DOMAIN, scope_id="ka-dom")
    ka.register_scope(D)
    for iid in ("ka-inst-a", "ka-inst-b"):
        ka.register_scope(Scope(scope_type=ScopeType.INSTANCE, scope_id=iid), D)
    with config.scoped(KA_GRAMMAR_DIR=str(Path(_ROOT) / "knowledge_worker" / "graph_model")):
        ka.grammar.refresh(force=True)
    return ka, store, D


def _promoted(ka, D, by="Pankaj Kamble"):
    got = ka.ingestion.write_note(text="Merchant underwriting is a decision process.", owner="u", scope=D)
    v = ka.governance.ingest_candidate(CandidateInput(
        title="typed", statement="Merchant underwriting is a decision process.", scope=D, source_ids=[got.source.id], evidence_ids=[],
        subject=Subject(kind="process", canonical_key=canonical_key("Merchant underwriting"), name="Merchant underwriting"), predicate="typed_as",
        object=ObjectRef(value="decision"), binding_method="evidenced", created_by="u"))
    ka.governance.decide(v.ref, DecisionOutcome.APPROVE, by=by, reason="test")
    p = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids][0]
    assert p.status == ProposalStatus.READY, p.validation_results
    ka.graph_change.approve(p.id, by=by)
    ka.graph_change.apply(p.id, by=by)
    return v, ka.repo.proposals.require(p.id)


def test_P1_characterization_a_ka_promotion_leaves_every_pin_on_the_old_version(eos):
    ka, store, D = eos
    v, p = _promoted(ka, D)
    assert p.status == ProposalStatus.APPLIED and p.new_version == "2"
    assert store.pinned_by("ka-dom") == {"ka-inst-a": "1", "ka-inst-b": "1"}
    assert sorted(p.pinned_instances) == ["ka-inst-a", "ka-inst-b"] and sorted(p.impact_summary["repin_required"]) == ["ka-inst-a", "ka-inst-b"]
    # (commit 4bcf9d9 also pinned "no repin method"; that is what this plan adds)


def test_P3_preview_writes_nothing_and_apply_moves_exactly_one_pin(eos):
    ka, store, D = eos
    v, p = _promoted(ka, D)
    pv = ka.graph_change.repin(p.id, "ka-inst-a", by="Pankaj Kamble", preview=True)
    assert pv.applied is False and pv.from_version == "1" and pv.to_version == "2" and not pv.blocking_edges
    assert store.pinned_by("ka-dom") == {"ka-inst-a": "1", "ka-inst-b": "1"}
    r = ka.graph_change.repin(p.id, "ka-inst-a", by="Pankaj Kamble")
    assert r.applied and store.pinned_by("ka-dom") == {"ka-inst-a": "2", "ka-inst-b": "1"}
    _, g = store.get_instance("ka-inst-a")
    assert g.node("ka-dom/p.merchant_underwriting").props.get("process_type") == "decision"
    _, gb = store.get_instance("ka-inst-b")
    assert gb.node("ka-dom/p.merchant_underwriting").props.get("process_type") is None


def test_P7_PT4_status_named_repin_store_state_and_audit(eos):
    ka, store, D = eos
    v, p = _promoted(ka, D)
    rows = {r["instance_id"]: r for r in ka.graph_change.repin_status(p.id)}
    assert rows["ka-inst-a"] == {"instance_id": "ka-inst-a", "pinned": "1", "target": "2", "current": False, "repinned": None}
    ka.graph_change.repin(p.id, "ka-inst-b", by="Pankaj Kamble")
    rows = {r["instance_id"]: r for r in ka.graph_change.repin_status(p.id)}
    assert rows["ka-inst-b"]["current"] and rows["ka-inst-b"]["repinned"]["by"] == "Pankaj Kamble" and not rows["ka-inst-a"]["current"]
    p2 = ka.repo.proposals.require(p.id)
    assert p2.impact_summary["repin_required"] == ["ka-inst-a"]
    a = [x for x in ka.repo.audit() if x.what == "graph.instance.repinned"]
    assert len(a) == 1 and a[0].who == "Pankaj Kamble" and a[0].before == {"pinned": "1"} and a[0].after == {"pinned": "2"}
    assert [r["instance_id"] for r in ka.needs_attention()["instances_awaiting_repin"]] == ["ka-inst-a"]


def test_N4_a_blocked_repin_leaves_the_pin_and_records_no_move(eos):
    ka, store, D = eos
    v, p = _promoted(ka, D)
    # make the new version drop a node the instance still points at from its own edge: add an instance-local edge to the child,
    # then a second promotion that removes the child → repin is blocked
    from knowledge_worker.graph_store import proposals as P
    from knowledge_worker.graph_model.model import Edge, Node
    pr = P.propose_instance_change("ka-inst-a", ops=[{"op": "add_node", "node": Node(id="local.clerk", kind="actor", name="Local clerk", description="", props={}).model_dump()},
                                                     {"op": "add_edge", "edge": Edge(id="performed_by:ka-dom~p.merchant_underwriting.collect_application->local.clerk", kind="performed_by",
                                                                                     source="ka-dom/p.merchant_underwriting.collect_application", target="local.clerk", props={}).model_dump()}],
                                   actor="Pankaj Kamble", reason="local edge", store=store)
    P.approve(pr.id, actor="Pankaj Kamble", store=store)                     # an instance change is awaiting_approval from birth
    P.apply(pr.id, store=store)
    pr2 = P.propose_promotion("ka-dom", "2", ops=[{"op": "remove_edge", "id": "contains:p.merchant_underwriting->p.merchant_underwriting.collect_application"},
                                                  {"op": "remove_node", "id": "p.merchant_underwriting.collect_application"}],
                              actor="Pankaj Kamble", reason="drop child", store=store)
    P.request_approval(pr2.id, store=store); P.approve(pr2.id, actor="Pankaj Kamble", store=store); P.apply(pr2.id, store=store)
    p.new_version = "3"; p.impact_summary["repin_required"] = ["ka-inst-a", "ka-inst-b"]; ka.repo.proposals.put(p)
    r = ka.graph_change.repin(p.id, "ka-inst-a", by="Pankaj Kamble")
    assert r.applied is False and r.blocking_edges and store.pinned_by("ka-dom")["ka-inst-a"] == "1"
    assert not any(x.what == "graph.instance.repinned" for x in ka.repo.audit())
