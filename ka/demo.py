"""Seed data: the §47 worked example (Merchant Acquiring → Merchant A/B/C) on the in-memory adapter, so the
Knowledge Console has something to show on first run."""
from __future__ import annotations

from pathlib import Path

from ka import config
from ka.model import Scope
from ka.service import KnowledgeAcquisition
from ka.vocab import AuthorityType, DecisionOutcome, ScopeType


def seed(storage: str | Path | None = None, *, provider=None) -> KnowledgeAcquisition:
    root = Path(storage) if storage else config.storage_root()
    ka = KnowledgeAcquisition(root, provider=provider, auto_approve_low_impact=True)
    S = Scope(scope_type=ScopeType.STRUCTURE, scope_id="universal")
    P = Scope(scope_type=ScopeType.PARENT_DOMAIN, scope_id="payment-processing")
    D = Scope(scope_type=ScopeType.DOMAIN, scope_id="merchant-acquiring")
    A, B, C = (Scope(scope_type=ScopeType.INSTANCE, scope_id=f"merchant-{x}") for x in "abc")
    for s, p, name in [(S, None, "Structure"), (P, S, "Payment Processing"), (D, P, "Merchant Acquiring"),
                       (A, D, "Merchant A"), (B, D, "Merchant B"), (C, D, "Merchant C")]:
        ka.register_scope(s, p, name)

    manual = (
        "# Merchant Onboarding\nKYC is required before a merchant account is activated.\n\n"
        "# Refunds\nRefunds above $500 require manager approval. Refunds settle within 3 days.\n\n"
        "# Chargebacks\nA chargeback response must be submitted within 30 days of the dispute notice.\n\n"
        "# Settlement\nSettlement occurs after clearing is complete.\n"
    )
    got = ka.ingestion.paste(text=manual, owner="pankaj", scope=D, title="Merchant Operations Manual", markdown=True,
                             authority=AuthorityType.OPERATING_PROCEDURE)
    for c in ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="pankaj"):
        ka.governance.decide(c.ref, DecisionOutcome.APPROVE, by="governance-lead", reason="matches the operations manual")
    for inst in (A, B, C):
        ka.adapter.realize(D, inst)

    # Merchant A's 2027 policy raises its own threshold — an instance override.
    got2 = ka.ingestion.upload(filename="Merchant A Refund Policy 2027.md", owner="pankaj", scope=A, authority=AuthorityType.APPROVED_ENTERPRISE_POLICY,
                               data=b"# Section 4.2\nMerchant A refunds above $1,000 require manager approval.\n")
    for c in ka.governance.extract_from_source(got2.source, got2.version, got2.extraction, actor="pankaj"):
        ka.governance.decide(c.ref, DecisionOutcome.APPROVE, by="governance-lead", reason="Merchant A policy 2027 §4.2")

    # A conflicting internet claim at the domain level stays pending for a reviewer.
    got3 = ka.ingestion.paste(text="Refunds above $250 require manager approval.", owner="pankaj", scope=D, title="Blog post on refund controls",
                              authority=AuthorityType.INTERNET_RESEARCH)
    ka.governance.extract_from_source(got3.source, got3.version, got3.extraction, actor="pankaj")

    # International refunds: a contextual specialization, pending review.
    got4 = ka.ingestion.write_note(text="International refunds settle within 5 days.", owner="pankaj", scope=D, title="Ops note")
    ka.governance.extract_from_source(got4.source, got4.version, got4.extraction, actor="pankaj")
    return ka
