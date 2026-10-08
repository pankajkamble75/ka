"""graph-change (§22, §26, §39; research-01 R1, R2, R7): Graph Change Proposals — propose, validate, approve, publish, rollback.

Plan-05 made this a ChangeOp emitter, not a compiler. A governed nugget with a subject becomes ops on the element whose id
derives from the subject's canonical key (`p.merchant_underwriting`), so a second document about the same process updates
one node; relation predicates become edges only when the grammar binding is `bound`; everything carries
`props.knowledge_lineage` (Invariant 2). Publication goes through the adapter's `publish`, which for Enterprise OS means
its own proposal lifecycle (`proposals.py`: propose → named-person approve → apply; promotions refuse a stale base). KA's
`GraphChangeProposal` stays the impact-and-approval record and carries the EOS proposal id, base version, status,
new version and pinned instances. A content key makes a retry return the live proposal instead of a second one.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ka import config
from ka.audit import Auditor
from ka.events import EventBus
from ka.graph_adapter import LINEAGE_KEY, GraphAdapter, GraphValidationError, PublishRefused
from ka.graph_impact import KIND_FOR_KNOWLEDGE, GraphImpactService, ImpactReport
from ka.lineage import LineageService
from ka.model import ElementChange, GraphChangeExecution, GraphChangeProposal, KnowledgeNuggetVersion, Scope, Subject
from ka.repository import Repository
from ka.timeutil import now_iso
from ka.vocab import BindingStatus, GraphElementKind, InheritanceState, NuggetStatus, ProposalStatus, ScopeType


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


# [block plan-05]
PREFIX_FOR_KIND = {"process": "p.", "entity": "e.", "actor": "ac.", "rule": "r.", "event": "ev.", "state": "s.",
                   "attribute": "a.", "metric": "m.", "goal": "g.", "physical_source": "ps."}
KIND_FOR_NODE = {"process": GraphElementKind.PROCESS, "rule": GraphElementKind.RULE, "entity": GraphElementKind.CONCEPT,
                 "event": GraphElementKind.STATE_TRANSITION, "state": GraphElementKind.NODE, "actor": GraphElementKind.NODE}


def element_id_for(subject: Subject, parent_key: str | None = None) -> str:
    """Canonical identity → element id (research-01 R2): `p.<key>`; a child process is `p.<parent>.<child>`."""
    prefix = PREFIX_FOR_KIND.get(subject.kind, "n.")
    if parent_key and subject.kind == "process":
        return f"p.{parent_key}.{subject.canonical_key}"
    return f"{prefix}{subject.canonical_key}"


def idempotency_key_for(refs: list[str], ops: list[dict[str, Any]]) -> str:
    """sha256 over the nugget refs and the element ids the ops touch. The ops' bodies are deliberately NOT part of the key:
    they describe the step from the graph's current state (add_node before, set_props after), so the same knowledge would
    key differently before and after its own application. Identity is the knowledge plus where it lands."""
    ids = sorted({str(op.get("id") or (op.get("node") or {}).get("id") or (op.get("edge") or {}).get("id") or "") for op in ops})
    body = json.dumps({"refs": sorted(refs), "elements": ids}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def to_change_ops(changes: list[ElementChange]) -> list[dict[str, Any]]:
    """KA ElementChanges → EOS `ChangeOp` dicts (add_node / set_props / add_edge / remove_node / remove_edge)."""
    ops: list[dict[str, Any]] = []
    for c in changes:
        after = c.after or {}
        if c.element_kind == GraphElementKind.EDGE:
            if c.operation == "remove":
                ops.append({"op": "remove_edge", "id": c.element_id})
            elif c.operation == "create":
                e = c.edge or {}
                ops.append({"op": "add_edge", "edge": {"id": c.element_id, "kind": e.get("kind"), "source": e.get("source"),
                                                        "target": e.get("target"), "props": after.get("props", {})}})
            else:
                ops.append({"op": "set_props", "id": c.element_id, "props": after.get("props", {})})
            continue
        if c.operation == "remove":
            ops.append({"op": "remove_node", "id": c.element_id})
        elif c.operation == "create":
            ops.append({"op": "add_node", "node": {"id": c.element_id, "kind": after.get("kind") or _node_kind(c.element_kind),
                                                    "name": after.get("name", c.element_id), "description": after.get("description", ""),
                                                    "props": after.get("props", {})}})
        else:
            props = dict(after.get("props", {}))
            if "description" in after:
                props["description_text"] = after["description"]       # Node.description is top-level; set_props cannot change it
            ops.append({"op": "set_props", "id": c.element_id, "props": props})
    return ops


def _node_kind(kind: GraphElementKind) -> str:
    return {GraphElementKind.RULE: "rule", GraphElementKind.PROCESS: "process", GraphElementKind.STEP: "process",
            GraphElementKind.CONCEPT: "entity", GraphElementKind.STATE_TRANSITION: "event", GraphElementKind.COMPUTATION: "metric"}.get(kind, "entity")


class GraphChangeService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, adapter: GraphAdapter,
                 impact: GraphImpactService, lineage: LineageService):
        self.repo, self.bus, self.auditor, self.adapter, self.impact, self.lineage = repo, bus, auditor, adapter, impact, lineage
        self.auto_approve_low_impact = False

    # ---------------------------------------------------------------- propose (§20 steps 1–5)

    def propose_for(self, v: KnowledgeNuggetVersion, *, by: str = "ka.graph_change") -> GraphChangeProposal:
        report = self.impact.analyze(v)
        self.bus.emit("graph.impact.detected", ref=v.ref, affected_instances=report.counts.get("affected_instances", 0))
        changes = self.emit_ops(v, report)
        ops = to_change_ops(changes)
        key = idempotency_key_for([v.ref], ops)
        live = self.repo.proposals.where(lambda p: p.idempotency_key == key and p.status in {
            ProposalStatus.PROPOSED, ProposalStatus.VALIDATING, ProposalStatus.READY, ProposalStatus.APPROVED, ProposalStatus.APPLIED})
        if live:
            self.auditor.record(who=by, what="graph.change.deduplicated", why=f"content key matches {live[0].id}", scope=v.scope, affected=[live[0].id, v.ref])
            return live[0]
        prop = GraphChangeProposal(
            knowledge_change_ids=[v.ref], affected_graph_ids=sorted({c.graph_id for c in changes}),
            affected_element_ids=sorted({c.element_id for c in changes}),
            before_state={f"{c.graph_id}/{c.element_id}": c.before for c in changes},
            proposed_after_state={f"{c.graph_id}/{c.element_id}": c.after for c in changes},
            changes=changes, ops=ops, idempotency_key=key, reason=v.change_reason or f"governed knowledge {v.ref} activated",
            impact_summary=report.summary(), inheritance_effects=report.descendants, created_by=by,
            eos_base_version=self.adapter.base_version(v.scope),
        )
        high = config.get("KA_HIGH_IMPACT_INSTANCES")
        prop.requires_approval = (report.counts.get("affected_instances", 0) >= high
                                  or report.counts.get("overridden_descendants", 0) > 0)
        self.repo.proposals.put(prop)
        self.bus.emit("graph.change.proposed", proposal_id=prop.id, ref=v.ref)
        self.auditor.record(who=by, what="graph.change.proposed", why=prop.reason, scope=v.scope, affected=[prop.id, v.ref])
        self.validate(prop.id)
        if self.auto_approve_low_impact and not prop.requires_approval and self.repo.proposals.require(prop.id).status == ProposalStatus.READY:
            self.approve(prop.id, by="ka.policy.auto", reason="low impact; auto-approved by policy")
            actor = config.get("KA_EOS_AUTO_ACTOR") or ""
            if self.adapter.needs_named_actor() and not actor:
                p = self.repo.proposals.require(prop.id)
                p.impact_summary["note"] = "awaiting a named approver (KA_EOS_AUTO_ACTOR unset)"
                self.repo.proposals.put(p)
            else:
                self.apply(prop.id, by=actor or "ka.policy.auto")
        return self.repo.proposals.require(prop.id)

    # ---------------------------------------------------------------- emission (research-01 R1, R2)

    def emit_ops(self, v: KnowledgeNuggetVersion, report: ImpactReport) -> list[ElementChange]:
        if v.subject is None:
            return self._statement_changes(v, report)
        lineage_entry = self.lineage.graph_metadata(v, graph_change_id=None)
        gid = self.adapter.graph_id_for(v.scope)
        changes: dict[tuple[str, str], ElementChange] = {}
        binding = self.repo.binding_for(v.ref)
        bound = binding is not None and binding.binding_status == BindingStatus.BOUND

        def ensure_node(subject: Subject, *, parent_key: str | None = None, description: str | None = None, extra: dict | None = None) -> str:
            local = element_id_for(subject, parent_key)
            eid = self.adapter.resolve_element_id(v.scope, local)
            key = (gid, eid)
            if key in changes:
                if extra:
                    changes[key].after["props"].update(extra)
                return eid
            existing = self.adapter.get_graph_element(gid, eid)
            props = {**(existing.props if existing else {}), LINEAGE_KEY: _merged_lineage(existing.props if existing else {}, lineage_entry, v)}
            if extra:
                props.update(extra)
            after = {"kind": subject.kind, "name": existing.name if existing else (subject.name or subject.canonical_key), "props": props}
            if description is not None or existing is None:
                after["description"] = description if description is not None else (existing.description if existing else "")
            changes[key] = ElementChange(graph_id=gid, element_id=eid, element_kind=KIND_FOR_NODE.get(subject.kind, GraphElementKind.NODE),
                                         operation="update" if existing else "create", op="set_props" if existing else "add_node",
                                         before=existing.model_dump(include={"name", "description", "props"}) if existing else None, after=after)
            return eid

        pred = v.predicate or "description"
        subject_extra: dict[str, Any] = {"statement": v.statement}
        if pred == "typed_as" and bound and binding.process_type:
            subject_extra["process_type"] = binding.process_type
        subject_id = ensure_node(v.subject, description=(v.object.value if pred == "description" and v.object and v.object.value else None), extra=subject_extra)

        edge_name = binding.edge if (bound and binding is not None) else None
        if edge_name and v.object is not None and (v.object.canonical_key or v.object.value):
            obj_kind = v.object.kind or (self.adapter.edge_target_kind(edge_name) or "entity")
            obj_subject = Subject(kind=obj_kind, canonical_key=v.object.canonical_key or _slug(v.object.value or ""), name=v.object.value or v.object.canonical_key or "")
            parent_key = v.subject.canonical_key if (pred == "decomposes_into" and obj_kind == "process") else None
            target_id = ensure_node(obj_subject, parent_key=parent_key)
            # EOS forbids "/" in instance-local ids; a realized endpoint (`ka-dom/p.x`) is written `ka-dom~p.x` inside the edge id.
            edge_id = f"{edge_name}:{subject_id.replace('/', '~')}->{target_id.replace('/', '~')}"
            existing_edge = self.adapter.get_graph_element(gid, edge_id)
            props = {**(existing_edge.props if existing_edge else {}), LINEAGE_KEY: _merged_lineage(existing_edge.props if existing_edge else {}, lineage_entry, v)}
            changes[(gid, edge_id)] = ElementChange(graph_id=gid, element_id=edge_id, element_kind=GraphElementKind.EDGE,
                                                    operation="update" if existing_edge else "create", op="set_props" if existing_edge else "add_edge",
                                                    edge={"kind": edge_name, "source": subject_id, "target": target_id},
                                                    before=existing_edge.model_dump(include={"props"}) if existing_edge else None,
                                                    after={"props": props, "source": subject_id, "target": target_id, "kind": edge_name})
        # a revision: elements that depended on the prior version and are not the subject node get the new lineage too
        for a in report.affected:
            if a.action == "proposed update" and (a.element.graph_id, a.element.element_id) not in changes:
                el = a.element
                props = {**el.props, "statement": v.statement, LINEAGE_KEY: _merged_lineage(el.props, lineage_entry, v)}
                changes[(el.graph_id, el.element_id)] = ElementChange(graph_id=el.graph_id, element_id=el.element_id, element_kind=el.kind, operation="update",
                                                                      op="set_props", before=el.model_dump(include={"name", "description", "props"}),
                                                                      after={"name": el.name, "description": el.description, "props": props})
        return list(changes.values())

    def _statement_changes(self, v: KnowledgeNuggetVersion, report: ImpactReport) -> list[ElementChange]:
        """Statement-only nuggets (no subject): plan-01's compilation, unchanged — `r.<slug(title)>` etc. (noted in plan-05)."""
        lineage_entry = self.lineage.graph_metadata(v, graph_change_id=None)
        changes: dict[tuple[str, str], ElementChange] = {}

        def update(el, *, kind=None) -> None:
            key = (el.graph_id, el.element_id)
            if key in changes:
                return
            props = {**el.props, **_value_props(v), LINEAGE_KEY: _merged_lineage(el.props, lineage_entry, v)}
            changes[key] = ElementChange(graph_id=el.graph_id, element_id=el.element_id, element_kind=kind or el.kind, operation="update", op="set_props",
                                         before=el.model_dump(include={"name", "description", "props"}),
                                         after={"name": v.title, "description": v.statement, "props": props})

        if report.is_new_knowledge:
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
                    changes[(gid, element_id)] = ElementChange(graph_id=gid, element_id=element_id, element_kind=kind, operation="create", op="add_node", before=None,
                                                               after={"kind": _node_kind(kind), "name": v.title, "description": v.statement, "props": props})
        else:
            for a in report.affected:
                if a.action == "proposed update":
                    update(a.element)

        # §26 downward propagation under the shadow adapter: INHERITED realized copies get the same update (EOS: repin, Q2).
        own = [c for c in list(changes.values()) if self.adapter.scope_for_graph(c.graph_id).key() == v.scope.key()]
        if own and not self.adapter.needs_named_actor():
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

    # ---------------------------------------------------------------- validate / approve / publish (§22 states)

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
        """Publish an APPROVED proposal through the adapter (EOS: its proposal lifecycle, under `by`'s name)."""
        p = self.repo.proposals.require(proposal_id)
        if p.status != ProposalStatus.APPROVED:
            raise ChangeError(f"proposal {p.id} is {p.status.value}; only APPROVED proposals can be applied")
        ex = GraphChangeExecution(proposal_id=p.id)
        self.repo.executions.put(ex)
        for c in p.changes:
            if c.after:
                for ln in c.after.get("props", {}).get(LINEAGE_KEY, []):
                    if ln.get("graph_change_id") is None:
                        ln["graph_change_id"] = p.id
        p.ops = to_change_ops(p.changes)
        scope = self.adapter.scope_for_graph(p.affected_graph_ids[0]) if p.affected_graph_ids else self.repo.require_version(p.knowledge_change_ids[0]).scope
        try:
            result = self.adapter.publish(scope, p.changes, actor=by, reason=p.reason, base_version=p.eos_base_version)
        except (PublishRefused, GraphValidationError) as e:
            code = getattr(e, "code", "validation")
            ex.status, ex.error, ex.completed_at = "FAILED", f"{code}: {e}", now_iso()
            self.repo.executions.put(ex)
            p.status = ProposalStatus.FAILED
            p.execution_ids.append(ex.id)
            p.validation_results = list(p.validation_results) + [{"element_id": "*", "ok": False, "code": code, "detail": str(e),
                                                                   "findings": list(getattr(e, "findings", []) or [])}]
            self.repo.proposals.put(p)
            self.bus.emit("graph.change.failed", proposal_id=p.id, execution_id=ex.id, stage="publish", code=code)
            self.auditor.record(who=by, what="graph.change.failed", why=f"{code}: {e}", affected=[p.id, ex.id])
            return ex
        p.eos_proposal_id, p.eos_status, p.new_version = result.eos_proposal_id, result.eos_status, result.new_version
        p.pinned_instances = list(result.pinned_instances)
        if result.notes:
            p.impact_summary["publish_notes"] = list(result.notes)
        if result.pinned_instances:
            p.impact_summary["repin_required"] = list(result.pinned_instances)     # Q2: repin is reported, never done

        # Lineage bookkeeping (Invariants 4 & 5) from the elements the adapter reads back after publication.
        for ref in p.knowledge_change_ids:
            v = self.repo.require_version(ref)
            for c in p.changes:
                el = self.adapter.get_graph_element(c.graph_id, c.element_id)
                if el is None:
                    continue
                state = self.adapter.calculate_inheritance(el.scope).get(el.element_id, InheritanceState.INHERITED)
                # plan-06 correction: an element composed from several assertions depends on ALL of them. Only prior
                # versions of THIS canonical id are retired; other nuggets' dependencies on the element stay active.
                for old in self.repo.dependencies_for_element(c.graph_id, c.element_id):
                    if old.nugget_ref != v.ref and old.nugget_ref.rsplit(":v", 1)[0] == v.canonical_id:
                        self.lineage.retire(nugget_ref=old.nugget_ref, graph_id=c.graph_id, element_id=c.element_id)
                self.lineage.register(version=v, graph_id=c.graph_id, element_id=c.element_id, element_kind=c.element_kind,
                                      scope=el.scope, graph_change_id=p.id, inheritance_state=state)
        ex.applied_changes, ex.status, ex.completed_at = list(p.changes), "APPLIED", now_iso()
        self.repo.executions.put(ex)
        p.status, p.applied_at = ProposalStatus.APPLIED, now_iso()
        p.execution_ids.append(ex.id)
        self.repo.proposals.put(p)
        self.bus.emit("graph.change.applied", proposal_id=p.id, execution_id=ex.id, eos_proposal_id=p.eos_proposal_id or "")
        self.auditor.record(who=by, what="graph.change.applied", approval=p.id, before=p.before_state, after=p.proposed_after_state,
                            affected=[p.id, ex.id] + p.affected_element_ids + ([p.eos_proposal_id] if p.eos_proposal_id else []))
        return ex

    # [block plan-12] research-02 R4 (Q2): explicit per-instance repin by a named person, through the adapter → store
    def repin_status(self, proposal_id: str) -> list[dict[str, Any]]:
        p = self.repo.proposals.require(proposal_id)
        if p.status != ProposalStatus.APPLIED or not p.affected_graph_ids:
            return []
        domain = self.adapter.scope_for_graph(p.affected_graph_ids[0])
        target = p.new_version or self.adapter.base_version(domain) or "current"
        pins = self.adapter.pinned_versions(domain)
        done = {r["instance_id"]: r for r in p.impact_summary.get("repinned", [])}
        rows = []
        for iid in sorted(set(pins) | set(p.pinned_instances)):
            pinned = pins.get(iid)
            rows.append({"instance_id": iid, "pinned": pinned, "target": target, "current": pinned is not None and str(pinned) == str(target),
                         "repinned": done.get(iid)})
        return rows

    def repin(self, proposal_id: str, instance_id: str, *, by: str, preview: bool = False, agent_ids: set[str] | None = None):
        p = self.repo.proposals.require(proposal_id)
        if p.status != ProposalStatus.APPLIED or not p.new_version and self.adapter.needs_named_actor():
            raise ChangeError(f"proposal {p.id} is {p.status.value}; only an APPLIED proposal with a new version can be repinned")
        if not by or by.startswith("ka.") or by in (agent_ids or set()):
            raise ChangeError("repin is a person's decision (Q2): `by` must name a person, not a policy or a research agent")
        domain = self.adapter.scope_for_graph(p.affected_graph_ids[0])
        target = str(p.new_version or self.adapter.base_version(domain) or "current")
        pins = self.adapter.pinned_versions(domain)
        if instance_id not in pins and instance_id not in p.pinned_instances:
            raise ChangeError(f"instance {instance_id!r} does not pin {domain.scope_id}")
        inst = Scope(scope_type=ScopeType.INSTANCE, scope_id=instance_id)
        result = self.adapter.repin(inst, domain, target, actor=by, apply=not preview)
        if preview or not result.applied:
            return result
        if result.from_version == result.to_version and result.note:
            return result                                                  # already current: nothing moved, nothing to record
        req = [i for i in p.impact_summary.get("repin_required", []) if i != instance_id]
        p.impact_summary["repin_required"] = req
        rec = {"instance_id": instance_id, "from": result.from_version, "to": result.to_version, "by": by, "at": now_iso()}
        p.impact_summary["repinned"] = [r for r in p.impact_summary.get("repinned", []) if r["instance_id"] != instance_id] + [rec]
        self.repo.proposals.put(p)
        self.bus.emit("graph.instance.repinned", proposal_id=p.id, instance_id=instance_id, to_version=result.to_version or "")
        self.auditor.record(who=by, what="graph.instance.repinned", why=f"{domain.scope_id} {result.from_version} → {result.to_version}", scope=inst,
                            before={"pinned": result.from_version}, after={"pinned": result.to_version}, approval=p.id, affected=[p.id, instance_id])
        return result

    def awaiting_repin(self) -> list[dict[str, Any]]:
        """One row per (APPLIED proposal, instance still on the old version) — the Dashboard's queue."""
        return [{"proposal_id": p.id, "instance_id": iid, "new_version": p.new_version, "knowledge_change_ids": p.knowledge_change_ids}
                for p in self.repo.proposals.where(lambda p: p.status == ProposalStatus.APPLIED) for iid in p.impact_summary.get("repin_required", [])]
    # [/block plan-12]

    # [block plan-10] research-02 R2 (Q4): retiring a version removes the graph elements that depend on it ALONE
    def propose_retirement(self, v: KnowledgeNuggetVersion, *, by: str = "ka.graph_change") -> GraphChangeProposal | None:
        """Removal ops for every element whose active lineage is only `v` (or other versions of its canonical id); elements
        another ACTIVE nugget depends on are left alone. Goes through validate → approve → apply like any proposal."""
        deps = self.repo.dependencies_for_nugget(v.ref, active_only=False)
        changes: list[ElementChange] = []
        for d in deps:
            others = [x for x in self.repo.dependencies_for_element(d.graph_id, d.element_id, active_only=True)
                      if x.nugget_ref.rsplit(":v", 1)[0] != v.canonical_id]
            others = [x for x in others if (ov := self.repo.version(x.nugget_ref)) is not None and ov.status == NuggetStatus.ACTIVE]
            if others:
                continue
            el = self.adapter.get_graph_element(d.graph_id, d.element_id)
            if el is None:
                continue
            is_edge = getattr(el, "kind", "") == "edge" or ":" in d.element_id and "->" in d.element_id
            changes.append(ElementChange(graph_id=d.graph_id, element_id=d.element_id,
                                         element_kind=GraphElementKind.EDGE if is_edge else GraphElementKind.NODE, operation="remove",
                                         op="remove_edge" if is_edge else "remove_node",
                                         before=el.model_dump(include={"name", "description", "props"}),
                                         after={"props": {LINEAGE_KEY: [{"nugget_id": v.canonical_id, "version": v.version, "retired": True}]}}))
        if not changes:
            return None
        changes.sort(key=lambda c: (c.element_kind != GraphElementKind.EDGE, c.element_id))   # edges first
        ops = to_change_ops(changes)
        key = idempotency_key_for([f"retire:{v.ref}"], ops)
        prop = GraphChangeProposal(
            knowledge_change_ids=[v.ref], affected_graph_ids=sorted({c.graph_id for c in changes}),
            affected_element_ids=sorted({c.element_id for c in changes}),
            before_state={f"{c.graph_id}/{c.element_id}": c.before for c in changes}, proposed_after_state={},
            changes=changes, ops=ops, idempotency_key=key, reason=f"retirement of {v.ref}: source revoked, re-review rejected (Q4)",
            impact_summary={"retirement": True, "elements": len(changes)}, created_by=by,
            eos_base_version=self.adapter.base_version(v.scope), requires_approval=True)
        self.repo.proposals.put(prop)
        self.bus.emit("graph.change.proposed", proposal_id=prop.id, ref=v.ref)
        self.auditor.record(who=by, what="graph.change.proposed", why=prop.reason, scope=v.scope, affected=[prop.id, v.ref])
        self.validate(prop.id)
        return self.repo.proposals.require(prop.id)
    # [/block plan-10]

    def rollback(self, execution_id: str, *, by: str, reason: str = "") -> GraphChangeExecution:
        """Publish the inverse of an applied execution (EOS: a new proposal; in-memory: the inverse applied)."""
        ex = self.repo.executions.require(execution_id)
        if ex.status != "APPLIED":
            raise ChangeError(f"execution {ex.id} is {ex.status}; only APPLIED executions roll back")
        p = self.repo.proposals.require(ex.proposal_id)
        inverse = inverse_changes(ex.applied_changes)
        scope = self.adapter.scope_for_graph(p.affected_graph_ids[0])
        result = self.adapter.publish(scope, inverse, actor=by, reason=f"rollback of {ex.id}: {reason}", base_version=self.adapter.base_version(scope), rollback=True)
        for ref in p.knowledge_change_ids:
            for c in ex.applied_changes:
                self.lineage.retire(nugget_ref=ref, graph_id=c.graph_id, element_id=c.element_id)
                for ln in (c.before or {}).get("props", {}).get(LINEAGE_KEY, []):
                    old = self.repo.version(f"{ln['nugget_id']}:v{ln['version']}")
                    if old is not None:
                        for d in self.repo.dependencies_for_element(c.graph_id, c.element_id, active_only=False):
                            if d.nugget_ref == old.ref:
                                d.active = True
                                self.repo.dependencies.put(d)
        rb = GraphChangeExecution(proposal_id=p.id, status="ROLLED_BACK", completed_at=now_iso(), rollback_of=ex.id, applied_changes=inverse,
                                  error=None)
        self.repo.executions.put(rb)
        ex.status = "ROLLED_BACK"
        self.repo.executions.put(ex)
        p.status = ProposalStatus.ROLLED_BACK
        if result.eos_proposal_id:
            p.impact_summary["rollback_eos_proposal_id"] = result.eos_proposal_id
        self.repo.proposals.put(p)
        self.auditor.record(who=by, what="graph.change.rolled_back", why=reason, affected=[p.id, ex.id, rb.id] + ([result.eos_proposal_id] if result.eos_proposal_id else []))
        return rb

    # ---------------------------------------------------------------- queues (§32)

    def awaiting_propagation(self) -> list[GraphChangeProposal]:
        return self.repo.proposals.where(lambda p: p.status in {ProposalStatus.READY, ProposalStatus.APPROVED, ProposalStatus.PROPOSED})

    def failed(self) -> list[GraphChangeProposal]:
        return self.repo.proposals.where(lambda p: p.status == ProposalStatus.FAILED)


def inverse_changes(changes: list[ElementChange]) -> list[ElementChange]:
    out = []
    for c in reversed(changes):
        if c.operation == "create":
            out.append(ElementChange(graph_id=c.graph_id, element_id=c.element_id, element_kind=c.element_kind, operation="remove",
                                     op="remove_edge" if c.element_kind == GraphElementKind.EDGE else "remove_node", edge=c.edge))
        elif c.before is not None:
            out.append(ElementChange(graph_id=c.graph_id, element_id=c.element_id, element_kind=c.element_kind, operation="update", op="set_props",
                                     edge=c.edge, before=c.after, after=c.before))
    return out
# [/block plan-05]


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
