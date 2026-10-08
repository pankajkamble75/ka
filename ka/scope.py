"""knowledge-scope (§7–§9, §24): the scope hierarchy, inheritance walking, and the Scope Decision Engine.

The hierarchy itself is registered, not discovered: enterprise-os has structures, domains (substructures)
and instances (pins) but no Parent Domain in code, so KA keeps its own `ScopeRegistry` that the graph
adapter populates (domain → instances from `pinned_by`) and that operators extend with parent domains.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ka.model import KnowledgeNuggetVersion, Scope
from ka.vocab import SCOPE_ORDER, ScopeType, is_broader


@dataclass
class ScopeRegistry:
    """parent[scope.key()] = parent Scope. Roots (structures) have no parent."""
    parents: dict[str, Scope] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)

    def register(self, scope: Scope, parent: Scope | None = None, name: str | None = None) -> None:
        if parent is not None and not is_broader(parent.scope_type, scope.scope_type):
            raise ValueError(f"{parent.key()} cannot be the parent of {scope.key()}")
        self.names[scope.key()] = name or scope.scope_id
        if parent is not None:
            self.parents[scope.key()] = parent
            self.names.setdefault(parent.key(), parent.scope_id)
        else:
            self.names.setdefault(scope.key(), scope.scope_id)

    def parent_of(self, scope: Scope) -> Scope | None:
        return self.parents.get(scope.key())

    def ancestors(self, scope: Scope) -> list[Scope]:
        """Nearest first."""
        out, cur = [], self.parent_of(scope)
        while cur is not None:
            out.append(cur)
            cur = self.parent_of(cur)
        return out

    def children(self, scope: Scope) -> list[Scope]:
        return [Scope(scope_type=ScopeType(k.split(":", 1)[0]), scope_id=k.split(":", 1)[1])
                for k, p in self.parents.items() if p.key() == scope.key()]

    def descendants(self, scope: Scope) -> list[Scope]:
        out: list[Scope] = []
        stack = self.children(scope)
        while stack:
            s = stack.pop()
            out.append(s)
            stack.extend(self.children(s))
        return out

    def instances_under(self, scope: Scope) -> list[Scope]:
        if scope.scope_type == ScopeType.INSTANCE:
            return [scope]
        return [s for s in self.descendants(scope) if s.scope_type == ScopeType.INSTANCE]

    def all_scopes(self) -> list[Scope]:
        keys = set(self.parents) | {p.key() for p in self.parents.values()} | set(self.names)
        return sorted(
            (Scope(scope_type=ScopeType(k.split(":", 1)[0]), scope_id=k.split(":", 1)[1]) for k in keys),
            key=lambda s: (SCOPE_ORDER.index(s.scope_type), s.scope_id),
        )

    def of_type(self, t: ScopeType) -> list[Scope]:
        return [s for s in self.all_scopes() if s.scope_type == t]

    def fill_hierarchy_fields(self, v: KnowledgeNuggetVersion) -> None:
        """Populate structure_id / parent_domain_id / domain_id / instance_id from the registry."""
        chain = [v.scope] + self.ancestors(v.scope)
        for s in chain:
            if s.scope_type == ScopeType.STRUCTURE:
                v.structure_id = v.structure_id or s.scope_id
            elif s.scope_type == ScopeType.PARENT_DOMAIN:
                v.parent_domain_id = v.parent_domain_id or s.scope_id
            elif s.scope_type == ScopeType.DOMAIN:
                v.domain_id = v.domain_id or s.scope_id
            elif s.scope_type == ScopeType.INSTANCE:
                v.instance_id = v.instance_id or s.scope_id


@dataclass
class ScopeDecision:
    scope: Scope
    confidence: float
    rationale: list[str]
    requires_approval: bool = False       # §24: high-impact broadening asks first
    alternatives: list[Scope] = field(default_factory=list)


_INSTANCE_WORDS = re.compile(r"\b(this (store|merchant|restaurant|site|branch|location)|here|our|we|at [A-Z][\w']+)\b")
_GENERAL_WORDS = re.compile(r"\b(all|every|any|always|never|each|regulat\w+|standard|industry|law|must)\b", re.I)


class ScopeDecisionEngine:
    """§24 — apply knowledge at the lowest semantic scope where the statement remains true.

    Inputs weighed, in the spec's order: graph location (where the correction/evidence was raised),
    original nugget scope, the user's wording, referenced evidence scope, inheritance relationships,
    similar nuggets, other-instance patterns. This is a heuristic ranker; the LLM may be asked for a
    recommendation separately but never decides (§33).
    """

    def __init__(self, registry: ScopeRegistry):
        self.registry = registry

    def decide(
        self,
        *,
        statement: str,
        location_scope: Scope | None = None,
        original_scope: Scope | None = None,
        user_scope: Scope | None = None,
        evidence_scopes: Iterable[Scope] = (),
        similar: Iterable[KnowledgeNuggetVersion] = (),
        sibling_instance_matches: int = 0,
        sibling_instance_total: int = 0,
    ) -> ScopeDecision:
        rationale: list[str] = []
        candidates: dict[str, tuple[Scope, float]] = {}

        def vote(scope: Scope | None, weight: float, why: str) -> None:
            if scope is None:
                return
            prev = candidates.get(scope.key(), (scope, 0.0))[1]
            candidates[scope.key()] = (scope, prev + weight)
            rationale.append(f"{why} → {scope.key()} (+{weight:.2f})")

        # Lowest valid scope is the default: the location the statement was raised at.
        vote(location_scope, 1.0, "raised at graph location")
        vote(original_scope, 0.6, "original nugget scope")
        vote(user_scope, 0.9, "user selected scope")
        ev_scopes = list(evidence_scopes)
        for s in ev_scopes:
            vote(s, 0.5, "evidence is scoped")
        for n in similar:
            vote(n.scope, 0.2, f"similar nugget {n.ref}")

        # Wording: "all merchants must…" argues for a broader scope than "our store…".
        if _GENERAL_WORDS.search(statement) and location_scope is not None:
            parent = self.registry.parent_of(location_scope)
            if parent:
                vote(parent, 0.4, "general wording in statement")
        if _INSTANCE_WORDS.search(statement) and location_scope is not None:
            vote(location_scope, 0.4, "instance-specific wording in statement")

        # Pattern across sibling instances (§25 feeds §24).
        if sibling_instance_total >= 3 and sibling_instance_matches / sibling_instance_total >= 0.75 and location_scope:
            parent = self.registry.parent_of(location_scope)
            if parent:
                vote(parent, 0.5, f"{sibling_instance_matches}/{sibling_instance_total} sibling instances share it")

        if not candidates:
            fallback = location_scope or original_scope or user_scope or Scope(scope_type=ScopeType.INSTANCE, scope_id="unknown")
            return ScopeDecision(scope=fallback, confidence=0.2, rationale=["no signals; defaulted to lowest scope"])

        ranked = sorted(candidates.values(), key=lambda t: (-t[1], SCOPE_ORDER.index(t[0].scope_type) * -1))
        best, score = ranked[0]
        total = sum(s for _, s in ranked)
        confidence = round(score / total, 2) if total else 0.0

        requires_approval = False
        baseline = location_scope or original_scope
        if baseline is not None and is_broader(best.scope_type, baseline.scope_type):
            affected = len(self.registry.instances_under(best))
            if affected >= 2:
                requires_approval = True
                rationale.append(f"broadening to {best.key()} affects {affected} instances — approval required (§24)")

        return ScopeDecision(
            scope=best, confidence=confidence, rationale=rationale, requires_approval=requires_approval,
            alternatives=[s for s, _ in ranked[1:4]],
        )
