"""knowledge-governance (§11–§13, §33): the ONE pipeline every channel converges on.

    Source → Extract Candidate → Normalize → Find Related → Classify (dup/support/conflict/extension) →
    Determine Scope → Determine Authority → Proposed Change → Governance Decision → Immutable Version → ACTIVE

Channels differ by provenance and authority, not lifecycle: `ingest_candidates` is used by content
ingestion, research synthesis and corrections alike. Nothing becomes ACTIVE without a GovernanceDecision,
and research agents cannot be the decider for their own candidates (§17).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ka import config
from ka.audit import Auditor
from ka.conflict import Analysis, ConflictDetector
from ka.events import EventBus
from ka.extraction import CandidateExtractor, CandidateStatement, TextExtraction, normalize
from ka.model import Evidence, GovernanceDecision, KnowledgeNuggetVersion, KnowledgeRelationship, Scope, Source, SourceVersion
from ka.repository import Repository
from ka.scope import ScopeDecisionEngine, ScopeRegistry
from ka.timeutil import now_iso
from ka.versioning import VersioningService
from ka.vocab import (
    AcquisitionChannel,
    AuthorityType,
    DecisionOutcome,
    NuggetStatus,
    RelationshipType,
    ScopeType,
    Visibility,
    narrowest_visibility,
)


class GovernanceError(RuntimeError):
    pass


@dataclass
class CandidateInput:
    """What a channel hands the pipeline. Everything else is derived."""
    title: str
    statement: str
    scope: Scope
    source_ids: list[str]
    evidence_ids: list[str]
    knowledge_type: str = "fact"
    authority_type: AuthorityType = AuthorityType.USER_KNOWLEDGE
    confidence: float = 0.5
    tags: list[str] | None = None
    normalized_meaning: str = ""
    graph_group: str | None = None
    channel: AcquisitionChannel = AcquisitionChannel.CONTENT
    created_by: str = "system"
    research_run_id: str | None = None
    correction_id: str | None = None
    effective_from: str | None = None
    canonical_id: str | None = None        # set to revise an existing nugget (→ next version)
    change_reason: str | None = None
    visibility: Visibility | None = None


class GovernanceService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, registry: ScopeRegistry,
                 versioning: VersioningService, detector: ConflictDetector, extractor: CandidateExtractor,
                 authority_policy: config.AuthorityPolicy | None = None):
        self.repo, self.bus, self.auditor, self.registry = repo, bus, auditor, registry
        self.versioning, self.detector, self.extractor = versioning, detector, extractor
        self.scope_engine = ScopeDecisionEngine(registry)
        self.authority = authority_policy or config.AuthorityPolicy()
        self.on_more_research: Callable[[KnowledgeNuggetVersion, str], str] | None = None   # set by ResearchOrchestrator
        self.research_agent_ids: set[str] = set()

    # ---------------------------------------------------------------- Extract (§11 step 1)

    def extract_from_source(self, source: Source, version: SourceVersion, extraction: TextExtraction, *,
                            actor: str, default_scope: Scope | None = None, analyze: bool = True) -> list[KnowledgeNuggetVersion]:
        if not extraction.text.strip():
            return []
        statements = self.extractor.extract(title=source.title, sections=extraction.sections, text=extraction.text)
        scope = source.scope or default_scope
        if scope is None:
            raise GovernanceError("a source needs a scope (structure / parent domain / domain / instance) before extraction (§7)")
        out = []
        for st in statements:
            ev = self.repo.evidence.put(Evidence(source_id=source.id, source_version_id=version.id, locator=st.locator,
                                                 excerpt=st.excerpt, created_by=actor, visibility=source.visibility))
            out.append(self.ingest_candidate(CandidateInput(
                title=st.title, statement=st.statement, scope=self._scope_from_hint(scope, st),
                source_ids=[source.id], evidence_ids=[ev.id], knowledge_type=st.knowledge_type.value,
                authority_type=source.authority_type, confidence=st.confidence, tags=st.tags,
                normalized_meaning=st.normalized_meaning, graph_group=st.graph_group, channel=source.channel,
                created_by=actor, effective_from=source.effective_date, visibility=source.visibility,
            ), analyze=analyze))
        return out

    def _scope_from_hint(self, scope: Scope, st: CandidateStatement) -> Scope:
        """§7 — pick the lowest valid scope. A hint can NARROW the source's scope to an instance below it
        only when there is exactly one; it never broadens silently (broadening needs approval, §24)."""
        if st.scope_hint == "instance" and scope.scope_type != ScopeType.INSTANCE:
            kids = self.registry.instances_under(scope)
            if len(kids) == 1:
                return kids[0]
        return scope

    # ---------------------------------------------------------------- Candidate → Analyzed (§11 steps 2–8)

    def ingest_candidate(self, inp: CandidateInput, *, analyze: bool = True) -> KnowledgeNuggetVersion:
        sources = [s for s in (self.repo.sources.get(i) for i in inp.source_ids) if s]
        vis = inp.visibility or narrowest_visibility([s.visibility for s in sources]) if sources else (inp.visibility or Visibility.ENTERPRISE)
        if inp.canonical_id:
            prior = self.repo.latest_version(inp.canonical_id)
            if prior is None:
                raise GovernanceError(f"unknown canonical id {inp.canonical_id}")
            v = self.versioning.new_version_from(prior, title=inp.title, statement=inp.statement,
                                                 normalized_meaning=inp.normalized_meaning or normalize(inp.statement),
                                                 scope_type=inp.scope.scope_type, scope_id=inp.scope.scope_id,
                                                 source_refs=inp.source_ids, evidence_refs=inp.evidence_ids,
                                                 authority_type=inp.authority_type, confidence=inp.confidence,
                                                 channel=inp.channel, created_by=inp.created_by, change_reason=inp.change_reason,
                                                 effective_from=inp.effective_from, visibility=vis,
                                                 research_run_refs=[inp.research_run_id] if inp.research_run_id else [],
                                                 correction_refs=[inp.correction_id] if inp.correction_id else [])
        else:
            v = KnowledgeNuggetVersion(
                canonical_id=self.repo.next_canonical_id(), title=inp.title, statement=inp.statement,
                normalized_meaning=inp.normalized_meaning or normalize(inp.statement),
                scope_type=inp.scope.scope_type, scope_id=inp.scope.scope_id, knowledge_type=inp.knowledge_type,
                status=NuggetStatus.CANDIDATE, authority_type=inp.authority_type, confidence=inp.confidence,
                source_refs=inp.source_ids, evidence_refs=inp.evidence_ids, tags=inp.tags or [], graph_group=inp.graph_group,
                channel=inp.channel, created_by=inp.created_by, effective_from=inp.effective_from, visibility=vis,
                research_run_refs=[inp.research_run_id] if inp.research_run_id else [],
                correction_refs=[inp.correction_id] if inp.correction_id else [], change_reason=inp.change_reason,
            )
        v.authority_rank = self.authority.rank(v.authority_type, v.scope_type, v.scope_id)
        self.registry.fill_hierarchy_fields(v)
        self.repo.nuggets.put(v)
        self.bus.emit("knowledge.candidate.created", ref=v.ref, canonical_id=v.canonical_id, scope=v.scope.key())
        self.auditor.record(who=inp.created_by, what="knowledge.candidate.created", why=inp.change_reason or inp.channel.value,
                            source=inp.source_ids[0] if inp.source_ids else None, scope=v.scope, affected=[v.ref, v.canonical_id])
        if analyze:
            self.analyze(v)
        return v

    def analyze(self, v: KnowledgeNuggetVersion) -> Analysis:
        """Steps 4–8: find related knowledge, classify, decide scope, apply authority, move to review."""
        if v.status != NuggetStatus.CANDIDATE:
            raise GovernanceError(f"{v.ref} is {v.status.value}, not CANDIDATE")
        pool = [n for n in self.repo.nuggets_by_status(NuggetStatus.ACTIVE, NuggetStatus.PENDING_REVIEW, NuggetStatus.APPROVED)
                if n.canonical_id != v.canonical_id and self._visible_scope(n, v)]
        analysis = self.detector.analyze(v, pool)

        # Record relationships with explanations (§10).
        rels = []
        for f in analysis.findings:
            if f.relationship == RelationshipType.INDEPENDENT_OF:
                continue
            r = self.repo.relationships.put(KnowledgeRelationship(
                from_ref=v.ref, to_ref=f.existing.ref, relationship_type=f.relationship, confidence=f.confidence,
                explanation=f.explanation, created_by="ka.conflict"))
            rels.append(r.id)
        v.relationships = rels

        # Scope decision (§24) using the signals the spec lists.
        decision = self.scope_engine.decide(statement=v.statement, location_scope=v.scope,
                                            similar=[f.existing for f in analysis.findings])
        v.analysis = {
            "findings": [{"existing_ref": f.existing.ref, "relationship": f.relationship.value, "confidence": f.confidence,
                          "explanation": f.explanation, "both_valid": f.both_valid, "suggested_resolution": f.suggested_resolution,
                          "llm": f.llm} for f in analysis.findings],
            "scope_decision": {"scope": decision.scope.key(), "confidence": decision.confidence, "rationale": decision.rationale,
                               "requires_approval": decision.requires_approval,
                               "alternatives": [s.key() for s in decision.alternatives]},
            "analyzed_at": now_iso(),
        }
        self.versioning.transition(v, NuggetStatus.ANALYZED)

        if analysis.has_conflict():
            self.versioning.transition(v, NuggetStatus.CONFLICT)
            for f in analysis.conflicts:
                self.bus.emit("knowledge.conflict.detected", ref=v.ref, existing_ref=f.existing.ref)
            auto = self._auto_resolve_by_authority(v, analysis)
            if auto is None:
                self.versioning.transition(v, NuggetStatus.PENDING_REVIEW)
                # keep the conflict marker visible to the queue (§32) via analysis
                v.analysis["conflict_open"] = True
                self.repo.nuggets.put(v)
        elif analysis.duplicates:
            dup = analysis.duplicates[0].existing
            v.analysis["duplicate_of"] = dup.ref
            self.versioning.transition(v, NuggetStatus.PENDING_REVIEW)
        else:
            self.versioning.transition(v, NuggetStatus.PENDING_REVIEW)
        return analysis

    def _visible_scope(self, existing: KnowledgeNuggetVersion, candidate: KnowledgeNuggetVersion) -> bool:
        """Compare against knowledge on the candidate's own inheritance chain, plus siblings' scope type."""
        chain = {candidate.scope.key()} | {s.key() for s in self.registry.ancestors(candidate.scope)}
        if existing.scope.key() in chain:
            return True
        # descendants matter too: a domain candidate may contradict an instance override
        return existing.scope.key() in {s.key() for s in self.registry.descendants(candidate.scope)}

    def _auto_resolve_by_authority(self, v: KnowledgeNuggetVersion, analysis: Analysis) -> GovernanceDecision | None:
        """§13: a low-authority candidate contradicting a much higher-authority ACTIVE nugget is resolved
        automatically — but preserved, with the explanation, as a REJECTED candidate."""
        gap = config.get("KA_AUTO_RESOLVE_AUTHORITY_GAP")
        if not gap or v.channel == AcquisitionChannel.FEEDBACK:
            return None   # a human correction always reaches a human reviewer
        strongest = max((f.existing for f in analysis.conflicts if f.existing.status == NuggetStatus.ACTIVE),
                        key=lambda n: n.authority_rank, default=None)
        if strongest is None or strongest.authority_rank - v.authority_rank < gap:
            return None
        d = GovernanceDecision(subject_ref=v.ref, related_refs=[strongest.ref], outcome=DecisionOutcome.AUTO_RESOLVED_BY_AUTHORITY,
                               decided_by="ka.governance", automatic=True,
                               reason=f"candidate authority {v.authority_type.value} (rank {v.authority_rank}) contradicts ACTIVE "
                                      f"{strongest.ref} of authority {strongest.authority_type.value} (rank {strongest.authority_rank}); "
                                      f"gap ≥ {gap} — kept existing automatically. Candidate preserved for review.")
        self.repo.decisions.put(d)
        v.governance_decision_id = d.id
        v.analysis["auto_resolved"] = d.reason
        self.versioning.transition(v, NuggetStatus.REJECTED)
        self.bus.emit("knowledge.rejected", ref=v.ref, decision_id=d.id)
        self.auditor.record(who="ka.governance", what="knowledge.auto_resolved", why=d.reason, scope=v.scope, approval=d.id,
                            affected=[v.ref, strongest.ref])
        return d

    # ---------------------------------------------------------------- Governance Decision (§11 step 9, §33)

    def decide(self, ref: str, outcome: DecisionOutcome, *, by: str, reason: str = "", comments: str | None = None,
               merged_statement: str | None = None, new_scope: Scope | None = None, existing_ref: str | None = None) -> GovernanceDecision:
        v = self.repo.require_version(ref)
        if by in self.research_agent_ids:
            raise GovernanceError("research agents cannot approve their own knowledge (§17)")
        if v.status not in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.ANALYZED}:
            raise GovernanceError(f"{ref} is {v.status.value}; only PENDING_REVIEW/CONFLICT candidates can be decided")
        partner = self.repo.version(existing_ref) if existing_ref else self._conflict_partner(v)
        d = GovernanceDecision(subject_ref=v.ref, related_refs=[partner.ref] if partner else [], outcome=outcome, decided_by=by,
                               reason=reason, comments=comments)
        before = {"status": v.status.value}

        if outcome in {DecisionOutcome.APPROVE, DecisionOutcome.ACCEPT_NEW}:
            self._activate(v, d, supersede=[partner] if (partner and outcome == DecisionOutcome.ACCEPT_NEW) else None)
        elif outcome in {DecisionOutcome.REJECT, DecisionOutcome.KEEP_EXISTING}:
            v.governance_decision_id = d.id
            self.versioning.transition(v, NuggetStatus.REJECTED)
            self.bus.emit("knowledge.rejected", ref=v.ref, decision_id=d.id)
        elif outcome == DecisionOutcome.MERGE:
            if not partner or not merged_statement:
                raise GovernanceError("MERGE needs a conflicting partner and a merged_statement")
            merged = self.versioning.new_version_from(partner, title=v.title, statement=merged_statement,
                                                      normalized_meaning=normalize(merged_statement),
                                                      source_refs=sorted(set(partner.source_refs) | set(v.source_refs)),
                                                      evidence_refs=sorted(set(partner.evidence_refs) | set(v.evidence_refs)),
                                                      created_by=by, change_reason=f"merge of {v.ref} into {partner.canonical_id}: {reason}")
            merged.authority_rank = max(v.authority_rank, partner.authority_rank)
            merged.authority_type = v.authority_type if v.authority_rank >= partner.authority_rank else partner.authority_type
            self.repo.nuggets.put(merged)
            self.repo.relationships.put(KnowledgeRelationship(from_ref=merged.ref, to_ref=v.ref, relationship_type=RelationshipType.MERGES,
                                                              explanation=reason, created_by=by))
            self.versioning.transition(merged, NuggetStatus.ANALYZED)
            self.versioning.transition(merged, NuggetStatus.PENDING_REVIEW)
            self._activate(merged, d, supersede=[partner])
            v.governance_decision_id = d.id
            self.versioning.transition(v, NuggetStatus.SUPERSEDED)
            v.superseded_by = merged.ref
            self.repo.nuggets.put(v)
            d.resulting_refs.append(merged.ref)
        elif outcome == DecisionOutcome.BOTH_VALID_ADD_CONTEXT:
            if partner:
                self.repo.relationships.put(KnowledgeRelationship(from_ref=v.ref, to_ref=partner.ref, relationship_type=RelationshipType.CONTEXTUALIZES,
                                                                  explanation=reason or "both valid in context", created_by=by))
            self._activate(v, d, supersede=None)
        elif outcome == DecisionOutcome.CHANGE_SCOPE:
            if new_scope is None:
                raise GovernanceError("CHANGE_SCOPE needs new_scope")
            v.governance_decision_id = d.id
            self.versioning.transition(v, NuggetStatus.REJECTED)
            re_scoped = self.ingest_candidate(CandidateInput(
                title=v.title, statement=v.statement, scope=new_scope, source_ids=v.source_refs, evidence_ids=v.evidence_refs,
                knowledge_type=v.knowledge_type.value, authority_type=v.authority_type, confidence=v.confidence, tags=v.tags,
                normalized_meaning=v.normalized_meaning, graph_group=v.graph_group, channel=v.channel, created_by=by,
                change_reason=f"re-scoped from {v.scope.key()} by {by}: {reason}", effective_from=v.effective_from))
            d.resulting_refs.append(re_scoped.ref)
        elif outcome == DecisionOutcome.REQUEST_MORE_RESEARCH:
            if self.on_more_research is None:
                raise GovernanceError("no research orchestrator attached")
            mission_id = self.on_more_research(v, reason)
            d.comments = f"{comments or ''} mission={mission_id}".strip()
            v.comments.append({"by": by, "at": now_iso(), "text": f"more research requested: {mission_id}"})
            self.repo.nuggets.put(v)
        else:
            raise GovernanceError(f"unsupported outcome {outcome}")

        self.repo.decisions.put(d)
        self.auditor.record(who=by, what=f"governance.{outcome.value.lower()}", why=reason, before=before,
                            after={"status": self.repo.require_version(v.ref).status.value}, scope=v.scope, approval=d.id,
                            affected=[v.ref] + d.related_refs + d.resulting_refs)
        return d

    def _conflict_partner(self, v: KnowledgeNuggetVersion) -> KnowledgeNuggetVersion | None:
        for f in v.analysis.get("findings", []):
            if f["relationship"] in {"CONTRADICTS", "DUPLICATES", "SUPERSEDES"}:
                p = self.repo.version(f["existing_ref"])
                if p is not None:
                    return p
        if v.supersedes:
            return self.repo.version(v.supersedes)
        return None

    def _activate(self, v: KnowledgeNuggetVersion, d: GovernanceDecision, *, supersede: list[KnowledgeNuggetVersion] | None) -> None:
        v.governance_decision_id = d.id
        v.approved_at, v.approved_by = now_iso(), d.decided_by
        if v.status == NuggetStatus.CONFLICT:
            self.versioning.transition(v, NuggetStatus.PENDING_REVIEW)
        self.versioning.transition(v, NuggetStatus.APPROVED)
        # Prior version of the same canonical id is superseded by activation (§14).
        prior_active = self.repo.active_version(v.canonical_id)
        to_supersede = list(supersede or [])
        if prior_active and prior_active.ref != v.ref:
            to_supersede.append(prior_active)
        self.versioning.transition(v, NuggetStatus.ACTIVE)
        for old in to_supersede:
            if old.ref == v.ref:
                continue
            self.versioning.supersede(old, v)
            self.repo.relationships.put(KnowledgeRelationship(from_ref=v.ref, to_ref=old.ref, relationship_type=RelationshipType.SUPERSEDES,
                                                              explanation=d.reason or "superseded by governance decision", created_by=d.decided_by))
            self.bus.emit("knowledge.superseded", ref=old.ref, by_ref=v.ref, decision_id=d.id)
        d.resulting_refs = sorted(set(d.resulting_refs) | {v.ref})
        self.bus.emit("knowledge.approved", ref=v.ref, canonical_id=v.canonical_id, decision_id=d.id, scope=v.scope.key())

    # ---------------------------------------------------------------- Proposed change (§11 step 8, §31 "Propose Correction")

    def propose_revision(self, canonical_id: str, *, statement: str, by: str, reason: str, source_ids: list[str] | None = None,
                         evidence_ids: list[str] | None = None, authority: AuthorityType | None = None, scope: Scope | None = None,
                         title: str | None = None) -> KnowledgeNuggetVersion:
        prior = self.repo.latest_version(canonical_id)
        if prior is None:
            raise GovernanceError(f"unknown nugget {canonical_id}")
        return self.ingest_candidate(CandidateInput(
            title=title or prior.title, statement=statement, scope=scope or prior.scope,
            source_ids=source_ids if source_ids is not None else prior.source_refs,
            evidence_ids=evidence_ids if evidence_ids is not None else prior.evidence_refs,
            knowledge_type=prior.knowledge_type.value, authority_type=authority or prior.authority_type,
            confidence=prior.confidence, tags=prior.tags, graph_group=prior.graph_group, channel=AcquisitionChannel.FEEDBACK,
            created_by=by, canonical_id=canonical_id, change_reason=reason))

    def add_comment(self, ref: str, by: str, text: str) -> KnowledgeNuggetVersion:
        v = self.repo.require_version(ref)
        v.comments.append({"by": by, "at": now_iso(), "text": text})
        return self.repo.nuggets.put(v)   # comments are bookkeeping, not semantics

    def add_evidence(self, ref: str, evidence: Evidence, by: str) -> KnowledgeNuggetVersion:
        """Evidence may be attached to any version; semantics do not change, so no new version."""
        v = self.repo.require_version(ref)
        self.repo.evidence.put(evidence)
        if evidence.id not in v.evidence_refs:
            v.evidence_refs.append(evidence.id)
        if evidence.source_id not in v.source_refs:
            v.source_refs.append(evidence.source_id)
        self.auditor.record(who=by, what="knowledge.evidence.added", source=evidence.source_id, scope=v.scope, affected=[v.ref, evidence.id])
        return self.repo.nuggets.put(v)
