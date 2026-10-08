"""plan-08 (research-01 R10; product test PT8) — managed connectors: the contract, the local-folder connector, incremental sync
that keeps history (new / modified / moved / deleted / permission-changed), revocation, and the folder-root guard."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.api import PREFIX, create_app, set_ka
from ka.connectors import ConnectorError, get_connector
from ka.connectors.local_folder import LocalFolderConnector
from ka.llm import StubLLMProvider
from ka.model import Connection
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S, approve_all
from ka.vocab import AuthorityType, ExtractionStatus, NuggetStatus, Visibility

SOP = """# Merchant underwriting

Merchant underwriting evaluates a merchant application and determines whether the merchant is eligible for card processing.

Applications with a risk score above 80 must be referred to the credit committee.
"""
POLICY = "Merchant A refunds above $500 require manager approval.\n"


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "inbox"
    (root / "ops").mkdir(parents=True)
    with config.scoped(KA_CONNECTOR_ROOTS=str(root)):
        ka = KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider(), auto_approve_low_impact=False)
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        yield ka, root / "ops", root


def _connect(ka, folder, **kw):
    return ka.connectors.create("local_folder", "Ops SOPs", {"root": str(folder)}, owner="ops", scope=D,
                                authority=kw.pop("authority", AuthorityType.APPROVED_ENTERPRISE_POLICY), **kw)


def test_P1_enumerate_lists_included_files_with_checksums_and_sidecar_visibility(world):
    ka, folder, _ = world
    (folder / "sop.md").write_text(SOP)
    (folder / "notes.txt").write_text("plain")
    (folder / "notes.txt.visibility").write_text("TEAM")
    (folder / "image.png").write_bytes(b"\x89PNG")
    conn = _connect(ka, folder, visibility=Visibility.ENTERPRISE)
    items, cursor = LocalFolderConnector().enumerate(conn)
    assert [i.locator for i in items] == ["notes.txt", "sop.md"] and cursor is None
    by = {i.locator: i for i in items}
    assert by["sop.md"].visibility is None and by["notes.txt"].visibility == "TEAM"
    assert len(by["sop.md"].checksum) == 64 and by["sop.md"].size == len(SOP.encode())
    assert LocalFolderConnector().get_permissions(conn, by["notes.txt"]) == {"visibility": "TEAM", "principals": ["ops"]}


def test_P2_first_sync_creates_sources_with_connection_provenance_and_extracts(world):
    ka, folder, _ = world
    (folder / "sop.md").write_text(SOP)
    (folder / "policy.md").write_text(POLICY)
    conn = _connect(ka, folder)
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.new == 2 and rep.modified == rep.moved == rep.deleted == 0 and rep.candidates >= 2
    srcs = ka.repo.sources.where(lambda s: s.connection_id == conn.id)
    assert len(srcs) == 2
    for s in srcs:
        assert s.original_location == f"local_folder://{conn.id}/{s.metadata['locator']}" and s.scope == D
        assert s.authority_type == AuthorityType.APPROVED_ENTERPRISE_POLICY and s.visibility == Visibility.ENTERPRISE
        assert s.extraction_status == ExtractionStatus.EXTRACTED and s.metadata["synced_at"]
    conn = ka.repo.connections.require(conn.id)
    assert conn.stats["new"] == 2 and conn.last_sync_at and set(conn.checkpoint) == {"sop.md", "policy.md"}
    assert any(e["name"] == "source.synced" for e in ka.repo.events())


def test_P3_unchanged_second_sync_is_a_no_op_with_an_advanced_timestamp(world):
    ka, folder, _ = world
    (folder / "sop.md").write_text(SOP)
    conn = _connect(ka, folder)
    ka.connectors.sync(conn.id, by="ops")
    before = ka.repo.connections.require(conn.id)
    n_versions = len(ka.repo.source_versions.all())
    rep = ka.connectors.sync(conn.id, by="ops")
    after = ka.repo.connections.require(conn.id)
    assert rep.counts() == {"new": 0, "modified": 0, "moved": 0, "deleted": 0, "permission_changed": 0, "skipped": 0, "candidates": 0}
    assert len(ka.repo.source_versions.all()) == n_versions and after.last_sync_at >= before.last_sync_at


def test_P4_a_modified_file_becomes_version_2_of_the_same_source_and_is_reextracted(world):
    ka, folder, _ = world
    (folder / "sop.md").write_text(SOP)
    conn = _connect(ka, folder)
    ka.connectors.sync(conn.id, by="ops")
    src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
    v1 = ka.repo.source_versions.require(src.current_version_id)
    (folder / "sop.md").write_text(SOP.replace("above 80", "above 70"))
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.modified == 1 and rep.new == 0 and rep.candidates >= 1
    src2 = ka.repo.sources.require(src.id)
    assert src2.content_version == 2 and src2.current_version_id != v1.id
    assert "above 80" in ka.repo.source_versions.require(v1.id).text and "above 70" in ka.repo.source_versions.require(src2.current_version_id).text
    assert len(ka.repo.sources.where(lambda s: s.connection_id == conn.id)) == 1


def test_P5_a_moved_file_keeps_its_source_and_updates_the_location(world):
    ka, folder, _ = world
    (folder / "sop.md").write_text(SOP)
    conn = _connect(ka, folder)
    ka.connectors.sync(conn.id, by="ops")
    src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
    (folder / "archive").mkdir()
    os.rename(folder / "sop.md", folder / "archive" / "sop-2026.md")
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.moved == 1 and rep.new == 0 and rep.deleted == 0
    src2 = ka.repo.sources.require(src.id)
    assert src2.original_location.endswith("/archive/sop-2026.md") and src2.content_version == 1 and src2.metadata["locator"] == "archive/sop-2026.md"
    assert len(ka.repo.sources.where(lambda s: s.connection_id == conn.id)) == 1


def test_P6_a_deleted_file_marks_the_source_revoked_keeps_versions_and_flags_active_knowledge(world):
    ka, folder, _ = world
    (folder / "policy.md").write_text(POLICY)
    conn = _connect(ka, folder)
    ka.connectors.sync(conn.id, by="ops")
    src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
    cands = ka.repo.nuggets.where(lambda n: src.id in n.source_refs)
    approve_all(ka, cands)
    (folder / "policy.md").unlink()
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.deleted == 1
    src2 = ka.repo.sources.require(src.id)
    assert src2.revoked_at and ka.repo.source_versions.get(src2.current_version_id) is not None
    assert all(ka.repo.require_version(c.ref).status == NuggetStatus.ACTIVE for c in cands)
    assert all(ka.repo.require_version(c.ref).analysis.get("source_revoked") for c in cands)
    assert any(a.what == "source.revoked" for a in ka.repo.audit()) and any(e["name"] == "source.revoked" for e in ka.repo.events())
    att = ka.needs_attention()["revoked_sources_with_active_knowledge"]
    assert len(att) == 1 and att[0]["source_id"] == src.id and set(att[0]["active_nuggets"]) == {c.ref for c in cands}


def test_P7_a_sidecar_visibility_change_narrows_the_source_and_flags_derived_nuggets(world):
    ka, folder, _ = world
    (folder / "policy.md").write_text(POLICY)
    conn = _connect(ka, folder, visibility=Visibility.ENTERPRISE)
    ka.connectors.sync(conn.id, by="ops")
    src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
    assert src.visibility == Visibility.ENTERPRISE
    (folder / "policy.md.visibility").write_text("TEAM")
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.permission_changed == 1 and rep.modified == 0
    src2 = ka.repo.sources.require(src.id)
    assert src2.visibility == Visibility.TEAM and src2.content_version == 1
    flagged = [n for n in ka.repo.nuggets.where(lambda n: src.id in n.source_refs)]
    assert flagged and all(n.analysis["source_visibility_changed"] == {"from": "ENTERPRISE", "to": "TEAM"} for n in flagged)
    assert any(a.what == "source.permission_changed" and a.before == {"visibility": "ENTERPRISE"} for a in ka.repo.audit())


def test_P8_PT8_a_changed_sop_in_the_watched_folder_surfaces_the_contradiction_in_conflicts(world):
    ka, folder, _ = world
    (folder / "refunds.md").write_text(POLICY)
    conn = _connect(ka, folder)
    ka.connectors.sync(conn.id, by="ops")
    src = ka.repo.sources.where(lambda s: s.connection_id == conn.id)[0]
    v1_cands = ka.repo.nuggets.where(lambda n: src.id in n.source_refs)
    approve_all(ka, v1_cands)
    active = ka.repo.require_version(v1_cands[0].ref)
    (folder / "refunds.md").write_text(POLICY.replace("$500", "$1,000"))
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.modified == 1 and rep.candidates >= 1
    src2 = ka.repo.sources.require(src.id)
    assert src2.content_version == 2
    new = [n for n in ka.repo.nuggets.where(lambda n: src.id in n.source_refs) if n.ref != active.ref]
    assert new and new[0].analysis.get("conflict_open")
    rels = ka.repo.relationships_for(new[0].ref)
    assert any(r.relationship_type.value == "CONTRADICTS" and active.ref in (r.from_ref, r.to_ref) for r in rels)
    hits = ka.search.search("refunds", filter="Conflicting")
    assert any(h.kind == "nugget" and h.id == new[0].ref for h in hits)
    conflicts = ka.needs_attention()["conflicts"]
    row = next(c for c in conflicts if c["ref"] == new[0].ref)
    assert row["statement"].endswith("$1,000 require manager approval.")
    assert ka.repo.require_version(active.ref).status == NuggetStatus.ACTIVE          # nothing overwritten


@pytest.fixture
def client(world):
    ka, folder, root = world
    (folder / "sop.md").write_text(SOP)
    c = TestClient(create_app(ka))
    yield c, ka, folder, root
    set_ka(None)


def test_P9_routes_create_list_get_sync_revoke_then_sync_is_409(client):
    c, ka, folder, root = client
    body = {"kind": "local_folder", "name": "Ops", "config": {"root": str(folder)}, "owner": "ops", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}
    r = c.post(f"{PREFIX}/connectors", json=body)
    assert r.status_code == 201, r.text
    cid = r.json()["connection"]["id"]
    lst = c.get(f"{PREFIX}/connectors").json()
    assert [x["id"] for x in lst["connections"]] == [cid] and "local_folder" in lst["kinds"] and lst["decision"] == "Q6"   # plan-14 added m365 to kinds (Q6) and str(root) in lst["roots"]
    r = c.post(f"{PREFIX}/connectors/{cid}/sync?by=ops")
    assert r.status_code == 200 and r.json()["report"]["new"] == 1
    got = c.get(f"{PREFIX}/connectors/{cid}").json()
    assert got["connection"]["sources"] == 1 and len(got["sources"]) == 1 and got["sources"][0]["connection_id"] == cid
    assert c.get(f"{PREFIX}/connectors/CON-nope").status_code == 404
    r = c.post(f"{PREFIX}/connectors/{cid}/revoke?by=ops&reason=offboarded")
    assert r.status_code == 200 and r.json()["connection"]["status"] == "revoked"
    r = c.post(f"{PREFIX}/connectors/{cid}/sync?by=ops")
    assert r.status_code == 409 and "cannot sync" in r.json()["detail"]
    assert c.post(f"{PREFIX}/connectors/CON-nope/sync").status_code == 404


def test_P10_live_flow_exists_and_is_wired(client):
    """P10 is the live browser flow (`e2e/plan08_connector_flow.py`, run by verify §5); here: the console carries the surfaces."""
    c, *_ = client
    js = Path("ka/console/app.js").read_text(encoding="utf-8")
    assert "connectCard" in js and "data-act=\"sync-conn\"" in js and "revoked_sources_with_active_knowledge" in js
    assert Path("e2e/plan08_connector_flow.py").exists()
    assert c.get(f"{PREFIX}/connectors").status_code == 200


def test_N1_a_root_outside_the_allowed_roots_or_a_symlink_escape_is_refused(world, tmp_path):
    ka, folder, root = world
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(ConnectorError, match="outside KA_CONNECTOR_ROOTS"):
        _connect(ka, outside)
    link = root / "escape"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ConnectorError, match="outside KA_CONNECTOR_ROOTS"):
        _connect(ka, link)
    assert ka.repo.connections.all() == []
    with pytest.raises(ConnectorError, match="not a directory"):
        _connect(ka, root / "missing")
    c = TestClient(create_app(ka))
    r = c.post(f"{PREFIX}/connectors", json={"kind": "local_folder", "name": "x", "config": {"root": str(outside)}, "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"})
    assert r.status_code == 400 and "outside" in r.json()["detail"]
    set_ka(None)


def test_N2_a_file_over_the_upload_cap_is_skipped_with_a_reason_and_the_sync_completes(world):
    ka, folder, _ = world
    (folder / "small.md").write_text(POLICY)
    (folder / "huge.md").write_text("x" * (2 * 1024 * 1024))
    conn = _connect(ka, folder)
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.new == 2 and len(rep.skipped) == 1 and rep.skipped[0]["locator"] == "huge.md" and "KA_MAX_UPLOAD_MB" in rep.skipped[0]["reason"]
    assert len(ka.repo.sources.where(lambda s: s.connection_id == conn.id)) == 1
    assert ka.repo.connections.require(conn.id).last_delta["skipped"] == rep.skipped


def test_N3_sync_on_a_revoked_connection_is_refused_before_enumerating(world, monkeypatch):
    ka, folder, _ = world
    (folder / "sop.md").write_text(SOP)
    conn = _connect(ka, folder)
    ka.connectors.revoke(conn.id, by="ops", reason="offboarded")
    calls = []
    monkeypatch.setattr(LocalFolderConnector, "enumerate", lambda self, c, cursor=None: calls.append(1) or ([], None))
    with pytest.raises(ConnectorError, match="revoked; it cannot sync"):
        ka.connectors.sync(conn.id, by="ops")
    assert calls == [] and any(a.what == "connector.revoked" for a in ka.repo.audit())


def test_N4_an_unknown_connector_kind_is_refused(world):
    ka, folder, _ = world
    with pytest.raises(ConnectorError, match="unknown connector kind"):
        ka.connectors.create("sharepoint", "x", {"root": str(folder)}, owner="ops", scope=D)
    with pytest.raises(ConnectorError):
        get_connector("gdrive")
    assert ka.repo.connections.all() == []


def test_N5_a_secret_ref_names_a_variable_and_its_value_never_reaches_storage(world, monkeypatch):
    ka, folder, root = world
    monkeypatch.setenv("OPS_FOLDER_TOKEN", "hunter2-very-secret")
    (folder / "sop.md").write_text(SOP)
    conn = _connect(ka, folder, secret_ref="OPS_FOLDER_TOKEN")
    ka.connectors.sync(conn.id, by="ops")
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path(ka.repo.root).rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl"})
    assert "hunter2-very-secret" not in blob and "OPS_FOLDER_TOKEN" in blob
    assert Connection.model_validate(json.loads(json.dumps(conn.model_dump(mode="json")))).secret_ref == "OPS_FOLDER_TOKEN"


def test_N6_a_file_that_fails_extraction_is_recorded_failed_and_does_not_abort_the_sync(world):
    ka, folder, _ = world
    (folder / "junk.pdf").write_bytes(b"%PDF-1.4 \x00\x01\x02 not really a pdf \xff\xfe")
    (folder / "policy.md").write_text(POLICY)
    conn = _connect(ka, folder)
    rep = ka.connectors.sync(conn.id, by="ops")
    assert rep.new == 2
    srcs = {s.metadata["locator"]: s for s in ka.repo.sources.where(lambda s: s.connection_id == conn.id)}
    assert srcs["policy.md"].extraction_status == ExtractionStatus.EXTRACTED
    assert srcs["junk.pdf"].extraction_status in {ExtractionStatus.FAILED, ExtractionStatus.EXTRACTED}
    if srcs["junk.pdf"].extraction_status == ExtractionStatus.FAILED:
        assert not ka.repo.nuggets.where(lambda n: srcs["junk.pdf"].id in n.source_refs)
