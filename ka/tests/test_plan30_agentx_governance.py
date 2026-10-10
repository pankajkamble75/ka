"""plan-30 (research-05 R4, R5; product tests PT1, PT4, PT5, PT6) — review, conflict resolution and publication for AgentX: human input as
AgentX interactions in its UiSchema, decisions through `decide(by=submitted_by)`, agents refused, publication only when applied, open work
as tasks, push registration and OperationEvent callbacks through the outbox."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.agentx import conformance as X
from ka.api import PREFIX, create_app, set_ka
from ka.tests.conftest import D, approve_all, ingest_policy
from ka.vocab import NuggetStatus, ProposalStatus

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "agentx-token-TEST"
PERMS = ["knowledge.acquire", "knowledge.read", "knowledge.revise", "knowledge.review", "knowledge.publish"]


@pytest.fixture
def c(ka_manual):
    with config.scoped(KA_AGENTX_TOKEN=TOKEN):
        client = TestClient(create_app(ka_manual))
        client.headers.update({"Authorization": f"Bearer {TOKEN}"})
        client.ka = ka_manual
        yield client
    set_ka(None)


def _invoke(c, cap, inp, *, user="alice", perms=PERMS, callback_url=None):
    return c.post(f"{PREFIX}/v1/capabilities/{cap}/invoke",
                  json={"schema_version": "1", "input": inp, "caller": {"service_id": "agentx", "user": user, "permissions": perms},
                        "callback_url": callback_url})


def _wait(c, op_id, until=("succeeded", "failed", "cancelled", "awaiting_input"), timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get(f"{PREFIX}/v1/operations/{op_id}").json()
        if st["status"] in until:
            return st
        time.sleep(0.05)
    raise AssertionError(st)


def _input(c, st, values, by="alice"):
    return c.post(f"{PREFIX}/v1/operations/{st['operation_id']}/input",
                  json={"interaction_id": st["interaction"]["interaction_id"], "values": values, "submitted_by": by})


def _pending(ka, text="Refunds above $500 require manager approval."):
    return ingest_policy(ka, D, text)


class _FakeAgentX:
    def __init__(self):
        self.calls = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _rec(self):
                n = int(self.headers.get("Content-Length") or 0)
                outer.calls.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"),
                                    "body": json.loads(self.rfile.read(n) or b"{}")})
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
            do_PUT = do_POST = _rec

            def log_message(self, *a):
                pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


def test_P1_seven_descriptors_conform_review_has_a_form_publish_needs_approval(c):
    caps = {d["id"]: d for d in c.get(f"{PREFIX}/v1/capabilities").json()["capabilities"]}
    assert set(caps) == {"knowledge.acquire", "knowledge.search", "knowledge.read", "knowledge.revise", "knowledge.review",
                         "knowledge.resolve_conflict", "knowledge.publish"}
    for d in caps.values():
        assert X.descriptor_errors(d) == [], d["id"]
    assert caps["knowledge.review"]["ui_schema"] and caps["knowledge.resolve_conflict"]["ui_schema"]
    assert caps["knowledge.publish"]["requires_approval"] is True and caps["knowledge.review"]["invocation"]["mode"] == "async"


def test_P2_PT4_review_waits_for_input_and_approve_is_governance_by_the_user(c):
    cand = _pending(c.ka)[0]
    st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}).json()["operation_id"])
    assert st["status"] == "awaiting_input" and st["interaction"]["required_permission"] == "knowledge.review"
    assert X.ui_errors(st["interaction"]["ui_schema"]) == [] and X.errors("OperationState.schema.json", st) == []
    assert st["references"]["candidate"]["ref"] == cand.ref and st["references"]["evidence"]
    done = _input(c, st, {"outcome": "APPROVE", "reason": "matches the SOP"}).json()
    assert done["status"] == "succeeded" and done["result"]["decided_by"] == "alice" and done["result"]["decision_id"]
    v = c.ka.repo.require_version(cand.ref)
    assert v.status == NuggetStatus.ACTIVE and c.ka.repo.decisions.require(done["result"]["decision_id"]).decided_by == "alice"


def test_P3_resolve_conflict_accept_new_and_merge(c):
    old = _pending(c.ka, "Refunds above $500 require manager approval.")
    approve_all(c.ka, old)
    new = _pending(c.ka, "Refunds above $900 require manager approval.")[0]
    assert any(f["relationship"] == "CONTRADICTS" for f in c.ka.repo.require_version(new.ref).analysis.get("findings", []))
    st = _wait(c, _invoke(c, "knowledge.resolve_conflict", {"item_id": new.ref}).json()["operation_id"])
    assert st["status"] == "awaiting_input" and "MERGE" in st["references"]["allowed_outcomes"] and st["references"]["conflicts"]
    done = _input(c, st, {"outcome": "ACCEPT_NEW", "reason": "policy raised"}).json()
    assert done["status"] == "succeeded" and c.ka.repo.require_version(new.ref).status == NuggetStatus.ACTIVE
    assert c.ka.repo.require_version(old[0].ref).status == NuggetStatus.SUPERSEDED
    third = _pending(c.ka, "Refunds above $700 require manager approval.")[0]
    st2 = _wait(c, _invoke(c, "knowledge.resolve_conflict", {"item_id": third.ref}).json()["operation_id"])
    done2 = _input(c, st2, {"outcome": "MERGE", "reason": "one rule", "merged_statement": "Refunds above $800 require manager approval."}).json()
    assert done2["status"] == "succeeded" and done2["result"]["outcome"] == "MERGE"
    assert any("$800" in c.ka.repo.require_version(r).statement for r in done2["result"]["resulting_refs"])


def test_P4_decided_in_the_console_completes_the_waiting_operation(c):
    cand = _pending(c.ka)[0]
    st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}).json()["operation_id"])
    c.ka.governance.decide(cand.ref, __import__("ka.vocab", fromlist=["DecisionOutcome"]).DecisionOutcome.REJECT, by="bob", reason="console")
    again = c.get(f"{PREFIX}/v1/operations/{st['operation_id']}").json()
    assert again["status"] == "succeeded" and again["message"] == "decided elsewhere" and again["result"]["decided_by"] == "bob"


def test_P5_PT5_a_v1_revision_and_a_wiki_edit_reach_the_same_decide(c):
    vs = _pending(c.ka)
    approve_all(c.ka, vs)
    rev = _invoke(c, "knowledge.revise", {"item_id": vs[0].ref, "change": {"statement": "Refunds above $600 require manager approval."},
                                          "rationale": "update"}).json()["result"]["proposal_id"]
    st = _wait(c, _invoke(c, "knowledge.resolve_conflict" if c.ka.repo.require_version(rev).status == NuggetStatus.CONFLICT else "knowledge.review",
                           {"item_id": rev}).json()["operation_id"])
    outcome = "ACCEPT_NEW" if "ACCEPT_NEW" in st["references"]["allowed_outcomes"] else "APPROVE"
    assert _input(c, st, {"outcome": outcome, "reason": "ok"}).json()["status"] == "succeeded"
    assert c.ka.repo.require_version(rev).status == NuggetStatus.ACTIVE
    d = c.ka.wiki.start_draft("scope:DOMAIN|merchant-acquiring", by="carol")
    md = c.ka.wiki.draft_markdown(d).replace("$600", "$650")
    c.ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="carol")
    c.ka.wiki.submit_draft(d.id, by="carol")
    produced = c.ka.repo.wiki_proposals.require(c.ka.repo.wiki_drafts.require(d.id).proposal_id).produced_refs
    assert produced
    st2 = _wait(c, _invoke(c, "knowledge.resolve_conflict" if c.ka.repo.require_version(produced[0]).status == NuggetStatus.CONFLICT else "knowledge.review",
                           {"item_id": produced[0]}).json()["operation_id"])
    out2 = "ACCEPT_NEW" if "ACCEPT_NEW" in st2["references"]["allowed_outcomes"] else "APPROVE"
    assert _input(c, st2, {"outcome": out2, "reason": "wiki edit ok"}).json()["status"] == "succeeded"
    assert c.ka.repo.require_version(produced[0]).status == NuggetStatus.ACTIVE


def test_P6_PT6_publish_applies_the_graph_change_and_a_wiki_proposal(c):
    vs = _pending(c.ka)
    approve_all(c.ka, vs)
    gcp = [p for p in c.ka.repo.proposals.where(lambda p: vs[0].ref in p.knowledge_change_ids)]
    assert gcp and gcp[0].status in (ProposalStatus.READY, ProposalStatus.APPROVED)
    st = _wait(c, _invoke(c, "knowledge.publish", {"item_id": vs[0].ref}).json()["operation_id"], until=("succeeded", "failed"))
    assert st["status"] == "succeeded" and st["result"]["status"] == "APPLIED" and st["result"]["execution_id"] and st["result"]["lineage"] == [vs[0].ref]
    assert c.ka.repo.proposals.require(gcp[0].id).status == ProposalStatus.APPLIED
    d = c.ka.wiki.start_draft("scope:DOMAIN|merchant-acquiring", by="carol")
    c.ka.wiki.save_draft(d.id, text=c.ka.wiki.draft_markdown(d).replace("## Rule", "## Rules"), expected_rev=0, by="carol")
    c.ka.wiki.submit_draft(d.id, by="carol")
    wp = c.ka.repo.wiki_drafts.require(d.id).proposal_id
    st2 = _wait(c, _invoke(c, "knowledge.publish", {"proposal_id": wp}).json()["operation_id"], until=("succeeded", "failed"))
    assert st2["status"] == "succeeded" and st2["result"]["kind"] == "wiki" and st2["result"]["status"] == "published"


def test_P7_tasks_list_open_work_with_a_ready_invocation(c):
    vs = _pending(c.ka)
    approve_all(c.ka, vs)
    _pending(c.ka, "Refunds above $900 require manager approval.")
    c.ka.governance.request_retirement(vs[0].canonical_id, by="u", why="old") if c.ka.repo.active_version(vs[0].canonical_id) else None
    t = c.get(f"{PREFIX}/v1/tasks").json()["tasks"]
    kinds = {x["kind"] for x in t}
    assert {"resolve_conflict"} <= kinds and all(x["start"]["capability"] in ("knowledge.review", "knowledge.resolve_conflict") for x in t)
    assert all(x["start"]["input"]["item_id"] == x["item_id"] for x in t)


def test_P8_push_registration_and_callbacks_reach_agentx_through_the_outbox(c):
    fake = _FakeAgentX()
    try:
        with config.scoped(KA_AGENTX_URL=fake.url, KA_AGENTX_TOKEN=TOKEN):
            r = c.post(f"{PREFIX}/v1/capabilities/register").json()
            assert r["pushed"] is True and r["state"] == "done"
            put = [x for x in fake.calls if x["method"] == "PUT"][0]
            assert put["path"] == "/api/v1/services/knowledge-acquisition/capabilities" and put["auth"] == f"Bearer {TOKEN}"
            assert len(put["body"]["capabilities"]) == 7
            cand = _pending(c.ka)[0]
            st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}, callback_url=fake.url + "/api/v1/callbacks/knowledge-acquisition").json()["operation_id"])
            _input(c, st, {"outcome": "APPROVE", "reason": "ok"})
            events = [x["body"] for x in fake.calls if x["method"] == "POST"]
            statuses = [e["operation"]["status"] for e in events]
            assert "awaiting_input" in statuses and statuses[-1] == "succeeded"
            assert all(X.errors("OperationEvent.schema.json", e) == [] for e in events)
            assert all(o.state == "done" for o in c.ka.repo.dp_outbox.where(lambda o: o.kind.startswith("agentx_")))
    finally:
        fake.close()
    assert (ROOT / "e2e" / "plan30_agentx_review_flow.py").exists()


def test_N1_an_agent_or_anonymous_user_cannot_decide(c):
    cand = _pending(c.ka)[0]
    c.ka.governance.research_agent_ids.add("research-bot")
    st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}).json()["operation_id"])
    r = _input(c, st, {"outcome": "APPROVE", "reason": "x"}, by="research-bot")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r2 = c.post(f"{PREFIX}/v1/operations/{st['operation_id']}/input", json={"interaction_id": st["interaction"]["interaction_id"], "values": {"outcome": "APPROVE", "reason": "x"}})
    assert r2.status_code == 403
    assert c.ka.repo.require_version(cand.ref).status in (NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT)
    assert c.get(f"{PREFIX}/v1/operations/{st['operation_id']}").json()["status"] == "awaiting_input"


def test_N2_values_outside_the_form_are_refused(c):
    cand = _pending(c.ka)[0]
    st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}).json()["operation_id"])
    for vals in ({"outcome": "MERGE", "reason": "x"}, {"outcome": "APPROVE"}, {"outcome": "NOPE", "reason": "x"}):
        r = _input(c, st, vals)
        assert r.status_code == 400 and r.json()["error"]["code"] == "schema_invalid"
    assert c.ka.repo.require_version(cand.ref).status in (NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT)


def test_N3_wrong_interaction_or_not_awaiting_input(c):
    cand = _pending(c.ka)[0]
    st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}).json()["operation_id"])
    r = c.post(f"{PREFIX}/v1/operations/{st['operation_id']}/input", json={"interaction_id": "nope", "values": {}, "submitted_by": "alice"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    _input(c, st, {"outcome": "APPROVE", "reason": "ok"})
    r2 = _input(c, st, {"outcome": "APPROVE", "reason": "again"})
    assert r2.status_code == 409


def test_N4_publish_needs_a_user_and_a_publishable_proposal_review_needs_an_open_item(c):
    vs = _pending(c.ka)
    approve_all(c.ka, vs)
    r = _invoke(c, "knowledge.publish", {"item_id": vs[0].ref}, user=None)
    st = _wait(c, r.json()["operation_id"], until=("succeeded", "failed"))
    assert st["status"] == "failed" and st["error"]["code"] == "forbidden"
    ok = _wait(c, _invoke(c, "knowledge.publish", {"item_id": vs[0].ref}).json()["operation_id"], until=("succeeded", "failed"))
    again = _wait(c, _invoke(c, "knowledge.publish", {"proposal_id": ok["result"]["proposal_id"]}).json()["operation_id"], until=("succeeded", "failed"))
    assert again["status"] == "failed" and again["error"]["code"] == "conflict"
    nope = _wait(c, _invoke(c, "knowledge.review", {"item_id": vs[0].ref}).json()["operation_id"], until=("succeeded", "failed", "awaiting_input"))
    assert nope["status"] == "failed" and nope["error"]["code"] == "conflict"


def test_N5_agentx_down_keeps_the_push_in_the_outbox_and_the_operation_is_unaffected(c):
    with config.scoped(KA_AGENTX_URL="http://127.0.0.1:9", KA_AGENTX_TOKEN=TOKEN, KA_DP_RETRIES=3, KA_DP_BACKOFF_BASE=0.0):
        r = c.post(f"{PREFIX}/v1/capabilities/register").json()
        assert r["pushed"] is False and r["state"] in ("pending", "dead") and r["error"]
        cand = _pending(c.ka)[0]
        st = _wait(c, _invoke(c, "knowledge.review", {"item_id": cand.ref}, callback_url="http://127.0.0.1:9/cb").json()["operation_id"])
        done = _input(c, st, {"outcome": "APPROVE", "reason": "ok"}).json()
        assert done["status"] == "succeeded"
        assert c.ka.repo.dp_outbox.where(lambda o: o.kind == "agentx_callback" and o.state != "done")


def test_N6_plan29_and_console_governance_are_unchanged():
    import subprocess
    out = subprocess.run(["git", "diff", "--quiet", "6921320", "--", "ka/tests/test_plan29_agentx_core.py", "ka/tests/test_plan10_governance_decisions.py",
                          "ka/tests/test_plan01_phase2_governance.py"], cwd=ROOT, capture_output=True)
    assert out.returncode == 0
