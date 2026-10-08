"""plan-16 (research-01 R17; product test PT9) — the Enterprise Content agent reuses governed knowledge and spends the model only on
never-extracted sources, capped and most-relevant first."""
from __future__ import annotations

import json

from ka import config
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import A, B, D, P, S, approve_all, ingest_policy
from ka.vocab import RunStatus, Visibility

FINDINGS = json.dumps([{"title": "x", "statement": "Settlement occurs two business days after clearing.", "knowledge_type": "fact", "excerpt": "Settlement", "confidence": 0.6}])


def _ka(tmp_path, **responses):
    inst = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(responses=responses, default_response="[]"), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P), (A, D), (B, D)]:
        inst.register_scope(s_, p_)
    return inst


def _extraction_calls(ka):
    return [c for c in ka.provider.calls if "Document title:" in c]


def test_P1_governed_knowledge_matching_the_question_is_reused_without_a_model_call(tmp_path):
    ka = _ka(tmp_path)
    active = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    pending = ingest_policy(ka, D, "Chargebacks must be answered within 30 days.", title="P2")
    n_before = len(_extraction_calls(ka))
    m = ka.research.create_mission(scope=D, objective="refund approval thresholds", by="u")
    run = ka.research.run_mission(m.mission_id)
    assert active[0].ref in run.reused_refs and pending[0].ref not in run.reused_refs      # pending matches no word of the question
    assert set(active[0].source_refs) <= set(run.sources_examined)
    assert len(_extraction_calls(ka)) == n_before                                            # nothing re-extracted: every source has knowledge
    assert run.status == RunStatus.COMPLETED


def test_P2_only_sources_without_derived_knowledge_are_re_extracted(tmp_path):
    ka = _ka(tmp_path)
    approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))      # has knowledge
    ka.ingestion.paste(text="Settlement occurs two business days after clearing.", owner="ops", scope=D, title="never extracted")
    n_before = len(_extraction_calls(ka))
    m = ka.research.create_mission(scope=D, objective="settlement timing after clearing", by="u")
    run = ka.research.run_mission(m.mission_id)
    calls = _extraction_calls(ka)[n_before:]
    assert len(calls) == 1 and "never extracted" in calls[0]
    assert any(ka.repo.sources.get(s).title == "never extracted" for s in run.sources_examined)


def test_P3_the_cap_keeps_the_most_relevant_sources_and_notes_the_rest(tmp_path):
    ka = _ka(tmp_path)
    for i in range(6):
        ka.ingestion.paste(text=("Settlement occurs two business days after clearing. " * (i + 1)) if i < 2 else f"Unrelated note {i} about office plants.", owner="ops", scope=D, title=f"src{i}")
    with config.scoped(KA_RESEARCH_MAX_SOURCES=2):
        m = ka.research.create_mission(scope=D, objective="settlement timing after clearing", by="u")
        run = ka.research.run_mission(m.mission_id)
    calls = _extraction_calls(ka)
    assert len(calls) == 2 and all(("src0" in c or "src1" in c) for c in calls)
    assert "4 never-extracted source(s) left" in run.notes


def test_P4_PT9_a_populated_store_makes_bounded_extraction_calls(tmp_path):
    ka = _ka(tmp_path, **{"Domain Research Agent": FINDINGS})
    for i in range(40):
        approve_all(ka, ingest_policy(ka, D, f"Rule {i}: refunds above ${100 + i} require approval at desk {i}.", title=f"Policy {i}"))
    for i in range(5):
        ka.ingestion.paste(text=f"Settlement note {i}: settlement occurs after clearing.", owner="ops", scope=D, title=f"raw{i}")
    n_before = len(_extraction_calls(ka))
    m = ka.research.create_mission(scope=D, objective="refund approval and settlement", by="u")
    run = ka.research.run_mission(m.mission_id)
    assert len(_extraction_calls(ka)) - n_before <= config.get("KA_RESEARCH_MAX_SOURCES")
    assert len(run.reused_refs) >= 40 and run.status == RunStatus.COMPLETED


def test_N1_reuse_respects_the_permitted_visibility_like_sources_do(tmp_path):
    ka = _ka(tmp_path)
    personal = approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $1,000 require manager approval.", owner="alice"))
    v = ka.repo.require_version(personal[0].ref); v.visibility = Visibility.PERSONAL; ka.repo.nuggets.put(v)
    ent = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval.", owner="ops"))
    m = ka.research.create_mission(scope=A, objective="refund approval", by="bob", permitted_visibility=Visibility.TEAM)
    run = ka.research.run_mission(m.mission_id)
    assert ent[0].ref in run.reused_refs and personal[0].ref not in run.reused_refs


def test_N2_research_channel_sources_are_never_re_extracted(tmp_path):
    ka = _ka(tmp_path, **{"LLM Knowledge Agent": FINDINGS})
    m1 = ka.research.create_mission(scope=D, objective="settlement", by="u")
    ka.research.run_mission(m1.mission_id)                      # records a RESEARCH-channel source with no governed knowledge yet
    n_before = len(_extraction_calls(ka))
    m2 = ka.research.create_mission(scope=D, objective="settlement after clearing", by="u")
    ka.research.run_mission(m2.mission_id)
    assert len(_extraction_calls(ka)) == n_before


def test_N3_cap_zero_extracts_nothing_but_still_reuses(tmp_path):
    ka = _ka(tmp_path)
    active = approve_all(ka, ingest_policy(ka, D, "Refunds above $500 require manager approval."))
    ka.ingestion.paste(text="Refund approvals are logged daily.", owner="ops", scope=D, title="raw")
    n_before = len(_extraction_calls(ka))
    with config.scoped(KA_RESEARCH_MAX_SOURCES=0):
        m = ka.research.create_mission(scope=D, objective="refund approval", by="u")
        run = ka.research.run_mission(m.mission_id)
    assert len(_extraction_calls(ka)) == n_before and active[0].ref in run.reused_refs and run.status == RunStatus.COMPLETED
