"""knowledge-governance (§11–§13, §33): the ONE pipeline every channel converges on.

    Source → Extract Candidate → Normalize → Find Related → Classify (dup/support/conflict/extension) →
    Determine Scope → Determine Authority → Proposed Change → Governance Decision → Immutable Version → ACTIVE

Channels differ by provenance and authority, not lifecycle: `ingest_candidates` is used by content
ingestion, research synthesis and corrections alike. Nothing becomes ACTIVE without a GovernanceDecision,
and research agents cannot be the decider for their own candidates (§17).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ka import config
from ka.audit import Auditor
from ka.conflict import Analysis, ConflictDetector
from ka.events import EventBus
from ka.extraction import CandidateExtractor, CandidateStatement, TextExtraction, normalize
from ka.model import Evidence, GovernanceDecision, KnowledgeNuggetVersion, KnowledgeRelationship, ObjectRef, Scope, Source, SourceVersion, Subject
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
    PREDICATES,
    Visibility,
    narrowest_visibility,
    widens_visibility,
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
    # plan-03 (research-01 R2): the assertion, optional; stored on the version and bound at birth (block in ingest_candidate)
    subject: Subject | None = None
    predicate: str | None = None
    object: ObjectRef | None = None
    binding_method: str = "inferred"       # evidenced when a person or the extractor stated it


class GovernanceService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, registry: ScopeRegistry,
                 versioning: VersioningService, detector: ConflictDetector, extractor: CandidateExtractor,
                 authority_policy: config.AuthorityPolicy | None = None, binder=None, subjects=None, process_extractor=None):
        self.repo, self.bus, self.auditor, self.registry = repo, bus, auditor, registry
        self.versioning, self.detector, self.extractor = versioning, detector, extractor
        self.binder, self.subjects = binder, subjects          # plan-03: ka.binding.Binder, ka.identity.SubjectRegistry
        self.process_extractor = process_extractor             # plan-04: ka.process_extraction.ProcessExtractor
        self.scope_engine = ScopeDecisionEngine(registry)
        self.authority = authority_policy or config.AuthorityPolicy()
        self.on_more_research: Callable[[KnowledgeNuggetVersion, str], str] | None = None   # set by ResearchOrchestrator
        # [block plan-10] research-02 R2: set by the service to GraphChangeService.propose_retirement (a retired version's graph elements)
        self.on_retire: Callable[[KnowledgeNuggetVersion, str], Any] | None = None
        # [/block plan-10]
        self.research_agent_ids: set[str] = set()

    # ---------------------------------------------------------------- Extract (§11 step 1)

    def extract_from_source(self, source: Source, version: SourceVersion, extraction: TextExtraction, *,
                            actor: str, default_scope: Scope | None = None, analyze: bool = True,
                            process_pass: bool = True) -> list[KnowledgeNuggetVersion]:
        if not extraction.text.strip():
            version.extraction_report = {"statements": 0, "assertions": 0, "dropped": [], "method": "none",
                                         "extraction_version": version.extraction_version}
            self.repo.source_versions.put(version)
            return []
        statements = self.extractor.extract(title=source.title, sections=extraction.sections, text=extraction.text)
        scope = source.scope or default_scope
        if scope is None:
            raise GovernanceError("a source needs a scope (structure / parent domain / domain / instance) before extraction (§7)")
        out = []
        for st in statements:
            span = next((sp for sp in extraction.spans if sp.locator == st.locator), None)
            ev = self.repo.evidence.put(Evidence(source_id=source.id, source_version_id=version.id, locator=st.locator,
                                                 excerpt=st.excerpt, created_by=actor, visibility=source.visibility,
                                                 span_id=span.span_id if span else None, start=span.start if span else None,
                                                 end=span.end if span else None))
            out.append(self.ingest_candidate(CandidateInput(
                title=st.title, statement=st.statement, scope=self._scope_from_hint(scope, st),
                source_ids=[source.id], evidence_ids=[ev.id], knowledge_type=st.knowledge_type.value,
                authority_type=source.authority_type, confidence=st.confidence, tags=st.tags,
                normalized_meaning=st.normalized_meaning, graph_group=st.graph_group, channel=source.channel,
                created_by=actor, effective_from=source.effective_date, visibility=source.visibility,
            ), analyze=analyze))
        # [block plan-04]
        # research-01 R3: the second pass reads PROCESSES — assertions in EOS terms, each on an addressable span.
        # It adds to the statement pass, never alters it; what the text does not state is not emitted.
        report: dict = {"statements": len(out), "assertions": 0, "dropped": [], "method": "off",
                        "extraction_version": version.extraction_version}
        if process_pass and self.process_extractor is not None:
            got = self.process_extractor.extract(source.title, extraction)
            report["method"], report["dropped"] = got.method, list(got.dropped)
            for a in got.assertions:
                span = extraction.span(a.span_id)
                if span is None:
                    report["dropped"].append({"item": a.statement, "reason": f"span {a.span_id!r} not in this version"})
                    continue
                excerpt = a.excerpt if a.excerpt and a.excerpt in extraction.text[span.start:span.end] else extraction.text[span.start:span.end][:600]
                ev = self.repo.evidence.put(Evidence(source_id=source.id, source_version_id=version.id, locator=a.locator, excerpt=excerpt,
                                                     created_by=actor, visibility=source.visibility, span_id=span.span_id,
                                                     start=span.start, end=span.end))
                obj = (ObjectRef(kind=a.object_kind, value=a.object_name or a.object_value) if (a.object_kind and a.object_name)
                       else ObjectRef(value=a.object_value or a.object_name) if (a.object_value or a.object_name) else None)
                ktype = {"decomposes_into": "process_step", "performed_by": "relationship", "consumes": "relationship", "produces": "relationship",
                         "acts_on": "relationship", "governed_by": "rule", "emits": "state_transition", "transitions_to": "state_transition",
                         "typed_as": "concept"}.get(a.predicate, "business_definition" if a.predicate == "description" else "fact")
                out.append(self.ingest_candidate(CandidateInput(
                    title=a.statement[:80], statement=a.statement, scope=scope, source_ids=[source.id], evidence_ids=[ev.id],
                    knowledge_type=ktype, authority_type=source.authority_type, confidence=a.confidence, channel=source.channel,
                    created_by=actor, effective_from=source.effective_date, visibility=source.visibility, graph_group=a.subject_name,
                    subject=Subject(kind=a.subject_kind, canonical_key=a.subject_name.lower().replace(" ", "_"), name=a.subject_name),
                    predicate=a.predicate, object=obj, binding_method="evidenced"), analyze=analyze))
                report["assertions"] += 1
        version.extraction_report = report
        self.repo.source_versions.put(version)
        # [/block plan-04]
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
        # [block plan-03]
        # research-01 R2: an assertion is validated and resolved to a canonical subject BEFORE the version exists,
        # because subject/predicate/object are semantic and immutable once the version is governed.
        if inp.predicate is not None and inp.predicate not in PREDICATES:
            raise GovernanceError(f"unknown predicate {inp.predicate!r}; one of {', '.join(PREDICATES)}")
        subject = inp.subject
        if subject is not None:
            kinds = self.binder.registry.node_kinds() if (self.binder and self.binder.registry.loaded) else None
            if kinds and subject.kind not in kinds:
                raise GovernanceError(f"subject kind {subject.kind!r} is not an EOS node kind ({', '.join(kinds)})")
            if self.subjects is not None:
                rec, _ = self.subjects.resolve(subject.kind, subject.name or subject.canonical_key, tuple(subject.aliases))
                subject = Subject(kind=rec.kind, canonical_key=rec.canonical_key, name=rec.name, aliases=list(rec.aliases))
        obj = inp.object
        if obj is not None and obj.kind and obj.canonical_key is None and obj.value and self.subjects is not None:
            rec, _ = self.subjects.resolve(obj.kind, obj.value)
            obj = ObjectRef(kind=rec.kind, canonical_key=rec.canonical_key, value=obj.value)
        # [/block plan-03]
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
                                                 correction_refs=[inp.correction_id] if inp.correction_id else [],
                                                 subject=subject if subject is not None else prior.subject,
                                                 predicate=inp.predicate if inp.predicate is not None else prior.predicate,
                                                 object=obj if obj is not None else prior.object)
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
                subject=subject, predicate=inp.predicate, object=obj,
            )
        v.authority_rank = self.authority.rank(v.authority_type, v.scope_type, v.scope_id)
        self.registry.fill_hierarchy_fields(v)
        self.repo.nuggets.put(v)
        if self.binder is not None and (v.subject is not None or v.predicate is not None):
            self.binder.bind(v, method=inp.binding_method)          # plan-03: a binding record from birth
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

        # plan-10 (Q11): an exact duplicate of an ACTIVE same-scope nugget is flagged whether or not it ALSO contradicts others —
        # those contradictions already exist for the nugget it duplicates, so the candidate adds nothing and resolves as Keep Existing.
        exact = next((f.existing for f in analysis.duplicates if f.existing.status == NuggetStatus.ACTIVE and f.existing.scope == v.scope), None)
        if exact is not None:
            v.analysis["duplicate_of"] = exact.ref
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
            v.analysis.setdefault("duplicate_of", dup.ref)
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
               merged_statement: str | None = None, new_scope: Scope | None = None, existing_ref: str | None = None,
               widen_visibility: bool = False) -> GovernanceDecision:
        v = self.repo.require_version(ref)
        if by in self.research_agent_ids:
            raise GovernanceError("research agents cannot approve their own knowledge (§17)")
        if v.status not in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.ANALYZED}:
            raise GovernanceError(f"{ref} is {v.status.value}; only PENDING_REVIEW/CONFLICT candidates can be decided")
        partner = self.repo.version(existing_ref) if existing_ref else self._conflict_partner(v)
        d = GovernanceDecision(subject_ref=v.ref, related_refs=[partner.ref] if partner else [], outcome=outcome, decided_by=by,
                               reason=reason, comments=comments)
        before = {"status": v.status.value}

        # research-02 R1 (Q11, decided 2026-10-08): a candidate flagged duplicate_of an ACTIVE nugget never becomes a second ACTIVE
        # version. APPROVE is resolved as an automatic Keep Existing; either way the candidate's provenance moves to the existing one.
        dup = self.repo.version(v.analysis.get("duplicate_of") or "") if v.analysis.get("duplicate_of") else None
        # Same scope only: the same statement in a sibling instance is repeated instance knowledge for promotion (§25), not a duplicate.
        if dup is not None and dup.status == NuggetStatus.ACTIVE and dup.canonical_id != v.canonical_id and dup.scope == v.scope \
                and outcome in {DecisionOutcome.APPROVE, DecisionOutcome.KEEP_EXISTING}:
            if outcome == DecisionOutcome.APPROVE:
                d.outcome, d.automatic = DecisionOutcome.KEEP_EXISTING, True
                d.reason = f"duplicate of {dup.ref}; resolved as Keep Existing (Q11)" + (f" — {reason}" if reason else "")
                outcome = DecisionOutcome.KEEP_EXISTING
            d.related_refs = sorted(set(d.related_refs) | {dup.ref})
            self.attach_provenance(dup.ref, v, by=by, decision_id=d.id)
            v.analysis["resolved_as"] = "duplicate"
            v.analysis["conflict_open"] = False            # its contradictions belong to the nugget it duplicates
            v.governance_decision_id = d.id
            self.versioning.transition(v, NuggetStatus.REJECTED)
            self.bus.emit("knowledge.rejected", ref=v.ref, decision_id=d.id)
        elif outcome in {DecisionOutcome.APPROVE, DecisionOutcome.ACCEPT_NEW}:
            self._activate(v, d, supersede=[partner] if (partner and outcome == DecisionOutcome.ACCEPT_NEW) else None)
        elif outcome in {DecisionOutcome.REJECT, DecisionOutcome.KEEP_EXISTING}:
            v.governance_decision_id = d.id
            self.versioning.transition(v, NuggetStatus.REJECTED)
            self.bus.emit("knowledge.rejected", ref=v.ref, decision_id=d.id)
            # research-02 R2 (Q4): rejecting a re-review revision retires the prior version it was re-reviewing.
            # [block plan-27] research-04 R7 (Q18, decided 2026-10-09): the same mechanism carries a second review reason — a person's
            # explicit retirement request (`request_retirement`). One mechanism, two reasons; never a second retirement path.
            review_reason = "source revoked" if v.analysis.get("source_revoked") else ("retirement requested" if v.analysis.get("retirement_requested") else None)
            if outcome == DecisionOutcome.REJECT and review_reason:
                prior = self.repo.active_version(v.canonical_id)
                if prior is not None and prior.ref != v.ref:
                    self.versioning.transition(prior, NuggetStatus.OBSOLETE)
                    prior.comments.append({"by": by, "at": now_iso(), "text": f"retired: {review_reason} and re-review {v.ref} rejected — {reason}"})
                    self.repo.nuggets.put(prior)
                    self.repo.relationships.put(KnowledgeRelationship(from_ref=v.ref, to_ref=prior.ref, relationship_type=RelationshipType.OBSOLETES,
                                                                      explanation=f"{review_reason}; re-review rejected by {by}", created_by=by))
            # [/block plan-27]
                    d.related_refs = sorted(set(d.related_refs) | {prior.ref})
                    if self.on_retire is not None:
                        try:
                            prop = self.on_retire(prior, by)
                            if prop is not None:
                                d.resulting_refs.append(prop.id)
                        except Exception as e:  # noqa: BLE001 — the retirement proposal must not undo the decision
                            v.analysis["retirement_proposal_error"] = f"{type(e).__name__}: {e}"
                    else:
                        v.analysis["retirement_note"] = "no graph change service attached; retired in knowledge only"
                    self.bus.emit("knowledge.superseded", ref=prior.ref, by_ref=v.ref, decision_id=d.id)
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
            # [block plan-02]
            # research-01 R6: re-scoping may not widen who can see the knowledge unless the decision says so.
            needed = widens_visibility(v.visibility, new_scope.scope_type)
            if needed is not None and not widen_visibility:
                raise GovernanceError(f"re-scoping {v.ref} to {new_scope.key()} would widen its visibility "
                                      f"{v.visibility.value} → {needed.value}; pass widen_visibility=True to decide that explicitly")
            new_visibility = needed if needed is not None else v.visibility
            if needed is not None:
                d.visibility_change = {"from": v.visibility.value, "to": needed.value}
            # [/block plan-02]
            v.governance_decision_id = d.id
            self.versioning.transition(v, NuggetStatus.REJECTED)
            re_scoped = self.ingest_candidate(CandidateInput(
                title=v.title, statement=v.statement, scope=new_scope, source_ids=v.source_refs, evidence_ids=v.evidence_refs,
                knowledge_type=v.knowledge_type.value, authority_type=v.authority_type, confidence=v.confidence, tags=v.tags,
                normalized_meaning=v.normalized_meaning, graph_group=v.graph_group, channel=v.channel, created_by=by,
                change_reason=f"re-scoped from {v.scope.key()} by {by}: {reason}", effective_from=v.effective_from,
                visibility=new_visibility))
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
                         title: str | None = None, subject: Subject | None = None, predicate: str | None = None,
                         object: ObjectRef | None = None, binding_method: str = "evidenced") -> KnowledgeNuggetVersion:
        prior = self.repo.latest_version(canonical_id)
        if prior is None:
            raise GovernanceError(f"unknown nugget {canonical_id}")
        return self.ingest_candidate(CandidateInput(
            title=title or prior.title, statement=statement, scope=scope or prior.scope,
            source_ids=source_ids if source_ids is not None else prior.source_refs,
            evidence_ids=evidence_ids if evidence_ids is not None else prior.evidence_refs,
            knowledge_type=prior.knowledge_type.value, authority_type=authority or prior.authority_type,
            confidence=prior.confidence, tags=prior.tags, graph_group=prior.graph_group, channel=AcquisitionChannel.FEEDBACK,
            created_by=by, canonical_id=canonical_id, change_reason=reason,
            subject=subject, predicate=predicate, object=object, binding_method=binding_method))   # plan-03: pass-through (prior's kept when None)

    # [block plan-10] research-02 R1 + R2 (Q11, Q4 — decided 2026-10-08)
    def attach_provenance(self, target_ref: str, from_version: KnowledgeNuggetVersion, *, by: str, decision_id: str | None = None) -> KnowledgeNuggetVersion:
        """Append a candidate's sources and evidence to a governed nugget. Provenance is not meaning (SEMANTIC_FIELDS), so the
        version stays the same; the audit carries before/after lists."""
        target = self.repo.require_version(target_ref)
        if target.status not in {NuggetStatus.ACTIVE, NuggetStatus.APPROVED, NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE}:
            raise GovernanceError(f"{target_ref} is {target.status.value}; provenance attaches to a governed version only")
        before = {"source_refs": list(target.source_refs), "evidence_refs": list(target.evidence_refs)}
        target.source_refs = sorted(set(target.source_refs) | set(from_version.source_refs))
        target.evidence_refs = sorted(set(target.evidence_refs) | set(from_version.evidence_refs))
        self.repo.nuggets.put(target)
        self.auditor.record(who=by, what="knowledge.provenance.attached", why=f"from duplicate candidate {from_version.ref}", before=before,
                            after={"source_refs": list(target.source_refs), "evidence_refs": list(target.evidence_refs)}, scope=target.scope,
                            approval=decision_id, affected=[target.ref, from_version.ref])
        return target

    def reopen_for_revocation(self, source_id: str, *, by: str, revoked_at: str | None = None) -> list[str]:
        """Q4: every ACTIVE nugget derived from a revoked source returns to review as a same-statement revision that carries
        `source_revoked`; the prior stays ACTIVE until a person decides. A canonical id already under re-review is skipped."""
        out: list[str] = []
        for prior in self.repo.nuggets.where(lambda n: n.status == NuggetStatus.ACTIVE and source_id in n.source_refs):
            if self.repo.nuggets.where(lambda n: n.canonical_id == prior.canonical_id and n.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT}):
                continue
            remaining_sources = [s for s in prior.source_refs if s != source_id]
            remaining_evidence = [e for e in prior.evidence_refs if (ev := self.repo.evidence.get(e)) is None or ev.source_id != source_id]
            rev = self.propose_revision(prior.canonical_id, statement=prior.statement, by=by,
                                        reason=f"source {source_id} revoked; re-review on remaining evidence (Q4)",
                                        source_ids=remaining_sources, evidence_ids=remaining_evidence)
            rev.analysis["source_revoked"] = {"source_id": source_id, "revoked_at": revoked_at or now_iso(), "prior_ref": prior.ref}
            rev.analysis["remaining_sources"] = len(remaining_sources)
            self.repo.nuggets.put(rev)
            out.append(rev.ref)
        return out
    # [/block plan-10]

    # [block plan-27] research-04 R7 (Q18): a person retires an ACTIVE nugget the way a revoked source does — a same-statement revision
    # carrying a review reason; REJECT on it retires the prior and proposes the graph retirement; APPROVE keeps the knowledge.
    def request_retirement(self, canonical_id: str, *, by: str, why: str) -> KnowledgeNuggetVersion | None:
        if by in self.research_agent_ids:
            raise GovernanceError("research agents cannot request retirement of governed knowledge (§17)")
        prior = self.repo.active_version(canonical_id)
        if prior is None:
            raise GovernanceError(f"no ACTIVE version of {canonical_id} to retire")
        if self.repo.nuggets.where(lambda n: n.canonical_id == canonical_id and n.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT}):
            return None                                             # already under review — one re-review at a time, as reopen_for_revocation does
        rev = self.propose_revision(canonical_id, statement=prior.statement, by=by, reason=f"retirement requested by {by}: {why}",
                                    subject=prior.subject, predicate=prior.predicate, object=prior.object)
        rev.analysis["retirement_requested"] = {"by": by, "why": why, "prior_ref": prior.ref, "at": now_iso()}
        self.repo.nuggets.put(rev)
        self.auditor.record(who=by, what="knowledge.retirement.requested", why=why, scope=prior.scope, affected=[prior.ref, rev.ref])
        return rev
    # [/block plan-27]

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
