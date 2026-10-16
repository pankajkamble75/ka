"""plan-36 — NEXOS IT MVP validation: governed knowledge reaches Knowledge Worker through the documented contract, and
never establishes a physical data mapping (knowledge-worker-v1-ka.md; EOS three-tier rule; Inv. 2, 12).

- Every KA proposal reaches KW under its own idempotency key `ka:<KA proposal id>`, also when the element it changes
  already carries another nugget's lineage (a second assertion about the same process).
- A physical source (where a business's data actually lives) is a data-layer fact. Document knowledge may not assert one,
  and an edge from a kind the grammar does not allow as its source never binds.
"""
from __future__ import annotations

import json
from pathlib import Path

from ka.governance import CandidateInput
from ka.graph_adapter import LINEAGE_KEY, KnowledgeWorkerHTTPAdapter
from ka.knowledge_worker.fake import FakeKnowledgeWorker
from ka.llm import StubLLMProvider
from ka.model import ElementChange, ObjectRef, Subject
from ka.process_extraction import ProcessExtractor
from ka.tests.conftest import A, D
from ka.tests.test_plan22_derived import dp  # noqa: F401 — the Data Platform fake fixture
from ka.tests.test_plan31_knowledge_worker import _ka_with_kw
from ka.vocab import AuthorityType, BindingStatus, DecisionOutcome, GraphElementKind, ProposalStatus

SOP = Path(__file__).parent / "fixtures" / "underwriting_sop.md"


def _publish(ka, ref):
    ka.governance.decide(ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    p = [p for p in ka.repo.proposals.all() if ref in p.knowledge_change_ids][-1]
    if p.status == ProposalStatus.READY:
        ka.graph_change.approve(p.id, by="alice")
    ka.graph_change.apply(p.id, by="alice")
    return ka.repo.proposals.require(p.id)


def test_P1_each_assertion_about_one_process_reaches_kw_under_its_own_key(tmp_path):
    fake = FakeKnowledgeWorker(token="kw-token")
    ka = _ka_with_kw(tmp_path, fake)
    got = ka.ingestion.upload(filename=SOP.name, data=SOP.read_bytes(), owner="ops", scope=D, authority=AuthorityType.OPERATING_PROCEDURE)
    vs = [v for v in ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops")
          if v.subject is not None and v.subject.canonical_key == "merchant_underwriting"][:3]
    assert len(vs) == 3
    props = [_publish(ka, v.ref) for v in vs]
    assert [p.status for p in props] == [ProposalStatus.APPLIED] * 3
    assert [r["idempotency_key"] for r in fake.requests if r.get("idempotency_key")][-3:] == [f"ka:{p.id}" for p in props]
    assert set(fake.by_key) >= {f"ka:{p.id}" for p in props}


def test_N1_the_key_never_comes_from_another_nuggets_lineage_entry():
    other = {"nugget_id": "KN-001", "version": 1, "governance_decision_id": "GD-1", "graph_change_id": "GCP-old"}
    own = {"nugget_id": "KN-002", "version": 1, "governance_decision_id": "GD-2", "graph_change_id": "GCP-new"}
    c = ElementChange(graph_id="merchant-acquiring", element_id="p.x", element_kind=GraphElementKind.PROCESS, operation="update", op="set_props",
                      before=None, after={"props": {LINEAGE_KEY: [other, own]}})
    _, refs, gcp = KnowledgeWorkerHTTPAdapter.kw_request([c])
    assert gcp == "GCP-new" and {r["nugget_ref"] for r in refs} == {"KN-001:v1", "KN-002:v1"}


def _ledger_items():
    return json.dumps([
        {"subject_kind": "physical_source", "subject_name": "Refund ledger", "predicate": "description",
         "object_value": "table REFUND_TXN in the FIN schema", "excerpt": "The refund ledger table REFUND_TXN in the FIN schema", "confidence": 0.8},
        {"subject_kind": "process", "subject_name": "Refund handling", "predicate": "consumes", "object_kind": "physical_source",
         "object_name": "Refund ledger", "excerpt": "Refund handling reads the refund ledger.", "confidence": 0.8},
        {"subject_kind": "process", "subject_name": "Refund handling", "predicate": "consumes", "object_kind": "entity",
         "object_name": "Refund record", "excerpt": "Refund handling reads the refund ledger.", "confidence": 0.8},
    ])


def test_P2_a_document_naming_a_table_never_creates_a_physical_source_on_the_graph(ka):
    ka.governance.process_extractor = ProcessExtractor(StubLLMProvider(responses={"PROCESS PASS": _ledger_items()}), ka.grammar)
    text = b"# Refund ledger\nThe refund ledger table REFUND_TXN in the FIN schema stores every refund.\nRefund handling reads the refund ledger.\n"
    for scope in (A, D):
        got = ka.ingestion.upload(filename=f"ledger-{scope.scope_id}.md", data=text, owner="ops", scope=scope, authority=AuthorityType.OPERATING_PROCEDURE)
        cands = ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops")
        assert not [c for c in cands if (c.subject and c.subject.kind == "physical_source") or (c.object and c.object.kind == "physical_source")]
        dropped = ka.repo.source_versions.get(got.version.id).extraction_report["dropped"]
        assert sum("data-layer" in d["reason"] for d in dropped) == 2         # disclosed, not silently lost
        for c in [c for c in cands if c.subject is not None]:
            ka.governance.decide(c.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
        assert not [e for e in ka.adapter.list_elements(scope) if e.element_id.split("/")[-1].startswith("ps.")]


def test_N2_an_assertion_about_a_physical_source_never_binds(ka):
    v = ka.governance.ingest_candidate(CandidateInput(
        title="Refund handling reads the ledger", statement="Refund handling consumes the refund ledger.", scope=A, source_ids=[], evidence_ids=[],
        subject=Subject(kind="process", canonical_key="refund_handling", name="Refund handling"), predicate="consumes",
        object=ObjectRef(kind="physical_source", value="Refund ledger")))
    b = ka.repo.binding_for(v.ref)
    assert b.binding_status == BindingStatus.UNRESOLVED and "data-layer" in b.reasons[0]


def test_N3_an_edge_from_a_kind_the_grammar_does_not_allow_stays_proposed(ka):
    v = ka.governance.ingest_candidate(CandidateInput(
        title="Refund record consumes a refund", statement="Refund record consumes the refund amount.", scope=A, source_ids=[], evidence_ids=[],
        subject=Subject(kind="entity", canonical_key="refund_record", name="Refund record"), predicate="consumes",
        object=ObjectRef(kind="attribute", value="Refund amount"), binding_method="approved"))
    b = ka.repo.binding_for(v.ref)
    assert b.binding_status == BindingStatus.PROPOSED and any("not an allowed source" in r for r in b.reasons)


def test_P3_a_derived_nugget_asset_carries_the_lineage_ids_the_graph_carries(dp):  # noqa: F811 — pytest fixture
    """Architecture §11: a DP asset's provenance and a graph node's knowledge_lineage join on the same ids."""
    from ka.tests.test_plan22_derived import _candidates, _cfg, approve_all as _approve
    ka, fake, _ = dp
    with _cfg():
        _, cands = _candidates(ka)
        _approve(ka, cands)
        ka.outbox.process_once()
    v = ka.repo.require_version(cands[0].ref)
    art = next(a for a in ka.repo.derived_artefacts.where(lambda a: a.ref == v.ref) if a.status == "ACTIVE")
    prov = fake.assets[art.dp_asset_id]["provenance"]
    assert prov["ref"] == v.ref and prov["governance_decision_id"] == v.governance_decision_id
