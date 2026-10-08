"""Shared fixtures. Every test gets a fresh storage dir, a stub LLM and the in-memory graph adapter, so the
suite never touches a real provider or the enterprise-os store."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("KA_LLM_PROVIDER", "stub")
os.environ["ANTHROPIC_API_KEY"] = ""

from ka.llm import StubLLMProvider  # noqa: E402
from ka.model import Scope  # noqa: E402
from ka.service import KnowledgeAcquisition  # noqa: E402
from ka.vocab import ScopeType  # noqa: E402

S = Scope(scope_type=ScopeType.STRUCTURE, scope_id="universal")
P = Scope(scope_type=ScopeType.PARENT_DOMAIN, scope_id="payment-processing")
D = Scope(scope_type=ScopeType.DOMAIN, scope_id="merchant-acquiring")
A = Scope(scope_type=ScopeType.INSTANCE, scope_id="merchant-a")
B = Scope(scope_type=ScopeType.INSTANCE, scope_id="merchant-b")
C = Scope(scope_type=ScopeType.INSTANCE, scope_id="merchant-c")


@pytest.fixture
def ka(tmp_path):
    inst = KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider(), auto_approve_low_impact=True)
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D), (C, D)]:
        inst.register_scope(s, p)
    return inst


@pytest.fixture
def ka_manual(tmp_path):
    """Same, but graph changes wait for a person (auto-approve off)."""
    inst = KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider(), auto_approve_low_impact=False)
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D), (C, D)]:
        inst.register_scope(s, p)
    return inst


def approve_all(ka, cands, by="reviewer"):
    from ka.vocab import DecisionOutcome
    for c in cands:
        ka.governance.decide(c.ref, DecisionOutcome.APPROVE, by=by, reason="test")
    return cands


def ingest_policy(ka, scope, text, *, title="Policy", authority=None, owner="pankaj"):
    from ka.vocab import AuthorityType
    got = ka.ingestion.paste(text=text, owner=owner, scope=scope, title=title, authority=authority or AuthorityType.APPROVED_ENTERPRISE_POLICY)
    return ka.governance.extract_from_source(got.source, got.version, got.extraction, actor=owner)
