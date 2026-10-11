"""plan-34 (NEXOS integration v1) — KA registers only actually available capabilities (publish needs a real Knowledge Worker), exposes its
existing console screens in Knowledge Worker's manifest shape, and the governed journey holds: acquire → review by a person → publish →
Knowledge Worker proposal (MOCK Knowledge Worker, labelled), plus rejected changes, conflicting versions, duplicate delivery and a missing
Data Platform."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.knowledge_worker.client import KnowledgeWorkerClient
from ka.knowledge_worker.fake import FakeKnowledgeWorker
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import A, B, C, D, P, S, approve_all, ingest_policy
from ka.vocab import NuggetStatus

AX, KW = "agentx-token-TEST", "kw-token"
PERMS = ["knowledge.acquire", "knowledge.read", "knowledge.revise", "knowledge.review", "knowledge.publish"]


def _ka(tmp_path, **cfg):
    with config.scoped(**cfg):
        k = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False, start_workers=False)
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D), (C, D)]:
        k.register_scope(s, p)
    return k


class _C:
    """A TestClient that keeps the AgentX token and the plan-34 setting in force for every call."""

    def __init__(self, ka, **cfg):
        self.ka, self.cfg = ka, {"KA_AGENTX_TOKEN": AX, **cfg}
        with config.scoped(**self.cfg):
            self.c = TestClient(create_app(ka))
        self.c.headers.update({"Authorization": f"Bearer {AX}"})

    def __getattr__(self, m):
        def call(*a, **kw):
            with config.scoped(**self.cfg):
                return getattr(self.c, m)(*a, **kw)
        return call


def _invoke(c, cap, inp, user="alice", key=None):
    return c.post(f"{PREFIX}/v1/capabilities/{cap}/invoke", json={"schema_version": "1", "input": inp,
                                                                  "caller": {"service_id": "agentx", "user": user, "permissions": PERMS}},
                  headers={"Idempotency-Key": key} if key else {})


def _wait(c, op, until=("succeeded", "failed", "awaiting_input"), timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get(f"{PREFIX}/v1/operations/{op}").json()
        if st["status"] in until:
            return st
        time.sleep(0.05)
    return st


def _input(c, st, values, by="alice"):
    return c.post(f"{PREFIX}/v1/operations/{st['operation_id']}/input",
                  json={"interaction_id": st["interaction"]["interaction_id"], "values": values, "submitted_by": by}).json()


@pytest.fixture(autouse=True)
def _reset():
    yield
    set_ka(None)


def _kw_ka(tmp_path, fake):
    k = _ka(tmp_path, KA_GRAPH_MODE="kw", KA_KW_URL="http://kw.test", KA_KW_TOKEN=KW, KA_KW_PUBLISH_WAIT_S=0.5)
    k.adapter.client = KnowledgeWorkerClient("http://kw.test", token=KW, http=fake.as_http())
    fake.add_substructure("merchant-acquiring")
    return k


def test_P1_publish_is_listed_with_a_real_knowledge_worker(tmp_path):
    k = _kw_ka(tmp_path, FakeKnowledgeWorker(token=KW))
    c = _C(k, KA_AGENTX_LOCAL_PUBLISH=False)
    ids = {d["id"] for d in c.get(f"{PREFIX}/v1/capabilities").json()["capabilities"]}
    assert "knowledge.publish" in ids and len(ids) == 7
    assert c.get(f"{PREFIX}/healthz").json()["checks"]["capabilities_unavailable"] == {}


def test_P2_local_publish_opt_in_lists_it_in_memory_mode(tmp_path):
    c = _C(_ka(tmp_path), KA_AGENTX_LOCAL_PUBLISH=True)
    assert "knowledge.publish" in {d["id"] for d in c.get(f"{PREFIX}/v1/capabilities").json()["capabilities"]}


def test_P3_screen_manifest_in_knowledge_workers_shape(tmp_path):
    c = _C(_ka(tmp_path))
    m = c.get(f"{PREFIX}/v1/screens").json()
    assert [s["id"] for s in m["screens"]] == ["ka.sources", "ka.research", "ka.wiki", "ka.nuggets", "ka.reviews", "ka.publications"]
    for s in m["screens"]:
        assert set(s) >= {"id", "title", "path", "launch_url", "embed_url", "deep_link_params", "requires", "provided_by"}
        assert s["launch_url"].startswith(("http://", "https://")) and s["launch_url"].endswith(s["path"]) and s["path"].startswith("/console/#/")
        assert s["embed_url"] is None and s["provided_by"] == "knowledge-acquisition"
    c.cfg["KA_PUBLIC_BASE_URL"] = "https://ka.example"
    assert c.get(f"{PREFIX}/v1/screens").json()["screens"][0]["launch_url"] == "https://ka.example/console/#/add"


def test_P4_MOCK_KW_journey_acquire_review_publish_reaches_kw_with_lineage(tmp_path):
    fake = FakeKnowledgeWorker(token=KW)                      # MOCK Knowledge Worker (wire-level fake, plan-31)
    k = _kw_ka(tmp_path, fake)
    c = _C(k, KA_AGENTX_LOCAL_PUBLISH=False)
    acq = _wait(c, _invoke(c, "knowledge.acquire", {"kind": "text", "name": "Refund SOP", "raw_content": "Refunds above $500 require manager approval.",
                                                    "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}).json()["operation_id"])
    ref = acq["result"]["candidates"][0]
    rv = _wait(c, _invoke(c, "knowledge.review", {"item_id": ref}).json()["operation_id"])
    assert rv["status"] == "awaiting_input"
    assert _input(c, rv, {"outcome": "APPROVE", "reason": "matches the SOP"})["status"] == "succeeded"
    pub = _wait(c, _invoke(c, "knowledge.publish", {"item_id": ref}).json()["operation_id"], until=("succeeded", "failed"))
    assert pub["status"] == "succeeded", pub
    assert k.repo.require_version(ref).status == NuggetStatus.ACTIVE
    req = fake.requests[-1]
    assert req["knowledge_refs"][0]["nugget_ref"] == ref and all(
        (o.get("node") or o.get("edge") or {}).get("props", {}).get("knowledge_lineage") for o in req["ops"] if not o["op"].startswith("remove"))
    types = [e["type"] for e in c.get(f"{PREFIX}/v1/events?after=0&limit=1000").json()["events"]]
    assert {"knowledge.acquisition.completed", "knowledge.review.required", "knowledge.publication.approved", "knowledge.publication.completed"} <= set(types)


def test_P5_duplicate_delivery_same_key_same_operation_and_stable_event_ids(tmp_path):
    c = _C(_ka(tmp_path))
    inp = {"kind": "text", "name": "SOP", "raw_content": "Refunds above $500 require manager approval.",
           "scope": {"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}}
    a = _invoke(c, "knowledge.acquire", inp, key="dup-1").json()
    b = _invoke(c, "knowledge.acquire", inp, key="dup-1").json()
    assert a["operation_id"] == b["operation_id"]
    _wait(c, a["operation_id"], until=("succeeded", "failed"))
    e1 = [e["event_id"] for e in c.get(f"{PREFIX}/v1/events?after=0").json()["events"]]
    e2 = [e["event_id"] for e in c.get(f"{PREFIX}/v1/events?after=0").json()["events"]]
    assert e1 and e1 == e2 and len(set(e1)) == len(e1)


def test_P6_missing_data_platform_leaves_the_upload_pending_not_lost(tmp_path):
    k = _ka(tmp_path, KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://127.0.0.1:9", KA_DP_API="v1", KA_DP_TIMEOUT=1.0)
    with config.scoped(KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://127.0.0.1:9", KA_DP_API="v1", KA_DP_TIMEOUT=1.0):
        got = k.ingestion.upload(filename="sop.md", data=b"Refunds above $500 require manager approval.", owner="ops", scope=D)
    b = k.repo.binding_for_version(got.version.id)
    assert k.physical.name == "data_platform" and b.status == "pending" and k.repo.dp_outbox.all()
    assert (k.repo.root / "spool" / f"{got.version.id}.bin").exists()


def test_N1_memory_mode_omits_publish_and_says_why(tmp_path):
    c = _C(_ka(tmp_path), KA_AGENTX_LOCAL_PUBLISH=False)
    ids = {d["id"] for d in c.get(f"{PREFIX}/v1/capabilities").json()["capabilities"]}
    assert "knowledge.publish" not in ids and len(ids) == 6
    why = c.get(f"{PREFIX}/healthz").json()["checks"]["capabilities_unavailable"]
    assert "Knowledge Worker" in why["knowledge.publish"]


def test_N2_invoking_an_omitted_capability_is_unavailable_and_records_nothing(tmp_path):
    k = _ka(tmp_path)
    c = _C(k, KA_AGENTX_LOCAL_PUBLISH=False)
    r = _invoke(c, "knowledge.publish", {"item_id": "KN-001:v1"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable" and r.json()["error"]["retryable"] is False
    assert not k.repo.operations.all()


def test_N3_push_registration_sends_only_available_capabilities(tmp_path, monkeypatch):
    k = _ka(tmp_path)
    sent = {}
    import ka.agentx.registration as reg
    monkeypatch.setattr(reg, "push_capabilities", lambda _ka, descs: sent.setdefault("ids", [d["id"] for d in descs]) and {"pushed": True})
    with config.scoped(KA_AGENTX_LOCAL_PUBLISH=False):
        k.agentx_push()
    assert len(sent["ids"]) == 6 and "knowledge.publish" not in sent["ids"]


def test_N4_a_rejected_change_is_never_published(tmp_path):
    k = _ka(tmp_path)
    c = _C(k)
    vs = ingest_policy(k, D, "Refunds above $500 require manager approval.")
    rv = _wait(c, _invoke(c, "knowledge.review", {"item_id": vs[0].ref}).json()["operation_id"])
    assert _input(c, rv, {"outcome": "REJECT", "reason": "not our policy"})["status"] == "succeeded"
    assert k.repo.require_version(vs[0].ref).status == NuggetStatus.REJECTED
    assert not k.repo.proposals.where(lambda p: vs[0].ref in p.knowledge_change_ids)
    types = {e["type"] for e in c.get(f"{PREFIX}/v1/events?after=0&limit=1000").json()["events"]}
    assert not types & {"knowledge.publication.approved", "knowledge.publication.completed"}


def test_N5_conflicting_versions_wait_for_a_person(tmp_path):
    k = _ka(tmp_path)
    c = _C(k)
    approve_all(k, ingest_policy(k, D, "Refunds above $500 require manager approval."))
    new = ingest_policy(k, D, "Refunds above $900 require manager approval.")[0]
    st = _wait(c, _invoke(c, "knowledge.resolve_conflict", {"item_id": new.ref}).json()["operation_id"])
    assert st["status"] == "awaiting_input" and st["interaction"]["required_permission"] == "knowledge.review"
    r = c.post(f"{PREFIX}/v1/operations/{st['operation_id']}/input", json={"interaction_id": st["interaction"]["interaction_id"],
                                                                            "values": {"outcome": "ACCEPT_NEW", "reason": "x"}})
    assert r.status_code == 403 and k.repo.require_version(new.ref).status != NuggetStatus.ACTIVE


def test_N6_healthz_accepts_agentx_token_from_another_host_but_nothing_else_does(tmp_path):
    """Found by the live evidence probe (2026-10-11): AgentX's token got 401 on /healthz over the public interface."""
    k = _ka(tmp_path)
    with config.scoped(KA_AGENTX_TOKEN=AX, KA_ACCESS_TOKEN="console-admin", KA_ACCESS_POLICY="token"):
        remote = TestClient(create_app(k), base_url="http://203.0.113.9", client=("203.0.113.9", 5000))
        assert remote.get(f"{PREFIX}/healthz", headers={"Authorization": f"Bearer {AX}"}).status_code == 200
        assert remote.get(f"{PREFIX}/healthz").status_code == 401
        assert remote.get(f"{PREFIX}/sources", headers={"Authorization": f"Bearer {AX}"}).status_code == 401
        assert remote.get(f"{PREFIX}/healthz", headers={"Authorization": "Bearer console-admin"}).status_code == 200
