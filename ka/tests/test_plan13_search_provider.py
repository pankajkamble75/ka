"""plan-13 (research-02 R5; product test PT5 fixture-driven) — Brave behind the SearchProvider seam, the key read at call time and
never stored, a monthly cap over all missions. The live PT5 skips until the author supplies the key (Q12)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config, security
from ka.api import PREFIX, create_app, set_ka
from ka.discovery import BraveSearchProvider, NullSearchProvider, SearchMeter, provider_status, select_provider
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "brave_response.json").read_text(encoding="utf-8"))
KEY = "brv-TESTKEY-0123456789-secret"


class Fetched:
    def __init__(self, url, content): self.url, self.content, self.content_type, self.hops = url, content, "text/html", []


def _fake_fetch(url, timeout=20.0, **kw):
    if url.endswith("/robots.txt"):
        raise ConnectionError("no robots")
    return Fetched(url, b"<html><body><p>Visa dispute responses must be submitted within 30 days.</p></body></html>")


@pytest.fixture
def net(monkeypatch):
    import ka.ingestion
    monkeypatch.setattr(security, "_resolve", lambda host: ["93.184.216.34"])
    monkeypatch.setattr(security, "safe_fetch", _fake_fetch)
    monkeypatch.setattr(ka.ingestion, "safe_fetch", _fake_fetch)


def _recorder(calls):
    def fetch_json(url, headers):
        calls.append((url, dict(headers)))
        return FIXTURE
    return fetch_json


def test_P1_the_recorded_brave_response_maps_to_search_results(tmp_path):
    calls = []
    with config.scoped(KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=10):
        p = BraveSearchProvider(fetch_json=_recorder(calls), meter=SearchMeter(tmp_path / "m.json"))
        out = p.search("Visa dispute processing rules", limit=10)
    assert [r.rank for r in out] == [1, 2, 3] and out[0].url.startswith("https://rules.example.com/visa/disputes")
    assert out[0].publisher == "Example Rules Co" and out[0].published_at == "2026-03-01T00:00:00" and out[0].snippet.startswith("Visa dispute")
    assert out[1].publisher == "rules.example.com" and out[1].published_at is None and out[0].query == "Visa dispute processing rules"
    assert calls and calls[0][1]["X-Subscription-Token"] == KEY and "count=10" in calls[0][0]
    with config.scoped(KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=10):
        assert len(p.search("Visa dispute processing rules", limit=2)) == 2


def test_P2_select_provider_brave_with_a_key_and_the_meter_lives_under_storage(tmp_path):
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_API_KEY=KEY, KA_STORAGE_ROOT=str(tmp_path)):
        p, note = select_provider()
        assert isinstance(p, BraveSearchProvider) and note is None
        assert p.meter.path == tmp_path / "search_usage.json"


def test_P3_the_meter_counts_per_month_and_persists(tmp_path, monkeypatch):
    m = SearchMeter(tmp_path / "u.json")
    assert m.used() == 0
    m.record(); m.record(2)
    assert SearchMeter(tmp_path / "u.json").used() == 3 and m.remaining(10) == 7
    import ka.discovery as d
    monkeypatch.setattr(d.SearchMeter, "month", staticmethod(lambda: "2099-01"))
    assert SearchMeter(tmp_path / "u.json").used() == 0 and json.loads((tmp_path / "u.json").read_text())[SearchMeter.month().replace("2099-01", list(json.loads((tmp_path / "u.json").read_text()))[0])] == 3


INTERNET_REPLY = json.dumps([{"title": "Dispute response window", "statement": "Visa dispute responses must be submitted within 30 days.",
                              "knowledge_type": "rule", "excerpt": "submitted within 30 days", "confidence": 0.7}])


def _world(tmp_path, calls, **env):
    env = {"KA_SEARCH_PROVIDER": "brave", "KA_SEARCH_API_KEY": KEY, "KA_SEARCH_MONTHLY_CAP": 50, "KA_STORAGE_ROOT": str(tmp_path / "store"), **env}
    with config.scoped(**env):
        ka = KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider(responses={"Internet Research Agent": INTERNET_REPLY}), auto_approve_low_impact=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        ka.research.agents[0].provider = BraveSearchProvider(fetch_json=_recorder(calls), meter=SearchMeter(tmp_path / "store" / "search_usage.json"))
        ka.research.agents[0].provider_note = None
        m = ka.research.create_mission(scope=D, objective="Visa dispute processing rules", by="u", questions=["What is the dispute response window?"])
        run = ka.research.run_mission(m.mission_id)
    return ka, m, run


def test_P4_a_mission_records_results_with_publisher_and_fetched_pages_carry_provenance(tmp_path, net):
    calls = []
    ka, m, run = _world(tmp_path, calls, KA_RESEARCH_INTERNET=True, KA_DISCOVERY_BUDGET=3)
    assert run.discovery["provider"] == "brave" and len(calls) == 2
    sel = {r["url"]: r for r in run.discovery["selected"]}
    assert "https://rules.example.com/visa/disputes" in sel and sel["https://rules.example.com/visa/disputes"]["publisher"] == "Example Rules Co"
    web = [ka.repo.sources.get(s) for s in run.sources_examined]
    web = [s for s in web if s.metadata.get("canonical_url")]
    assert web and any(s.metadata["publisher"] == "Example Rules Co" and s.metadata["published_at"] == "2026-03-01T00:00:00" for s in web)
    assert SearchMeter(tmp_path / "store" / "search_usage.json").used() == 2


@pytest.fixture
def client(tmp_path):
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=50, KA_STORAGE_ROOT=str(tmp_path / "store")):
        ka = KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider())
        c = TestClient(create_app(ka))
        yield c, ka
    set_ka(None)


def test_P5_the_providers_route_reports_presence_and_usage_never_the_key(client):
    c, ka = client
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=50):
        pv = c.get(f"{PREFIX}/research/providers").json()
    assert pv["requested"] == "brave" and pv["search_provider"] == "brave" and pv["key_present"] is True
    assert pv["monthly_cap"] == 50 and pv["used_this_month"] == 0 and len(pv["month"]) == 7
    assert KEY not in json.dumps(pv)


def test_P6_the_dashboard_payload_carries_usage_and_cap(client):
    c, ka = client
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=50):
        d = c.get(f"{PREFIX}/dashboard").json()
    assert d["research"]["search_requested"] == "brave" and d["research"]["search_key_present"] is True
    assert d["research"]["search_used"] == 0 and d["research"]["search_cap"] == 50 and KEY not in json.dumps(d)


def test_P7_PT5_fixture_driven_candidates_come_from_provider_urls(tmp_path, net):
    calls = []
    ka, m, run = _world(tmp_path, calls, KA_RESEARCH_INTERNET=True)
    m = ka.repo.missions.require(m.mission_id)
    urls = {r["url"] for r in run.discovery["selected"]}
    web_cands = [ref for ref in m.candidate_refs if any(ka.repo.sources.get(s).metadata.get("canonical_url") in urls for s in ka.repo.require_version(ref).source_refs)]
    assert run.discovery["fetched"] and web_cands, "candidates came from URLs the provider returned"


@pytest.mark.skipif(not os.environ.get("KA_SEARCH_API_KEY"), reason="PT5 live needs KA_SEARCH_API_KEY (Q12 — the author's key); NOT RUN")
def test_P7b_PT5_live_search_with_the_real_key():
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_MONTHLY_CAP=1000):
        out = BraveSearchProvider().search("Visa dispute processing rules", limit=3)
    assert out and all(r.url.startswith("http") for r in out)


def test_N1_the_key_never_reaches_storage_or_the_run_record(tmp_path, net):
    calls = []
    ka, m, run = _world(tmp_path, calls, KA_RESEARCH_INTERNET=True)
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in (tmp_path / "store").rglob("*") if p.is_file())
    assert KEY not in blob and KEY not in json.dumps(run.model_dump(mode="json"))
    assert calls and all(KEY == h["X-Subscription-Token"] for _, h in calls)            # it went only to the provider


def test_N2_brave_without_a_key_fails_closed_with_the_q12_note_and_the_mission_completes(tmp_path):
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_API_KEY="", KA_RESEARCH_INTERNET=True):
        p, note = select_provider()
        assert isinstance(p, NullSearchProvider) and "Q12" in note
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        m = ka.research.create_mission(scope=D, objective="Visa dispute processing rules", by="u")
        run = ka.research.run_mission(m.mission_id)
    assert run.discovery["provider"] == "none" and any("Q12" in n for n in run.discovery["notes"])
    assert provider_status()["key_present"] is False


def test_N3_http_error_or_malformed_json_answers_nothing_with_a_note(tmp_path, net):
    def boom(url, headers):
        raise RuntimeError("502 bad gateway")
    with config.scoped(KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=10):
        p = BraveSearchProvider(fetch_json=boom, meter=SearchMeter(tmp_path / "m.json"))
        assert p.search("x", limit=5) == [] and p.last_note.startswith("search failed: RuntimeError")
        p2 = BraveSearchProvider(fetch_json=lambda u, h: {"web": "not-a-dict"}, meter=SearchMeter(tmp_path / "m2.json"))
        assert p2.search("x", limit=5) == [] and "no usable results" in p2.last_note
    calls = []
    ka, m, run = _world(tmp_path, calls, KA_RESEARCH_INTERNET=True)
    ka.research.agents[0].provider = BraveSearchProvider(fetch_json=boom, meter=SearchMeter(tmp_path / "m3.json"))
    with config.scoped(KA_SEARCH_PROVIDER="brave", KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=50, KA_RESEARCH_INTERNET=True):
        m2 = ka.research.create_mission(scope=D, objective="dispute windows", by="u")
        run2 = ka.research.run_mission(m2.mission_id)
    assert any("search failed" in n for n in run2.discovery["notes"]) and run2.status.value in {"COMPLETED", "FAILED"}


def test_N4_at_the_cap_no_call_is_made_and_the_run_says_so(tmp_path, net):
    calls = []
    with config.scoped(KA_SEARCH_API_KEY=KEY, KA_SEARCH_MONTHLY_CAP=0):
        p = BraveSearchProvider(fetch_json=_recorder(calls), meter=SearchMeter(tmp_path / "m.json"))
        assert p.search("x", limit=5) == [] and "monthly cap reached (0/0)" in p.last_note and calls == []
    ka, m, run = _world(tmp_path, calls, KA_RESEARCH_INTERNET=True, KA_SEARCH_MONTHLY_CAP=1)
    # cap 1: the first query is answered, the second hits the cap
    assert len(calls) == 1 and any("monthly cap reached (1/1)" in n for n in run.discovery["notes"])


def test_N5_the_per_mission_budget_still_applies_on_top_of_the_cap(tmp_path, net):
    calls = []
    ka, m, run = _world(tmp_path, calls, KA_RESEARCH_INTERNET=True, KA_DISCOVERY_BUDGET=1)
    assert len(run.discovery["selected"]) == 1 and any(x["reason"] == "budget" for x in run.discovery["skipped"])
