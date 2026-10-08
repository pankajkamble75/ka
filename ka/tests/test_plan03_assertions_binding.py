"""plan-03 (research-01 R2, R8 KA half) — process assertions on nuggets, grammar registry, binder, canonical subjects.

Characterization cases (P8, N3a) ran green against the pre-plan-03 governance code before Phase 4 changed it.
"""
from __future__ import annotations

import pytest

from ka.tests.conftest import A, D, approve_all, ingest_policy
from ka.versioning import SEMANTIC_FIELDS, ImmutableVersionError


# ---------------------------------------------------------------- Phase 4 characterization (pre-change behaviour)

def test_P8_a_candidate_today_carries_no_assertion_and_no_binding(ka):
    cand = ingest_policy(ka, D, "Refunds above $500 require manager approval.")[0]
    assert getattr(cand, "subject", None) is None and getattr(cand, "predicate", None) is None and getattr(cand, "object", None) is None
    assert not hasattr(ka.repo, "bindings") or len(ka.repo.bindings) == 0


def test_N3a_semantic_fields_today_are_plan02s_eight_and_statement_edits_are_refused(ka):
    assert set(SEMANTIC_FIELDS) >= {"title", "statement", "normalized_meaning", "scope_type", "scope_id", "knowledge_type",
                                    "authority_type", "effective_from"}
    v = approve_all(ka, ingest_policy(ka, A, "Merchant A refunds above $500 require manager approval."))[0]
    v.statement = "tampered"
    with pytest.raises(ImmutableVersionError):
        ka.versioning.save(v)


# ---------------------------------------------------------------- Phase 1: registry

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from ka import config  # noqa: E402
from ka.api import PREFIX, create_app, set_ka  # noqa: E402
from ka.governance import CandidateInput, GovernanceError  # noqa: E402
from ka.grammar import GrammarMismatch, GrammarRegistry  # noqa: E402
from ka.identity import SubjectRegistry, canonical_key  # noqa: E402
from ka.model import ObjectRef, Subject  # noqa: E402
from ka.service import KnowledgeAcquisition  # noqa: E402
from ka.llm import StubLLMProvider  # noqa: E402
from ka.tests.conftest import FIXTURE_GRAMMAR, S, P  # noqa: E402
from ka.vocab import BindingStatus  # noqa: E402

EOS_GRAMMAR = Path(os.environ.get("KA_ENTERPRISE_OS_ROOT") or "/root/enterprise-os-070626") / "knowledge_worker" / "graph_model"


def _registry(tmp_path, src=FIXTURE_GRAMMAR):
    d = tmp_path / "g"
    shutil.copytree(src, d)
    r = GrammarRegistry(d, tmp_path / "snap.json")
    r.load()
    return r, d


def _assert(ka, statement, subject_name, predicate, obj=None, kind="process", scope=D, method="evidenced"):
    got = ka.ingestion.write_note(text=statement, owner="u", scope=scope)
    return ka.governance.ingest_candidate(CandidateInput(
        title=statement[:60], statement=statement, scope=scope, source_ids=[got.source.id], evidence_ids=[],
        subject=Subject(kind=kind, canonical_key=canonical_key(subject_name), name=subject_name), predicate=predicate,
        object=obj, binding_method=method, created_by="u"))


def test_P1_the_registry_loads_the_fixture_pair_with_versions_digests_and_a_snapshot(tmp_path):
    r, _ = _registry(tmp_path)
    v = r.versions()
    assert v["grammar_version"] == "grammar/v2" and v["type_table_version"] == "process-types/v2"
    assert len(v["grammar_digest"]) == 64 and len(v["type_table_digest"]) == 64
    assert len(r.node_kinds()) == 10 and len(r.slots()) == 15 and r.type_names() == ["decision", "interaction", "control"]
    assert (tmp_path / "snap.json").exists() and not r.is_stale()
    assert r.type_grammar("decision")["input"] == "required" and r.slot_for_edge("produces") == "output"


def test_P2_the_registry_loads_the_real_eos_files_when_present(tmp_path):
    if not (EOS_GRAMMAR / "grammar.json").exists():
        pytest.skip("enterprise-os checkout not reachable")
    r, _ = _registry(tmp_path, EOS_GRAMMAR)
    assert len(r.type_names()) == 10 and len([e for e in r.edge_pairs()]) == 15 and r.descriptor()["loaded"]


def test_N2_files_changed_under_the_same_version_make_the_registry_stale_and_refresh_fails_closed(tmp_path):
    r, d = _registry(tmp_path)
    g = json.loads((d / "grammar.json").read_text()); g["slots"].append({"name": "surprise", "description": "x"})
    (d / "grammar.json").write_text(json.dumps(g))
    r.load()
    assert r.is_stale() and "digest" in r.stale_reason()
    with pytest.raises(GrammarMismatch):
        r.refresh()
    snap = r.refresh(force=True)
    assert not r.is_stale() and "surprise" in r.slots() and snap.grammar_digest != ""


# ---------------------------------------------------------------- Phases 2–4: binder, identity, pipeline

def test_P3_typed_as_a_known_type_binds_exactly(ka):
    v = _assert(ka, "Merchant underwriting is a decision process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decision"))
    b = ka.repo.binding_for(v.ref)
    assert b.binding_status == BindingStatus.BOUND and b.process_type == "decision" and b.confidence == 1.0
    assert b.grammar_version == "grammar/v2" and b.type_table_version == "process-types/v2" and b.method == "evidenced"
    assert v.subject.canonical_key == "merchant_underwriting" and ka.repo.subjects.get("merchant_underwriting").kind == "process"


def test_P4_a_relation_predicate_binds_to_the_eos_edge_and_slot(ka):
    v = _assert(ka, "Merchant underwriting consumes the merchant application.", "Merchant Underwriting", "consumes",
                ObjectRef(kind="entity", value="merchant application"))
    b = ka.repo.binding_for(v.ref)
    assert b.binding_status == BindingStatus.BOUND and b.edge == "consumes" and b.slot == "input"
    assert v.object.canonical_key == "merchant_application" and ka.repo.subjects.get("merchant_application").kind == "entity"


def test_P5_description_is_a_property_not_an_edge(ka):
    v = _assert(ka, "Merchant underwriting evaluates applications for eligibility.", "Merchant Underwriting", "description",
                ObjectRef(value="Evaluates applications for eligibility"))
    b = ka.repo.binding_for(v.ref)
    assert b.binding_status == BindingStatus.NOT_APPLICABLE and b.edge is None and b.grammar_version == "grammar/v2"


def test_P6_subject_resolution_by_key_alias_and_similarity(ka):
    reg = SubjectRegistry(ka.repo)
    a, created_a = reg.resolve("process", "Merchant Underwriting")
    b, created_b = reg.resolve("process", "Underwrite merchant applications", aliases=["merchant underwriting"])
    c, created_c = reg.resolve("process", "Chargeback dispute handling")
    assert created_a and not created_b and a.canonical_key == b.canonical_key and "Underwrite merchant applications" in a.aliases
    assert created_c and c.canonical_key != a.canonical_key
    d, created_d = reg.resolve("process", "merchant underwriting process")      # similarity, not exact
    assert not created_d and d.canonical_key == a.canonical_key
    e, created_e = reg.resolve("entity", "Merchant Underwriting")               # same name, different kind → different subject
    assert created_e


def test_P7_a_grammar_release_adds_bindings_and_leaves_governed_versions_untouched(tmp_path):
    d = tmp_path / "g"; shutil.copytree(FIXTURE_GRAMMAR, d)
    with config.scoped(KA_GRAMMAR_DIR=str(d)):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False)
        for s_, p_ in [(S, None), (P, S), (D, P), (A, D)]:
            ka.register_scope(s_, p_)
        v = _assert(ka, "Merchant underwriting is a planning process.", "Merchant Underwriting", "typed_as", ObjectRef(value="planning"))
        approve_all(ka, [v])
        before = ka.repo.nuggets.get_stored(v.id).model_dump()
        assert ka.repo.binding_for(v.ref).binding_status == BindingStatus.UNRESOLVED       # fixture has no 'planning'
        t = json.loads((d / "process_types.json").read_text()); t["version"] = "process-types/v3"
        t["types"]["planning"] = t["types"]["decision"]; (d / "process_types.json").write_text(json.dumps(t))
        ka.grammar.refresh()
        assert not ka.grammar.is_stale() and ka.grammar.versions()["type_table_version"] == "process-types/v3"
        n = ka.binder.rebind_all()
        assert n == 1 and len(ka.repo.bindings_of(v.ref)) == 2
        assert ka.repo.binding_for(v.ref).binding_status == BindingStatus.BOUND and ka.repo.binding_for(v.ref).process_type == "planning"
        assert ka.repo.bindings_of(v.ref)[0].binding_status == BindingStatus.UNRESOLVED      # history intact
        assert ka.repo.nuggets.get_stored(v.id).model_dump() == before                            # version byte-identical


def test_P9_propose_revision_carries_the_subject_and_predicate_to_v2_with_a_fresh_binding(ka):
    v = _assert(ka, "Merchant underwriting is a decision process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decision"))
    approve_all(ka, [v])
    v2 = ka.governance.propose_revision(v.canonical_id, statement="Merchant underwriting is an interaction process.", by="u", reason="x",
                                        object=ObjectRef(value="interaction"))
    assert v2.subject.canonical_key == "merchant_underwriting" and v2.predicate == "typed_as"
    assert ka.repo.binding_for(v2.ref).process_type == "interaction" and ka.repo.binding_for(v.ref).process_type == "decision"


def test_N1_an_unknown_type_is_unresolved_with_alternatives(ka):
    v = _assert(ka, "Merchant underwriting is a decisionmaking process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decisionmaking"))
    b = ka.repo.binding_for(v.ref)
    assert b.binding_status in {BindingStatus.UNRESOLVED, BindingStatus.PROPOSED} and b.alternatives[0] == "decision"
    assert "process-types/v2" in " ".join(b.reasons)
    w = _assert(ka, "Merchant underwriting is a frobnication process.", "Merchant Underwriting", "typed_as", ObjectRef(value="frobnication"))
    assert ka.repo.binding_for(w.ref).binding_status == BindingStatus.UNRESOLVED


def test_N3b_semantic_fields_now_include_the_assertion(ka):
    assert set(SEMANTIC_FIELDS) == {"title", "statement", "normalized_meaning", "scope_type", "scope_id", "knowledge_type",
                                    "authority_type", "effective_from", "subject", "predicate", "object"}


def test_N4_unknown_predicate_or_subject_kind_is_refused(ka):
    got = ka.ingestion.write_note(text="x", owner="u", scope=D)
    with pytest.raises(GovernanceError, match="unknown predicate"):
        ka.governance.ingest_candidate(CandidateInput(title="x", statement="x", scope=D, source_ids=[got.source.id], evidence_ids=[], predicate="frobnicates"))
    with pytest.raises(GovernanceError, match="not an EOS node kind"):
        ka.governance.ingest_candidate(CandidateInput(title="x", statement="x", scope=D, source_ids=[got.source.id], evidence_ids=[],
                                                      subject=Subject(kind="widget", canonical_key="w", name="W"), predicate="description"))


def test_N5_without_a_grammar_every_binding_is_unresolved_and_nothing_raises(tmp_path):
    with config.scoped(KA_GRAMMAR_DIR="/nonexistent/grammar", KA_ENTERPRISE_OS_ROOT=""):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        assert not ka.grammar.loaded
        v = _assert(ka, "Merchant underwriting is a decision process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decision"))
        b = ka.repo.binding_for(v.ref)
        assert b.binding_status == BindingStatus.UNRESOLVED and "no grammar loaded" in b.reasons[0]
        client = TestClient(create_app(ka))
        try:
            assert client.get(f"{PREFIX}/grammar").json()["loaded"] is False
        finally:
            set_ka(None)


def test_N6_subject_is_immutable_on_a_governed_version_but_bindings_are_not(ka):
    v = _assert(ka, "Merchant underwriting is a decision process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decision"))
    approve_all(ka, [v])
    v = ka.repo.require_version(v.ref)
    v.subject = Subject(kind="process", canonical_key="other", name="Other")
    with pytest.raises(ImmutableVersionError):
        ka.versioning.save(v)
    assert ka.binder.bind(ka.repo.require_version(v.ref)).binding_status == BindingStatus.BOUND and len(ka.repo.bindings_of(v.ref)) == 2


def test_N9_rebind_all_refuses_on_a_stale_registry(tmp_path):
    d = tmp_path / "g"; shutil.copytree(FIXTURE_GRAMMAR, d)
    with config.scoped(KA_GRAMMAR_DIR=str(d)):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
        for s_, p_ in [(S, None), (P, S), (D, P)]:
            ka.register_scope(s_, p_)
        _assert(ka, "Merchant underwriting is a decision process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decision"))
        g = json.loads((d / "grammar.json").read_text()); g["core_roles"] = g["core_roles"] + ["partner"] if isinstance(g["core_roles"], list) else g["core_roles"]
        (d / "grammar.json").write_text(json.dumps(g) + "\n")
        ka.grammar.load()
        assert ka.grammar.is_stale()
        before = len(ka.repo.bindings)
        with pytest.raises(GrammarMismatch):
            ka.binder.rebind_all()
        assert len(ka.repo.bindings) == before
        v = _assert(ka, "Merchant underwriting is a control process.", "Merchant Underwriting", "typed_as", ObjectRef(value="control"))
        assert ka.repo.binding_for(v.ref).binding_status == BindingStatus.STALE


# ---------------------------------------------------------------- Phase 5: API

@pytest.fixture
def client(ka):
    yield TestClient(create_app(ka))
    set_ka(None)


def test_P10_detail_grammar_and_subject_routes(client, ka):
    v = _assert(ka, "Merchant underwriting is a decision process.", "Merchant Underwriting", "typed_as", ObjectRef(value="decision"))
    d = client.get(f"{PREFIX}/nugget/{v.ref}").json()
    assert d["assertion"]["subject"]["canonical_key"] == "merchant_underwriting" and d["binding"]["binding_status"] == "bound"
    g = client.get(f"{PREFIX}/grammar").json()
    assert g["grammar_version"] == "grammar/v2" and g["stale"] is False and "decision" in g["types"]
    s = client.get(f"{PREFIX}/subjects/merchant_underwriting").json()
    assert s["subject"]["kind"] == "process" and s["nuggets"][0]["ref"] == v.ref
    assert client.get(f"{PREFIX}/subjects").json()["subjects"][0]["nuggets"] == 1
    assert client.get(f"{PREFIX}/nugget/{v.ref}/binding").json()["binding"]["process_type"] == "decision"
    assert client.post(f"{PREFIX}/nugget/{v.ref}/rebind").json()["binding"]["binding_status"] == "bound"


def test_P11_a_note_with_an_assertion_yields_one_bound_candidate(client):
    r = client.post(f"{PREFIX}/sources/note", json={"text": "Merchant underwriting is a decision process.", "owner": "u", "scope_type": "DOMAIN",
                                                     "scope_id": "merchant-acquiring",
                                                     "assertion": {"subject_kind": "process", "subject_name": "Merchant underwriting", "predicate": "typed_as", "object_value": "decision"}})
    assert r.status_code == 200 and len(r.json()["candidates"]) == 1
    row = r.json()["candidates"][0]
    assert row["subject"] == "merchant_underwriting" and row["predicate"] == "typed_as"
    assert client.get(f"{PREFIX}/nugget/{row['ref']}/binding").json()["binding"]["binding_status"] == "bound"
    bad = client.post(f"{PREFIX}/sources/note", json={"text": "x", "owner": "u", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring",
                                                       "assertion": {"subject_name": "X", "predicate": "frobnicates"}})
    assert bad.status_code == 400


def test_N8_refresh_without_force_on_a_stale_registry_is_409(tmp_path):
    d = tmp_path / "g"; shutil.copytree(FIXTURE_GRAMMAR, d)
    with config.scoped(KA_GRAMMAR_DIR=str(d)):
        ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
        client = TestClient(create_app(ka))
        try:
            (d / "grammar.json").write_text((d / "grammar.json").read_text() + "\n")
            assert client.post(f"{PREFIX}/grammar/refresh", json={"force": False}).status_code == 409
            assert client.post(f"{PREFIX}/grammar/rebind-all").status_code == 409
            assert client.post(f"{PREFIX}/grammar/refresh", json={"force": True}).status_code == 200
            assert client.get(f"{PREFIX}/grammar").json()["stale"] is False
        finally:
            set_ka(None)
