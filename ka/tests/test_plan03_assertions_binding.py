"""plan-03 (research-01 R2, R8 KA half) — process assertions on nuggets, grammar registry, binder, canonical subjects.

Characterization cases (P8, N3a) ran green against the pre-plan-03 governance code before Phase 4 changed it.
"""
from __future__ import annotations

import pytest

from ka.tests.conftest import A, D, approve_all, ingest_policy
from ka.versioning import SEMANTIC_FIELDS, ImmutableVersionError


# ---------------------------------------------------------------- Phase 4 characterization (pre-change behaviour)

def test_P8_a_candidate_today_carries_no_assertion_and_no_binding(ka):
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]
    assert getattr(cand, "subject", None) is None and getattr(cand, "predicate", None) is None and getattr(cand, "object", None) is None
    assert not hasattr(ka.repo, "bindings") or len(ka.repo.bindings) == 0


def test_N3a_semantic_fields_today_are_plan02s_eight_and_statement_edits_are_refused(ka):
    assert set(SEMANTIC_FIELDS) >= {"title", "statement", "normalized_meaning", "scope_type", "scope_id", "knowledge_type",
                                    "authority_type", "effective_from"}
    v = approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))[0]
    v.statement = "tampered"
    with pytest.raises(ImmutableVersionError):
        ka.versioning.save(v)
