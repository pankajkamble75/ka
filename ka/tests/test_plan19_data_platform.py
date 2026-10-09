"""plan-19 (research-03 R11 + R2's HTTP half; product tests PT1, PT2, PT3, PT5-physical, PT8) — the Data Platform contract as fixtures,
the wire-level fake, and the HTTP physical store. No network: the fake is injected as the client's transport."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.data_platform import DataPlatformClient, DataPlatformError
from ka.data_platform.fake import FakeDataPlatform
from ka.data_platform.store import DataPlatformPhysicalStore
from ka.llm import StubLLMProvider
from ka.physical import LocalPhysicalStore, select_physical_store
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S
from ka.vocab import Visibility

POLICY = b"Merchant A refunds above $500 require manager approval.\n"
TOKEN = "dp-service-token-TEST"
FIX = Path(__file__).resolve().parent / "fixtures" / "dp_contract"


def _client(fake: FakeDataPlatform) -> DataPlatformClient:
    return DataPlatformClient("http://dp.test", http=fake.as_http(), tenant_id="default")


@pytest.fixture
def dp(tmp_path):
    fake = FakeDataPlatform(token=TOKEN)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://dp.test"):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        store = DataPlatformPhysicalStore(_client(fake))
        ka.physical, ka.physical_note = store, None
        ka.ingestion.physical = store
        yield ka, fake, store


def test_P1_the_fake_answers_every_contract_fixture():
    fake = FakeDataPlatform(token=TOKEN)
    H = {"Authorization": f"Bearer {TOKEN}", "X-KA-Tenant": "default"}
    fx = {p.name: json.loads(p.read_text()) for p in sorted(FIX.glob("*.json"))}
    assert len(fx) == 10
    s, _, raw = fake.handle("POST", "/v1/assets/uploads", {**H, "Idempotency-Key": "ka:default:SRC-1:1"}, json.dumps(fx["01_create_upload.json"]["request"]["json"]).encode())
    assert s == 201 and set(json.loads(raw)) >= set(fx["01_create_upload.json"]["response"]["json_keys"])
    uid = json.loads(raw)["upload_id"]
    s, _, _ = fake.handle("PUT", f"/v1/assets/uploads/{uid}/content", H, base64.b64decode(fx["02_upload_content.json"]["request"]["body_b64"]))
    assert s == 204
    s, _, raw = fake.handle("POST", f"/v1/assets/uploads/{uid}/commit", H, json.dumps(fx["03_commit.json"]["request"]["json"]).encode())
    d = json.loads(raw); assert s == 200 and d["sha256"] == fx["03_commit.json"]["response"]["json_values"]["sha256"] and d["state"] == "available"
    aid, vid = d["asset_id"], d["asset_version_id"]
    # 04 wrong sha on a fresh upload
    s, _, raw = fake.handle("POST", "/v1/assets/uploads", {**H, "Idempotency-Key": "ka:default:SRC-9:1"}, b'{"asset_type":"source_document","owner":"ops","visibility":"ENTERPRISE"}')
    u2 = json.loads(raw)["upload_id"]; fake.handle("PUT", f"/v1/assets/uploads/{u2}/content", H, POLICY)
    s, _, raw = fake.handle("POST", f"/v1/assets/uploads/{u2}/commit", H, json.dumps(fx["04_commit_checksum_mismatch.json"]["request"]["json"]).encode())
    assert s == 422 and json.loads(raw)["code"] == "checksum_mismatch"
    # 05 same key, different bytes
    s, _, raw = fake.handle("POST", "/v1/assets/uploads", {**H, "Idempotency-Key": "ka:default:SRC-1:1"}, json.dumps(fx["05_idempotency_conflict.json"]["request"]["json"]).encode())
    u3 = json.loads(raw)["upload_id"]; fake.handle("PUT", f"/v1/assets/uploads/{u3}/content", H, base64.b64decode(fx["05_idempotency_conflict.json"]["request"]["then_content_b64"]))
    s, _, raw = fake.handle("POST", f"/v1/assets/uploads/{u3}/commit", H, json.dumps({"sha256": hashlib.sha256(b"different bytes\n").hexdigest()}).encode())
    assert s == 409 and json.loads(raw)["code"] == "idempotency_conflict"
    # 06 denied read of a PERSONAL asset
    s, _, raw = fake.handle("POST", "/v1/assets/uploads", {**H, "Idempotency-Key": "ka:default:SRC-2:1"}, b'{"asset_type":"source_document","owner":"ops","visibility":"PERSONAL"}')
    u4 = json.loads(raw)["upload_id"]; fake.handle("PUT", f"/v1/assets/uploads/{u4}/content", H, POLICY)
    d4 = json.loads(fake.handle("POST", f"/v1/assets/uploads/{u4}/commit", H, json.dumps({"sha256": hashlib.sha256(POLICY).hexdigest()}).encode())[2])
    s, _, raw = fake.handle("GET", f"/v1/assets/{d4['asset_id']}/versions/{d4['asset_version_id']}/content", {**H, "X-KA-Owner": "someone-else"}, None)
    assert s == 403 and json.loads(raw)["code"] == "policy_denied" and fake.denials
    # 07 derived
    req = fx["07_put_derived.json"]["request"]["json"]; req["parent_asset_id"], req["parent_asset_version_id"] = aid, vid
    s, _, raw = fake.handle("POST", "/v1/assets/derived", {**H, "Idempotency-Key": "KN-001:v1:ACTIVE"}, json.dumps(req).encode())
    assert s == 200 and set(json.loads(raw)) >= set(fx["07_put_derived.json"]["response"]["json_keys"])
    # 08 events
    s, _, raw = fake.handle("GET", "/v1/events?after=0&limit=200", H, None)
    ev = json.loads(raw); assert s == 200 and ev["events"] and set(ev) >= {"events", "next_after"}
    assert set(fx["08_events.json"]["response"]["event_types"]) >= {e["type"] for e in ev["events"]}
    # 09 unavailable, 10 unauthenticated
    fake.fail_next(1); s, _, raw = fake.handle("POST", "/v1/assets/uploads", H, b"{}"); assert s == 503 and json.loads(raw)["retryable"] is True
    s, _, raw = fake.handle("POST", "/v1/assets/uploads", {"X-KA-Tenant": "default"}, b"{}"); assert s == 401 and json.loads(raw)["code"] == "unauthenticated"


def test_P2_client_round_trip_carries_the_token_read_at_call_time():
    fake = FakeDataPlatform(token=TOKEN)
    c = _client(fake)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        uid = c.create_upload(asset_type="source_document", content_type="text/markdown", idempotency_key="ka:default:SRC-1:1", owner="ops", visibility="ENTERPRISE")
        c.upload_content(uid, POLICY)
        d = c.commit(uid, sha256=hashlib.sha256(POLICY).hexdigest())
    assert d["state"] == "available" and d["sha256"] == hashlib.sha256(POLICY).hexdigest()
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        assert c.get_content(d["asset_id"], d["asset_version_id"], owner="ops") == POLICY and c.exists(d["asset_id"], d["asset_version_id"])
    with config.scoped(KA_DP_SERVICE_TOKEN="wrong"):
        with pytest.raises(DataPlatformError) as ei:
            c.commit(uid, sha256="0" * 64)
        assert ei.value.status == 401 and ei.value.code == "unauthenticated" and ei.value.retryable is False


def test_P3_PT1_ingest_on_the_dp_backend_same_shape_no_blob_binding_available(dp):
    ka, fake, store = dp
    c = TestClient(create_app(ka))
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        r = c.post(f"{PREFIX}/sources/paste", json={"text": POLICY.decode(), "title": "policy", "owner": "ops", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "markdown": True})
    assert r.status_code == 200 and set(r.json()) >= {"source", "source_version", "extraction_status", "candidates", "is_new_version"}
    vid = r.json()["source_version"]["id"]
    b = ka.repo.binding_for_version(vid)
    assert b.backend == "data_platform" and b.status == "available" and b.sha256 == hashlib.sha256(POLICY).hexdigest()
    assert b.dp_asset_id in fake.assets and fake.assets[b.dp_asset_id]["versions"][b.dp_asset_version_id]["bytes"] == POLICY
    assert not (ka.repo.root / "blobs").exists() or not list((ka.repo.root / "blobs").glob("*"))
    assert ka.repo.source_versions.require(vid).stored_path is None and ka.repo.version_available(vid)
    set_ka(None)


def test_P4_PT2_a_changed_document_is_a_new_asset_version_and_v1_is_untouched(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        g1 = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        g2 = ka.ingestion.upload(filename="policy.md", data=POLICY.replace(b"$500", b"$1,000"), owner="ops", scope=D)
    b1, b2 = ka.repo.binding_for_version(g1.version.id), ka.repo.binding_for_version(g2.version.id)
    assert g2.version.version == 2 and b2.dp_asset_version_id != b1.dp_asset_version_id
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        assert store.client.get_content(b1.dp_asset_id, b1.dp_asset_version_id, owner="ops") == POLICY


def test_P5_PT3_identical_bytes_two_owners_two_sources_two_bindings_no_cross_read(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ga = ka.ingestion.write_note(text=POLICY.decode(), owner="alice", scope=D, visibility=Visibility.PERSONAL)
        gb = ka.ingestion.write_note(text=POLICY.decode(), owner="bob", scope=D, visibility=Visibility.PERSONAL)
    assert ga.source.id != gb.source.id
    ba, bb = ka.repo.binding_for_version(ga.version.id), ka.repo.binding_for_version(gb.version.id)
    assert ba.dp_asset_id != bb.dp_asset_id and ba.sha256 == bb.sha256
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        with pytest.raises(DataPlatformError) as ei:
            store.client.get_content(ba.dp_asset_id, ba.dp_asset_version_id, owner="bob")
    assert ei.value.code == "policy_denied" and fake.denials


def test_P6_reextract_reads_through_dp(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        n_before = sum(1 for m, p in fake.calls if p.endswith("/content") and m == "GET")
        again = ka.ingestion.reextract(g.source.id, owner="ops")
    assert again.version.version == 2 and "refunds" in again.version.text
    assert sum(1 for m, p in fake.calls if p.endswith("/content") and m == "GET") == n_before + 1


def test_P7_put_derived_stores_a_json_artefact_with_provenance(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        b = ka.repo.binding_for_version(g.version.id)
        from ka.physical import PhysicalRef
        parent = PhysicalRef(backend="data_platform", asset_id=b.dp_asset_id, asset_version_id=b.dp_asset_version_id, sha256=b.sha256)
        ref = store.put_derived("nugget_version", b'{"ref": "KN-001:v1"}', parent=parent, provenance={"nugget_ref": "KN-001:v1"}, idempotency_key="KN-001:v1:ACTIVE")
    assert ref.asset_id in fake.assets and fake.assets[ref.asset_id]["parent"] == (b.dp_asset_id, b.dp_asset_version_id)
    assert fake.assets[ref.asset_id]["provenance"] == {"nugget_ref": "KN-001:v1"}


def test_P8_PT8_flow_exists_and_no_cloud_sdk_is_imported():
    assert Path("e2e/plan19_dp_flow.py").exists()
    bad = [p for p in Path("ka").rglob("*.py") if re.search(r"^\s*(import|from)\s+google(\.|\s)", p.read_text(encoding="utf-8"), re.M)]
    assert bad == []


def test_N1_a_wrong_sha_commit_yields_a_failed_binding(dp, monkeypatch):
    ka, fake, store = dp
    real = store.client.commit
    monkeypatch.setattr(store.client, "commit", lambda uid, *, sha256: real(uid, sha256="0" * 64))
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    b = ka.repo.binding_for_version(g.version.id)
    assert b.status == "failed" and "checksum_mismatch" in (b.reason or "") and not ka.repo.version_available(g.version.id)


def test_N2_idempotency_replay_and_conflict(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        r1 = store.put(POLICY, content_type="text/markdown", sha256=hashlib.sha256(POLICY).hexdigest(), idempotency_key="ka:default:SRC-1:1:SRV-a", owner="ops", visibility="ENTERPRISE", tenant_id="default")
        r2 = store.put(POLICY, content_type="text/markdown", sha256=hashlib.sha256(POLICY).hexdigest(), idempotency_key="ka:default:SRC-1:1:SRV-b", owner="ops", visibility="ENTERPRISE", tenant_id="default")
        assert (r1.asset_id, r1.asset_version_id) == (r2.asset_id, r2.asset_version_id)
        other = POLICY.replace(b"$500", b"$900")
        with pytest.raises(DataPlatformError) as ei:
            store.put(other, content_type="text/markdown", sha256=hashlib.sha256(other).hexdigest(), idempotency_key="ka:default:SRC-1:1:SRV-c", owner="ops", visibility="ENTERPRISE", tenant_id="default")
    assert ei.value.status == 409 and ei.value.code == "idempotency_conflict"


def test_N3_dp_down_yields_a_failed_retryable_binding_and_nothing_raises(dp):
    ka, fake, store = dp
    fake.fail_next(3)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    b = ka.repo.binding_for_version(g.version.id)
    assert b.status == "failed" and "unavailable" in (b.reason or "") and g.source.extraction_status.value == "EXTRACTED"   # extraction still ran from the bytes in hand


def test_N4_denied_read_is_a_policy_denied_error(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        g = ka.ingestion.write_note(text="private", owner="alice", scope=D, visibility=Visibility.PERSONAL)
        b = ka.repo.binding_for_version(g.version.id)
        with pytest.raises(DataPlatformError, match="policy_denied"):
            store.client.get_content(b.dp_asset_id, b.dp_asset_version_id, owner="mallory")
    assert fake.denials[-1]["owner"] == "mallory"


def test_N5_selection_fails_closed_without_a_base_url_and_never_silently_local_with_one(tmp_path):
    with config.scoped(KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL=""):
        st, note = select_physical_store(tmp_path)
    assert isinstance(st, LocalPhysicalStore) and "KA_DP_BASE_URL unset" in note
    with config.scoped(KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://dp.test"):
        st, note = select_physical_store(tmp_path)
    assert isinstance(st, DataPlatformPhysicalStore) and note is None
    fake = FakeDataPlatform(token=TOKEN)
    st.client.http = fake.as_http()
    with config.scoped(KA_DP_SERVICE_TOKEN=""):
        with pytest.raises(DataPlatformError) as ei:
            st.put(POLICY, content_type="text/plain", sha256=hashlib.sha256(POLICY).hexdigest(), idempotency_key="ka:default:S:1:V", owner="o", visibility="ENTERPRISE", tenant_id="default")
    assert ei.value.status == 401


def test_N6_the_service_token_never_reaches_storage_or_fixtures(dp):
    ka, fake, store = dp
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path(ka.repo.root).rglob("*") if p.is_file())
    assert TOKEN not in blob
    assert TOKEN not in "".join(p.read_text() for p in FIX.glob("*.json")) and TOKEN not in Path("docs/contracts/data-platform-v1-ka-subset.md").read_text()
