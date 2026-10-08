"""plan-01 Phase 2 — Governance (§10–§14, §33): new content cannot silently overwrite enterprise knowledge."""
from __future__ import annotations

import pytest

from ka.governance import GovernanceError
from ka.model import Scope
from ka.tests.conftest import A, D, approve_all, ingest_policy
from ka.vocab import AuthorityType, DecisionOutcome, NuggetStatus, RelationshipType, ScopeType


def test_P1_contradiction_in_same_scope_is_detected_and_held_for_review(ka):
    approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.", title="Policy 2027")[0]
    assert cand.status == NuggetStatus.PENDING_REVIEW and cand.analysis["conflict_open"]
    rels = ka.repo.relationships_for(cand.ref)
    assert [r.relationship_type for r in rels] == [RelationshipType.CONTRADICTS]
    assert any(e["name"] == "knowledge.conflict.detected" for e in ka.repo.events())
    assert ka.repo.active_nuggets(A)[0].statement.endswith("$500 require manager approval.")   # nothing overwritten


def test_P2_accept_new_supersedes_the_conflicting_existing_version(ka):
    old = approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))[0]
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.")[0]
    d = ka.governance.decide(cand.ref, DecisionOutcome.ACCEPT_NEW, by="reviewer", reason="2027 policy")
    assert ka.repo.require_version(old.ref).status == NuggetStatus.SUPERSEDED
    assert ka.repo.require_version(cand.ref).status == NuggetStatus.ACTIVE
    assert d.related_refs == [old.ref] and old.ref in [r.to_ref for r in ka.repo.relationships_for(cand.ref) if r.relationship_type == RelationshipType.SUPERSEDES]


def test_P3_keep_existing_rejects_the_candidate_and_preserves_it(ka):
    approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.")[0]
    ka.governance.decide(cand.ref, DecisionOutcome.KEEP_EXISTING, by="reviewer", reason="unverified source")
    c = ka.repo.require_version(cand.ref)
    assert c.status == NuggetStatus.REJECTED and c.governance_decision_id and "$1,000" in c.statement


def test_P4_duplicate_is_flagged_not_doubled(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="Copy")[0]
    assert cand.analysis.get("duplicate_of") == "KN-001:v1"
    assert RelationshipType.DUPLICATES in {r.relationship_type for r in ka.repo.relationships_for(cand.ref)}


def test_P5_contextual_specialization_is_not_a_contradiction(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds settle within 3 days."))
    cand = ingest_policy(ka, D, "International refunds settle within 5 days.")[0]
    rels = {r.relationship_type for r in ka.repo.relationships_for(cand.ref)}
    assert RelationshipType.SPECIALIZES in rels and RelationshipType.CONTRADICTS not in rels
    assert not cand.analysis.get("conflict_open")


def test_P6_instance_override_of_domain_rule_is_a_specialization(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.")[0]
    assert {r.relationship_type for r in ka.repo.relationships_for(cand.ref)} == {RelationshipType.SPECIALIZES}


def test_P7_low_authority_contradiction_is_auto_resolved_but_preserved(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval.", authority=AuthorityType.APPROVED_ENTERPRISE_POLICY))
    cand = ingest_policy(ka, D, "Refunds above $250 require manager approval.", authority=AuthorityType.INTERNET_RESEARCH)[0]
    c = ka.repo.require_version(cand.ref)
    assert c.status == NuggetStatus.REJECTED
    d = ka.repo.decisions.get(c.governance_decision_id)
    assert d.automatic and d.outcome == DecisionOutcome.AUTO_RESOLVED_BY_AUTHORITY and "rank" in d.reason
    assert ka.repo.active_nuggets(D)[0].statement.startswith("Refunds above $500")


def test_P8_authority_rank_is_configurable_per_scope(ka):
    ka.governance.authority.set_rank(ScopeType.DOMAIN, "merchant-acquiring", AuthorityType.INTERNET_RESEARCH, 95)
    v = ingest_policy(ka, D, "Refunds above $250 require manager approval.", authority=AuthorityType.INTERNET_RESEARCH)[0]
    assert v.authority_rank == 95 and v.authority_type == AuthorityType.INTERNET_RESEARCH


def test_P9_merge_creates_one_new_version_from_both(ka):
    old = approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))[0]
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.")[0]
    d = ka.governance.decide(cand.ref, DecisionOutcome.MERGE, by="reviewer", reason="combine",
                             merged_statement="Merchant A refunds above $1,000 require manager approval; above $500 require supervisor sign-off.")
    merged = ka.repo.require_version(d.resulting_refs[-1])
    assert merged.canonical_id == old.canonical_id and merged.version == 2 and merged.status == NuggetStatus.ACTIVE
    assert ka.repo.require_version(old.ref).status == NuggetStatus.SUPERSEDED and ka.repo.require_version(cand.ref).status == NuggetStatus.SUPERSEDED
    assert set(merged.source_refs) >= set(old.source_refs) | set(cand.source_refs)


def test_P10_change_scope_re_creates_the_candidate_at_the_new_scope(ka):
    cand = ingest_policy(ka, D, "All merchants must complete KYC before activation.")[0]
    d = ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="applies to all payment domains",
                             new_scope=Scope(scope_type=ScopeType.PARENT_DOMAIN, scope_id="payment-processing"))
    new = ka.repo.require_version(d.resulting_refs[0])
    assert new.scope_type == ScopeType.PARENT_DOMAIN and ka.repo.require_version(cand.ref).status == NuggetStatus.REJECTED


def test_P11_request_more_research_opens_a_mission_in_the_nugget_scope(ka):
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]
    d = ka.governance.decide(cand.ref, DecisionOutcome.REQUEST_MORE_RESEARCH, by="reviewer", reason="verify against card network rules")
    assert "mission=" in d.comments
    m = ka.repo.missions.all()[0]
    assert m.scope_id == "merchant-acquiring" and m.trigger == "governance"


def test_N1_nothing_becomes_active_without_a_decision(ka):
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]
    assert cand.status == NuggetStatus.PENDING_REVIEW and ka.repo.active_nuggets(D) == []
    from ka.versioning import IllegalTransition
    with pytest.raises(IllegalTransition):
        ka.versioning.transition(cand, NuggetStatus.ACTIVE)


def test_N2_research_agents_cannot_approve_their_own_knowledge(ka):
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]
    with pytest.raises(GovernanceError):
        ka.governance.decide(cand.ref, DecisionOutcome.APPROVE, by="agent.synthesis", reason="I made it")


def test_N3_deciding_an_already_active_version_is_refused(ka):
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    with pytest.raises(GovernanceError):
        ka.governance.decide(v.ref, DecisionOutcome.REJECT, by="reviewer")


def test_P12_comments_and_evidence_can_be_added_to_a_governed_version_without_a_new_version(ka):
    from ka.model import Evidence
    v = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    ka.governance.add_comment(v.ref, "ops", "confirmed with finance")
    src = ka.ingestion.write_note(text="Finance confirmed the $500 threshold on 2026-01-05.", owner="ops", scope=D)
    ka.governance.add_evidence(v.ref, Evidence(source_id=src.source.id, source_version_id=src.version.id, excerpt="Finance confirmed"), by="ops")
    v = ka.repo.require_version(v.ref)
    assert v.version == 1 and len(v.evidence_refs) == 2 and v.comments[0]["text"] == "confirmed with finance"


def test_P13_every_decision_is_audited_with_who_what_why_before_after(ka):
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]
    ka.governance.decide(cand.ref, DecisionOutcome.APPROVE, by="reviewer", reason="policy")
    rec = [a for a in ka.auditor.for_object(cand.ref) if a.what == "governance.approve"][0]
    assert rec.who == "reviewer" and rec.why == "policy" and rec.before == {"status": "PENDING_REVIEW"} and rec.after == {"status": "ACTIVE"} and rec.approval
