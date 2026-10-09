"""plan-22 (research-03 R6, R7; product tests PT4, PT5) — nugget versions become immutable derived artefacts on knowledge events through a
service subscriber (never governance); bytes are read through the physical store; images mirror to the Data Platform on that backend."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.data_platform import DataPlatformClient
from ka.data_platform.fake import FakeDataPlatform
from ka.data_platform.store import DataPlatformPhysicalStore
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S, approve_all
from ka.vocab import DecisionOutcome

POLICY = b"Merchant A refunds above $500 require manager approval.\n"
TOKEN = "dp-token-TEST"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture
def dp(tmp_path):
    fake = FakeDataPlatform(token=TOKEN)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://dp.test", KA_DP_RETRIES=3, KA_DP_BACKOFF_BASE=0.0):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False, start_workers=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        store = DataPlatformPhysicalStore(DataPlatformClient("http://dp.test", http=fake.as_http(), tenant_id="default"))
        ka.physical, ka.physical_note = store, None
        ka.ingestion.physical = store
        ka.outbox.physical = store
        ka.derived.physical = store
        yield ka, fake, store


@pytest.fixture
def local(tmp_path):
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    return ka


def _cfg():
    return config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_DP_RETRIES=3, KA_DP_BACKOFF_BASE=0.0)


def _candidates(ka):
    got = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    return got, ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops")


def _derived_assets(fake):
    return {aid: a for aid, a in fake.assets.items() if a["type"] == "nugget_version"}


def test_P1_a_candidate_becomes_one_derived_artefact_with_the_payload(dp):
    ka, fake, store = dp
    with _cfg():
        got, cands = _candidates(ka)
        ka.outbox.process_once()
    arts = ka.repo.derived_artefacts.all()
    assert len(arts) == len(cands) and all(a.status == "CANDIDATE" and a.state == "available" and a.backend == "data_platform" for a in arts)
    assets = _derived_assets(fake)
    assert len(assets) == len(cands)
    payload = json.loads(next(iter(next(iter(assets.values()))["versions"].values()))["bytes"])
    assert payload["canonical_id"] == cands[0].canonical_id and payload["version"] == 1 and payload["statement"] == cands[0].statement
    assert payload["scope"] == D.key() and payload["visibility"] == "ENTERPRISE" and payload["status"] == "CANDIDATE"


def test_P2_PT4_an_approved_nugget_resolves_to_source_asset_evidence_span_and_decision_ids(dp):
    ka, fake, store = dp
    with _cfg():
        got, cands = _candidates(ka)
        approve_all(ka, cands)
        ka.outbox.process_once()
    v = ka.repo.require_version(cands[0].ref)
    b = ka.repo.binding_for_version(got.version.id)
    active = [a for a in ka.repo.derived_artefacts.where(lambda a: a.ref == v.ref) if a.status == "ACTIVE"]
    assert len(active) == 1 and active[0].state == "available" and active[0].parent_asset_id == b.dp_asset_id
    asset = fake.assets[active[0].dp_asset_id]
    assert asset["parent"] == (b.dp_asset_id, b.dp_asset_version_id) and asset["provenance"]["producer"] == "ka" and asset["provenance"]["event"] == "knowledge.approved"
    payload = json.loads(asset["versions"][active[0].dp_asset_version_id]["bytes"])
    assert payload["sources"][0]["dp_asset_id"] == b.dp_asset_id and payload["sources"][0]["dp_asset_version_id"] == b.dp_asset_version_id
    ev = payload["evidence"][0]
    assert ev["span_id"] and ev["start"] is not None and ev["end"] is not None and ev["dp_asset_id"] == b.dp_asset_id
    assert payload["governance_decision_id"] == v.governance_decision_id and payload["governance_decision_id"]
    assert payload["graph_change_refs"] == list(v.graph_change_refs) and payload["approved_by"] == "reviewer"


def test_P3_a_revision_writes_artefacts_for_prior_and_new_versions_without_overwriting(dp):
    ka, fake, store = dp
    with _cfg():
        got, cands = _candidates(ka)
        approve_all(ka, cands)
        v1 = ka.repo.require_version(cands[0].ref)
        rev = ka.governance.propose_revision(v1.canonical_id, statement=v1.statement + " Revised.", by="ops", reason="test")
        ka.governance.decide(rev.ref, DecisionOutcome.APPROVE, by="reviewer", reason="ok")
        ka.outbox.process_once()
    keys = sorted(a.idempotency_key for a in ka.repo.derived_artefacts.where(lambda a: a.canonical_id == v1.canonical_id))
    tail = [k.split(":", 3)[-1] for k in keys]              # "<canonical>:<version>:<status>"
    assert f"{v1.canonical_id}:1:CANDIDATE" in tail and f"{v1.canonical_id}:1:ACTIVE" in tail and f"{v1.canonical_id}:1:SUPERSEDED" in tail
    assert f"{v1.canonical_id}:2:CANDIDATE" in tail and f"{v1.canonical_id}:2:ACTIVE" in tail
    assert len(keys) == len(set(keys)) and len(_derived_assets(fake)) == len(keys)


def test_P4_the_local_backend_writes_derived_json_synchronously(local):
    ka = local
    got, cands = _candidates(ka)
    approve_all(ka, cands)
    arts = ka.repo.derived_artefacts.where(lambda a: a.ref == cands[0].ref)
    assert {a.status for a in arts} == {"CANDIDATE", "ACTIVE"} and all(a.state == "available" and a.backend == "local" for a in arts)
    files = list((ka.repo.root / "derived" / "nugget_version").glob("*.json"))
    assert len(files) >= 2 and ka.nugget_detail(cands[0].ref)["derived"][0]["backend"] == "local"
    assert ka.repo.dp_outbox.where(lambda o: o.state == "pending") == []


def test_P5_content_route_serves_bytes_on_both_backends(local, dp):
    for ka in (local, dp[0]):
        c = TestClient(create_app(ka))
        with _cfg():
            got, _ = _candidates(ka)
            r = c.get(f"{PREFIX}/sources/{got.source.id}/versions/1/content")
        assert r.status_code == 200 and r.content == POLICY and r.headers["content-type"].startswith("text/")
        assert c.get(f"{PREFIX}/sources/{got.source.id}/versions/9/content").status_code == 404
        assert c.get(f"{PREFIX}/sources/SRC-nope/versions/1/content").status_code == 404
        set_ka(None)


def test_P6_images_mirror_to_the_data_platform_and_still_serve_locally(dp):
    ka, fake, store = dp
    c = TestClient(create_app(ka))
    with _cfg():
        r = c.post(f"{PREFIX}/images", json={"data": base64.b64encode(PNG).decode(), "name": "shot.png"}).json()["image"]
    assert r["dp_asset_id"] in fake.assets and fake.assets[r["dp_asset_id"]]["versions"][r["dp_asset_version_id"]]["sha"] == hashlib.sha256(PNG).hexdigest()
    assert c.get(f"{PREFIX}/images/{r['number']}").content == PNG
    assert c.get(f"{PREFIX}/images").json()["images"][0]["dp_asset_id"] == r["dp_asset_id"]
    set_ka(None)


def test_P7_derived_route_and_flow_exist(dp):
    ka, fake, store = dp
    c = TestClient(create_app(ka))
    with _cfg():
        got, cands = _candidates(ka)
        ka.outbox.process_once()
        d = c.get(f"{PREFIX}/nugget/{cands[0].ref}/derived").json()["derived"]
    assert d and d[0]["state"] == "available" and d[0]["dp_asset_id"]
    assert c.get(f"{PREFIX}/nugget/KN-999:v1/derived").status_code == 404
    set_ka(None)
    assert Path("e2e/plan22_derived_flow.py").exists()


def test_N1_dp_down_at_the_event_leaves_a_pending_artefact_the_worker_completes_once(dp):
    ka, fake, store = dp
    with _cfg():
        got, cands = _candidates(ka)
        ka.outbox.process_once()                                 # candidate artefacts delivered
        fake.fail_next(1)
        approve_all(ka, cands)
        a = [x for x in ka.repo.derived_artefacts.where(lambda x: x.ref == cands[0].ref) if x.status == "ACTIVE"][0]
        assert a.state == "pending" and ka.repo.dp_outbox.require(a.op_id).state == "pending"
        ka.outbox.process_once()                                 # fails once (retryable)
        assert ka.repo.derived_artefacts.require(a.id).state == "pending"
        ka.outbox.process_once()
    a = ka.repo.derived_artefacts.require(a.id)
    assert a.state == "available" and len([x for x in _derived_assets(fake).values() if json.loads(next(iter(x["versions"].values()))["bytes"])["status"] == "ACTIVE"]) == len(cands)


def test_N2_a_replayed_event_produces_one_artefact_one_op_one_asset(dp):
    ka, fake, store = dp
    with _cfg():
        got, cands = _candidates(ka)
        ka.outbox.process_once()
        v = ka.repo.require_version(cands[0].ref)
        n_before = len(ka.repo.derived_artefacts.all())
        key = f"ka:default:nugget:{v.canonical_id}:{v.version}:{v.status.value}"
        for _ in range(2):                                                  # the same event twice, plus a direct replay
            ka.bus.emit("knowledge.candidate.created", ref=v.ref, canonical_id=v.canonical_id, scope=D.key())
        ka.derived.publish(v.ref, event="knowledge.candidate.created")
        ka.outbox.process_once()
    same_key = ka.repo.derived_artefacts.where(lambda a: a.idempotency_key == key)
    ops = ka.repo.dp_outbox.where(lambda o: o.idempotency_key == key)
    assert len(same_key) == 1 and len(ops) == 1
    # a status change between the event and the replay is a NEW derived version by design (research-03 §6), never a duplicate of this key
    assert len(ka.repo.derived_artefacts.all()) <= n_before + 1 and len(_derived_assets(fake)) == len(ka.repo.derived_artefacts.all())


def test_N3_publication_never_writes_a_nugget_version_and_touches_no_governance(dp):
    ka, fake, store = dp
    with _cfg():
        got, cands = _candidates(ka)
        approve_all(ka, cands)
        v = ka.repo.require_version(cands[0].ref)
        before = (ka.repo.root / "nuggets" / f"{v.id}.json").read_bytes()
        ka.outbox.process_once()
        ka.derived.publish(v.ref, event="knowledge.approved")
    assert (ka.repo.root / "nuggets" / f"{v.id}.json").read_bytes() == before
    import inspect
    import ka.governance as g
    src = inspect.getsource(g)
    assert "ka.derived" not in src and "put_derived" not in src and "DerivedArtefact" not in src and "derived_artefacts" not in src


def test_N4_content_route_refuses_a_version_that_is_not_available(dp):
    ka, fake, store = dp
    c = TestClient(create_app(ka))
    fake.fail_next(1)
    with _cfg():
        got, _ = _candidates(ka)
        r = c.get(f"{PREFIX}/sources/{got.source.id}/versions/1/content")
    assert r.status_code == 409 and "not available" in r.json()["detail"] and "pending" in r.json()["detail"] and POLICY not in r.content
    set_ka(None)


def test_N5_the_payload_carries_no_token_and_no_filesystem_path(dp, local):
    for ka in (dp[0], local):
        with _cfg():
            got, cands = _candidates(ka)
            approve_all(ka, cands)
            ka.outbox.process_once()
        for o in ka.repo.dp_outbox.all():
            text = json.dumps(o.payload)
            assert TOKEN not in text and str(ka.repo.root) not in text and "/blobs/" not in text
