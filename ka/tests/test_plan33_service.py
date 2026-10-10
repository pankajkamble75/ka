"""plan-33 (research-05 R1, R6, R11, R12; product test PT7) — the v1 event view over KA's one event log (ids, schema, provenance, replay),
the OpenAPI document kept current, the service documentation, and the two-process run."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka import config
from ka.agentx.events import V1_NAMES, v1_events
from ka.api import PREFIX, create_app, set_ka
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import A, B, C, D, P, S, approve_all, ingest_policy

ROOT = Path(__file__).resolve().parents[2]
AX = "agentx-token-TEST"


@pytest.fixture
def ka(tmp_path):
    k = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False, start_workers=False)
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D), (C, D)]:
        k.register_scope(s, p)
    yield k
    set_ka(None)


def _client(ka):
    with config.scoped(KA_AGENTX_TOKEN=AX):
        c = TestClient(create_app(ka))
    c.headers.update({"Authorization": f"Bearer {AX}"})
    return c


def test_P1_PT7_review_required_carries_id_schema_seq_and_provenance(ka):
    ka.bus.emit("knowledge.acquisition.completed", source_id="SRC-1", operation_id="AXO-1")
    ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    out = v1_events(ka, after=0, limit=100)
    types = [e["type"] for e in out["events"]]
    assert "knowledge.acquisition.completed" in types and "knowledge.review.required" in types
    e = next(e for e in out["events"] if e["type"] == "knowledge.review.required")
    assert e["event_id"] and e["event_id"] == next(r["event_id"] for r in ka.repo.events() if r["seq"] == e["seq"])
    assert e["schema_version"] == "ka.v1" and isinstance(e["seq"], int) and e["provenance"]["source_event"] == "knowledge.candidate.created"
    assert e["provenance"]["service_id"] == config.get("KA_SERVICE_ID") and e["occurred_at"]


def test_P2_PT7_after_resumes_exactly_and_replays_the_same_ids(ka):
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    ingest_policy(ka, D, "Chargebacks must be answered within 10 days.", title="Chargebacks")
    first = v1_events(ka, after=0, limit=1)
    rest = v1_events(ka, after=first["next_after"], limit=100)
    whole = v1_events(ka, after=0, limit=100)
    assert [e["event_id"] for e in first["events"] + rest["events"]] == [e["event_id"] for e in whole["events"]]
    assert [e["event_id"] for e in v1_events(ka, after=0, limit=100)["events"]] == [e["event_id"] for e in whole["events"]]
    assert vs


def test_P3_publication_approved_and_completed_including_wiki(ka):
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, vs)
    p = ka.repo.proposals.where(lambda p: vs[0].ref in p.knowledge_change_ids)[0]
    ka.graph_change.approve(p.id, by="alice", reason="ok")
    ka.graph_change.apply(p.id, by="alice")
    ka.bus.emit("wiki.published", page_id="WP-1", proposal_id="WPR-1")
    out = v1_events(ka, after=0, limit=1000)
    by = {}
    for e in out["events"]:
        by.setdefault(e["type"], []).append(e["provenance"]["source_event"])
    assert "graph.change.approved" in by["knowledge.publication.approved"]
    assert {"graph.change.applied", "wiki.published"} <= set(by["knowledge.publication.completed"])


def test_P4_the_openapi_document_is_current_and_lists_every_v1_route():
    sys.path.insert(0, str(ROOT / "tools"))
    import export_openapi
    on_disk = (ROOT / "docs" / "integration" / "openapi-v1.json").read_text()
    assert on_disk == export_openapi.render(), "docs/integration/openapi-v1.json is stale: run tools/export_openapi.py"
    paths = set(json.loads(on_disk)["paths"])
    for p in ("/v1/capabilities", "/v1/capabilities/{capability_id}/invoke", "/v1/operations/{operation_id}", "/v1/operations/{operation_id}/input",
              "/v1/tasks", "/v1/events", "/healthz"):
        assert f"{PREFIX}{p}" in paths


def test_P5_the_docs_name_every_v1_route_and_every_service_setting():
    guide = (ROOT / "docs" / "integration" / "README.md").read_text()
    arch = (ROOT / "docs" / "architecture" / "knowledge-acquisition.md").read_text()
    inv = (ROOT / "docs" / "integration" / "source-inventory.md").read_text()
    assert "## 13. KA as a service" in arch and "pankajkamble75/ka" in inv and "Ownership and dependencies" in inv
    for s in ("KA_SERVICE_ID", "KA_AGENTX_TOKEN", "KA_AGENTX_URL", "KA_GRAPH_MODE", "KA_KW_URL", "KA_KW_TOKEN", "KA_KW_PUBLISH_WAIT_S", "KA_GRAMMAR_URL",
              "KA_DP_API", "KA_DP_AUTH_MODE", "KA_DP_PRINCIPAL"):
        assert s in guide, s
    for route in ("/v1/capabilities", "/invoke", "/v1/operations/{id}", "/input", "/v1/tasks", "/v1/events"):
        assert route in guide, route
    assert "docs/integration/README.md" in (ROOT / "README.md").read_text()


def test_P6_the_two_process_flow_covers_the_journey():
    src = (ROOT / "e2e" / "plan33_two_process_flow.py").read_text()
    for needle in ('"KA_ENTERPRISE_OS_ROOT": ""', "KA_AGENTX_URL", "KA_KW_URL", "knowledge.acquire", "knowledge.review", "submitted_by",
                   "knowledge.publish", "/v1/events"):
        assert needle in src, needle


def test_N1_events_need_the_agentx_token(ka):
    with config.scoped(KA_AGENTX_TOKEN=AX):
        c = TestClient(create_app(ka))
        r = c.get(f"{PREFIX}/v1/events")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_N2_unmapped_events_stay_in_events_only(ka):
    ka.bus.emit("physical.binding.available", binding_id="PB-1")
    assert not any(e["provenance"]["source_event"] == "physical.binding.available" for e in v1_events(ka)["events"])
    assert any(e["name"] == "physical.binding.available" for e in ka.repo.events())
    assert "physical.binding.available" not in V1_NAMES


@pytest.mark.parametrize("q", ["limit=0", "limit=1001", "after=-1"])
def test_N3_bounds(ka, q):
    c = _client(ka)
    with config.scoped(KA_AGENTX_TOKEN=AX):
        r = c.get(f"{PREFIX}/v1/events?{q}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "schema_invalid"


def test_N4_subjects_are_ids_not_content(ka):
    vs = ingest_policy(ka, D, "Refunds above $500 require manager approval. " * 20)
    approve_all(ka, vs)
    for e in v1_events(ka, after=0, limit=1000)["events"]:
        for v in e["subject"].values():
            assert not isinstance(v, str) or len(v) <= 200
        assert not re.search(r"Refunds above", json.dumps(e["subject"]))
