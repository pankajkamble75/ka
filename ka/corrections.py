"""§3.3, §23 — Enterprise Console corrections. "Correct this" never edits the graph: it captures the
correction, resolves the graph element's knowledge lineage, suggests a scope (§24), and creates a
candidate revision in the governance pipeline. Only an applied Graph Change Proposal changes the graph.
"""
from __future__ import annotations

from ka.audit import Auditor
from ka.events import EventBus
from ka.governance import CandidateInput, GovernanceService
from ka.graph_adapter import GraphAdapter
from ka.ingestion import IngestionService
from ka.lineage import LineageService
from ka.model import Evidence, KnowledgeCorrection, Scope
from ka.repository import Repository
from ka.scope import ScopeDecisionEngine, ScopeRegistry
from ka.vocab import AcquisitionChannel, AuthorityType, CorrectionStatus, SourceType, Visibility


class CorrectionService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, governance: GovernanceService,
                 lineage: LineageService, adapter: GraphAdapter, registry: ScopeRegistry, ingestion: IngestionService):
        self.repo, self.bus, self.auditor, self.governance = repo, bus, auditor, governance
        self.lineage, self.adapter, self.registry, self.ingestion = lineage, adapter, registry, ingestion
        self.scope_engine = ScopeDecisionEngine(registry)

    def submit(self, *, graph_id: str | None, element_id: str | None, what_is_incorrect: str, correct_value: str, reason: str,
               by: str, comments: str | None = None, note: str | None = None, url: str | None = None,
               upload: tuple[str, bytes] | None = None, existing_source_ids: list[str] | None = None,
               user_scope: Scope | None = None, nugget_ref: str | None = None) -> KnowledgeCorrection:
        c = KnowledgeCorrection(graph_id=graph_id, element_id=element_id, what_is_incorrect=what_is_incorrect,
                                correct_value=correct_value, reason=reason, comments=comments, submitted_by=by,
                                user_scope=user_scope, source_refs=list(existing_source_ids or []))
        self.repo.corrections.put(c)
        self.bus.emit("correction.submitted", correction_id=c.id, graph_id=graph_id or "", element_id=element_id or "")

        # 1. Resolve existing knowledge lineage from the graph element (or the nugget the user pointed at).
        location: Scope | None = None
        if nugget_ref:
            c.resolved_lineage = [nugget_ref]
        elif graph_id and element_id:
            for dep in self.repo.dependencies_for_element(graph_id, element_id):
                c.resolved_lineage.append(dep.nugget_ref)
            for ln in self.adapter.get_graph_lineage(graph_id, element_id):
                ref = f"{ln.get('nugget_id')}:v{ln.get('version')}"
                if ref not in c.resolved_lineage and self.repo.version(ref):
                    c.resolved_lineage.append(ref)
            el = self.adapter.get_graph_element(graph_id, element_id)
            location = el.scope if el else None

        # 2. Supporting evidence: Note / Upload / URL / Existing Source (§23) — each becomes a Source + Evidence.
        text = f"Correction: {what_is_incorrect}\nCorrect value/meaning: {correct_value}\nReason: {reason}\n{note or ''}".strip()
        vis = Visibility.ENTERPRISE
        rec = self.ingestion.record_derived(title=f"Correction by {by}", text=text, owner=by, scope=location or user_scope,
                                            channel=AcquisitionChannel.FEEDBACK, source_type=SourceType.CORRECTION,
                                            authority=AuthorityType.USER_KNOWLEDGE, visibility=vis,
                                            metadata={"correction_id": c.id})
        evidence_ids = [self.repo.evidence.put(Evidence(source_id=rec.source.id, source_version_id=rec.version.id, locator="correction form",
                                                        excerpt=text[:600], created_by=by)).id]
        c.source_refs.append(rec.source.id)
        if upload:
            got = self.ingestion.upload(filename=upload[0], data=upload[1], owner=by, scope=location or user_scope,
                                        authority=AuthorityType.PROJECT_DOCUMENTATION)
            c.source_refs.append(got.source.id)
            evidence_ids.append(self.repo.evidence.put(Evidence(source_id=got.source.id, source_version_id=got.version.id, locator="uploaded",
                                                                excerpt=got.extraction.text[:600] or upload[0], created_by=by)).id)
        if url:
            got = self.ingestion.link(url=url, owner=by, scope=location or user_scope)
            c.source_refs.append(got.source.id)
            evidence_ids.append(self.repo.evidence.put(Evidence(source_id=got.source.id, source_version_id=got.version.id, locator=url,
                                                                excerpt=got.extraction.text[:600] or url, created_by=by)).id)
        c.evidence_refs = evidence_ids

        # 3. Scope recommendation (§24).
        original = self.repo.version(c.resolved_lineage[0]) if c.resolved_lineage else None
        decision = self.scope_engine.decide(statement=correct_value, location_scope=location or (original.scope if original else None),
                                            original_scope=original.scope if original else None, user_scope=user_scope,
                                            similar=[original] if original else [])
        c.suggested_scope = decision.scope
        c.scope_rationale = "; ".join(decision.rationale)
        c.status = CorrectionStatus.SCOPED
        self.repo.corrections.put(c)

        # 4. Create the knowledge correction proposal — a candidate (new version or new nugget) in governance.
        statement = correct_value if len(correct_value.split()) > 3 else (
            f"{original.title}: {correct_value}" if original else f"{what_is_incorrect} → {correct_value}")
        if original:
            cand = self.governance.ingest_candidate(CandidateInput(
                title=original.title, statement=statement, scope=decision.scope, source_ids=c.source_refs, evidence_ids=evidence_ids,
                knowledge_type=original.knowledge_type.value, authority_type=AuthorityType.USER_KNOWLEDGE, confidence=0.6,
                tags=original.tags, graph_group=original.graph_group, channel=AcquisitionChannel.FEEDBACK, created_by=by,
                canonical_id=original.canonical_id, correction_id=c.id, change_reason=f"correction {c.id}: {reason}"))
        else:
            cand = self.governance.ingest_candidate(CandidateInput(
                title=what_is_incorrect[:80], statement=statement, scope=decision.scope, source_ids=c.source_refs, evidence_ids=evidence_ids,
                authority_type=AuthorityType.USER_KNOWLEDGE, confidence=0.5, channel=AcquisitionChannel.FEEDBACK, created_by=by,
                correction_id=c.id, change_reason=f"correction {c.id}: {reason}"))
        c.candidate_ref = cand.ref
        c.status = CorrectionStatus.GOVERNED
        self.repo.corrections.put(c)
        self.auditor.record(who=by, what="correction.submitted", why=reason, scope=decision.scope, source=rec.source.id,
                            affected=[c.id, cand.ref] + c.resolved_lineage)
        return c

    def pending(self, scope: Scope | None = None) -> list[KnowledgeCorrection]:
        out = []
        for c in self.repo.corrections.all():
            if not c.candidate_ref:
                continue
            v = self.repo.version(c.candidate_ref)
            if v and v.status.value in {"CANDIDATE", "ANALYZED", "PENDING_REVIEW", "CONFLICT"}:
                if scope is None or (v.scope_type == scope.scope_type and v.scope_id == scope.scope_id):
                    out.append(c)
        return out
