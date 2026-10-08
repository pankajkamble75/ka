"""plan-14 (research-02 R6; product test PT6 fixture-driven) — the Microsoft 365 / SharePoint connector behind the plan-08 contract,
verified against a recorded Graph fixture. The live PT6 skips until the author supplies the app registration (Q13)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.connectors import CONNECTOR_KINDS, ConnectorError
from ka.connectors.m365 import M365Connector, visibility_from_permissions
from ka.llm import StubLLMProvider
from ka.model import Connection
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S, approve_all
from ka.vocab import AuthorityType, ExtractionStatus, Visibility

FIX = json.loads((Path(__file__).resolve().parent / "fixtures" / "m365_graph_fixture.json").read_text(encoding="utf-8"))
SECRET = "s3cr3t-CLIENT-SECRET-value"
CFG = {"tenant_id": "TENANT1", "client_id": "CLIENT1", "drive_id": "DRIVE1"}


class FakeGraph:
    """Serves the recorded fixture; `state` advances the delta link and the item versions."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.v2 = False               # refunds.md changed
        self.sweep = False            # permissions narrowed
        self.fail_with: int | None = None

    def __call__(self, method, url, headers, data):
        self.calls.append((method, url))
        if self.fail_with and "graph.microsoft.com" in url:
            return self.fail_with, {}, b"{}"
        if "/oauth2/v2.0/token" in url:
            assert SECRET.encode() in (data or b"")
            return 200, {}, json.dumps(FIX["token"]).encode()
        assert headers.get("Authorization") == f"Bearer {FIX['token']['access_token']}"
        if url.endswith("/root/delta"):
            return 200, {}, json.dumps(FIX["delta_full"]).encode()
        if "skiptoken=PAGE2" in url:
            return 200, {}, json.dumps(FIX["delta_page2"]).encode()
        if "token=T1" in url:
            return 200, {}, json.dumps(FIX["delta_T1"]).encode()
        if "token=T2" in url or "token=T3" in url:
            return 200, {}, json.dumps(FIX["delta_T2"]).encode()
        if url.endswith("/content"):
            iid = url.split("/items/")[1].split("/")[0]
            key = f"{iid}@v2" if (self.v2 and f"{iid}@v2" in FIX["content"]) else iid
            return 200, {}, FIX["content"][key].encode()
        if url.endswith("/permissions"):
            iid = url.split("/items/")[1].split("/")[0]
            key = f"{iid}@sweep" if (self.sweep and f"{iid}@sweep" in FIX["permissions"]) else iid
            return 200, {}, json.dumps(FIX["permissions"].get(key, {"value": []})).encode()
        return 404, {}, b"{}"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("M365_SECRET", SECRET)
    ka = KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider(), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    graph = FakeGraph()
    import ka.connectors as C
    real = C.get_connector
    conn_obj = M365Connector(http=graph)
    monkeypatch.setattr(C, "get_connector", lambda kind: conn_obj if kind == "m365" else real(kind))
    import ka.connectors.sync as S_
    monkeypatch.setattr(S_, "get_connector", lambda kind: conn_obj if kind == "m365" else real(kind))
    return ka, graph, conn_obj


def _connect(ka, **kw):
    return ka.connectors.create("m365", "Finance SharePoint", CFG, owner="ops", scope=D, authority=AuthorityType.APPROVED_ENTERPRISE_POLICY,
                                visibility=kw.pop("visibility", Visibility.ENTERPRISE), secret_ref="M365_SECRET")


def test_P1_authorize_reads_the_secret_from_the_named_variable_and_caches_the_token(world):
    ka, graph, connector = world
    conn = _connect(ka)
    tokens = [u for m, u in graph.calls if "/oauth2/v2.0/token" in u]
    assert len(tokens) == 1 and "TENANT1" in tokens[0]
    connector.authorize(conn)
    assert len([u for m, u in graph.calls if "/oauth2/v2.0/token" in u]) == 1           # cached


def test_P2_enumerate_maps_the_delta_pages(world):
    ka, graph, connector = world
    conn = _connect(ka)
    items, link = connector.enumerate(conn)
    by = {i.locator: i for i in items}
    assert set(by) == {"ITEM0001", "ITEM0002", "ITEM0003", "ITEM0004", "ITEM0005"} and "FOLDER01" not in by
    assert by["ITEM0001"].name == "Policies/refunds.md" and by["ITEM0001"].checksum == "QX-A1" and by["ITEM0001"].size == 61
    assert by["ITEM0003"].name == "settlement.md" and link.endswith("token=T1")
    items2, link2 = connector.enumerate(conn, cursor=link)
    assert {i.locator: i.deleted for i in items2} == {"ITEM0001": False, "ITEM0002": True, "ITEM0003": False} and link2.endswith("token=T2")


def test_P3_first_sync_maps_permissions_to_visibility_under_the_ceiling(world):
    ka, graph, connector = world
    conn = _connect(ka, visibility=Visibility.ENTERPRISE)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.new == 5 and len(rep.skipped) == 1 and rep.skipped[0]["locator"] == "ITEM0004"
    srcs = {s.metadata["locator"]: s for s in ka.repo.sources.where(lambda s: s.connection_id == conn.id)}
    assert srcs["ITEM0001"].visibility == Visibility.ENTERPRISE          # organization link
    assert srcs["ITEM0002"].visibility == Visibility.TEAM                # group
    assert srcs["ITEM0003"].visibility == Visibility.PERSONAL            # single user
    assert srcs["ITEM0005"].visibility == Visibility.ENTERPRISE          # "Everyone except external users"
    assert srcs["ITEM0001"].original_filename == "Policies/refunds.md" and srcs["ITEM0001"].extraction_status == ExtractionStatus.EXTRACTED
    conn2 = ka.connectors.create("m365", "Team-only", CFG, owner="ops", scope=D, visibility=Visibility.TEAM, secret_ref="M365_SECRET")
    ka.connectors.sync(conn2.id, by="ops")
    s2 = {s.metadata["locator"]: s for s in ka.repo.sources.where(lambda s: s.connection_id == conn2.id)}
    assert s2["ITEM0001"].visibility == Visibility.TEAM                  # ceiling applied


def test_P4_second_sync_uses_the_delta_link_modified_deleted_moved(world):
    ka, graph, connector = world
    conn = _connect(ka)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        ka.connectors.sync(conn.id, by="ops")
    cp = ka.repo.connections.require(conn.id).checkpoint
    assert cp["delta_link"].endswith("token=T1") and cp["syncs"] == 1
    srcs = {s.metadata["locator"]: s for s in ka.repo.sources.where(lambda s: s.connection_id == conn.id)}
    approve_all(ka, ka.repo.nuggets.where(lambda n: srcs["ITEM0002"].id in n.source_refs))
    graph.v2 = True
    n_calls = len(graph.calls)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        rep = ka.connectors.sync(conn.id, by="ops")
    assert any("token=T1" in u for m, u in graph.calls[n_calls:]) and not any(u.endswith("/root/delta") for m, u in graph.calls[n_calls:])
    assert rep.modified == 1 and rep.deleted == 1 and rep.moved == 1 and rep.new == 0
    s1 = ka.repo.sources.require(srcs["ITEM0001"].id)
    assert s1.content_version == 2 and "$1,000" in ka.repo.source_versions.require(s1.current_version_id).text
    s2 = ka.repo.sources.require(srcs["ITEM0002"].id)
    assert s2.revoked_at and rep.reviews                                  # plan-10 re-review follows revocation
    s3 = ka.repo.sources.require(srcs["ITEM0003"].id)
    assert s3.original_filename == "Archive/settlement.md" and s3.content_version == 1
    assert ka.repo.connections.require(conn.id).checkpoint["syncs"] == 2


def test_P5_the_permission_sweep_runs_every_nth_sync(world):
    ka, graph, connector = world
    conn = _connect(ka)
    with config.scoped(KA_MAX_UPLOAD_MB=1, KA_M365_PERMISSION_SWEEP_EVERY=2):
        ka.connectors.sync(conn.id, by="ops")
        graph.sweep = True                                                # ITEM0001 narrowed from an org link to the Finance group
        rep = ka.connectors.sync(conn.id, by="ops")                       # sync 2 → sweep
    assert rep.permission_changed >= 1
    s1 = [s for s in ka.repo.sources.where(lambda s: s.connection_id == conn.id) if s.metadata["locator"] == "ITEM0001"][0]
    assert s1.visibility == Visibility.TEAM


def test_P6_PT6_fixture_driven_library_sync(world):
    ka, graph, connector = world
    conn = _connect(ka)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        ka.connectors.sync(conn.id, by="ops")
    srcs = {s.metadata["locator"]: s for s in ka.repo.sources.where(lambda s: s.connection_id == conn.id)}
    assert {k: v.visibility.value for k, v in srcs.items() if k in ("ITEM0001", "ITEM0002", "ITEM0003")} == {"ITEM0001": "ENTERPRISE", "ITEM0002": "TEAM", "ITEM0003": "PERSONAL"}
    graph.v2 = True
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        ka.connectors.sync(conn.id, by="ops")
    s1 = ka.repo.sources.require(srcs["ITEM0001"].id)
    assert s1.content_version == 2 and len(ka.repo.source_versions.where(lambda v: v.source_id == s1.id)) == 2


@pytest.mark.skipif(not (os.environ.get("M365_TENANT_ID") and os.environ.get("M365_CLIENT_ID") and os.environ.get("M365_DRIVE_ID") and os.environ.get("M365_CLIENT_SECRET")),
                    reason="PT6 live needs the M365 app registration (Q13 — the author's); NOT RUN")
def test_P7_PT6_live_with_the_real_registration(tmp_path):
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        ka.register_scope(s_, p_)
    conn = ka.connectors.create("m365", "live", {"tenant_id": os.environ["M365_TENANT_ID"], "client_id": os.environ["M365_CLIENT_ID"], "drive_id": os.environ["M365_DRIVE_ID"]},
                                owner="ops", scope=D, secret_ref="M365_CLIENT_SECRET")
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.new >= 0


def test_N1_secret_and_token_never_reach_storage(world):
    ka, graph, connector = world
    conn = _connect(ka)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        ka.connectors.sync(conn.id, by="ops")
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path(ka.repo.root).rglob("*") if p.is_file())
    assert SECRET not in blob and FIX["token"]["access_token"] not in blob and "M365_SECRET" in blob
    assert Connection.model_validate(ka.repo.connections.require(conn.id).model_dump()).secret_ref == "M365_SECRET"


def test_N2_missing_secret_variable_or_config_is_refused_before_anything_is_stored(world, monkeypatch):
    ka, graph, connector = world
    monkeypatch.delenv("M365_SECRET", raising=False)
    with pytest.raises(ConnectorError, match="unset"):
        _connect(ka)
    monkeypatch.setenv("M365_SECRET", SECRET)
    with pytest.raises(ConnectorError, match="needs config"):
        ka.connectors.create("m365", "x", {"tenant_id": "t"}, owner="ops", scope=D, secret_ref="M365_SECRET")
    with pytest.raises(ConnectorError, match="secret_ref"):
        ka.connectors.create("m365", "x", CFG, owner="ops", scope=D)
    assert ka.repo.connections.all() == [] and "m365" in CONNECTOR_KINDS
    c = TestClient(create_app(ka))
    r = c.post(f"{PREFIX}/connectors", json={"kind": "m365", "name": "x", "config": CFG, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "secret_ref": "NOPE_VAR"})
    assert r.status_code == 400 and "unset" in r.json()["detail"]
    set_ka(None)


def test_N3_a_graph_refusal_during_sync_raises_and_leaves_the_checkpoint(world):
    ka, graph, connector = world
    conn = _connect(ka)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        ka.connectors.sync(conn.id, by="ops")
    cp = dict(ka.repo.connections.require(conn.id).checkpoint)
    graph.fail_with = 403
    with pytest.raises(ConnectorError, match="refused"):
        ka.connectors.sync(conn.id, by="ops")
    c2 = ka.repo.connections.require(conn.id)
    assert c2.status == "active" and c2.checkpoint == cp


def test_N4_an_oversized_item_is_skipped_without_a_content_request(world):
    ka, graph, connector = world
    conn = _connect(ka)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        rep = ka.connectors.sync(conn.id, by="ops")
    assert any(x["locator"] == "ITEM0004" and "KA_MAX_UPLOAD_MB" in x["reason"] for x in rep.skipped)
    assert not any("/items/ITEM0004/content" in u for m, u in graph.calls)


def test_N5_revoke_drops_the_token_and_a_later_sync_makes_no_graph_call(world):
    ka, graph, connector = world
    conn = _connect(ka)
    ka.connectors.revoke(conn.id, by="ops", reason="offboarded")
    assert conn.id not in connector._tokens
    n = len(graph.calls)
    with pytest.raises(ConnectorError, match="cannot sync"):
        ka.connectors.sync(conn.id, by="ops")
    assert len(graph.calls) == n
    assert visibility_from_permissions([], Visibility.TEAM) == Visibility.TEAM
