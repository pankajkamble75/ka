"""plan-29 (research-05 R2, R3, R10; product tests PT2, PT3) — the AgentX services contract (PROPOSED v1) over KA's existing services:
capabilities in AgentX's descriptor shape, one invoke endpoint, durable idempotent operations, AgentX's error envelope, the AgentX bearer."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.agentx.capabilities import DESCRIPTOR_KEYS
from ka.tests.conftest import D, approve_all, ingest_policy
from ka.vocab import NuggetStatus

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "agentx-token-TEST"
ALL = ["knowledge.acquire", "knowledge.read", "knowledge.revise", "knowledge.review", "knowledge.publish"]
POLICY = "Refunds above $500 require manager approval. Chargebacks must be answered within 30 days."


@pytest.fixture
def c(ka):
    with config.scoped(KA_AGENTX_TOKEN=TOKEN):
        client = TestClient(create_app(ka))
        client.headers.update({"Authorization": f"Bearer {TOKEN}"})
        yield client
    set_ka(None)


def _invoke(c, cap, inp, *, perms=ALL, key=None, user="pankaj", **extra):
    headers = {"Idempotency-Key": key} if key else {}
    return c.post(f"{PREFIX}/v1/capabilities/{cap}/invoke", headers=headers,
                  json={"schema_version": "1", "input": inp, "caller": {"service_id": "agentx", "user": user, "permissions": perms}, **extra})


def _wait(c, op_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get(f"{PREFIX}/v1/operations/{op_id}").json()
        if st["status"] in ("succeeded", "failed", "cancelled", "timed_out"):
            return st
        time.sleep(0.05)
    raise AssertionError(f"operation {op_id} did not finish: {st}")


def _governed(ka):
    cands = ingest_policy(ka, D, POLICY)
    approve_all(ka, cands)
    return [ka.repo.require_version(x.ref) for x in cands]


def test_P1_capabilities_are_in_agentx_descriptor_shape(c):
    r = c.get(f"{PREFIX}/v1/capabilities").json()
    assert r["service_id"] == "knowledge-acquisition" and r["schema_version"] == "1"
    ids = {d["id"] for d in r["capabilities"]}
    assert {"knowledge.acquire", "knowledge.search", "knowledge.read", "knowledge.revise"} <= ids
    for d in r["capabilities"]:
        assert set(d) <= set(DESCRIPTOR_KEYS) and set(d) >= set(DESCRIPTOR_KEYS) - {"ui_schema"}
        assert d["input_schema"]["type"] == "object" and d["output_schema"]["type"] == "object"
        assert d["invocation"] == {"endpoint": "/v1/capabilities/{capability_id}/invoke", "mode": d["invocation"]["mode"]}
        assert d["version"].count(".") == 2 and d["health_endpoint"] == "/healthz" and d["deprecated"] is False


def test_P2_PT2_acquire_returns_an_operation_and_polls_to_candidates(c, ka):
    r = _invoke(c, "knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": POLICY,
                                         "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}})
    assert r.status_code == 202 and r.json()["status"] in ("accepted", "running", "succeeded") and r.json()["operation_id"].startswith("AXO-")
    st = _wait(c, r.json()["operation_id"])
    assert st["status"] == "succeeded" and st["progress"] == 1.0 and st["result"]["source_id"].startswith("SRC-")
    assert st["result"]["candidates"] and st["result"]["mapped_into"] == []
    for ref in st["result"]["candidates"]:
        assert ka.repo.require_version(ref).status in (NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT)
    assert ka.repo.sources.require(st["result"]["source_id"]).owner == "pankaj"


def test_P3_PT3a_search_finds_governed_nuggets_and_articles_with_provenance(c, ka):
    vs = _governed(ka)
    r = _invoke(c, "knowledge.search", {"query": "refunds approval", "kind": "all"})
    assert r.status_code == 200
    st = r.json()
    assert st["status"] == "succeeded"
    hits = st["result"]["hits"]
    nug = [h for h in hits if h["kind"] == "nugget"]
    assert nug and nug[0]["id"] in {v.ref for v in vs} and nug[0]["provenance"]["source_ids"] and nug[0]["provenance"]["decision_id"]
    assert any(h["kind"] == "article" for h in hits)


def test_P4_PT3b_read_a_ref_a_canonical_id_and_a_wiki_key(c, ka):
    vs = _governed(ka)
    for item in (vs[0].ref, vs[0].canonical_id):
        st = _invoke(c, "knowledge.read", {"item_id": item}).json()
        assert st["status"] == "succeeded" and st["result"]["kind"] == "nugget" and st["result"]["item"]["canonical_id"] == vs[0].canonical_id
        prov = st["result"]["provenance"]
        assert prov["sources"] and prov["evidence"] and prov["decisions"]
    art = _invoke(c, "knowledge.read", {"item_id": "scope:DOMAIN|merchant-acquiring"}).json()
    assert art["status"] == "succeeded" and art["result"]["kind"] == "article" and art["result"]["provenance"]["statements"]


def test_P5_revise_proposes_and_retire_requests_nothing_active_changes(c, ka):
    vs = _governed(ka)
    st = _invoke(c, "knowledge.revise", {"item_id": vs[0].ref, "change": {"statement": "Refunds above $750 require manager approval."},
                                          "rationale": "policy update"}).json()
    assert st["status"] == "succeeded" and st["result"]["review_required"] is True
    rev = ka.repo.require_version(st["result"]["proposal_id"])
    assert rev.canonical_id == vs[0].canonical_id and rev.created_by == "pankaj" and ka.repo.require_version(vs[0].ref).status == NuggetStatus.ACTIVE
    st2 = _invoke(c, "knowledge.revise", {"item_id": vs[1].canonical_id, "change": {"retire": True}, "rationale": "withdrawn"}).json()
    assert st2["status"] == "succeeded" and ka.repo.require_version(st2["result"]["proposal_id"]).analysis.get("retirement_requested")


def test_P6_idempotency_returns_the_same_operation_and_one_source(c, ka):
    inp = {"kind": "text", "name": "Same", "raw_content": "Settlement runs nightly at 02:00.", "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}
    a = _invoke(c, "knowledge.acquire", inp, key="agentx-run-1").json()
    _wait(c, a["operation_id"])
    b = _invoke(c, "knowledge.acquire", inp, key="agentx-run-1").json()
    assert b["operation_id"] == a["operation_id"] and len(ka.repo.sources.where(lambda s: s.title == "Same")) == 1


def test_P7_health_aliases_and_the_knowledge_worker_search_shape(c, ka):
    _governed(ka)
    h = c.get(f"{PREFIX}/healthz").json()
    assert h["status"] in ("ok", "degraded") and h["service_id"] == "knowledge-acquisition" and h["version"] and "checks" in h and h["ok"] is True
    s1 = c.get(f"{PREFIX}/v1/knowledge/search", params={"query": "refunds"}).json()
    assert s1["status"] == "succeeded" and s1["result"]["hits"]
    s2 = c.post(f"{PREFIX}/v1/knowledge/search", json={"query": "refunds", "domain_id": "merchant-acquiring", "limit": 5}).json()
    assert s2["results"] and set(s2["results"][0]) >= {"id", "kind", "title", "snippet", "status", "scope", "provenance"} and s2["version"]
    a = c.post(f"{PREFIX}/v1/acquisitions", json={"kind": "note", "name": "n", "raw_content": "Merchants file disputes within 10 days.",
                                                  "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}})
    assert a.status_code == 202 and _wait(c, a.json()["operation_id"])["status"] == "succeeded"
    assert c.get(f"{PREFIX}/v1/acquisitions/{a.json()['operation_id']}").json()["operation_id"] == a.json()["operation_id"]
    ref = ka.repo.nuggets_by_status(NuggetStatus.ACTIVE)[0].ref
    assert c.get(f"{PREFIX}/v1/knowledge/{ref}").json()["result"]["kind"] == "nugget"
    assert (ROOT / "e2e" / "plan29_agentx_flow.py").exists()


def test_N1_the_agentx_bearer_is_required_and_the_console_token_is_refused(ka):
    with config.scoped(KA_AGENTX_TOKEN=TOKEN, KA_ACCESS_TOKEN="console-token", KA_ACCESS_POLICY="token"):
        c = TestClient(create_app(ka))
        r = c.get(f"{PREFIX}/v1/capabilities")
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized" and r.json()["error"]["retryable"] is False
        assert c.get(f"{PREFIX}/v1/capabilities", headers={"Authorization": "Bearer console-token"}).status_code == 401
        assert c.get(f"{PREFIX}/v1/capabilities", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    set_ka(None)


def test_N2_missing_permission_and_tenant_mismatch_are_forbidden(c):
    r = _invoke(c, "knowledge.revise", {"item_id": "KN-1", "change": {"retire": True}, "rationale": "x"}, perms=["knowledge.read"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r2 = _invoke(c, "knowledge.search", {"query": "x", "tenant_id": "another-tenant"})
    assert r2.json()["status"] == "failed" and r2.json()["error"]["code"] == "forbidden"


def test_N3_invalid_input_unknown_capability_and_stale_version(c):
    r = _invoke(c, "knowledge.search", {"query": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "schema_invalid" and r.json()["error"]["details"]["errors"]
    assert _invoke(c, "knowledge.nothing", {}).json()["error"]["code"] == "not_found"
    r3 = _invoke(c, "knowledge.search", {"query": "x"}, capability_version="2.0.0")
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "stale_version"
    r4 = c.post(f"{PREFIX}/v1/capabilities/knowledge.search/invoke", json={"input": "not-an-object"})
    assert r4.status_code == 400 and r4.json()["error"]["code"] == "schema_invalid"


def test_N4_same_key_different_input_is_a_conflict_and_nothing_runs_twice(c, ka):
    base = {"kind": "text", "name": "K", "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}
    a = _invoke(c, "knowledge.acquire", {**base, "raw_content": "First text body here."}, key="k-1").json()
    _wait(c, a["operation_id"])
    r = _invoke(c, "knowledge.acquire", {**base, "raw_content": "A different body."}, key="k-1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict" and r.json()["error"]["details"]["operation_id"] == a["operation_id"]
    assert len(ka.repo.sources.where(lambda s: s.title == "K")) == 1


def test_N5_cancel_rules(c, ka):
    from ka.agentx.contract import InvokeRequest
    from ka.agentx.operations import Operations
    ops = Operations(ka.repo)
    op = ops.repo.operations.put(__import__("ka.model", fromlist=["Operation"]).Operation(capability_id="knowledge.acquire"))
    ka._agentx_ops = ops
    assert c.post(f"{PREFIX}/v1/operations/{op.id}/cancel").json()["status"] == "cancelled"
    r = c.post(f"{PREFIX}/v1/operations/{op.id}/cancel")
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "not_cancellable"
    assert c.get(f"{PREFIX}/v1/operations/AXO-nope").json()["error"]["code"] == "not_found"
    done = ops.start("knowledge.search", "1.0.0", InvokeRequest(input={"query": "x"}), lambda ctx: {"hits": []}, mode="sync")
    assert done.status == "succeeded" and c.post(f"{PREFIX}/v1/operations/{done.id}/cancel").status_code == 409


def test_N6_a_failing_handler_fails_the_operation_with_the_envelope(c, ka):
    st = _invoke(c, "knowledge.revise", {"item_id": "KN-999", "change": {"statement": "x"}, "rationale": "y"}).json()
    assert st["status"] == "failed" and st["error"]["code"] == "not_found" and set(st["error"]) == {"code", "message", "retryable", "details"}
    r = _invoke(c, "knowledge.acquire", {"kind": "link", "name": "x", "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}})
    st2 = _wait(c, r.json()["operation_id"])
    assert st2["status"] == "failed" and st2["error"]["code"] == "schema_invalid"
    assert c.get(f"{PREFIX}/nuggets").status_code == 200                       # console routes unchanged


def test_P1b_everything_kA_sends_conforms_to_agentx_schemas(c, ka):
    """AgentX's own schemas (vendored, PROPOSED v1) and its code-level rules: descriptors, the list, health, operation states, errors."""
    from ka.agentx import conformance as X
    lst = c.get(f"{PREFIX}/v1/capabilities").json()
    assert X.errors("CapabilityList.schema.json", lst) == []
    for d in lst["capabilities"]:
        assert X.descriptor_errors(d) == [], d["id"]
    assert X.errors("Health.schema.json", c.get(f"{PREFIX}/healthz").json()) == []
    _governed(ka)
    ok = _invoke(c, "knowledge.search", {"query": "refunds"}).json()
    assert X.errors("OperationState.schema.json", ok) == []
    bad = _invoke(c, "knowledge.search", {"query": ""}).json()
    assert X.errors("ErrorInfo.schema.json", bad["error"]) == []
    failed = _invoke(c, "knowledge.read", {"item_id": "KN-999"}).json()
    assert X.errors("OperationState.schema.json", failed) == [] and failed["status"] == "failed"
