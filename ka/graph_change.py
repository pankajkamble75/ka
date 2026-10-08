"""graph-change (§22, §26, §39): Graph Change Proposals — propose, validate, approve, apply, rollback.

Production graphs are never mutated straight after governance. Activation produces a PROPOSED change;
validation checks every element change carries knowledge lineage (Invariant 2) and that the adapter
accepts it; low-impact proposals may be auto-approved by policy, high-impact ones wait for a person.
Applying registers the new dependencies (Invariant 4/5) and retires the old; every application is an
execution record so it can be rolled back by version (§26).
"""
from __future__ import annotations

import re
from typing import Any

from ka import config
from ka.audit import Auditor
from ka.events import EventBus
from ka.graph_adapter import LINEAGE_KEY, GraphAdapter, GraphValidationError
from ka.graph_impact import KIND_FOR_KNOWLEDGE, GraphImpactService, ImpactReport
from ka.lineage import LineageService
from ka.model import ElementChange, GraphChangeExecution, GraphChangeProposal, KnowledgeNuggetVersion
from ka.repository import Repository
from ka.timeutil import now_iso
from ka.vocab import GraphElementKind, InheritanceState, ProposalStatus


class ChangeError(RuntimeError):
    pass


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:48]


def _value_props(v: KnowledgeNuggetVersion) -> dict[str, Any]:
    """What a compiled element carries from its nugget: the statement, and any numeric threshold."""
    props: dict[str, Any] = {"statement": v.statement, "knowledge_type": v.knowledge_type.value}
    nums = re.findall(r"\$?\d[\d,]*(?:\.\d+)?%?", v.statement)
    if nums:
        props["value"] = nums[0]
    return props


class GraphChangeService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, adapter: GraphAdapter,
                 impact: GraphImpactService, lineage: LineageService):
        self.repo, self.bus, self.auditor, self.adapter, self.impact, self.lineage = repo, bus, auditor, adapter, impact, lineage
        self.auto_approve_low_impact = False

    # ---------------------------------------------------------------- propose (§20 steps 1–5)

    def propose_for(self, v: KnowledgeNuggetVersion, *, by: str = "ka.graph_change") -> GraphChangeProposal:
        report = self.impact.analyze(v)
        self.bus.emit("graph.impact.detected", ref=v.ref, affected_instances=report.counts.get("affected_instances", 0))
        changes = self._changes_from(v, report)
        prop = GraphChangeProposal(
            knowledge_change_ids=[v.ref], affected_graph_ids=sorted({c.graph_id for c in changes}),
            affected_element_ids=sorted({c.element_id for c in changes}),
            before_state={f"{c.graph_id}/{c.element_id}": c.before for c in changes},
            proposed_after_state={f"{c.graph_id}/{c.element_id}": c.after for c in changes},
            changes=changes, reason=v.change_reason or f"governed knowledge {v.ref} activated",
            impact_summary=report.summary(), inheritance_effects=report.descendants, created_by=by,
        )
        high = config.get("KA_HIGH_IMPACT_INSTANCES")
        prop.requires_approval = (report.counts.get("affected_instances", 0) >= high
                                  or report.counts.get("overridden_descendants", 0) > 0)
        self.repo.proposals.put(prop)
        self.bus.emit("graph.change.proposed", proposal_id=prop.id, ref=v.ref)
        self.auditor.record(who=by, what="graph.change.proposed", why=prop.reason, scope=v.scope, affected=[prop.id, v.ref])
        self.validate(prop.id)
        if self.auto_approve_low_impact and not prop.requires_approval and prop.status == ProposalStatus.READY:
            self.approve(prop.id, by="ka.policy.auto", reason="low impact; auto-approved by policy")
            self.apply(prop.id, by="ka.policy.auto")
        return self.repo.proposals.require(prop.id)

    def _changes_from(self, v: KnowledgeNuggetVersion, report: ImpactReport) -> list[ElementChange]:
        lineage_entry = self.lineage.graph_metadata(v, graph_change_id=None)
        changes: dict[tuple[str, str], ElementChange] = {}

        def update(el, *, kind=None) -> None:
            key = (el.graph_id, el.element_id)
            if key in changes:
                return
            props = {**el.props, **_value_props(v), LINEAGE_KEY: _merged_lineage(el.props, lineage_entry, v)}
            changes[key] = ElementChange(graph_id=el.graph_id, element_id=el.element_id, element_kind=kind or el.kind, operation="update",
                                         before=el.model_dump(include={"name", "description", "props"}),
                                         after={"name": v.title, "description": v.statement, "props": props})

        if report.is_new_knowledge:
            # An instance nugget that specializes / supersedes a parent-scope nugget is an OVERRIDE of the
            # realized copy of that parent's element — update the copy, don't add a second rule (§9).
            override_targets = self._override_targets(v)
            for el in override_targets:
                update(el)
            if not override_targets:
                kind = KIND_FOR_KNOWLEDGE.get(v.knowledge_type, GraphElementKind.NODE)
                prefix = {"rule": "r", "step": "p", "process": "p", "concept": "e", "edge": "rel", "state_transition": "ev"}.get(kind.value, "n")
                element_id = f"{prefix}.{_slug(v.title)}"
                gid = self.adapter.graph_id_for(v.scope)
                existing = self.adapter.get_graph_element(gid, element_id)
                if existing:
                    update(existing, kind=kind)
                else:
                    props = {**_value_props(v), LINEAGE_KEY: [dict(lineage_entry)]}
                    changes[(gid, element_id)] = ElementChange(graph_id=gid, element_id=element_id, element_kind=kind, operation="create", before=None,
                                                               after={"name": v.title, "description": v.statement, "props": props})
        else:
            for a in report.affected:
                if a.action == "proposed update":
                    update(a.element)

        # §26 downward propagation: every INHERITED realized copy of an own-scope element in a descendant
        # scope gets the same update; OVERRIDDEN / LOCALLY_REMOVED copies are left alone (review only).
        own = [c for c in list(changes.values()) if self.adapter.scope_for_graph(c.graph_id).key() == v.scope.key()]
        if own:
            for ds in report.descendants:
                if ds.inheritance_state != InheritanceState.INHERITED and ds.action != "proposed update":
                    continue
                states = self.adapter.calculate_inheritance(ds.scope)
                for el in self.adapter.list_elements(ds.scope):
                    tgt = _realizes_target(el)
                    if tgt is None:
                        continue
                    for c in own:
                        if tgt == (c.graph_id, c.element_id) and states.get(el.element_id) == InheritanceState.INHERITED:
                            update(el)
        return list(changes.values())

    def _override_targets(self, v: KnowledgeNuggetVersion):
        out = []
        for r in self.repo.relationships_for(v.ref):
            if r.from_ref != v.ref or r.relationship_type.value not in {"SPECIALIZES", "SUPERSEDES", "CONTRADICTS", "REFINES"}:
                continue
            parent = self.repo.version(r.to_ref)
            if parent is None or parent.scope.key() == v.scope.key():
                continue
            parent_deps = self.lineage.where_used(parent.ref)
            if not parent_deps:
                continue
            for el in self.adapter.list_elements(v.scope):
                tgt = _realizes_target(el)
                if tgt and any(tgt == (d.graph_id, d.element_id) for d in parent_deps):
                    out.append(el)
        return out

    # ---------------------------------------------------------------- validate / approve / apply (§22 states)

    def validate(self, proposal_id: str) -> GraphChangeProposal:
        p = self.repo.proposals.require(proposal_id)
        p.status = ProposalStatus.VALIDATING
        results = []
        for c in p.changes:
            if c.operation != "remove" and not (c.after or {}).get("props", {}).get(LINEAGE_KEY):
                results.append({"element_id": c.element_id, "ok": False, "detail": "no knowledge lineage (Invariant 2)"})
        results += self.adapter.validate_change(p.changes)
        for ref in p.knowledge_change_ids:
            v = self.repo.version(ref)
            if v is None or not v.is_governed():
                results.append({"element_id": "*", "ok": False, "detail": f"{ref} is not governed knowledge"})
        p.validation_results = results
        p.status = ProposalStatus.READY if all(r["ok"] for r in results) else ProposalStatus.FAILED
        self.repo.proposals.put(p)
        if p.status == ProposalStatus.FAILED:
            self.bus.emit("graph.change.failed", proposal_id=p.id, stage="validation")
        return p

    def approve(self, proposal_id: str, *, by: str, reason: str = "") -> GraphChangeProposal:
        p = self.repo.proposals.require(proposal_id)
        if p.status != ProposalStatus.READY:
            raise ChangeError(f"proposal {p.id} is {p.status.value}; only READY proposals can be approved")
        p.status, p.approved_at, p.approved_by = ProposalStatus.APPROVED, now_iso(), by
        self.repo.proposals.put(p)
        self.bus.emit("graph.change.approved", proposal_id=p.id)
        self.auditor.record(who=by, what="graph.change.approved", why=reason, approval=p.id, affected=[p.id] + p.knowledge_change_ids)
        return p

    def reject(self, proposal_id: str, *, by: str, reason: str = "") -> GraphChangeProposal:
        p = self.repo.proposals.require(proposal_id)
        p.status = ProposalStatus.REJECTED
        self.repo.proposals.put(p)
        self.auditor.record(who=by, what="graph.change.rejected", why=reason, affected=[p.id])
        return p

    def apply(self, proposal_id: str, *, by: str) -> GraphChangeExecution:
        p = self.repo.proposals.require(proposal_id)
        if p.status != ProposalStatus.APPROVED:
            raise ChangeError(f"proposal {p.id} is {p.status.value}; only APPROVED proposals can be applied")
        ex = GraphChangeExecution(proposal_id=p.id)
        self.repo.executions.put(ex)
        # stamp the graph_change_id into the lineage entries now that we have it
        for c in p.changes:
            if c.after:
                for ln in c.after.get("props", {}).get(LINEAGE_KEY, []):
                    if ln.get("graph_change_id") is None:
                        ln["graph_change_id"] = p.id
        try:
            self.adapter.apply_change(p.changes)
        except GraphValidationError as e:
            ex.status, ex.error, ex.completed_at = "FAILED", str(e), now_iso()
            self.repo.executions.put(ex)
            p.status = ProposalStatus.FAILED
            p.execution_ids.append(ex.id)
            self.repo.proposals.put(p)
            self.bus.emit("graph.change.failed", proposal_id=p.id, execution_id=ex.id, stage="apply")
            self.auditor.record(who=by, what="graph.change.failed", why=str(e), affected=[p.id, ex.id])
            return ex

        # Lineage bookkeeping (Invariants 4 & 5).
        for ref in p.knowledge_change_ids:
            v = self.repo.require_version(ref)
            for c in p.changes:
                el = self.adapter.get_graph_element(c.graph_id, c.element_id)
                if el is None:
                    continue
                state = self.adapter.calculate_inheritance(el.scope).get(el.element_id, InheritanceState.INHERITED)
                for old in self.repo.dependencies_for_element(c.graph_id, c.element_id):
                    if old.nugget_ref != v.ref:
                        self.lineage.retire(nugget_ref=old.nugget_ref, graph_id=c.graph_id, element_id=c.element_id)
                self.lineage.register(version=v, graph_id=c.graph_id, element_id=c.element_id, element_kind=c.element_kind,
                                      scope=el.scope, graph_change_id=p.id, inheritance_state=state)
        ex.applied_changes, ex.status, ex.completed_at = list(p.changes), "APPLIED", now_iso()
        self.repo.executions.put(ex)
        p.status, p.applied_at = ProposalStatus.APPLIED, now_iso()
        p.execution_ids.append(ex.id)
        self.repo.proposals.put(p)
        self.bus.emit("graph.change.applied", proposal_id=p.id, execution_id=ex.id)
        self.auditor.record(who=by, what="graph.change.applied", approval=p.id, before=p.before_state, after=p.proposed_after_state,
                            affected=[p.id, ex.id] + p.affected_element_ids)
        return ex

    def rollback(self, execution_id: str, *, by: str, reason: str = "") -> GraphChangeExecution:
        ex = self.repo.executions.require(execution_id)
        if ex.status != "APPLIED":
            raise ChangeError(f"execution {ex.id} is {ex.status}; only APPLIED executions roll back")
        self.adapter.rollback_change(ex.applied_changes)
        p = self.repo.proposals.require(ex.proposal_id)
        for ref in p.knowledge_change_ids:
            for c in ex.applied_changes:
                self.lineage.retire(nugget_ref=ref, graph_id=c.graph_id, element_id=c.element_id)
                # restore the previous lineage pointers
                for ln in (c.before or {}).get("props", {}).get(LINEAGE_KEY, []):
                    old = self.repo.version(f"{ln['nugget_id']}:v{ln['version']}")
                    if old is not None:
                        el = self.adapter.get_graph_element(c.graph_id, c.element_id)
                        if el is not None:
                            for d in self.repo.dependencies_for_element(c.graph_id, c.element_id, active_only=False):
                                if d.nugget_ref == old.ref:
                                    d.active = True
                                    self.repo.dependencies.put(d)
        rb = GraphChangeExecution(proposal_id=p.id, status="ROLLED_BACK", completed_at=now_iso(), rollback_of=ex.id,
                                  applied_changes=ex.applied_changes)
        self.repo.executions.put(rb)
        ex.status = "ROLLED_BACK"
        self.repo.executions.put(ex)
        p.status = ProposalStatus.ROLLED_BACK
        self.repo.proposals.put(p)
        self.auditor.record(who=by, what="graph.change.rolled_back", why=reason, affected=[p.id, ex.id, rb.id])
        return rb

    # ---------------------------------------------------------------- queues (§32)

    def awaiting_propagation(self) -> list[GraphChangeProposal]:
        return self.repo.proposals.where(lambda p: p.status in {ProposalStatus.READY, ProposalStatus.APPROVED, ProposalStatus.PROPOSED})

    def failed(self) -> list[GraphChangeProposal]:
        return self.repo.proposals.where(lambda p: p.status == ProposalStatus.FAILED)


def _realizes_target(el) -> tuple[str, str] | None:
    """(graph_id, element_id) a realized copy points at, for both adapter shapes."""
    r = el.realizes()
    if not r:
        return None
    if "graph_id" in r:
        return (r["graph_id"], r["element_id"])
    return (r.get("substructure_id"), r.get("node_id") or r.get("edge_id"))


def _merged_lineage(existing_props: dict[str, Any], entry: dict[str, Any], v: KnowledgeNuggetVersion) -> list[dict[str, Any]]:
    """Keep lineage entries from OTHER nuggets; replace entries of this canonical id with the new version."""
    kept = [ln for ln in existing_props.get(LINEAGE_KEY, []) if ln.get("nugget_id") != v.canonical_id]
    return kept + [dict(entry)]
