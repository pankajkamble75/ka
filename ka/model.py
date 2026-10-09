"""Core domain objects (spec §37), with the field lists of §4.1, §6, §16 and §22 carried verbatim.

Everything here is a pydantic model persisted as one JSON document per object by ka.repository.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ka.ids import new_id, version_ref
from ka.timeutil import now_iso
from ka.vocab import (
    AcquisitionChannel,
    AuthorityType,
    BindingStatus,
    CorrectionStatus,
    DecisionOutcome,
    ExtractionStatus,
    GraphElementKind,
    InheritanceState,
    KnowledgeType,
    MissionStatus,
    NuggetStatus,
    ProposalStatus,
    RelationshipType,
    RunStatus,
    ScopeType,
    SourceType,
    Visibility,
)


class Scope(BaseModel):
    """§7 — an explicit semantic scope. `scope_id` names the structure / parent domain / domain / instance."""
    scope_type: ScopeType
    scope_id: str

    def key(self) -> str:
        return f"{self.scope_type.value}:{self.scope_id}"

    def __hash__(self) -> int:  # pragma: no cover - trivial
        return hash(self.key())


# ---------------------------------------------------------------- raw content (§4.1)


class Source(BaseModel):
    """Raw content record. Immutable once stored; a changed document becomes a new SourceVersion."""
    id: str = Field(default_factory=lambda: new_id("source"))
    source_type: SourceType
    channel: AcquisitionChannel = AcquisitionChannel.CONTENT
    title: str
    original_location: str | None = None          # path / URL / connector locator
    original_filename: str | None = None
    owner: str | None = None
    author: str | None = None
    ingested_at: str = Field(default_factory=now_iso)
    source_created_at: str | None = None
    effective_date: str | None = None
    checksum: str
    visibility: Visibility = Visibility.ENTERPRISE
    permissions: list[str] = Field(default_factory=list)   # principals allowed to see it
    domain_id: str | None = None
    instance_id: str | None = None
    scope: Scope | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    content_version: int = 1
    current_version_id: str | None = None
    authority_type: AuthorityType = AuthorityType.USER_KNOWLEDGE
    metadata: dict[str, Any] = Field(default_factory=dict)
    # [block plan-08] research-01 R10: synced sources know their connection; a deleted/revoked one is marked, never erased
    connection_id: str | None = None
    revoked_at: str | None = None
    # [/block plan-08]


class SourceVersion(BaseModel):
    """One immutable snapshot of a source's content."""
    id: str = Field(default_factory=lambda: new_id("source_version"))
    source_id: str
    version: int
    checksum: str
    media_type: str = "text/plain"
    text: str = ""                                  # extracted text (empty when extraction unavailable)
    byte_size: int = 0
    stored_path: str | None = None                  # where the original bytes live, if kept
    created_at: str = Field(default_factory=now_iso)
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    extraction_note: str | None = None
    # [block plan-04] research-01 R16 / R3
    extraction_version: str = "ka-extract/1"        # the extractor that produced `text`; re-extraction is a new version
    extraction_report: dict[str, Any] = Field(default_factory=dict)   # statements / assertions / dropped / method
    # [/block plan-04]


class Evidence(BaseModel):
    """A located excerpt of a source version that supports a nugget. Evidence is not knowledge (§4.1)."""
    id: str = Field(default_factory=lambda: new_id("evidence"))
    source_id: str
    source_version_id: str
    locator: str | None = None                       # "Section 4.2", "p.3", char offsets, URL fragment
    span_id: str | None = None                       # plan-04: stable span in the source version's text
    start: int | None = None
    end: int | None = None
    excerpt: str
    created_at: str = Field(default_factory=now_iso)
    created_by: str = "system"
    research_run_id: str | None = None
    visibility: Visibility = Visibility.ENTERPRISE


# ---------------------------------------------------------------- process assertions (research-01 R2)

# [block plan-03]
class Subject(BaseModel):
    """What a nugget is about, in EOS terms. Identity = (kind, canonical_key); scope is not part of it."""
    kind: str                                        # an EOS node kind: process, entity, actor, rule, event, state, …
    canonical_key: str
    name: str = ""
    aliases: list[str] = Field(default_factory=list)


class ObjectRef(BaseModel):
    """The object of an assertion: another subject (kind + key) or a literal value (a type name, a description)."""
    kind: str | None = None
    canonical_key: str | None = None
    value: str | None = None


class GrammarBinding(BaseModel):
    """One binding of one nugget version under one grammar release. Recomputed per release; never edits the version."""
    id: str = Field(default_factory=lambda: new_id("binding"))
    nugget_ref: str
    grammar_version: str | None = None
    type_table_version: str | None = None
    digest: str = ""
    process_type: str | None = None
    edge: str | None = None
    slot: str | None = None
    binding_status: BindingStatus = BindingStatus.UNRESOLVED
    method: str = "inferred"                         # evidenced | inferred
    confidence: float = 0.0
    alternatives: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    bound_at: str = Field(default_factory=now_iso)


class SubjectRecord(BaseModel):
    canonical_key: str
    kind: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    first_ref: str | None = None
# [/block plan-03]


# ---------------------------------------------------------------- knowledge nugget (§5, §6)


class GraphRef(BaseModel):
    """§15 reverse lineage — what a nugget version materialized as."""
    graph_id: str
    element_id: str
    element_kind: GraphElementKind
    graph_change_id: str | None = None


class KnowledgeNuggetVersion(BaseModel):
    """§6 schema. One row per (canonical_id, version). Immutable once status is governed (§14)."""
    id: str = Field(default_factory=lambda: new_id("nugget"))
    canonical_id: str
    version: int = 1
    title: str
    statement: str
    normalized_meaning: str = ""

    scope_type: ScopeType
    scope_id: str
    domain_id: str | None = None
    instance_id: str | None = None
    parent_domain_id: str | None = None
    structure_id: str | None = None

    knowledge_type: KnowledgeType = KnowledgeType.FACT
    # research-01 R2 (plan-03): the assertion, semantic and immutable with the version; binding lives in its own record
    subject: Subject | None = None
    predicate: str | None = None
    object: ObjectRef | None = None
    status: NuggetStatus = NuggetStatus.CANDIDATE
    authority_type: AuthorityType = AuthorityType.USER_KNOWLEDGE
    authority_rank: int = 0
    confidence: float = 0.5
    visibility: Visibility = Visibility.ENTERPRISE

    effective_from: str | None = None
    effective_to: str | None = None

    created_at: str = Field(default_factory=now_iso)
    created_by: str = "system"
    approved_at: str | None = None
    approved_by: str | None = None
    activated_at: str | None = None

    supersedes: str | None = None                   # version ref  "KN-983:v2"
    superseded_by: str | None = None

    source_refs: list[str] = Field(default_factory=list)      # source ids
    evidence_refs: list[str] = Field(default_factory=list)    # evidence ids
    relationships: list[str] = Field(default_factory=list)    # relationship ids
    tags: list[str] = Field(default_factory=list)
    graph_group: str | None = None                  # §29 — domain graph area the nugget belongs to

    governance_decision_id: str | None = None
    derived_graph_refs: list[GraphRef] = Field(default_factory=list)
    graph_change_refs: list[str] = Field(default_factory=list)

    research_run_refs: list[str] = Field(default_factory=list)
    correction_refs: list[str] = Field(default_factory=list)

    channel: AcquisitionChannel = AcquisitionChannel.CONTENT
    inherited_from: str | None = None               # version ref of the parent-scope nugget this derives from
    inheritance_state: InheritanceState | None = None

    change_reason: str | None = None
    comments: list[dict[str, Any]] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict)   # conflict/scope engine output, by name

    @property
    def ref(self) -> str:
        return version_ref(self.canonical_id, self.version)

    @property
    def scope(self) -> Scope:
        return Scope(scope_type=self.scope_type, scope_id=self.scope_id)

    def is_governed(self) -> bool:
        return self.status in {NuggetStatus.APPROVED, NuggetStatus.ACTIVE, NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE}


class KnowledgeRelationship(BaseModel):
    """§10 — typed edge between two nugget versions."""
    id: str = Field(default_factory=lambda: new_id("relationship"))
    from_ref: str
    to_ref: str
    relationship_type: RelationshipType
    confidence: float = 0.5
    explanation: str = ""
    created_at: str = Field(default_factory=now_iso)
    created_by: str = "system"


# ---------------------------------------------------------------- governance (§11, §13, §33)


class GovernanceDecision(BaseModel):
    id: str = Field(default_factory=lambda: new_id("decision"))
    subject_ref: str                                # the candidate version decided on
    related_refs: list[str] = Field(default_factory=list)  # existing versions involved (conflict partner, etc.)
    outcome: DecisionOutcome
    decided_by: str
    decided_at: str = Field(default_factory=now_iso)
    reason: str = ""
    comments: str | None = None
    automatic: bool = False
    resulting_refs: list[str] = Field(default_factory=list)  # versions created by the decision
    llm_recommendation: dict[str, Any] | None = None
    # [block plan-02]
    visibility_change: dict[str, str] | None = None          # {"from": "PERSONAL", "to": "DOMAIN"} when a decision widened it
    # [/block plan-02]


class KnowledgeCorrection(BaseModel):
    """§23 — a correction captured in the Enterprise Console. Knowledge first, graph second (Inv. 6)."""
    id: str = Field(default_factory=lambda: new_id("correction"))
    graph_id: str | None = None
    element_id: str | None = None
    what_is_incorrect: str
    correct_value: str
    reason: str = ""
    comments: str | None = None
    submitted_by: str
    submitted_at: str = Field(default_factory=now_iso)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    resolved_lineage: list[str] = Field(default_factory=list)   # nugget version refs behind the element
    suggested_scope: Scope | None = None
    user_scope: Scope | None = None
    scope_rationale: str = ""
    status: CorrectionStatus = CorrectionStatus.SUBMITTED
    candidate_ref: str | None = None
    decision_id: str | None = None


# ---------------------------------------------------------------- research (§16, §17)


class ResearchMission(BaseModel):
    mission_id: str = Field(default_factory=lambda: new_id("mission"))
    scope_type: ScopeType
    scope_id: str
    objective: str
    research_questions: list[str] = Field(default_factory=list)
    preferred_source_types: list[str] = Field(default_factory=list)
    created_by: str
    status: MissionStatus = MissionStatus.REQUESTED
    created_at: str = Field(default_factory=now_iso)
    trigger: str = "manual"                          # manual | domain_creation | instance_creation | graph_gap | on_demand
    # §42 — the most restricted class of source the requester may read (ENTERPRISE = only enterprise-wide
    # sources; TEAM = team-and-wider; PERSONAL = everything they own). Agents never see further.
    permitted_visibility: Visibility = Visibility.ENTERPRISE
    run_ids: list[str] = Field(default_factory=list)
    candidate_refs: list[str] = Field(default_factory=list)
    completed_at: str | None = None

    @property
    def id(self) -> str:
        return self.mission_id


class ResearchRun(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    mission_id: str
    agent_id: str
    model: str | None = None
    started_at: str = Field(default_factory=now_iso)
    completed_at: str | None = None
    sources_examined: list[str] = Field(default_factory=list)
    evidence_created: list[str] = Field(default_factory=list)
    candidate_nuggets_created: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    cost: float = 0.0
    status: RunStatus = RunStatus.STARTED
    errors: list[str] = Field(default_factory=list)
    notes: str = ""
    # [block plan-07] research-01 R9: what discovery searched, selected, fetched and skipped (with reasons)
    discovery: dict[str, Any] = Field(default_factory=dict)
    # [/block plan-07]
    # [block plan-16] governed / pending knowledge the Enterprise Content agent reused instead of re-extracting (research-01 §6)
    reused_refs: list[str] = Field(default_factory=list)
    # [/block plan-16]
    # [block plan-17] research-01 R18 (Q14): progress of a background run — agents done / total, current agent, candidates so far
    progress: dict[str, Any] = Field(default_factory=dict)
    # [/block plan-07]

    @property
    def id(self) -> str:
        return self.run_id


# ---------------------------------------------------------------- graph lineage (§20–§22, §40)


class GraphDependency(BaseModel):
    """§20 registry row: a graph element depends on a nugget version. Both directions are indexed."""
    id: str = Field(default_factory=lambda: new_id("dependency"))
    graph_id: str
    element_id: str
    element_kind: GraphElementKind
    scope: Scope
    nugget_ref: str
    governance_decision_id: str | None = None
    graph_change_id: str | None = None
    inheritance_state: InheritanceState = InheritanceState.INHERITED
    created_at: str = Field(default_factory=now_iso)
    active: bool = True


class InheritanceEffect(BaseModel):
    """§21 — one descendant's verdict in an impact analysis."""
    scope: Scope
    inheritance_state: InheritanceState
    action: str                                     # "proposed update" | "review only" | "no change"
    element_ids: list[str] = Field(default_factory=list)
    note: str = ""


class ElementChange(BaseModel):
    graph_id: str
    element_id: str
    element_kind: GraphElementKind
    operation: str                                  # create | update | remove
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    # [block plan-05] the EOS-shaped op this change renders to, and the edge triple for edge changes
    op: str | None = None                           # add_node | set_props | remove_node | add_edge | remove_edge
    edge: dict[str, str] | None = None              # {"kind", "source", "target"}
    # [/block plan-05]


class GraphChangeProposal(BaseModel):
    """§22 schema."""
    id: str = Field(default_factory=lambda: new_id("proposal"))
    knowledge_change_ids: list[str] = Field(default_factory=list)   # nugget version refs
    affected_graph_ids: list[str] = Field(default_factory=list)
    affected_element_ids: list[str] = Field(default_factory=list)
    before_state: dict[str, Any] = Field(default_factory=dict)
    proposed_after_state: dict[str, Any] = Field(default_factory=dict)
    changes: list[ElementChange] = Field(default_factory=list)
    reason: str = ""
    impact_summary: dict[str, Any] = Field(default_factory=dict)
    inheritance_effects: list[InheritanceEffect] = Field(default_factory=list)
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    status: ProposalStatus = ProposalStatus.PROPOSED
    created_at: str = Field(default_factory=now_iso)
    created_by: str = "system"
    approved_at: str | None = None
    approved_by: str | None = None
    applied_at: str | None = None
    execution_ids: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    # plan-05 (research-01 R1, R7): publication record and content key
    idempotency_key: str | None = None
    ops: list[dict[str, Any]] = Field(default_factory=list)
    eos_proposal_id: str | None = None
    eos_base_version: str | None = None
    eos_status: str | None = None
    new_version: str | None = None
    pinned_instances: list[str] = Field(default_factory=list)


class GraphChangeExecution(BaseModel):
    id: str = Field(default_factory=lambda: new_id("execution"))
    proposal_id: str
    started_at: str = Field(default_factory=now_iso)
    completed_at: str | None = None
    applied_changes: list[ElementChange] = Field(default_factory=list)
    status: str = "RUNNING"                          # RUNNING | APPLIED | FAILED | ROLLED_BACK
    error: str | None = None
    rollback_of: str | None = None


class PromotionProposal(BaseModel):
    """§25 — repeated instance knowledge proposed for a higher scope. Never automatic (Inv. 10)."""
    id: str = Field(default_factory=lambda: new_id("promotion"))
    target_scope: Scope
    pattern_refs: list[str] = Field(default_factory=list)     # the instance versions that match
    instance_ids: list[str] = Field(default_factory=list)
    statement: str
    title: str
    status: str = "PROPOSED"                         # PROPOSED | APPROVED | REJECTED
    created_at: str = Field(default_factory=now_iso)
    decided_by: str | None = None
    decided_at: str | None = None
    candidate_ref: str | None = None


class KnowledgeAcquisitionRequest(BaseModel):
    """§43 — what the runtime raises on GRAPH GAP DETECTED instead of reading raw knowledge."""
    id: str = Field(default_factory=lambda: new_id("request"))
    scope: Scope
    question: str
    gap_description: str
    requested_by: str = "runtime"
    created_at: str = Field(default_factory=now_iso)
    mission_id: str | None = None
    status: str = "OPEN"                            # OPEN | IN_RESEARCH | FULFILLED | CANCELLED
    # [block plan-09] research-01 R11 (KA half): the richer contract — who asked, with what grammar intent, what is missing,
    # and a correlation id; dedupe while open; a lifecycle with cancel and fulfilment. Whether EOS calls it is Q7.
    principal: str = "runtime"
    intent: str = "answer"                          # found_new | grow_existing | answer | other
    missing_semantics: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    dedupe_key: str = ""
    updated_at: str = Field(default_factory=now_iso)
    fulfilled_by: list[str] = Field(default_factory=list)
    cancelled_reason: str | None = None
    deduplicated_count: int = 0
    # [/block plan-09]


# ---------------------------------------------------------------- physical bindings (research-03 R3 — plan-18)

# [block plan-18]
class PhysicalBinding(BaseModel):
    """Where one SourceVersion's bytes physically live. Separate from the version so the version's constructor and every test stay
    as they are. Unique on (tenant_id, ka_source_id, ka_source_version); `available` is what makes the version usable."""
    id: str = Field(default_factory=lambda: new_id("binding"))
    tenant_id: str
    ka_source_id: str
    ka_source_version: int
    source_version_id: str
    backend: str                                   # local | data_platform
    dp_asset_id: str | None = None
    dp_asset_version_id: str | None = None
    sha256: str
    extracted_text_asset_id: str | None = None
    status: str = "pending"                         # pending | available | failed | revoked
    reason: str | None = None
    owner: str | None = None
    visibility: Visibility = Visibility.ENTERPRISE
    locator: str | None = None
    created_at: str = Field(default_factory=now_iso)
    last_synced_at: str | None = None
# [/block plan-18]


# [block plan-20]
class PendingOp(BaseModel):
    """One operation KA owes the Data Platform, durable until done or dead (research-03 R4)."""
    id: str = Field(default_factory=lambda: new_id("op"))
    kind: str                                          # upload_source | put_derived | ack_event
    idempotency_key: str
    backend: str = "data_platform"                     # plan-23: one operation per (kind, key, backend) — a backfill re-sends local copies
    payload: dict[str, Any] = Field(default_factory=dict)
    state: str = "pending"                             # pending | done | dead
    attempts: int = 0
    next_at: str = Field(default_factory=now_iso)
    last_error: str | None = None
    last_code: str | None = None
    by: str = "ka.outbox"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
# [/block plan-20]


# [block plan-22]
class DerivedArtefact(BaseModel):
    """A nugget version's immutable physical copy — one per (canonical_id, version, status) (research-03 R6)."""
    id: str = Field(default_factory=lambda: new_id("derived"))
    kind: str = "nugget_version"
    canonical_id: str
    version: int
    status: str
    ref: str
    idempotency_key: str
    backend: str = "local"
    state: str = "pending"                             # pending | available | failed
    event: str | None = None
    op_id: str | None = None
    dp_asset_id: str | None = None
    dp_asset_version_id: str | None = None
    parent_asset_id: str | None = None
    sha256: str | None = None
    locator: str | None = None
    created_at: str = Field(default_factory=now_iso)
    published_at: str | None = None
# [/block plan-22]


# [block plan-25] research-04 R2 (Q19): the Knowledge Wiki stores only what a person authors — the article itself is computed on read
class WikiPage(BaseModel):
    """A page's identity and editorial layout. `key` is deterministic for derived pages (`process:<k>`, `subject:<k>`, `scope:<T>|<id>`)
    and a slug for authored pages (`page:<slug>`). Facts are never stored here."""
    key: str
    kind: str                                          # process | subject | scope | page
    title: str
    ceiling: Visibility = Visibility.ENTERPRISE        # a page never shows a version narrower than its ceiling
    layout: dict[str, Any] = Field(default_factory=dict)   # section order, pinned refs, prose-only blocks (authored pages)
    layout_rev: int = 0
    scope_type: ScopeType | None = None
    scope_id: str | None = None
    owner: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class WikiDraft(BaseModel):
    """An editor's working copy of a page: blocks as edited, against the layout revision and the selection digest the editor saw."""
    id: str = Field(default_factory=lambda: new_id("wiki_draft"))
    page_key: str
    base_layout_rev: int = 0
    base_digest: str | None = None
    rev: int = 0                                       # bumped on every save; `expected_rev` must match (optimistic lock)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    editor: str = "console-user"
    state: str = "DRAFT"                               # DRAFT | SUBMITTED | CLOSED
    note: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class WikiEditProposal(BaseModel):
    """What a submitted draft asks governance for: the block diff, each change's class, the candidate/revision refs it produced."""
    id: str = Field(default_factory=lambda: new_id("wiki_proposal"))
    page_key: str
    draft_id: str
    diff: list[dict[str, Any]] = Field(default_factory=list)      # {block_id, op: insert|update|delete|move, before, after}
    operations: list[dict[str, Any]] = Field(default_factory=list)  # {block_id, cls, statement, target_ref, produced_ref, note}
    produced_refs: list[str] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    state: str = "SUBMITTED"                           # SUBMITTED | RESOLVED | PUBLISHED | REJECTED
    submitted_by: str = "console-user"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class WikiPublication(BaseModel):
    """The record that a page was shown as published with this layout and this selection digest."""
    id: str = Field(default_factory=lambda: new_id("wiki_publication"))
    page_key: str
    layout_rev: int
    digest: str
    manifest: list[str] = Field(default_factory=list)  # the refs in the selection at publication
    by: str = "console-user"
    proposal_id: str | None = None
    created_at: str = Field(default_factory=now_iso)
# [/block plan-25]


# ---------------------------------------------------------------- connectors (research-01 R10 — plan-08)


class Connection(BaseModel):
    id: str = Field(default_factory=lambda: new_id("connection"))
    kind: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    owner: str
    scope: Scope
    authority: AuthorityType = AuthorityType.PROJECT_DOCUMENTATION
    visibility: Visibility = Visibility.ENTERPRISE
    secret_ref: str | None = None                   # the NAME of an environment variable; never its value
    status: str = "active"                          # active | revoked
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    last_sync_at: str | None = None
    last_delta: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, int] = Field(default_factory=dict)
    revoked_at: str | None = None


# ---------------------------------------------------------------- audit (§41)


class AuditRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("audit"))
    who: str
    what: str
    when: str = Field(default_factory=now_iso)
    why: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    source: str | None = None
    scope: Scope | None = None
    approval: str | None = None
    affected_objects: list[str] = Field(default_factory=list)
