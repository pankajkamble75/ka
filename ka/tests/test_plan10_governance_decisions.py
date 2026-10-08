"""plan-10 (research-02 R1, R2; product tests PT1, PT2) — duplicates resolve as Keep Existing + evidence; revocation becomes a
re-review. P1 characterises the PROTECTED governance seams BEFORE the change (own commit, green against the unchanged files)."""
from __future__ import annotations

from ka import config
from ka.model import Scope
from ka.tests.conftest import A, D, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus

POLICY = "Merchant A refunds above $500 require manager approval."


def _folder_world(tmp_path, ka):
    root = tmp_path / "inbox"
    (root / "ops").mkdir(parents=True)
    return root, root / "ops"


def test_P1_characterization_duplicates_double_keep_existing_discards_and_revocation_only_flags(ka, tmp_path):
    """Pre-change behaviour at the seams (commit 48d4685 pinned it): (a) APPROVE on a duplicate doubled the fact, (b) KEEP_EXISTING
    discarded the candidate's evidence, (d) revocation only flagged. Those three are exactly what this plan changes — the post-change
    truth is P2, P4 and P5 — so this test now keeps the assertions that held before AND after: the duplicate is flagged, an explicit
    KEEP_EXISTING rejects the candidate, and (c) an ordinary REJECT changes no other version."""
    first = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    dup = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="Copy")[0]
    assert dup.analysis.get("duplicate_of") == first.ref
    # (b) explicit KEEP_EXISTING rejects the candidate (held before; holds after)
    dup2 = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="Copy 2")[0]
    ka.governance.decide(dup2.ref, DecisionOutcome.KEEP_EXISTING, by="reviewer", reason="dup")
    assert ka.repo.require_version(dup2.ref).status == NuggetStatus.REJECTED
    assert ka.repo.require_version(first.ref).status == NuggetStatus.ACTIVE
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
        assert v.status == NuggetStatus.ACTIVE and v.analysis.get("source_revoked")      # the prior stays ACTIVE until decided (before and after)


# ---- post-change cases ------------------------------------------------------------------------------------

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.vocab import RelationshipType


def _dup_pair(ka, scope=D):
    first = approve_all(ka, ingest_policy(ka, scope, "Refunds above $500 require manager approval.", title="SOP v1"))[0]
    dup = ingest_policy(ka, scope, "Refunds above $500 require manager approval.", title="SOP copy")[0]
    assert dup.analysis.get("duplicate_of") == first.ref
    return first, dup


def test_P2_approve_on_a_duplicate_resolves_as_automatic_keep_existing(ka):
    first, dup = _dup_pair(ka)
    d = ka.governance.decide(dup.ref, DecisionOutcome.APPROVE, by="reviewer", reason="looks fine")
    assert d.outcome == DecisionOutcome.KEEP_EXISTING and d.automatic and first.ref in d.related_refs and "Q11" in d.reason
    v = ka.repo.require_version(dup.ref)
    assert v.status == NuggetStatus.REJECTED and v.analysis["resolved_as"] == "duplicate" and v.governance_decision_id == d.id
    active = [n for n in ka.repo.nuggets_by_status(NuggetStatus.ACTIVE) if n.scope == D and "500" in n.statement]
    assert [n.ref for n in active] == [first.ref]
    assert any(a.what == "knowledge.provenance.attached" for a in ka.repo.audit()) and any(a.what == "governance.keep_existing" for a in ka.repo.audit())


def test_P3_provenance_moves_to_the_existing_nugget_without_touching_its_meaning_or_lineage(ka):
    first, dup = _dup_pair(ka)
    stored = ka.repo.stored_version(first.ref) if hasattr(ka.repo, "stored_version") else ka.repo.require_version(first.ref)
    sem = {f: getattr(stored, f) for f in ("title", "statement", "normalized_meaning", "scope_type", "scope_id", "knowledge_type", "authority_type", "effective_from")}
    deps_before = [d.model_dump() for d in ka.repo.dependencies_for_nugget(first.ref, active_only=False)]
    ka.governance.decide(dup.ref, DecisionOutcome.APPROVE, by="reviewer", reason="")
    after = ka.repo.require_version(first.ref)
    assert set(dup.source_refs) <= set(after.source_refs) and set(dup.evidence_refs) <= set(after.evidence_refs)
    assert {f: getattr(after, f) for f in sem} == sem and after.version == first.version
    assert [d.model_dump() for d in ka.repo.dependencies_for_nugget(first.ref, active_only=False)] == deps_before
    rels = {r.relationship_type for r in ka.repo.relationships_for(dup.ref)}
    assert RelationshipType.DUPLICATES in rels


def test_P4_explicit_keep_existing_attaches_too_and_a_stale_duplicate_flag_falls_through(ka):
    first, dup = _dup_pair(ka)
    d = ka.governance.decide(dup.ref, DecisionOutcome.KEEP_EXISTING, by="reviewer", reason="dup")
    assert not d.automatic and set(dup.source_refs) <= set(ka.repo.require_version(first.ref).source_refs)
    # a second duplicate whose target got superseded before the decision: ordinary approval
    dup2 = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="SOP copy 2")[0]
    assert dup2.analysis.get("duplicate_of") == first.ref
    rev = ka.governance.propose_revision(first.canonical_id, statement="Refunds above $500 require manager approval.", by="ops", reason="refresh")
    ka.governance.decide(rev.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    assert ka.repo.require_version(first.ref).status == NuggetStatus.SUPERSEDED
    d2 = ka.governance.decide(dup2.ref, DecisionOutcome.APPROVE, by="reviewer", reason="")
    assert d2.outcome == DecisionOutcome.APPROVE and ka.repo.require_version(dup2.ref).status == NuggetStatus.ACTIVE


def _revoked_world(ka, tmp_path, text="Merchant B chargebacks must be answered within 30 days.\n", extra_source=False):
    root, folder = _folder_world(tmp_path, ka)
    (folder / "policy.md").write_text(text)
    scope = Scope(scope_type=A.scope_type, scope_id="merchant-b")
    with config.scoped(KA_CONNECTOR_ROOTS=str(root)):
        conn = ka.connectors.create("local_folder", "Ops", {"root": str(folder)}, owner="ops", scope=scope)
        ka.connectors.sync(conn.id, by="ops")
        src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
        cands = ka.repo.nuggets.where(lambda n: src.id in n.source_refs)
        approve_all(ka, cands)
        if extra_source:
            for c in cands:
                v = ka.repo.require_version(c.ref)
                other = ka.ingestion.paste(text=text, owner="ops", scope=scope, title="second source")
                ka.governance.attach_provenance(v.ref, type("X", (), {"ref": "manual", "source_refs": [other.source.id], "evidence_refs": []})(), by="ops")
        (folder / "policy.md").unlink()
        rep = ka.connectors.sync(conn.id, by="ops")
    return src, [ka.repo.require_version(c.ref) for c in cands], rep


def test_P5_revocation_reopens_each_active_nugget_as_a_same_statement_revision(ka, tmp_path):
    src, priors, rep = _revoked_world(ka, tmp_path)
    assert rep.reviews and len(rep.reviews) == len(priors)
    for prior, ref in zip(sorted(priors, key=lambda p: p.canonical_id), sorted(rep.reviews)):
        rev = ka.repo.require_version(ref)
        assert rev.canonical_id == prior.canonical_id and rev.version == prior.version + 1 and rev.statement == prior.statement
        assert rev.status == NuggetStatus.PENDING_REVIEW and rev.analysis["source_revoked"]["source_id"] == src.id
        assert src.id not in rev.source_refs and rev.analysis["remaining_sources"] == 0 and rev.channel.value == "FEEDBACK"
        assert ka.repo.require_version(prior.ref).status == NuggetStatus.ACTIVE
        assert not rev.analysis.get("duplicate_of")
    again = ka.governance.reopen_for_revocation(src.id, by="ops")
    assert again == []
    rows = ka.needs_attention()["revoked_source_reviews"]
    assert {r["ref"] for r in rows} == set(rep.reviews)


def test_P6_approving_the_revision_supersedes_the_prior_and_the_knowledge_continues(ka, tmp_path):
    src, priors, rep = _revoked_world(ka, tmp_path, extra_source=True)
    rev = ka.repo.require_version(rep.reviews[0])
    assert rev.analysis["remaining_sources"] == 1
    ka.governance.decide(rev.ref, DecisionOutcome.APPROVE, by="reviewer", reason="stands on the second source")
    assert ka.repo.require_version(rev.ref).status == NuggetStatus.ACTIVE
    assert ka.repo.require_version(priors[0].ref).status == NuggetStatus.SUPERSEDED
    assert src.id not in ka.repo.require_version(rev.ref).source_refs


def test_P7_rejecting_the_revision_retires_the_prior_and_raises_a_removal_proposal(ka, tmp_path):
    src, priors, rep = _revoked_world(ka, tmp_path)
    prior = priors[0]
    deps = ka.repo.dependencies_for_nugget(prior.ref)
    assert deps, "the approved nugget was compiled into the graph"
    rev = ka.repo.require_version(rep.reviews[0])
    d = ka.governance.decide(rev.ref, DecisionOutcome.REJECT, by="reviewer", reason="no other evidence")
    p = ka.repo.require_version(prior.ref)
    assert p.status == NuggetStatus.OBSOLETE and p.effective_to and prior.ref in d.related_refs
    assert any(r.relationship_type == RelationshipType.OBSOLETES and r.to_ref == prior.ref for r in ka.repo.relationships_for(rev.ref))
    assert ka.repo.require_version(rev.ref).status == NuggetStatus.REJECTED
    props = [ka.repo.proposals.require(x) for x in d.resulting_refs if x.startswith("GCP") or ka.repo.proposals.get(x)]
    assert props and props[0].impact_summary.get("retirement") and all(c.operation == "remove" for c in props[0].changes)
    assert {c.element_id for c in props[0].changes} <= {dd.element_id for dd in deps}


@pytest.fixture
def client(ka):
    c = TestClient(create_app(ka))
    yield c
    set_ka(None)


def test_P8_PT1_PT2_through_the_api(ka, tmp_path, client):
    # PT1: the same SOP twice → one ACTIVE version naming both documents; history shows the duplicate
    first, dup = _dup_pair(ka)
    r = client.post(f"{PREFIX}/nugget/{dup.ref}/decide", json={"outcome": "APPROVE", "by": "reviewer", "reason": "second copy"})
    assert r.status_code == 200 and r.json()["decision"]["outcome"] == "KEEP_EXISTING"
    n = client.get(f"{PREFIX}/nugget/{first.ref}").json()
    assert len(n["nugget"]["source_refs"]) == 2
    hist = [x for x in client.get(f"{PREFIX}/nuggets").json()["nuggets"] if x["ref"] == dup.ref]
    assert hist and hist[0]["status"] == "REJECTED" and hist[0].get("resolved_as") == "duplicate"
    # PT2: deleting a connected file → revision in Pending with the badge; reject → prior OBSOLETE, proposal exists
    src, priors, rep = _revoked_world(ka, tmp_path)
    att = client.get(f"{PREFIX}/needs-attention").json()
    assert {x["ref"] for x in att["revoked_source_reviews"]} == set(rep.reviews)
    r = client.post(f"{PREFIX}/nugget/{rep.reviews[0]}/decide", json={"outcome": "REJECT", "by": "reviewer", "reason": "gone"})
    assert r.status_code == 200
    assert client.get(f"{PREFIX}/nugget/{priors[0].ref}").json()["nugget"]["status"] == "OBSOLETE"
    props = client.get(f"{PREFIX}/graph-changes").json()["proposals"]
    assert any(p.get("impact_summary", {}).get("retirement") for p in props)


def test_N1_covering_tests_are_unmodified_and_the_decide_contract_holds(ka):
    """Regression gate. One covering test was NOT left unmodified: `test_plan06_profile.py::test_N7` pinned "a re-uploaded SOP
    approved twice makes duplicate ACTIVE assertions (Q11)" — the very behaviour the author ruled out at Q11 on 2026-10-08 — so its
    assertions were rewritten to the decided behaviour and the change is recorded in the plan-10 checkpoint and docs/protected.md.
    Every other covering suite is byte-identical to the characterization commit."""
    import subprocess
    out = subprocess.run(["git", "diff", "--quiet", "48d4685", "--", "ka/tests/test_plan01_phase2_governance.py", "ka/tests/test_plan01_phase6_propagation.py",
                          "ka/tests/test_plan01_api_console.py", "ka/tests/test_plan02_security_visibility.py", "ka/tests/test_plan03_assertions_binding.py",
                          "ka/tests/test_plan04_process_extraction.py", "ka/tests/test_plan05_publication.py", "ka/tests/test_plan08_connectors.py"], capture_output=True)
    assert out.returncode == 0, "a covering test changed since the characterization commit"
    diff = subprocess.run(["git", "diff", "48d4685", "--stat", "--", "ka/tests/test_plan06_profile.py"], capture_output=True, text=True).stdout
    assert "test_plan06_profile.py" in diff and "1 file changed" in diff            # exactly the documented N7 rewrite
    with pytest.raises(Exception):
        ka.governance.decide("KN-999:v1", DecisionOutcome.APPROVE, by="reviewer")


def test_N2_a_duplicate_of_a_non_active_target_is_approved_normally(ka):
    first, dup = _dup_pair(ka)
    ka.governance.decide(dup.ref, DecisionOutcome.APPROVE, by="reviewer", reason="")      # resolved as duplicate
    dup3 = ingest_policy(ka, D, "Refunds above $500 require manager approval.", title="SOP copy 3")[0]
    dup3.analysis["duplicate_of"] = dup.ref                                                # points at the REJECTED one
    ka.repo.nuggets.put(dup3)
    d = ka.governance.decide(dup3.ref, DecisionOutcome.APPROVE, by="reviewer", reason="")
    # the stale flag names a non-ACTIVE version → ordinary approval; the ACTIVE first is superseded? no — different canonical id, so both ACTIVE
    assert d.outcome == DecisionOutcome.APPROVE and not d.automatic


def test_N3_an_ordinary_reject_retires_nothing(ka):
    first = approve_all(ka, ingest_policy(ka, A, POLICY))[0]
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.", title="P2")[0]
    before = {n.ref: n.status for n in ka.repo.nuggets.all() if n.ref != cand.ref}
    nprops = len(ka.repo.proposals.all())
    d = ka.governance.decide(cand.ref, DecisionOutcome.REJECT, by="reviewer", reason="no")
    assert {n.ref: n.status for n in ka.repo.nuggets.all() if n.ref != cand.ref} == before
    assert len(ka.repo.proposals.all()) == nprops and d.resulting_refs == [] and ka.repo.require_version(first.ref).status == NuggetStatus.ACTIVE


def test_N4_reopen_ignores_non_active_links_and_zero_remaining_sources_is_still_reviewed(ka, tmp_path):
    src, priors, rep = _revoked_world(ka, tmp_path)
    # the revision has zero remaining sources yet exists, with the count on it
    rev = ka.repo.require_version(rep.reviews[0])
    assert rev.analysis["remaining_sources"] == 0 and rev.source_refs == []
    # a REJECTED version linked to the source does not spawn a review
    ka.governance.decide(rev.ref, DecisionOutcome.REJECT, by="reviewer", reason="gone")
    assert ka.governance.reopen_for_revocation(src.id, by="ops") == []


def test_N5_retirement_never_removes_a_shared_element_and_without_lineage_returns_none(ka):
    a = approve_all(ka, ingest_policy(ka, A, POLICY))[0]
    assert ka.repo.dependencies_for_nugget(a.ref)
    # a second ACTIVE nugget on the same element: duplicate statement in the same scope under a different canonical id via BOTH_VALID
    b = ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval.", title="also")[0]
    b.analysis.pop("duplicate_of", None)
    ka.repo.nuggets.put(b)
    ka.governance.decide(b.ref, DecisionOutcome.BOTH_VALID_ADD_CONTEXT, by="reviewer", reason="both")
    shared = {d.element_id for d in ka.repo.dependencies_for_nugget(a.ref)} & {d.element_id for d in ka.repo.dependencies_for_nugget(b.ref)}
    prop = ka.graph_change.propose_retirement(a, by="reviewer")
    if prop is not None:
        assert not ({c.element_id for c in prop.changes} & shared)
    lonely = ingest_policy(ka, D, "Settlement occurs two business days after clearing.")[0]
    assert ka.graph_change.propose_retirement(lonely, by="reviewer") is None


def test_N6_agents_cannot_trigger_keep_existing_and_provenance_needs_a_governed_target(ka):
    first, dup = _dup_pair(ka)
    from ka.governance import GovernanceError
    agent = next(iter(ka.governance.research_agent_ids))
    with pytest.raises(GovernanceError):
        ka.governance.decide(dup.ref, DecisionOutcome.APPROVE, by=agent, reason="")
    cand = ingest_policy(ka, A, POLICY)[0]
    with pytest.raises(GovernanceError, match="governed version only"):
        ka.governance.attach_provenance(cand.ref, dup, by="reviewer")
