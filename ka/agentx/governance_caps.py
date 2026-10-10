# [block plan-30]
"""Governance capabilities for AgentX (research-05 R4, R5): `knowledge.review`, `knowledge.resolve_conflict`, `knowledge.publish`, and the
open-work listing behind `GET /v1/tasks`. A person's decision arrives as AgentX `OperationInput` and becomes `governance.decide(by=
submitted_by)` — the one pipeline; a research-agent user is refused exactly as governance refuses it. Publication approves and applies a
graph change proposal (Q3: a named person; AgentX inserts its own approval first) or publishes a wiki proposal, and succeeds only when the
change is applied. Interaction forms are AgentX's declarative UiSchema v1 (data only)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ka.agentx.capabilities import Capability, check_tenant
from ka.agentx.contract import AgentXError
from ka.governance import GovernanceError
from ka.vocab import DecisionOutcome, NuggetStatus, ProposalStatus

OPEN = {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.ANALYZED}
REVIEW_OUTCOMES = ["APPROVE", "REJECT", "REQUEST_MORE_RESEARCH"]
CONFLICT_OUTCOMES = ["ACCEPT_NEW", "KEEP_EXISTING", "MERGE", "BOTH_VALID_ADD_CONTEXT", "REJECT"]
LABELS = {"APPROVE": "Approve", "REJECT": "Reject", "REQUEST_MORE_RESEARCH": "Request more research", "ACCEPT_NEW": "Accept the new statement",
          "KEEP_EXISTING": "Keep the existing statement", "MERGE": "Merge into one statement", "BOTH_VALID_ADD_CONTEXT": "Both valid (add context)"}


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, description="a PENDING_REVIEW / CONFLICT nugget ref, or a wiki proposal id (WP-…)")
    tenant_id: Optional[str] = None


class DecisionOut(BaseModel):
    decision_id: Optional[str] = None
    outcome: str
    decided_by: str
    resulting_refs: list[str] = Field(default_factory=list)
    graph_change_ids: list[str] = Field(default_factory=list)
    note: Optional[str] = None


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: Optional[str] = Field(default=None, description="a graph change proposal (GCP-…) or a wiki proposal (WP-…)")
    item_id: Optional[str] = Field(default=None, description="an ACTIVE nugget ref: its newest READY / APPROVED graph change is published")
    tenant_id: Optional[str] = None


class PublishOut(BaseModel):
    kind: Literal["graph_change", "wiki"]
    proposal_id: str
    status: str
    execution_id: Optional[str] = None
    graph_ids: list[str] = Field(default_factory=list)
    element_ids: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    digest: Optional[str] = None


# ---- the interaction form (AgentX UiSchema v1) -------------------------------------------------------------------------------

def decision_ui(title: str, outcomes: list[str], *, merge: bool) -> dict[str, Any]:
    fields = [{"name": "outcome", "type": "select", "label": "Decision", "required": True,
               "options": [{"value": o, "label": LABELS[o]} for o in outcomes]},
              {"name": "reason", "type": "textarea", "label": "Reason", "required": True, "max_length": 2000,
               "help": "Recorded on the governance decision and in the audit trail."}]
    if merge:
        fields.append({"name": "merged_statement", "type": "textarea", "label": "Merged statement", "max_length": 4000,
                       "help": "Required when the decision is Merge: the single statement that replaces both."})
    return {"version": "1", "title": title,
            "forms": [{"id": "decision", "title": "Your decision", "fields": fields, "submit": "submit"}],
            "views": [{"id": "candidate", "type": "detail", "title": "Candidate", "binding": {"source": "operation", "path": "references.candidate"}},
                      {"id": "evidence", "type": "table", "title": "Evidence", "binding": {"source": "operation", "path": "references.evidence"},
                       "columns": [{"key": "source_title", "label": "Source"}, {"key": "locator", "label": "Where"}, {"key": "excerpt", "label": "Excerpt"}]},
                      {"id": "conflicts", "type": "table", "title": "Conflicts", "binding": {"source": "operation", "path": "references.conflicts"},
                       "columns": [{"key": "existing_ref", "label": "Existing"}, {"key": "relationship", "label": "Relationship"},
                                   {"key": "explanation", "label": "Why"}]}],
            "actions": [{"id": "submit", "label": "Submit decision", "kind": "submit", "style": "primary"}]}


WIKI_UI = {"version": "1", "title": "Review a wiki edit",
           "forms": [{"id": "decision", "title": "Your decision", "submit": "submit", "fields": [
               {"name": "outcome", "type": "select", "label": "Decision", "required": True,
                "options": [{"value": "PUBLISH", "label": "Publish the edit"}, {"value": "REJECT", "label": "Reject the edit"}]},
               {"name": "reason", "type": "textarea", "label": "Reason", "required": True, "max_length": 2000}]}],
           "views": [{"id": "operations", "type": "table", "title": "What the edit asks governance for",
                      "binding": {"source": "operation", "path": "references.operations"},
                      "columns": [{"key": "cls", "label": "Class"}, {"key": "statement", "label": "Statement"}, {"key": "produced_ref", "label": "Candidate"}]}],
           "actions": [{"id": "submit", "label": "Submit decision", "kind": "submit", "style": "primary"}]}


# ---- helpers ------------------------------------------------------------------------------------------------------------------

def _card(ka, v) -> dict[str, Any]:
    d = ka.nugget_detail(v.ref)
    ev = [{"source_title": next((s["title"] for s in d["sources"] if s["id"] == e["source_id"]), e["source_id"]), "locator": e.get("locator") or "",
           "excerpt": (e.get("excerpt") or "")[:400]} for e in d["evidence"]]
    conflicts = [{"existing_ref": f["existing_ref"], "relationship": f["relationship"], "explanation": f.get("explanation") or ""}
                 for f in v.analysis.get("findings", []) if f.get("relationship") in ("CONTRADICTS", "DUPLICATES", "REFINES", "EXTENDS")]
    cand = {"ref": v.ref, "statement": v.statement, "status": v.status.value, "scope": v.scope.key(), "authority": v.authority_type.value,
            "created_by": v.created_by, "retirement_requested": bool(v.analysis.get("retirement_requested")),
            "source_revoked": bool(v.analysis.get("source_revoked"))}
    return {"candidate": cand, "evidence": ev, "conflicts": conflicts}


def _open_version(ka, item_id: str, *, conflict_only: bool = False):
    v = ka.repo.version(item_id) if ":v" in item_id else (ka.repo.latest_version(item_id) if item_id.startswith("KN-") else None)
    if v is None:
        raise AgentXError("not_found", f"no nugget version {item_id!r}")
    if v.status not in OPEN:
        raise AgentXError("conflict", f"{v.ref} is {v.status.value}; only open candidates are reviewed", details={"status": v.status.value})
    if conflict_only and not any(f.get("relationship") == "CONTRADICTS" for f in v.analysis.get("findings", [])) and v.status != NuggetStatus.CONFLICT:
        raise AgentXError("conflict", f"{v.ref} has no open conflict; use knowledge.review")
    return v


def _decision_result(ka, d, by: str) -> dict[str, Any]:
    graph = [p.id for r in d.resulting_refs for p in ka.repo.proposals.where(lambda p, r=r: r in p.knowledge_change_ids)]
    return DecisionOut(decision_id=d.id, outcome=d.outcome.value, decided_by=by, resulting_refs=list(d.resulting_refs),
                       graph_change_ids=sorted(set(graph))).model_dump(mode="json")


def _user(ka, user: Optional[str]) -> str:
    if not user:
        raise AgentXError("forbidden", "a named user is required: governance decisions are made by a person")
    if user in ka.governance.research_agent_ids:
        raise AgentXError("forbidden", f"{user!r} is a research agent; agents cannot decide or publish governed knowledge (§17)")
    return user


# ---- handlers -----------------------------------------------------------------------------------------------------------------

def review(ka, ctx, *, conflict: bool = False) -> dict[str, Any]:
    inp = ReviewIn.model_validate(ctx.input)
    check_tenant(inp.tenant_id)
    if inp.item_id.startswith("WP-"):
        p = ka.repo.wiki_proposals.get(inp.item_id)
        if p is None:
            raise AgentXError("not_found", f"no wiki proposal {inp.item_id!r}")
        if p.state not in ("SUBMITTED", "RESOLVED"):
            raise AgentXError("conflict", f"wiki proposal {p.id} is {p.state}")
        return ctx.await_input(f"Review the wiki edit to {p.page_key}", WIKI_UI, required_permission="knowledge.review",
                               subject=p.id, page_key=p.page_key, operations=[{k: o.get(k) for k in ("cls", "statement", "produced_ref")} for o in p.operations])
    v = _open_version(ka, inp.item_id, conflict_only=conflict)
    card = _card(ka, v)
    outcomes = CONFLICT_OUTCOMES if conflict else REVIEW_OUTCOMES
    title = ("Resolve a conflict: " if conflict else "Review a candidate: ") + v.statement[:120]
    return ctx.await_input(title, decision_ui(title, outcomes, merge=conflict), required_permission="knowledge.review",
                           subject=v.ref, allowed_outcomes=outcomes, **card)


def resume_decision(ka, op, values: dict[str, Any], by: str) -> dict[str, Any]:
    by = _user(ka, by)
    allowed = op.references.get("allowed_outcomes") or ["PUBLISH", "REJECT"]
    outcome, reason = str(values.get("outcome") or ""), str(values.get("reason") or "").strip()
    if outcome not in allowed:
        raise AgentXError("schema_invalid", f"outcome must be one of {allowed}", details={"field": "outcome"})
    if not reason:
        raise AgentXError("schema_invalid", "reason is required", details={"field": "reason"})
    subject = op.references.get("subject")
    if str(subject).startswith("WP-"):
        p = ka.repo.wiki_proposals.require(subject)
        if outcome == "REJECT":
            ka.wiki.reject_proposal(p.id, by=by, reason=reason)
            return DecisionOut(outcome="REJECT", decided_by=by, note=f"wiki proposal {p.id} rejected").model_dump(mode="json")
        try:
            out = ka.wiki.publish(p.page_key, by=by, proposal_id=p.id)
        except PermissionError as e:
            raise AgentXError("conflict", str(e)) from None
        return DecisionOut(outcome="PUBLISH", decided_by=by, note=out.get("reason") or f"published · digest {out['digest'][:12]}").model_dump(mode="json")
    merged = values.get("merged_statement")
    if outcome == "MERGE" and not (merged and str(merged).strip()):
        raise AgentXError("schema_invalid", "merged_statement is required for MERGE", details={"field": "merged_statement"})
    try:
        d = ka.governance.decide(subject, DecisionOutcome(outcome), by=by, reason=reason, merged_statement=str(merged).strip() if merged else None)
    except GovernanceError as e:
        raise AgentXError("conflict", str(e)) from None
    return _decision_result(ka, d, by)


def decided_elsewhere(ka, op) -> Optional[dict[str, Any]]:
    subject = str(op.references.get("subject") or "")
    if subject.startswith("WP-"):
        p = ka.repo.wiki_proposals.get(subject)
        return {"outcome": p.state, "decided_by": "elsewhere", "resulting_refs": []} if p and p.state in ("PUBLISHED", "REJECTED") else None
    v = ka.repo.version(subject)
    if v is None or v.status in OPEN:
        return None
    d = ka.repo.decisions.get(v.governance_decision_id) if v.governance_decision_id else None
    return {"decision_id": d.id if d else None, "outcome": d.outcome.value if d else v.status.value, "decided_by": d.decided_by if d else "elsewhere",
            "resulting_refs": list(d.resulting_refs) if d else [v.ref], "graph_change_ids": []}


def publish(ka, ctx) -> dict[str, Any]:
    inp = PublishIn.model_validate(ctx.input)
    check_tenant(inp.tenant_id)
    by = _user(ka, ctx.op.user)
    pid = inp.proposal_id
    if not pid and inp.item_id:
        ps = sorted((p for p in ka.repo.proposals.where(lambda p: inp.item_id in p.knowledge_change_ids)
                     if p.status in (ProposalStatus.READY, ProposalStatus.APPROVED)), key=lambda p: p.created_at)
        if not ps:
            raise AgentXError("not_found", f"no READY or APPROVED graph change for {inp.item_id}")
        pid = ps[-1].id
    if not pid:
        raise AgentXError("schema_invalid", "proposal_id or item_id is required")
    if pid.startswith("WP-"):
        p = ka.repo.wiki_proposals.get(pid)
        if p is None:
            raise AgentXError("not_found", f"no wiki proposal {pid!r}")
        try:
            out = ka.wiki.publish(p.page_key, by=by, proposal_id=pid)
        except PermissionError as e:
            raise AgentXError("conflict", str(e)) from None
        return PublishOut(kind="wiki", proposal_id=pid, status="published" if out["published"] else out.get("reason", "unchanged"),
                          digest=out.get("digest")).model_dump(mode="json")
    p = ka.repo.proposals.get(pid)
    if p is None:
        raise AgentXError("not_found", f"no graph change proposal {pid!r}")
    if p.status not in (ProposalStatus.READY, ProposalStatus.APPROVED):
        raise AgentXError("conflict", f"graph change {pid} is {p.status.value}; only READY or APPROVED changes are published", details={"status": p.status.value})
    ctx.progress(0.2, "approving", graph_change_id=pid)
    if p.status == ProposalStatus.READY:
        ka.graph_change.approve(pid, by=by, reason=f"published through AgentX by {by}")
    # [block plan-31] research-05 R7: with Knowledge Worker, success only when KW reports the change applied — submit, wait, then apply
    from ka.graph_adapter import KnowledgeWorkerHTTPAdapter
    if isinstance(ka.adapter, KnowledgeWorkerHTTPAdapter):
        _await_kw(ka, ctx, pid, by)
    # [/block plan-31]
    ctx.progress(0.5, "applying")
    ex = ka.graph_change.apply(pid, by=by)
    p = ka.repo.proposals.require(pid)
    if p.status != ProposalStatus.APPLIED:
        raise AgentXError("conflict", f"graph change {pid} did not apply ({p.status.value})", details={"status": p.status.value, "execution_id": ex.id})
    return PublishOut(kind="graph_change", proposal_id=pid, status=p.status.value, execution_id=ex.id, graph_ids=list(p.affected_graph_ids),
                      element_ids=list(p.affected_element_ids), lineage=list(p.knowledge_change_ids)).model_dump(mode="json")


# [block plan-31]
def _await_kw(ka, ctx, pid: str, by: str) -> None:
    """Submit the approved change to Knowledge Worker and keep the operation running until KW applies it (or refuses). KA's own `apply`
    afterwards replays the same idempotency key and records the result; KA's proposal stays APPROVED if KW refuses."""
    import time as _t
    from ka.graph_adapter import PublishRefused
    from ka.knowledge_worker.client import KnowledgeWorkerError
    p = ka.repo.proposals.require(pid)
    for c in p.changes:                                              # the lineage carries KA's proposal id, as apply would set it
        if c.after:
            for ln in c.after.get("props", {}).get("knowledge_lineage", []):
                if ln.get("graph_change_id") is None:
                    ln["graph_change_id"] = pid
    scope = ka.adapter.scope_for_graph(p.affected_graph_ids[0]) if p.affected_graph_ids else ka.repo.require_version(p.knowledge_change_ids[0]).scope
    try:
        res = ka.adapter.submit(scope, p.changes, actor=by, reason=p.reason, base_version=p.eos_base_version, graph_change_id=pid)
    except PublishRefused as e:
        raise AgentXError("unavailable" if e.code in ("UNAVAILABLE",) else ("forbidden" if e.code == "FORBIDDEN" else "conflict"),
                          f"Knowledge Worker refused the change: {e}", details={"kw_code": e.code}) from None
    ctx.progress(0.3, "awaiting Knowledge Worker", kw_proposal_id=res.get("proposal_id"))
    while res.get("status") == "awaiting_approval":
        if ctx.cancelled():
            raise AgentXError("cancelled", "cancelled while Knowledge Worker had not applied the change")
        _t.sleep(0.25)
        try:
            res = ka.adapter.client.get(res["proposal_id"])
        except KnowledgeWorkerError as e:
            if not e.retryable:
                raise AgentXError("conflict", f"Knowledge Worker: {e}", details={"kw_code": e.code}) from None
    if res.get("status") != "applied":
        raise AgentXError("conflict", f"Knowledge Worker proposal {res.get('proposal_id')} is {res.get('status')}",
                          details={"kw_proposal_id": res.get("proposal_id"), "kw_status": res.get("status")})
# [/block plan-31]


# ---- open review work --------------------------------------------------------------------------------------------------------

def tasks(ka, limit: int = 200) -> list[dict[str, Any]]:
    out = []
    for v in sorted(ka.repo.nuggets.where(lambda n: n.status in OPEN), key=lambda n: n.created_at):
        conflict = v.status == NuggetStatus.CONFLICT or any(f.get("relationship") == "CONTRADICTS" for f in v.analysis.get("findings", []))
        kind = "review_retirement" if v.analysis.get("retirement_requested") else ("resolve_conflict" if conflict else "review_candidate")
        cap = "knowledge.resolve_conflict" if conflict else "knowledge.review"
        out.append({"task_id": f"task:{v.ref}", "kind": kind, "item_id": v.ref, "title": v.title[:200], "summary": v.statement[:300],
                    "scope": v.scope.key(), "created_at": v.created_at, "start": {"capability": cap, "input": {"item_id": v.ref}}})
    for p in sorted(ka.repo.wiki_proposals.where(lambda p: p.state in ("SUBMITTED", "RESOLVED")), key=lambda p: p.created_at):
        out.append({"task_id": f"task:{p.id}", "kind": "review_wiki_proposal", "item_id": p.id, "title": f"Wiki edit to {p.page_key}",
                    "summary": f"{len(p.operations)} operations from draft {p.draft_id}", "scope": None, "created_at": p.created_at,
                    "start": {"capability": "knowledge.review", "input": {"item_id": p.id}}})
    return out[:limit]


def extend(ka) -> dict[str, Capability]:
    caps = [
        Capability("knowledge.review", "Review a candidate",
                   "Ask a person to approve or reject a candidate nugget (or a wiki edit). The operation waits for input in AgentX's form; "
                   "the decision is KA governance's own (`decide`), made by the submitting user — never by an agent.",
                   ReviewIn, DecisionOut, ["knowledge.review"], "async", lambda ctx: review(ka, ctx), ["approve", "reject", "review"],
                   ["Review the pending refund candidate"], idempotent=True, timeout={"request_s": 30, "operation_s": 604800},
                   ui_schema=decision_ui("Review a candidate", REVIEW_OUTCOMES, merge=False)),
        Capability("knowledge.resolve_conflict", "Resolve a knowledge conflict",
                   "Ask a person to resolve a candidate that contradicts governed knowledge: accept the new statement, keep the existing one, "
                   "merge them, or keep both with context.",
                   ReviewIn, DecisionOut, ["knowledge.review"], "async", lambda ctx: review(ka, ctx, conflict=True), ["conflict", "merge"],
                   ["Resolve the refund threshold conflict"], idempotent=True, timeout={"request_s": 30, "operation_s": 604800},
                   ui_schema=decision_ui("Resolve a conflict", CONFLICT_OUTCOMES, merge=True)),
        Capability("knowledge.publish", "Publish governed knowledge",
                   "Approve and apply a graph change compiled from approved knowledge (or publish a reviewed wiki edit). Succeeds only "
                   "when the change is applied. Requires a named person's approval (KA Q3).",
                   PublishIn, PublishOut, ["knowledge.publish"], "async", lambda ctx: publish(ka, ctx), ["publish", "graph", "apply"],
                   ["Publish the approved refund rule to the domain graph"], idempotent=True, requires_approval=True),
    ]
    return {c.id: c for c in caps}
# [/block plan-30]
