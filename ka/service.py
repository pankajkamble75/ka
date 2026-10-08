"""The composition root: one `KnowledgeAcquisition` object owns the repository, the event bus and every
service of §36, wired so that `knowledge.approved` → impact analysis → Graph Change Proposal happens by
event (§38), not by the governance service knowing about graphs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ka import config
from ka.audit import Auditor
from ka.conflict import ConflictDetector
from ka.corrections import CorrectionService
from ka.events import EventBus
from ka.extraction import CandidateExtractor
from ka.binding import Binder
from ka.governance import GovernanceService
from ka.grammar import GrammarRegistry
from ka.identity import SubjectRegistry
from ka.graph_adapter import EnterpriseOSGraphAdapter, GraphAdapter, InMemoryGraphAdapter
from ka.graph_change import GraphChangeService
from ka.graph_impact import GraphImpactService
from ka.ingestion import IngestionService
from ka.lineage import LineageService
from ka.llm import LLMProvider, select_provider
from ka.model import Scope
from ka.promotion import PromotionService
from ka.repository import Repository
from ka.research import ResearchOrchestrator
from ka.runtime_guard import RuntimeGuard
from ka.scope import ScopeRegistry
from ka.search import SearchService
from ka.versioning import VersioningService
from ka.vocab import NuggetStatus, ScopeType


class KnowledgeAcquisition:
    def __init__(self, storage_root: Path | None = None, *, provider: LLMProvider | None = None,
                 adapter: GraphAdapter | None = None, registry: ScopeRegistry | None = None,
                 auto_propose_graph_changes: bool = True, auto_approve_low_impact: bool = False):
        self.repo = Repository(storage_root)
        self.bus = EventBus(sink=self.repo.append_event)
        self.auditor = Auditor(self.repo)
        self.provider = provider if provider is not None else select_provider()
        self.registry = registry or ScopeRegistry()
        self.adapter = adapter if adapter is not None else self._default_adapter()
        self.versioning = VersioningService(self.repo)
        self.lineage = LineageService(self.repo)
        self.ingestion = IngestionService(self.repo, self.bus, self.auditor)
        # [block plan-03]
        self.grammar = GrammarRegistry.from_config(self.repo.root)
        self.subjects = SubjectRegistry(self.repo)
        self.binder = Binder(self.grammar, self.repo)
        # [/block plan-03]
        self.governance = GovernanceService(self.repo, self.bus, self.auditor, self.registry, self.versioning,
                                            ConflictDetector(self.provider), CandidateExtractor(self.provider),
                                            binder=self.binder, subjects=self.subjects)
        self.impact = GraphImpactService(self.repo, self.adapter, self.lineage, self.registry)
        self.graph_change = GraphChangeService(self.repo, self.bus, self.auditor, self.adapter, self.impact, self.lineage)
        self.graph_change.auto_approve_low_impact = auto_approve_low_impact
        self.research = ResearchOrchestrator(self.repo, self.bus, self.auditor, self.ingestion, self.governance, self.registry, self.provider)
        self.corrections = CorrectionService(self.repo, self.bus, self.auditor, self.governance, self.lineage, self.adapter,
                                             self.registry, self.ingestion)
        self.promotion = PromotionService(self.repo, self.bus, self.auditor, self.registry, self.governance)
        self.search = SearchService(self.repo)
        self.runtime_guard = RuntimeGuard(self.repo, self.bus, self.research)
        self._restore_registry()
        if auto_propose_graph_changes:
            self.bus.subscribe("knowledge.approved", self._on_approved)

    # ---- wiring --------------------------------------------------------------------------------------

    def _default_adapter(self) -> GraphAdapter:
        if config.get("KA_ENTERPRISE_OS_ROOT") and EnterpriseOSGraphAdapter.available():
            return EnterpriseOSGraphAdapter()
        return InMemoryGraphAdapter(path=self.repo.root / "graph_shadow.json")

    def _on_approved(self, ev: dict[str, Any]) -> None:
        v = self.repo.version(ev["ref"])
        if v is not None:
            self.graph_change.propose_for(v)

    # ---- scope registry persistence (the registry is configuration, kept beside the data) ------------

    def register_scope(self, scope: Scope, parent: Scope | None = None, name: str | None = None) -> None:
        self.registry.register(scope, parent, name)
        if isinstance(self.adapter, InMemoryGraphAdapter):
            self.adapter.add_graph(scope, parent=parent if parent and parent.key() in self.adapter._graph_of else None)
        self._save_registry()

    def _save_registry(self) -> None:
        from ka.json_io import write_json
        write_json(self.repo.root / "scopes.json", {
            "parents": {k: v.model_dump() for k, v in self.registry.parents.items()},
            "names": self.registry.names,
        })

    def _restore_registry(self) -> None:
        from ka.json_io import read_json
        p = self.repo.root / "scopes.json"
        if p.exists() and not self.registry.parents and not self.registry.names:
            data = read_json(p)
            self.registry.names = dict(data.get("names", {}))
            for k, v in data.get("parents", {}).items():
                self.registry.parents[k] = Scope(**v)
            if isinstance(self.adapter, InMemoryGraphAdapter):
                for s in self.registry.all_scopes():
                    self.adapter.add_graph(s, parent=self.registry.parent_of(s))

    def sync_scopes_from_graph(self) -> int:
        """Populate the registry from the enterprise-os store: every substructure is a DOMAIN, every
        instance pinned to it is an INSTANCE child. Parent domains stay operator-defined."""
        if not isinstance(self.adapter, EnterpriseOSGraphAdapter):
            return 0
        n = 0
        structure = Scope(scope_type=ScopeType.STRUCTURE, scope_id="universal-typed@1")
        self.registry.register(structure)
        for sid in self.adapter.store.list_substructures():
            d = Scope(scope_type=ScopeType.DOMAIN, scope_id=sid)
            self.registry.register(d, structure)
            n += 1
            for iid in self.adapter.store.pinned_by(sid):
                self.registry.register(Scope(scope_type=ScopeType.INSTANCE, scope_id=iid), d)
                n += 1
        self._save_registry()
        return n

    # ---- one-step "apply to scope" for the console (§11 decision + §24 scope) --------------------------

    def apply_nugget(self, ref: str, *, scope: Scope | None, by: str, reason: str = "", widen_visibility: bool = False) -> dict[str, Any]:
        """Approve a candidate at its own scope, or re-scope it first (CHANGE_SCOPE) and approve the result.
        Still one governance decision per step — this is a convenience, not a bypass."""
        from ka.governance import GovernanceError
        from ka.vocab import DecisionOutcome
        v = self.repo.require_version(ref)
        steps: list[dict[str, Any]] = []
        if scope is not None and scope.key() != v.scope.key():
            d = self.governance.decide(ref, DecisionOutcome.CHANGE_SCOPE, by=by, reason=reason or f"applied to {scope.key()}", new_scope=scope,
                                       widen_visibility=widen_visibility)
            steps.append({"decision": d.outcome.value, "from": ref, "to": d.resulting_refs[0]})
            v = self.repo.require_version(d.resulting_refs[0])
        if v.status == NuggetStatus.REJECTED:
            return {"nugget": _nugget_row(v), "steps": steps, "applied": False,
                    "note": v.analysis.get("auto_resolved") or "rejected by governance"}
        if v.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.ANALYZED}:
            try:
                d = self.governance.decide(v.ref, DecisionOutcome.APPROVE, by=by, reason=reason or "applied from console")
            except GovernanceError as e:
                return {"nugget": _nugget_row(v), "steps": steps, "applied": False, "note": str(e)}
            steps.append({"decision": d.outcome.value, "ref": v.ref})
        v = self.repo.require_version(v.ref)
        proposals = [p.model_dump(mode="json", include={"id", "status", "affected_element_ids", "requires_approval"})
                     for p in self.repo.proposals.where(lambda p: v.ref in p.knowledge_change_ids)]
        return {"nugget": _nugget_row(v), "steps": steps, "applied": v.status == NuggetStatus.ACTIVE, "proposals": proposals,
                "note": "" if v.status == NuggetStatus.ACTIVE else f"status {v.status.value}"}

    def engine_status(self) -> dict[str, Any]:
        """§29/§32 rolled up for the Dashboard tab."""
        from collections import Counter
        nuggets = self.repo.nuggets.all()
        by_status = Counter(n.status.value for n in nuggets)
        by_scope_type = Counter(n.scope_type.value for n in nuggets if n.status == NuggetStatus.ACTIVE)
        by_channel = Counter(n.channel.value for n in nuggets)
        by_authority = Counter(n.authority_type.value for n in nuggets if n.status == NuggetStatus.ACTIVE)
        proposals = Counter(p.status.value for p in self.repo.proposals.all())
        missions = Counter(m.status.value for m in self.repo.missions.all())
        sources = self.repo.sources.all()
        att = self.needs_attention()
        return {
            "sources": {"total": len(sources), "by_type": Counter(s.source_type.value for s in sources),
                        "extraction": Counter(s.extraction_status.value for s in sources)},
            "nuggets": {"total": len(nuggets), "canonical": len(self.repo.canonical_ids()), "by_status": by_status,
                        "active_by_scope_type": by_scope_type, "by_channel": by_channel, "active_by_authority": by_authority},
            "graph": {"proposals_by_status": proposals, "dependencies": len(self.repo.dependencies.where(lambda d: d.active)),
                      "elements_with_lineage": len({(d.graph_id, d.element_id) for d in self.repo.dependencies.where(lambda d: d.active)})},
            "research": {"missions_by_status": missions, "runs": len(self.repo.runs), "cost_usd": round(sum(r.cost for r in self.repo.runs), 4)},
            "corrections": {"total": len(self.repo.corrections), "pending": len(self.corrections.pending())},
            "queues": {k: len(v) for k, v in att.items()},
            "attention": att,
            "scopes": [{"key": s.key(), "name": self.registry.names.get(s.key(), s.scope_id), "scope_type": s.scope_type.value,
                        "scope_id": s.scope_id, "active": len(self.repo.active_nuggets(s)),
                        "pending": len(self.repo.nuggets_in_scope(s, [NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT]))}
                       for s in self.registry.all_scopes()],
            "recent_events": self.repo.events()[-25:][::-1],
            "recent_audit": [a.model_dump(mode="json") for a in self.repo.audit()[-25:][::-1]],
            "provider": getattr(self.provider, "name", "?"), "adapter": type(self.adapter).__name__, "storage": str(self.repo.root),
            "grammar": self.grammar.descriptor() | {"bindings": len(self.repo.bindings), "subjects": len(self.repo.subjects)},
        }

    # ---- "Why?" (§15, §47) ----------------------------------------------------------------------------

    def explain_element(self, graph_id: str, element_id: str) -> dict[str, Any]:
        """Registry first; then the element's own props.knowledge_lineage, for copies realized outside KA."""
        out = self.lineage.explain_element(graph_id, element_id)
        seen = {c["ref"] for c in out["knowledge_lineage"]}
        for ln in self.adapter.get_graph_lineage(graph_id, element_id):
            ref = f"{ln.get('nugget_id')}:v{ln.get('version')}"
            v = self.repo.version(ref)
            if v is not None and ref not in seen:
                out["knowledge_lineage"].append(self.lineage.trace(v, graph_change_id=ln.get("graph_change_id")))
                seen.add(ref)
        out["explained"] = bool(out["knowledge_lineage"])
        return out

    # ---- dashboards (§29, §30, §32) -------------------------------------------------------------------

    def needs_attention(self) -> dict[str, list[dict[str, Any]]]:
        pending = self.repo.nuggets_by_status(NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT)
        conflicts = [n for n in pending if n.analysis.get("conflict_open") or n.status == NuggetStatus.CONFLICT]
        proposed = [n for n in pending if n.supersedes or n.correction_refs or n.channel.value != "CONTENT"]
        return {
            "conflicts": [_nugget_row(n) for n in conflicts],
            "pending_governance": [_nugget_row(n) for n in pending if n not in conflicts],
            "proposed_changes": [_nugget_row(n) for n in proposed],
            "graph_impact": [p.model_dump(mode="json", include={"id", "status", "knowledge_change_ids", "affected_element_ids", "requires_approval", "created_at"})
                             for p in self.graph_change.awaiting_propagation()],
            "failed_propagation": [p.model_dump(mode="json", include={"id", "status", "knowledge_change_ids", "validation_results", "created_at"})
                                   for p in self.graph_change.failed()],
            "promotions": [p.model_dump(mode="json") for p in self.repo.promotions.where(lambda p: p.status == "PROPOSED")],
            "acquisition_requests": [r.model_dump(mode="json") for r in self.runtime_guard.open_requests()],
        }

    def domain_dashboard(self, scope: Scope) -> dict[str, Any]:
        in_scope = self.repo.nuggets_in_scope(scope)
        active = [n for n in in_scope if n.status == NuggetStatus.ACTIVE]
        pending = [n for n in in_scope if n.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT}]
        recent = sorted(in_scope, key=lambda n: n.approved_at or n.created_at, reverse=True)[:10]
        groups: dict[str, list[dict]] = {}
        for n in active:
            groups.setdefault(n.graph_group or "Ungrouped", []).append(_nugget_row(n))
        deps = [d for n in active for d in self.lineage.where_used(n.ref)]
        return {
            "scope": scope.model_dump(), "name": self.registry.names.get(scope.key(), scope.scope_id),
            "active_nuggets": len(active), "pending_review": len(pending),
            "conflicts": sum(1 for n in pending if n.analysis.get("conflict_open")),
            "recently_changed": [_nugget_row(n) for n in recent],
            "research_missions": [m.model_dump(mode="json", include={"mission_id", "objective", "status", "created_at"}) for m in
                                  self.repo.missions.where(lambda m: m.scope_type == scope.scope_type and m.scope_id == scope.scope_id)],
            "affected_graph_elements": len({(d.graph_id, d.element_id) for d in deps}),
            "instances_using": [s.model_dump() for s in self.registry.instances_under(scope)] if scope.scope_type != ScopeType.INSTANCE else [],
            "knowledge_by_graph_group": groups,
            "sources": len(self.repo.sources.where(lambda s: s.scope is not None and s.scope.key() == scope.key())),
        }

    def instance_dashboard(self, scope: Scope) -> dict[str, Any]:
        states = self.promotion.instance_states(scope)
        base = self.domain_dashboard(scope)
        base.update({k: [_nugget_row(n) for n in v] for k, v in states.items()})
        base["counts"] = {k: len(v) for k, v in states.items()}
        base["pending_corrections"] = [c.model_dump(mode="json") for c in self.corrections.pending(scope)]
        return base

    def nugget_detail(self, ref: str) -> dict[str, Any]:
        v = self.repo.require_version(ref)
        history = self.repo.versions_of(v.canonical_id)
        inherited_value = None
        ancestors = {a.key() for a in self.registry.ancestors(v.scope)}
        best_rank = 99
        for r in self.repo.relationships_for(v.ref):
            other = self.repo.version(r.to_ref if r.from_ref == v.ref else r.from_ref)
            if other is None or other.scope.key() not in ancestors:
                continue
            # prefer the ACTIVE ancestor nugget this version specializes / supersedes; never a rejected candidate
            rank = (0 if other.status == NuggetStatus.ACTIVE else 2) + (0 if r.from_ref == v.ref else 1)
            if other.status in {NuggetStatus.REJECTED, NuggetStatus.ARCHIVED}:
                continue
            if rank < best_rank:
                best_rank = rank
                inherited_value = {"scope": other.scope.key(), "ref": other.ref, "statement": other.statement, "status": other.status.value}
        used_by_descendants = [d.model_dump(mode="json") for d in self.lineage.where_used(v.ref) if d.scope.key() != v.scope.key()]
        return {
            "nugget": v.model_dump(mode="json"), "ref": v.ref,
            "version_history": [{"ref": h.ref, "version": h.version, "status": h.status.value, "statement": h.statement,
                                 "approved_at": h.approved_at, "approved_by": h.approved_by} for h in history],
            "sources": [s.model_dump(mode="json") for s in self.repo.sources_for(v)],
            "evidence": [e.model_dump(mode="json") for e in self.repo.evidence_for(v)],
            "relationships": [{**r.model_dump(mode="json"), "other": (r.to_ref if r.from_ref == v.ref else r.from_ref)}
                              for r in self.repo.relationships_for(v.ref)],
            "conflicts": [f for f in v.analysis.get("findings", []) if f["relationship"] == "CONTRADICTS"],
            "governance": [d.model_dump(mode="json") for d in self.repo.decisions.where(lambda d: d.subject_ref == v.ref or v.ref in d.related_refs or v.ref in d.resulting_refs)],
            "lineage": self.lineage.trace(v),
            "graph_usage": [d.model_dump(mode="json") for d in self.lineage.where_used(v.ref)],
            "graph_changes": [p.model_dump(mode="json", include={"id", "status", "affected_element_ids", "created_at", "applied_at"})
                              for p in self.repo.proposals.where(lambda p: v.ref in p.knowledge_change_ids)],
            "inherited_value": inherited_value, "used_by_descendants": used_by_descendants,
            "audit": [a.model_dump(mode="json") for a in self.auditor.for_object(v.ref)],
            # plan-03 (block is the wiring in __init__)
            "assertion": {"subject": v.subject.model_dump() if v.subject else None, "predicate": v.predicate,
                          "object": v.object.model_dump() if v.object else None},
            "binding": (b.model_dump(mode="json") if (b := self.repo.binding_for(v.ref)) else None),
            "bindings_history": [b.model_dump(mode="json") for b in self.repo.bindings_of(v.ref)],
            "subject_record": (r.model_dump(mode="json") if v.subject and (r := self.repo.subjects.get(v.subject.canonical_key)) else None),
            "grammar": self.grammar.versions() | {"stale": self.grammar.is_stale(), "loaded": self.grammar.loaded},
        }


def _nugget_row(n) -> dict[str, Any]:
    return {"ref": n.ref, "canonical_id": n.canonical_id, "version": n.version, "title": n.title, "statement": n.statement,
            "status": n.status.value, "scope": n.scope.key(), "authority": n.authority_type.value, "confidence": n.confidence,
            "knowledge_type": n.knowledge_type.value, "channel": n.channel.value, "graph_group": n.graph_group,
            "created_at": n.created_at, "approved_at": n.approved_at, "conflict_open": bool(n.analysis.get("conflict_open")),
            "subject": n.subject.canonical_key if n.subject else None, "predicate": n.predicate,
            "suggested_resolution": next((f.get("suggested_resolution") for f in n.analysis.get("findings", []) if f["relationship"] == "CONTRADICTS"), None)}
