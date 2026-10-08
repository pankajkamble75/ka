"""plan-01 Phase 5 — Research Agents (§3.2, §16, §17, §18, §42)."""
from __future__ import annotations

import json

from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import A, B, D, P, S, approve_all, ingest_policy
from ka.vocab import AcquisitionChannel, AuthorityType, MissionStatus, NuggetStatus, RunStatus, Visibility


def _ka_with_llm(tmp_path, responses):
    inst = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(responses=responses, default_response="[]"), auto_approve_low_impact=True)
    for s, p in [(S, None), (P, S), (D, P), (A, D), (B, D)]:
        inst.register_scope(s, p)
    return inst


def test_P1_a_mission_runs_agents_and_yields_candidate_nuggets_with_lineage(tmp_path):
    findings = json.dumps([{"title": "Dispute response window", "statement": "Visa dispute responses are due within 30 days.",
                            "knowledge_type": "rule", "excerpt": "Visa Core Rules §11", "confidence": 0.7, "tags": ["visa"]}])
    ka = _ka_with_llm(tmp_path, {"Standards / Regulatory Agent": findings, "Domain Research Agent": findings})
    m = ka.research.create_mission(scope=D, objective="Research Visa dispute rules", by="pankaj", questions=["What is the response window?"])
    run = ka.research.run_mission(m.mission_id)
    m = ka.repo.missions.require(m.mission_id)
    assert run.status == RunStatus.COMPLETED and m.status == MissionStatus.COMPLETED
    assert len(m.candidate_refs) == 1       # two agents found the same thing → synthesis de-duplicated
    v = ka.repo.require_version(m.candidate_refs[0])
    assert v.status == NuggetStatus.PENDING_REVIEW and v.channel == AcquisitionChannel.RESEARCH and v.research_run_refs == [run.run_id]
    assert len(v.evidence_refs) == 2 and len(run.sources_examined) >= 2 and run.token_usage["calls"] >= 2
    assert v.authority_type == AuthorityType.EXTERNAL_REFERENCE    # the higher of the two agents' authorities
    assert ka.adapter.list_elements(D) == []                        # research never touched the graph


def test_P2_research_lineage_is_separate_until_governed(tmp_path):
    findings = json.dumps([{"title": "KYC", "statement": "KYC is required before activation.", "knowledge_type": "rule", "excerpt": "LLM", "confidence": 0.6}])
    ka = _ka_with_llm(tmp_path, {"LLM Knowledge Agent": findings})
    m = ka.research.create_mission(scope=D, objective="KYC", by="u")
    ka.research.run_mission(m.mission_id)
    v = ka.repo.require_version(ka.repo.missions.require(m.mission_id).candidate_refs[0])
    trace = ka.lineage.trace(v)
    assert trace["research_runs"][0]["mission_id"] == m.mission_id and trace["governance_decision"] is None
    approve_all(ka, [v], by="reviewer")
    assert ka.lineage.trace(ka.repo.require_version(v.ref))["governance_decision"]["decided_by"] == "reviewer"
    assert ka.adapter.list_elements(D)[0].lineage()[0]["nugget_id"] == v.canonical_id


def test_P3_enterprise_content_agent_respects_visibility(tmp_path):
    ka = _ka_with_llm(tmp_path, {})
    ka.ingestion.write_note(text="Merchant A refunds above $1,000 require manager approval.", owner="alice", scope=A, visibility=Visibility.PERSONAL)
    ka.ingestion.paste(text="Refunds above $500 require manager approval.", owner="ops", scope=D, visibility=Visibility.ENTERPRISE)
    m = ka.research.create_mission(scope=A, objective="refund approval", by="bob", permitted_visibility=Visibility.TEAM)
    run = ka.research.run_mission(m.mission_id)
    examined = {ka.repo.sources.get(s).visibility for s in run.sources_examined}
    assert Visibility.PERSONAL not in examined and Visibility.ENTERPRISE in examined


def test_P4_domain_builder_reuses_governed_knowledge_and_researches_only_the_gap(ka):
    out = ka.research.knowledge_for_domain(D, objective="build merchant acquiring", by="builder")
    assert out["reused"] == [] and out["mission_id"]
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    out2 = ka.research.knowledge_for_domain(A, objective="build merchant a", by="builder")
    assert out2["reused"] and out2["mission_id"] is None     # the instance inherits; no rediscovery


def test_N1_internet_agent_is_off_by_default_and_a_failing_agent_does_not_lose_others(tmp_path):
    from ka import config
    class Boom:
        agent_id = "agent.boom"
        def research(self, ctx):
            raise RuntimeError("network down")
    findings = json.dumps([{"title": "x", "statement": "Settlement occurs after clearing.", "knowledge_type": "fact", "excerpt": "e", "confidence": 0.6}])
    ka = _ka_with_llm(tmp_path, {"Domain Research Agent": findings})
    from ka.research import DomainResearchAgent, InternetResearchAgent
    ka.research.agents = [Boom(), InternetResearchAgent(), DomainResearchAgent()]
    assert config.get("KA_RESEARCH_INTERNET") is False
    m = ka.research.create_mission(scope=D, objective="settlement", by="u", questions=["https://example.test/x"])
    run = ka.research.run_mission(m.mission_id)
    assert run.errors and "agent.boom" in run.errors[0] and "internet research disabled" in run.notes
    assert len(run.candidate_nuggets_created) == 1
