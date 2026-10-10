# [block plan-29]
"""KA's capabilities for AgentX (research-05 R2, R4): each is a `CapabilityDescriptor` in AgentX's exact shape plus a handler over a service
KA already has — no domain rule moves. plan-29 builds acquire, search, read and revise; plan-30 adds review, resolve_conflict and publish.

Descriptor keys are AgentX's set exactly (AgentX refuses extra keys): id, version, title, description, input_schema, output_schema,
permissions, discovery, health_endpoint, timeout, retry, invocation, idempotent, requires_approval, ui_schema (optional), deprecated.
Schemas are JSON Schema 2020-12 generated from the pydantic models below, so a model change is a schema change."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ka import config
from ka.agentx.contract import AgentXError
from ka.model import Scope
from ka.vocab import AuthorityType, ScopeType, Visibility

DESCRIPTOR_KEYS = ("id", "version", "title", "description", "input_schema", "output_schema", "permissions", "discovery", "health_endpoint",
                   "timeout", "retry", "invocation", "idempotent", "requires_approval", "ui_schema", "deprecated")
INVOKE_ENDPOINT = "/v1/capabilities/{capability_id}/invoke"


# ---- shared input/output models ------------------------------------------------------------------------------------

class ScopeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: ScopeType
    scope_id: str = Field(min_length=1)

    def scope(self) -> Scope:
        return Scope(scope_type=self.scope_type, scope_id=self.scope_id)


class Provenance(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    decision_id: Optional[str] = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


# knowledge.acquire
class TargetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structure_id: Optional[str] = None
    instance_id: Optional[str] = None
    leaf_id: Optional[str] = None


class AcquireIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text", "note", "link", "research", "gap"] = "text"
    name: str = Field(default="Acquired content", max_length=300)
    raw_content: Optional[str] = Field(default=None, max_length=2_000_000)
    uri: Optional[str] = Field(default=None, max_length=4000)
    question: Optional[str] = Field(default=None, max_length=4000, description="research/gap: what knowledge is missing")
    scope: ScopeIn
    authority: AuthorityType = AuthorityType.USER_KNOWLEDGE
    visibility: Visibility = Visibility.ENTERPRISE
    target: Optional[TargetIn] = None
    tenant_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Refusal(BaseModel):
    statement: str
    reason: str


class AcquireOut(BaseModel):
    source_id: Optional[str] = None
    source_version_id: Optional[str] = None
    candidates: list[str] = Field(default_factory=list, description="nugget version refs awaiting review (knowledge.review)")
    refusals: list[Refusal] = Field(default_factory=list)
    mission_id: Optional[str] = None
    request_id: Optional[str] = None
    mapped_into: list[str] = Field(default_factory=list, description="always empty here: a graph change needs governance first (knowledge.publish)")


# knowledge.search
class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    scope: Optional[ScopeIn] = None
    instance_id: Optional[str] = None
    domain_id: Optional[str] = None
    kind: Literal["nugget", "article", "all"] = "all"
    limit: int = Field(default=20, ge=1, le=100)
    tenant_id: Optional[str] = None


class Hit(BaseModel):
    id: str
    kind: str
    title: str
    snippet: str
    status: Optional[str] = None
    scope: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class SearchOut(BaseModel):
    hits: list[Hit]


# knowledge.read
class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, description="a nugget ref (KN-001:v2), a canonical id (KN-001), or a wiki key (process:<key>, subject:<key>, scope:<T>|<id>)")
    tenant_id: Optional[str] = None


class ReadOut(BaseModel):
    kind: str
    item: dict[str, Any]
    provenance: dict[str, Any]


# knowledge.revise
class ChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    retire: bool = False


class ReviseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1)
    change: ChangeIn
    rationale: str = Field(min_length=1, max_length=2000)
    tenant_id: Optional[str] = None


class ReviseOut(BaseModel):
    proposal_id: Optional[str] = Field(default=None, description="the candidate version ref that now awaits review")
    status: str
    review_required: bool = True
    note: Optional[str] = None


# ---- the registry ----------------------------------------------------------------------------------------------------

@dataclass
class Capability:
    id: str
    title: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    permissions: list[str]
    mode: Literal["sync", "async"]
    handler: Callable
    keywords: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    idempotent: bool = True
    requires_approval: bool = False
    timeout: dict[str, int] = field(default_factory=lambda: {"request_s": 30, "operation_s": 600})
    ui_schema: Optional[dict[str, Any]] = None
    version: str = "1.0.0"

    def descriptor(self) -> dict[str, Any]:
        d = {"id": self.id, "version": self.version, "title": self.title, "description": self.description,
             "input_schema": self.input_model.model_json_schema(), "output_schema": self.output_model.model_json_schema(),
             "permissions": list(self.permissions),
             "discovery": {"category": "knowledge", "tags": ["knowledge-acquisition", "governed-knowledge"], "keywords": self.keywords,
                           "examples": self.examples, "processes": []},
             "health_endpoint": "/healthz", "timeout": dict(self.timeout), "retry": {"max_attempts": 3, "backoff_s": 2},
             "invocation": {"endpoint": INVOKE_ENDPOINT, "mode": self.mode}, "idempotent": self.idempotent,
             "requires_approval": self.requires_approval, "deprecated": False}
        if self.ui_schema is not None:
            d["ui_schema"] = self.ui_schema
        return d

    def parse(self, raw: dict[str, Any]) -> BaseModel:
        try:
            return self.input_model.model_validate(raw)
        except ValidationError as e:
            raise AgentXError("schema_invalid", f"input does not match {self.id} {self.version}",
                              details={"errors": e.errors(include_url=False, include_context=False)}) from None


def check_tenant(tenant_id: Optional[str]) -> None:
    if tenant_id and tenant_id != config.get("KA_TENANT_ID"):
        raise AgentXError("forbidden", f"tenant {tenant_id!r} is not served by this KA (tenant {config.get('KA_TENANT_ID')!r})")


# ---- handlers --------------------------------------------------------------------------------------------------------

def _refusals(ka, version_id: str) -> list[dict[str, str]]:
    v = ka.repo.source_versions.get(version_id)
    out = []
    for d in (v.extraction_report or {}).get("dropped", []) if v else []:
        if isinstance(d, dict):
            out.append({"statement": str(d.get("item") or d.get("statement") or "")[:500], "reason": str(d.get("reason") or "dropped")})
    return out


def acquire(ka, ctx) -> dict[str, Any]:
    inp: AcquireIn = AcquireIn.model_validate(ctx.input)
    check_tenant(inp.tenant_id)
    scope, who = inp.scope.scope(), ctx.user
    if inp.target and inp.target.instance_id and scope.scope_type != ScopeType.INSTANCE:
        scope = Scope(scope_type=ScopeType.INSTANCE, scope_id=inp.target.instance_id)      # the target narrows extraction to that instance
    if inp.kind in ("text", "note", "link"):
        ctx.progress(0.1, "ingesting")
        if inp.kind == "link":
            if not inp.uri:
                raise AgentXError("schema_invalid", "kind=link needs uri")
            got = ka.ingestion.link(url=inp.uri, owner=who, scope=scope, title=inp.name, authority=inp.authority)
        else:
            if not inp.raw_content:
                raise AgentXError("schema_invalid", f"kind={inp.kind} needs raw_content")
            if inp.kind == "note":
                got = ka.ingestion.write_note(text=inp.raw_content, owner=who, scope=scope, title=inp.name)
            else:
                got = ka.ingestion.paste(text=inp.raw_content, owner=who, scope=scope, title=inp.name, authority=inp.authority, visibility=inp.visibility)
        ctx.progress(0.5, "extracting candidates", source_id=got.source.id)
        cands = ka.governance.extract_from_source(got.source, got.version, got.extraction, actor=who)
        ka.bus.emit("knowledge.acquisition.completed", source_id=got.source.id, operation_id=ctx.op.id)
        return AcquireOut(source_id=got.source.id, source_version_id=got.version.id, candidates=[c.ref for c in cands],
                          refusals=[Refusal(**r) for r in _refusals(ka, got.version.id)]).model_dump(mode="json")
    if inp.kind == "research":
        if not inp.question:
            raise AgentXError("schema_invalid", "kind=research needs question")
        m = ka.research.create_mission(scope=scope, objective=inp.question, by=who, questions=[inp.question], trigger="agentx")
        ctx.progress(0.05, "research mission started", mission_id=m.mission_id)
        before = {v.ref for v in ka.repo.nuggets.all()}
        ka.research.run_mission(m.mission_id)                         # this thread is already the background one
        made = [v.ref for v in ka.repo.nuggets.all() if v.ref not in before]
        ka.bus.emit("knowledge.acquisition.completed", mission_id=m.mission_id, operation_id=ctx.op.id)
        return AcquireOut(candidates=made, mission_id=m.mission_id).model_dump(mode="json")
    if not inp.question:
        raise AgentXError("schema_invalid", "kind=gap needs question")
    out = ka.runtime_guard.graph_gap_detected(scope=scope, question=inp.question, gap_description=str(inp.metadata.get("gap_description") or inp.question),
                                              requested_by="agentx", open_mission=bool(inp.metadata.get("open_mission", False)), principal=who,
                                              intent=str(inp.metadata.get("intent") or "answer"), correlation_id=ctx.op.correlation_id)
    return AcquireOut(request_id=out.request_id, mission_id=out.mission_id).model_dump(mode="json")


def _scope_filter(inp: SearchIn) -> Optional[Scope]:
    if inp.scope:
        return inp.scope.scope()
    if inp.instance_id:
        return Scope(scope_type=ScopeType.INSTANCE, scope_id=inp.instance_id)
    if inp.domain_id:
        return Scope(scope_type=ScopeType.DOMAIN, scope_id=inp.domain_id)
    return None


def search(ka, ctx) -> dict[str, Any]:
    inp: SearchIn = SearchIn.model_validate(ctx.input)
    check_tenant(inp.tenant_id)
    hits: list[Hit] = []
    if inp.kind in ("nugget", "all"):
        for h in ka.search.search(inp.query, filter="Current", scope=_scope_filter(inp), include_sources=False, limit=inp.limit):
            v = ka.repo.version(h.id)
            hits.append(Hit(id=h.id, kind="nugget", title=h.title, snippet=h.snippet, status=h.status, scope=h.scope,
                            provenance=Provenance(source_ids=list(v.source_refs) if v else [], decision_id=v.governance_decision_id if v else None)))
    if inp.kind in ("article", "all"):
        for w in ka.wiki.search(inp.query, limit=inp.limit):
            hits.append(Hit(id=w["key"], kind="article", title=w["title"], snippet=w["snippet"], status="computed",
                            provenance=Provenance()))
    return SearchOut(hits=hits[: inp.limit]).model_dump(mode="json")


def _resolve(ka, item_id: str):
    if ":" in item_id and item_id.split(":", 1)[0] in ("process", "subject", "scope", "page"):
        return "article", item_id
    if ":v" in item_id:
        v = ka.repo.version(item_id)
        if v is None:
            raise AgentXError("not_found", f"no nugget version {item_id!r}")
        return "nugget", v
    v = ka.repo.active_version(item_id) or ka.repo.latest_version(item_id)
    if v is None:
        raise AgentXError("not_found", f"no nugget {item_id!r}")
    return "nugget", v


def read(ka, ctx) -> dict[str, Any]:
    inp: ReadIn = ReadIn.model_validate(ctx.input)
    check_tenant(inp.tenant_id)
    kind, obj = _resolve(ka, inp.item_id)
    if kind == "article":
        try:
            art = ka.wiki.article(obj)
            ev = ka.wiki.evidence(obj)
        except KeyError as e:
            raise AgentXError("not_found", str(e.args[0]) if e.args else "not found") from None
        except ValueError as e:
            raise AgentXError("bad_request", str(e)) from None
        return ReadOut(kind="article", item=art, provenance={"statements": ev["items"], "sources": art["sources"]}).model_dump(mode="json")
    d = ka.nugget_detail(obj.ref)
    return ReadOut(kind="nugget", item=d["nugget"],
                   provenance={"sources": d["sources"], "evidence": d["evidence"], "decisions": d["governance"], "lineage": d["lineage"],
                               "graph_usage": d["graph_usage"], "graph_changes": d["graph_changes"]}).model_dump(mode="json")


def revise(ka, ctx) -> dict[str, Any]:
    inp: ReviseIn = ReviseIn.model_validate(ctx.input)
    check_tenant(inp.tenant_id)
    kind, obj = _resolve(ka, inp.item_id)
    if kind == "article":
        raise AgentXError("unsupported", "revise a wiki article through its draft (console) or revise the cited nugget by its ref",
                          details={"hint": "knowledge.read the article, then knowledge.revise a nugget ref it cites"})
    if inp.change.retire:
        rev = ka.governance.request_retirement(obj.canonical_id, by=ctx.user, why=inp.rationale)
        if rev is None:
            return ReviseOut(status="already_under_review", note="another revision of this nugget is awaiting review").model_dump(mode="json")
        return ReviseOut(proposal_id=rev.ref, status=rev.status.value).model_dump(mode="json")
    if not inp.change.statement:
        raise AgentXError("schema_invalid", "change.statement or change.retire is required")
    rev = ka.governance.propose_revision(obj.canonical_id, statement=inp.change.statement, by=ctx.user, reason=inp.rationale,
                                         subject=obj.subject, predicate=obj.predicate, object=obj.object)
    return ReviseOut(proposal_id=rev.ref, status=rev.status.value).model_dump(mode="json")


def registry(ka) -> dict[str, Capability]:
    caps = [
        Capability("knowledge.acquire", "Acquire knowledge",
                   "Ingest content (text, note, link), start a research mission, or raise a knowledge gap. Extracted statements become "
                   "CANDIDATE nuggets awaiting human review — nothing becomes governed knowledge or changes a graph here.",
                   AcquireIn, AcquireOut, ["knowledge.acquire"], "async", lambda ctx: acquire(ka, ctx),
                   ["ingest", "document", "source", "research", "gap"], ["Add this SOP to the merchant-acquiring domain"]),
        Capability("knowledge.search", "Search governed knowledge",
                   "Search ACTIVE governed nuggets and computed wiki articles. A governance/research read, not a runtime answer path "
                   "(runtime answers navigate the graph — KA Invariant 1).",
                   SearchIn, SearchOut, ["knowledge.read"], "sync", lambda ctx: search(ka, ctx), ["find", "lookup", "knowledge"],
                   ["What do we know about refund approval?"], timeout={"request_s": 30, "operation_s": 30}),
        Capability("knowledge.read", "Read knowledge with provenance",
                   "Read one nugget (by ref or canonical id) or one computed wiki article, with its provenance chain: sources, evidence "
                   "spans, governance decisions, lineage and graph usage.",
                   ReadIn, ReadOut, ["knowledge.read"], "sync", lambda ctx: read(ka, ctx), ["provenance", "lineage", "evidence"],
                   ["Why does KA say refunds need approval?"], timeout={"request_s": 30, "operation_s": 30}),
        Capability("knowledge.revise", "Propose a revision",
                   "Propose a changed statement for a governed nugget, or request its retirement. Creates a candidate that awaits human "
                   "review; the ACTIVE version is unchanged until a person decides.",
                   ReviseIn, ReviseOut, ["knowledge.revise"], "sync", lambda ctx: revise(ka, ctx), ["correct", "change", "retire"],
                   ["The refund threshold is now $750"], timeout={"request_s": 30, "operation_s": 30}),
    ]
    return {c.id: c for c in caps}
# [/block plan-29]
