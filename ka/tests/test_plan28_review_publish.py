"""plan-28 (research-04 R8; product tests PT4, PT11) — review: side-by-side blocks, produced candidates with status/conflicts/graph
proposals; decisions through the existing decide path resolve the proposal; publication records a digest, applies an authored layout,
is idempotent; graph proposals are shown and never advanced; publication writes no nugget, decision or graph proposal."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.tests.conftest import D
from ka.tests.test_plan25_wiki_read import _subject_nuggets
from ka.vocab import DecisionOutcome, NuggetStatus, Visibility

ROOT = Path(__file__).resolve().parents[2]
KEY = "subject:refund_policy"


def _submitted(ka, change=("need approval level 1.", "need approval level 21. Cash refunds are logged by the cashier at closing."), by="editor"):
    d = ka.wiki.start_draft(KEY, by=by)
    md = ka.wiki.draft_markdown(d).replace(*change)
    ka.wiki.save_draft(d.id, text=md, expected_rev=0, by=by)
    ka.wiki.submit_draft(d.id, by=by)
    d = ka.repo.wiki_drafts.require(d.id)
    return d, ka.repo.wiki_proposals.require(d.proposal_id)


def test_P1_review_shows_both_sides_and_the_open_produced_candidates(ka):
    vs = _subject_nuggets(ka, 3)
    d, p = _submitted(ka)
    r = ka.wiki.proposal_review(p.id)
    assert r["current_blocks"] and r["draft_blocks"] and len(r["produced"]) == 2 and r["resolved"] is False and r["publishable"] is False
    assert {x["status"] for x in r["produced"]} <= {"PENDING_REVIEW", "CONFLICT"} and all(x["open"] for x in r["produced"])
    assert r["pending_refs"] == [x["ref"] for x in r["produced"]] and r["page"]["key"] == KEY


def test_P2_PT4_approving_through_decide_resolves_the_proposal_and_the_article_follows(ka):
    vs = _subject_nuggets(ka, 3)
    d, p = _submitted(ka)
    r = ka.wiki.proposal_review(p.id)
    for x in r["produced"]:
        outcome = DecisionOutcome.ACCEPT_NEW if x["conflicts"] else DecisionOutcome.APPROVE
        ka.governance.decide(x["ref"], outcome, by="reviewer", reason="ok")
    r2 = ka.wiki.proposal_review(p.id)
    assert r2["resolved"] is True and r2["publishable"] is True and ka.repo.wiki_proposals.require(p.id).state == "RESOLVED"
    art = ka.wiki.article(KEY)
    text = " ".join(b["text"] for b in art["blocks"])
    assert "level 21" in text and "Cash refunds are logged" in text and vs[1].ref not in art["refs"]
    assert ka.repo.require_version(vs[1].ref).status == NuggetStatus.SUPERSEDED
    graph = [g for x in r2["produced"] for g in x["graph_changes"]]
    assert graph and all(g["status"] in {"PROPOSED", "READY", "VALIDATED", "APPROVED", "APPLIED", "FAILED"} for g in graph)   # listed, not advanced here


def test_P3_publish_after_resolution_records_the_digest_and_closes(ka):
    vs = _subject_nuggets(ka, 2)
    d, p = _submitted(ka)
    for x in ka.wiki.proposal_review(p.id)["produced"]:
        ka.governance.decide(x["ref"], DecisionOutcome.ACCEPT_NEW if x["conflicts"] else DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    out = ka.wiki.publish(KEY, by="reviewer", proposal_id=p.id)
    assert out["published"] is True and out["digest"] == ka.wiki.digest(KEY)
    pub = ka.repo.wiki_publications.require(out["publication"]["id"])
    assert pub.manifest == ka.wiki.manifest(KEY) and pub.proposal_id == p.id
    assert ka.repo.wiki_proposals.require(p.id).state == "PUBLISHED" and ka.repo.wiki_drafts.require(d.id).state == "CLOSED"
    assert ka.wiki.stale(KEY)["stale"] is False and ka.wiki.article(KEY)["published"] is True
    assert any(e["name"] == "wiki.published" for e in ka.repo.events())


def test_P4_PT11_a_second_publish_is_a_no_op_until_something_changes(ka):
    vs = _subject_nuggets(ka, 2)
    assert ka.wiki.publish(KEY, by="reviewer")["published"] is True
    again = ka.wiki.publish(KEY, by="reviewer")
    assert again["published"] is False and again["reason"] == "already published" and len(ka.repo.wiki_publications.all()) == 1
    rev = ka.governance.propose_revision(vs[0].canonical_id, statement="Refunds above $100 need approval level 5.", by="u", reason="t", subject=vs[0].subject, predicate=vs[0].predicate)
    ka.governance.decide(rev.ref, DecisionOutcome.ACCEPT_NEW if ka.repo.require_version(rev.ref).status == NuggetStatus.CONFLICT else DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    assert ka.wiki.stale(KEY)["stale"] is True
    third = ka.wiki.publish(KEY, by="reviewer")
    assert third["published"] is True and len(ka.repo.wiki_publications.all()) == 2 and ka.wiki.stale(KEY)["stale"] is False


def test_P5_an_authored_page_publication_applies_the_layout(ka):
    vs = _subject_nuggets(ka, 1)
    pg, d = ka.wiki.create_page(slug="handbook", title="Handbook", scope=D, ceiling=Visibility.ENTERPRISE, by="editor")
    ka.wiki.save_draft(d.id, text=f"<!-- n1 -->\n# Handbook\n\nSee the rule [[{vs[0].ref}]].\n", expected_rev=0, by="editor")
    ka.wiki.submit_draft(d.id, by="editor")
    p = ka.repo.wiki_proposals.require(ka.repo.wiki_drafts.require(d.id).proposal_id)
    r = ka.wiki.proposal_review(p.id)
    assert r["resolved"] and r["publishable"]
    out = ka.wiki.publish("page:handbook", by="reviewer", proposal_id=p.id)
    assert out["published"] and ka.repo.wiki_pages.require("page:handbook").layout_rev == 1
    art = ka.wiki.article("page:handbook")
    assert any("See the rule" in b["text"] for b in art["blocks"]) and art["refs"] == [vs[0].ref] and art["published"] is True


def test_P6_editorial_only_resolves_at_once_and_reject_closes(ka):
    _subject_nuggets(ka, 2)
    d, p = _submitted(ka, change=("## Fact", "## Facts about refunds"))
    r = ka.wiki.proposal_review(p.id)
    assert r["produced"] == [] and r["resolved"] and r["publishable"]
    rp = ka.wiki.reject_proposal(p.id, by="reviewer", reason="not wanted")
    assert rp.state == "REJECTED" and ka.repo.wiki_drafts.require(d.id).state == "CLOSED" and any(e["name"] == "wiki.proposal.rejected" for e in ka.repo.events())


def test_P7_routes_and_flow(ka):
    _subject_nuggets(ka, 2)
    d, p = _submitted(ka)
    c = TestClient(create_app(ka))
    assert c.get(f"{PREFIX}/wiki/proposals?state=SUBMITTED").json()["proposals"][0]["id"] == p.id
    r = c.get(f"{PREFIX}/wiki/proposals/{p.id}/review").json()
    assert r["resolved"] is False
    assert c.post(f"{PREFIX}/wiki/proposals/{p.id}/publish", json={"by": "reviewer"}).status_code == 409
    for x in r["produced"]:
        c.post(f"{PREFIX}/nugget/{x['ref']}/decide", json={"outcome": "ACCEPT_NEW" if x["conflicts"] else "APPROVE", "by": "reviewer", "reason": "ok"})
    pub = c.post(f"{PREFIX}/wiki/proposals/{p.id}/publish", json={"by": "reviewer"}).json()
    assert pub["published"] is True
    assert c.post(f"{PREFIX}/wiki/pages/{KEY}/publish", json={"by": "reviewer"}).json()["published"] is False
    assert c.post(f"{PREFIX}/wiki/proposals/WP-nope/reject", json={"by": "r"}).status_code == 404
    set_ka(None)
    assert (ROOT / "e2e" / "plan28_review_flow.py").exists()


def test_N1_publishing_an_unresolved_proposal_is_refused_naming_the_pending_refs(ka):
    _subject_nuggets(ka, 2)
    d, p = _submitted(ka)
    with pytest.raises(PermissionError, match="still await a decision"):
        ka.wiki.publish(KEY, by="reviewer", proposal_id=p.id)
    assert ka.repo.wiki_publications.all() == [] and ka.repo.wiki_proposals.require(p.id).state == "SUBMITTED"


def test_N3_unknown_proposal_and_agents_are_refused(ka):
    _subject_nuggets(ka, 1)
    with pytest.raises(KeyError):
        ka.wiki.proposal_review("WP-nope")
    agent = "research-agent"
    ka.governance.research_agent_ids = set(ka.governance.research_agent_ids) | {agent}
    with pytest.raises(PermissionError):
        ka.wiki.publish(KEY, by=agent)


def test_N4_publication_writes_no_nugget_decision_or_graph_proposal(ka):
    _subject_nuggets(ka, 2)
    snap = lambda: {p: p.read_bytes() for d in ("nuggets", "decisions", "proposals") for p in (ka.repo.root / d).glob("*.json")}  # noqa: E731
    before = snap()
    ka.wiki.publish(KEY, by="reviewer")
    assert snap() == before
