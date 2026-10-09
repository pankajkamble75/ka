"""plan-18 (research-03 R2, R3) — the PhysicalStore port beneath ingestion, the local store, and the PhysicalBinding that gates a
version. The Data Platform store, fake and fixtures are plan-19."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config, security
from ka.api import PREFIX, create_app, set_ka
from ka.model import PhysicalBinding
from ka.physical import LocalPhysicalStore, select_physical_store
from ka.tests.conftest import D
from ka.vocab import AuthorityType, Visibility

POLICY = b"Merchant A refunds above $500 require manager approval.\n"


def test_P1_local_store_writes_the_same_blob_path_and_round_trips(tmp_path):
    st = LocalPhysicalStore(tmp_path)
    sha = hashlib.sha256(POLICY).hexdigest()
    ref = st.put(POLICY, content_type="text/plain", sha256=sha, idempotency_key="ka:default:SRC-1:1:SRV-abc", owner="u", visibility="ENTERPRISE", tenant_id="default", filename_hint="policy.md")
    assert ref.backend == "local" and ref.state == "available" and ref.sha256 == sha and ref.asset_id == "SRV-abc"
    assert Path(ref.locator) == tmp_path / "blobs" / "SRV-abc.md" and st.get(ref) == POLICY and st.exists(ref)
    d = st.put_derived("nugget_version", b'{"a": 1}', parent=ref, provenance={"x": 1}, idempotency_key="KN-001:v1")
    assert Path(d.locator) == tmp_path / "derived" / "nugget_version" / "KN-001_v1.json" and d.content_type == "application/json"


def test_P2_an_upload_gets_an_available_binding_and_stored_path_still_works(ka):
    got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D, visibility=Visibility.TEAM)
    b = ka.repo.binding_for_version(got.version.id)
    assert b is not None and (b.tenant_id, b.ka_source_id, b.ka_source_version) == ("default", got.source.id, 1)
    assert b.backend == "local" and b.status == "available" and b.sha256 == hashlib.sha256(POLICY).hexdigest()
    assert b.owner == "ops" and b.visibility == Visibility.TEAM and b.locator == got.version.stored_path
    assert Path(got.version.stored_path).read_bytes() == POLICY and ka.repo.version_available(got.version.id)


def test_P3_a_changed_document_gets_its_own_binding_and_leaves_version_1_alone(ka):
    g1 = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    g2 = ka.ingestion.upload(filename="policy.md", data=POLICY.replace(b"$500", b"$1,000"), owner="ops", scope=D)
    assert g2.source.id == g1.source.id and g2.version.version == 2
    b1, b2 = ka.repo.binding_for_version(g1.version.id), ka.repo.binding_for_version(g2.version.id)
    assert b1.ka_source_version == 1 and b2.ka_source_version == 2 and b1.sha256 != b2.sha256
    assert Path(b1.locator).read_bytes() == POLICY and Path(b2.locator).read_bytes() != POLICY


def test_P4_every_channel_passes_the_funnel_research_and_connector_sources_get_bindings(ka, tmp_path):
    from ka.vocab import AcquisitionChannel, SourceType
    got = ka.ingestion.record_derived(title="finding", text="Settlement occurs after clearing.", owner="agent", scope=D, channel=AcquisitionChannel.RESEARCH,
                                      source_type=SourceType.RESEARCH, authority=AuthorityType.LLM_GENERATED, visibility=Visibility.ENTERPRISE)
    assert ka.repo.binding_for_version(got.version.id).status == "available"
    root = tmp_path / "inbox"; (root / "ops").mkdir(parents=True); (root / "ops" / "sop.md").write_bytes(POLICY)
    with config.scoped(KA_CONNECTOR_ROOTS=str(root)):
        conn = ka.connectors.create("local_folder", "Ops", {"root": str(root / "ops")}, owner="ops", scope=D)
        ka.connectors.sync(conn.id, by="ops")
    src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
    assert ka.repo.binding_for_version(src.current_version_id).status == "available"


def test_P5_reextract_reads_through_the_port_and_legacy_versions_still_work(ka):
    got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    again = ka.ingestion.reextract(got.source.id, owner="ops")
    assert again.version.version == 2 and again.version.text.startswith("Merchant A refunds")
    # a legacy version: stored_path only, no binding
    legacy = ka.ingestion.upload(filename="old.md", data=b"Legacy note about refunds.\n", owner="ops", scope=D)
    b = ka.repo.binding_for_version(legacy.version.id); ka.repo.physical_bindings.delete(b.id) if hasattr(ka.repo.physical_bindings, "delete") else None
    if ka.repo.binding_for_version(legacy.version.id) is None:
        assert ka.repo.version_available(legacy.version.id)
        assert ka.ingestion.reextract(legacy.source.id, owner="ops").version.version == 2


@pytest.fixture
def client(ka):
    c = TestClient(create_app(ka))
    yield c, ka
    set_ka(None)


def test_P6_source_detail_lists_bindings_and_the_status_route_reports_the_backend(client):
    c, ka = client
    got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    d = c.get(f"{PREFIX}/sources/{got.source.id}").json()
    assert d["bindings"] and d["bindings"][0]["status"] == "available" and d["bindings"][0]["source_version_id"] == got.version.id
    st = c.get(f"{PREFIX}/physical/status").json()
    assert st["backend"] == "local" and st["tenant_id"] == "default" and st["bindings"] >= 1 and st["by_status"]["available"] >= 1
    dash = c.get(f"{PREFIX}/dashboard").json()
    assert dash["physical"]["backend"] == "local"


def test_P7_live_flow_exists():
    assert Path("e2e/plan18_physical_flow.py").exists()


def test_N1_a_blocked_link_gets_a_failed_binding_and_no_blob(ka, monkeypatch):
    monkeypatch.setattr(security, "_resolve", lambda host: ["127.0.0.1"])
    before = set((ka.repo.root / "blobs").glob("*")) if (ka.repo.root / "blobs").exists() else set()
    got = ka.ingestion.link(url="http://127.0.0.1/secret", owner="ops", scope=D)
    b = ka.repo.binding_for_version(got.version.id)
    assert b.status == "failed" and "blocked" in (b.reason or "") and not ka.repo.version_available(got.version.id)
    after = set((ka.repo.root / "blobs").glob("*")) if (ka.repo.root / "blobs").exists() else set()
    assert after == before


def test_N2_unavailable_backends_fail_closed_to_local_with_a_note(tmp_path):
    with config.scoped(KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL=""):
        st, note = select_physical_store(tmp_path)
    assert isinstance(st, LocalPhysicalStore) and "KA_DP_BASE_URL unset" in note      # plan-19 supplied the store; without a URL it still fails closed
    with config.scoped(KA_STORAGE_BACKEND="s3-magic"):
        st, note = select_physical_store(tmp_path)
    assert isinstance(st, LocalPhysicalStore) and "failing closed" in note
    with config.scoped(KA_STORAGE_BACKEND="local"):
        assert select_physical_store(tmp_path)[1] is None


def test_N3_a_binding_key_is_unique_and_a_committed_target_is_immutable(ka):
    got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    b = ka.repo.binding_for_version(got.version.id)
    same = ka.repo.put_binding(PhysicalBinding(tenant_id="default", ka_source_id=got.source.id, ka_source_version=1, source_version_id="SRV-other",
                                               backend="local", sha256=b.sha256))
    assert same.id == b.id                                                  # idempotent
    with pytest.raises(ValueError, match="immutable"):
        ka.repo.put_binding(PhysicalBinding(tenant_id="default", ka_source_id=got.source.id, ka_source_version=1, source_version_id="SRV-x",
                                            backend="local", sha256="f" * 64))


def test_N4_a_failed_version_is_not_available_and_reextract_refuses_it(ka, monkeypatch):
    monkeypatch.setattr(security, "_resolve", lambda host: ["127.0.0.1"])
    got = ka.ingestion.link(url="http://127.0.0.1/secret", owner="ops", scope=D)
    assert not ka.repo.version_available(got.version.id)
    with pytest.raises(ValueError, match="not available \\(failed"):
        ka.ingestion.reextract(got.source.id, owner="ops")


def test_N5_legacy_availability_follows_the_file(ka):
    got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    b = ka.repo.binding_for_version(got.version.id)
    # simulate a pre-plan-18 version: remove the binding record
    (ka.repo.root / "physical_bindings" / f"{b.id}.json").unlink()
    ka.repo.physical_bindings._cache = None
    assert ka.repo.binding_for_version(got.version.id) is None and ka.repo.version_available(got.version.id)
    Path(got.version.stored_path).unlink()
    assert not ka.repo.version_available(got.version.id)
