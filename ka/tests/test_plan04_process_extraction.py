"""plan-04 (research-01 R3, R16 layout extras) — the second extraction pass, spans, row locators, re-extraction, OCR hook.

Characterization cases (P8, N5-before, P9-before) ran green against the pre-plan-04 governance code before Phase 3 changed it.
"""
from __future__ import annotations

from pathlib import Path

from ka.tests.conftest import D
from ka.vocab import AuthorityType

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "underwriting_sop.md"


def _upload_sop(ka, **kw):
    got = ka.ingestion.upload(filename="underwriting_sop.md", data=FIXTURE.read_bytes(), owner="ops", scope=D,
                              authority=AuthorityType.OPERATING_PROCEDURE)
    return got, ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="ops", **kw)


# ---------------------------------------------------------------- Phase 3 characterization (pre-change behaviour)

def test_P8_today_the_sop_yields_statement_only_candidates_without_subjects_or_spans(ka):
    got, cands = _upload_sop(ka)
    assert cands and all(c.subject is None and c.predicate is None for c in cands)
    for c in cands:
        ev = ka.repo.evidence.get(c.evidence_refs[0])
        assert ev.locator and getattr(ev, "span_id", None) is None
    # the statements the modal-verb pass finds today (pinned so P9 can compare after Phase 3)
    assert {c.statement for c in cands} == STATEMENTS_BEFORE


STATEMENTS_BEFORE = {
    "Applications with a risk score above 80 must be referred to the credit committee.",
    "Beneficial owner means a natural person who owns 25% or more of the merchant.",
    "Communicate decision — send the outcome to the merchant within two business days.",
    "Make credit decision — approve, decline, or refer the application based on the risk score.",
}


def test_N5_an_empty_source_yields_no_candidates(ka):
    got = ka.ingestion.paste(text="   ", owner="u", scope=D)
    assert ka.governance.extract_from_source(got.source, got.version, got.extraction, actor="u") == []
