"""plan-25 (research-04 R2, R3, R4, R9, R13; Q17, Q19, Q20; product tests PT1, PT2, PT8, PT12) — the Knowledge Wiki, read side: articles
computed on read from ACTIVE versions at a visibility ceiling, every sentence cited; staleness by digest; wiki search at the ceiling;
model prose behind a verifier; reading writes nothing; tabs 1–6 untouched."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.governance import CandidateInput
from ka.llm import StubLLMProvider
from ka.model import Evidence, Subject, WikiPublication
from ka.tests.conftest import D, approve_all
from ka.tests.test_plan06_profile import _sop_profile
from ka.vocab import DecisionOutcome, Visibility
from ka.wiki import REF_MARK

ROOT = Path(__file__).resolve().parents[2]


def _subject_nuggets(ka, n=5, *, visibility=Visibility.ENTERPRISE, key="refund_policy", kind="entity", secret=False):
    """n ACTIVE nuggets on one subject from three independent sources (PT1's shape); `secret` gives distinct PERSONAL statements."""
    # three ENTERPRISE sources (a note would be PERSONAL and governance narrows every revision to its sources' visibility — §10)
    sources = [ka.ingestion.upload(filename=f"refund-source-{k}.md", data=f"Refund policy source {k}: refunds need approval by amount.\n".encode(), owner="u", scope=D,
                                   visibility=Visibility.ENTERPRISE).source for k in range(3)]
    out = []
    for i in range(n):
        st = f"Secret override code {4242 + i} unlocks any refund." if secret else f"Refunds above ${100 * (i + 1)} need approval level {i}."
        src = sources[i % 3]
        ev = ka.repo.evidence.put(Evidence(source_id=src.id, source_version_id=src.current_version_id, span_id=f"s{i + 1}", start=0, end=len(st), excerpt=st,
                                           locator=f"¶{i + 1}", created_by="u", visibility=visibility))
        v = ka.governance.ingest_candidate(CandidateInput(title=f"rule {i}", statement=st, scope=D, source_ids=[src.id], evidence_ids=[ev.id],
                                                          subject=Subject(kind=kind, canonical_key=key, name="Refund policy"), predicate="governed_by",
                                                          binding_method="evidenced", created_by="u", visibility=visibility))
        out.append(v)
    approve_all(ka, out)
    return [ka.repo.require_version(v.ref) for v in out]


def _text(a):
    return " ".join(b["text"] for b in a["blocks"])


def test_P1_PT1_five_nuggets_from_three_sources_become_one_cited_article(ka):
    vs = _subject_nuggets(ka)
    a = ka.wiki.article("subject:refund_policy")
    assert a["kind"] == "subject" and a["title"] == "Refund policy" and set(a["refs"]) == {v.ref for v in vs}
    paras = [b for b in a["blocks"] if b["kind"] == "paragraph"]
    assert paras and all(len(REF_MARK.findall(b["text"])) == len(b["refs"]) for b in paras)       # every sentence carries its citation
    assert all(ka.repo.require_version(r).status.value == "ACTIVE" for b in paras for r in b["refs"])
    assert len(a["sources"]) == 3
    ev = ka.wiki.evidence("subject:refund_policy")
    assert {i["ref"] for i in ev["items"]} == set(a["refs"]) and all(i["evidence"] and i["evidence"][0]["source_title"] for i in ev["items"])


def test_P2_PT12_a_process_article_follows_the_template_and_lists_what_is_not_known(ka):
    _sop_profile(ka)
    a = ka.wiki.article("process:merchant_underwriting")
    heads = [b["text"] for b in a["blocks"] if b["kind"] == "heading"]
    assert heads[:2] == ["Merchant underwriting", "What it is"] and "Activities" in heads and "Actors" in heads
    assert "Inputs" not in heads and "Rules" not in heads                      # unevidenced sections are omitted
    lst = next(b for b in a["blocks"] if b["kind"] == "list")
    assert [i["text"] for i in lst["items"]][:2] == ["Collect application", "Validate application"] and lst["ordered"]
    assert isinstance(a["not_known"], list) and isinstance(a["pending"], list)
    assert heads.index("Activities") < heads.index("Actors")


def test_P3_a_scope_article_groups_by_subject_then_knowledge_type(ka):
    _subject_nuggets(ka, 2)
    got = ka.ingestion.write_note(text="Settlement runs nightly.", owner="u", scope=D)
    loose = ka.governance.ingest_candidate(CandidateInput(title="settlement", statement="Settlement runs nightly.", scope=D, source_ids=[got.source.id], evidence_ids=[], created_by="u",
                                                          visibility=Visibility.ENTERPRISE))        # a note is PERSONAL by default — the ceiling would hide it
    approve_all(ka, [loose])
    a = ka.wiki.article("scope:DOMAIN|merchant-acquiring")
    heads = [b["text"] for b in a["blocks"] if b["kind"] == "heading"]
    assert heads[0] == "Merchant Acquiring" or heads[0] == "merchant-acquiring"
    assert "Refund policy" in heads and "General" in heads and heads.index("Refund policy") < heads.index("General")
    assert loose.ref in a["refs"]


def test_P4_digest_moves_with_governance_and_stale_follows_the_last_publication(ka):
    vs = _subject_nuggets(ka, 2)
    key = "subject:refund_policy"
    st0 = ka.wiki.stale(key)
    assert st0 == {"published": False, "stale": False, "digest": st0["digest"], "published_digest": None, "published_at": None}
    ka.repo.wiki_publications.put(WikiPublication(page_key=key, layout_rev=0, digest=ka.wiki.digest(key), manifest=ka.wiki.manifest(key), by="u"))
    assert ka.wiki.stale(key)["stale"] is False and ka.wiki.article(key)["published"] is True
    rev = ka.governance.propose_revision(vs[0].canonical_id, statement="Refunds above $100 need approval level 9.", by="u", reason="test",
                                         subject=vs[0].subject, predicate=vs[0].predicate)        # explicit, as the wiki's reconciliation will pass them
    ka.governance.decide(rev.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    st = ka.wiki.stale(key)
    assert st["stale"] is True and st["digest"] != st["published_digest"] and rev.ref in ka.wiki.manifest(key) and vs[0].ref not in ka.wiki.manifest(key)


def test_P5_PT8_a_revoked_source_marks_statements_and_the_source(ka):
    vs = _subject_nuggets(ka, 2)
    src = ka.repo.sources.require(vs[0].source_refs[0])
    ka.connectors.revoke_source(src, by="ops", reason="test")
    a = ka.wiki.article("subject:refund_policy")
    flagged = [f for b in a["blocks"] for f in b.get("flags", [])]
    assert flagged and flagged[0]["ref"] == vs[0].ref and "re-review pending" in flagged[0]["flag"]
    assert any(s["id"] == src.id and s["revoked_at"] for s in a["sources"])
    assert any(i["source_revoked"] for i in ka.wiki.evidence("subject:refund_policy")["items"])


def test_P6_wiki_search_finds_pages_by_title_and_statement_words(ka):
    _subject_nuggets(ka, 3)
    hits = ka.wiki.search("refund policy")
    assert hits and hits[0]["key"] == "subject:refund_policy" and hits[0]["kind"] == "subject" and hits[0]["snippet"]
    assert any(h["key"] == "subject:refund_policy" for h in ka.wiki.search("approval level"))
    assert ka.wiki.search("") == []


def test_P7_model_prose_is_verified_sentence_by_sentence(ka):
    vs = _subject_nuggets(ka, 2)
    r0, r1 = vs[0].ref, vs[1].ref
    ka.wiki.provider = StubLLMProvider(default_response=f"Refunds need approval at two levels. [[{r0}]] This sentence invents a fact. Approval grows with amount. [[{r1}]] Cites a stranger. [[KN-999:v1]]")
    a = ka.wiki.article("subject:refund_policy", prose="llm")
    para = next(b for b in a["blocks"] if b["kind"] == "paragraph")
    assert para["origin"] == "synthesized" and para["dropped"] == 2
    assert all(set(REF_MARK.findall(s)) <= {r0, r1} and REF_MARK.findall(s) for s in re.split(r"(?<=\]\])\s+", para["text"]))
    plain = ka.wiki.article("subject:refund_policy")
    assert all(b["origin"] == "projected" for b in plain["blocks"])              # off by default (Q20)


def test_P8_routes_and_flow_exist(ka):
    _subject_nuggets(ka, 2)
    c = TestClient(create_app(ka))
    assert c.get(f"{PREFIX}/wiki/pages").json()["subjects"][0]["key"] == "subject:refund_policy"
    a = c.get(f"{PREFIX}/wiki/pages/subject:refund_policy").json()
    assert a["kind"] == "subject" and a["blocks"]
    assert c.get(f"{PREFIX}/wiki/pages/subject:refund_policy/evidence").json()["items"]
    assert c.get(f"{PREFIX}/wiki/search?q=refund").json()["hits"]
    assert c.get(f"{PREFIX}/wiki/pages/subject:refund_policy?prose=weird").status_code == 400
    set_ka(None)
    assert (ROOT / "e2e" / "plan25_wiki_flow.py").exists()


def test_N1_PT2_a_personal_nugget_never_enters_an_enterprise_page_or_search(ka):
    public = _subject_nuggets(ka, 2)
    secret = _subject_nuggets(ka, 1, visibility=Visibility.PERSONAL, secret=True)[0]
    a = ka.wiki.article("subject:refund_policy")
    assert secret.ref not in a["refs"] and secret.ref not in _text(a) and {v.ref for v in public} <= set(a["refs"])
    assert secret.ref not in {i["ref"] for i in ka.wiki.evidence("subject:refund_policy")["items"]}
    assert all("override code" not in h["snippet"] for h in ka.wiki.search("approval level override code"))
    assert secret.ref in {v.ref for v in ka.wiki.select("subject:refund_policy", Visibility.PERSONAL)}   # a PERSONAL ceiling would show it


def test_N2_pending_and_superseded_versions_never_enter_paragraphs(ka):
    vs = _subject_nuggets(ka, 2)
    rev = ka.governance.propose_revision(vs[0].canonical_id, statement="Refunds above $100 need approval level 7.", by="u", reason="t",
                                         subject=vs[0].subject, predicate=vs[0].predicate)
    a = ka.wiki.article("subject:refund_policy")
    assert rev.ref not in a["refs"] and any(p["ref"] == rev.ref for p in a["pending"])
    ka.governance.decide(rev.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    a2 = ka.wiki.article("subject:refund_policy")
    assert rev.ref in a2["refs"] and vs[0].ref not in a2["refs"] and ka.repo.require_version(vs[0].ref).status.value == "SUPERSEDED"


def test_N3_reading_writes_nothing(ka):
    _subject_nuggets(ka, 2)
    before = {p: p.read_bytes() for p in (ka.repo.root / "nuggets").glob("*.json")}
    ka.wiki.article("subject:refund_policy"); ka.wiki.evidence("subject:refund_policy"); ka.wiki.search("refund"); ka.wiki.list_pages()
    assert {p: p.read_bytes() for p in (ka.repo.root / "nuggets").glob("*.json")} == before
    assert ka.repo.wiki_pages.all() == [] and ka.repo.wiki_publications.all() == [] and not (ka.repo.root / "wiki_pages").exists()


def test_N4_unknown_empty_and_malformed_keys(ka):
    c = TestClient(create_app(ka))
    assert c.get(f"{PREFIX}/wiki/pages/subject:nobody").status_code == 404
    _subject_nuggets(ka, 1, visibility=Visibility.PERSONAL, secret=True)      # exists, but nothing at the ENTERPRISE ceiling
    r = c.get(f"{PREFIX}/wiki/pages/subject:refund_policy")
    assert r.status_code == 404 and "no governed knowledge yet" in r.json()["detail"]
    assert c.get(f"{PREFIX}/wiki/pages/bogus").status_code == 400 and c.get(f"{PREFIX}/wiki/pages/scope:NOPE|x").status_code == 400
    set_ka(None)


def test_N5_tabs_one_to_six_and_the_existing_routes_are_unchanged():
    head = subprocess.run(["git", "show", "HEAD:ka/console/app.js"], cwd=ROOT, capture_output=True, text=True).stdout
    now = (ROOT / "ka/console/app.js").read_text()
    labels = re.compile(r"'#/(add|nuggets|browse|processes|dashboard|images)': '[^']+'")
    assert labels.findall(head) == labels.findall(now)
    routes_head = re.search(r"const routes = \[(.*?)\n\];", head, re.S).group(1).strip().splitlines()
    routes_now = re.search(r"const routes = \[(.*?)\n\];", now, re.S).group(1).strip().splitlines()
    assert routes_now[:len(routes_head) - 1] == routes_head[:-1] and routes_now[-1] == routes_head[-1]   # only insertions before the redirect
