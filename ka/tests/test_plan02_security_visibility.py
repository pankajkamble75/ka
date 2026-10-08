"""plan-02 (research-01 R4 step 1, R5, R6) — access containment, upload/URL safety, visibility protection on scope changes.

Characterization cases (P6, P7, P8, N4) were run green against the pre-plan-02 governance code before Phase 3 changed it.
"""
from __future__ import annotations

import pytest

from ka.governance import GovernanceError
from ka.model import Scope
from ka.tests.conftest import A, B, C, D, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus, ScopeType, Visibility


def _personal_candidate(ka, scope=A, text="Our store must close on Sundays."):
    got = ka.ingestion.write_note(text=text, owner="alice", scope=scope, visibility=Visibility.PERSONAL)
    return ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="alice")[0]


# ---------------------------------------------------------------- Phase 3 characterization (pre-change behaviour)

def test_P6_change_scope_keeps_an_enterprise_candidates_visibility(ka):
    cand = ingest_policy(ka, A, "KYC is required before activation.")[0]
    assert cand.visibility == Visibility.ENTERPRISE
    d = ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="domain-wide", new_scope=D)
    new = ka.repo.require_version(d.resulting_refs[0])
    assert new.scope_type == ScopeType.DOMAIN and new.visibility == Visibility.ENTERPRISE


def test_P7_promotion_keeps_the_lead_nuggets_enterprise_visibility(ka):
    for inst in (A, B, C):
        approve_all(ka, ingest_policy(ka, inst, "Weekend refunds require two approvals."))
    prop = ka.promotion.detect(D)[0]
    p = ka.promotion.decide(prop.id, approve=True, by="lead", reason="pattern")
    assert ka.repo.require_version(p.candidate_ref).visibility == Visibility.ENTERPRISE


def test_P8_change_scope_between_two_instances_leaves_a_personal_candidate_personal(ka):
    cand = _personal_candidate(ka)
    assert cand.visibility == Visibility.PERSONAL
    d = ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="wrong store", new_scope=B)
    new = ka.repo.require_version(d.resulting_refs[0])
    assert new.scope_id == "merchant-b" and new.visibility == Visibility.PERSONAL


def test_N4_change_scope_by_a_research_agent_is_refused(ka):
    cand = ingest_policy(ka, A, "KYC is required before activation.")[0]
    with pytest.raises(GovernanceError):
        ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="agent.synthesis", reason="x", new_scope=D)
