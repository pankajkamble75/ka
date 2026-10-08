"""plan-17 (research-01 R18; product test PT10) — missions run in the background with a RUNNING state the mission page polls; the
API default stays synchronous; the console asks for wait=false."""
from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.llm import StubLLMProvider
from ka.research import ResearchError
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S
from ka.vocab import MissionStatus, RunStatus

FINDINGS = json.dumps([{"title": "x", "statement": "Settlement occurs two business days after clearing.", "knowledge_type": "fact", "excerpt": "Settlement", "confidence": 0.6}])


class SlowAgent:
    """Blocks until released so a test can observe RUNNING and progress mid-run."""
    agent_id = "agent.slow"

    def __init__(self):
        self.gate = threading.Event()
        self.started = threading.Event()

    def research(self, ctx):
        self.started.set()
        assert self.gate.wait(10), "test released the gate"
        return []


def _ka(tmp_path, slow=None):
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(responses={"Domain Research Agent": FINDINGS}, default_response="[]"), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    if slow is not None:
        ka.research.agents.insert(1, slow)
    return ka


def test_P1_start_mission_returns_running_at_once_and_completes_in_the_background(tmp_path):
    ka = _ka(tmp_path)
    m = ka.research.create_mission(scope=D, objective="settlement timing", by="u")
    t0 = time.time()
    run = ka.research.start_mission(m.mission_id)
    assert time.time() - t0 < 1.0 and run.status == RunStatus.STARTED and ka.repo.missions.require(m.mission_id).status == MissionStatus.RUNNING
    ka.research._threads[m.mission_id].join(20)
    assert ka.repo.runs.require(run.run_id).status == RunStatus.COMPLETED
    mm = ka.repo.missions.require(m.mission_id)
    assert mm.status == MissionStatus.COMPLETED and mm.candidate_refs


def test_P2_progress_is_readable_mid_run_and_advances_per_agent(tmp_path):
    slow = SlowAgent()
    ka = _ka(tmp_path, slow)
    m = ka.research.create_mission(scope=D, objective="settlement timing", by="u")
    run = ka.research.start_mission(m.mission_id)
    assert slow.started.wait(10)
    mid = ka.repo.runs.require(run.run_id)
    assert mid.status == RunStatus.STARTED and mid.progress["agents_done"] == 1 and mid.progress["current_agent"] == "agent.slow"
    assert mid.progress["agents_total"] == len(ka.research.agents)
    slow.gate.set()
    ka.research._threads[m.mission_id].join(20)
    done = ka.repo.runs.require(run.run_id)
    assert done.progress["agents_done"] == len(ka.research.agents) and done.progress["current_agent"] is None and done.progress["candidates_so_far"] >= 1


@pytest.fixture
def client(tmp_path):
    slow = SlowAgent()
    ka = _ka(tmp_path, slow)
    c = TestClient(create_app(ka))
    yield c, ka, slow
    slow.gate.set()
    set_ka(None)


def test_P3_the_api_returns_running_with_wait_false_and_get_shows_completed_after(client):
    c, ka, slow = client
    r = c.post(f"{PREFIX}/research/missions", json={"wait": False, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "settlement timing", "by": "u"})
    assert r.status_code == 200 and r.json()["mission"]["status"] == "RUNNING" and r.json()["run"]["status"] == "STARTED"
    mid = r.json()["mission"]["mission_id"]
    assert slow.started.wait(10)
    d = c.get(f"{PREFIX}/research/missions/{mid}").json()
    assert d["mission"]["status"] == "RUNNING" and d["runs"][-1]["progress"]["current_agent"] == "agent.slow"
    slow.gate.set()
    ka.research._threads[mid].join(20)
    d = c.get(f"{PREFIX}/research/missions/{mid}").json()
    assert d["mission"]["status"] == "COMPLETED" and d["candidates"]
    # /run in the background too
    slow.started.clear()
    r2 = c.post(f"{PREFIX}/research/missions/{mid}/run?wait=false")
    assert r2.status_code == 200 and r2.json()["run"]["status"] == "STARTED"
    slow.gate.set()
    ka.research._threads[mid].join(20)


def test_P4_the_default_stays_synchronous_for_scripts_and_tests(tmp_path):
    ka = _ka(tmp_path)
    c = TestClient(create_app(ka))
    r = c.post(f"{PREFIX}/research/missions", json={"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "settlement timing", "by": "u"})
    assert r.status_code == 200 and r.json()["mission"]["status"] == "COMPLETED" and r.json()["run"]["status"] == "COMPLETED"
    set_ka(None)


def test_P5_the_console_navigates_at_once_and_polls_while_running():
    from pathlib import Path
    js = Path("ka/console/app.js").read_text(encoding="utf-8")
    assert "wait: false" in js and "/run?wait=false" in js and "function progressLine" in js and "setTimeout(() => { if (location.hash === `#/mission/${id}`) render(); }, 2000)" in js
    assert Path("e2e/plan17_background_mission_flow.py").exists()


def test_N1_a_failing_agent_in_the_worker_ends_failed_and_nothing_escapes(tmp_path):
    class Boom:
        agent_id = "agent.boom"
        def research(self, ctx):
            raise RuntimeError("down")
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(default_response="[]"), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    ka.research.agents = [Boom()]
    m = ka.research.create_mission(scope=D, objective="x", by="u")
    run = ka.research.start_mission(m.mission_id)
    ka.research._threads[m.mission_id].join(20)
    done = ka.repo.runs.require(run.run_id)
    assert done.status == RunStatus.FAILED and any("down" in e for e in done.errors)
    assert ka.repo.missions.require(m.mission_id).status == MissionStatus.FAILED


def test_N2_starting_a_running_mission_is_refused(client):
    c, ka, slow = client
    r = c.post(f"{PREFIX}/research/missions", json={"wait": False, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "settlement timing", "by": "u"})
    mid = r.json()["mission"]["mission_id"]
    assert slow.started.wait(10)
    with pytest.raises(ResearchError, match="already RUNNING"):
        ka.research.start_mission(mid)
    assert c.post(f"{PREFIX}/research/missions/{mid}/run?wait=false").status_code == 409
    assert c.post(f"{PREFIX}/research/missions/{mid}/run").status_code == 409
    slow.gate.set()
    ka.research._threads[mid].join(20)
    assert ka.repo.missions.require(mid).status == MissionStatus.COMPLETED and len(ka.repo.missions.require(mid).run_ids) == 1


def test_N3_a_disconnected_client_does_not_stop_the_worker(client):
    c, ka, slow = client
    r = c.post(f"{PREFIX}/research/missions", json={"wait": False, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "settlement timing", "by": "u"})
    mid = r.json()["mission"]["mission_id"]
    c.close()                                                  # the client is gone; the worker keeps going
    slow.gate.set()
    ka.research._threads[mid].join(20)
    assert ka.repo.missions.require(mid).status == MissionStatus.COMPLETED
