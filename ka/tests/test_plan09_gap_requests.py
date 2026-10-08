"""plan-09 (research-01 R11 KA half, R15, R16 benchmark) — the gap request contract, events as an outbox, the store benchmark.
P1 characterises the PROTECTED runtime guard BEFORE the change (committed on its own, green against the unchanged file)."""
from __future__ import annotations

import pytest

from ka.runtime_guard import GRAPH_GAP_DETECTED, RuntimeKnowledgeAccessError
from ka.tests.conftest import A, D


def test_P1_characterization_every_gap_is_a_new_open_request_and_the_door_is_shut(ka):
    """Pre-change behaviour at the seam (commit 67df074 pinned it with two IDENTICAL questions; that case is the one this plan
    changes — see P3 — so it now uses two DISTINCT questions, which held before and holds after): distinct gaps are distinct
    OPEN requests, a mission gap carries trigger graph_gap, retrieval raises."""
    g = ka.runtime_guard
    a = g.graph_gap_detected(scope=A, question="What approval is required for a $750 refund?", gap_description="no rule")
    b = g.graph_gap_detected(scope=A, question="What approval is required for a $7,500 refund?", gap_description="no rule")
    assert a.signal == b.signal == GRAPH_GAP_DETECTED and a.request_id != b.request_id
    assert {r.status for r in ka.repo.requests.all()} == {"OPEN"} and len(g.open_requests()) == 2
    c = g.graph_gap_detected(scope=D, question="Who approves chargebacks?", gap_description="no rule", open_mission=True)
    assert c.mission_id and ka.repo.missions.require(c.mission_id).trigger == "graph_gap"
    assert ka.repo.requests.require(c.request_id).mission_id == c.mission_id
    with pytest.raises(RuntimeKnowledgeAccessError):
        g.retrieve_for_answer("what approval for $750 refund?")
    assert any(e["name"] == "graph.gap.detected" and e["request_id"] == a.request_id for e in ka.repo.events())


# ---- post-change cases ------------------------------------------------------------------------------------

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.tests.conftest import ingest_policy
from ka.vocab import DecisionOutcome


def test_P2_a_gap_carries_principal_intent_missing_semantics_and_correlation_id(ka):
    out = ka.runtime_guard.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="no actor on chargeback",
                                              principal="eos:console", intent="grow_existing", missing_semantics=["actor", "decision"],
                                              correlation_id="corr-123")
    r = ka.repo.requests.require(out.request_id)
    assert (r.principal, r.intent, r.missing_semantics, r.correlation_id) == ("eos:console", "grow_existing", ["actor", "decision"], "corr-123")
    assert r.dedupe_key == "corr-123" and r.status == "OPEN" and not out.deduplicated


def test_P3_the_same_gap_raised_while_live_returns_the_same_request(ka):
    g = ka.runtime_guard
    a = g.graph_gap_detected(scope=A, question="What approval is required for a $750 refund?", gap_description="no rule")
    b = g.graph_gap_detected(scope=A, question="  what approval is REQUIRED for a $750 refund?  ", gap_description="no rule again")
    assert b.request_id == a.request_id and b.deduplicated and not a.deduplicated
    assert ka.repo.requests.require(a.request_id).deduplicated_count == 1
    c = g.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="no rule")
    assert c.request_id != a.request_id and len(ka.repo.requests.all()) == 2
    d = g.graph_gap_detected(scope=A, question="totally different wording", gap_description="x", correlation_id="corr-9")
    e = g.graph_gap_detected(scope=D, question="another wording still", gap_description="y", correlation_id="corr-9")
    assert e.request_id == d.request_id and e.deduplicated                     # a correlation id is the key when given


def test_P4_a_mission_gap_is_in_research_and_an_approved_candidate_fulfils_it(ka):
    out = ka.runtime_guard.graph_gap_detected(scope=D, question="What is the settlement timing?", gap_description="no settlement rule", open_mission=True)
    assert ka.repo.requests.require(out.request_id).status == "IN_RESEARCH" and len(ka.runtime_guard.open_requests()) == 1
    m = ka.repo.missions.require(out.mission_id)
    cand = ingest_policy(ka, D, "Settlement occurs two business days after clearing.")[0]
    m.candidate_refs.append(cand.ref)
    ka.repo.missions.put(m)
    ka.governance.decide(cand.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    r = ka.repo.requests.require(out.request_id)
    assert r.status == "FULFILLED" and r.fulfilled_by == [cand.ref] and r.updated_at >= r.created_at
    assert ka.runtime_guard.open_requests() == []


def test_P5_cancel_records_the_reason_and_the_same_gap_then_creates_a_new_request(ka):
    g = ka.runtime_guard
    a = g.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="no rule")
    r = g.cancel(a.request_id, by="ops", reason="not needed")
    assert r.status == "CANCELLED" and r.cancelled_reason == "ops: not needed" and r.updated_at
    b = g.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="no rule")
    assert b.request_id != a.request_id and not b.deduplicated
    assert [x.id for x in g.requests("CANCELLED")] == [a.request_id] and [x.id for x in g.requests("OPEN")] == [b.request_id]


@pytest.fixture
def client(ka):
    c = TestClient(create_app(ka))
    yield c
    set_ka(None)


def test_P6_request_routes(client):
    body = {"scope_type": "INSTANCE", "scope_id": "merchant-a", "question": "Who approves chargebacks?", "gap_description": "no rule",
            "principal": "eos:runtime", "intent": "found_new", "missing_semantics": ["actor"], "correlation_id": "c-1"}
    r = client.post(f"{PREFIX}/runtime/graph-gap", json=body).json()
    assert r["signal"] == "GRAPH GAP DETECTED" and r["deduplicated"] is False
    again = client.post(f"{PREFIX}/runtime/graph-gap", json=body).json()
    assert again["request_id"] == r["request_id"] and again["deduplicated"] is True
    lst = client.get(f"{PREFIX}/runtime/requests?status=OPEN").json()["requests"]
    assert [x["id"] for x in lst] == [r["request_id"]] and lst[0]["intent"] == "found_new" and lst[0]["principal"] == "eos:runtime"
    assert client.get(f"{PREFIX}/runtime/requests/{r['request_id']}").json()["request"]["correlation_id"] == "c-1"
    assert client.get(f"{PREFIX}/runtime/requests/REQ-nope").status_code == 404
    c = client.post(f"{PREFIX}/runtime/requests/{r['request_id']}/cancel?by=ops&reason=dup")
    assert c.status_code == 200 and c.json()["request"]["status"] == "CANCELLED"
    assert client.post(f"{PREFIX}/runtime/requests/{r['request_id']}/cancel?by=ops").status_code == 409
    assert client.post(f"{PREFIX}/runtime/requests/REQ-nope/cancel").status_code == 404


def test_P7_every_event_has_a_monotonic_seq_and_after_resumes_exactly(ka, client):
    for i, t in enumerate(["Merchant A refunds above $500 require manager approval.", "Merchant A chargebacks must be answered within 30 days.",
                           "Merchant A settlement occurs two business days after clearing."]):
        ingest_policy(ka, A, t, title=f"Policy {i}")
    evs = ka.repo.events()
    seqs = [e["seq"] for e in evs]
    assert len(seqs) >= 6 and seqs == list(range(1, len(evs) + 1)) and all(e["version"] == "ka-events/1" for e in evs)
    cut = seqs[len(seqs) // 2]
    after_cut = [s for s in seqs if s > cut]
    assert [e["seq"] for e in ka.repo.events(after=cut)] == after_cut
    page = client.get(f"{PREFIX}/events?after={cut}&limit=2").json()
    assert [e["seq"] for e in page["events"]] == after_cut[:2] and page["next_after"] == after_cut[1] and page["version"] == "ka-events/1"
    rest = client.get(f"{PREFIX}/events?after={page['next_after']}").json()
    assert [e["seq"] for e in rest["events"]] == after_cut[2:]
    tail = client.get(f"{PREFIX}/events?limit=3&tail=1").json()
    assert [e["seq"] for e in tail["events"]] == seqs[-3:]


def test_P8_a_pre_plan_events_file_is_served_with_line_number_seqs_and_new_records_continue(tmp_path):
    from ka.repository import Repository
    from ka.json_io import append_jsonl
    root = tmp_path / "s"
    root.mkdir()
    append_jsonl(root / "events.jsonl", {"event_id": "EV-old1", "name": "source.ingested", "at": "2026-01-01T00:00:00+00:00"})
    append_jsonl(root / "events.jsonl", {"event_id": "EV-old2", "name": "source.ingested", "at": "2026-01-01T00:00:01+00:00"})
    repo = Repository(root)
    old = repo.events()
    assert [(e["seq"], e["version"]) for e in old] == [(1, "ka-events/0"), (2, "ka-events/0")]
    repo.append_event({"event_id": "EV-new", "name": "source.ingested", "at": "2026-01-02T00:00:00+00:00"})
    assert [e["seq"] for e in repo.events()] == [1, 2, 3] and repo.events(after=2)[0]["event_id"] == "EV-new"
    assert Repository(root)._last_seq() == 3                                    # a fresh process resumes the counter from the file


def test_P9_the_benchmark_tool_runs_and_the_recorded_results_exist(tmp_path):
    out = subprocess.run([sys.executable, "tools/bench_store.py", "200", "--root", str(tmp_path / "bench")], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "| 200 |" in out.stdout and "cold load" in out.stdout
    rec = Path("docs/research/benchmarks/store-bench-2026-10-08.md").read_text(encoding="utf-8")
    assert "| 10000 |" in rec and "| 100000 |" in rec


def test_N1_the_covering_test_passes_unmodified_and_the_door_is_still_shut(ka):
    """The regression gate: `test_plan01_phase4_corrections.py::test_N1` is run unmodified by the suite; here the door."""
    with pytest.raises(RuntimeKnowledgeAccessError):
        ka.runtime_guard.retrieve_for_answer("anything")
    src = Path("ka/tests/test_plan01_phase4_corrections.py").read_text(encoding="utf-8")
    assert "def test_N1_the_runtime_cannot_pull_knowledge_as_an_answer_fallback" in src


def test_N2_dedupe_never_swallows_a_distinct_gap(ka):
    g = ka.runtime_guard
    a = g.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="x")
    b = g.graph_gap_detected(scope=D, question="Who approves chargebacks?", gap_description="x")          # other scope
    assert b.request_id != a.request_id
    g.fulfil(a.request_id, refs=["KN-001:v1"])
    c = g.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="x")          # fulfilled → new
    assert c.request_id != a.request_id and not c.deduplicated
    g.cancel(c.request_id, by="ops")
    d = g.graph_gap_detected(scope=A, question="Who approves chargebacks?", gap_description="x")          # cancelled → new
    assert d.request_id not in {a.request_id, c.request_id}


def test_N3_cancel_of_a_terminal_request_and_an_unknown_intent_are_refused(ka, client):
    g = ka.runtime_guard
    a = g.graph_gap_detected(scope=A, question="q1", gap_description="x")
    g.fulfil(a.request_id, refs=["KN-001:v1"])
    with pytest.raises(ValueError, match="only OPEN or IN_RESEARCH"):
        g.cancel(a.request_id, by="ops")
    with pytest.raises(ValueError, match="unknown intent"):
        g.graph_gap_detected(scope=A, question="q2", gap_description="x", intent="mutate")
    r = client.post(f"{PREFIX}/runtime/graph-gap", json={"scope_type": "INSTANCE", "scope_id": "merchant-a", "question": "q3", "gap_description": "x", "intent": "mutate"})
    assert r.status_code == 422


def test_N4_an_approval_without_a_mission_touches_no_request_and_a_failing_subscriber_cannot_break_approval(ka, monkeypatch):
    out = ka.runtime_guard.graph_gap_detected(scope=A, question="q", gap_description="x", open_mission=True)
    cand = ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval.")[0]
    ka.governance.decide(cand.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    assert ka.repo.requests.require(out.request_id).status == "IN_RESEARCH"
    def boom(ref):
        raise RuntimeError("subscriber down")
    monkeypatch.setattr(ka.runtime_guard, "fulfil_from_approval", boom)
    cand2 = ingest_policy(ka, A, "Merchant A chargebacks must be answered within 30 days.")[0]
    ka.governance.decide(cand2.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    assert ka.repo.require_version(cand2.ref).status.value == "ACTIVE"


def test_N5_after_beyond_the_end_is_empty_and_a_negative_limit_is_422(ka, client):
    ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval.")
    last = ka.repo.events()[-1]["seq"]
    page = client.get(f"{PREFIX}/events?after={last + 50}").json()
    assert page["events"] == [] and page["next_after"] == last + 50
    assert client.get(f"{PREFIX}/events?limit=-1").status_code == 422
    assert ka.repo.events(after=last) == []


def test_N6_the_in_memory_history_is_unstamped_and_the_content_rule_still_holds(ka):
    ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval.")
    assert all("seq" not in e for e in ka.bus.history) and all("seq" in e for e in ka.repo.events())
    with pytest.raises(ValueError, match="looks like content"):
        ka.bus.emit("source.ingested", source_id="x" * 201)
