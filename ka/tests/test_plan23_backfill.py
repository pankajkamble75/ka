"""plan-23 (research-03 R12, R13, R14; product test PT9) — asset families named once; the backfill binds every legacy version with SHA-256
verification, fails byte-less ones with a reason, publishes ACTIVE nuggets, is idempotent, is refused on the local backend (the rollback)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ka import config
from ka.data_platform import DataPlatformClient
from ka.data_platform.fake import FakeDataPlatform
from ka.data_platform.store import DataPlatformPhysicalStore
from ka.llm import StubLLMProvider
from ka.physical import ASSET_FAMILIES, PhysicalRef
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S, approve_all
from ka.vocab import NuggetStatus

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.backfill_physical import backfill  # noqa: E402

TOKEN = "dp-token-TEST"
TEXTS = [b"Merchant A refunds above $500 require manager approval.\n", b"Chargebacks must be answered within 30 days.\n", b"Settlement runs nightly at 02:00.\n"]


def _legacy_storage(tmp_path):
    """Three versions ingested on the LOCAL backend (plan-18 bindings, local); one made byte-less like a blocked link."""
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    gots = [ka.ingestion.upload(filename=f"p{i}.md", data=t, owner="ops", scope=D) for i, t in enumerate(TEXTS)]
    cands = ka.governance.extract_from_source(gots[0].source, gots[0].version, gots[0].extraction, actor="ops")
    approve_all(ka, cands)
    v = ka.repo.source_versions.require(gots[2].version.id)
    Path(v.stored_path).unlink(); v.stored_path = None; v.extraction_note = "blocked: 403 at origin"
    ka.repo.source_versions.put(v)
    for b in ka.repo.physical_bindings.all():                       # pre-plan-18 storage had no bindings at all
        (tmp_path / "s" / "physical_bindings" / f"{b.id}.json").unlink()
    ka.repo.physical_bindings._cache = None
    return tmp_path / "s", gots


def _dp_ka(root, fake):
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_STORAGE_BACKEND="data_platform", KA_DP_BASE_URL="http://dp.test", KA_DP_RETRIES=3, KA_DP_BACKOFF_BASE=0.0):
        ka = KnowledgeAcquisition(root, provider=StubLLMProvider(), auto_propose_graph_changes=False, start_workers=False)
    store = DataPlatformPhysicalStore(DataPlatformClient("http://dp.test", http=fake.as_http(), tenant_id="default"))
    ka.physical, ka.physical_note, ka.ingestion.physical, ka.outbox.physical, ka.derived.physical = store, None, store, store, store
    return ka


@pytest.fixture
def legacy(tmp_path):
    root, gots = _legacy_storage(tmp_path)
    fake = FakeDataPlatform(token=TOKEN)
    return root, gots, fake, _dp_ka(root, fake)


def test_P1_dry_run_writes_nothing(legacy):
    root, gots, fake, ka = legacy
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        rep = backfill(ka, apply=False)
    assert rep["would_bind"] == 3 and rep["versions"] == 3 and rep["available"] == 0 and not fake.assets and ka.repo.physical_bindings.all() == []


def test_P2_apply_binds_two_available_with_sha_verified_and_one_failed(legacy):
    root, gots, fake, ka = legacy
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        rep = backfill(ka, apply=True)
    assert rep["available"] == 2 and rep["failed"] == 1 and rep["sha_mismatch"] == 0
    for g in gots[:2]:
        b = ka.repo.binding_for_version(g.version.id)
        assert b.status == "available" and b.backend == "data_platform" and b.sha256 == g.version.checksum and ka.repo.version_available(g.version.id)
        assert fake.assets[b.dp_asset_id]["versions"][b.dp_asset_version_id]["sha"] == g.version.checksum
    b3 = ka.repo.binding_for_version(gots[2].version.id)
    assert b3.status == "failed" and "blocked: 403" in b3.reason and not ka.repo.version_available(gots[2].version.id)


def test_P3_publish_active_gives_every_active_nugget_a_derived_artefact(legacy):
    root, gots, fake, ka = legacy
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        rep = backfill(ka, apply=True, publish_active=True)
    active = ka.repo.nuggets.where(lambda n: n.status == NuggetStatus.ACTIVE)
    assert active and rep["published"] == len(active)
    for v in active:
        arts = [a for a in ka.repo.derived_artefacts.where(lambda a: a.ref == v.ref) if a.status == "ACTIVE" and a.backend == "data_platform"]
        assert len(arts) == 1 and arts[0].state == "available" and fake.assets[arts[0].dp_asset_id]["type"] == "nugget_version"
        assert any(a.backend == "local" for a in ka.repo.derived_artefacts.where(lambda a: a.ref == v.ref))   # the local copy stays (rollback)


def test_P4_a_second_run_is_idempotent(legacy):
    root, gots, fake, ka = legacy
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        backfill(ka, apply=True, publish_active=True)
        n_assets = sum(len(a["versions"]) for a in fake.assets.values())
        rep = backfill(ka, apply=True, publish_active=True)
    assert rep["would_bind"] == 1 and rep["available"] == 0 and rep["failed"] == 1        # only the byte-less one is re-attempted
    assert sum(len(a["versions"]) for a in fake.assets.values()) == n_assets and rep["published"] == len(ka.repo.nuggets.where(lambda n: n.status == NuggetStatus.ACTIVE))


def test_P5_asset_families_are_named_once_and_sent(legacy):
    root, gots, fake, ka = legacy
    assert ASSET_FAMILIES == {"source": "source_document", "text": "extracted_text", "nugget": "nugget_version"}
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        backfill(ka, apply=True, publish_active=True)
    types = {a["type"] for a in fake.assets.values()}
    assert types == {"source_document", "nugget_version"}


def test_P6_rehearsal_flow_exists_and_dry_run_cli_works(tmp_path):
    root, gots = _legacy_storage(tmp_path)
    out = subprocess.run([sys.executable, "tools/backfill_physical.py", "--storage", str(root)], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
    assert out.returncode == 0 and json.loads(out.stdout)["would_bind"] == 3 and json.loads(out.stdout)["backend"] == "local"
    assert Path("e2e/plan23_backfill_rehearsal.py").exists()


def test_N1_a_sha_mismatch_is_failed_never_available(legacy, monkeypatch):
    root, gots, fake, ka = legacy
    real = ka.physical.put
    def bad_put(data, **kw):
        ref = real(data, **kw)
        return PhysicalRef(backend=ref.backend, asset_id=ref.asset_id, asset_version_id=ref.asset_version_id, sha256="0" * 64, state=ref.state, locator=ref.locator)
    monkeypatch.setattr(ka.physical, "put", bad_put)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        rep = backfill(ka, apply=True)
    assert rep["sha_mismatch"] == 2 and rep["available"] == 0
    for g in gots[:2]:
        b = ka.repo.binding_for_version(g.version.id)
        assert b.status == "failed" and "sha mismatch" in b.reason and not ka.repo.version_available(g.version.id)


def test_N2_an_available_binding_is_skipped_not_reuploaded(legacy):
    root, gots, fake, ka = legacy
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        backfill(ka, apply=True)
        calls = {"n": 0}
        real = ka.physical.put
        ka.physical.put = lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), real(*a, **k))[1]
        rep = backfill(ka, apply=True)
    assert rep["skipped"] == 2 and calls["n"] == 0


def test_N3_apply_is_refused_on_the_local_backend(tmp_path):
    root, gots = _legacy_storage(tmp_path)
    out = subprocess.run([sys.executable, "tools/backfill_physical.py", "--storage", str(root), "--apply"], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
    assert out.returncode == 2 and "refusing --apply" in out.stderr and "local" in out.stderr


def test_N4_PT9_rollback_the_local_backend_serves_legacy_versions_and_runs_no_worker(tmp_path):
    root, gots = _legacy_storage(tmp_path)
    ka = KnowledgeAcquisition(root, provider=StubLLMProvider())
    assert ka.physical.name == "local" and ka.outbox_worker.thread is None and ka.outbox_worker.ticks == []
    got = ka.ingestion.reextract(gots[0].source.id, owner="ops")           # through stored_path, no binding needed
    assert got.version.version == 2 and got.version.checksum == gots[0].version.checksum
    with pytest.raises(ValueError, match="no stored bytes"):
        ka.ingestion.reextract(gots[2].source.id, owner="ops")


def test_N5_a_duplicate_version_number_is_reported_as_a_conflict_not_bound_not_raised(legacy):
    """Rehearsal finding 2026-10-09: the live storage holds two SourceVersions numbered v5 for one source with different bytes."""
    root, gots, fake, ka = legacy
    dup = ka.repo.source_versions.require(gots[1].version.id).model_copy(update={"id": "SRV-dup00001", "checksum": "f" * 64})
    ka.repo.source_versions.put(dup)                                   # same (source, version), other bytes
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN):
        rep = backfill(ka, apply=True)
    assert rep["conflicts"] == 1 and rep["conflict_versions"][0]["source_version_id"] == "SRV-dup00001"
    assert rep["available"] + rep["failed"] + rep["skipped"] + rep["conflicts"] == rep["versions"] == 4
    assert ka.repo.binding_for_version("SRV-dup00001") is None and ka.repo.binding_for_version(gots[1].version.id).status == "available"


def test_P7_the_payload_carries_a_grammar_binding_when_one_exists(legacy):
    """Rehearsal finding 2026-10-09: the live storage has grammar bindings; the payload builder had never met one (tests load no grammar)."""
    from ka.derived import build_payload
    from ka.model import GrammarBinding
    from ka.vocab import BindingStatus, NuggetStatus
    root, gots, fake, ka = legacy
    v = ka.repo.nuggets.where(lambda n: n.status == NuggetStatus.ACTIVE)[0]
    ka.repo.bindings.put(GrammarBinding(nugget_ref=v.ref, grammar_version="g1", digest="abc/def", process_type="refund", edge="requires", binding_status=BindingStatus.BOUND, method="evidenced"))
    pl = build_payload(ka.repo, v)
    assert pl["binding"] == {"status": "bound", "digest": "abc/def", "grammar_version": "g1", "process_type": "refund", "edge": "requires", "method": "evidenced"}
