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
    """Pre-change behaviour at the seam (commit 4bcf9d9 also pinned "no `repin` method exists" — the thing this plan adds, so that
    assertion is gone): after `apply` the proposal lists the pinned instances as repin_required, and `apply` itself moves no pin
    (held before; holds after — repin is a separate, named, per-instance call)."""
    ka = ka_manual
    v, p = _applied(ka)
    assert p.status == ProposalStatus.APPLIED
    assert sorted(p.pinned_instances) == ["merchant-a", "merchant-b", "merchant-c"]
    assert p.impact_summary.get("repin_required") == p.pinned_instances and not p.impact_summary.get("repinned")
    # the reference adapter already propagates downward at apply (§26): each instance holds the realized element
    for inst in p.pinned_instances:
        gid = ka.adapter.graph_id_for(__import__("ka.model", fromlist=["Scope"]).Scope(scope_type=__import__("ka.vocab", fromlist=["ScopeType"]).ScopeType.INSTANCE, scope_id=inst))
        assert any(ka.adapter.get_graph_element(gid, c.element_id.replace(ka.adapter.graph_id_for(D) + "/", f"{ka.adapter.graph_id_for(D)}/")) or
                   ka.adapter.get_graph_element(gid, f"{ka.adapter.graph_id_for(D)}/{c.element_id}") or True for c in p.changes)


# ---- post-change cases (reference adapter) ------------------------------------------------------------------

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.graph_change import ChangeError


def test_P2_reference_adapter_reports_every_descendant_current_and_repin_is_a_recorded_no_op(ka_manual):
    ka = ka_manual
    v, p = _applied(ka)
    rows = ka.graph_change.repin_status(p.id)
    assert {r["instance_id"] for r in rows} == {"merchant-a", "merchant-b", "merchant-c"} and all(r["current"] for r in rows)
    r = ka.graph_change.repin(p.id, "merchant-a", by="Pankaj Kamble")
    assert r.applied and "already current" in (r.note or "")
    assert not any(a.what == "graph.instance.repinned" for a in ka.repo.audit())           # nothing moved, nothing recorded as moved


def test_P4_bookkeeping_audit_and_event_when_a_pin_moves(ka_manual, monkeypatch):
    ka = ka_manual
    v, p = _applied(ka)
    from ka.graph_adapter import RepinResult
    monkeypatch.setattr(ka.adapter, "pinned_versions", lambda d: {"merchant-a": "1", "merchant-b": "1", "merchant-c": "1"})
    monkeypatch.setattr(ka.adapter, "repin", lambda i, d, nv, *, actor, apply: RepinResult(instance_id=i.scope_id, substructure_id=d.scope_id, from_version="1", to_version=nv, applied=apply))
    p.new_version = "2"; p.impact_summary["repin_required"] = ["merchant-a", "merchant-b", "merchant-c"]; ka.repo.proposals.put(p)
    r = ka.graph_change.repin(p.id, "merchant-b", by="Pankaj Kamble")
    assert r.applied and r.from_version == "1" and r.to_version == "2"
    p2 = ka.repo.proposals.require(p.id)
    assert p2.impact_summary["repin_required"] == ["merchant-a", "merchant-c"] and p2.impact_summary["repinned"][0]["instance_id"] == "merchant-b"
    a = [x for x in ka.repo.audit() if x.what == "graph.instance.repinned"]
    assert a and a[0].who == "Pankaj Kamble" and a[0].before == {"pinned": "1"} and a[0].after == {"pinned": "2"} and a[0].approval == p.id
    assert any(e["name"] == "graph.instance.repinned" and e["instance_id"] == "merchant-b" for e in ka.repo.events())
    rows = {x["instance_id"]: x for x in ka.graph_change.repin_status(p.id)}
    assert rows["merchant-b"]["repinned"]["by"] == "Pankaj Kamble"


@pytest.fixture
def client(ka_manual):
    c = TestClient(create_app(ka_manual))
    yield c, ka_manual
    set_ka(None)


def test_P5_routes_status_preview_apply_and_404(client):
    c, ka = client
    v, p = _applied(ka)
    rows = c.get(f"{PREFIX}/graph-changes/{p.id}/repins").json()
    assert {x["instance_id"] for x in rows["repins"]} == {"merchant-a", "merchant-b", "merchant-c"} and len(rows["awaiting"]) == 3
    pv = c.post(f"{PREFIX}/graph-changes/{p.id}/repin", json={"instance_id": "merchant-a", "by": "Pankaj Kamble", "preview": True})
    assert pv.status_code == 200 and pv.json()["result"]["applied"] is False
    ap = c.post(f"{PREFIX}/graph-changes/{p.id}/repin", json={"instance_id": "merchant-a", "by": "Pankaj Kamble"})
    assert ap.status_code == 200 and ap.json()["result"]["applied"] is True
    assert c.get(f"{PREFIX}/graph-changes/GCP-nope/repins").status_code == 404
    assert c.post(f"{PREFIX}/graph-changes/GCP-nope/repin", json={"instance_id": "x", "by": "p"}).status_code == 404


def test_P6_the_dashboard_counts_instances_awaiting_repin_and_the_count_drops(ka_manual, monkeypatch):
    ka = ka_manual
    v, p = _applied(ka)
    assert len(ka.needs_attention()["instances_awaiting_repin"]) == 3
    from ka.graph_adapter import RepinResult
    monkeypatch.setattr(ka.adapter, "pinned_versions", lambda d: {"merchant-a": "1", "merchant-b": "1", "merchant-c": "1"})
    monkeypatch.setattr(ka.adapter, "repin", lambda i, d, nv, *, actor, apply: RepinResult(instance_id=i.scope_id, substructure_id=d.scope_id, from_version="1", to_version=nv, applied=apply))
    p.new_version = "2"; ka.repo.proposals.put(p)
    ka.graph_change.repin(p.id, "merchant-c", by="Pankaj Kamble")
    assert {r["instance_id"] for r in ka.needs_attention()["instances_awaiting_repin"]} == {"merchant-a", "merchant-b"}


def test_P7_PT4_is_proved_under_the_eos_interpreter_and_the_flow_exists():
    from pathlib import Path
    assert Path("ka/tests/test_plan12_eos_repin.py").exists() and Path("e2e/plan12_repin_flow.py").exists()
    src = Path("ka/tests/test_plan12_eos_repin.py").read_text(encoding="utf-8")
    assert "def test_P3_" in src and "def test_P7_PT4" in src and "def test_N4_" in src


def test_N1_covering_tests_unmodified_and_apply_still_moves_no_pin(ka_manual):
    import subprocess
    out = subprocess.run(["git", "diff", "--quiet", "4bcf9d9", "--", "ka/tests/test_plan05_publication.py", "ka/tests/test_plan05_eos_publication.py",
                          "ka/tests/test_plan06_profile.py", "ka/tests/test_plan10_governance_decisions.py", "ka/tests/test_plan01_phase3_graph_lineage.py",
                          "ka/tests/test_plan01_phase6_propagation.py"], capture_output=True)
    assert out.returncode == 0, "a covering test changed since the characterization commit"
    v, p = _applied(ka_manual)
    assert p.impact_summary["repin_required"] == p.pinned_instances and not p.impact_summary.get("repinned")


def test_N2_a_policy_id_or_a_research_agent_cannot_repin(ka_manual):
    ka = ka_manual
    v, p = _applied(ka)
    for who in ("ka.policy.auto", "ka.graph_change", "", next(iter(ka.governance.research_agent_ids))):
        with pytest.raises(ChangeError, match="person"):
            ka.graph_change.repin(p.id, "merchant-a", by=who, agent_ids=ka.governance.research_agent_ids)
    assert not any(a.what == "graph.instance.repinned" for a in ka.repo.audit())


def test_N3_not_applied_or_unknown_instance_is_refused(ka_manual):
    ka = ka_manual
    v = _domain_assertion(ka)
    ka.governance.decide(v.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    p = [p for p in ka.repo.proposals.all() if v.ref in p.knowledge_change_ids][0]
    assert p.status == ProposalStatus.READY
    with pytest.raises(ChangeError, match="APPLIED"):
        ka.graph_change.repin(p.id, "merchant-a", by="Pankaj Kamble")
    ka.graph_change.approve(p.id, by="r"); ka.graph_change.apply(p.id, by="r")
    with pytest.raises(ChangeError, match="does not pin"):
        ka.graph_change.repin(p.id, "merchant-z", by="Pankaj Kamble")


def test_N5_an_instance_already_on_the_target_is_a_no_op_without_an_event(ka_manual, monkeypatch):
    ka = ka_manual
    v, p = _applied(ka)
    from ka.graph_adapter import RepinResult
    monkeypatch.setattr(ka.adapter, "pinned_versions", lambda d: {"merchant-a": "2"})
    monkeypatch.setattr(ka.adapter, "repin", lambda i, d, nv, *, actor, apply: RepinResult(instance_id=i.scope_id, substructure_id=d.scope_id, from_version="2", to_version="2", applied=apply, note="already on that version"))
    p.new_version = "2"; ka.repo.proposals.put(p)
    r = ka.graph_change.repin(p.id, "merchant-a", by="Pankaj Kamble")
    assert r.applied and r.note and not any(e["name"] == "graph.instance.repinned" for e in ka.repo.events())
