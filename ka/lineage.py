"""knowledge-lineage (§15, §16, §40): the graph dependency registry, indexed both ways.

  Graph → Why does this exist?        explain_element(graph_id, element_id)
  Knowledge → Where is this used?     where_used(nugget_ref)

Full chain (§15): Source → Research/Ingestion/Correction → Candidate → Decision → Version → Graph Change →
Element → Scope. `trace()` assembles it for a version; `explain_element` walks it backwards.
"""
from __future__ import annotations

from typing import Any

from ka.model import GraphDependency, GraphRef, KnowledgeNuggetVersion, Scope
from ka.repository import Repository
from ka.vocab import GraphElementKind, InheritanceState


class LineageService:
    def __init__(self, repo: Repository):
        self.repo = repo

    # ---- registry writes ------------------------------------------------------------------------

    def register(self, *, version: KnowledgeNuggetVersion, graph_id: str, element_id: str, element_kind: GraphElementKind,
                 scope: Scope, graph_change_id: str | None, inheritance_state: InheritanceState = InheritanceState.INHERITED) -> GraphDependency:
        # One active dependency per (element, nugget ref).
        for d in self.repo.dependencies_for_element(graph_id, element_id):
            if d.nugget_ref == version.ref:
                return d
        dep = GraphDependency(graph_id=graph_id, element_id=element_id, element_kind=element_kind, scope=scope,
                              nugget_ref=version.ref, governance_decision_id=version.governance_decision_id,
                              graph_change_id=graph_change_id, inheritance_state=inheritance_state)
        self.repo.dependencies.put(dep)
        ref = GraphRef(graph_id=graph_id, element_id=element_id, element_kind=element_kind, graph_change_id=graph_change_id)
        if ref not in version.derived_graph_refs:
            version.derived_graph_refs.append(ref)
        if graph_change_id and graph_change_id not in version.graph_change_refs:
            version.graph_change_refs.append(graph_change_id)
        self.repo.nuggets.put(version)
        return dep

    def retire(self, *, nugget_ref: str, graph_id: str | None = None, element_id: str | None = None) -> int:
        n = 0
        for d in self.repo.dependencies_for_nugget(nugget_ref):
            if graph_id and d.graph_id != graph_id:
                continue
            if element_id and d.element_id != element_id:
                continue
            d.active = False
            self.repo.dependencies.put(d)
            n += 1
        return n

    def set_inheritance_state(self, graph_id: str, element_id: str, state: InheritanceState) -> None:
        for d in self.repo.dependencies_for_element(graph_id, element_id):
            d.inheritance_state = state
            self.repo.dependencies.put(d)

    # ---- the two questions -------------------------------------------------------------------------

    def where_used(self, nugget_ref: str) -> list[GraphDependency]:
        return self.repo.dependencies_for_nugget(nugget_ref)

    def where_used_canonical(self, canonical_id: str) -> list[GraphDependency]:
        refs = {v.ref for v in self.repo.versions_of(canonical_id)}
        return self.repo.dependencies.where(lambda d: d.active and d.nugget_ref in refs)

    def explain_element(self, graph_id: str, element_id: str) -> dict[str, Any]:
        """Graph → Why does this exist? Returns the lineage chain for the element, newest version first."""
        deps = self.repo.dependencies_for_element(graph_id, element_id)
        chain = []
        for d in deps:
            v = self.repo.version(d.nugget_ref)
            if v is None:
                continue
            chain.append(self.trace(v, graph_change_id=d.graph_change_id, inheritance_state=d.inheritance_state))
        return {"graph_id": graph_id, "element_id": element_id, "knowledge_lineage": chain,
                "explained": bool(chain)}

    def trace(self, v: KnowledgeNuggetVersion, *, graph_change_id: str | None = None,
              inheritance_state: InheritanceState | None = None) -> dict[str, Any]:
        decision = self.repo.decisions.get(v.governance_decision_id) if v.governance_decision_id else None
        sources = [{"source_id": s.id, "title": s.title, "type": s.source_type.value, "authority": s.authority_type.value,
                    "location": s.original_location} for s in self.repo.sources_for(v)]
        evidence = [{"evidence_id": e.id, "source_id": e.source_id, "locator": e.locator, "excerpt": e.excerpt[:280]}
                    for e in self.repo.evidence_for(v)]
        runs = [r.model_dump(include={"run_id", "mission_id", "agent_id", "model", "status"}) for r in
                (self.repo.runs.get(i) for i in v.research_run_refs) if r]
        corrections = [c.model_dump(include={"id", "submitted_by", "what_is_incorrect", "correct_value", "status"}) for c in
                       (self.repo.corrections.get(i) for i in v.correction_refs) if c]
        return {
            "nugget_id": v.canonical_id, "version": v.version, "ref": v.ref, "title": v.title, "statement": v.statement,
            "status": v.status.value, "scope": v.scope.key(), "channel": v.channel.value,
            "sources": sources, "evidence": evidence, "research_runs": runs, "corrections": corrections,
            "governance_decision": decision.model_dump(include={"id", "outcome", "decided_by", "decided_at", "reason"}) if decision else None,
            "supersedes": v.supersedes, "superseded_by": v.superseded_by,
            "graph_change_id": graph_change_id, "graph_change_refs": v.graph_change_refs,
            "materialized_as": [r.model_dump() for r in v.derived_graph_refs],
            "inheritance_state": inheritance_state.value if inheritance_state else v.inheritance_state,
            "inherited_from": v.inherited_from,
        }

    @staticmethod
    def graph_metadata(v: KnowledgeNuggetVersion, graph_change_id: str | None) -> dict[str, Any]:
        """§40 — the lineage entry written on a graph element: a reference, never the nugget itself."""
        return {"nugget_id": v.canonical_id, "version": v.version, "governance_decision_id": v.governance_decision_id,
                "graph_change_id": graph_change_id}
