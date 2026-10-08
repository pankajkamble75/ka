"""Controlled vocabularies, verbatim from the specification. Every enum cites its section."""
from __future__ import annotations

from enum import Enum


class ScopeType(str, Enum):
    """§7 — knowledge MUST be explicitly scoped. Ordered broadest → narrowest."""
    STRUCTURE = "STRUCTURE"
    PARENT_DOMAIN = "PARENT_DOMAIN"
    DOMAIN = "DOMAIN"
    INSTANCE = "INSTANCE"


SCOPE_ORDER = [ScopeType.STRUCTURE, ScopeType.PARENT_DOMAIN, ScopeType.DOMAIN, ScopeType.INSTANCE]


def is_broader(a: ScopeType, b: ScopeType) -> bool:
    return SCOPE_ORDER.index(a) < SCOPE_ORDER.index(b)


class InheritanceState(str, Enum):
    """§9"""
    INHERITED = "INHERITED"
    OVERRIDDEN = "OVERRIDDEN"
    LOCALLY_EXTENDED = "LOCALLY_EXTENDED"
    LOCALLY_REMOVED = "LOCALLY_REMOVED"
    CONFLICTING = "CONFLICTING"


class RelationshipType(str, Enum):
    """§10"""
    DUPLICATES = "DUPLICATES"
    SUPPORTS = "SUPPORTS"
    EXTENDS = "EXTENDS"
    REFINES = "REFINES"
    SUPERSEDES = "SUPERSEDES"
    CONTRADICTS = "CONTRADICTS"
    CONTEXTUALIZES = "CONTEXTUALIZES"
    SPECIALIZES = "SPECIALIZES"
    OBSOLETES = "OBSOLETES"
    MERGES = "MERGES"
    SPLITS = "SPLITS"
    INDEPENDENT_OF = "INDEPENDENT_OF"


class NuggetStatus(str, Enum):
    """§12 — minimum lifecycle plus terminal/intermediate states."""
    INGESTED = "INGESTED"
    EXTRACTED = "EXTRACTED"
    CANDIDATE = "CANDIDATE"
    ANALYZED = "ANALYZED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    OBSOLETE = "OBSOLETE"
    CONFLICT = "CONFLICT"
    ARCHIVED = "ARCHIVED"


# §12 — the only legal forward moves. "No candidate knowledge should become active merely because an
# LLM generated it": the path to ACTIVE passes through PENDING_REVIEW and APPROVED, always.
STATUS_TRANSITIONS: dict[NuggetStatus, set[NuggetStatus]] = {
    NuggetStatus.INGESTED: {NuggetStatus.EXTRACTED, NuggetStatus.ARCHIVED},
    NuggetStatus.EXTRACTED: {NuggetStatus.CANDIDATE, NuggetStatus.ARCHIVED},
    NuggetStatus.CANDIDATE: {NuggetStatus.ANALYZED, NuggetStatus.REJECTED, NuggetStatus.ARCHIVED},
    NuggetStatus.ANALYZED: {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.REJECTED},
    NuggetStatus.CONFLICT: {NuggetStatus.PENDING_REVIEW, NuggetStatus.REJECTED, NuggetStatus.ARCHIVED},
    # PENDING_REVIEW → SUPERSEDED: a candidate folded into a MERGE result (§33) is superseded by that result.
    NuggetStatus.PENDING_REVIEW: {NuggetStatus.APPROVED, NuggetStatus.REJECTED, NuggetStatus.CONFLICT, NuggetStatus.SUPERSEDED},
    NuggetStatus.APPROVED: {NuggetStatus.ACTIVE, NuggetStatus.REJECTED},
    NuggetStatus.ACTIVE: {NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE, NuggetStatus.ARCHIVED},
    NuggetStatus.SUPERSEDED: {NuggetStatus.ARCHIVED},
    NuggetStatus.OBSOLETE: {NuggetStatus.ARCHIVED},
    NuggetStatus.REJECTED: {NuggetStatus.ARCHIVED},
    NuggetStatus.ARCHIVED: set(),
}

GOVERNED_STATUSES = {NuggetStatus.APPROVED, NuggetStatus.ACTIVE, NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE}


class AuthorityType(str, Enum):
    """§13 — configurable categories; rank is stored separately and is configurable."""
    REGULATION = "Regulation"
    APPROVED_ENTERPRISE_POLICY = "Approved Enterprise Policy"
    APPROVED_STANDARD = "Approved Standard"
    APPROVED_ARCHITECTURE = "Approved Architecture"
    OPERATING_PROCEDURE = "Operating Procedure"
    VENDOR_NETWORK_DOCUMENTATION = "Vendor / Network Documentation"
    PROJECT_DOCUMENTATION = "Project Documentation"
    USER_KNOWLEDGE = "User Knowledge"
    EXTERNAL_REFERENCE = "External Reference"
    INTERNET_RESEARCH = "Internet Research"
    LLM_GENERATED = "LLM-Generated Knowledge"


# Default ranks, highest authority first. §13: "Rank should be configurable by organization/domain" —
# ka.config.AuthorityPolicy overrides these per scope.
DEFAULT_AUTHORITY_RANK: dict[AuthorityType, int] = {
    AuthorityType.REGULATION: 100,
    AuthorityType.APPROVED_ENTERPRISE_POLICY: 90,
    AuthorityType.APPROVED_STANDARD: 85,
    AuthorityType.APPROVED_ARCHITECTURE: 80,
    AuthorityType.OPERATING_PROCEDURE: 70,
    AuthorityType.VENDOR_NETWORK_DOCUMENTATION: 60,
    AuthorityType.PROJECT_DOCUMENTATION: 50,
    AuthorityType.USER_KNOWLEDGE: 40,
    AuthorityType.EXTERNAL_REFERENCE: 30,
    AuthorityType.INTERNET_RESEARCH: 20,
    AuthorityType.LLM_GENERATED: 10,
}


class KnowledgeType(str, Enum):
    """§2.2 — the kinds of enterprise meaning a nugget can carry."""
    PROCESS_STEP = "process_step"
    RULE = "rule"
    RELATIONSHIP = "relationship"
    CONCEPT = "concept"
    DEFINITION = "business_definition"
    STATE_TRANSITION = "state_transition"
    CONDITION = "condition"
    POLICY = "policy"
    CONSTRAINT = "constraint"
    DOMAIN_SEMANTICS = "domain_semantics"
    INSTANCE_SEMANTICS = "instance_operational_semantics"
    FACT = "fact"


class SourceType(str, Enum):
    """§3.1"""
    NOTE = "note"
    MARKDOWN = "markdown"
    TEXT = "text"
    WORD = "word"
    PDF = "pdf"
    POWERPOINT = "powerpoint"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    URL = "url"
    GITHUB = "github"
    COMPANY_DOCUMENT = "company_document"
    CONNECTOR = "connector"
    MANUAL = "manual"
    RESEARCH = "research"
    CORRECTION = "correction"


class AcquisitionChannel(str, Enum):
    """§3 — the three channels. They differ by provenance and authority, not lifecycle (§11)."""
    CONTENT = "CONTENT"
    RESEARCH = "RESEARCH"
    FEEDBACK = "FEEDBACK"


class ExtractionStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTED = "EXTRACTED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class Visibility(str, Enum):
    """§42 — knowledge access, scoped independently from graph access."""
    PERSONAL = "PERSONAL"
    TEAM = "TEAM"
    DOMAIN = "DOMAIN"
    INSTANCE = "INSTANCE"
    ENTERPRISE = "ENTERPRISE"


# Narrowest → broadest. A nugget's visibility must never exceed its sources' (§42).
VISIBILITY_ORDER = [Visibility.PERSONAL, Visibility.TEAM, Visibility.INSTANCE, Visibility.DOMAIN, Visibility.ENTERPRISE]


def narrowest_visibility(items: list[Visibility]) -> Visibility:
    if not items:
        return Visibility.PERSONAL
    return min(items, key=VISIBILITY_ORDER.index)


# [block plan-02]
def required_visibility(scope_type: "ScopeType") -> Visibility:
    """§42 / research-01 R6: the narrowest visibility knowledge may carry at a scope. Knowledge an instance holds may be
    personal; a domain's knowledge is at least DOMAIN-visible; parent-domain and structure knowledge is enterprise-wide."""
    if scope_type == ScopeType.INSTANCE:
        return Visibility.PERSONAL
    if scope_type == ScopeType.DOMAIN:
        return Visibility.DOMAIN
    return Visibility.ENTERPRISE


def widens_visibility(current: Visibility, scope_type: "ScopeType") -> Visibility | None:
    """The visibility the knowledge would have to take at `scope_type`, or None when no widening is needed."""
    needed = required_visibility(scope_type)
    return needed if VISIBILITY_ORDER.index(current) < VISIBILITY_ORDER.index(needed) else None
# [/block plan-02]


class DecisionOutcome(str, Enum):
    """§33 actions, plus the plain approve/reject a reviewer takes on a pending candidate."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    KEEP_EXISTING = "KEEP_EXISTING"
    ACCEPT_NEW = "ACCEPT_NEW"
    MERGE = "MERGE"
    BOTH_VALID_ADD_CONTEXT = "BOTH_VALID_ADD_CONTEXT"
    CHANGE_SCOPE = "CHANGE_SCOPE"
    REQUEST_MORE_RESEARCH = "REQUEST_MORE_RESEARCH"
    AUTO_RESOLVED_BY_AUTHORITY = "AUTO_RESOLVED_BY_AUTHORITY"


class MissionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStatus(str, Enum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProposalStatus(str, Enum):
    """§22"""
    PROPOSED = "PROPOSED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class CorrectionStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    SCOPED = "SCOPED"
    GOVERNED = "GOVERNED"
    REJECTED = "REJECTED"


# [block plan-03]
PREDICATES = ("description", "typed_as", "decomposes_into", "consumes", "produces", "acts_on", "performed_by", "governed_by",
              "emits", "transitions_to", "precondition", "postcondition", "related_to")


class BindingStatus(str, Enum):
    """research-01 R2 — what a nugget's assertion is, against the loaded EOS grammar."""
    BOUND = "bound"
    PROPOSED = "proposed"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"
    STALE = "stale"
# [/block plan-03]


class GraphElementKind(str, Enum):
    """§15 / §21 — what a nugget can materialize as."""
    NODE = "node"
    EDGE = "edge"
    RULE = "rule"
    PROCESS = "process"
    STEP = "step"
    STATE_TRANSITION = "state_transition"
    APPLICATION = "application"
    COMPUTATION = "computation"
    CONCEPT = "concept"
