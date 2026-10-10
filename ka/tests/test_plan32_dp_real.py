"""plan-32 (research-05 R9; product test PT9) — KA on the REAL Data Platform /v1: staging with the real body, PUT to content_url, commit at
commit_url with the Idempotency-Key, a knowledge binding, real reads, nugget derived assets with a parent; both auth modes; DP's error
envelope; visibility narrowed (never widened) without a tag; no inbound polling on the real API. The plans 18–23 tests (ka-subset wire)
stay unmodified."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from ka import config
from ka.data_platform import DataPlatformError
from ka.data_platform.fake_v1 import FakeDataPlatformV1
from ka.data_platform.v1 import DataPlatformV1Client, DataPlatformV1Store
from ka.llm import StubLLMProvider
from ka.physical import select_physical_store
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S, approve_all

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "dp-token"
POLICY = b"# Refunds\n\nRefunds above $500 require manager approval.\n"


def _env(**kw):
    return config.scoped(**{"KA_DP_SERVICE_TOKEN": TOKEN, "KA_STORAGE_BACKEND": "data_platform", "KA_DP_BASE_URL": "http://dp.test", "KA_DP_API": "v1",
                            "KA_DP_RETRIES": 3, "KA_DP_BACKOFF_BASE": 0.0, **kw})


@pytest.fixture
def dp(tmp_path):
    fake = FakeDataPlatformV1(token=TOKEN)
    with _env():
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False, start_workers=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        assert isinstance(ka.physical, DataPlatformV1Store)
        ka.physical.client.http = fake.http
        for part in (ka.ingestion, ka.outbox, ka.derived):
            part.physical = ka.physical
        yield ka, fake, ka.physical


def _upload(ka, visibility=None):
    from ka.vocab import Visibility
    return ka.ingestion.upload(filename="policy.md", data=POLICY, owner="ops", scope=D, **({"visibility": visibility} if visibility else {"visibility": Visibility.ENTERPRISE}))


def test_P1_upload_stages_puts_commits_with_the_key_and_binds(dp):
    ka, fake, _ = dp
    with _env():
        got = _upload(ka)
    b = ka.repo.binding_for_version(got.version.id)
    assert b.status == "available" and b.dp_asset_id.startswith("asset_") and b.dp_asset_version_id.startswith("av_")
    assert b.locator == f"/v1/assets/{b.dp_asset_id}/versions/1/content"
    calls = [(m, p) for m, p, _ in fake.requests]
    up = next(iter(fake.uploads.values()))
    assert {k: up[k] for k in ("type", "scope", "format", "provenance")} == {"type": "document", "scope": "ENTERPRISE", "format": "md", "provenance": "supplied"}
    assert up["size_bytes"] == len(POLICY) and up["sha256"] == hashlib.sha256(POLICY).hexdigest()
    assert [c[0] for c in calls[:4]] == ["POST", "PUT", "POST", "POST"] and calls[1][1].endswith("/content") and calls[3][1] == "/v1/knowledge-bindings"
    commit_headers = fake.requests[2][2]
    assert commit_headers["idempotency-key"] == f"ka:default:{got.source.id}:{got.source.content_version}"
    assert (got.source.id, got.source.content_version) in fake.bindings


def test_P2_bytes_read_back_through_the_real_read_path(dp):
    ka, fake, _ = dp
    with _env():
        got = _upload(ka)
        data, _ct = ka.version_bytes(got.source.id, got.source.content_version)
        again = ka.ingestion.reextract(got.source.id, owner="ops")
    assert data == POLICY and again.version is not None
    assert any(m == "GET" and p.endswith("/versions/1/content") for m, p, _ in fake.requests)


def test_P3_PT9_a_nugget_version_lands_as_a_nugget_derived_asset_with_its_source_as_parent(dp):
    ka, fake, _ = dp
    with _env():
        got = _upload(ka)
        cands = ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops")
        approve_all(ka, cands)
        for _ in range(4):
            ka.outbox.process_once()
    b = ka.repo.binding_for_version(got.version.id)
    nuggets = [c for c in fake.derived_calls if c["type"] == "nugget"]
    assert nuggets and all(c["parent_asset_version_ids"] == [b.dp_asset_version_id] and c["mime_type"] == "application/json" for c in nuggets)
    arts = ka.repo.derived_artefacts.all()
    assert arts and all(a.state == "available" and a.dp_asset_id.startswith("asset_") for a in arts)
    assert json.loads(fake.assets[arts[-1].dp_asset_id]["versions"][0]["bytes"])["canonical_id"] == cands[0].canonical_id


def test_P4_the_same_version_committed_twice_returns_the_same_ids(dp):
    ka, fake, store = dp
    with _env():
        sha = hashlib.sha256(POLICY).hexdigest()
        a = store.put(POLICY, content_type="text/markdown", sha256=sha, idempotency_key="ka:default:SRC-1:1:V1", owner="o", visibility="ENTERPRISE", tenant_id="default")
        b = store.put(POLICY, content_type="text/markdown", sha256=sha, idempotency_key="ka:default:SRC-1:1:V1", owner="o", visibility="ENTERPRISE", tenant_id="default")
    assert (a.asset_id, a.asset_version_id) == (b.asset_id, b.asset_version_id) and len(fake.bindings) == 1


def test_P5_auth_bearer_or_principal_headers():
    seen = []
    c = DataPlatformV1Client("http://dp.test", http=lambda m, u, h, b: (seen.append(h), (200, {}, b"{}"))[1], tenant_id="t1")
    with config.scoped(KA_DP_SERVICE_TOKEN=TOKEN, KA_DP_AUTH_MODE="auto"):
        c.version("a", 1)
    with config.scoped(KA_DP_SERVICE_TOKEN="", KA_DP_AUTH_MODE="auto", KA_DP_PRINCIPAL="ka-svc"):
        c.version("a", 1)
    assert seen[0]["Authorization"] == f"Bearer {TOKEN}" and "X-Principal-Id" not in seen[0]
    assert seen[1]["X-Principal-Id"] == "ka-svc" and seen[1]["X-Tenant-Id"] == "t1" and "storage:write" in seen[1]["X-Scopes"] and "Authorization" not in seen[1]


def test_P6_the_live_flow_against_the_real_service_exists():
    assert (ROOT / "e2e" / "plan32_dp_real_flow.py").exists()


def test_N1_checksum_mismatch_is_invalid_contract_and_the_version_fails(dp):
    ka, fake, store = dp
    with _env(), pytest.raises(DataPlatformError) as e:
        store.put(POLICY, content_type="text/plain", sha256="0" * 64, idempotency_key="ka:default:S:1:V", owner="o", visibility="ENTERPRISE", tenant_id="default")
    assert e.value.status == 422 and e.value.code == "invalid_contract" and not e.value.retryable
    fake.fail_next.append((422, "invalid_contract"))
    with _env():
        got = _upload(ka)
    b = ka.repo.binding_for_version(got.version.id)
    assert b.status == "failed" and "invalid_contract" in b.reason and not ka.repo.dp_outbox.all()


def test_N2_expired_is_a_non_retryable_conflict_and_503_is_retryable_pending(dp):
    ka, fake, store = dp
    c = store.client
    with _env():
        st = c.stage(sha256=hashlib.sha256(POLICY).hexdigest(), size_bytes=len(POLICY), mime_type="text/plain", asset_type="document", scope="ENTERPRISE", tags={}, fmt="text")
        c.put_bytes(st["content_url"], POLICY)
        fake.expire(st["upload_id"])
        with pytest.raises(DataPlatformError) as e:
            c.commit_at(st["commit_url"], sha256=hashlib.sha256(POLICY).hexdigest(), idempotency_key="k-exp")
        assert e.value.status == 409 and e.value.code == "conflict" and not e.value.retryable
        fake.fail_next.append((503, "unavailable"))
        got = _upload(ka)
    b = ka.repo.binding_for_version(got.version.id)
    assert b.status == "pending" and ka.repo.dp_outbox.all()


def test_N3_domain_visibility_without_a_tag_is_narrowed_never_widened(dp):
    ka, fake, store = dp
    with _env():
        store.put(POLICY, content_type="text/plain", sha256=hashlib.sha256(POLICY).hexdigest(), idempotency_key="ka:default:S9:1:V", owner="o",
                  visibility="DOMAIN", tenant_id="default")
        store.put(POLICY + b"x", content_type="text/plain", sha256=hashlib.sha256(POLICY + b"x").hexdigest(), idempotency_key="ka:default:S9:2:V",
                  owner="o", visibility="DOMAIN", tenant_id="default", tags={"domain_id": "merchant-acquiring"})
    scopes = [u["scope"] for u in fake.uploads.values()]
    assert scopes == ["PERSONAL", "DOMAIN"] and any("narrowed to PERSONAL" in n for n in store.notes)


def test_N4_no_inbound_polling_on_the_real_api(tmp_path):
    with _env():
        ka = KnowledgeAcquisition(tmp_path / "a", provider=StubLLMProvider(), start_workers=False)
    assert isinstance(ka.physical, DataPlatformV1Store) and not ka.outbox_worker.ticks
    with _env(KA_DP_API="ka-subset"):
        old = KnowledgeAcquisition(tmp_path / "b", provider=StubLLMProvider(), start_workers=False)
    assert type(old.physical).__name__ == "DataPlatformPhysicalStore" and len(old.outbox_worker.ticks) == 1
    with _env():
        st, note = select_physical_store(tmp_path)
    assert isinstance(st, DataPlatformV1Store) and note is None


def test_N5_the_plans_18_to_23_tests_are_unmodified():
    files = ["ka/tests/test_plan18_physical_store.py", "ka/tests/test_plan19_data_platform.py", "ka/tests/test_plan20_outbox.py",
             "ka/tests/test_plan21_inbound_events.py", "ka/tests/test_plan22_derived.py", "ka/tests/test_plan23_backfill.py"]
    assert subprocess.run(["git", "diff", "--quiet", "7427778", "--", *files], cwd=ROOT).returncode == 0
