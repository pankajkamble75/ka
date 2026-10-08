I streamlined the material into a single implementation specification. I also made the lineage requirement explicit because your notes establish that every semantic graph element should trace back to governed Knowledge Nuggets and every knowledge change should have graph-impact lineage. Pasted markdown

# Enterprise OS — Knowledge Acquisition System
## Technical & Product Requirements

## 1. Purpose

Build a **Knowledge Acquisition subsystem** for Enterprise OS that acquires, curates, governs, versions, researches, and maintains the knowledge used to construct and evolve Enterprise OS graphs.

Knowledge Acquisition is **not the runtime mechanism for answering normal Enterprise OS questions**.

The fundamental architecture is:

**Knowledge Acquisition learns and governs.  
The Graph represents operational knowledge.  
Data provides operational truth/evidence.  
The Enterprise Console uses the Graph to answer and act.**

The core invariant is:

> **Knowledge is acquired and governed first, compiled into the graph second, and consumed through graph navigation at runtime.**

---

# 2. Core Architectural Principles

## 2.1 Knowledge Acquisition is upstream of the Graph

Normal runtime question flow:

```text
User Question
      ↓
Enterprise Console
      ↓
Question Decomposition
      ↓
Instance Discovery
      ↓
Instance Graph
      ↓
Substructure / Structure Navigation
      ↓
Operational Data / Compute if required
      ↓
Answer / Action
```

Do not introduce the Knowledge Repository, document retrieval, Internet search, or Research Agents into this normal runtime path.

Knowledge Acquisition operates separately:

```text
Sources
   ↓
Knowledge Acquisition
   ↓
Governed Knowledge
   ↓
Graph Construction / Graph Change
   ↓
Structure / Domain / Instance Graph
```

---

## 2.2 Never silently mutate semantic graph meaning

The system MUST enforce:

> **No semantic graph mutation without a corresponding governed knowledge change.**

Technical graph operations such as indexing, caching, physical mappings, performance optimization, or storage changes do not require Knowledge Nuggets.

Changes affecting enterprise meaning do.

Examples:

- process step changes;
- rule changes;
- relationship changes;
- concept changes;
- business definitions;
- state transitions;
- conditions;
- policies;
- constraints;
- domain semantics;
- instance-specific operational semantics.

Every semantic graph change MUST be attributable to one or more governed Knowledge Nugget versions.

---

# 3. Knowledge Sources

Knowledge Acquisition must support three primary acquisition channels.

```text
                   KNOWLEDGE ACQUISITION
                           │
             ┌─────────────┼─────────────┐
             │             │             │
          CONTENT       RESEARCH      FEEDBACK
             │             │             │
       User/company     Autonomous     Enterprise
         content       research agents   Console
```

## 3.1 Content ingestion

Allow users to add:

- typed notes;
- Markdown;
- plain text;
- Word documents;
- PDFs;
- PowerPoint;
- spreadsheets;
- images where extraction is available;
- Internet URLs;
- GitHub/documentation links;
- company documents;
- connector-based sources;
- manually entered knowledge.

The ingestion mechanism should be intentionally low-friction.

Users should be able to:

```text
Upload
Paste
Write
Link
Connect
```

without first understanding the internal knowledge model.

---

## 3.2 Research Agents

Knowledge Acquisition must contain an offline Research subsystem.

Research Agents may use:

- Internet research;
- LLM internal knowledge;
- standards;
- regulatory sources;
- company documentation;
- vendor documentation;
- technical documentation;
- configured enterprise connectors.

Research Agents MUST NOT directly change production graphs.

Research output must become **Candidate Knowledge Nuggets** and enter the same governance workflow as all other knowledge.

Example:

```text
Research Mission
      ↓
Research Runs
      ↓
Sources
      ↓
Evidence
      ↓
Candidate Nuggets
      ↓
Governance
      ↓
Governed Nuggets
      ↓
Graph Impact
```

Research can be:

- on-demand;
- triggered during domain creation;
- triggered during instance creation;
- triggered because of a graph gap;
- manually requested;
- periodically scheduled in a future implementation.

---

## 3.3 Enterprise Console corrections

When a user interacts with an Enterprise OS graph and identifies an error, the graph MUST NOT be directly edited.

Instead:

```text
Enterprise Console
       ↓
User reports problem
       ↓
Correction Proposal
       ↓
Knowledge Acquisition
       ↓
Governance
       ↓
Knowledge Nugget version
       ↓
Graph Impact Analysis
       ↓
Graph Change
```

The correction becomes part of enterprise knowledge history.

The next runtime answer should be correct because the **Graph changed**, not because a conversational memory remembered the correction.

---

# 4. Raw Content and Governed Knowledge

Maintain a strict separation between source material and governed knowledge.

```text
RAW CONTENT STORE
       ↓
Extraction
       ↓
Candidate Knowledge
       ↓
Reconciliation / Governance
       ↓
GOVERNED KNOWLEDGE STORE
```

## 4.1 Raw Content Store

Raw content should be immutable wherever practical.

Store:

- source ID;
- source type;
- original location;
- original file/link;
- source owner;
- author if known;
- ingestion timestamp;
- source creation timestamp;
- effective date if available;
- content checksum;
- permissions;
- domain association;
- instance association;
- extraction status;
- content version.

Raw content is evidence.

It is **not automatically authoritative knowledge**.

---

# 5. Knowledge Nugget

The fundamental semantic object in Knowledge Acquisition is the:

# Knowledge Nugget

A Knowledge Nugget represents a discrete piece of knowledge that can be independently:

- sourced;
- compared;
- governed;
- versioned;
- scoped;
- approved;
- rejected;
- superseded;
- traced into the graph.

Do not treat the document as the minimum governance unit.

One document can produce many Knowledge Nuggets.

Example:

```text
Merchant Operations Manual
        ↓
KN-001 — KYC is required before activation
KN-002 — Refunds require approval above X
KN-003 — Chargeback response must occur within Y
KN-004 — Settlement occurs after clearing
```

---

# 6. Knowledge Nugget Data Model

Minimum Knowledge Nugget schema:

```text
KnowledgeNugget
---------------
id
canonical_id
version
title
statement
normalized_meaning

scope_type
scope_id

domain_id
instance_id
parent_domain_id
structure_id

knowledge_type
status
authority_level
confidence

effective_from
effective_to

created_at
created_by
approved_at
approved_by

supersedes
superseded_by

source_refs[]
evidence_refs[]

relationships[]
tags[]

governance_decision_id

derived_graph_refs[]
graph_change_refs[]

research_run_refs[]
correction_refs[]

change_reason
comments
```

---

# 7. Knowledge Scope

Knowledge MUST be explicitly scoped.

Supported semantic scopes:

```text
STRUCTURE
PARENT_DOMAIN
DOMAIN / SUBSTRUCTURE
INSTANCE
```

The system should select the **lowest scope at which the knowledge is valid**.

Example:

```text
"Restaurant A requires manager approval > $1,000"

→ INSTANCE
```

Not:

```text
Restaurant Domain
```

unless evidence supports the broader claim.

---

# 8. Domain Inheritance

Knowledge scope must align with Graph inheritance.

Example:

```text
Structure
   ↓
Payment Processing
   ↓
Merchant Acquiring
   ├── Merchant A
   ├── Merchant B
   └── Merchant C
```

A domain-level knowledge change may affect many instances.

An instance-level change should affect only that instance.

A parent-domain change may affect multiple specialized domains.

A Structure-level change may affect many domains and instances.

---

# 9. Inheritance States

For any knowledge or graph element derived from a parent scope, track its inheritance status.

Required states:

```text
INHERITED
OVERRIDDEN
LOCALLY_EXTENDED
LOCALLY_REMOVED
CONFLICTING
```

Example:

```text
Merchant Acquiring:
Refund Approval = $1,000

Merchant A
INHERITED → $1,000

Merchant B
INHERITED → $1,000

Merchant C
OVERRIDDEN → $750
```

If the domain changes to `$1,500`:

- Merchant A may inherit `$1,500`;
- Merchant B may inherit `$1,500`;
- Merchant C must preserve its `$750` override unless explicitly changed.

Never blindly propagate parent changes across overrides.

---

# 10. Knowledge Relationships

The system must model relationships between knowledge versions and nuggets.

At minimum support:

```text
DUPLICATES
SUPPORTS
EXTENDS
REFINES
SUPERSEDES
CONTRADICTS
CONTEXTUALIZES
SPECIALIZES
OBSOLETES
MERGES
SPLITS
INDEPENDENT_OF
```

This allows the system to distinguish genuine contradictions from contextual differences.

Example:

```text
"Refunds settle within 3 days."
```

and:

```text
"International refunds settle within 5 days."
```

may represent contextual specialization rather than contradiction.

---

# 11. Knowledge Governance Pipeline

All acquisition channels must converge on one governance pipeline.

```text
Source
   ↓
Extract Candidate Knowledge
   ↓
Normalize
   ↓
Find Existing Related Knowledge
   ↓
Detect Duplicate / Support / Conflict / Extension
   ↓
Determine Semantic Scope
   ↓
Determine Authority
   ↓
Generate Proposed Knowledge Change
   ↓
Governance Decision
   ↓
Create Immutable Knowledge Version
   ↓
ACTIVE GOVERNED KNOWLEDGE
```

Do not build separate governance systems for:

- research;
- uploaded documents;
- user corrections;
- Internet sources;
- LLM knowledge.

They differ by provenance and authority, not lifecycle.

---

# 12. Knowledge Status Model

Minimum lifecycle:

```text
INGESTED
    ↓
EXTRACTED
    ↓
CANDIDATE
    ↓
ANALYZED
    ↓
PENDING_REVIEW
    ↓
APPROVED
    ↓
ACTIVE
```

Additional terminal/intermediate states:

```text
REJECTED
SUPERSEDED
OBSOLETE
CONFLICT
ARCHIVED
```

No candidate knowledge should become active merely because an LLM generated it.

---

# 13. Authority Model

Different sources have different authority.

Support configurable authority categories such as:

```text
Regulation
Approved Enterprise Policy
Approved Standard
Approved Architecture
Operating Procedure
Vendor / Network Documentation
Project Documentation
User Knowledge
External Reference
Internet Research
LLM-Generated Knowledge
```

Do not rely only on a numeric score.

Store both:

```text
authority_type
authority_rank
```

Rank should be configurable by organization/domain.

The system can automatically resolve obvious situations where a low-authority source contradicts a significantly higher-authority governed source, but it should preserve the conflicting candidate and explanation.

---

# 14. Versioning

Knowledge Nuggets must be immutable once governed.

A semantic modification creates a new version.

Example:

```text
KN-983 v1
     ↓
KN-983 v2
     ↓
KN-983 v3
```

Do not overwrite `KN-983 v2`.

Example:

```text
KN-983 v2
Approval > $500
Status: SUPERSEDED

KN-983 v3
Approval > $1,000
Status: ACTIVE
Supersedes: KN-983 v2
```

Historical versions must remain queryable.

This enables temporal reconstruction:

```text
"What knowledge was active on March 1, 2025?"
```

---

# 15. Knowledge Lineage

Knowledge lineage is a mandatory architectural capability.

The complete lineage should support:

```text
Source
  ↓
Research / Ingestion / Correction
  ↓
Candidate Nugget
  ↓
Governance Decision
  ↓
Governed Nugget Version
  ↓
Graph Change
  ↓
Graph Node / Edge / Rule / Process
  ↓
Domain / Instance
  ↓
Runtime Answer / Action
```

Every semantic graph element should maintain:

```text
derived_from:
  - knowledge_nugget_id
  - knowledge_version
```

Every Knowledge Nugget should maintain reverse lineage:

```text
materialized_as:
  - graph_id
  - node_id
  - edge_id
  - rule_id
  - process_id
```

The system MUST support both questions:

```text
Graph → Why does this exist?
```

and:

```text
Knowledge → Where is this used?
```

---

# 16. Research Lineage

Research must have separate lineage before it becomes governed knowledge.

```text
ResearchMission
      ↓
ResearchRun
      ↓
SourceDiscovery
      ↓
SourceEvidence
      ↓
CandidateNugget
      ↓
GovernanceDecision
      ↓
KnowledgeNuggetVersion
```

Minimum Research Mission fields:

```text
mission_id
scope_type
scope_id
objective
research_questions[]
preferred_source_types[]
created_by
status
created_at
```

Minimum Research Run fields:

```text
run_id
mission_id
agent_id
model
started_at
completed_at
sources_examined[]
evidence_created[]
candidate_nuggets_created[]
token_usage
cost
status
errors[]
```

---

# 17. Research Agent Architecture

Initial implementation:

```text
Research Coordinator
        │
        ├── Domain Research Agent
        ├── Enterprise Content Agent
        ├── Standards / Regulatory Agent
        ├── Internet Research Agent
        └── LLM Knowledge Agent
                 │
                 ▼
          Synthesis Agent
                 │
                 ▼
        Candidate Knowledge Nuggets
```

The Synthesis Agent should:

- identify duplicate discoveries;
- cluster evidence;
- create candidate nuggets;
- identify existing governed nuggets;
- identify conflicts;
- propose scope;
- preserve all evidence/source relationships.

Research Agents cannot approve their own knowledge.

---

# 18. Domain / Instance Construction

Today:

```text
Need Domain
   ↓
LLM
   ↓
LLM internal knowledge / Internet
   ↓
Build Domain
   ↓
Build Instance
```

Target architecture:

```text
Need Domain
   ↓
Domain Builder
   ↓
Knowledge Acquisition
   ↓
Existing Governed Knowledge?
   │
   ├── YES → use it
   │
   └── NO / insufficient
          ↓
     Research Mission
          ↓
     Candidate Nuggets
          ↓
       Governance
          ↓
     Governed Knowledge
   ↓
Build / Extend Domain
   ↓
Build Instance
```

Knowledge acquisition therefore becomes reusable.

If Restaurant domain knowledge has already been researched and governed, each restaurant instance should not independently rediscover Restaurant domain knowledge.

---

# 19. Graph Compilation

Treat the graph conceptually as a compiled representation of governed knowledge.

```text
Software                  Enterprise OS

Source Code               Governed Knowledge
    ↓                            ↓
Compiler                  Graph Builder
    ↓                            ↓
Executable                Domain / Instance Graph
```

Knowledge Acquisition is the source layer.

The Graph is the operational representation.

Runtime executes/navigates the Graph.

---

# 20. Incremental Graph Evolution

A knowledge change must not trigger unnecessary full graph rebuilds.

Implement dependency-driven incremental updates.

```text
Knowledge Version Created
         ↓
Find Graph Dependencies
         ↓
Impact Analysis
         ↓
Determine Required Changes
         ↓
Create Graph Change Proposal
         ↓
Validate
         ↓
Apply Affected Changes
         ↓
Validate Descendants
```

---

# 21. Graph Impact Analysis

For each approved semantic Knowledge change, calculate:

```text
Affected Structure Elements
Affected Parent Domains
Affected Domains
Affected Instances
Affected Graph Nodes
Affected Graph Edges
Affected Rules
Affected Processes
Affected Applications
Affected Computations
```

The result should identify inherited vs overridden descendants.

Example:

```text
Knowledge Change KN-122 v2

Affected:
1 Domain
1 Process
3 Instances

Merchant A
INHERITED
→ proposed update

Merchant B
OVERRIDDEN
→ review only

Merchant C
INHERITED
→ proposed update
```

---

# 22. Graph Change Proposal

Do not immediately mutate production graphs after governance.

Create a Graph Change Proposal:

```text
GraphChangeProposal
-------------------
id
knowledge_change_ids[]
affected_graph_ids[]
affected_element_ids[]
before_state
proposed_after_state
reason
impact_summary
inheritance_effects[]
validation_results[]
status
created_at
approved_at
applied_at
```

Possible states:

```text
PROPOSED
VALIDATING
READY
APPROVED
APPLIED
FAILED
REJECTED
```

---

# 23. Enterprise Console Correction Workflow

Add a graph correction capability directly to the Enterprise Console.

Example:

```text
Refund approval threshold: $500

[ Correct this ]
```

Correction flow:

```text
User selects "Correct this"
       ↓
Capture Correction
       ↓
Identify Graph Element
       ↓
Resolve Existing Knowledge Lineage
       ↓
Create Knowledge Correction Proposal
       ↓
Determine Scope
       ↓
Govern
       ↓
New Nugget Version
       ↓
Graph Impact Analysis
       ↓
Graph Change Proposal
       ↓
Apply
```

Correction form should allow:

```text
What is incorrect?
Correct value/meaning
Reason
Optional comments

Supporting evidence:
[ Note ]
[ Upload ]
[ URL ]
[ Existing Source ]

Suggested scope:
[ Instance ]
[ Domain ]
[ Parent Domain ]
[ Structure ]
```

The system should suggest scope automatically.

The user should not need to understand the internal architecture to submit a correction.

---

# 24. Scope Decision Engine

For every correction, determine whether it belongs to:

```text
INSTANCE
DOMAIN
PARENT_DOMAIN
STRUCTURE
```

Default principle:

> **Apply knowledge at the lowest semantic scope where the statement remains true.**

The Scope Decision Engine should use:

- graph location;
- original nugget scope;
- user's wording;
- referenced evidence;
- inheritance relationships;
- similar nuggets;
- other instance patterns.

For high-impact broadening, request approval.

---

# 25. Upward Promotion

Knowledge must also be able to move upward through deliberate generalization.

Example:

```text
Restaurant A → Nugget X
Restaurant B → Nugget X
Restaurant C → Nugget X
Restaurant D → Nugget X
```

The system may identify a repeated pattern and propose:

```text
"Should Nugget X be promoted to Restaurant Domain knowledge?"
```

Promotion workflow:

```text
Repeated Instance Knowledge
        ↓
Pattern Detection
        ↓
Domain Promotion Proposal
        ↓
Governance
        ↓
Domain Knowledge Nugget
        ↓
Graph Impact Analysis
```

Never promote automatically without appropriate governance.

---

# 26. Downward Propagation

Higher-scope governed knowledge propagates downward through inheritance.

```text
Structure
   ↓
Parent Domain
   ↓
Domain
   ↓
Instance
```

Propagation MUST:

- preserve overrides;
- identify conflicts;
- identify local extensions;
- validate descendants;
- produce lineage;
- be reversible using versions.

---

# 27. Knowledge Console

Build a dedicated **Knowledge Console** separate from the Enterprise Console.

The two products serve different purposes:

```text
Enterprise Console
→ Operate / Ask / Inspect Graph / Correct

Knowledge Console
→ Acquire / Inspect / Research / Govern / Version / Trace
```

Both should use the same:

```text
Structure → Domain → Instance
```

mental model.

---

# 28. Knowledge Console Navigation

Primary navigation:

```text
Knowledge
│
├── Structure
│
├── Domains
│   ├── Domain A
│   ├── Domain B
│   └── ...
│
└── Instances
    ├── Instance A
    ├── Instance B
    └── ...
```

Users should be able to enter a domain and see all related knowledge.

Example:

```text
Merchant Acquiring
────────────────────────────

Overview
Knowledge
Sources
Conflicts
Research
Changes
Graph Impact
History
```

---

# 29. Domain Knowledge UI

Domain dashboard should show at minimum:

```text
Active Nuggets
Pending Review
Conflicts
Recently Changed
Research Missions
Affected Graph Elements
Instances Using Domain
```

Knowledge should also be grouped according to the domain graph where possible.

Example:

```text
Merchant Acquiring
│
├── Merchant Onboarding
├── Authorization
├── Clearing
├── Settlement
├── Funding
├── Reconciliation
├── Refunds
└── Chargebacks
```

This allows users to understand the domain semantically rather than browsing a flat document repository.

---

# 30. Instance Knowledge UI

An Instance Knowledge view must clearly distinguish:

```text
Inherited Knowledge
Instance-Specific Knowledge
Overrides
Extensions
Removed Knowledge
Conflicts
Pending Corrections
```

Example:

```text
Merchant A / Knowledge

Inherited                 842
Instance-specific          63
Overrides                  11
Pending corrections         2
```

When viewing a Nugget:

```text
Refund approval threshold

Current
$1,000

Scope
Merchant A

Status
ACTIVE

Version
v3

Inherited value
Merchant Acquiring → $500

Source
Merchant A Policy 2026

Graph Usage
Refund Process
 → Approval Decision
 → Rule GR-881
```

---

# 31. Knowledge Nugget Detail UI

Every Nugget detail screen should expose:

```text
ID
Title
Current statement
Normalized meaning

Scope
Status
Authority
Confidence

Current version
Version history
Effective dates

Sources
Evidence

Relationships
Conflicts

Governance history
Approvals
Comments

Research lineage
Correction lineage

Graph lineage
Affected graph elements

Inherited from
Overrides
Used by descendants
```

Primary actions:

```text
Propose Correction
Add Evidence
Add Comment
Compare Version
View Source
View Graph Usage
Research This
Propose Scope Change
```

---

# 32. Governance Queues

Knowledge Console should have a global **Needs Attention** area.

At minimum:

### Conflicts

Knowledge that conflicts with existing active knowledge.

### Pending Governance

Candidate Nuggets requiring review.

### Proposed Changes

User/research/document changes awaiting approval.

### Graph Impact

Approved knowledge changes awaiting graph propagation.

### Failed Propagation

Graph changes that failed validation or deployment.

---

# 33. Conflict Resolution UI

When conflicting knowledge is detected, display:

```text
Existing Knowledge
New Candidate Knowledge

Existing Sources
New Sources

Existing Scope
Proposed Scope

Authority Comparison
Effective Dates

LLM Explanation:
- Why they appear to conflict
- Whether both could be contextually valid
- Suggested resolution
```

Actions:

```text
Keep Existing
Accept New
Merge
Both Valid — Add Context
Change Scope
Request More Research
Reject Candidate
Add Comment
```

The LLM may recommend.

The LLM does not independently establish enterprise truth.

---

# 34. Research UI

Research should exist inside appropriate Knowledge contexts.

Example:

```text
Merchant Acquiring
  → Research
```

Show:

```text
Active Missions
Completed Missions
Candidate Nuggets
Sources Discovered
Research Runs
Research History
```

Allow:

```text
[ Start Research ]
```

Example prompt:

```text
Research current Visa dispute processing rules
and identify anything that conflicts with the
current Merchant Acquiring domain.
```

Instance-level research should also be possible:

```text
Merchant A
 → Research
```

Example:

```text
Review Merchant A operating documents and
identify knowledge inconsistent with the
current Merchant A instance.
```

---

# 35. Search

Knowledge Console should support semantic and structured search.

Search across:

- Nugget content;
- source content;
- domains;
- instances;
- process/capability;
- entity;
- author;
- tags;
- source;
- authority;
- status;
- effective date;
- graph elements.

Allow scope filters:

```text
All Knowledge
Structure
Domain
Instance
Current
Historical
Pending
Conflicting
```

---

# 36. API / Service Boundaries

Recommended initial logical services/modules:

```text
knowledge-ingestion
knowledge-extraction
knowledge-repository
knowledge-governance
knowledge-conflict
knowledge-versioning
knowledge-lineage
knowledge-scope
research-orchestrator
research-agents
graph-impact
graph-change
knowledge-search
knowledge-ui-api
```

These can initially live in one deployable application if that is simpler.

The important requirement is **logical separation**, not premature microservices.

---

# 37. Core Domain Objects

At minimum implement:

```text
Source
SourceVersion
Evidence

KnowledgeNugget
KnowledgeNuggetVersion
KnowledgeRelationship

GovernanceDecision
KnowledgeCorrection

ResearchMission
ResearchRun

GraphDependency
GraphChangeProposal
GraphChangeExecution
```

---

# 38. Event Model

Use event-driven boundaries where practical.

Important events:

```text
source.ingested
source.updated

knowledge.candidate.created
knowledge.conflict.detected
knowledge.approved
knowledge.rejected
knowledge.superseded

research.started
research.completed

correction.submitted
correction.approved

graph.impact.detected
graph.change.proposed
graph.change.approved
graph.change.applied
graph.change.failed
```

Event payloads should contain IDs, not large duplicated content.

---

# 39. Integration with Existing Graph

Do not redesign the existing graph implementation unnecessarily.

Create an adapter around the current Enterprise OS graph APIs.

Required graph adapter operations:

```text
get_graph_element(id)
get_graph_lineage(id)

find_elements_by_knowledge_nugget(id, version)

find_descendants(scope_id)

calculate_inheritance(scope_id)

create_change_proposal(...)

validate_change(...)

apply_change(...)

rollback_change(...)
```

---

# 40. Graph Metadata Extension

Add knowledge lineage metadata to semantic graph elements.

Minimum:

```text
knowledge_lineage: [
  {
    nugget_id,
    version,
    governance_decision_id,
    graph_change_id
  }
]
```

Do not duplicate the entire Knowledge Nugget in the graph.

Reference it.

---

# 41. Auditability

Every state-changing operation should record:

```text
who
what
when
why
before
after
source
scope
approval
affected_objects
```

The system should be able to reconstruct:

- why a graph node exists;
- who introduced the underlying knowledge;
- which source supports it;
- when it became effective;
- how it changed;
- which graph elements changed;
- which instances inherited it;
- which instances overrode it.

---

# 42. Security and Access

Knowledge access must be scoped independently from Graph access.

Support at minimum:

```text
PERSONAL
TEAM
DOMAIN
INSTANCE
ENTERPRISE
```

Knowledge Nugget visibility must never exceed source permissions.

Derived knowledge must preserve security lineage from its evidence.

Research Agents must not be given access to sources beyond the initiating user's/agent's permitted scope.

---

# 43. Runtime Guardrail

Normal Enterprise Console question answering MUST NOT automatically fall back to raw Knowledge Acquisition retrieval.

If the Graph does not contain enough information, the runtime should produce something similar to:

```text
GRAPH GAP DETECTED
```

The system may then create:

```text
Knowledge Acquisition Request
```

or:

```text
Research Mission
```

But that should improve the Graph for future queries rather than silently bypassing the Graph architecture.

Explicit Research/Discovery mode may be treated differently.

---

# 44. MVP Scope

Implement the first release in the following order.

## Phase 1 — Knowledge Foundation

Build:

- Raw Source ingestion;
- Notes;
- PDF / Word / text ingestion;
- URL ingestion;
- Knowledge Nugget model;
- source → nugget lineage;
- versioning;
- Structure/Domain/Instance scope;
- basic Knowledge Console;
- Knowledge search.

Success criterion:

Users can add sources and inspect structured Knowledge Nuggets organized by Domain and Instance.

---

## Phase 2 — Governance

Add:

- duplicate detection;
- contradiction detection;
- Nugget relationships;
- approval workflow;
- conflict resolution;
- effective dates;
- authority;
- comments/reasoning;
- immutable versions.

Success criterion:

New content cannot silently overwrite existing enterprise knowledge.

---

## Phase 3 — Graph Lineage

Add:

- Nugget → graph relationships;
- graph → Nugget relationships;
- graph dependency registry;
- graph impact analysis;
- Graph Change Proposals;
- lineage visualization.

Success criterion:

Every affected semantic graph element can explain which governed Knowledge Nugget produced it.

---

## Phase 4 — Enterprise Console Corrections

Add:

- "Correct this" on Graph-backed answers;
- correction capture;
- automatic lineage resolution;
- scope recommendation;
- governance workflow;
- graph propagation.

Success criterion:

A user can identify a graph error in the Enterprise Console and the correction flows through Knowledge Acquisition before updating the Graph.

---

## Phase 5 — Research Agents

Add:

- Research Mission;
- Research Run;
- Internet research;
- LLM research;
- company source research;
- Synthesis Agent;
- Candidate Nugget creation;
- research lineage.

Success criterion:

A new Domain can request research and receive governed reusable Knowledge Nuggets without directly allowing research agents to modify the Graph.

---

## Phase 6 — Intelligent Propagation

Add:

- inheritance-aware propagation;
- override protection;
- Parent Domain propagation;
- instance pattern detection;
- promotion proposals;
- incremental recompilation;
- rollback.

Success criterion:

Domain knowledge changes correctly propagate to inheriting instances without destroying local overrides.

---

# 45. Non-Goals

Do NOT turn Knowledge Acquisition into:

- another chat RAG system;
- the normal Enterprise OS question-answering layer;
- a generic vector database UI;
- a document dumping ground;
- an ungoverned enterprise search product;
- a mechanism for agents to silently modify graphs;
- a replacement for operational Data.

Raw documents are inputs.

Knowledge Nuggets are governed knowledge.

Graphs are operational representations.

Data is operational truth/evidence.

---

# 46. Required Architectural Invariants

The implementation MUST preserve these invariants.

### Invariant 1

**Normal runtime questions are answered through Graph navigation, not direct Knowledge Acquisition retrieval.**

### Invariant 2

**No semantic Graph mutation occurs without governed Knowledge lineage.**

### Invariant 3

**Knowledge Nuggets are versioned and semantic history is never silently overwritten.**

### Invariant 4

**Every semantic Graph element can identify the Knowledge Nugget versions that caused it to exist.**

### Invariant 5

**Every Knowledge Nugget can identify the Graph elements that currently depend on it.**

### Invariant 6

**Corrections discovered through the Enterprise Console become Knowledge corrections first and Graph corrections second.**

### Invariant 7

**Knowledge always has explicit semantic scope: Structure, Parent Domain, Domain, or Instance.**

### Invariant 8

**Knowledge is introduced at the lowest valid scope.**

### Invariant 9

**Higher-level changes propagate downward through inheritance without destroying local overrides.**

### Invariant 10

**Instance patterns can be proposed for upward promotion but are never automatically generalized.**

### Invariant 11

**Research Agents create candidate knowledge, never production truth or direct Graph mutations.**

### Invariant 12

**Raw source content remains distinguishable from governed knowledge.**

---

# 47. End-to-End Example

A user uploads:

```text
Merchant A Refund Policy 2027.pdf
```

Knowledge Acquisition:

```text
Source Ingestion
      ↓
Extraction
      ↓
Candidate Nugget

"Merchant A refunds above $1,000
require manager approval."
      ↓
Existing Knowledge Search
      ↓
Find:

KN-983 v2
Merchant A refunds above $500
require manager approval
      ↓
CONTRADICTION / SUPERSESSION CANDIDATE
      ↓
Scope Analysis
INSTANCE: Merchant A
      ↓
Governance
      ↓
KN-983 v3 created
$1,000
ACTIVE

KN-983 v2
SUPERSEDED
      ↓
Graph Impact Analysis
      ↓
Merchant A Refund Process
Approval Rule affected
      ↓
Graph Change Proposal
      ↓
Validation
      ↓
Apply
      ↓
Graph now references:
KN-983:v3
```

Later a user asks:

```text
"What approval is required for a $750 refund?"
```

Runtime:

```text
Question
   ↓
Merchant A Instance
   ↓
Refund Graph
   ↓
Approval Rule
   ↓
$750 < $1,000
   ↓
No manager approval required
```

Knowledge Acquisition is not queried in that runtime path.

If the user selects:

```text
"Why?"
```

the Graph lineage can show:

```text
Graph Rule GR-889
      ↓
KN-983 v3
      ↓
Merchant A Refund Policy 2027
Section 4.2
```

That is the complete desired behavior.

---

# 48. Definition of the Component

Use the following definition consistently in architecture and UI documentation:

> **Knowledge Acquisition is the learning and governance subsystem of Enterprise OS. It acquires knowledge from enterprise and personal content, autonomous research, and operational human feedback; converts that information into versioned, scoped, governed Knowledge Nuggets; maintains complete source and Graph lineage; and propagates approved knowledge changes into Structure, Domain, and Instance graphs.**

And define the Graph relationship as:

> **The Graph is the compiled operational representation of governed enterprise knowledge.**

The simplest conceptual model is therefore:

```text
ACQUIRE
   ↓
GOVERN
   ↓
KNOW
   ↓
COMPILE
   ↓
GRAPH
   ↓
OPERATE
   ↓
OBSERVE / CORRECT
   └───────────────→ ACQUIRE
```

This closed loop is the Knowledge Acquisition architecture for Enterprise OS.

This version is much more suitable to hand directly to a coding agent than the original combined notes. I deliberately removed repeated explanations and turned the important ideas into **invariants, domain objects, workflows, UI requirements, events, integration boundaries, and phased acceptance criteria**.