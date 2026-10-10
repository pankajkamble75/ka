"""plan-31 (research-05 R7, R8; product tests PT1, PT6, PT8) — Knowledge Worker over HTTP: KA's intake contract as executable fixtures
against a wire-level fake, the HTTP adapter (no `knowledge_worker` import), publication that succeeds only when KW reports `applied`,
graph-mode selection, and the grammar over HTTP."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.graph_adapter import KnowledgeWorkerHTTPAdapter, PublishRefused
from ka.knowledge_worker.client import KnowledgeWorkerClient
from ka.knowledge_worker.fake import FakeKnowledgeWorker
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import A, B, C, D, P, S, approve_all, ingest_policy
from ka.vocab import ProposalStatus

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures" / "kw_contract"
TOKEN, AX = "kw-token", "agentx-token-TEST"
PERMS = ["knowledge.acquire", "knowledge.read", "knowledge.revise", "knowledge.review", "knowledge.publish"]


def _ka_with_kw(tmp_path, fake, **extra):
    with config.scoped(KA_GRAPH_MODE="kw", KA_KW_URL="http://kw.test", KA_KW_TOKEN=TOKEN, KA_KW_PUBLISH_WAIT_S=0.5, **extra):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False, start_workers=False)
    ka.adapter.client = KnowledgeWorkerClient("http://kw.test", token=TOKEN, http=fake.as_http())
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D), (C, D)]:
        ka.register_scope(s, p)
    fake.add_substructure("merchant-acquiring")
    return ka


@pytest.mark.parametrize("name", sorted(p.stem for p in FIX.glob("*.json")))
def test_P1_every_contract_fixture_holds_against_the_fake(name):
    fx = json.loads((FIX / f"{name}.json").read_text())
    st = fx["setup"]
    fake = FakeKnowledgeWorker(token=TOKEN, mode=st.get("mode", "auto"), scopes=tuple(st.get("scopes", ("graph-changes:propose", "graphs:read"))))
    for i in st.get("instances", []):
        fake.add_instance(i)
    for sid, v in st.get("substructures", {}).items():
        fake.add_substructure(sid, v)
    r = fx["request"]
    status, data = fake.handle(r["method"], r["path"], {"Authorization": f"Bearer {TOKEN}", "X-Correlation-ID": "c1"},
                               json.dumps(r["body"]).encode() if r["body"] is not None else None)
    e = fx["expect"]
    assert status == e["status"]
    if "envelope_status" in e:
        assert data["contract_version"] == "knowledge-worker/v1" and data["status"] == e["envelope_status"] and data["correlation_id"] == "c1"
    if "result_status" in e:
        assert data["result"]["status"] == e["result_status"]
    if "error_status" in e:                                         # KW v1: error.status is the typed status, error.code the AgentX class
        assert data["error"]["status"] == e["error_status"] and data["error"]["code"] == e["error_class"]
        assert set(data["error"]) >= {"status", "code", "message", "retryable", "detail"}
    if "new_version" in e:
        assert data["result"]["new_version"] == e["new_version"]
    for k in e.get("keys", []):
        assert k in data


def _client(ka):
    with config.scoped(KA_AGENTX_TOKEN=AX):
        c = TestClient(create_app(ka))
    c.headers.update({"Authorization": f"Bearer {AX}"})
    return c


def _invoke(c, cap, inp, user="alice"):
    with config.scoped(KA_AGENTX_TOKEN=AX):
        return c.post(f"{PREFIX}/v1/capabilities/{cap}/invoke", json={"schema_version": "1", "input": inp,
                                                                     "caller": {"service_id": "agentx", "user": user, "permissions": PERMS}}).json()


def _poll(c, op, until=("succeeded", "failed"), timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        with config.scoped(KA_AGENTX_TOKEN=AX):
            st = c.get(f"{PREFIX}/v1/operations/{op}").json()
        if st["status"] in until:
            return st
        time.sleep(0.05)
    return st


def test_P2_PT6_publish_through_kw_reaches_kw_with_lineage_and_applies(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN)
    ka = _ka_with_kw(tmp_path, fake)
    assert isinstance(ka.adapter, KnowledgeWorkerHTTPAdapter) and ka.graph_mode == "kw"
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, vs)
    c = _client(ka)
    st = _poll(c, _invoke(c, "knowledge.publish", {"item_id": vs[0].ref})["operation_id"])
    assert st["status"] == "succeeded" and st["result"]["status"] == "APPLIED", st
    req = fake.requests[-1]
    assert req["target"] == {"kind": "substructure", "id": "merchant-acquiring", "base_version": "1"} or req["target"]["kind"] == "substructure"
    assert req["idempotency_key"].startswith("ka:GCP-") and req["knowledge_refs"][0]["nugget_ref"] == vs[0].ref
    assert all((op.get("node") or op.get("edge") or {}).get("props", {}).get("knowledge_lineage") for op in req["ops"] if not op["op"].startswith("remove"))
    p = ka.repo.proposals.require(st["result"]["proposal_id"])
    assert p.status == ProposalStatus.APPLIED and p.eos_proposal_id.startswith("prop-") and ka.repo.dependencies_for_nugget(vs[0].ref)
    set_ka(None)


def test_P3_PT6_publish_stays_running_until_kw_approves(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN, mode="approval")
    ka = _ka_with_kw(tmp_path, fake)
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, vs)
    c = _client(ka)
    op = _invoke(c, "knowledge.publish", {"item_id": vs[0].ref})["operation_id"]
    st = _poll(c, op, until=("succeeded", "failed", "x"), timeout=1.0)
    assert st["status"] == "running" and st["message"] == "awaiting Knowledge Worker" and st["references"]["kw_proposal_id"]
    fake.approve(st["references"]["kw_proposal_id"])
    done = _poll(c, op)
    assert done["status"] == "succeeded" and ka.repo.proposals.require(done["result"]["proposal_id"]).status == ProposalStatus.APPLIED
    assert len(fake.proposals) == 1                                     # apply's replay reused the idempotency key
    set_ka(None)


def test_P4_a_repeated_submit_replays_one_kw_proposal(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN)
    ka = _ka_with_kw(tmp_path, fake)
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, vs)
    p = ka.repo.proposals.where(lambda p: vs[0].ref in p.knowledge_change_ids)[0]
    scope = ka.adapter.scope_for_graph(p.affected_graph_ids[0])
    a = ka.adapter.submit(scope, p.changes, actor="alice", reason="r", base_version=None, graph_change_id=p.id)
    b = ka.adapter.submit(scope, p.changes, actor="alice", reason="r", base_version=None, graph_change_id=p.id)
    assert a["proposal_id"] == b["proposal_id"] and len(fake.proposals) == 1


def test_P5_PT8_grammar_over_http_with_digests_and_fail_closed_on_drift(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN)
    srv = fake.serve()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/graph-model"
    try:
        from ka.grammar import GrammarRegistry
        with config.scoped(KA_GRAMMAR_URL=url, KA_KW_TOKEN=TOKEN):
            reg = GrammarRegistry.from_config(tmp_path)
            gd, td = fake.file_digests()
            assert reg.loaded and reg.snapshot.grammar_digest == gd and reg.snapshot.type_table_digest == td
            assert (tmp_path / "grammar_snapshot.json").exists() and not reg.is_stale()
            fake.grammar = {**fake.grammar, "nodes": [{"kind": "changed"}]}          # same version, different content
            reg2 = GrammarRegistry.from_config(tmp_path)
            assert reg2.is_stale() and "same version" in reg2.stale_reason()
    finally:
        srv.shutdown()


def test_P6_PT1_PT8_graph_mode_selection_and_no_eos_import(tmp_path):
    code = ("import sys; from ka import config; from ka.llm import StubLLMProvider; from ka.service import KnowledgeAcquisition; from pathlib import Path\n"
            "import tempfile\n"
            "with config.scoped(KA_GRAPH_MODE='auto', KA_KW_URL='', KA_ENTERPRISE_OS_ROOT=''):\n"
            "    a = KnowledgeAcquisition(Path(tempfile.mkdtemp()), provider=StubLLMProvider(), start_workers=False)\n"
            "with config.scoped(KA_GRAPH_MODE='auto', KA_KW_URL='http://kw.test', KA_ENTERPRISE_OS_ROOT=''):\n"
            "    b = KnowledgeAcquisition(Path(tempfile.mkdtemp()), provider=StubLLMProvider(), start_workers=False)\n"
            "print(a.graph_mode, type(a.adapter).__name__, b.graph_mode, type(b.adapter).__name__, any(m.startswith('knowledge_worker') for m in sys.modules))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"})
    assert out.stdout.split() == ["memory", "InMemoryGraphAdapter", "kw", "KnowledgeWorkerHTTPAdapter", "False"], out.stderr[-500:]


def test_P7_the_live_flow_exists():
    assert (ROOT / "e2e" / "plan31_kw_flow.py").exists()


def test_N1_stale_base_fails_the_operation_and_leaves_the_proposal_approved(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN)
    ka = _ka_with_kw(tmp_path, fake)
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, vs)
    p = ka.repo.proposals.where(lambda p: vs[0].ref in p.knowledge_change_ids)[0]
    p.eos_base_version = "999"
    ka.repo.proposals.put(p)
    c = _client(ka)
    st = _poll(c, _invoke(c, "knowledge.publish", {"proposal_id": p.id})["operation_id"])
    assert st["status"] == "failed" and st["error"]["code"] == "stale_version" and st["error"]["details"]["kw_code"] == "STALE_BASE"
    assert ka.repo.proposals.require(p.id).status == ProposalStatus.APPROVED
    set_ka(None)


def test_N2_wrong_token_is_forbidden(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN, scopes=("graphs:read",))
    ka = _ka_with_kw(tmp_path, fake)
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, vs)
    c = _client(ka)
    st = _poll(c, _invoke(c, "knowledge.publish", {"item_id": vs[0].ref})["operation_id"])
    assert st["status"] == "failed" and st["error"]["code"] == "forbidden"
    set_ka(None)


def test_N3_kw_unreachable_and_grammar_url_unreachable(tmp_path):
    from ka.grammar import GrammarRegistry
    client = KnowledgeWorkerClient("http://127.0.0.1:9", token=TOKEN)
    from ka.knowledge_worker.client import KnowledgeWorkerError
    with pytest.raises(KnowledgeWorkerError) as e:
        client.get("prop-x")
    assert e.value.code == "DEPENDENCY_UNAVAILABLE" and e.value.error_class == "unavailable" and e.value.retryable
    with config.scoped(KA_GRAMMAR_URL="http://127.0.0.1:9/v1/graph-model"):
        reg = GrammarRegistry.from_config(tmp_path)
    assert not reg.loaded and reg.load_error


def test_N4_same_key_different_body_is_a_conflict():
    fake = FakeKnowledgeWorker(token=TOKEN)
    fake.add_instance("acme")
    c = KnowledgeWorkerClient("http://kw.test", token=TOKEN, http=fake.as_http())
    L = [{"nugget_id": "KN-1", "version": 1}]
    c.propose(target={"kind": "instance", "id": "acme"}, ops=[{"op": "add_node", "node": {"id": "a", "props": {"knowledge_lineage": L}}}],
              reason="r", actor="a", knowledge_refs=[], idempotency_key="k")
    from ka.knowledge_worker.client import KnowledgeWorkerError
    with pytest.raises(KnowledgeWorkerError) as e:
        c.propose(target={"kind": "instance", "id": "acme"}, ops=[{"op": "add_node", "node": {"id": "b", "props": {"knowledge_lineage": L}}}],
                  reason="r", actor="a", knowledge_refs=[], idempotency_key="k")
    assert e.value.code == "CONFLICT"


def test_N5_rollback_through_kw_is_unsupported(tmp_path):
    fake = FakeKnowledgeWorker(token=TOKEN)
    ka = _ka_with_kw(tmp_path, fake)
    with pytest.raises(PublishRefused) as e:
        ka.adapter.publish(D, [], actor="a", reason="r", base_version=None, rollback=True)
    assert e.value.code == "unsupported"


def test_N6_graph_change_covering_tests_are_unmodified():
    out = subprocess.run(["git", "diff", "--quiet", "beae3f1", "--", "ka/graph_change.py", "ka/tests/test_plan05_publication.py",
                          "ka/tests/test_plan10_governance_decisions.py"], cwd=ROOT, capture_output=True)
    assert out.returncode == 0


def test_P2b_publish_declares_a_timeout_long_enough_to_wait_for_kw(tmp_path):
    """AgentX cancels at timeout.operation_s and counts `running` time (AgentX session, 2026-10-10); a KW approval can take days."""
    from ka.agentx.governance_caps import extend
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), start_workers=False)
    d = extend(ka)["knowledge.publish"].descriptor()
    assert d["timeout"]["operation_s"] >= 7 * 24 * 3600


def test_P4b_base_versions_read_kw_real_graph_versions_shape(tmp_path):
    """KW's GET /v1/graph-versions is enveloped with `domains[id].latest` and `instances[id].graph_digest` (KW session, 2026-10-10)."""
    from ka.model import Scope
    from ka.vocab import ScopeType
    fake = FakeKnowledgeWorker(token=TOKEN)
    ka = _ka_with_kw(tmp_path, fake)
    fake.add_instance("acme")
    v = ka.adapter.client.graph_versions()
    assert set(v) >= {"domains", "instances"} and "contract_version" not in v
    assert ka.adapter.base_version(D) == fake.substructures["merchant-acquiring"]["version"]
    assert ka.adapter.base_version(Scope(scope_type=ScopeType.INSTANCE, scope_id="acme")) == fake._digest(fake.instances["acme"])
