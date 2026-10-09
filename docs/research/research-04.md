# Research 04 - The Knowledge Wiki: readable articles computed from governed nuggets, edits that become governance proposals, and what the console cannot promise until identity exists

Created: 2026-10-09 19:40 UTC
Source note: [KA-Human-Knowledge-Wiki.md](../user-research/notes/KA-Human-Knowledge-Wiki.md)
Class: PRODUCT
Severity: MAJOR
Verdict: Aligned with corrections

## What this research is about

The note asks for a seventh console tab where a person reads coherent articles — paragraphs, headings, tables, citations — composed
from governed knowledge, and edits them; an edit never touches an ACTIVE nugget or a graph but becomes a draft whose factual changes
are turned into candidate nuggets, revisions or retirement proposals that go through the one governance pipeline. The nuggets stay the
machine representation; the article is the human one; the two are kept in step.

The implicit problem is that KA today exposes knowledge only as atoms: a nugget list (`#/nuggets`), a per-scope browse, a per-nugget
detail page and one composed view — the process profile. Fifty-one ACTIVE nuggets across sixty-five sources on the live server (the
Dashboard, 2026-10-09) are already more than a person reads as a list, and the only "document" a reader can open is the original
source text. The note's product principle — humans author and read documents, KA keeps atoms, EOS runs graphs — is the right division.

What the note under-specifies is **what is stored and what is computed**. It proposes five stored objects including a "published
revision" of every page. This research argues the published article must be a *computed projection* over ACTIVE nuggets (exactly as
the process profile already is), and that only what a human authors — drafts, editorial layout, edit proposals, the record of a
publication — is stored. It also names the one promise the note makes that this repository cannot keep yet: server-derived identity.

## Why it matters

- **Reading.** A reviewer who wants to know what KA says about refunds today opens `#/nuggets`, filters, and reads one-sentence
  statements one at a time (`ka/console/app.js:475`, "TAB 2 — Knowledge nuggets: review, resolve, apply"). The process profile
  (`ka/profile.py:1-7`) shows that a composed view is possible and is the one place the console reads like a document.
- **Editing.** The only way a person corrects knowledge is per nugget: "Propose correction → new version" on the nugget page
  (`ka/console/app.js:183-188` → `POST /nuggets/{canonical_id}/propose-revision`, `ka/api.py:455`). A person who notices three wrong
  facts in one paragraph makes three separate proposals and never sees them together.
- **Risk of doing it wrong.** A stored "published page" becomes a second approved-fact store the moment it drifts from the nuggets
  behind it — the exact thing spec §45 forbids ("a document dumping ground", `knowledge-acquisition-requirements.md:1838-1856`) and the
  note itself rules out (note §WIKI-02: "A Wiki page is not a second approved-fact store"). Rendering untrusted rich text is a second
  risk: the console has one escaping helper and no sanitizer (`ka/console/app.js:4`).

## What the code does today

**Composed, read-only views exist, as queries.** `ka/profile.py:1-7`: the process profile is "a COMPOSED, read-only view … a query over
governed versions, never a stored object"; ACTIVE assertions make it, PENDING/CONFLICT ones are listed apart, "Nothing is filled in". Its
fields (`ProcessProfile`, `ka/profile.py:53`: description, type, activities, actors, inputs, outputs, rules, events, states, coverage)
are the note's suggested process template (note §WIKI-03) already, each field carrying its nugget ref and evidence (`ProfileField`,
`ka/profile.py:35-45`). Reached through `GET /processes`, `GET /processes/{key}` (`ka/api.py:939, 945`) and the Processes tab
(`ka/console/app.js:59`).

**Grouping keys exist.** Subjects are registered records (`SubjectRecord`, `ka/model.py:150-157`; collection `subjects`,
`ka/repository.py:125`); nugget versions carry `scope`, `subject/predicate/object`, `knowledge_type`, `tags`, `graph_group`
(`ka/model.py:171-214`); relationships between versions are stored (`KnowledgeRelationship`, `ka/model.py:243`; `relationships_for`,
`ka/repository.py:207`). Lineage per version — sources, evidence excerpts, decision, runs, corrections — is one call
(`LineageService.trace`, `ka/lineage.py:80-92`); evidence carries span ids and offsets (`Evidence.span_id/start/end`, `ka/model.py:104-106`).

**The edit-to-governance path exists, per nugget.** `propose_revision` (`ka/governance.py:466-474`) creates a new candidate version
through `ingest_candidate` with the prior's title/scope and the new statement; the route is `POST /nuggets/{canonical_id}/propose-revision`
(`ka/api.py:455-459`). Corrections from the Enterprise Console take the same shape (`CorrectionService.submit`, `ka/corrections.py:26`;
`ka/api.py:516`). Decisions go through one call (`decide`, `ka/governance.py:312`) with the outcomes at `ka/vocab.py:202-212`. Duplicate
candidates auto-resolve as Keep Existing with the evidence attached (Q11, `attach_provenance`, `ka/governance.py:483`). Semantic fields are
immutable per version (`SEMANTIC_FIELDS`, `ka/versioning.py:17`).

**There is no human retirement path.** `ka/governance.py` has no `retire`; REJECT on a plan-10 re-review retires the prior version, and
`propose_retirement` is the graph side (`ka/graph_change.py:429`). A person cannot say "this ACTIVE nugget is no longer true" except by
proposing a revision and hoping the reviewer rejects the right thing.

**Claim extraction from prose exists.** `extract_from_source` (`ka/governance.py:90-103`) runs the extractor over sections and text to
candidate statements, under Q10's trust tiers; the channel enum has `FEEDBACK` for human-originated knowledge (`ka/vocab.py:151-155`).
Relationship classification between a candidate and existing nuggets — DUPLICATES / SUPPORTS / CONTRADICTS / … — is lexical and structural
(`ConflictDetector.analyze`, `ka/conflict.py:116`; types at `ka/vocab.py:31`), with an LLM used only to explain.

**Identity does not exist.** `ka/security.py:3-14`: the access policy "is a containment, not an access policy". `by` is free text on every
request model (`ka/api.py:128, 140, 149, 157`) and is passed straight into governance (`ka/api.py:433, 459, 469`); the console fills it from
`localStorage` (`who()`, `ka/console/app.js:8`). Search filters on status, scope, authority, tags, author and dates but does **no visibility or
permission filtering** (`ka/search.py:43-72`; the word "visib" does not occur in the file). What the model does carry is a visibility order
and the rule that a nugget never exceeds its sources (`VISIBILITY_ORDER`, `ka/vocab.py:174-175`), enforced at CHANGE_SCOPE/promotion
(architecture §10) and at research time (`permitted_visibility`).

**Rendering.** The console is vanilla JS with template strings written into `innerHTML` (`ka/console/app.js:72`) and one escaping helper
(`esc`, `:4`). There is no Markdown renderer and no HTML sanitizer. The raw source text of a version is already viewable (`SourceVersion.text`,
`ka/model.py:85`; the version card and `GET /sources/{id}/versions/{n}/content`, `ka/api.py:721`).

**Storage and concurrency.** One JSON per object, last write wins (`Collection.put`, `ka/repository.py:60-64`); nothing carries an expected
base version. Nugget comments are a list on the version (`ka/model.py:228`).

**Two things the note names that do not exist as such.** "versions and revision endpoints" beyond the two above — there is no
`/revise` route; and the five-page layout in `KA-enhancement.md` §KA-REQ-012 was declined by Q8 (2026-10-08): the console keeps its tabs and
adds one when a kind of knowledge earns it.

## Architecture this research obeys

| decision | where | bearing on this |
|---|---|---|
| Invariant 3: governed versions immutable; a semantic change is a new version through the one pipeline | `knowledge-acquisition.md` §4; `docs/protected.md` | constrains R6, R7 — every factual change from the wiki is a candidate or revision; nothing else |
| Invariant 2 and Q3: graph changes are separate proposals approved by a named person; never automatic | `knowledge-acquisition.md` §5; Q3 | constrains R8 — wiki publication authorises no graph mutation |
| Invariant 1: no runtime path reads nuggets to answer a question; the console is a human tool | `ka/runtime_guard.py:113-116`; README L64 | obeyed — the wiki is a console read like Processes, not a retrieval endpoint; R3 obeys it |
| The process profile is a query over governed versions, never a stored object; nothing is filled in | `knowledge-acquisition.md` §8 (plan-06) | **this research extends it** — R1 makes every article a projection of the same kind |
| Q8: the console keeps its tabs; a kind of knowledge earns a top-level entry | `knowledge-acquisition.md` §8; Q8 | **extends it** — R10 proposes the seventh tab under the same rule |
| Q1 access policy is containment; identity provider and tenant model are Q4 (open, two-repo) | `knowledge-acquisition.md` §10; Q1, Q4 | constrains R4, R11 — no wiki-only identity; per-caller filtering waits on Q4 |
| Q10: prompt structure and trust tiers; LLM output is never a typed assertion without review | `knowledge-acquisition.md` §3; Q10 | constrains R6, R12 |
| Q11: APPROVE of a same-scope duplicate auto-resolves as Keep Existing | `knowledge-acquisition.md` §4; Q11 | constrains R6 — LINK_EXISTING is this outcome, not a new mechanism |
| A nugget's visibility never exceeds its sources; widening is an explicit decision | `knowledge-acquisition.md` §10; `ka/vocab.py:174` | constrains R4 — a page's ceiling is its narrowest nugget |
| §45 non-goals: not a document dumping ground, not an ungoverned search product; §12 "no document browser as the primary view" | spec §45; `knowledge-acquisition.md` §12 | constrains R1, R10 — the wiki is a seventh tab, not the primary view, and stores no facts |
| Human-readable articles, drafts and editorial layout | — | **silent — no document owns this; R2, R5 propose the section** (`knowledge-acquisition.md` §8a "The Knowledge Wiki") |

## Reading of the source note

The note proposes: a Wiki tab with reader and editor; five stored objects (page, revision, block, knowledge mapping, edit proposal); a
read-only projection from approved nuggets grouped by scope/subject/process with citations; a Markdown or structured editor with drafts
and optimistic locking; semantic reconciliation of edits into seven classes; a review screen and a publication state machine kept
separate from graph proposals; source/evidence, process-first and search requirements; ten invariants; twelve acceptance tests; five
phases; a gate before any code.

| Claim in the note | Verdict | Evidence |
|---|---|---|
| `POST /nuggets/{canonical_id}/propose-revision` already supports the edit-to-governed-nugget workflow | Confirmed | `ka/api.py:455-459` → `ka/governance.py:466` |
| `ka/governance.py`, `ka/versioning.py`, `ka/conflict.py` hold candidate, revision, conflicts, review, approval — reuse | Confirmed | `ingest_candidate` :161, `decide` :312; `SEMANTIC_FIELDS` `ka/versioning.py:17`; `ConflictDetector` `ka/conflict.py:98` |
| `ka/lineage.py` traces claims to evidence, nuggets and EOS usage | Confirmed | `trace` `ka/lineage.py:80`, `where_used` :61 |
| Existing "versions and revision endpoints" | Partly true | `GET /nuggets/{id}/versions` :405, `compare` :413; no `/revise`; one revision route |
| Approved nuggets remain canonical; a page is not a second approved-fact store | Confirmed as a rule, contradicted by the model | the note's `WikiPageRevision.PUBLISHED` stores article text; §The research 1 |
| Server-side edit authorization; server-derived actor identity | Contradicted today | `ka/security.py:3-14` containment only; `by` free text `ka/api.py:128`; Q4 open |
| Source access filters apply before retrieval, synthesis, caching, serving | Partly achievable | no caller principal exists; visibility ceiling by construction is achievable (`ka/vocab.py:175`); per-caller filtering waits on Q4 |
| Process template: What It Is … Sources, only evidenced sections | Confirmed — it exists as the profile | `ProcessProfile` `ka/profile.py:53`; `coverage` :144 |
| `PROPOSE_RETIREMENT` class | Needs a path that does not exist | no human retirement in governance; REJECT on a re-review only (plan-10) |
| Rich-text rendering sanitizes HTML | Nothing to reuse | `esc` only, `ka/console/app.js:4`; no sanitizer or Markdown renderer |
| Optimistic locking with expected base revision | Nothing to reuse | `Collection.put` last-write-wins `ka/repository.py:60` |
| Keep existing tabs; add `#/wiki` | Confirmed as the Q8 rule | `TAB_LABELS` `ka/console/app.js:59`; Q8 |
| "Original Source" view | Already exists | `SourceVersion.text` `ka/model.py:85`; `ka/api.py:721` |

## The research

### 1. What is stored and what is computed

The note's five objects mix two kinds of thing. A `WikiPageRevision` in `PUBLISHED` state with "structured blocks" is a stored copy of
facts; a `WikiBlock` with "linked nugget refs" is a stored mapping that must be kept in step with every approval, supersession and
revocation; a `WikiKnowledgeMapping` with "mapping confidence" is a second record of what the nuggets already say about themselves.
Every one of those drifts the moment a nugget changes, and the note then needs "re-project after approvals", "maintain a manifest",
"mark stale", "reconciliation job statuses" and "projection staleness metrics" (§WIKI-06, §WIKI-07, §WIKI-09) to chase the drift.

The repository already has the answer in `ka/profile.py`: the profile is computed from ACTIVE versions on every request, PENDING ones
listed apart, unknowns shown as unknown. It is never stale because it is never stored. Fifty-one ACTIVE nuggets compose in
milliseconds; the plan-09 benchmark puts a 100k-version lexical scan at 3.7 s, which is the only figure that would make caching a question
(R13), and caching a computed value is a different thing from storing a fact.

So the rule this research proposes: **the published article is a projection.** `article(page_key) = render(select(ACTIVE versions
visible at the page's ceiling, grouped by the page's key), layout)`. What is stored is only what a human authors and what cannot be
recomputed:

| stored | why it cannot be computed |
|---|---|
| `WikiPage` — key, title, scope, kind (`process` / `subject` / `authored`), layout (section order, headings, which nuggets are pinned where, prose-only blocks), visibility ceiling, created/updated | editorial layout is a human choice |
| `WikiDraft` — page key, `base_layout_rev`, `base_manifest` (the ACTIVE set the editor saw), blocks as edited, editor, timestamps, state DRAFT / SUBMITTED / CLOSED | the edit itself |
| `WikiEditProposal` — draft id, the block diff, per-block classification, the candidate / revision refs it produced, reviewer decisions | the reconciliation result and its governance ids |
| `WikiPublication` — page key, layout rev, manifest digest, who, when | the audit record of "this is what was shown as published" |

The note's `WikiBlock` survives as the unit of a draft and of layout, not as a stored projection of a nugget. The note's
`WikiKnowledgeMapping` disappears: a block's citations are the nugget refs it names, and a nugget's "where shown" is a query over pages
whose selection includes it. "Keep stable page IDs across regeneration" (§WIKI-03) is free when the key is deterministic: `process:<canonical
key>`, `subject:<canonical key>`, `scope:<type>|<id>`, plus authored pages with a slug. The manifest the note wants (exact nugget versions,
scope, grammar version, generator version) becomes a digest computed on read and recorded at publication; staleness is `digest(now) !=
digest(published)`, with nothing to run.

### 2. The projection: process pages are the profile, the rest group by subject and scope

Process articles are `ProcessProfile` rendered as prose sections in the note's order, each sentence a statement with its citation; a
section with no evidenced field is omitted, and `coverage` becomes a short "Not yet known" list at the end — which is the note's "label
absent facts as unknown" (§WIKI-08, acceptance test 12) and already the profile's rule. Subject pages (a concept, an entity, a rule family)
select ACTIVE versions whose `subject.canonical_key` matches, then group by `knowledge_type` and `predicate`; scope pages select by scope and
group by subject; authored pages pin specific refs into a human layout. In every kind, a sentence is a statement from one version, cited
by `ref`; nothing in a projected section is written by the projector.

Deterministic prose is the default and is enough: statements are already sentences (`KnowledgeNuggetVersion.statement`), and grouping with
headings is what turns a list into a document. LLM assistance (R12) is a bounded, separately validated layer on top: when on, it may
rewrite a section's statements into connected prose, and every output sentence must cite at least one ref from its input; a verifier drops
any sentence without a citation or with a citation that is not in the input set. Its output is never evidence, never a typed assertion, and
is marked "synthesized" in the UI (Q10, §WIKI-03). This is not an Invariant 1 question: the wiki is a human reading tool in the Knowledge
Console (spec §27), the same as the nugget list, and no runtime path reaches it (`ka/runtime_guard.py:113`).

The "Original Source" view the note asks for is the existing source page plus the version's text and bytes; a page's Sources section links
there. Building a second faithful-document renderer would duplicate `#/source/:id`.

### 3. Visibility: a ceiling by construction now, a principal later

Today no caller has an identity, so "filters apply before retrieval" cannot be a per-user filter. What **can** be enforced is the rule the
model already states: a derived thing is never wider than its narrowest input (`ka/vocab.py:174-175`). For the wiki:

- every page declares a visibility ceiling, defaulting to ENTERPRISE for process/subject/scope pages;
- the projection selects only versions whose `visibility` is at or above the ceiling in `VISIBILITY_ORDER`, so a PERSONAL or TEAM nugget never
  enters an ENTERPRISE page (acceptance test 2), and a page that pins a narrower nugget is itself narrowed, never the nugget widened;
- wiki search runs over page titles and the projected text, and inherits the same ceiling; since `ka/search.py` has no visibility filter at
  all (`:43-72`), the wiki must not call it unfiltered and must not become the broader search product §45 forbids.

Per-caller enforcement — "this person may read PERSONAL pages of their own" — is Q4's identity work and arrives with it; the ceiling makes the
wiki safe in the meantime, and a PERSONAL page is simply not served while there is no one to serve it to. The note's invariant 2 ("no
content access widening from synthesis, citation links, caches or search") holds by construction under this rule.

### 4. Editing: a block model, a Markdown subset, no HTML

Two choices follow from `esc` being the only rendering safeguard (`ka/console/app.js:4`). First, the stored form of a draft is a block list
(heading, paragraph, list, table, quote, citation), each block's text a plain string with an inline Markdown subset (emphasis, links with
`http(s)` only, `[[KN-001:v3]]` citations); the server parses the editor's Markdown into blocks and refuses raw HTML, scripts, data URLs and
unknown constructs. Second, the console renders blocks through `esc` exactly as it renders statements today — there is no HTML to sanitize
because none is ever stored or produced. Images are the existing image store by number (`ka/images.py`), referenced, not embedded.

Lost updates: a draft carries `base_layout_rev` and `base_manifest`; `PUT …/drafts/{id}` requires the client's `expected_rev` to equal the
stored one and returns 409 otherwise; a second draft on the same page is allowed but shows "another draft exists" and submitting while the
other is SUBMITTED is refused until the reviewer closes one (acceptance test 9 — an explicit outcome, not a merge algorithm). This is the first
object in the repository with an expected-version write; `Collection.put` stays last-write-wins for everything else.

Editorial-only changes (headings, order, wording that extracts to the same statements) never produce candidates (acceptance test 5): they
update the page's layout through the same draft → review path but with no governance ids, and the reviewer's approval is an editorial one.

### 5. Reconciliation: existing atoms, one new seam

Submission runs in this order, every step on something that exists:

1. **Block diff** by stable block id: inserted, updated, deleted, moved (new, small).
2. **Claim extraction** on inserted and updated blocks: the existing extractor over the block text with the page's scope, channel `FEEDBACK`
   (`ka/vocab.py:155`), the editor as `created_by`, under Q10's structure and tiers (`ka/governance.py:90-103` is the entry; the wiki calls the
   same extractor on a block instead of a source section). A block with no extractable statement is EDITORIAL_ONLY.
3. **Comparison** of each extracted statement with the nuggets the block cites and with the page's selection: `ConflictDetector.analyze`
   (`ka/conflict.py:116`) gives DUPLICATES → LINK_EXISTING (and Q11 makes an accidental APPROVE harmless), REFINES/EXTENDS/CONTRADICTS against a
   cited nugget → PROPOSE_REVISION of that canonical id, no relation → ADD_CANDIDATE; a statement whose prose names no source and whose
   extraction has no evidence → NEEDS_EVIDENCE (kept in the draft, marked, never published as verified — acceptance test 8's spirit); anything
   the heuristics cannot place → UNRESOLVED for the reviewer.
4. **Deleted blocks** produce no governance operation (acceptance test 6); the editor may attach an explicit retirement request to a cited
   nugget, which is R7.
5. **Submission** creates candidates through `ingest_candidate` and revisions through `propose_revision` — the one pipeline — and records
   their refs on the `WikiEditProposal`. A paragraph citing three nuggets with one changed claim yields one revision and two untouched
   citations (acceptance test 7), because the comparison is per extracted statement against its cited nugget, not per paragraph.

The one new seam is the block ↔ claim comparison; its inputs and outputs are all existing objects.

### 6. Retirement needs a governance path

A person who deletes a paragraph is not retiring knowledge (acceptance test 6), but a person who *knows* a nugget is wrong needs a way to
say so, and governance has none for an ACTIVE version. plan-10 built the closest thing: a same-statement revision flagged by analysis
(`source_revoked`), where REJECT retires the prior and proposes the graph retirement through `propose_retirement`
(`ka/graph_change.py:429`). The recommendation (R7) is to generalise that mechanism rather than add a second one: a revision may carry a
`review_reason` (today "source revoked"; new "retirement requested by <person>: <why>"), and REJECT on such a revision retires the prior
exactly as plan-10 does. This touches `ka/governance.py`, which is protected; the plan carries the seven-step protocol, and the covering
tests of plan-10 stay unmodified because the revoked-source case is unchanged.

### 7. Review and publication, kept apart from graphs

The reviewer sees the draft and the current article side by side, the classified operations, and each produced candidate's conflict
analysis — all of which is today's nugget review, grouped by proposal. Decisions are `decide` calls (`ka/governance.py:312`); the proposal
is resolved when every produced ref has a decision. Publication then means: apply the draft's layout to the page, record a
`WikiPublication` with the current manifest digest, and nothing else — the article's facts are whatever is ACTIVE, which the approvals just
changed. Graph proposals arise from approvals as they do now (`_on_approved`, `ka/service.py`) and are decided separately (Q3, Invariant 2);
the wiki shows their state and never advances it (acceptance tests 3, 4, 11). Because publication writes one local record, "idempotent
publication and retry" collapses to a replayable write; there is no cross-service publication to fail.

### 8. Staleness and revocation

A page is stale when its published digest differs from the digest of the current selection; the reader sees "updated since publication" and
the projection is already the new state. Revocation (plan-10, plan-21) flags derived versions `source_revoked` and opens re-reviews; the
projection shows those versions with the same flag the nugget page shows (acceptance test 8) and the page's Sources section marks the source
revoked. No job runs; nothing is re-projected because nothing was projected into storage.

### 9. Console shape

Q8's rule is that a kind of knowledge earns a top-level entry and nothing else moves. Readable articles are such a kind; the recommendation
is "7 · Wiki" at `#/wiki`, `#/wiki/:key`, `#/wiki/:key/edit`, `#/wiki/:key/review/:proposal`, with the left tree by scope → process/subject,
the article in the centre, and the evidence sidebar as the existing lineage rendering. Nothing in tabs 1–6 changes (acceptance test 10).
§12's "no document browser as the primary view" stands: the primary view remains Add → Nuggets → Browse.

### 10. What the note asks for that cannot be promised yet

"Server-side edit authorization" and "server-derived actor identity" (note §WIKI-04, invariant 3) require a principal. Q1 (2026-10-08) made
the access policy a containment on purpose and put identity under Q4 as a two-repo plan. The wiki therefore records editors and reviewers the
way decisions record `by` today — a name the person types — and the optimistic lock, not identity, is what prevents lost updates. Building a
wiki-only login would be a second access path beside Q1's; this research recommends against it (R11) and names Q4 as where identity arrives
for the whole console at once.

## Where I differ

1. **Published pages must not be stored.** The note's `WikiPageRevision.PUBLISHED` with blocks and a nugget manifest is a copy of facts that
   needs re-projection, staleness metrics and reconciliation jobs to stay honest (§WIKI-06, §WIKI-09). The profile precedent
   (`ka/profile.py:1-7`) and spec §45 both say the opposite: compute it. Store layout, drafts, proposals and the publication record only.
2. **`WikiKnowledgeMapping` is redundant.** Citations in blocks and the nuggets' own lineage (`ka/lineage.py:80`) already give both directions;
   a stored many-to-many with "confidence" is a third copy that drifts.
3. **Identity cannot be server-derived in this repository today** (`ka/security.py:3-14`, `ka/api.py:128`); the note's requirement is right and
   is Q4's, not the wiki's. The wiki should not carry its own.
4. **"Original Source" view already exists** (`#/source/:id`, `ka/api.py:721`); link to it.
5. **No WYSIWYG, no HTML.** With `esc` as the only safeguard (`ka/console/app.js:4`), a block model with a Markdown subset is the design that
   makes the note's XSS invariant true by construction rather than by a sanitizer nobody has written.
6. **Retirement is a gap the note assumes away.** `PROPOSE_RETIREMENT` has no governance path; it needs the plan-10 mechanism generalised (R7),
   under the protected-code protocol.

## Open questions

- **Q17 — the seventh tab.** Add "7 · Wiki" (recommended, Q8's rule) or fold articles into Browse by scope as a mode? Settled by the author.
- **Q18 — human retirement.** Generalise plan-10's re-review (recommended) or leave retirement to reviewers rejecting revisions? Settled by the
  author because it touches protected governance.
- Whether 100k-version selection needs a cache is settled by measurement after the projection exists (R13).

## What this does not cover

Phasing, file-by-file changes, schema field lists, wireframes and the test plan are the implementation plans' job
(`create-implementation-plan`); the note's phases 1–5 are a reasonable order but are not adopted here. Multilingual support and diagram
rendering (note §Phase 5) are not researched. Identity (Q4) and the Data Platform's search index (research-03 §7) are not reopened.

## Research points (14)

| # | Research point | Kind | Class | Severity | Where argued |
|---|---|---|---|---|---|
| R1 | The published article is a projection computed from ACTIVE versions on read (the profile's rule); only layout, drafts, edit proposals and publication records are stored; no `WikiPageRevision.PUBLISHED`, no stored knowledge mapping | decide | PRODUCT | MAJOR | §1, §Where I differ 1–2 |
| R2 | Wiki objects: `WikiPage` (deterministic key, layout, ceiling), `WikiDraft` (blocks, base layout rev, base manifest, state), `WikiEditProposal` (diff, classes, produced refs, decisions), `WikiPublication` (digest, who, when); one JSON per object | build | PRODUCT | MAJOR | §1 |
| R3 | Projection: process pages from `ProcessProfile` sections in the note's order with "Not yet known"; subject and scope pages grouped by subject / knowledge type / predicate; authored pages pin refs; every sentence a cited statement; Sources section links the existing source page | build | PRODUCT | MAJOR | §2 |
| R4 | Visibility ceiling by construction: a page selects only versions at or above its ceiling in `VISIBILITY_ORDER`; PERSONAL/TEAM never enter wider pages; wiki search inherits the ceiling and never calls the unfiltered search; per-caller filtering waits on Q4 | build | PRODUCT | MAJOR | §3 |
| R5 | Editor: block model with an inline Markdown subset parsed server-side (no raw HTML, `http(s)` links only, `[[ref]]` citations), rendered through `esc`; drafts with `expected_rev` optimistic lock (409); second drafts allowed, concurrent submission refused explicitly | build | PRODUCT | MAJOR | §4 |
| R6 | Reconciliation: block diff → existing extractor on changed blocks (FEEDBACK channel, page scope, Q10 tiers) → `ConflictDetector` comparison with cited nuggets → EDITORIAL_ONLY / LINK_EXISTING / ADD_CANDIDATE / PROPOSE_REVISION / NEEDS_EVIDENCE / UNRESOLVED → `ingest_candidate` / `propose_revision`; deletions produce nothing | build | PRODUCT | MAJOR | §5 |
| R7 | Human retirement: generalise plan-10's re-review — a revision carries `review_reason` ("retirement requested by …"); REJECT retires the prior as today; protected governance under the seven-step protocol | decide | PRODUCT | MAJOR | §6 |
| R8 | Review and publication: side-by-side article/draft with classified operations and produced candidates; decisions through `decide`; publication = apply layout + record digest; graph proposals shown, never advanced; replayable local write, no cross-service retry | build | PRODUCT | MAJOR | §7 |
| R11 | No wiki-only identity or login: editors and reviewers are recorded as `by` is today; the lock, not identity, prevents lost updates; server-derived identity arrives with Q4 for the whole console | decide | PRODUCT | MAJOR | §10, §Where I differ 3 |
| R9 | Staleness is `digest(now) != digest(published)` shown on the page; revoked-source flags and re-reviews surface in the article; no projection job | build | PRODUCT | MINOR | §8 |
| R10 | Console: "7 · Wiki" tab with `#/wiki`, `#/wiki/:key`, `/edit`, `/review/:proposal`; tree by scope → process/subject; tabs 1–6 unchanged; Original Source = existing source page (Q17) | decide | PRODUCT | MINOR | §9 |
| R12 | LLM prose assistance off by default; when on, every output sentence must cite an input ref or is dropped by a verifier; output is marked synthesized and is never evidence | decide | PRODUCT | MINOR | §2 |
| R13 | Measure projection cost at 100k versions with the plan-09 benchmark before adding any cache or bounded job | investigate | PRODUCT | MINOR | §1, §Open questions |
| R14 | Regression gate: the route table and tab labels of the existing console and every existing suite are unchanged by the wiki (byte-compare the routes list and `TAB_LABELS` prefix) | build | TEST INFRASTRUCTURE | MINOR | §9 |

**Total research points: 14.** 8 `build`, 5 `decide`, 1 `investigate`.

**Class and severity split (`Q231`):** 13 `PRODUCT`, 1 `TEST INFRASTRUCTURE`; 0 `CRITICAL`, 9 `MAJOR`, 5 `MINOR`. The MAJOR rows are the
capability itself and the two gaps the note assumed away (retirement, identity).

**Coverage of the source note (`Q199`):** covers all nine requirement groups WIKI-01 … WIKI-09, all ten invariants (§6) and all twelve
acceptance tests (§8, adopted below as product tests); the proposed API names (§4) and the five phases (§7) are left to the implementation
plans; multilingual and diagram support (§7 Phase 5) are not researched.

## Product tests (12)

| # | Product test | Proves | Runnable today? |
|---|---|---|---|
| PT1 | Five governed nuggets from three independent sources render as one readable article with a citation on every sentence that opens the source span and the nugget | R1, R3 | no — needs the projection plan |
| PT2 | A PERSONAL-only nugget never appears in an ENTERPRISE page or in wiki search results | R4 | no — needs the projection plan |
| PT3 | Editing one paragraph to add a process activity creates a candidate while the published article, ACTIVE nuggets and the graph are unchanged until approval | R5, R6 | no — needs the editor and reconciliation plans |
| PT4 | Approving that candidate changes the governed nuggets and the article reflects it; any graph change takes the separate proposal route | R8 | no — needs the review plan |
| PT5 | Changing only headings and order produces no candidate or revision | R6 | no — needs the reconciliation plan |
| PT6 | Deleting a paragraph retires nothing; an explicit retirement request on a cited nugget reaches a reviewer and REJECT retires it | R6, R7 | no — needs the reconciliation plan and the Q18 decision |
| PT7 | A paragraph citing three nuggets with one changed claim yields one revision and leaves the other two citations untouched | R6 | no — needs the reconciliation plan |
| PT8 | Revoking a source marks the article's affected statements and the page stale, and the revoked source's evidence is not shown as current | R9 | no — needs the projection plan |
| PT9 | Two drafts on one page: the second save with a stale expected revision is refused with 409, and submitting while the other is under review is refused with a named reason | R5 | no — needs the editor plan |
| PT10 | Every existing console route and tab, and every existing test suite, is unchanged | R14 | no — the gate exists once the wiki does; it would pass trivially before |
| PT11 | Publishing after approvals records a digest; a second publish with nothing changed is a no-op that reports "already published" | R8 | no — needs the review plan |
| PT12 | A process article presents description, decomposition, actors, inputs, outputs, rules, events and states from the profile with EOS grammar labels, and lists what is not yet known | R3 | no — needs the projection plan |

**Total product tests: 12.** None can run today; all wait on the plans that build R2–R9, and PT6 also on the author's Q18.
