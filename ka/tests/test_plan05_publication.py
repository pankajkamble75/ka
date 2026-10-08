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


def test_P7a_two_nuggets_about_one_subject_with_different_titles_make_two_elements_today(ka):
    a = _assert(ka, "Merchant underwriting is a decision process.", "Merchant underwriting", "typed_as", ObjectRef(value="decision"), title="Underwriting type")
    b = _assert(ka, "Merchant underwriting: evaluates applications.", "Merchant underwriting", "description", ObjectRef(value="evaluates applications"), title="Underwriting purpose")
    approve_all(ka, [a, b])
    ids = sorted(e.element_id for e in ka.adapter.list_elements(D))
    assert len(ids) == 2 and all(i.startswith(("n.", "e.", "r.", "p.")) for i in ids)


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
