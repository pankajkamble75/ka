"""plan-07 (research-01 R9; product test PT7) — discovery before fetching: provider seam, canonical URLs, robots, allow-list, budget,
provenance on fetched sources. No network: `ka.security._resolve` and `safe_fetch` are patched."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config, security
from ka.api import PREFIX, create_app, set_ka
from ka.discovery import DiscoveryAgent, FixtureSearchProvider, NullSearchProvider, RobotsCache, canonical_url, select_provider
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S
from ka.vocab import AuthorityType, MissionStatus, RunStatus

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "search_fixture.json"
PAGES = {
    "https://rules.example.com/visa/disputes": b"<html><body><h2>Disputes</h2><p>Visa dispute responses must be submitted within 30 days.</p></body></html>",
    "https://rules.example.com/visa/windows": b"<html><body><p>The dispute response window is 30 days for all merchants.</p></body></html>",
    "https://news.example.com/windows": b"<html><body><p>Dispute windows must be respected by acquirers.</p></body></html>",
    "https://blog.example.net/private/notes": b"<html><body><p>Private notes must not be fetched.</p></body></html>",
}
ROBOTS = {"https://blog.example.net": b"User-agent: enterprise-os-ka\nDisallow: /private\n", "https://rules.example.com": b"User-agent: *\nAllow: /\n"}


@dataclass
class Fetched:
    url: str
    content: bytes
    content_type: str = "text/html"
    hops: list = None


def _fake_fetch(url, timeout=20.0, **kw):
    if url.endswith("/robots.txt"):
        host = url[: -len("/robots.txt")]
        if host in ROBOTS:
            return Fetched(url, ROBOTS[host])
        raise ConnectionError("no robots")
    if url in PAGES:
        return Fetched(url, PAGES[url])
    raise ConnectionError(f"no page for {url}")


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setattr(security, "_resolve", lambda host: ["93.184.216.34"])
    monkeypatch.setattr(security, "safe_fetch", _fake_fetch)
    import ka.ingestion
    monkeypatch.setattr(ka.ingestion, "safe_fetch", _fake_fetch)


INTERNET_REPLY = json.dumps([{"title": "Dispute response window", "statement": "Visa dispute responses must be submitted within 30 days.",
                              "knowledge_type": "rule", "excerpt": "submitted within 30 days", "confidence": 0.7}])
LLM_REPLY = json.dumps([{"title": "LLM recollection", "statement": "Disputes are usually answered within a month.", "knowledge_type": "fact",
                         "excerpt": "model knowledge", "confidence": 0.4}])


def _ka(tmp_path, **env):
    with config.scoped(KA_SEARCH_PROVIDER="fixture", KA_SEARCH_FIXTURE=str(FIXTURE), **env):
        # the model is stubbed: it "reads" fetched pages into findings and also offers its own recollection (LLM_GENERATED)
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(responses={"Internet Research Agent": INTERNET_REPLY, "LLM Knowledge Agent": LLM_REPLY}),
                                  auto_approve_low_impact=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        m = ka.research.create_mission(scope=D, objective="Visa dispute processing rules", by="u", questions=["What is the dispute response window?"])
        return ka, m


def _run(ka, m, **env):
    with config.scoped(KA_SEARCH_PROVIDER="fixture", KA_SEARCH_FIXTURE=str(FIXTURE), **env):
        return ka.research.run_mission(m.mission_id)


def test_P1_fixture_and_null_providers():
    p = FixtureSearchProvider(FIXTURE)
    assert [r.rank for r in p.search("Visa dispute processing rules", limit=10)] == [1, 2, 3, 4, 5]
    near = p.search("visa dispute rules processing", limit=2)
    assert len(near) == 2 and near[0].query == "visa dispute rules processing"
    assert p.search("completely unrelated soup", limit=5) == [] and NullSearchProvider().search("x", limit=5) == []


def test_P2_canonical_url_strips_fragments_and_tracking_parameters():
    assert canonical_url("https://Rules.Example.com/visa/disputes?utm_source=x&fbclid=1#top") == "https://rules.example.com/visa/disputes"
    assert canonical_url("https://rules.example.com/visa/disputes?utm_source=y") == canonical_url("https://rules.example.com/visa/disputes?gclid=z")
    assert canonical_url("https://a.example.com/p?page=2&utm_x=1") == "https://a.example.com/p?page=2"


def test_P3_robots_cache_honours_disallow_and_records_unreachable(net):
    rc = RobotsCache(fetch=_fake_fetch)
    assert rc.allowed("https://blog.example.net/private/notes") == (False, "robots disallows")
    assert rc.allowed("https://blog.example.net/public") [0] is True
    ok, why = rc.allowed("https://nobots.example.com/x")
    assert ok and "unreachable" in why and rc.notes


def test_P4_queries_come_from_the_objective_and_questions(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=False)
    assert run.discovery["queries"] == ["Visa dispute processing rules", "What is the dispute response window?"] and run.discovery["provider"] == "fixture"


def test_P5_selection_ranks_by_overlap_and_respects_the_budget(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=False, KA_DISCOVERY_BUDGET=2)
    sel = [r["url"] for r in run.discovery["selected"]]
    assert sel[0] == "https://rules.example.com/visa/disputes" and len(sel) == 2
    assert any(x["reason"] == "budget" for x in run.discovery["skipped"])
    assert any(x["reason"].startswith("duplicate") for x in run.discovery["skipped"])


def test_P6_fetched_sources_carry_provenance_and_internet_authority(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=True, KA_DISCOVERY_BUDGET=3)
    assert run.status == RunStatus.COMPLETED and run.discovery["fetched"]
    srcs = [ka.repo.sources.get(s) for s in run.sources_examined]
    web = [s for s in srcs if s.metadata.get("canonical_url")]
    assert web and all(s.authority_type == AuthorityType.INTERNET_RESEARCH and s.metadata["retrieved_at"] and "query" in s.metadata for s in web)
    first = next(s for s in web if s.metadata["canonical_url"] == "https://rules.example.com/visa/disputes")
    assert first.metadata["publisher"] == "Example Rules Co" and first.metadata["published_at"] == "2026-03-01"
    unknown = next(s for s in web if s.metadata["canonical_url"] == "https://rules.example.com/visa/windows")
    assert unknown.metadata["published_at"] is None


def test_P7_PT7_candidates_come_from_fetched_urls_and_no_model_answer_poses_as_an_internet_source(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=True)
    m = ka.repo.missions.require(m.mission_id)
    assert run.status == RunStatus.COMPLETED and m.status == MissionStatus.COMPLETED and m.candidate_refs
    for ref in m.candidate_refs:
        v = ka.repo.require_version(ref)
        for s in ka.repo.sources_for(v):
            if v.authority_type == AuthorityType.INTERNET_RESEARCH:
                assert s.metadata.get("canonical_url", "").startswith("https://") and s.metadata.get("retrieved_at")
            if s.authority_type == AuthorityType.LLM_GENERATED:
                assert "canonical_url" not in s.metadata and s.source_type.value == "research"
    assert any(ka.repo.require_version(r).authority_type == AuthorityType.INTERNET_RESEARCH for r in m.candidate_refs)


@pytest.fixture
def client(tmp_path, net):
    ka, m = _ka(tmp_path)
    with config.scoped(KA_SEARCH_PROVIDER="fixture", KA_SEARCH_FIXTURE=str(FIXTURE), KA_RESEARCH_INTERNET=False):
        ka.research.run_mission(m.mission_id)
        c = TestClient(create_app(ka))
        yield c, m
    set_ka(None)


def test_P8_providers_route_and_mission_detail_carry_discovery(client):
    c, m = client
    with config.scoped(KA_SEARCH_PROVIDER="fixture", KA_SEARCH_FIXTURE=str(FIXTURE)):
        p = c.get(f"{PREFIX}/research/providers").json()
        assert p["search_provider"] == "fixture" and p["decision"] == "Q5" and p["respect_robots"] is True
        d = c.get(f"{PREFIX}/research/missions/{m.mission_id}").json()
        assert d["runs"][0]["discovery"]["provider"] == "fixture" and d["runs"][0]["discovery"]["queries"]


def test_N1_no_provider_means_nothing_selected_and_the_mission_still_completes(tmp_path, net):
    with config.scoped(KA_SEARCH_PROVIDER="none", KA_RESEARCH_INTERNET=True):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        m = ka.research.create_mission(scope=D, objective="Visa dispute processing rules", by="u")
        run = ka.research.run_mission(m.mission_id)
    assert run.discovery["provider"] == "none" and "no search provider (Q5)" in run.discovery["notes"]
    assert run.discovery["selected"] == [] and run.discovery["fetched"] == [] and ka.repo.missions.require(m.mission_id).status in {MissionStatus.COMPLETED, MissionStatus.FAILED}


def test_N2_disallowed_domains_and_unsafe_hosts_are_skipped_never_fetched(tmp_path, net, monkeypatch):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=True, KA_ALLOWED_DOMAINS="rules.example.com, news.example.com")
    reasons = {x["url"]: x["reason"] for x in run.discovery["skipped"]}
    assert reasons["https://other.example.org/unrelated"] == "domain not allowed"
    assert reasons["https://blog.example.net/private/notes"] == "domain not allowed"
    assert all(u.startswith(("https://rules.example.com", "https://news.example.com")) for u in run.discovery["fetched"])
    # the private-address result: with no allow-list it is caught by the URL guard
    monkeypatch.setattr(security, "_resolve", lambda host: ["93.184.216.34"])
    ka2, m2 = _ka(tmp_path / "b")
    run2 = _run(ka2, m2, KA_RESEARCH_INTERNET=True)
    assert any(x["url"].startswith("http://10.0.0.7") and x["reason"].startswith("unsafe url") for x in run2.discovery["skipped"])
    assert not any(u.startswith("http://10.") for u in run2.discovery["fetched"])


def test_N3_robots_disallow_is_honoured_unless_told_otherwise(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=True, KA_DISCOVERY_BUDGET=10)
    assert any(x["url"] == "https://blog.example.net/private/notes" and x["reason"] == "robots" for x in run.discovery["skipped"])
    assert "https://blog.example.net/private/notes" not in run.discovery["fetched"]
    ka2, m2 = _ka(tmp_path / "b")
    run2 = _run(ka2, m2, KA_RESEARCH_INTERNET=True, KA_DISCOVERY_BUDGET=10, KA_RESPECT_ROBOTS=False)
    assert "https://blog.example.net/private/notes" in run2.discovery["fetched"] and any("robots.txt ignored" in n for n in run2.discovery["notes"])


def test_N4_gate_off_records_selection_as_skipped_and_fetches_nothing(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=False)
    assert run.discovery["selected"] and run.discovery["fetched"] == []
    assert all(x["reason"].startswith("gate off") for x in run.discovery["skipped"] if x["url"] in {r["url"] for r in run.discovery["selected"]})
    assert ka.repo.missions.require(m.mission_id).status in {MissionStatus.COMPLETED, MissionStatus.FAILED}


def test_N5_a_raising_provider_is_isolated(tmp_path, net):
    class Boom:
        name = "boom"
        def search(self, query, *, limit):
            raise RuntimeError("provider down")
    with config.scoped(KA_RESEARCH_INTERNET=True):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(responses={"Domain Research Agent": json.dumps([{"title": "x", "statement": "Settlement occurs after clearing.", "knowledge_type": "fact", "excerpt": "e", "confidence": 0.6}])}))
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        ka.research.agents[0] = DiscoveryAgent(provider=Boom())
        m = ka.research.create_mission(scope=D, objective="settlement", by="u")
        run = ka.research.run_mission(m.mission_id)
    assert any("provider down" in e for e in run.errors) and run.candidate_nuggets_created and run.status == RunStatus.COMPLETED


def test_N6_unknown_provider_value_fails_closed():
    with config.scoped(KA_SEARCH_PROVIDER="google-magic"):
        p, note = select_provider()
    assert p.name == "none" and "failing closed" in note


def test_N7_the_budget_is_per_mission_not_per_query(tmp_path, net):
    ka, m = _ka(tmp_path)
    run = _run(ka, m, KA_RESEARCH_INTERNET=True, KA_DISCOVERY_BUDGET=3, KA_DISCOVERY_RESULTS=4)
    assert len(run.discovery["fetched"]) == 3 and len(run.discovery["selected"]) == 3
