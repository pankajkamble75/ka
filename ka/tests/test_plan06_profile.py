"""plan-06 (research-01 R12) — the process profile: composed from ACTIVE assertions, coverage against the bound type, nothing invented."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.governance import CandidateInput
from ka.model import ObjectRef, Scope, Subject
from ka.tests.conftest import A, D, approve_all
from ka.vocab import AuthorityType, DecisionOutcome, ScopeType

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "underwriting_sop.md"


def _sop_profile(ka, approve=True):
    got = ka.ingestion.upload(filename="underwriting_sop.md", data=FIXTURE.read_bytes(), owner="ops", scope=D, authority=AuthorityType.OPERATING_PROCEDURE)
    cands = ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops")
    procs = [c for c in cands if c.subject and c.subject.canonical_key == "merchant_underwriting"]
    if approve:
        approve_all(ka, procs)
    return procs


def _assert(ka, statement, predicate, obj, scope=D):
    got = ka.ingestion.write_note(text=statement, owner="u", scope=scope)
    return ka.governance.ingest_candidate(CandidateInput(
        title=statement[:60], statement=statement, scope=scope, source_ids=[got.source.id], evidence_ids=[],
        subject=Subject(kind="process", canonical_key="merchant_underwriting", name="Merchant underwriting"), predicate=predicate,
        object=obj, binding_method="evidenced", created_by="u"))


def test_P1_the_sop_profile_has_description_five_ordered_activities_and_the_actor(ka):
    _sop_profile(ka)
    p = ka.process_profile("merchant_underwriting")
    assert p.description and "evaluates a merchant application" in p.description.value
    assert [a.value for a in p.activities] == ["Collect application", "Validate application", "Analyze merchant risk", "Make credit decision", "Communicate decision"]
    assert [a.order for a in p.activities] == [1, 2, 3, 4, 5] and p.activities[0].child_key == "collect_application"
    assert [f.value for f in p.actors] == ["Underwriting team"] and p.counts["assertions"] == 7


def test_P2_every_field_carries_a_ref_evidence_span_and_the_published_element(ka):
    _sop_profile(ka)
    p = ka.process_profile("merchant_underwriting")
    fields = [p.description] + p.activities + p.actors
    assert all(f.ref.startswith("KN-") and f.evidence and f.evidence[0]["span_id"] == "s1" for f in fields)
    assert "merchant-acquiring/p.merchant_underwriting" in p.published_as
    assert all(any(x.endswith("p.merchant_underwriting") for x in f.published_as) for f in [p.description] + p.actors)


def test_P3_coverage_against_the_bound_types_slot_grammar(ka):
    _sop_profile(ka)
    approve_all(ka, [_assert(ka, "Merchant underwriting is a decision process.", "typed_as", ObjectRef(value="decision"))])
    p = ka.process_profile("merchant_underwriting")
    assert p.type == {**p.type, "status": "bound", "value": "decision"}
    cov = {c["slot"]: (c["level"], c["status"]) for c in p.coverage}
    g = ka.grammar.type_grammar("decision")
    assert set(cov) == {s for s, lvl in g.items() if lvl in {"required", "recommended"}}
    assert cov["input"] == ("required", "not_evidenced") and cov["rule"] == ("required", "not_evidenced")
    assert cov["goal"] == (g["goal"], "evidenced") and cov["output"] == ("required", "not_evidenced")
    assert p.coverage[0]["level"] == "required" and p.coverage_note is None
    assert "actor" not in cov or cov["actor"][1] == "evidenced"        # actor is optional for decision in the fixture


def test_P4_without_a_type_the_profile_says_so_and_has_no_coverage(ka):
    _sop_profile(ka)
    p = ka.process_profile("merchant_underwriting")
    assert p.type["status"] == "not_evidenced" and p.type["value"] is None and p.coverage == [] and p.coverage_note == "coverage needs a bound type"


def test_P5_pending_assertions_are_listed_apart(ka):
    _sop_profile(ka)
    v = _assert(ka, "Merchant underwriting consumes: merchant application", "consumes", ObjectRef(kind="entity", value="merchant application"))
    p = ka.process_profile("merchant_underwriting")
    assert p.inputs == [] and [x["ref"] for x in p.pending] == [v.ref] and p.counts["pending"] == 1


def test_P6_list_processes_with_and_without_a_scope(ka):
    _sop_profile(ka)
    rows = ka.profiles.list_processes()
    assert [r["key"] for r in rows] == ["merchant_underwriting"] and rows[0]["activities"] == 5 and rows[0]["type"]["status"] == "not_evidenced"
    assert ka.profiles.list_processes(D)[0]["key"] == "merchant_underwriting"
    assert ka.profiles.list_processes(A)[0]["key"] == "merchant_underwriting"          # instance inherits the domain's processes
    assert ka.profiles.list_processes(Scope(scope_type=ScopeType.DOMAIN, scope_id="other")) == []


@pytest.fixture
def client(ka):
    yield TestClient(create_app(ka))
    set_ka(None)


def test_P7_routes(client, ka):
    _sop_profile(ka)
    r = client.get(f"{PREFIX}/processes/merchant_underwriting")
    assert r.status_code == 200 and len(r.json()["activities"]) == 5 and r.json()["description"]["ref"]
    assert client.get(f"{PREFIX}/processes").json()["processes"][0]["key"] == "merchant_underwriting"
    assert client.get(f"{PREFIX}/processes", params={"scope_type": "INSTANCE", "scope_id": "merchant-a"}).json()["processes"]


def test_N1_a_superseded_description_is_replaced_not_shown(ka):
    _sop_profile(ka)
    old = ka.process_profile("merchant_underwriting").description.ref
    v2 = ka.governance.propose_revision(old.split(":")[0], statement="Merchant underwriting: decides merchant eligibility.", by="u", reason="better",
                                        object=ObjectRef(value="decides merchant eligibility"))
    approve_all(ka, [v2])
    p = ka.process_profile("merchant_underwriting")
    assert p.description.ref == v2.ref and p.description.value == "decides merchant eligibility"
    assert old not in [f.ref for f in [p.description] + p.activities + p.actors]


def test_N2_a_rejected_assertion_contributes_nothing(ka):
    _sop_profile(ka)
    v = _assert(ka, "Merchant underwriting produces: underwriting decision", "produces", ObjectRef(kind="entity", value="underwriting decision"))
    ka.governance.decide(v.ref, DecisionOutcome.REJECT, by="reviewer", reason="no")
    p = ka.process_profile("merchant_underwriting")
    assert p.outputs == [] and p.pending == []


def test_N3_unknown_or_non_process_subjects_are_404(client, ka):
    _sop_profile(ka)
    assert client.get(f"{PREFIX}/processes/no_such_key").status_code == 404
    approve_all(ka, [_assert(ka, "Merchant underwriting is performed by: Underwriting team", "performed_by", ObjectRef(kind="actor", value="Underwriting team"))])
    r = client.get(f"{PREFIX}/processes/underwriting_team")
    assert r.status_code == 404 and "not a known process" in r.json()["detail"]


def test_N4_an_activity_without_its_own_profile_renders_with_has_profile_false(ka):
    _sop_profile(ka)
    p = ka.process_profile("merchant_underwriting")
    assert all(a.has_profile is False for a in p.activities)
    approve_all(ka, [ka.governance.ingest_candidate(CandidateInput(
        title="Collect application: gathers documents", statement="Collect application: gathers documents", scope=D, source_ids=[], evidence_ids=[],
        subject=Subject(kind="process", canonical_key="collect_application", name="Collect application"), predicate="description",
        object=ObjectRef(value="gathers documents"), created_by="u"))])
    p = ka.process_profile("merchant_underwriting")
    assert p.activities[0].has_profile is True and p.activities[1].has_profile is False


def test_N5_the_profile_never_invents(ka):
    _sop_profile(ka)
    p = ka.process_profile("merchant_underwriting")
    assert p.type["value"] is None and p.inputs == [] and p.outputs == [] and p.rules == []
    # a statement-only nugget about refunds (no subject) never reaches any profile
    from ka.tests.conftest import ingest_policy
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    assert "refund" not in str(ka.process_profile("merchant_underwriting").model_dump()).lower()


def test_N6_apply_keeps_every_nuggets_dependency_on_a_shared_element(ka):
    """Characterization (plan-06 correction). Before the fix this asserted the DEFECT: a second nugget publishing onto
    `p.merchant_underwriting` retired the first nugget's dependency (where_used(first) == []). After the fix both stay active:
    an element composed from several assertions depends on all of them (Invariants 4/5)."""
    a = approve_all(ka, [_assert(ka, "Merchant underwriting: evaluates applications", "description", ObjectRef(value="evaluates applications"))])[0]
    assert [d.element_id for d in ka.lineage.where_used(a.ref)] == ["p.merchant_underwriting"]
    b = approve_all(ka, [_assert(ka, "Merchant underwriting is performed by: Underwriting team", "performed_by", ObjectRef(kind="actor", value="Underwriting team"))])[0]
    assert [d.element_id for d in ka.lineage.where_used(a.ref)] == ["p.merchant_underwriting"]      # fixed: stays active (pre-fix: [] — commit 00fd176)
    assert "p.merchant_underwriting" in [d.element_id for d in ka.lineage.where_used(b.ref)]
    why = ka.explain_element("merchant-acquiring", "p.merchant_underwriting")
    assert {x["ref"] for x in why["knowledge_lineage"]} == {a.ref, b.ref}


def test_N7_identical_active_assertions_compose_once(ka):
    """plan-06 correction, then Q11 (the author, 2026-10-08; built by plan-10): a re-uploaded SOP approved twice no longer makes
    duplicate ACTIVE assertions — the second approvals resolve as Keep Existing with the new document attached as evidence — so the
    profile shows each fact once with NOTHING to compose. (Before plan-10 this test pinned `also == 1` and `duplicates == 6`; that
    behaviour was the open question Q11 and the author ruled it out.)"""
    _sop_profile(ka)
    _sop_profile(ka)
    p = ka.process_profile("merchant_underwriting")
    assert [a.value for a in p.activities] == ["Collect application", "Validate application", "Analyze merchant risk", "Make credit decision", "Communicate decision"]
    assert all(len(a.also) == 0 for a in p.activities) and len(p.actors) == 1 and len(p.actors[0].also) == 0
    assert p.counts["duplicates"] == 0 and p.counts["assertions"] == 7
