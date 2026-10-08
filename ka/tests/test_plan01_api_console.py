"""plan-01 — the Knowledge Console API (§27–§35) and the Enterprise Console seams (§23 corrections, §47 Why?)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.tests.conftest import A, D, approve_all, ingest_policy


@pytest.fixture
def client(ka):
    app = create_app(ka)
    yield TestClient(app)
    set_ka(None)


def test_P1_health_vocab_scopes(client):
    assert client.get(f"{PREFIX}/healthz").json()["ok"] is True
    assert "STRUCTURE" in client.get(f"{PREFIX}/vocab").json()["scope_types"]
    scopes = client.get(f"{PREFIX}/scopes").json()["scopes"]
    assert [s["key"] for s in scopes][:3] == ["STRUCTURE:universal", "PARENT_DOMAIN:payment-processing", "DOMAIN:merchant-acquiring"]


def test_P2_paste_extract_decide_and_inspect(client):
    r = client.post(f"{PREFIX}/sources/paste", json={"text": "Refunds above $500 require manager approval.", "owner": "u", "scope_type": "DOMAIN",
                                                      "scope_id": "merchant-acquiring", "authority": "Approved Enterprise Policy"})
    assert r.status_code == 200 and r.json()["candidates"][0]["status"] == "PENDING_REVIEW"
    ref = r.json()["candidates"][0]["ref"]
    assert client.get(f"{PREFIX}/needs-attention").json()["pending_governance"][0]["ref"] == ref
    d = client.post(f"{PREFIX}/nugget/{ref}/decide", json={"outcome": "APPROVE", "by": "reviewer", "reason": "ok"})
    assert d.status_code == 200 and d.json()["nugget"]["status"] == "ACTIVE"
    detail = client.get(f"{PREFIX}/nugget/{ref}").json()
    assert detail["version_history"][0]["status"] == "ACTIVE" and detail["graph_usage"] and detail["lineage"]["sources"]
    dash = client.get(f"{PREFIX}/scopes/DOMAIN/merchant-acquiring/dashboard").json()
    assert dash["active_nuggets"] == 1 and dash["affected_graph_elements"] == 1 and len(dash["instances_using"]) == 3


def test_P3_upload_endpoint_accepts_a_file(client):
    r = client.post(f"{PREFIX}/sources/upload", data={"owner": "u", "scope_type": "INSTANCE", "scope_id": "merchant-a"},
                    files={"file": ("policy.md", b"# 4.2\nMerchant A refunds above $1,000 require manager approval.", "text/markdown")})
    assert r.status_code == 200 and r.json()["source"]["source_type"] == "markdown" and r.json()["candidates"]


def test_P4_conflict_view_and_resolution_actions(client, ka):
    approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))
    cand = ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.")[0]
    view = client.get(f"{PREFIX}/conflicts/{cand.ref}").json()
    assert view["conflicts"][0]["existing"]["statement"].endswith("$500 require manager approval.")
    assert "Keep Existing".upper().replace(" ", "_") in view["actions"] and view["conflicts"][0]["authority_comparison"]
    r = client.post(f"{PREFIX}/nugget/{cand.ref}/decide", json={"outcome": "ACCEPT_NEW", "by": "reviewer", "reason": "2027"})
    assert r.json()["nugget"]["status"] == "ACTIVE"


def test_P5_enterprise_console_seams_correct_this_and_why(client, ka):
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    el = ka.adapter.list_elements(D)[0]
    why = client.get(f"{PREFIX}/lineage/explain", params={"graph_id": el.graph_id, "element_id": el.element_id}).json()
    assert why["explained"] and why["knowledge_lineage"][0]["ref"] == "KN-001:v1"
    r = client.post(f"{PREFIX}/corrections", json={"graph_id": el.graph_id, "element_id": el.element_id, "what_is_incorrect": "threshold",
                                                   "correct_value": "Refunds above $750 require manager approval.", "reason": "update", "by": "ops"})
    assert r.status_code == 200 and r.json()["correction"]["status"] == "GOVERNED" and r.json()["correction"]["suggested_scope"]["scope_type"] == "DOMAIN"
    gap = client.post(f"{PREFIX}/runtime/graph-gap", json={"scope_type": "INSTANCE", "scope_id": "merchant-a", "question": "q", "gap_description": "g"}).json()
    assert gap["signal"] == "GRAPH GAP DETECTED"


def test_P6_graph_change_queue_approve_apply_and_search(ka_manual):
    ka = ka_manual
    client = TestClient(create_app(ka))
    try:
        approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
        q = client.get(f"{PREFIX}/graph-changes", params={"status": "READY"}).json()["proposals"]
        assert len(q) == 1
        pid = q[0]["id"]
        assert client.post(f"{PREFIX}/graph-changes/{pid}/apply", json={"by": "g"}).status_code == 409   # not approved yet
        assert client.post(f"{PREFIX}/graph-changes/{pid}/approve", json={"by": "g"}).json()["proposal"]["status"] == "APPROVED"
        assert client.post(f"{PREFIX}/graph-changes/{pid}/apply", json={"by": "g"}).json()["execution"]["status"] == "APPLIED"
        hits = client.get(f"{PREFIX}/search", params={"q": "manager approval", "filter": "Current"}).json()["hits"]
        assert hits and hits[0]["kind"] == "nugget"
        assert client.get("/console/").status_code == 200 and client.get("/console/../pyproject.toml").status_code in {404, 400}
    finally:
        set_ka(None)


def test_P7_research_mission_endpoint(client):
    r = client.post(f"{PREFIX}/research/missions", json={"scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "objective": "Visa dispute rules", "by": "u"})
    assert r.status_code == 200 and r.json()["mission"]["status"] in {"COMPLETED", "FAILED"} and r.json()["run"]["agent_id"] == "coordinator"
    assert client.get(f"{PREFIX}/research/missions", params={"scope_type": "DOMAIN", "scope_id": "merchant-acquiring"}).json()["missions"]


def test_N1_bad_scope_type_and_unknown_nugget_are_clean_errors(client):
    assert client.get(f"{PREFIX}/scopes/GALAXY/x/dashboard").status_code == 400
    assert client.get(f"{PREFIX}/nugget/KN-999:v1").status_code == 404
    assert client.post(f"{PREFIX}/nugget/KN-999:v1/decide", json={"outcome": "APPROVE", "by": "x"}).status_code == 409


def test_P8_apply_to_scope_rescopes_then_approves_in_one_call(client, ka):
    cand = ingest_policy(ka, A, "KYC is required before activation.")[0]
    r = client.post(f"{PREFIX}/nugget/{cand.ref}/apply", json={"by": "reviewer", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"})
    assert r.status_code == 200 and r.json()["applied"] is True
    out = r.json()["nugget"]
    assert out["scope"] == "DOMAIN:merchant-acquiring" and out["status"] == "ACTIVE" and len(r.json()["steps"]) == 2
    assert ka.repo.require_version(cand.ref).status.value == "REJECTED"      # the instance-scoped candidate was re-scoped, not lost
    assert client.get(f"{PREFIX}/dashboard").json()["nuggets"]["by_status"]["ACTIVE"] == 1
