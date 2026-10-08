"""graph-impact (§20, §21): dependency-driven impact analysis for an approved knowledge change.

For the activated version: find graph elements that depend on the superseded version(s) (or on the same
canonical id), walk the scope's descendants, classify each descendant element INHERITED / OVERRIDDEN /
LOCALLY_EXTENDED / LOCALLY_REMOVED / CONFLICTING, and say per descendant whether it gets a proposed update
or review only. Never blindly propagate across overrides (§9).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ka.graph_adapter import GraphAdapter, GraphElement
from ka.lineage import LineageService
from ka.model import InheritanceEffect, KnowledgeNuggetVersion, Scope
from ka.repository import Repository
from ka.scope import ScopeRegistry
from ka.vocab import GraphElementKind, InheritanceState, KnowledgeType, ScopeType


@dataclass
class AffectedElement:
    element: GraphElement
    inheritance_state: InheritanceState
    via_nugget_ref: str          # which version the element currently depends on
    action: str                  # proposed update | review only | create


@dataclass
class ImpactReport:
    nugget_ref: str
    affected: list[AffectedElement] = field(default_factory=list)
    descendants: list[InheritanceEffect] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    is_new_knowledge: bool = False
    target_scope: Scope | None = None

    def summary(self) -> dict[str, Any]:
        return {"nugget_ref": self.nugget_ref, "is_new_knowledge": self.is_new_knowledge, **self.counts,
                "descendants": [d.model_dump(mode="json") for d in self.descendants]}


# Which graph element kind a new nugget compiles to (§19: knowledge → graph builder → graph).
KIND_FOR_KNOWLEDGE: dict[KnowledgeType, GraphElementKind] = {
    KnowledgeType.RULE: GraphElementKind.RULE, KnowledgeType.POLICY: GraphElementKind.RULE,
    KnowledgeType.CONSTRAINT: GraphElementKind.RULE, KnowledgeType.CONDITION: GraphElementKind.RULE,
    KnowledgeType.PROCESS_STEP: GraphElementKind.STEP, KnowledgeType.STATE_TRANSITION: GraphElementKind.STATE_TRANSITION,
    KnowledgeType.RELATIONSHIP: GraphElementKind.EDGE, KnowledgeType.CONCEPT: GraphElementKind.CONCEPT,
    KnowledgeType.DEFINITION: GraphElementKind.CONCEPT, KnowledgeType.DOMAIN_SEMANTICS: GraphElementKind.NODE,
    KnowledgeType.INSTANCE_SEMANTICS: GraphElementKind.NODE, KnowledgeType.FACT: GraphElementKind.NODE,
}


class GraphImpactService:
    def __init__(self, repo: Repository, adapter: GraphAdapter, lineage: LineageService, registry: ScopeRegistry):
        self.repo, self.adapter, self.lineage, self.registry = repo, adapter, lineage, registry

    def analyze(self, v: KnowledgeNuggetVersion) -> ImpactReport:
        report = ImpactReport(nugget_ref=v.ref, target_scope=v.scope)
        prior_refs = [x.ref for x in self.repo.versions_of(v.canonical_id) if x.ref != v.ref]
        deps = [d for ref in prior_refs for d in self.lineage.where_used(ref)]
        # also elements already pointing at this version (re-analysis)
        deps += self.lineage.where_used(v.ref)

        seen: set[tuple[str, str]] = set()
        for d in deps:
            if (d.graph_id, d.element_id) in seen:
                continue
            seen.add((d.graph_id, d.element_id))
            el = self.adapter.get_graph_element(d.graph_id, d.element_id)
            if el is None:
                continue
            state = self.adapter.calculate_inheritance(el.scope).get(el.element_id, InheritanceState.LOCALLY_EXTENDED)
            own = el.scope.key() == v.scope.key()
            if own or state in {InheritanceState.INHERITED, InheritanceState.LOCALLY_EXTENDED}:
                action = "proposed update"
            else:
                action = "review only"
            report.affected.append(AffectedElement(el, state if not own else InheritanceState.INHERITED, d.nugget_ref, action))

        report.is_new_knowledge = not report.affected
        # Descendant scopes (§8, §21): inherited vs overridden per descendant.
        descendants = self.registry.descendants(v.scope) or self.adapter.find_descendants(v.scope)
        own_elements = [a.element for a in report.affected if a.element.scope.key() == v.scope.key()]
        for ds in descendants:
            states = self.adapter.calculate_inheritance(ds)
            elems: list[str] = []
            worst = InheritanceState.INHERITED
            for oe in own_elements:
                for eid, st in states.items():
                    if eid.endswith("/" + oe.element_id) or eid == oe.element_id:
                        elems.append(eid)
                        if st == InheritanceState.OVERRIDDEN:
                            worst = InheritanceState.OVERRIDDEN
                        elif st == InheritanceState.LOCALLY_REMOVED and worst != InheritanceState.OVERRIDDEN:
                            worst = InheritanceState.LOCALLY_REMOVED
            if report.is_new_knowledge:
                worst = InheritanceState.INHERITED
            action = "proposed update" if worst == InheritanceState.INHERITED else "review only"
            report.descendants.append(InheritanceEffect(scope=ds, inheritance_state=worst, action=action, element_ids=elems,
                                                        note="override preserved (§9)" if worst == InheritanceState.OVERRIDDEN else ""))

        report.counts = self._counts(v, report, descendants)
        return report

    def _counts(self, v: KnowledgeNuggetVersion, report: ImpactReport, descendants: list[Scope]) -> dict[str, int]:
        c = Counter()
        c["affected_structure_elements"] = sum(1 for a in report.affected if a.element.scope.scope_type == ScopeType.STRUCTURE)
        c["affected_parent_domains"] = len({s.scope_id for s in descendants if s.scope_type == ScopeType.PARENT_DOMAIN}) + (
            1 if v.scope_type == ScopeType.PARENT_DOMAIN else 0)
        c["affected_domains"] = len({s.scope_id for s in descendants if s.scope_type == ScopeType.DOMAIN}) + (1 if v.scope_type == ScopeType.DOMAIN else 0)
        c["affected_instances"] = len({s.scope_id for s in descendants if s.scope_type == ScopeType.INSTANCE}) + (1 if v.scope_type == ScopeType.INSTANCE else 0)
        kinds = Counter(a.element.kind for a in report.affected)
        c["affected_graph_nodes"] = sum(n for k, n in kinds.items() if k not in {GraphElementKind.EDGE})
        c["affected_graph_edges"] = kinds.get(GraphElementKind.EDGE, 0)
        c["affected_rules"] = kinds.get(GraphElementKind.RULE, 0)
        c["affected_processes"] = kinds.get(GraphElementKind.PROCESS, 0) + kinds.get(GraphElementKind.STEP, 0)
        c["affected_applications"] = kinds.get(GraphElementKind.APPLICATION, 0)
        c["affected_computations"] = kinds.get(GraphElementKind.COMPUTATION, 0)
        c["inherited_descendants"] = sum(1 for d in report.descendants if d.inheritance_state == InheritanceState.INHERITED)
        c["overridden_descendants"] = sum(1 for d in report.descendants if d.inheritance_state == InheritanceState.OVERRIDDEN)
        return dict(c)
