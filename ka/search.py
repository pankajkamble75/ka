"""knowledge-search (§35): structured + lexical search over nuggets, sources, evidence and graph lineage,
with the scope filters the Knowledge Console offers. Lexical on purpose — this is not a vector-DB UI (§45).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ka.conflict import similarity, tokens
from ka.model import KnowledgeNuggetVersion, Scope
from ka.repository import Repository
from ka.vocab import NuggetStatus, ScopeType

FILTERS = ("All Knowledge", "Structure", "Domain", "Instance", "Current", "Historical", "Pending", "Conflicting")

_CURRENT = {NuggetStatus.ACTIVE}
_HISTORICAL = {NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE, NuggetStatus.ARCHIVED, NuggetStatus.REJECTED}
_PENDING = {NuggetStatus.CANDIDATE, NuggetStatus.ANALYZED, NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.APPROVED}


@dataclass
class SearchHit:
    kind: str                    # nugget | source | evidence
    id: str
    score: float
    title: str
    snippet: str
    scope: str | None = None
    status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class SearchService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def search(self, query: str = "", *, filter: str = "All Knowledge", scope: Scope | None = None, status: str | None = None,
               authority: str | None = None, tags: list[str] | None = None, author: str | None = None, knowledge_type: str | None = None,
               source_id: str | None = None, effective_on: str | None = None, graph_element_id: str | None = None,
               include_sources: bool = True, limit: int = 50) -> list[SearchHit]:
        q = tokens(query) if query else set()
        hits: list[SearchHit] = []
        for n in self.repo.nuggets.all():
            if not self._status_ok(n, filter, status):
                continue
            if filter == "Structure" and n.scope_type != ScopeType.STRUCTURE:
                continue
            if filter == "Domain" and n.scope_type not in {ScopeType.DOMAIN, ScopeType.PARENT_DOMAIN}:
                continue
            if filter == "Instance" and n.scope_type != ScopeType.INSTANCE:
                continue
            if scope and (n.scope_type != scope.scope_type or n.scope_id != scope.scope_id):
                continue
            if authority and n.authority_type.value != authority:
                continue
            if knowledge_type and n.knowledge_type.value != knowledge_type:
                continue
            if tags and not set(tags) <= set(n.tags):
                continue
            if author and author not in {n.created_by, n.approved_by}:
                continue
            if source_id and source_id not in n.source_refs:
                continue
            if effective_on and not _effective(n, effective_on):
                continue
            if graph_element_id and not any(r.element_id == graph_element_id for r in n.derived_graph_refs):
                continue
            score = self._score(n, q, query)
            if q and score <= 0:
                continue
            hits.append(SearchHit("nugget", n.ref, score, n.title, n.statement, n.scope.key(), n.status.value,
                                  {"canonical_id": n.canonical_id, "version": n.version, "authority": n.authority_type.value,
                                   "knowledge_type": n.knowledge_type.value, "tags": n.tags, "graph_group": n.graph_group}))
        if include_sources and q and filter == "All Knowledge" and not scope:
            for s in self.repo.sources.all():
                st = tokens(s.title) & q
                ver = self.repo.source_versions.get(s.current_version_id or "")
                body = tokens(ver.text[:20000]) & q if ver else set()
                score = len(st) * 1.0 + len(body) * 0.3
                if score > 0:
                    hits.append(SearchHit("source", s.id, score, s.title, (ver.text[:200] if ver else ""), s.scope.key() if s.scope else None,
                                          s.extraction_status.value, {"source_type": s.source_type.value, "authority": s.authority_type.value}))
        hits.sort(key=lambda h: -h.score)
        return hits[:limit]

    @staticmethod
    def _status_ok(n: KnowledgeNuggetVersion, filt: str, status: str | None) -> bool:
        if status and n.status.value != status:
            return False
        if filt == "Current":
            return n.status in _CURRENT
        if filt == "Historical":
            return n.status in _HISTORICAL
        if filt == "Pending":
            return n.status in _PENDING
        if filt == "Conflicting":
            return bool(n.analysis.get("conflict_open")) or n.status == NuggetStatus.CONFLICT
        return True

    @staticmethod
    def _score(n: KnowledgeNuggetVersion, q: set[str], raw: str) -> float:
        if not q:
            return 1.0
        t_title, t_body = tokens(n.title), tokens(n.statement) | tokens(n.normalized_meaning) | set(n.tags)
        exact = 2.0 if raw.lower() in n.statement.lower() else 0.0
        return exact + len(q & t_title) * 1.5 + len(q & t_body) * 1.0 + similarity(raw, n.statement)


def _effective(n: KnowledgeNuggetVersion, when: str) -> bool:
    start = n.effective_from or n.activated_at or n.approved_at
    if not start or start > when:
        return False
    return n.effective_to is None or n.effective_to > when
