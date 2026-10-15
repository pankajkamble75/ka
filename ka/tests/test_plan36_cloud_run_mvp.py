"""plan-36 (NEXOS Cloud Run MVP) — the container is ready without an Enterprise OS checkout (bundled grammar, unauthenticated
/readyz that reveals only ready / not ready), and `seed-demo copper-kettle` puts SYNTHETIC Copper Kettle Coffee pricing policy through
KA's governed flow (upload → extraction → approval) idempotently, so Knowledge Worker's search request finds it with lineage."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from ka import config
from ka.__main__ import main
from ka.api import PREFIX, create_app
from ka.demo_copper_kettle import DOCUMENTS, INSTANCE, REVIEWER, seed_copper_kettle
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.vocab import NuggetStatus

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "deploy" / "grammar"
AX = "agentx-token-TEST"
QUESTION = "How does Copper Kettle Coffee set its menu prices?"
# Knowledge Worker's adapter body, verbatim shape (knowledge_worker/adapters/knowledge_acquisition.py: search()):
#   {"query": ..., "instance_id": ..., "domain_id": ..., "limit": 1..20}  →  POST {KW_KA_URL}/v1/knowledge/search
KW_BODY = {"query": QUESTION, "instance_id": "copper_kettle_coffee", "domain_id": "coffee-shop", "limit": 5}


def _ka(tmp_path, grammar: Path | str = BUNDLED) -> KnowledgeAcquisition:
    with config.scoped(KA_GRAMMAR_DIR=str(grammar), KA_GRAPH_MODE="memory"):
        return KnowledgeAcquisition(tmp_path / "store", provider=StubLLMProvider(), start_workers=False)


def _counts(ka) -> tuple[int, ...]:
    return (len(ka.repo.sources.all()), len(ka.repo.source_versions.all()), len(ka.repo.nuggets.all()), len(ka.repo.evidence.all()),
            len(ka.repo.decisions.all()))


def test_P1_the_seed_goes_through_governance_and_kw_search_returns_the_pricing_nuggets_with_lineage(tmp_path):
    ka = _ka(tmp_path)
    report = seed_copper_kettle(ka)
    assert report["sources_new"] == len(DOCUMENTS) == 7 and report["approved"] == report["candidates_extracted"] >= 12
    active = ka.repo.active_nuggets(INSTANCE)
    assert len(active) == report["candidates_extracted"] and all(n.status == NuggetStatus.ACTIVE for n in active)
    for n in active:                                                    # governed, not written: decision + source + evidence on every version
        d = ka.repo.decisions.get(n.governance_decision_id)
        assert d is not None and d.decided_by == REVIEWER and n.source_refs and n.evidence_refs
        assert "SYNTHETIC" in ka.repo.sources.get(n.source_refs[0]).title

    with config.scoped(KA_AGENTX_TOKEN=AX, KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN="console-token"):
        c = TestClient(create_app(ka))
        assert c.post(f"{PREFIX}/v1/knowledge/search", json=KW_BODY).status_code == 401          # no bearer, no answer
        r = c.post(f"{PREFIX}/v1/knowledge/search", json=KW_BODY, headers={"Authorization": f"Bearer {AX}"})
        assert r.status_code == 200, r.text
        body = r.json()
        nuggets = [h for h in body["results"] if h["kind"] == "nugget"]
        assert body["version"] and len(nuggets) == 5
        assert all(h["scope"] == "INSTANCE:copper_kettle_coffee" and h["status"] == "ACTIVE" and "price" in h["snippet"].lower() for h in nuggets)
        assert all(h["provenance"]["source_ids"] and h["provenance"]["decision_id"] for h in nuggets)
        # instance_id alone (domain_id null, as KW sends it when the caller gives none) finds the same knowledge
        alone = c.post(f"{PREFIX}/v1/knowledge/search", json={**KW_BODY, "domain_id": None}, headers={"Authorization": f"Bearer {AX}"}).json()
        assert [h["id"] for h in alone["results"]] == [h["id"] for h in body["results"]]
        # lineage: the read route walks a hit back to its synthetic source, evidence excerpt and the approval decision
        item = c.get(f"{PREFIX}/v1/knowledge/{nuggets[0]['id']}", headers={"Authorization": f"Bearer {AX}"}).json()["result"]
        prov = item["provenance"]
        assert prov["sources"] and all("SYNTHETIC" in s["title"] for s in prov["sources"])
        assert prov["evidence"] and prov["evidence"][0]["excerpt"] == item["item"]["statement"] and prov["evidence"][0]["source_version_id"]
        assert prov["lineage"]["ref"] == nuggets[0]["id"]
        assert any(d.get("decided_by") == REVIEWER for d in prov["decisions"])


def test_P2_seeding_twice_adds_nothing(tmp_path):
    ka = _ka(tmp_path)
    first = seed_copper_kettle(ka)
    before = _counts(ka)
    again = seed_copper_kettle(_ka(tmp_path))                            # a fresh process over the same store, as a re-run job would be
    assert _counts(_ka(tmp_path)) == before
    assert again["sources_new"] == 0 and again["sources_unchanged"] == 7 and again["candidates_extracted"] == again["approved"] == 0
    assert again["active_refs"] == first["active_refs"]


def test_P3_the_cli_seeds_the_store_it_is_given(tmp_path, capsys):
    with config.scoped(KA_GRAMMAR_DIR=str(BUNDLED), KA_GRAPH_MODE="memory"):
        assert main(["seed-demo", "copper-kettle", str(tmp_path / "cli")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"] == "INSTANCE:copper_kettle_coffee" and len(out["active_refs"]) >= 12 and out["storage"].endswith("cli")
    assert main(["seed-demo"]) == 2


def test_P4_readyz_is_unauthenticated_and_ready_with_the_bundled_grammar(tmp_path):
    ka = _ka(tmp_path)
    assert ka.grammar.loaded and ka.grammar.snapshot.grammar_version.startswith("grammar/")
    with config.scoped(KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN="console-token", KA_AGENTX_TOKEN=AX):
        for path in ("/readyz", "/ready"):
            r = TestClient(create_app(ka)).get(f"{PREFIX}{path}")
            assert r.status_code == 200 and r.json() == {"status": "ready"}         # nothing else: no version, path or checks
        h = TestClient(create_app(ka)).get(f"{PREFIX}/healthz", headers={"Authorization": f"Bearer {AX}"}).json()
        assert h["status"] == "ok" and h["checks"]["grammar"] == "ok"


def test_N1_readyz_is_not_ready_without_a_grammar(tmp_path):
    empty = tmp_path / "no-grammar"
    empty.mkdir()
    r = TestClient(create_app(_ka(tmp_path, grammar=empty))).get(f"{PREFIX}/readyz")
    assert r.status_code == 503 and r.json() == {"status": "not_ready"}


def test_N2_another_instance_does_not_see_copper_kettle_knowledge(tmp_path):
    ka = _ka(tmp_path)
    seed_copper_kettle(ka)
    with config.scoped(KA_AGENTX_TOKEN=AX):
        r = TestClient(create_app(ka)).post(f"{PREFIX}/v1/knowledge/search", json={**KW_BODY, "instance_id": "old_mill_bakehouse"},
                                            headers={"Authorization": f"Bearer {AX}"}).json()
    assert not [h for h in r["results"] if h["kind"] == "nugget"]


def test_P5_the_image_bundles_the_knowledge_worker_grammar_and_defaults_ka_grammar_dir_to_it():
    kw = json.loads((BUNDLED / "grammar.json").read_text()), json.loads((BUNDLED / "process_types.json").read_text())
    assert kw[0]["version"].startswith("grammar/") and kw[1]["version"].startswith("process-types/")
    docker = (ROOT / "Dockerfile").read_text()
    assert "KA_GRAMMAR_DIR=/opt/ka/grammar" in docker and "COPY deploy/grammar/grammar.json deploy/grammar/process_types.json /opt/ka/grammar/" in docker
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    assert "!deploy/grammar" in ignore and "deploy" not in ignore
    doc = (ROOT / "docs" / "deploy" / "cloud-run-mvp.md").read_text()
    for s in ("KA_STORAGE_ROOT", "KA_ACCESS_POLICY", "KA_ACCESS_TOKEN", "KA_AGENTX_TOKEN", "KA_GRAPH_MODE", "KA_GRAMMAR_DIR", "/readyz",
              "seed-demo copper-kettle"):
        assert s in doc, s
