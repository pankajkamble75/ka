"""knowledge-ui-api (§36): the FastAPI surface the Knowledge Console uses, plus the two endpoints the
Enterprise Console calls — `POST /corrections` ("Correct this", §23) and `GET /lineage/explain` ("Why?", §47).

Prefix mirrors enterprise-os: /api/knowledge-acquisition/<area>. The console itself is static HTML served
from /console. Nothing here is a question-answering endpoint (§43).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from ka import __version__, config, images
from ka.governance import GovernanceError
from ka.graph_change import ChangeError
from ka.model import Scope
from ka.security import require_access
from ka.service import KnowledgeAcquisition, _nugget_row
from ka.versioning import IllegalTransition, ImmutableVersionError
from ka.vocab import AuthorityType, DecisionOutcome, NuggetStatus, ScopeType, Visibility

PREFIX = "/api/knowledge-acquisition"
CONSOLE_DIR = Path(__file__).resolve().parent / "console"

_ka: KnowledgeAcquisition | None = None


def get_ka() -> KnowledgeAcquisition:
    global _ka
    if _ka is None:
        _ka = KnowledgeAcquisition()
    return _ka


def set_ka(instance: KnowledgeAcquisition | None) -> None:
    global _ka
    _ka = instance


def _scope(scope_type: str, scope_id: str) -> Scope:
    try:
        return Scope(scope_type=ScopeType(scope_type.upper()), scope_id=scope_id)
    except ValueError:
        raise HTTPException(400, f"unknown scope_type {scope_type!r}")


# ------------------------------------------------------------------------------------ schemas


class ScopeIn(BaseModel):
    scope_type: ScopeType
    scope_id: str
    parent_type: ScopeType | None = None
    parent_id: str | None = None
    name: str | None = None


class PasteIn(BaseModel):
    text: str
    title: str = "Pasted text"
    owner: str = "user"
    scope_type: ScopeType
    scope_id: str
    authority: AuthorityType = AuthorityType.USER_KNOWLEDGE
    visibility: Visibility = Visibility.ENTERPRISE
    markdown: bool = False
    extract: bool = True


# [block plan-03]
class AssertionIn(BaseModel):
    """A person stating what a note asserts, in EOS terms (research-01 R2)."""
    subject_kind: str | None = None          # process | entity | actor | rule | event | state | …
    subject_name: str | None = None
    predicate: str | None = None             # one of ka.vocab.PREDICATES
    object_value: str | None = None          # a type name for typed_as, or a literal
    object_kind: str | None = None           # when the object is another subject
    object_name: str | None = None

    def to_fields(self) -> dict[str, Any]:
        from ka.identity import canonical_key
        from ka.model import ObjectRef, Subject
        out: dict[str, Any] = {}
        if self.subject_name:
            out["subject"] = Subject(kind=self.subject_kind or "process", canonical_key=canonical_key(self.subject_name), name=self.subject_name)
        if self.predicate:
            out["predicate"] = self.predicate
        if self.object_value or self.object_name:
            out["object"] = ObjectRef(kind=self.object_kind, canonical_key=canonical_key(self.object_name) if self.object_name else None,
                                      value=self.object_value or self.object_name)
        if out:
            out["binding_method"] = "evidenced"
        return out


class GrammarRefreshIn(BaseModel):
    force: bool = False
# [/block plan-03]


class NoteIn(BaseModel):
    text: str
    title: str = "Note"
    owner: str = "user"
    scope_type: ScopeType
    scope_id: str
    extract: bool = True
    assertion: AssertionIn | None = None


class LinkIn(BaseModel):
    url: str
    title: str | None = None
    owner: str = "user"
    scope_type: ScopeType
    scope_id: str
    authority: AuthorityType = AuthorityType.EXTERNAL_REFERENCE
    extract: bool = True


class DecisionIn(BaseModel):
    outcome: DecisionOutcome
    by: str
    reason: str = ""
    comments: str | None = None
    merged_statement: str | None = None
    new_scope_type: ScopeType | None = None
    new_scope_id: str | None = None
    existing_ref: str | None = None
    widen_visibility: bool = False


class RevisionIn(BaseModel):
    statement: str
    by: str
    reason: str
    title: str | None = None
    scope_type: ScopeType | None = None
    scope_id: str | None = None
    assertion: AssertionIn | None = None


class ApplyIn(BaseModel):
    by: str
    reason: str = ""
    scope_type: ScopeType | None = None
    scope_id: str | None = None
    widen_visibility: bool = False


class CommentIn(BaseModel):
    by: str
    text: str


class CorrectionIn(BaseModel):
    """§23 correction form."""
    graph_id: str | None = None
    element_id: str | None = None
    nugget_ref: str | None = None
    what_is_incorrect: str
    correct_value: str
    reason: str = ""
    comments: str | None = None
    by: str = "user"
    note: str | None = None
    url: str | None = None
    existing_source_ids: list[str] = Field(default_factory=list)
    suggested_scope_type: ScopeType | None = None
    suggested_scope_id: str | None = None


class MissionIn(BaseModel):
    scope_type: ScopeType
    scope_id: str
    objective: str
    questions: list[str] = Field(default_factory=list)
    preferred_source_types: list[str] = Field(default_factory=list)
    by: str = "user"
    run: bool = True
    permitted_visibility: Visibility = Visibility.ENTERPRISE


class ProposalActionIn(BaseModel):
    by: str
    reason: str = ""


class PromotionDecisionIn(BaseModel):
    approve: bool
    by: str
    reason: str = ""
    widen_visibility: bool = False


class GapIn(BaseModel):
    scope_type: ScopeType
    scope_id: str
    question: str
    gap_description: str
    requested_by: str = "runtime"
    open_mission: bool = False


# ------------------------------------------------------------------------------------ routers

# [block plan-02]
router = APIRouter(prefix=PREFIX, tags=["knowledge-acquisition"], dependencies=[Depends(require_access)])


def _upload_cap() -> int:
    return config.get("KA_MAX_UPLOAD_MB") * 1024 * 1024


async def _read_capped(request: Request, file: UploadFile) -> bytes:
    """Refuse an oversize body before reading it when Content-Length says so, and after reading otherwise (413)."""
    cap = _upload_cap()
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > cap + 4096:     # multipart framing allowance
        raise HTTPException(413, f"upload exceeds KA_MAX_UPLOAD_MB ({config.get('KA_MAX_UPLOAD_MB')} MB)")
    data = await file.read(cap + 1)
    if len(data) > cap:
        raise HTTPException(413, f"upload exceeds KA_MAX_UPLOAD_MB ({config.get('KA_MAX_UPLOAD_MB')} MB)")
    return data
# [/block plan-02]


@router.get("/healthz")
def healthz(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"ok": True, "version": __version__, "provider": getattr(ka.provider, "name", "?"),
            "adapter": type(ka.adapter).__name__, "storage": str(ka.repo.root)}


# ---- scopes (§27, §28)

@router.get("/scopes")
def list_scopes(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    tree = []
    for s in ka.registry.all_scopes():
        p = ka.registry.parent_of(s)
        tree.append({"scope_type": s.scope_type.value, "scope_id": s.scope_id, "key": s.key(),
                     "name": ka.registry.names.get(s.key(), s.scope_id), "parent": p.key() if p else None,
                     "active_nuggets": len(ka.repo.active_nuggets(s))})
    return {"scopes": tree}


@router.post("/scopes")
def register_scope(body: ScopeIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    parent = Scope(scope_type=body.parent_type, scope_id=body.parent_id) if body.parent_type and body.parent_id else None
    try:
        ka.register_scope(Scope(scope_type=body.scope_type, scope_id=body.scope_id), parent, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/scopes/sync-from-graph")
def sync_scopes(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"registered": ka.sync_scopes_from_graph()}


@router.get("/scopes/{scope_type}/{scope_id}/dashboard")
def dashboard(scope_type: str, scope_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    s = _scope(scope_type, scope_id)
    return ka.instance_dashboard(s) if s.scope_type == ScopeType.INSTANCE else ka.domain_dashboard(s)


@router.get("/scopes/{scope_type}/{scope_id}/knowledge")
def scope_knowledge(scope_type: str, scope_id: str, status: str | None = None, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    s = _scope(scope_type, scope_id)
    statuses = [NuggetStatus(status)] if status else None
    return {"nuggets": [_nugget_row(n) for n in ka.repo.nuggets_in_scope(s, statuses)]}


@router.get("/scopes/{scope_type}/{scope_id}/sources")
def scope_sources(scope_type: str, scope_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    s = _scope(scope_type, scope_id)
    return {"sources": [x.model_dump(mode="json") for x in ka.repo.sources.where(lambda src: src.scope is not None and src.scope.key() == s.key())]}


@router.get("/scopes/{scope_type}/{scope_id}/history")
def scope_history(scope_type: str, scope_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    s = _scope(scope_type, scope_id)
    return {"audit": [a.model_dump(mode="json") for a in ka.repo.audit() if a.scope and a.scope.key() == s.key()][-200:]}


@router.get("/scopes/{scope_type}/{scope_id}/active-at")
def active_at(scope_type: str, scope_id: str, when: str = Query(..., description="ISO timestamp"),
              ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"when": when, "nuggets": [_nugget_row(n) for n in ka.repo.active_at(when, _scope(scope_type, scope_id))]}


# ---- ingestion (§3.1)

@router.post("/sources/upload")
async def upload(request: Request, file: UploadFile = File(...), owner: str = Form("user"), scope_type: str = Form(...), scope_id: str = Form(...),
                 authority: str = Form(AuthorityType.PROJECT_DOCUMENTATION.value), title: str | None = Form(None),
                 extract: bool = Form(True), ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    data = await _read_capped(request, file)
    s = _scope(scope_type, scope_id)
    got = ka.ingestion.upload(filename=file.filename or "upload", data=data, owner=owner, scope=s, title=title, authority=AuthorityType(authority))
    return _ingested(ka, got, extract, owner)


@router.post("/sources/paste")
def paste(body: PasteIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    got = ka.ingestion.paste(text=body.text, owner=body.owner, scope=Scope(scope_type=body.scope_type, scope_id=body.scope_id), title=body.title,
                             authority=body.authority, visibility=body.visibility, markdown=body.markdown)
    return _ingested(ka, got, body.extract, body.owner)


@router.post("/sources/note")
def note(body: NoteIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    scope = Scope(scope_type=body.scope_type, scope_id=body.scope_id)
    got = ka.ingestion.write_note(text=body.text, owner=body.owner, scope=scope, title=body.title)
    if body.assertion and body.assertion.to_fields():
        from ka.governance import CandidateInput
        from ka.model import Evidence
        ev = ka.repo.evidence.put(Evidence(source_id=got.source.id, source_version_id=got.version.id, locator="note", excerpt=body.text[:600], created_by=body.owner))
        try:
            cand = ka.governance.ingest_candidate(CandidateInput(
                title=body.title if body.title != "Note" else body.text[:80], statement=body.text.strip(), scope=scope,
                source_ids=[got.source.id], evidence_ids=[ev.id], created_by=body.owner, **body.assertion.to_fields()))
        except GovernanceError as e:
            raise HTTPException(400, str(e))
        return {"source": got.source.model_dump(mode="json"), "source_version": got.version.model_dump(mode="json", exclude={"text"}),
                "extraction_status": got.extraction.status.value, "extraction_note": None, "is_new_version": got.is_new_version,
                "candidates": [_nugget_row(cand)]}
    return _ingested(ka, got, body.extract, body.owner)


@router.post("/sources/link")
def link(body: LinkIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    got = ka.ingestion.link(url=body.url, owner=body.owner, scope=Scope(scope_type=body.scope_type, scope_id=body.scope_id), title=body.title,
                            authority=body.authority)
    return _ingested(ka, got, body.extract, body.owner)


def _ingested(ka: KnowledgeAcquisition, got, extract: bool, actor: str) -> dict[str, Any]:
    cands = []
    if extract:
        try:
            cands = ka.governance.extract_from_source(got.source, got.version, got.extraction, actor=actor)
        except GovernanceError as e:
            raise HTTPException(400, str(e))
    return {"source": got.source.model_dump(mode="json"), "source_version": got.version.model_dump(mode="json", exclude={"text"}),
            "extraction_status": got.extraction.status.value, "extraction_note": got.extraction.note,
            "is_new_version": got.is_new_version, "candidates": [_nugget_row(c) for c in cands]}


@router.get("/sources")
def list_sources(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"sources": [s.model_dump(mode="json") for s in ka.repo.sources.all()]}


@router.get("/sources/{source_id}")
def get_source(source_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    s = ka.repo.sources.get(source_id)
    if s is None:
        raise HTTPException(404, "source not found")
    versions = ka.repo.source_versions.where(lambda v: v.source_id == source_id)
    nuggets = ka.repo.nuggets.where(lambda n: source_id in n.source_refs)
    return {"source": s.model_dump(mode="json"), "versions": [v.model_dump(mode="json") for v in versions],
            "nuggets": [_nugget_row(n) for n in nuggets]}


# ---- nuggets (§31)

@router.get("/nuggets")
def list_nuggets(status: str | None = None, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    ns = ka.repo.nuggets_by_status(NuggetStatus(status)) if status else ka.repo.nuggets.all()
    return {"nuggets": [_nugget_row(n) for n in sorted(ns, key=lambda n: n.created_at, reverse=True)]}


@router.get("/nuggets/{canonical_id}/versions")
def versions(canonical_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    vs = ka.repo.versions_of(canonical_id)
    if not vs:
        raise HTTPException(404, "unknown nugget")
    return {"versions": [v.model_dump(mode="json") for v in vs]}


@router.get("/nuggets/{canonical_id}/compare")
def compare(canonical_id: str, a: int, b: int, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    va, vb = ka.repo.version(f"{canonical_id}:v{a}"), ka.repo.version(f"{canonical_id}:v{b}")
    if va is None or vb is None:
        raise HTTPException(404, "version not found")
    return {"a": va.ref, "b": vb.ref, "diff": {k: list(v) for k, v in ka.versioning.diff(va, vb).items()}}


@router.get("/nugget/{ref}")
def nugget(ref: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        return ka.nugget_detail(ref)
    except KeyError:
        raise HTTPException(404, "nugget version not found")


@router.post("/nugget/{ref}/decide")
def decide(ref: str, body: DecisionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    new_scope = Scope(scope_type=body.new_scope_type, scope_id=body.new_scope_id) if body.new_scope_type and body.new_scope_id else None
    try:
        d = ka.governance.decide(ref, body.outcome, by=body.by, reason=body.reason, comments=body.comments,
                                 merged_statement=body.merged_statement, new_scope=new_scope, existing_ref=body.existing_ref,
                                 widen_visibility=body.widen_visibility)
    except (GovernanceError, IllegalTransition, ImmutableVersionError, KeyError) as e:
        raise HTTPException(409, str(e))
    return {"decision": d.model_dump(mode="json"), "nugget": _nugget_row(ka.repo.require_version(ref))}


@router.post("/nugget/{ref}/apply")
def apply_nugget(ref: str, body: ApplyIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    scope = Scope(scope_type=body.scope_type, scope_id=body.scope_id) if body.scope_type and body.scope_id else None
    try:
        return ka.apply_nugget(ref, scope=scope, by=body.by, reason=body.reason, widen_visibility=body.widen_visibility)
    except (GovernanceError, IllegalTransition, KeyError) as e:
        raise HTTPException(409, str(e))


@router.get("/dashboard")
def engine_dashboard(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return ka.engine_status()


@router.post("/nuggets/{canonical_id}/propose-revision")
def propose_revision(canonical_id: str, body: RevisionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    scope = Scope(scope_type=body.scope_type, scope_id=body.scope_id) if body.scope_type and body.scope_id else None
    try:
        v = ka.governance.propose_revision(canonical_id, statement=body.statement, by=body.by, reason=body.reason, title=body.title, scope=scope,
                                           **(body.assertion.to_fields() if body.assertion else {}))
    except GovernanceError as e:
        raise HTTPException(400, str(e))
    return {"candidate": _nugget_row(v)}


@router.post("/nugget/{ref}/comment")
def comment(ref: str, body: CommentIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        v = ka.governance.add_comment(ref, body.by, body.text)
    except KeyError:
        raise HTTPException(404, "nugget version not found")
    return {"comments": v.comments}


@router.get("/nugget/{ref}/where-used")
def where_used(ref: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"ref": ref, "used_by": [d.model_dump(mode="json") for d in ka.lineage.where_used(ref)]}


# ---- governance queues (§32) and conflicts (§33)

@router.get("/needs-attention")
def needs_attention(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return ka.needs_attention()


@router.get("/conflicts/{ref}")
def conflict_view(ref: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    v = ka.repo.version(ref)
    if v is None:
        raise HTTPException(404, "nugget version not found")
    out = []
    for f in v.analysis.get("findings", []):
        if f["relationship"] not in {"CONTRADICTS", "DUPLICATES"}:
            continue
        e = ka.repo.version(f["existing_ref"])
        if e is None:
            continue
        out.append({"existing": _nugget_row(e), "existing_sources": [s.model_dump(mode="json") for s in ka.repo.sources_for(e)],
                    "existing_scope": e.scope.key(), "existing_effective": [e.effective_from, e.effective_to],
                    "candidate": _nugget_row(v), "candidate_sources": [s.model_dump(mode="json") for s in ka.repo.sources_for(v)],
                    "proposed_scope": v.analysis.get("scope_decision", {}).get("scope", v.scope.key()),
                    "candidate_effective": [v.effective_from, v.effective_to],
                    "authority_comparison": {"existing": [e.authority_type.value, e.authority_rank], "candidate": [v.authority_type.value, v.authority_rank]},
                    "explanation": f})
    return {"ref": ref, "conflicts": out,
            "actions": [o.value for o in DecisionOutcome if o != DecisionOutcome.AUTO_RESOLVED_BY_AUTHORITY]}


# ---- corrections (§23) — called from the Enterprise Console

@router.post("/corrections")
def submit_correction(body: CorrectionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    user_scope = Scope(scope_type=body.suggested_scope_type, scope_id=body.suggested_scope_id) if body.suggested_scope_type and body.suggested_scope_id else None
    c = ka.corrections.submit(graph_id=body.graph_id, element_id=body.element_id, nugget_ref=body.nugget_ref,
                              what_is_incorrect=body.what_is_incorrect, correct_value=body.correct_value, reason=body.reason, by=body.by,
                              comments=body.comments, note=body.note, url=body.url, existing_source_ids=body.existing_source_ids, user_scope=user_scope)
    return {"correction": c.model_dump(mode="json")}


@router.post("/corrections/upload")
async def submit_correction_with_file(request: Request, file: UploadFile = File(...), graph_id: str | None = Form(None), element_id: str | None = Form(None),
                                      nugget_ref: str | None = Form(None), what_is_incorrect: str = Form(...), correct_value: str = Form(...),
                                      reason: str = Form(""), by: str = Form("user"), ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    data = await _read_capped(request, file)
    c = ka.corrections.submit(graph_id=graph_id, element_id=element_id, nugget_ref=nugget_ref, what_is_incorrect=what_is_incorrect,
                              correct_value=correct_value, reason=reason, by=by, upload=(file.filename or "evidence", data))
    return {"correction": c.model_dump(mode="json")}


@router.get("/corrections")
def list_corrections(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"corrections": [c.model_dump(mode="json") for c in ka.repo.corrections.all()]}


# ---- lineage (§15) — "Why?" from the Enterprise Console

@router.get("/lineage/explain")
def explain(graph_id: str, element_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return ka.explain_element(graph_id, element_id)


@router.get("/lineage/graph/{graph_id}")
def graph_lineage(graph_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    deps = ka.repo.dependencies.where(lambda d: d.graph_id == graph_id and d.active)
    return {"graph_id": graph_id, "dependencies": [d.model_dump(mode="json") for d in deps]}


# ---- graph change proposals (§22)

@router.get("/graph-changes")
def proposals(status: str | None = None, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    ps = ka.repo.proposals.all()
    if status:
        ps = [p for p in ps if p.status.value == status]
    return {"proposals": [p.model_dump(mode="json", exclude={"changes", "before_state", "proposed_after_state"}) for p in
                          sorted(ps, key=lambda p: p.created_at, reverse=True)]}


@router.get("/graph-changes/{proposal_id}")
def proposal(proposal_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    p = ka.repo.proposals.get(proposal_id)
    if p is None:
        raise HTTPException(404, "proposal not found")
    return {"proposal": p.model_dump(mode="json"), "executions": [e.model_dump(mode="json") for e in ka.repo.executions.where(lambda e: e.proposal_id == p.id)]}


@router.post("/graph-changes/{proposal_id}/{action}")
def proposal_action(proposal_id: str, action: str, body: ProposalActionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        if action == "validate":
            p = ka.graph_change.validate(proposal_id)
        elif action == "approve":
            p = ka.graph_change.approve(proposal_id, by=body.by, reason=body.reason)
        elif action == "reject":
            p = ka.graph_change.reject(proposal_id, by=body.by, reason=body.reason)
        elif action == "apply":
            ex = ka.graph_change.apply(proposal_id, by=body.by)
            return {"execution": ex.model_dump(mode="json"), "proposal": ka.repo.proposals.require(proposal_id).model_dump(mode="json", exclude={"changes"})}
        else:
            raise HTTPException(404, f"unknown action {action}")
    except (ChangeError, KeyError) as e:
        raise HTTPException(409, str(e))
    return {"proposal": p.model_dump(mode="json", exclude={"changes"})}


@router.post("/graph-executions/{execution_id}/rollback")
def rollback(execution_id: str, body: ProposalActionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        rb = ka.graph_change.rollback(execution_id, by=body.by, reason=body.reason)
    except (ChangeError, KeyError) as e:
        raise HTTPException(409, str(e))
    return {"execution": rb.model_dump(mode="json")}


# ---- research (§16, §34)

@router.post("/research/missions")
def create_mission(body: MissionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    m = ka.research.create_mission(scope=Scope(scope_type=body.scope_type, scope_id=body.scope_id), objective=body.objective, by=body.by,
                                   questions=body.questions, preferred_source_types=body.preferred_source_types,
                                   permitted_visibility=body.permitted_visibility)
    run = ka.research.run_mission(m.mission_id) if body.run else None
    return {"mission": ka.repo.missions.require(m.mission_id).model_dump(mode="json"), "run": run.model_dump(mode="json") if run else None}


@router.post("/research/missions/{mission_id}/run")
def run_mission(mission_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        run = ka.research.run_mission(mission_id)
    except KeyError:
        raise HTTPException(404, "mission not found")
    return {"run": run.model_dump(mode="json")}


@router.get("/research/missions")
def missions(scope_type: str | None = None, scope_id: str | None = None, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    ms = ka.repo.missions.all()
    if scope_type and scope_id:
        ms = [m for m in ms if m.scope_type.value == scope_type.upper() and m.scope_id == scope_id]
    return {"missions": [m.model_dump(mode="json") for m in sorted(ms, key=lambda m: m.created_at, reverse=True)],
            "runs": [r.model_dump(mode="json") for r in ka.repo.runs.all()]}


@router.get("/research/missions/{mission_id}")
def mission(mission_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    m = ka.repo.missions.get(mission_id)
    if m is None:
        raise HTTPException(404, "mission not found")
    runs = [r.model_dump(mode="json") for r in ka.repo.runs.where(lambda r: r.mission_id == mission_id)]
    cands = [_nugget_row(v) for v in (ka.repo.version(ref) for ref in m.candidate_refs) if v]
    sources = [s.model_dump(mode="json") for s in ka.repo.sources.where(lambda s: s.metadata.get("mission_id") == mission_id)]
    return {"mission": m.model_dump(mode="json"), "runs": runs, "candidates": cands, "sources_discovered": sources}


# ---- promotion (§25)

@router.post("/promotions/detect/{scope_type}/{scope_id}")
def detect_promotions(scope_type: str, scope_id: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"proposals": [p.model_dump(mode="json") for p in ka.promotion.detect(_scope(scope_type, scope_id))]}


@router.post("/promotions/{promotion_id}/decide")
def decide_promotion(promotion_id: str, body: PromotionDecisionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        p = ka.promotion.decide(promotion_id, approve=body.approve, by=body.by, reason=body.reason, widen_visibility=body.widen_visibility)
    except KeyError:
        raise HTTPException(404, "promotion not found")
    except GovernanceError as e:
        raise HTTPException(409, str(e))
    return {"promotion": p.model_dump(mode="json")}


# ---- search (§35)

@router.get("/search")
def search(q: str = "", filter: str = "All Knowledge", scope_type: str | None = None, scope_id: str | None = None, status: str | None = None,
           authority: str | None = None, knowledge_type: str | None = None, author: str | None = None, tag: list[str] | None = Query(None),
           source_id: str | None = None, effective_on: str | None = None, graph_element_id: str | None = None,
           ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    scope = _scope(scope_type, scope_id) if scope_type and scope_id else None
    hits = ka.search.search(q, filter=filter, scope=scope, status=status, authority=authority, tags=tag, author=author,
                            knowledge_type=knowledge_type, source_id=source_id, effective_on=effective_on, graph_element_id=graph_element_id)
    return {"hits": [h.__dict__ for h in hits], "filters": list(__import__("ka.search", fromlist=["FILTERS"]).FILTERS)}


# ---- runtime guard (§43) — called by the Enterprise Console runtime, never returns knowledge

@router.post("/runtime/graph-gap")
def graph_gap(body: GapIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    out = ka.runtime_guard.graph_gap_detected(scope=Scope(scope_type=body.scope_type, scope_id=body.scope_id), question=body.question,
                                              gap_description=body.gap_description, requested_by=body.requested_by, open_mission=body.open_mission)
    return {"signal": out.signal, "request_id": out.request_id, "mission_id": out.mission_id}


# ---- grammar, bindings, subjects (research-01 R2, R8 — plan-03)

@router.get("/grammar")
def grammar(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return ka.grammar.descriptor()


@router.post("/grammar/refresh")
def grammar_refresh(body: GrammarRefreshIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    from ka.grammar import GrammarMismatch
    try:
        snap = ka.grammar.refresh(force=body.force)
    except GrammarMismatch as e:
        raise HTTPException(409, str(e))
    return {"snapshot": snap.__dict__ if snap else None, "descriptor": ka.grammar.descriptor()}


@router.post("/grammar/rebind-all")
def rebind_all(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    from ka.grammar import GrammarMismatch
    try:
        return {"rebound": ka.binder.rebind_all(), **ka.grammar.versions()}
    except GrammarMismatch as e:
        raise HTTPException(409, str(e))


@router.get("/nugget/{ref}/binding")
def nugget_binding(ref: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    if ka.repo.version(ref) is None:
        raise HTTPException(404, "nugget version not found")
    b = ka.repo.binding_for(ref)
    return {"ref": ref, "binding": b.model_dump(mode="json") if b else None, "history": [x.model_dump(mode="json") for x in ka.repo.bindings_of(ref)]}


@router.post("/nugget/{ref}/rebind")
def nugget_rebind(ref: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    v = ka.repo.version(ref)
    if v is None:
        raise HTTPException(404, "nugget version not found")
    return {"binding": ka.binder.bind(v).model_dump(mode="json")}


@router.get("/subjects")
def subjects(kind: str | None = None, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    recs = ka.repo.subjects.all()
    if kind:
        recs = [r for r in recs if r.kind == kind]
    return {"subjects": [r.model_dump(mode="json") | {"nuggets": len(ka.repo.nuggets_by_subject(r.canonical_key))} for r in sorted(recs, key=lambda r: r.name.lower())]}


@router.get("/subjects/{key}")
def subject(key: str, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    rec = ka.repo.subjects.get(key)
    if rec is None:
        raise HTTPException(404, "subject not found")
    ns = ka.repo.nuggets_by_subject(key)
    return {"subject": rec.model_dump(mode="json"), "nuggets": [_nugget_row(n) | {"binding": (b.model_dump(mode="json") if (b := ka.repo.binding_for(n.ref)) else None)} for n in ns]}


# ---- images for conversations (not knowledge; see ka/images.py)

class ImageIn(BaseModel):
    data: str                      # base64
    name: str = "pasted image"
    caption: str = ""


class CaptionIn(BaseModel):
    caption: str


@router.get("/images")
def list_images(ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"images": images.list_images(ka.repo.root)}


@router.post("/images")
def save_image(body: ImageIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        return {"image": images.save(ka.repo.root, data_b64=body.data, name=body.name, caption=body.caption)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/images/{number}")
def get_image(number: int, ka: KnowledgeAcquisition = Depends(get_ka)) -> Response:
    try:
        data, mime = images.read(ka.repo.root, number)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/images/{number}/caption")
def caption_image(number: int, body: CaptionIn, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        return {"image": images.update(ka.repo.root, number, body.caption)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/images/{number}/delete")
def delete_image(number: int, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    try:
        return images.delete(ka.repo.root, number)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ---- audit / events (§38, §41)

@router.get("/audit")
def audit(object_id: str | None = None, limit: int = 200, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    recs = ka.auditor.for_object(object_id) if object_id else ka.repo.audit()
    return {"audit": [a.model_dump(mode="json") for a in recs[-limit:]]}


@router.get("/events")
def events(limit: int = 200, ka: KnowledgeAcquisition = Depends(get_ka)) -> dict[str, Any]:
    return {"events": ka.repo.events()[-limit:]}


@router.get("/vocab")
def vocab() -> dict[str, Any]:
    return {"scope_types": [s.value for s in ScopeType], "statuses": [s.value for s in NuggetStatus],
            "authorities": [a.value for a in AuthorityType], "outcomes": [o.value for o in DecisionOutcome],
            "visibilities": [v.value for v in Visibility]}


# ------------------------------------------------------------------------------------ app


def create_app(ka: KnowledgeAcquisition | None = None) -> FastAPI:
    if ka is not None:
        set_ka(ka)
    app = FastAPI(title="Enterprise OS — Knowledge Acquisition", version=__version__,
                  description="Acquire · Govern · Know · Compile · (Graph) · Operate · Observe/Correct")
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        return HTMLResponse('<meta http-equiv="refresh" content="0; url=/console/">')

    @app.get("/console/", include_in_schema=False)
    @app.get("/console", include_in_schema=False)
    def console() -> FileResponse:
        return FileResponse(CONSOLE_DIR / "index.html")

    @app.get("/console/{asset}", include_in_schema=False)
    def console_asset(asset: str) -> FileResponse:
        p = (CONSOLE_DIR / asset).resolve()
        if CONSOLE_DIR not in p.parents or not p.exists():
            raise HTTPException(404)
        return FileResponse(p)

    return app


app = create_app()
