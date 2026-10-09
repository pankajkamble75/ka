# KA Human Knowledge Wiki — Technical Specification

**Document ID:** KA-WIKI-001  
**Date:** 2026-10-09  
**Status:** Proposed; research/plan before coding  
**Repository:** `pankajkamble75/ka`  
**Location:** `docs/user-research/notes/KA-Human-Knowledge-Wiki.md`  
**Related:** `docs/user-research/notes/KA-enhancement.md`; Enterprise OS repository `pankajkamble75/enterprise-os-070626`

## 1. Objective

Build a new **Knowledge Wiki** tab in the KA console that allows users to read and edit coherent, formatted knowledge articles (paragraphs, headings, tables, lists, diagrams, citations). Existing **Knowledge Nuggets** remain the internal machine-readable and governance representation. The Wiki provides the human-facing experience of acquiring, combining, understanding and correcting personal, enterprise and internet-sourced knowledge.

**Architectural invariant:** One governed knowledge system, two synchronized representations. Published factual claims originate from approved nuggets with evidence. Wiki edits create drafts and proposed nugget changes, never silently overwrite ACTIVE nuggets or mutate Enterprise OS graphs.

## 2. Existing code and integration seams to reuse

Review the latest default-branch code before implementation:

| File | Existing role / extension |
|---|---|
| `ka/console/app.js` | Vanilla-JS hash router and nav; preserve `#/nuggets`, `#/browse`, `#/processes`, existing source and nugget detail pages; add `#/wiki` |
| `ka/console/styles.css` | Reuse clean styles; add readable typography, document canvas and editor |
| `ka/api.py` | Existing nugget, source, versions and revision endpoints; extend with Wiki API |
| `ka/model.py`, `ka/repository.py` | Source, Evidence, Subject, Nugget, versions and binding records; add separate Wiki page/revision/projection models |
| `ka/governance.py`, `ka/versioning.py`, `ka/conflict.py` | Candidate, revision, conflicts, review and approval; **reuse**, do not duplicate |
| `ka/lineage.py` | Trace Wiki claims to evidence, nuggets and EOS usage |
| `ka/graph_change.py`, `ka/graph_adapter.py` | Existing EOS graph publication gates; Wiki never bypasses these |
| `ka/tests/` | Extend regression and security tests |

Existing API `POST /nuggets/{canonical_id}/propose-revision` already supports a key portion of the edit-to-governed-nugget workflow. Existing process assertions, semantic bindings, evidence spans, source revocation and access controls must be respected.

## 3. Functional requirements

### WIKI-01: Human-readable Wiki (P0)
- New sidebar tab **Knowledge Wiki**, with routes `#/wiki`, `#/wiki/:pageId`, `#/wiki/:pageId/edit`. No changes to existing Nuggets tab behavior.
- Hierarchical browsing by scope (Structure → Domain → Instance), subject and process; search titles/body; optional personal collections.
- Article reader: title, concise overview, coherent paragraphs, headings, lists, tables, images/diagrams when supported, inline citations, related pages, history, source links.
- Keep the page minimal: left knowledge tree, central document canvas, optional right evidence/review sidebar.
- Offer both **Original Source** (faithful document) and **Synthesized Wiki** (approved cross-document knowledge), clearly labeled.

### WIKI-02: Data model (P0)
Implement separate objects using existing persistence conventions:
- `WikiPage`: stable id/slug, title, scope, owner, visibility/permissions, canonical subject/process ids, parent/collection, published revision, created/updated timestamps.
- `WikiPageRevision`: immutable revision id, page id, base revision, editor, timestamp, structured blocks, lifecycle (`DRAFT`, `IN_REVIEW`, `PUBLISHED`, `REJECTED`, `SUPERSEDED`), nugget-version manifest/digest and generator/schema versions.
- `WikiBlock`: stable block id, kind (heading/paragraph/list/table/quote/image/process), text/structured content, section ordering, citations, linked nugget refs, editorial/generated origin.
- `WikiKnowledgeMapping`: many-to-many block/span ↔ canonical nugget/version ↔ evidence/source-version anchors; mapping confidence and relationship (supports/paraphrase/quote).
- `WikiEditProposal`: semantic change classification, original/new blocks, affected nugget candidates, supporting evidence, conflicts, reviewer decisions, publication status.

Page editorial layout and drafts have their own versions. **Approved nuggets and their evidence remain canonical for factual content.** A Wiki page is not a second approved-fact store.

### WIKI-03: Read-only projection (P0)
- Generate pages from approved, visibility-eligible nuggets and process assertions grouped by domain/instance/subject/process.
- Suggested process template: What It Is; Purpose; How It Works; Activities; Inputs/Outputs; Actors; Rules; Events/States; Related Processes; Sources. Only include evidenced sections.
- Use deterministic selection and grouping. LLM prose assistance is optional, bounded and separately validated: every substantive generated claim must map to approved evidence-backed nuggets. Do not invent missing attributes or activities.
- Keep stable page IDs and block mappings across regeneration where possible; record input nugget versions, scope, grammar version and generator version.
- Show unobtrusive citation markers; click to reveal the exact source, page/section/span, and nugget detail.
- Source access filters apply before retrieval, synthesis, caching or serving the page.

### WIKI-04: Human editor and drafts (P0)
- Markdown-backed or structured WYSIWYG editor for paragraphs, headings, lists, tables, links and citations.
- Editable draft, preview, save, cancel, version diff and submit for review. Show unsaved changes and current revision.
- Editing text **does not change** ACTIVE nuggets, the published Wiki or EOS graphs before governance.
- Server-side edit authorization; optimistic locking with expected base revision to prevent lost updates.
- Allow editorial-only changes (headings, ordering, style) to follow an appropriate editorial approval path without creating fake nugget revisions.

### WIKI-05: Semantic edit reconciliation (P0)
On submission:
1. Diff blocks (insert/update/delete/reorder) using stable IDs.
2. Extract factual changes, not just string differences; compare each changed claim to mapped nuggets and existing canonical subjects.
3. Classify: `EDITORIAL_ONLY`, `LINK_EXISTING`, `ADD_CANDIDATE`, `PROPOSE_REVISION`, `PROPOSE_RETIREMENT`, `NEEDS_EVIDENCE`, `UNRESOLVED`.
4. Produce a reviewable mapping of changed paragraph → proposed atomic assertions and supporting evidence.
5. Reuse the existing KA governance/verification/conflict pipeline, including process grammar bindings and source scope.
6. **Deleting a paragraph does not automatically retire a nugget.** Retirement requires an explicit semantic retirement proposal and approval.
7. One paragraph can map to many nuggets; one nugget can support many pages. Preserve unrelated mappings when prose changes.
8. If unsupported factual prose is submitted, keep it as a clearly marked draft pending evidence/review, never publish as verified.

### WIKI-06: Governance and publication (P0)
- Reviewer sees side-by-side rendered old/new article, semantic operations, affected nugget versions, sources, scope, confidence, conflicts and EOS impact.
- Distinct states: draft saved → submitted → nugget candidates approved/rejected → Wiki published → separate EOS graph proposal/applied.
- Approval of the Wiki does **not** automatically authorize an EOS graph mutation. Existing EOS grammar and graph publication gates remain authoritative.
- Re-project published Wiki after nugget approvals/updates; maintain a manifest of exact approved nugget versions.
- Idempotent publication and retry handling; partial cross-service failure is surfaced honestly and recoverably.
- Version history, audit of who changed what/when/why, comparison and rollback or compensating publication.

### WIKI-07: Source and evidence experience (P1)
- Source citations open original document/version and exact page, section or span where available; show synthesis versus quotation explicitly.
- Support source origin, author/publisher, dates, authority and freshness metadata.
- Source revocation, supersession or ACL change marks affected pages stale and triggers revalidation/reprojection.
- Prevent unauthorized disclosure from aggregating nuggets with different PERSONAL/TEAM/DOMAIN/INSTANCE/ENTERPRISE visibility.

### WIKI-08: Process-first integration (P1)
- Process articles expose definition, description, decomposition, types, actors, inputs, outputs, rules, events and states **only when supported by governed knowledge**.
- Bind to the current EOS Process Grammar, Process Types and Data Grammar rather than create independent vocabulary.
- Stable links to EOS domain/instance/process views and to the technical Nugget detail view.
- Missing process knowledge appears as a gap/acquisition request, not as invented narrative.

### WIKI-09: Search and operating quality (P1)
- Permission-aware search across page titles, text and linked nuggets; filter by scope, process, source and status.
- Fast browse with pagination and bounded projection jobs; projection staleness metrics, reconciliation job statuses, errors, audit IDs, token costs.
- Responsive, accessible reading/editing UI; no unnecessary dashboard graphs.

## 4. Proposed APIs (names are proposals, not existing routes)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/knowledge-acquisition/wiki/pages` | Search/list authorized pages |
| POST | `/api/knowledge-acquisition/wiki/pages` | Create page or generation request |
| GET | `/api/knowledge-acquisition/wiki/pages/{page_id}` | Published page and version manifest |
| GET | `/api/knowledge-acquisition/wiki/pages/{page_id}/revisions` | Readable history |
| POST | `/api/knowledge-acquisition/wiki/pages/{page_id}/drafts` | Create editable revision |
| PUT | `/api/knowledge-acquisition/wiki/pages/{page_id}/drafts/{rev_id}` | Save with optimistic lock |
| POST | `/api/knowledge-acquisition/wiki/pages/{page_id}/drafts/{rev_id}/reconcile` | Semantic change preview |
| POST | `/api/knowledge-acquisition/wiki/pages/{page_id}/drafts/{rev_id}/submit` | Governance submission |
| POST | `/api/knowledge-acquisition/wiki/pages/{page_id}/publish` | Authorized validated publication |
| GET | `/api/knowledge-acquisition/wiki/pages/{page_id}/evidence` | Block-level lineage |
| POST | `/api/knowledge-acquisition/wiki/projections` | Generate/refresh projection |

Use documented schema revisions, request IDs, server-derived actor identity, permission validation and idempotency keys. Keep existing endpoint contracts intact.

## 5. Example workflow

```text
Personal / Work / Internet content
          ↓
Existing KA ingestion and extraction
          ↓
Governed atomic Knowledge Nuggets
          ↓
Wiki projection + citations
          ↓
Published readable Wiki article
          ↓
Human edits a paragraph → DRAFT page
          ↓
Semantic diff → added/revised/removed CLAIM proposals
          ↓
Existing nugget governance and approval
          ↓
Refresh published Wiki article
          ↓
EOS graph proposal / validation / publication (if graph-impacting)
```

## 6. Security and nonfunctional invariants

1. No client Wiki edit directly changes ACTIVE nuggets or EOS graphs.
2. No content access widening from page synthesis, citation links, caches or search.
3. Authenticate/authorize every read/edit/review/publish action on the server. Do not trust user-entered `by` fields as proof of identity.
4. Rich-text rendering sanitizes HTML/URLs; prevent XSS and untrusted embeds.
5. Approved nugget/source versions remain immutable; corrections create new versions.
6. Existing review rules, scope inheritance, conflict handling and graph lineage remain in force.
7. LLM output is untrusted proposed prose, not automatic evidence or authority.
8. Two editors changing the same page cannot silently overwrite one another.
9. All generated claims must carry traceable support or be explicitly marked unverified.
10. No replacement of the current Nuggets, Processes, Sources or governance screens.

## 7. Implementation plan

**Phase 0 — Research & design gate.** Verify current code, models, API and EOS compatibility. Deliver architecture note, proposed schema, page wireframes, sequence diagrams, file-level changes, migration and acceptance-test plan. **Do not change application code before this review is approved.**

**Phase 1 — Read-only Wiki.** New tab, page/revision model, projection from ACTIVE nuggets, citations, subject/process grouping, source links, tests.

**Phase 2 — Editing.** Block editor, drafts, diff, preview, ACL checks and concurrent edit protection.

**Phase 3 — Reconciliation.** Claim-level semantic matching to nuggets; proposed corrections/additions/retirements; review UI and existing governance integration.

**Phase 4 — Publication.** Approved nugget-driven Wiki regeneration, EOS graph proposal linking, stale-page handling, publication retry/audit.

**Phase 5 — Hardening.** Revocation, multilingual/diagram support if needed, search quality, performance, accessibility and regression coverage.

Avoid real-time multiplayer editing, inventing a second knowledge store, replacing EOS grammar ownership, or rewriting existing governance.

## 8. Mandatory acceptance tests

1. Five governed nuggets from three independent sources render as one readable article with traceable citations.
2. Personal-only evidence never appears in a broader enterprise page or search result.
3. Editing one paragraph to introduce a new process activity creates a **candidate**, while published Wiki, ACTIVE nuggets and EOS graph remain unchanged pending approval.
4. Approval updates governed nuggets and regenerates the published page; graph changes take the existing separate EOS proposal route.
5. Editing only formatting/headings does not generate nugget revisions.
6. Removing a paragraph does not automatically retire source-supported knowledge.
7. Multi-nugget paragraphs reconcile correctly without overwriting unaffected claims.
8. Revoking a source marks affected page content stale and prevents restricted evidence leakage.
9. Simultaneous conflicting drafts require an explicit merge/conflict outcome.
10. Existing nugget/source/process navigation and governance regression tests still pass.
11. Failed publication can retry idempotently without falsely claiming EOS synchronization.
12. A process Wiki correctly presents process descriptions/decomposition using EOS grammar and labels absent facts as unknown.

## 9. Instructions for coding agent

**Pick up this file as a new research/planning request, not authorization to begin coding.**

1. Read this file and `docs/user-research/notes/KA-enhancement.md`.
2. Review the latest `ka` branch and corresponding EOS grammar APIs before proposing modifications.
3. Produce research report, technical plan, schema/API contracts, minimal multi-page UI prototype, file-by-file implementation map and test plan.
4. Identify reuse opportunities and risks with current nugget revisions, source ACLs, process assertions, versioning and graph publication.
5. Request approval at the implementation gate. No application code changes until approved.
6. After approval, implement incrementally behind explicit tests and keep changes scoped.

**Product principle:** Humans author and read coherent documents. KA maintains governed atomic knowledge. Enterprise OS uses process-aware graphs to understand and operate the enterprise.
