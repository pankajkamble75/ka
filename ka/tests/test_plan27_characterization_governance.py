"""plan-27 Phase 2, step 2 — CHARACTERIZATION of `ka/governance.py` at the seam the plan changes, run green against the UNCHANGED file
and committed alone (docs/protected.md protocol). Pins what governance does TODAY: an ordinary REJECT retires nothing; a revision
stamped with a reason other than `source_revoked` and rejected ALSO retires nothing; there is no `request_retirement`."""
from __future__ import annotations

from ka.tests.conftest import D, approve_all, ingest_policy
from ka.vocab import DecisionOutcome, NuggetStatus


def _active(ka):
    cands = ingest_policy(ka, D, "Refunds above $500 require manager approval.")
    approve_all(ka, cands)
    return ka.repo.require_version(cands[0].ref)


def test_P1_characterization_an_ordinary_reject_retires_nothing_today(ka):
    prior = _active(ka)
    rev = ka.governance.propose_revision(prior.canonical_id, statement=prior.statement, by="u", reason="same statement, no reason stamped")
    d = ka.governance.decide(rev.ref, DecisionOutcome.REJECT, by="reviewer", reason="no")
    assert ka.repo.require_version(prior.ref).status == NuggetStatus.ACTIVE and ka.repo.require_version(rev.ref).status == NuggetStatus.REJECTED
    assert d.related_refs == [prior.ref] and d.resulting_refs == []          # the prior is the conflict partner; nothing is produced or retired


def test_P1b_characterization_a_stamped_retirement_request_is_ignored_today(ka):
    """The seam plan-27 changes: today only `source_revoked` makes REJECT retire the prior."""
    prior = _active(ka)
    rev = ka.governance.propose_revision(prior.canonical_id, statement=prior.statement, by="u", reason="retirement requested by u: wrong")
    rev.analysis["retirement_requested"] = {"by": "u", "why": "wrong", "prior_ref": prior.ref}
    ka.repo.nuggets.put(rev)
    ka.governance.decide(rev.ref, DecisionOutcome.REJECT, by="reviewer", reason="agreed")
    assert ka.repo.require_version(prior.ref).status == NuggetStatus.ACTIVE          # TODAY: ignored (plan-27 makes this OBSOLETE)


def test_P1c_characterization_there_is_no_request_retirement_today(ka):
    assert not hasattr(ka.governance, "request_retirement")


def test_P7_characterization_the_revoked_source_path_retires_on_reject(ka):
    """Positive coverage of the contract that must survive the change (plan-10 P7's shape at the seam)."""
    prior = _active(ka)
    src = ka.repo.sources.require(prior.source_refs[0])
    refs = ka.governance.reopen_for_revocation(src.id, by="ops")
    assert refs
    ka.governance.decide(refs[0], DecisionOutcome.REJECT, by="reviewer", reason="no other evidence")
    assert ka.repo.require_version(prior.ref).status == NuggetStatus.OBSOLETE
