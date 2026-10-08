"""§25 Upward Promotion: detect the same instance knowledge repeated across sibling instances and PROPOSE a
domain-level nugget. Never automatic (Invariant 10) — the proposal becomes a candidate that governance decides.
"""
from __future__ import annotations

from ka import config
from ka.audit import Auditor
from ka.conflict import similarity
from ka.events import EventBus
from ka.governance import CandidateInput, GovernanceError, GovernanceService
from ka.model import KnowledgeNuggetVersion, PromotionProposal, Scope
from ka.repository import Repository
from ka.scope import ScopeRegistry
from ka.timeutil import now_iso
from ka.vocab import AcquisitionChannel, NuggetStatus, RelationshipType, ScopeType


class PromotionService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, registry: ScopeRegistry, governance: GovernanceService):
        self.repo, self.bus, self.auditor, self.registry, self.governance = repo, bus, auditor, registry, governance

    def detect(self, parent: Scope) -> list[PromotionProposal]:
        """Pattern Detection for one domain / parent domain: clusters of ACTIVE instance nuggets shared by
        at least KA_PROMOTION_MIN_INSTANCES instances, not already present at the parent."""
        instances = self.registry.instances_under(parent)
        minimum = config.get("KA_PROMOTION_MIN_INSTANCES")
        if len(instances) < minimum:
            return []
        pool: list[KnowledgeNuggetVersion] = []
        for inst in instances:
            pool += self.repo.active_nuggets(inst)
        clusters: list[list[KnowledgeNuggetVersion]] = []
        for n in pool:
            for cl in clusters:
                if similarity(cl[0].statement, n.statement) >= config.get("KA_DUPLICATE_THRESHOLD"):
                    cl.append(n)
                    break
            else:
                clusters.append([n])
        parent_active = self.repo.active_nuggets(parent)
        out = []
        for cl in clusters:
            inst_ids = sorted({n.scope_id for n in cl})
            if len(inst_ids) < minimum:
                continue
            if any(similarity(p.statement, cl[0].statement) >= config.get("KA_DUPLICATE_THRESHOLD") for p in parent_active):
                continue
            already = self.repo.promotions.where(lambda p: p.target_scope.key() == parent.key() and p.status == "PROPOSED"
                                                 and similarity(p.statement, cl[0].statement) >= config.get("KA_DUPLICATE_THRESHOLD"))
            if already:
                out += already
                continue
            prop = PromotionProposal(target_scope=parent, pattern_refs=[n.ref for n in cl], instance_ids=inst_ids,
                                     statement=cl[0].statement, title=cl[0].title)
            self.repo.promotions.put(prop)
            self.bus.emit("promotion.proposed", promotion_id=prop.id, scope=parent.key(), instances=len(inst_ids))
            out.append(prop)
        return out

    def decide(self, promotion_id: str, *, approve: bool, by: str, reason: str = "", widen_visibility: bool = False) -> PromotionProposal:
        p = self.repo.promotions.require(promotion_id)
        p.decided_by, p.decided_at = by, now_iso()
        if not approve:
            p.status = "REJECTED"
            self.repo.promotions.put(p)
            self.auditor.record(who=by, what="promotion.rejected", why=reason, scope=p.target_scope, affected=[p.id])
            return p
        lead = self.repo.require_version(p.pattern_refs[0])
        # [block plan-02]
        # research-01 R6: promoting instance knowledge to a domain may not widen its visibility silently.
        from ka.vocab import widens_visibility
        needed = widens_visibility(lead.visibility, p.target_scope.scope_type)
        if needed is not None and not widen_visibility:
            raise GovernanceError(f"promoting {lead.ref} to {p.target_scope.key()} would widen its visibility "
                                  f"{lead.visibility.value} → {needed.value}; pass widen_visibility=True to decide that explicitly")
        promoted_visibility = needed if needed is not None else lead.visibility
        # [/block plan-02]
        src, ev = [], []
        for ref in p.pattern_refs:
            v = self.repo.version(ref)
            if v:
                src += [s for s in v.source_refs if s not in src]
                ev += [e for e in v.evidence_refs if e not in ev]
        cand = self.governance.ingest_candidate(CandidateInput(
            title=lead.title, statement=lead.statement, scope=p.target_scope, source_ids=src, evidence_ids=ev,
            knowledge_type=lead.knowledge_type.value, authority_type=lead.authority_type, confidence=min(0.95, lead.confidence + 0.1),
            tags=lead.tags, graph_group=lead.graph_group, channel=AcquisitionChannel.FEEDBACK, created_by=by,
            change_reason=f"promotion {p.id} from {len(p.instance_ids)} instances: {reason}", visibility=promoted_visibility))
        for ref in p.pattern_refs:
            from ka.model import KnowledgeRelationship
            self.repo.relationships.put(KnowledgeRelationship(from_ref=cand.ref, to_ref=ref, relationship_type=RelationshipType.MERGES,
                                                              explanation="promoted pattern", created_by=by))
        p.status, p.candidate_ref = "APPROVED", cand.ref
        self.repo.promotions.put(p)
        self.auditor.record(who=by, what="promotion.approved", why=reason, scope=p.target_scope, affected=[p.id, cand.ref])
        return p

    def instance_states(self, instance: Scope) -> dict[str, list[KnowledgeNuggetVersion]]:
        """§30 — Inherited / Instance-specific / Overrides / Extensions / Removed / Conflicts for one instance."""
        own = self.repo.nuggets_in_scope(instance, [NuggetStatus.ACTIVE])
        inherited: list[KnowledgeNuggetVersion] = []
        for anc in self.registry.ancestors(instance):
            inherited += self.repo.active_nuggets(anc)
        overrides, extensions, specific = [], [], []
        for n in own:
            rels = self.repo.relationships_for(n.ref)
            kinds = {r.relationship_type for r in rels}
            if RelationshipType.SPECIALIZES in kinds or RelationshipType.SUPERSEDES in kinds and any(
                    self.repo.version(r.to_ref) and self.repo.version(r.to_ref).scope_type != ScopeType.INSTANCE for r in rels):
                overrides.append(n)
            elif RelationshipType.EXTENDS in kinds:
                extensions.append(n)
            else:
                specific.append(n)
        conflicts = [n for n in self.repo.nuggets_in_scope(instance) if n.analysis.get("conflict_open") and n.status == NuggetStatus.PENDING_REVIEW]
        removed = [n for n in self.repo.nuggets_in_scope(instance, [NuggetStatus.OBSOLETE])]
        overridden_refs = {r.to_ref for n in overrides for r in self.repo.relationships_for(n.ref) if r.from_ref == n.ref}
        inherited = [n for n in inherited if n.ref not in overridden_refs]
        return {"inherited": inherited, "instance_specific": specific, "overrides": overrides, "extensions": extensions,
                "removed": removed, "conflicts": conflicts}
