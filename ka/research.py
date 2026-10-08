"""research-orchestrator + research-agents (§3.2, §16, §17).

    Research Coordinator → {Domain, Enterprise Content, Standards/Regulatory, Internet, LLM Knowledge} agents
                        → Synthesis Agent → Candidate Knowledge Nuggets → (the one) governance pipeline

Agents produce Evidence and raw findings; the Synthesis Agent de-duplicates, clusters, proposes scope and
creates CANDIDATE nuggets. Agents never write to the graph and cannot approve knowledge (§17); the
governance service refuses decisions signed by an agent id. Every run records sources, evidence,
candidates, token usage and cost (§16). Agents see only sources within the mission's permitted
visibility (§42).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ka import config
from ka.audit import Auditor
from ka.conflict import similarity
from ka.events import EventBus
from ka.extraction import CandidateExtractor, classify_statement, normalize
from ka.governance import CandidateInput, GovernanceService
from ka.ingestion import IngestionService
from ka.llm import LLMProvider, LLMUsage, complete_json
from ka.model import Evidence, KnowledgeNuggetVersion, ResearchMission, ResearchRun, Scope
from ka.repository import Repository
from ka.scope import ScopeRegistry
from ka.security import is_safe_url
from ka.timeutil import now_iso
from ka.vocab import (
    VISIBILITY_ORDER,
    AcquisitionChannel,
    AuthorityType,
    MissionStatus,
    RunStatus,
    SourceType,
    Visibility,
)


@dataclass
class Finding:
    statement: str
    title: str
    excerpt: str
    source_id: str
    source_version_id: str
    locator: str | None
    authority: AuthorityType
    confidence: float
    evidence_id: str | None = None
    knowledge_type: str = "fact"
    tags: list[str] = field(default_factory=list)
    scope_hint: str | None = None


@dataclass
class AgentContext:
    mission: ResearchMission
    run: ResearchRun
    repo: Repository
    ingestion: IngestionService
    provider: LLMProvider | None
    usage: LLMUsage = field(default_factory=LLMUsage)
    discovered: list = field(default_factory=list)       # plan-07: SearchResults the discovery agent selected


class ResearchAgent(Protocol):
    agent_id: str

    def research(self, ctx: AgentContext) -> list[Finding]: ...


_LLM_RESEARCH_PROMPT = """You are the {role} for an enterprise knowledge system. Scope: {scope}.
Objective: {objective}
Research questions:
{questions}

{context}

Return a JSON array of findings. Each: {{"title": "...", "statement": "one self-contained sentence, numbers verbatim",
"knowledge_type": one of rule|policy|constraint|condition|process_step|state_transition|business_definition|concept|relationship|fact,
"excerpt": "the exact passage or, for your own knowledge, the authority you rely on", "confidence": 0-1,
"tags": [...], "scope_hint": "instance"|"domain"|"structure"|null}}.
State only what you can support. Mark anything you are unsure of with confidence below 0.5."""


def _ask(ctx: AgentContext, role: str, context: str) -> list[dict[str, Any]]:
    if ctx.provider is None:
        return []
    prompt = _LLM_RESEARCH_PROMPT.format(role=role, scope=f"{ctx.mission.scope_type.value}:{ctx.mission.scope_id}",
                                         objective=ctx.mission.objective, questions="\n".join(f"- {q}" for q in ctx.mission.research_questions) or "- (none)",
                                         context=context)
    got = complete_json(ctx.provider, prompt, default=[])
    ctx.usage.add(ctx.provider.last_usage)
    ctx.run.model = getattr(ctx.provider.last_usage, "model", None) or ctx.run.model
    return [g for g in got if isinstance(g, dict) and g.get("statement")] if isinstance(got, list) else []


def _record_source(ctx: AgentContext, *, title: str, text: str, source_type: SourceType, authority: AuthorityType,
                   location: str | None = None) -> tuple[str, str]:
    got = ctx.ingestion.record_derived(title=title, text=text, owner=ctx.mission.created_by,
                                       scope=Scope(scope_type=ctx.mission.scope_type, scope_id=ctx.mission.scope_id),
                                       channel=AcquisitionChannel.RESEARCH, source_type=source_type, authority=authority,
                                       visibility=ctx.mission.permitted_visibility, location=location,
                                       metadata={"mission_id": ctx.mission.mission_id, "run_id": ctx.run.run_id})
    ctx.run.sources_examined.append(got.source.id)
    return got.source.id, got.version.id


def _findings_from(ctx: AgentContext, items: list[dict[str, Any]], source_id: str, version_id: str, authority: AuthorityType,
                   locator: str | None = None) -> list[Finding]:
    out = []
    for it in items:
        st = str(it["statement"]).strip()
        out.append(Finding(statement=st, title=str(it.get("title") or st)[:80], excerpt=str(it.get("excerpt") or st),
                           source_id=source_id, source_version_id=version_id, locator=locator, authority=authority,
                           confidence=float(it.get("confidence", 0.5) or 0.5), knowledge_type=str(it.get("knowledge_type") or classify_statement(st).value),
                           tags=[str(t).lower() for t in it.get("tags", [])][:5], scope_hint=it.get("scope_hint")))
    return out


class EnterpriseContentAgent:
    """Reads sources already in the repository within the mission's scope chain and permitted visibility."""
    agent_id = "agent.enterprise_content"

    def __init__(self, registry: ScopeRegistry):
        self.registry = registry

    def research(self, ctx: AgentContext) -> list[Finding]:
        scope = Scope(scope_type=ctx.mission.scope_type, scope_id=ctx.mission.scope_id)
        chain = {scope.key()} | {s.key() for s in self.registry.ancestors(scope)} | {s.key() for s in self.registry.descendants(scope)}
        allowed = VISIBILITY_ORDER.index(ctx.mission.permitted_visibility)
        out: list[Finding] = []
        extractor = CandidateExtractor(ctx.provider)
        for src in ctx.repo.sources.all():
            if src.channel == AcquisitionChannel.RESEARCH or not src.scope or src.scope.key() not in chain:
                continue
            if VISIBILITY_ORDER.index(src.visibility) < allowed and src.owner != ctx.mission.created_by:
                continue   # §42 — a source more restricted than the requester's clearance, and not their own
            ver = ctx.repo.source_versions.get(src.current_version_id or "")
            if ver is None or not ver.text.strip():
                continue
            ctx.run.sources_examined.append(src.id)
            words = set(normalize(ctx.mission.objective + " " + " ".join(ctx.mission.research_questions)).split())
            relevant = [(loc, t) for loc, t in _sections(ver.text) if words & set(normalize(t).split())] or _sections(ver.text)[:3]
            for st in extractor.extract(title=src.title, sections=relevant, text=""):
                out.append(Finding(statement=st.statement, title=st.title, excerpt=st.excerpt, source_id=src.id, source_version_id=ver.id,
                                   locator=st.locator, authority=src.authority_type, confidence=st.confidence,
                                   knowledge_type=st.knowledge_type.value, tags=st.tags, scope_hint=st.scope_hint))
            if ctx.provider is not None:
                ctx.usage.add(ctx.provider.last_usage)
        return out


def _sections(text: str) -> list[tuple[str, str]]:
    out, n = [], 0
    for para in text.split("\n\n"):
        if para.strip():
            n += 1
            out.append((f"¶{n}", para.strip()))
    return out


class DomainResearchAgent:
    """Asks the model what the business type (domain) generally holds true. Authority: LLM-generated."""
    agent_id = "agent.domain_research"

    def research(self, ctx: AgentContext) -> list[Finding]:
        items = _ask(ctx, "Domain Research Agent", "Describe the standard rules, process steps, definitions and constraints of this "
                                                   "domain that an operator would expect every instance to inherit.")
        if not items:
            return []
        sid, vid = _record_source(ctx, title=f"Domain research: {ctx.mission.objective[:60]}", text=json.dumps(items, indent=1),
                                  source_type=SourceType.RESEARCH, authority=AuthorityType.LLM_GENERATED)
        return _findings_from(ctx, items, sid, vid, AuthorityType.LLM_GENERATED)


class StandardsRegulatoryAgent:
    agent_id = "agent.standards_regulatory"

    def research(self, ctx: AgentContext) -> list[Finding]:
        items = _ask(ctx, "Standards / Regulatory Agent", "List only requirements that come from laws, regulations, card-network "
                                                          "or industry standards, naming the standard in the excerpt.")
        if not items:
            return []
        sid, vid = _record_source(ctx, title=f"Standards & regulatory research: {ctx.mission.objective[:50]}", text=json.dumps(items, indent=1),
                                  source_type=SourceType.RESEARCH, authority=AuthorityType.EXTERNAL_REFERENCE)
        # The model is asserting what a standard says; until a person verifies the citation it is external reference, not regulation.
        return _findings_from(ctx, items, sid, vid, AuthorityType.EXTERNAL_REFERENCE)


class InternetResearchAgent:
    """Fetches the URLs discovery selected (plan-07) plus any the mission names explicitly, when KA_RESEARCH_INTERNET is on."""
    agent_id = "agent.internet_research"

    def research(self, ctx: AgentContext) -> list[Finding]:
        if not config.get("KA_RESEARCH_INTERNET"):
            ctx.run.notes += "internet research disabled (KA_RESEARCH_INTERNET=0); "
            return []
        # [block plan-07]
        explicit = [u for u in ctx.mission.preferred_source_types + ctx.mission.research_questions if u.startswith("http")]
        targets: list[tuple[str, dict]] = [(r.url, {"canonical_url": r.url, "publisher": r.publisher, "published_at": r.published_at,
                                                     "query": r.query, "discovered_rank": r.rank, "title": r.title}) for r in ctx.discovered]
        targets += [(u, {"canonical_url": u, "publisher": None, "published_at": None, "query": None, "discovered_rank": None}) for u in explicit[:5]]
        out: list[Finding] = []
        fetched: list[str] = []
        for url, meta in targets:
            ok, why = is_safe_url(url)
            if not ok:
                ctx.run.errors.append(f"{url}: blocked: {why}")
                continue
            try:
                got = ctx.ingestion.link(url=url, owner=ctx.mission.created_by, title=meta.get("title") or None,
                                         scope=Scope(scope_type=ctx.mission.scope_type, scope_id=ctx.mission.scope_id),
                                         authority=AuthorityType.INTERNET_RESEARCH, visibility=ctx.mission.permitted_visibility, metadata=meta)
            except httpx.HTTPError as e:  # pragma: no cover
                ctx.run.errors.append(f"{url}: {e}")
                continue
            ctx.run.sources_examined.append(got.source.id)
            fetched.append(url)
            if not got.extraction.text:
                continue
            items = _ask(ctx, "Internet Research Agent", f"SOURCE {url}:\n{got.extraction.text[:12000]}")
            out += _findings_from(ctx, items, got.source.id, got.version.id, AuthorityType.INTERNET_RESEARCH, locator=url)
        if ctx.run.discovery:
            ctx.run.discovery["fetched"] = fetched
        return out
        # [/block plan-07]


class LLMKnowledgeAgent:
    agent_id = "agent.llm_knowledge"

    def research(self, ctx: AgentContext) -> list[Finding]:
        items = _ask(ctx, "LLM Knowledge Agent", "Answer the research questions directly from your own knowledge. Be explicit "
                                                 "about uncertainty; these become low-authority candidates a person must approve.")
        if not items:
            return []
        sid, vid = _record_source(ctx, title=f"LLM knowledge: {ctx.mission.objective[:60]}", text=json.dumps(items, indent=1),
                                  source_type=SourceType.RESEARCH, authority=AuthorityType.LLM_GENERATED)
        return _findings_from(ctx, items, sid, vid, AuthorityType.LLM_GENERATED)


class SynthesisAgent:
    """§17: dedupe discoveries, cluster evidence, create candidate nuggets, note existing governed nuggets,
    propose scope, preserve every evidence/source relationship."""
    agent_id = "agent.synthesis"

    def __init__(self, repo: Repository, governance: GovernanceService, registry: ScopeRegistry):
        self.repo, self.governance, self.registry = repo, governance, registry

    def synthesize(self, ctx: AgentContext, findings: list[Finding]) -> list[KnowledgeNuggetVersion]:
        clusters: list[list[Finding]] = []
        for f in sorted(findings, key=lambda x: -x.confidence):
            for cl in clusters:
                if similarity(cl[0].statement, f.statement) >= config.get("KA_DUPLICATE_THRESHOLD"):
                    cl.append(f)
                    break
            else:
                clusters.append([f])
        scope = Scope(scope_type=ctx.mission.scope_type, scope_id=ctx.mission.scope_id)
        out: list[KnowledgeNuggetVersion] = []
        for cl in clusters:
            lead = cl[0]
            ev_ids, src_ids = [], []
            for f in cl:
                ev = self.repo.evidence.put(Evidence(source_id=f.source_id, source_version_id=f.source_version_id, locator=f.locator,
                                                     excerpt=f.excerpt, created_by=self.agent_id, research_run_id=ctx.run.run_id,
                                                     visibility=ctx.mission.permitted_visibility))
                ctx.run.evidence_created.append(ev.id)
                ev_ids.append(ev.id)
                if f.source_id not in src_ids:
                    src_ids.append(f.source_id)
            authority = max((f.authority for f in cl), key=lambda a: self.governance.authority.rank(a))
            target = scope
            if lead.scope_hint == "instance" and scope.scope_type.value != "INSTANCE":
                kids = self.registry.instances_under(scope)
                if len(kids) == 1:
                    target = kids[0]
            v = self.governance.ingest_candidate(CandidateInput(
                title=lead.title, statement=lead.statement, scope=target, source_ids=src_ids, evidence_ids=ev_ids,
                knowledge_type=lead.knowledge_type, authority_type=authority,
                confidence=round(min(0.95, max(f.confidence for f in cl) + 0.05 * (len(cl) - 1)), 2),
                tags=sorted({t for f in cl for t in f.tags})[:5], channel=AcquisitionChannel.RESEARCH, created_by=self.agent_id,
                research_run_id=ctx.run.run_id, visibility=ctx.mission.permitted_visibility))
            ctx.run.candidate_nuggets_created.append(v.ref)
            out.append(v)
        return out


class ResearchOrchestrator:
    """The Research Coordinator (§17)."""

    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, ingestion: IngestionService,
                 governance: GovernanceService, registry: ScopeRegistry, provider: LLMProvider | None,
                 agents: list[ResearchAgent] | None = None):
        self.repo, self.bus, self.auditor, self.ingestion = repo, bus, auditor, ingestion
        self.governance, self.registry, self.provider = governance, registry, provider
        from ka.discovery import DiscoveryAgent
        self.agents: list[ResearchAgent] = agents if agents is not None else [
            DiscoveryAgent(), EnterpriseContentAgent(registry), DomainResearchAgent(), StandardsRegulatoryAgent(), InternetResearchAgent(), LLMKnowledgeAgent()]
        self.synthesis = SynthesisAgent(repo, governance, registry)
        governance.research_agent_ids |= {a.agent_id for a in self.agents} | {self.synthesis.agent_id}
        governance.on_more_research = self._more_research

    def create_mission(self, *, scope: Scope, objective: str, by: str, questions: list[str] | None = None,
                       preferred_source_types: list[str] | None = None, trigger: str = "manual",
                       permitted_visibility: Visibility = Visibility.ENTERPRISE) -> ResearchMission:
        m = ResearchMission(scope_type=scope.scope_type, scope_id=scope.scope_id, objective=objective, research_questions=questions or [],
                            preferred_source_types=preferred_source_types or [], created_by=by, trigger=trigger,
                            permitted_visibility=permitted_visibility)
        self.repo.missions.put(m)
        self.auditor.record(who=by, what="research.mission.created", why=objective, scope=scope, affected=[m.mission_id])
        return m

    def run_mission(self, mission_id: str) -> ResearchRun:
        m = self.repo.missions.require(mission_id)
        run = ResearchRun(mission_id=m.mission_id, agent_id="coordinator", model=getattr(self.provider, "name", None))
        self.repo.runs.put(run)
        m.status = MissionStatus.RUNNING
        m.run_ids.append(run.run_id)
        self.repo.missions.put(m)
        self.bus.emit("research.started", mission_id=m.mission_id, run_id=run.run_id)
        ctx = AgentContext(mission=m, run=run, repo=self.repo, ingestion=self.ingestion, provider=self.provider)
        findings: list[Finding] = []
        for agent in self.agents:
            try:
                findings += agent.research(ctx)
            except Exception as e:  # noqa: BLE001 — one agent failing must not lose the others' evidence
                run.errors.append(f"{agent.agent_id}: {type(e).__name__}: {e}")
        candidates = self.synthesis.synthesize(ctx, findings)
        run.token_usage = ctx.usage.as_dict()
        run.cost = round(ctx.usage.cost_usd, 6)
        run.completed_at = now_iso()
        run.status = RunStatus.COMPLETED if not run.errors or candidates else RunStatus.FAILED
        self.repo.runs.put(run)
        m.candidate_refs += [c.ref for c in candidates]
        m.status = MissionStatus.COMPLETED if run.status == RunStatus.COMPLETED else MissionStatus.FAILED
        m.completed_at = run.completed_at
        self.repo.missions.put(m)
        self.bus.emit("research.completed", mission_id=m.mission_id, run_id=run.run_id, candidates=len(candidates))
        self.auditor.record(who="coordinator", what="research.completed", why=m.objective, scope=Scope(scope_type=m.scope_type, scope_id=m.scope_id),
                            affected=[m.mission_id, run.run_id] + [c.ref for c in candidates])
        return run

    def _more_research(self, v: KnowledgeNuggetVersion, reason: str) -> str:
        m = self.create_mission(scope=v.scope, objective=f"Resolve open question on {v.ref}: {v.title}. {reason}".strip(),
                                by="ka.governance", questions=[v.statement], trigger="governance")
        return m.mission_id

    # §18 — Domain Builder entry: reuse governed knowledge, research only the gap.
    def knowledge_for_domain(self, scope: Scope, *, objective: str, by: str, minimum: int = 1) -> dict[str, Any]:
        existing = self.repo.active_nuggets(scope)
        for anc in self.registry.ancestors(scope):
            existing += self.repo.active_nuggets(anc)
        if len(existing) >= minimum:
            return {"reused": [n.ref for n in existing], "mission_id": None}
        m = self.create_mission(scope=scope, objective=objective, by=by, trigger="domain_creation")
        return {"reused": [n.ref for n in existing], "mission_id": m.mission_id}
