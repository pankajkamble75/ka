"""plan-21 (research-03 R5, R9; product test PT7) — inbound Data Platform events handled once with a durable cursor; revocation, quarantine
and deletion go through the ONE rule (`SyncService.revoke_source`) that a deleted connector file takes."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.data_platform import DataPlatformClient
from ka.data_platform.fake import FakeDataPlatform
from ka.data_platform.inbound import InboundEvents
from ka.data_platform.store import DataPlatformPhysicalStore
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S, approve_all
from ka.vocab import NuggetStatus

POLICY = b"Merchant A refunds above $500 require manager approval.\n"
TOKEN = "dp-token-TEST"


@pytest.fixture
def dp(tmp_path):
    fake = FakeDataPlatform(token=TOKEN)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://dp.test"):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False, start_workers=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        store = DataPlatformPhysicalStore(DataPlatformClient("http://dp.test", http=fake.as_http(), tenant_id="default"))
        ka.physical, ka.physical_note = store, None
        ka.ingestion.physical = store
        ka.outbox.physical = store
        yield ka, fake, store


def _approved_source(ka):
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        cands = ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops")
    approve_all(ka, cands)
    return got, cands


def test_P1_poll_handles_each_event_once_and_persists_the_cursor(dp):
    ka, fake, store = dp
    got, cands = _approved_source(ka)                          # the commit produced one event in the fake
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        c1 = ka.inbound.poll(store.client)
        c2 = ka.inbound.poll(store.client)
    assert c1["received"] == 1 and c1["handled"] == 1 and c2["received"] == 0
    st = ka.inbound.status()
    assert st["after"] == 1 and st["handled"] == 1 and Path(ka.repo.root / "dp_inbound.json").exists()
    assert InboundEvents(ka.repo, ka.bus, ka.auditor, ka.connectors).state["after"] == 1          # durable
    assert any(e["name"] == "physical.event.received" for e in ka.repo.events())


def test_P2_committed_flips_a_pending_binding_to_available(dp):
    ka, fake, store = dp
    got, _ = _approved_source(ka)
    b = ka.repo.binding_for_version(got.version.id)
    b.status = "pending"; ka.repo.physical_bindings.put(b)
    fake.events.clear(); fake._event("data.asset.committed.v1", b.dp_asset_id, b.dp_asset_version_id)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.inbound.poll(store.client)
    assert ka.repo.binding_for_version(got.version.id).status == "available"


def test_P3_PT7a_access_revoked_returns_derived_knowledge_to_review_through_the_one_rule(dp):
    ka, fake, store = dp
    got, cands = _approved_source(ka)
    b = ka.repo.binding_for_version(got.version.id)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.inbound.poll(store.client)                           # consume the commit event
        fake.revoke(b.dp_asset_id)
        out = ka.inbound.poll(store.client)
    assert out["handled"] == 1
    b2 = ka.repo.binding_for_version(got.version.id)
    assert b2.status == "revoked" and "access revoked" in b2.reason and not ka.repo.version_available(got.version.id)
    src = ka.repo.sources.require(got.source.id)
    assert src.revoked_at
    for c in cands:
        v = ka.repo.require_version(c.ref)
        assert v.status == NuggetStatus.ACTIVE and v.analysis.get("source_revoked")
        rev = ka.repo.nuggets.where(lambda n: n.canonical_id == c.canonical_id and n.status == NuggetStatus.PENDING_REVIEW)
        assert rev and rev[0].analysis["source_revoked"]["source_id"] == src.id
    assert any(e["name"] == "source.revoked" for e in ka.repo.events()) and any(a.what == "source.revoked" and "Data Platform" in a.why for a in ka.repo.audit())
    assert ka.needs_attention()["revoked_source_reviews"]


def test_P4_PT7b_deleted_marks_the_source_revoked_with_reason_deleted(dp):
    ka, fake, store = dp
    got, cands = _approved_source(ka)
    b = ka.repo.binding_for_version(got.version.id)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.inbound.poll(store.client)
        fake.delete(b.dp_asset_id)
        ka.inbound.poll(store.client)
    b2 = ka.repo.binding_for_version(got.version.id)
    assert b2.status == "revoked" and b2.reason.startswith("deleted") and ka.repo.sources.require(got.source.id).revoked_at
    assert not ka.repo.version_available(got.version.id)


def test_P5_quarantined_index_ready_and_ingestion_completed(dp):
    ka, fake, store = dp
    got, _ = _approved_source(ka)
    b = ka.repo.binding_for_version(got.version.id)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.inbound.poll(store.client)
        fake.quarantine(b.dp_asset_id)
        fake.events.append({"event_id": "evt-idx", "seq": len(fake.events) + 1, "type": "data.index.ready.v1", "asset_id": b.dp_asset_id, "asset_version_id": b.dp_asset_version_id, "derived_asset_id": "asset_text_1", "at": "x"})
        fake.events.append({"event_id": "evt-ing", "seq": len(fake.events) + 1, "type": "data.ingestion.completed.v1", "asset_id": None, "asset_version_id": None, "at": "x"})
        out = ka.inbound.poll(store.client)
    assert out["handled"] == 3
    b2 = ka.repo.binding_for_version(got.version.id)
    assert b2.status == "revoked" and "quarantined" in b2.reason and b2.extracted_text_asset_id == "asset_text_1"


def test_P6_routes_and_dashboard(dp):
    ka, fake, store = dp
    got, _ = _approved_source(ka)
    c = TestClient(create_app(ka))
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        st = c.get(f"{PREFIX}/physical/inbound").json()
        assert st["after"] == 0 and st["handled"] == 0
        r = c.post(f"{PREFIX}/physical/inbound/poll?by=ops").json()
        assert r["polled"]["handled"] == 1 and r["status"]["after"] == 1
        d = c.get(f"{PREFIX}/dashboard").json()
        assert d["physical"]["inbound"]["handled"] == 1
    set_ka(None)


def test_P7_R9_connector_deletion_and_dp_deletion_share_revoke_source(dp, tmp_path, monkeypatch):
    ka, fake, store = dp
    calls = []
    real = ka.connectors.revoke_source
    monkeypatch.setattr(ka.connectors, "revoke_source", lambda src, *, by, reason: (calls.append(reason), real(src, by=by, reason=reason))[1])
    # DP path
    got, _ = _approved_source(ka)
    b = ka.repo.binding_for_version(got.version.id)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.inbound.poll(store.client); fake.delete(b.dp_asset_id); ka.inbound.poll(store.client)
    # connector path
    root = tmp_path / "inbox"; (root / "ops").mkdir(parents=True); (root / "ops" / "sop.md").write_bytes(b"Chargebacks must be answered within 30 days.\n")
    with config.scoped(KA_CONNECTOR_ROOTS=str(root), KA_DP_SERVICE_TOKEN=TOKEN):
        conn = ka.connectors.create("local_folder", "Ops", {"root": str(root / "ops")}, owner="ops", scope=D)
        ka.connectors.sync(conn.id, by="ops")
        (root / "ops" / "sop.md").unlink()
        ka.connectors.sync(conn.id, by="ops")
    assert calls == ["deleted at the Data Platform", "deleted at the connector"]


def test_N1_unknown_event_types_are_recorded_and_ignored(dp):
    ka, fake, store = dp
    fake.events.append({"event_id": "evt-x", "seq": 1, "type": "data.something.new.v9", "asset_id": "asset_zzz", "asset_version_id": None, "at": "x"})
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        out = ka.inbound.poll(store.client)
    assert out["ignored"] == 1 and ka.inbound.status()["after"] == 1 and any(e["name"] == "physical.event.received" for e in ka.repo.events())


def test_N2_events_for_unknown_assets_are_unmatched_not_errors(dp):
    ka, fake, store = dp
    fake._event("data.asset.access_revoked.v1", "asset_unknown")
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        out = ka.inbound.poll(store.client)
    assert out["unmatched"] == 1 and ka.inbound.status()["unmatched"] == 1


def test_N3_a_duplicate_event_id_is_handled_once(dp):
    ka, fake, store = dp
    got, cands = _approved_source(ka)
    b = ka.repo.binding_for_version(got.version.id)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.inbound.poll(store.client)
        fake.revoke(b.dp_asset_id)
        ka.inbound.poll(store.client)
        n_reviews = len(ka.needs_attention()["revoked_source_reviews"])
        ka.inbound.state["after"] = 0                              # a reset cursor replays everything
        out = ka.inbound.poll(store.client)
    assert out["duplicate"] == out["received"] and len(ka.needs_attention()["revoked_source_reviews"]) == n_reviews


def test_N4_a_failed_poll_leaves_the_cursor_and_does_not_raise(dp):
    ka, fake, store = dp
    _approved_source(ka)
    fake.fail_next(1)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        out = ka.inbound.poll(store.client)
        assert out["received"] == 0 and ka.inbound.status()["after"] == 0 and ka.inbound.last_error
        assert ka.inbound.poll(store.client)["handled"] == 1 and ka.inbound.last_error is None


def test_N5_the_local_backend_registers_no_poll_and_writes_no_cursor(tmp_path):
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
    assert ka.outbox_worker.ticks == [] and not (tmp_path / "s" / "dp_inbound.json").exists()
    c = TestClient(create_app(ka))
    assert c.post(f"{PREFIX}/physical/inbound/poll").status_code == 409
    set_ka(None)
    assert Path("e2e/plan21_inbound_flow.py").exists()
