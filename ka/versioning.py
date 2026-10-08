"""knowledge-versioning (§12, §14): the status machine and immutable versions.

Invariant 3 lives here: once a version is governed (APPROVED/ACTIVE/SUPERSEDED/OBSOLETE) its semantic
fields never change. A semantic modification is a NEW version of the same canonical_id that SUPERSEDES
the old one. Only lifecycle bookkeeping (status, superseded_by, graph refs, comments, evidence) may be written.
"""
from __future__ import annotations

from ka.model import KnowledgeNuggetVersion
from ka.repository import Repository
from ka.timeutil import now_iso
from ka.vocab import STATUS_TRANSITIONS, NuggetStatus

# Adding evidence/sources to a governed version is allowed (§31 "Add Evidence"); it does not change meaning.
SEMANTIC_FIELDS = ("title", "statement", "normalized_meaning", "scope_type", "scope_id", "knowledge_type",
                   "authority_type", "effective_from")


class ImmutableVersionError(RuntimeError):
    pass


class IllegalTransition(RuntimeError):
    pass


class VersioningService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def transition(self, v: KnowledgeNuggetVersion, to: NuggetStatus) -> KnowledgeNuggetVersion:
        if to not in STATUS_TRANSITIONS[v.status]:
            raise IllegalTransition(f"{v.ref}: {v.status.value} → {to.value} is not allowed (§12)")
        v.status = to
        if to == NuggetStatus.ACTIVE:
            v.activated_at = now_iso()
            v.effective_from = v.effective_from or v.activated_at
        if to in {NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE} and not v.effective_to:
            v.effective_to = now_iso()
        return self.repo.nuggets.put(v)

    def save(self, v: KnowledgeNuggetVersion) -> KnowledgeNuggetVersion:
        """Write a version, refusing semantic edits to a governed one. Compares against the copy ON DISK,
        because the caller may be holding the very object the cache holds."""
        stored = self.repo.stored_version(v.ref)
        if stored is not None and stored.is_governed():
            changed = [f for f in SEMANTIC_FIELDS if getattr(stored, f) != getattr(v, f)]
            if changed:
                raise ImmutableVersionError(f"{v.ref} is governed; semantic field(s) {changed} cannot change — create a new version (§14)")
        return self.repo.nuggets.put(v)

    def new_version_from(self, prior: KnowledgeNuggetVersion, **changes) -> KnowledgeNuggetVersion:
        """Draft vN+1 of the same canonical id as a CANDIDATE. Does not touch `prior`; supersession is
        recorded on activation (see GovernanceService)."""
        latest = self.repo.latest_version(prior.canonical_id) or prior
        data = prior.model_dump()
        for k in ("id", "approved_at", "approved_by", "activated_at", "governance_decision_id", "superseded_by",
                  "derived_graph_refs", "graph_change_refs", "effective_to", "comments", "analysis", "relationships"):
            data.pop(k, None)
        data.update(changes)
        data.update(version=latest.version + 1, status=NuggetStatus.CANDIDATE, created_at=now_iso(), supersedes=latest.ref)
        return KnowledgeNuggetVersion(**data)

    def supersede(self, old: KnowledgeNuggetVersion, new: KnowledgeNuggetVersion) -> None:
        if old.status in {NuggetStatus.ACTIVE, NuggetStatus.PENDING_REVIEW}:
            self.transition(old, NuggetStatus.SUPERSEDED)
        old.superseded_by = new.ref
        self.repo.nuggets.put(old)
        new.supersedes = new.supersedes or old.ref
        self.repo.nuggets.put(new)

    def history(self, canonical_id: str) -> list[KnowledgeNuggetVersion]:
        return self.repo.versions_of(canonical_id)

    @staticmethod
    def diff(a: KnowledgeNuggetVersion, b: KnowledgeNuggetVersion) -> dict[str, tuple]:
        """Compare Version (§31)."""
        out = {}
        for f in SEMANTIC_FIELDS + ("status", "confidence", "authority_rank", "tags", "source_refs", "evidence_refs"):
            if getattr(a, f) != getattr(b, f):
                out[f] = (getattr(a, f), getattr(b, f))
        return out
