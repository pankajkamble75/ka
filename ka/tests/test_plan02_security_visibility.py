"""plan-02 (research-01 R4 step 1, R5, R6) — access containment, upload/URL safety, visibility protection on scope changes.

Characterization cases (P6, P7, P8, N4) were run green against the pre-plan-02 governance code before Phase 3 changed it.
"""
from __future__ import annotations

import pytest

from ka.governance import GovernanceError
from ka.model import Scope
from ka.tests.conftest import A, B, C, D, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus, ScopeType, Visibility


def _personal_candidate(ka, scope=A, text="Our store must close on Sundays."):
    got = ka.ingestion.write_note(text=text, owner="alice", scope=scope, visibility=Visibility.PERSONAL)
    return ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="alice")[0]


# ---------------------------------------------------------------- Phase 3 characterization (pre-change behaviour)

def test_P6_change_scope_keeps_an_enterprise_candidates_visibility(ka):
    cand = ingest_policy(ka, A, "KYC is required before activation.")[0]
    assert cand.visibility == Visibility.ENTERPRISE
    d = ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="domain-wide", new_scope=D)
    new = ka.repo.require_version(d.resulting_refs[0])
    assert new.scope_type == ScopeType.DOMAIN and new.visibility == Visibility.ENTERPRISE


def test_P7_promotion_keeps_the_lead_nuggets_enterprise_visibility(ka):
    for inst in (A, B, C):
        approve_all(ka, ingest_policy(ka, inst, "Weekend refunds require two approvals."))
    prop = ka.promotion.detect(D)[0]
    p = ka.promotion.decide(prop.id, approve=True, by="lead", reason="pattern")
    assert ka.repo.require_version(p.candidate_ref).visibility == Visibility.ENTERPRISE


def test_P8_change_scope_between_two_instances_leaves_a_personal_candidate_personal(ka):
    cand = _personal_candidate(ka)
    assert cand.visibility == Visibility.PERSONAL
    d = ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="wrong store", new_scope=B)
    new = ka.repo.require_version(d.resulting_refs[0])
    assert new.scope_id == "merchant-b" and new.visibility == Visibility.PERSONAL


def test_N4_change_scope_by_a_research_agent_is_refused(ka):
    cand = ingest_policy(ka, A, "KYC is required before activation.")[0]
    with pytest.raises(GovernanceError):
        ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="agent.synthesis", reason="x", new_scope=D)


# ---------------------------------------------------------------- Phase 1: access containment

from fastapi.testclient import TestClient  # noqa: E402

from ka import config, security  # noqa: E402
from ka.api import PREFIX, create_app, set_ka  # noqa: E402

REMOTE = ("203.0.113.9", 12345)
LOCAL = ("127.0.0.1", 1)


@pytest.fixture
def app(ka):
    a = create_app(ka)
    yield a
    set_ka(None)


def test_P1_loopback_peer_needs_no_token_under_token_policy(app):
    with config.scoped(KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN="s3cret"):
        assert TestClient(app, client=LOCAL).get(f"{PREFIX}/healthz").status_code == 200


def test_P2_remote_peer_with_the_right_bearer_token_is_admitted(app):
    with config.scoped(KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN="s3cret"):
        r = TestClient(app, client=REMOTE).get(f"{PREFIX}/scopes", headers={"Authorization": "Bearer s3cret"})
        assert r.status_code == 200 and r.json()["scopes"]


def test_P3_open_policy_admits_a_remote_peer_without_a_token(app):
    with config.scoped(KA_ACCESS_POLICY="open", KA_ACCESS_TOKEN=""):
        assert TestClient(app, client=REMOTE).get(f"{PREFIX}/healthz").status_code == 200


def test_N1_remote_peer_without_a_token_gets_401_with_a_challenge(app):
    with config.scoped(KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN="s3cret"):
        r = TestClient(app, client=REMOTE).get(f"{PREFIX}/healthz")
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
        assert TestClient(app, client=REMOTE).get("/console/").status_code == 200     # the static console stays reachable


def test_N2_wrong_token_and_no_configured_token_both_fail_closed(app):
    with config.scoped(KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN="s3cret"):
        assert TestClient(app, client=REMOTE).get(f"{PREFIX}/healthz", headers={"Authorization": "Bearer nope"}).status_code == 401
    with config.scoped(KA_ACCESS_POLICY="token", KA_ACCESS_TOKEN=""):
        assert TestClient(app, client=REMOTE).get(f"{PREFIX}/healthz", headers={"Authorization": "Bearer anything"}).status_code == 401
    with config.scoped(KA_ACCESS_POLICY="garbage", KA_ACCESS_TOKEN="s3cret"):
        assert TestClient(app, client=REMOTE).get(f"{PREFIX}/healthz", headers={"Authorization": "Bearer s3cret"}).status_code == 403


def test_N3_loopback_policy_refuses_a_remote_peer_even_with_a_token(app):
    with config.scoped(KA_ACCESS_POLICY="loopback", KA_ACCESS_TOKEN="s3cret"):
        assert TestClient(app, client=REMOTE).get(f"{PREFIX}/healthz", headers={"Authorization": "Bearer s3cret"}).status_code == 403
        assert TestClient(app, client=LOCAL).get(f"{PREFIX}/healthz").status_code == 200


# ---------------------------------------------------------------- Phase 2: upload cap and URL safety

def test_P4_an_upload_under_the_cap_is_accepted_and_extracted(app):
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        body = b"# Policy\nRefunds above $500 require manager approval.\n\nX" + b"x" * (1024 * 1024 - 200)
        r = TestClient(app).post(f"{PREFIX}/sources/upload", data={"owner": "u", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"},
                                 files={"file": ("policy.md", body, "text/markdown")})
        assert r.status_code == 200 and r.json()["candidates"]


def test_N5_an_upload_over_the_cap_is_refused_and_creates_no_source(app, ka):
    with config.scoped(KA_MAX_UPLOAD_MB=1):
        before = len(ka.repo.sources)
        big = b"y" * (1024 * 1024 + 10)
        r = TestClient(app).post(f"{PREFIX}/sources/upload", data={"owner": "u", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"},
                                 files={"file": ("big.txt", big, "text/plain")})
        assert r.status_code == 413 and len(ka.repo.sources) == before
        r2 = TestClient(app).post(f"{PREFIX}/corrections/upload", data={"what_is_incorrect": "x", "correct_value": "Refunds above $750 require manager approval."},
                                  files={"file": ("big.txt", big, "text/plain")})
        assert r2.status_code == 413
        # Content-Length alone is enough to refuse, before the body is read
        r3 = TestClient(app).post(f"{PREFIX}/sources/upload", data={"owner": "u", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"},
                                  files={"file": ("big.txt", big, "text/plain")}, headers={"Content-Length": str(50 * 1024 * 1024)})
        assert r3.status_code == 413


def test_P5_public_and_allow_listed_hosts_are_safe(monkeypatch):
    monkeypatch.setattr(security, "_resolve", lambda host: ["93.184.216.34"])
    assert security.is_safe_url("https://example.com/doc") == (True, "ok")
    monkeypatch.setattr(security, "_resolve", lambda host: ["10.1.2.3"])
    with config.scoped(KA_URL_ALLOWLIST="wiki.corp.internal, other"):
        assert security.is_safe_url("http://wiki.corp.internal/page")[0] is True
    assert security.is_safe_url("http://wiki.corp.internal/page")[0] is False


def test_N6_unsafe_links_are_never_fetched_by_link_or_the_internet_agent(ka, monkeypatch):
    calls = []
    monkeypatch.setattr(security, "_resolve", lambda host: ["10.0.0.5"] if host == "intranet.example" else ["93.184.216.34"])
    monkeypatch.setattr(security.httpx, "Client", lambda **kw: (_ for _ in ()).throw(AssertionError("network touched")))
    for url in ("http://127.0.0.1:8011/", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/", "file:///etc/passwd",
                "http://intranet.example/secret", "http://[::1]/"):
        got = ka.ingestion.link(url=url, owner="u", scope=D)
        assert got.version.extraction_status.value == "FAILED" and got.version.extraction_note.startswith("blocked:"), url
        assert got.version.byte_size == 0
    assert any(a.what == "source.blocked" for a in ka.repo.audit())
    with config.scoped(KA_RESEARCH_INTERNET=True):
        m = ka.research.create_mission(scope=D, objective="x", by="u", questions=["http://10.0.0.5/"])
        run = ka.research.run_mission(m.mission_id)
    assert any("blocked:" in e for e in run.errors) and not calls


# ---------------------------------------------------------------- Phase 3: visibility rule (post-change)

def test_P9_change_scope_with_widen_visibility_records_the_change(ka):
    cand = _personal_candidate(ka)
    d = ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="all stores", new_scope=D, widen_visibility=True)
    new = ka.repo.require_version(d.resulting_refs[0])
    assert new.visibility == Visibility.DOMAIN and d.visibility_change == {"from": "PERSONAL", "to": "DOMAIN"}
    d2 = ka.governance.decide(new.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="everywhere",
                              new_scope=Scope(scope_type=ScopeType.STRUCTURE, scope_id="universal"), widen_visibility=True)
    assert ka.repo.require_version(d2.resulting_refs[0]).visibility == Visibility.ENTERPRISE


def test_N8_change_scope_that_would_widen_visibility_is_refused_without_the_flag(ka):
    cand = _personal_candidate(ka)
    n_before = len(ka.repo.nuggets)
    with pytest.raises(GovernanceError, match="PERSONAL → DOMAIN"):
        ka.governance.decide(cand.ref, DecisionOutcome.CHANGE_SCOPE, by="reviewer", reason="x", new_scope=D)
    assert ka.repo.require_version(cand.ref).status == NuggetStatus.PENDING_REVIEW and len(ka.repo.nuggets) == n_before
    client = TestClient(create_app(ka))
    try:
        r = client.post(f"{PREFIX}/nugget/{cand.ref}/apply", json={"by": "reviewer", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring"})
        assert r.status_code == 409 and "widen_visibility" in r.json()["detail"]
        r = client.post(f"{PREFIX}/nugget/{cand.ref}/apply", json={"by": "reviewer", "scope_type": "DOMAIN", "scope_id": "merchant-acquiring", "widen_visibility": True})
        assert r.status_code == 200 and r.json()["applied"] is True
    finally:
        set_ka(None)


def test_N9_promotion_of_team_visible_knowledge_is_refused_without_the_flag(ka):
    for inst in (A, B, C):
        got = ka.ingestion.write_note(text="Weekend refunds must have two approvals.", owner="ops", scope=inst, visibility=Visibility.TEAM)
        approve_all(ka, ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops"))
    prop = ka.promotion.detect(D)[0]
    with pytest.raises(GovernanceError, match="TEAM → DOMAIN"):
        ka.promotion.decide(prop.id, approve=True, by="lead")
    assert ka.repo.promotions.require(prop.id).status == "PROPOSED"
    p = ka.promotion.decide(prop.id, approve=True, by="lead", widen_visibility=True)
    assert ka.repo.require_version(p.candidate_ref).visibility == Visibility.DOMAIN
