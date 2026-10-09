"""plan-20 (research-03 R4; product test PT6) — the pending-operations outbox: a retryable Data Platform failure spools the bytes and
queues the upload; the worker retries with backoff, dead-letters, and reconciles by idempotency key so the commit lands once."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.data_platform import DataPlatformClient, DataPlatformError
from ka.data_platform.fake import FakeDataPlatform
from ka.data_platform.store import DataPlatformPhysicalStore
from ka.llm import StubLLMProvider
from ka.outbox import Outbox, OutboxWorker
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S

POLICY = b"Merchant A refunds above $500 require manager approval.\n"
TOKEN = "dp-token-TEST"


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
        ka.outbox = Outbox(ka.repo, ka.bus, ka.auditor, store)
        ka.ingestion.outbox = ka.outbox
        ka.outbox_worker = OutboxWorker(ka.outbox)
        yield ka, fake, store


def _cfg(**extra):
    return config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_DP_RETRIES=3, KA_DP_BACKOFF_BASE=0.0, **extra)


def test_P1_enqueue_then_process_flips_pending_to_available_and_clears_the_spool(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        b = ka.repo.binding_for_version(g.version.id)
        assert b.status == "pending" and "queued for retry" in b.reason and Path(ka.repo.root / "spool" / f"{g.version.id}.bin").exists()
        ops = ka.repo.dp_outbox.all()
        assert len(ops) == 1 and ops[0].kind == "upload_source" and ops[0].idempotency_key == f"ka:default:{g.source.id}:1"
        assert not ka.repo.version_available(g.version.id)
        out = ka.outbox.process_once()
    assert out["done"] == 1
    b = ka.repo.binding_for_version(g.version.id)
    assert b.status == "available" and b.dp_asset_id in fake.assets and not (ka.repo.root / "spool" / f"{g.version.id}.bin").exists()
    assert ka.repo.dp_outbox.all()[0].state == "done" and any(e["name"] == "physical.binding.available" for e in ka.repo.events())


def test_P2_backoff_increments_attempts_and_pushes_next_at(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    op = ka.repo.dp_outbox.all()[0]
    fake.fail_next(1)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_DP_RETRIES=5, KA_DP_BACKOFF_BASE=60.0):
        out = ka.outbox.process_once()
    assert out["retried"] == 1
    op = ka.repo.dp_outbox.require(op.id)
    assert op.attempts == 1 and op.state == "pending" and datetime.fromisoformat(op.next_at) > datetime.now(timezone.utc) + timedelta(seconds=50)
    assert ka.outbox.due() == []                                             # not due yet
    assert ka.outbox.due(now=(datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat())


def test_P3_PT6_dp_down_at_ingest_then_the_worker_commits_exactly_once(dp):
    ka, fake, store = dp
    fake.fail_next(2)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        assert not ka.repo.version_available(g.version.id)
        r1 = ka.outbox.process_once()                 # first retry hits the second failure
        r2 = ka.outbox.process_once()                 # second retry succeeds
    assert r1["retried"] == 1 and r2["done"] == 1
    assert ka.repo.version_available(g.version.id)
    assert len(fake.assets) == 1 and sum(len(a["versions"]) for a in fake.assets.values()) == 1
    assert len(ka.repo.sources.all()) == 1 and len(ka.repo.source_versions.all()) == 1 and len(ka.repo.physical_bindings.all()) == 1


def test_P4_a_crash_between_content_and_commit_replays_to_the_same_asset(dp, monkeypatch):
    ka, fake, store = dp
    real_commit = store.client.commit
    calls = {"n": 0}
    def commit_once_fails(uid, *, sha256):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DataPlatformError(503, "unavailable", "network blip", retryable=True)
        return real_commit(uid, sha256=sha256)
    monkeypatch.setattr(store.client, "commit", commit_once_fails)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        assert ka.repo.binding_for_version(g.version.id).status == "pending"
        ka.outbox.process_once()
    b = ka.repo.binding_for_version(g.version.id)
    assert b.status == "available" and len(fake.assets) == 1 and sum(len(a["versions"]) for a in fake.assets.values()) == 1


def test_P5_reconcile_requeues_a_pending_binding_with_a_spool_and_fails_one_without(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    for o in ka.repo.dp_outbox.all():                                          # simulate: the op was lost
        (ka.repo.root / "dp_outbox" / f"{o.id}.json").unlink()
    ka.repo.dp_outbox._cache = None
    rec = ka.outbox.reconcile()
    assert rec == {"requeued": 1, "failed": 0} and len(ka.repo.dp_outbox.all()) == 1
    fake.fail_next(1)
    with _cfg():
        g2 = ka.ingestion.upload(filename="other.md", data=b"Other policy text.\n", owner="ops", scope=D)
    (ka.repo.root / "spool" / f"{g2.version.id}.bin").unlink()
    for o in ka.repo.dp_outbox.where(lambda o: o.payload.get("source_version_id") == g2.version.id):
        (ka.repo.root / "dp_outbox" / f"{o.id}.json").unlink()
    ka.repo.dp_outbox._cache = None
    rec = ka.outbox.reconcile()
    assert rec["failed"] == 1 and ka.repo.binding_for_version(g2.version.id).status == "failed"


def test_P6_routes_status_run_and_retry(dp):
    ka, fake, store = dp
    c = TestClient(create_app(ka))
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        st = c.get(f"{PREFIX}/physical/outbox").json()
        assert st["by_state"] == {"pending": 1} and st["ops"][0]["kind"] == "upload_source"
        r = c.post(f"{PREFIX}/physical/outbox/run?by=ops").json()
        assert r["processed"]["done"] == 1 and r["status"]["by_state"] == {"done": 1}
        assert c.get(f"{PREFIX}/dashboard").json()["physical"]["outbox"]["by_state"] == {"done": 1}
        assert c.post(f"{PREFIX}/physical/outbox/OP-nope/retry").status_code == 404
        op = ka.repo.dp_outbox.all()[0]
        assert c.post(f"{PREFIX}/physical/outbox/{op.id}/retry").status_code == 409        # done, not dead
    set_ka(None)


def test_P7_the_worker_thread_runs_and_stops(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_DP_OUTBOX_INTERVAL=0.05, KA_DP_RETRIES=3, KA_DP_BACKOFF_BASE=0.0):
        w = OutboxWorker(ka.outbox)
        w.start()
        import time
        for _ in range(100):
            if ka.repo.binding_for_version(g.version.id).status == "available":
                break
            time.sleep(0.05)
        w.stop()
    assert ka.repo.binding_for_version(g.version.id).status == "available" and w.runs >= 1
    assert Path("e2e/plan20_outbox_flow.py").exists()


def test_N1_a_non_retryable_error_dead_letters_at_once_and_fails_the_binding(dp, monkeypatch):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    real = store.client.commit
    monkeypatch.setattr(store.client, "commit", lambda uid, *, sha256: real(uid, sha256="0" * 64))
    with _cfg():
        out = ka.outbox.process_once()
    assert out["dead"] == 1
    op = ka.repo.dp_outbox.all()[0]; b = ka.repo.binding_for_version(g.version.id)
    assert op.state == "dead" and op.last_code == "checksum_mismatch" and op.attempts == 0
    assert b.status == "failed" and "checksum_mismatch" in b.reason and not (ka.repo.root / "spool" / f"{g.version.id}.bin").exists()


def test_N2_after_the_retry_budget_the_op_is_dead_and_retry_resets_it(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        fake.fail_next(3)
        for _ in range(3):
            ka.outbox.process_once()
    op = ka.repo.dp_outbox.all()[0]; b = ka.repo.binding_for_version(g.version.id)
    assert op.state == "dead" and op.attempts == 3 and b.status == "pending" and "dead-lettered" in b.reason
    assert any(e["name"] == "physical.outbox.dead" for e in ka.repo.events())
    with _cfg():
        ka.outbox.retry(op.id, by="ops")
        assert ka.outbox.process_once()["done"] == 1
    assert ka.repo.binding_for_version(g.version.id).status == "available" and len(fake.assets) == 1


def test_N3_the_local_backend_starts_no_worker_and_never_enqueues(tmp_path):
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
    assert ka.outbox_worker.thread is None and ka.physical.name == "local"
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
    assert ka.repo.dp_outbox.all() == []


def test_N4_no_bytes_in_the_spool_after_success_and_no_token_in_any_op(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        ka.outbox.process_once()
    assert not list((ka.repo.root / "spool").glob("*"))
    assert TOKEN not in "".join(p.read_text() for p in (ka.repo.root / "dp_outbox").glob("*.json"))


def test_N5_a_double_enqueue_collapses_to_one_op_and_one_asset(dp):
    ka, fake, store = dp
    fake.fail_next(1)
    with _cfg():
        g = ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D)
        op = ka.repo.dp_outbox.all()[0]
        again = ka.outbox.enqueue("upload_source", op.idempotency_key, dict(op.payload))
        assert again.id == op.id and len(ka.repo.dp_outbox.all()) == 1
        ka.outbox.process_once()
    assert len(fake.assets) == 1 and ka.repo.dp_outbox.all()[0].state == "done"
