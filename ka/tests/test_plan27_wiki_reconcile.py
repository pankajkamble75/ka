"""plan-27 (research-04 R6, builds R7/Q18; product tests PT3, PT5, PT6, PT7) — reconciliation: a submitted draft becomes governance
operations through the one pipeline; deleting prose retires nothing; an explicit retirement request becomes a reviewable revision whose
REJECT retires the prior; the protected change leaves every covering suite byte-identical."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.governance import GovernanceError
from ka.tests.test_plan25_wiki_read import _subject_nuggets
from ka.vocab import DecisionOutcome, NuggetStatus
from ka.wiki_markdown import to_markdown

ROOT = Path(__file__).resolve().parents[2]
KEY = "subject:refund_policy"


def _draft(ka, by="editor"):
    d = ka.wiki.start_draft(KEY, by=by)
    return d, ka.wiki.draft_markdown(d)


def _para(md, old, new):
    assert old in md
    return md.replace(old, new)


def _snapshot(ka):
    return ({p: p.read_bytes() for p in (ka.repo.root / "nuggets").glob("*.json")}, ka.wiki.article(KEY)["blocks"], len(ka.repo.proposals.all()))


def test_P2_PT7_one_changed_claim_in_a_three_citation_paragraph_yields_one_revision(ka):
    vs = _subject_nuggets(ka, 3)
    d, md = _draft(ka)
    md = _para(md, "need approval level 1.", "need approval level 11.")
    ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="editor")
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    cls = sorted(o["cls"] for o in c["operations"])
    assert cls == ["LINK_EXISTING", "LINK_EXISTING", "PROPOSE_REVISION"]
    target = next(o for o in c["operations"] if o["cls"] == "PROPOSE_REVISION")
    assert target["target_ref"] == vs[1].ref
    ka.wiki.submit_draft(d.id, by="editor")
    prop = ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id)
    assert len(prop.produced_refs) == 1
    rev = ka.repo.require_version(prop.produced_refs[0])
    assert rev.canonical_id == vs[1].canonical_id and rev.version == 2 and rev.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT}
    assert rev.subject == vs[1].subject and rev.predicate == vs[1].predicate and "level 11" in rev.statement
    assert all(ka.repo.require_version(v.ref).status == NuggetStatus.ACTIVE for v in vs)              # untouched until a decision


def test_P3_PT3_a_new_sentence_becomes_a_candidate_and_nothing_governed_moves(ka):
    vs = _subject_nuggets(ka, 2)
    before = _snapshot(ka)
    d, md = _draft(ka)
    md = _para(md, "need approval level 1.", "need approval level 1. Refunds in cash are collected by the store manager at closing.")
    ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="editor")
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    assert "ADD_CANDIDATE" in {o["cls"] for o in c["operations"]}
    ka.wiki.submit_draft(d.id, by="editor")
    prop = ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id)
    cands = [ka.repo.require_version(r) for r in prop.produced_refs]
    assert len(cands) == 1 and cands[0].status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT} and cands[0].channel.value == "FEEDBACK"
    assert cands[0].scope == vs[0].scope and cands[0].evidence_refs and cands[0].subject == vs[0].subject
    src = ka.repo.sources.require(cands[0].source_refs[0])
    assert src.channel.value == "FEEDBACK" and "Wiki draft" in src.title
    nuggets_before, art_before, props_before = before
    now = {p: p.read_bytes() for p in (ka.repo.root / "nuggets").glob("*.json")}
    assert all(now[p] == b for p, b in nuggets_before.items())                   # existing versions untouched (new files are the candidate)
    assert ka.wiki.article(KEY)["blocks"] == art_before and len(ka.repo.proposals.all()) == props_before


def test_P4_PT5_editorial_only_changes_produce_nothing(ka):
    vs = _subject_nuggets(ka, 2)
    d, md = _draft(ka)
    md = md.replace("## Fact", "## Facts about refunds").replace("Refunds above $100", "Refunds above **$100**")
    ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="editor")
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    assert c["operations"] and {o["cls"] for o in c["operations"]} == {"EDITORIAL_ONLY"}
    ka.wiki.submit_draft(d.id, by="editor")
    prop = ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id)
    assert prop.produced_refs == [] and len(ka.repo.nuggets.all()) == 2


def test_P5_PT6a_deleting_a_paragraph_retires_nothing(ka):
    vs = _subject_nuggets(ka, 2)
    d, md = _draft(ka)
    blocks = ka.repo.wiki_drafts.require(d.id).blocks
    md = to_markdown([b for b in blocks if b["kind"] != "paragraph"])
    ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="editor")
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    dele = [o for o in c["operations"] if o["op"] == "delete"]
    assert dele and all(o["cls"] == "EDITORIAL_ONLY" and "retires nothing" in o["note"] for o in dele)
    ka.wiki.submit_draft(d.id, by="editor")
    assert all(ka.repo.require_version(v.ref).status == NuggetStatus.ACTIVE for v in vs)


def test_P6_PT6b_a_retirement_request_becomes_a_reviewable_revision_and_reject_retires(ka):
    vs = _subject_nuggets(ka, 2)
    d, md = _draft(ka)
    ka.wiki.add_request(d.id, kind="retire", ref=vs[0].ref, why="superseded by the 2026 policy", by="editor")
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    assert [o["cls"] for o in c["operations"]] == ["PROPOSE_RETIREMENT"]
    ka.wiki.submit_draft(d.id, by="editor")
    prop = ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id)
    rev = ka.repo.require_version(prop.produced_refs[0])
    assert rev.canonical_id == vs[0].canonical_id and rev.statement == vs[0].statement and rev.analysis["retirement_requested"]["by"] == "editor"
    assert ka.repo.require_version(vs[0].ref).status == NuggetStatus.ACTIVE          # until a person decides
    dec = ka.governance.decide(rev.ref, DecisionOutcome.REJECT, by="reviewer", reason="agreed, retire it")
    prior = ka.repo.require_version(vs[0].ref)
    assert prior.status == NuggetStatus.OBSOLETE and prior.ref in dec.related_refs and any("retirement requested" in c["text"] for c in prior.comments)
    assert vs[0].ref not in ka.wiki.manifest(KEY) and vs[1].ref in ka.wiki.manifest(KEY)
    # APPROVE on another request keeps the knowledge (the same-statement revision becomes the ACTIVE version)
    ka.wiki.close_draft(d.id, by="editor")                                             # plan-28 resolves proposals; here the editor closes
    d2, _ = _draft(ka, by="other")
    ka.wiki.add_request(d2.id, kind="retire", ref=vs[1].ref, why="not sure", by="other")
    ka.wiki.submit_draft(d2.id, by="other")
    rev2 = ka.repo.require_version(ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d2.id).proposal_id).produced_refs[0])
    ka.governance.decide(rev2.ref, DecisionOutcome.APPROVE, by="reviewer", reason="still true")
    assert ka.repo.require_version(rev2.ref).status == NuggetStatus.ACTIVE and ka.repo.require_version(vs[1].ref).status == NuggetStatus.SUPERSEDED


def test_P7_the_revoked_source_path_still_retires_and_covering_tests_are_unmodified(ka):
    vs = _subject_nuggets(ka, 1)
    src = ka.repo.sources.require(vs[0].source_refs[0])
    refs = ka.governance.reopen_for_revocation(src.id, by="ops")
    ka.governance.decide(refs[0], DecisionOutcome.REJECT, by="reviewer", reason="no other evidence")
    assert ka.repo.require_version(vs[0].ref).status == NuggetStatus.OBSOLETE
    # every covering suite named in docs/protected.md is byte-identical to the plan-27 characterization commit b8dce22
    out = subprocess.run(["git", "diff", "--quiet", "b8dce22", "--", "ka/tests/test_plan01_phase2_governance.py", "ka/tests/test_plan01_phase6_propagation.py",
                          "ka/tests/test_plan01_api_console.py", "ka/tests/test_plan02_security_visibility.py", "ka/tests/test_plan03_assertions_binding.py",
                          "ka/tests/test_plan04_process_extraction.py", "ka/tests/test_plan10_governance_decisions.py"], cwd=ROOT, capture_output=True)
    assert out.returncode == 0, "a covering test changed since the plan-27 characterization commit"


def test_P8_routes_and_flow(ka):
    vs = _subject_nuggets(ka, 2)
    c = TestClient(create_app(ka))
    r = c.post(f"{PREFIX}/wiki/pages/{KEY}/drafts", json={"by": "editor"}).json()
    did = r["draft"]["id"]
    md = r["markdown"].replace("need approval level 1.", "need approval level 12.")
    c.put(f"{PREFIX}/wiki/drafts/{did}", json={"text": md, "expected_rev": 0, "by": "editor"})
    rc = c.post(f"{PREFIX}/wiki/drafts/{did}/reconcile").json()
    assert rc["summary"].get("PROPOSE_REVISION") == 1
    assert c.post(f"{PREFIX}/wiki/drafts/{did}/requests", json={"ref": vs[0].ref, "why": "old", "by": "editor"}).json()["draft"]["requests"][0]["ref"] == vs[0].ref
    s = c.post(f"{PREFIX}/wiki/drafts/{did}/submit", json={"by": "editor"}).json()
    assert s["proposal_id"]
    p = c.get(f"{PREFIX}/wiki/proposals/{s['proposal_id']}").json()
    assert len(p["produced"]) == 2 and any(x["retirement_requested"] for x in p["produced"])
    set_ka(None)
    assert (ROOT / "e2e" / "plan27_reconcile_flow.py").exists()


def test_N1_an_uncited_absolute_claim_on_an_unscoped_authored_page_needs_evidence(ka):
    _subject_nuggets(ka, 1)
    from ka.vocab import Visibility
    pg, d = ka.wiki.create_page(slug="handbook", title="Handbook", scope=None, ceiling=Visibility.ENTERPRISE, by="editor")
    ka.wiki.save_draft(d.id, text="<!-- n1 -->\n# Handbook\n\nAll refunds must be countersigned within 48 hours.\n", expected_rev=0, by="editor")
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    assert [o["cls"] for o in c["operations"] if o["op"] == "insert"] == ["NEEDS_EVIDENCE"]
    ka.wiki.submit_draft(d.id, by="editor")
    prop = ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id)
    assert prop.produced_refs == [] and any(o["cls"] == "NEEDS_EVIDENCE" for o in prop.operations)


def test_N2_a_changed_paragraph_with_nothing_extractable_is_unresolved(ka, monkeypatch):
    _subject_nuggets(ka, 2)
    d, md = _draft(ka)
    md = _para(md, "need approval level 1.", "need approval level 1. Lorem ipsum dolor sit amet consectetur adipiscing elit sed.")
    ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="editor")
    monkeypatch.setattr(ka.wiki.reconciler.extractor, "extract", lambda **kw: [])
    c = ka.wiki.reconciler.classify(ka.repo.wiki_drafts.require(d.id))
    assert [o["cls"] for o in c["operations"]] == ["UNRESOLVED"]
    ka.wiki.submit_draft(d.id, by="editor")
    assert ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id).produced_refs == []


def test_N3_request_retirement_refuses_agents_skips_pending_and_unknown(ka):
    vs = _subject_nuggets(ka, 1)
    agent = next(iter(ka.governance.research_agent_ids)) if ka.governance.research_agent_ids else "research-agent"
    ka.governance.research_agent_ids = set(ka.governance.research_agent_ids) | {agent}
    with pytest.raises(GovernanceError):
        ka.governance.request_retirement(vs[0].canonical_id, by=agent, why="x")
    first = ka.governance.request_retirement(vs[0].canonical_id, by="u", why="first")
    assert first is not None and ka.governance.request_retirement(vs[0].canonical_id, by="u", why="again") is None
    with pytest.raises(GovernanceError):
        ka.governance.request_retirement("KN-999", by="u", why="x")


def test_N4_an_ordinary_reject_still_retires_nothing_after_the_change(ka):
    vs = _subject_nuggets(ka, 1)
    rev = ka.governance.propose_revision(vs[0].canonical_id, statement=vs[0].statement, by="u", reason="plain revision")
    ka.governance.decide(rev.ref, DecisionOutcome.REJECT, by="reviewer", reason="no")
    assert ka.repo.require_version(vs[0].ref).status == NuggetStatus.ACTIVE


def test_N5_submitting_twice_creates_no_second_proposal(ka):
    _subject_nuggets(ka, 2)
    d, md = _draft(ka)
    ka.wiki.save_draft(d.id, text=_para(md, "need approval level 1.", "need approval level 13."), expected_rev=0, by="editor")
    ka.wiki.submit_draft(d.id, by="editor")
    with pytest.raises(PermissionError):
        ka.wiki.submit_draft(d.id, by="editor")
    assert len(ka.repo.wiki_proposals.all()) == 1
    c = TestClient(create_app(ka))
    assert c.post(f"{PREFIX}/wiki/drafts/{d.id}/submit", json={"by": "editor"}).status_code == 409
    set_ka(None)
