"""plan-36 — NEXOS IT MVP validation: existing KA content survives service revisions and recovery (Inv. 3, 4, 5; §41).

A restart on the same storage serves the same versions, decisions and lineage; a crash that tears the last line of the
event or audit log does not silence the logs afterwards; a field written by a newer service revision survives a rollback
to this one and a later bookkeeping write.
"""
from __future__ import annotations

import json

from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import A, B, C, D, P, S, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus


def _reopen(ka):
    inst = KnowledgeAcquisition(ka.repo.root, provider=StubLLMProvider(), auto_approve_low_impact=True)
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D), (C, D)]:
        inst.register_scope(s, p)
    return inst


def _revised(ka):
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    v2 = ka.governance.propose_revision(v1.canonical_id, statement="Refunds above $750 require manager approval.", by="ops", reason="update")
    ka.governance.decide(v2.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
    return v1, v2, ka.adapter.list_elements(D)[0]


def test_P1_a_restart_serves_the_same_history_decisions_and_lineage(ka):
    v1, v2, el = _revised(ka)
    before = {"history": [x.model_dump(mode="json") for x in ka.versioning.history(v1.canonical_id)],
              "explain": ka.lineage.explain_element(el.graph_id, el.element_id),
              "element": ka.adapter.get_graph_element(el.graph_id, el.element_id).model_dump(mode="json"),
              "decisions": sorted(d.id for d in ka.repo.decisions.all()), "seq": ka.repo.events()[-1]["seq"]}
    again = _reopen(ka)
    assert [x.model_dump(mode="json") for x in again.versioning.history(v1.canonical_id)] == before["history"]
    assert again.lineage.explain_element(el.graph_id, el.element_id) == before["explain"]
    assert again.adapter.get_graph_element(el.graph_id, el.element_id).model_dump(mode="json") == before["element"]
    assert sorted(d.id for d in again.repo.decisions.all()) == before["decisions"]
    assert again.repo.require_version(v1.ref).status == NuggetStatus.SUPERSEDED and again.repo.require_version(v1.ref).superseded_by == v2.ref
    again.bus.emit("knowledge.candidate.created", ref="KN-X:v1", canonical_id="KN-X", scope=D.key())
    assert again.repo.events()[-1]["seq"] == before["seq"] + 1           # sequence continues, never reused


def test_P2_a_torn_last_event_line_does_not_silence_the_event_log(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    n = len(ka.repo.events())
    with ka.repo.event_log.open("a", encoding="utf-8") as f:
        f.write('{"name": "knowledge.appro')                          # crash mid-append
    again = _reopen(ka)
    approve_all(again, ingest_policy(again, D, "Chargebacks are answered within 7 days."))
    events = again.repo.events()
    assert len(events) > n and "knowledge.approved" in {e["name"] for e in events[n:]}
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))


def test_P3_a_torn_last_audit_line_keeps_the_audit_readable_and_the_next_record_whole(ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    n = len(ka.repo.audit())
    with ka.repo.audit_log.open("a", encoding="utf-8") as f:
        f.write('{"who": "x')
    ka.auditor.record(who="ops", what="knowledge.comment", why="after the crash")
    recs = ka.repo.audit()
    assert len(recs) == n + 1 and recs[-1].who == "ops" and recs[-1].why == "after the crash"


def test_P4_a_field_from_a_newer_revision_survives_a_bookkeeping_write(ka):
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    path = ka.repo.nuggets.dir / f"{v1.id}.json"
    raw = json.loads(path.read_text())
    raw["future_field"] = {"written_by": "a newer KA"}
    path.write_text(json.dumps(raw))
    again = _reopen(ka)
    again.governance.add_comment(v1.ref, "ops", "noted")                  # lifecycle write after a rollback
    stored = json.loads(path.read_text())
    assert stored["future_field"] == {"written_by": "a newer KA"} and stored["comments"][-1]["text"] == "noted"
    assert stored["statement"] == v1.statement


def test_N1_a_known_field_is_never_resurrected_from_the_old_file(ka):
    v1 = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))[0]
    again = _reopen(ka)
    v = again.repo.require_version(v1.ref)
    v.comments.append({"by": "ops", "at": "now", "text": "x"})
    again.repo.nuggets.put(v)
    stored = json.loads((again.repo.nuggets.dir / f"{v1.id}.json").read_text())
    assert stored["comments"][-1]["text"] == "x" and "future_field" not in stored
