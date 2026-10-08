"""plan-10 (research-02 R1, R2; product tests PT1, PT2) — duplicates resolve as Keep Existing + evidence; revocation becomes a
re-review. P1 characterises the PROTECTED governance seams BEFORE the change (own commit, green against the unchanged files)."""
from __future__ import annotations

from ka import config
from ka.model import Scope
from ka.tests.conftest import A, D, S, P, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus

POLICY = "Merchant A refunds above $500 require manager approval."


def _folder_world(tmp_path, ka):
    root = tmp_path / "inbox"
    (root / "ops").mkdir(parents=True)
    return root, root / "ops"


def test_P1_characterization_duplicates_double_keep_existing_discards_and_revocation_only_flags(ka, tmp_path):
    """Pre-change behaviour at the seams this plan changes."""
    # (a) APPROVE on a duplicate_of candidate activates it → two ACTIVE versions of one fact
    first = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    dup = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="Copy")[0]
    assert dup.analysis.get("duplicate_of") == first.ref
    ka.governance.decide(dup.ref, DecisionOutcome.APPROVE, by="reviewer", reason="test")
    active = [n for n in ka.repo.nuggets_by_status(NuggetStatus.ACTIVE) if n.scope == D]
    assert {n.ref for n in active} >= {first.ref, dup.ref}                      # doubled
    # (b) explicit KEEP_EXISTING rejects the candidate and leaves the target's provenance untouched
    dup2 = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="Copy 2")[0]
    before = list(ka.repo.require_version(first.ref).source_refs)
    ka.governance.decide(dup2.ref, DecisionOutcome.KEEP_EXISTING, by="reviewer", reason="dup")
    assert ka.repo.require_version(dup2.ref).status == NuggetStatus.REJECTED
    assert ka.repo.require_version(first.ref).source_refs == before             # evidence discarded
    # (c) an ordinary REJECT changes no other version
    other = ingest_policy(ka, A, POLICY)[0]
    statuses = {n.ref: n.status for n in ka.repo.nuggets.all() if n.ref != other.ref}
    ka.governance.decide(other.ref, DecisionOutcome.REJECT, by="reviewer", reason="no")
    assert {n.ref: n.status for n in ka.repo.nuggets.all() if n.ref != other.ref} == statuses
    # (d) deleting a connected file leaves derived nuggets ACTIVE and flagged (plan-08)
    root, folder = _folder_world(tmp_path, ka)
    (folder / "policy.md").write_text("Merchant B chargebacks must be answered within 30 days.\n")
    with config.scoped(KA_CONNECTOR_ROOTS=str(root)):
        conn = ka.connectors.create("local_folder", "Ops", {"root": str(folder)}, owner="ops", scope=Scope(scope_type=A.scope_type, scope_id="merchant-b"))
        ka.connectors.sync(conn.id, by="ops")
        src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
        cands = ka.repo.nuggets.where(lambda n: src.id in n.source_refs)
        approve_all(ka, cands)
        (folder / "policy.md").unlink()
        ka.connectors.sync(conn.id, by="ops")
    for c in cands:
        v = ka.repo.require_version(c.ref)
        assert v.status == NuggetStatus.ACTIVE and v.analysis.get("source_revoked")
    assert not ka.repo.nuggets.where(lambda n: n.canonical_id == cands[0].canonical_id and n.status == NuggetStatus.PENDING_REVIEW)
