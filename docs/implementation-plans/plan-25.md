# Plan 25 - The read-only Knowledge Wiki: computed articles with citations, a visibility ceiling, staleness by digest, the seventh tab, and the projection cost measured (research-04 R2, R3, R4, R9, R13; builds decided R10, R12)

Created: 2026-10-09 21:10 UTC

## Problem Description

KA shows knowledge only as atoms (nugget list, browse, nugget detail) and one composed view (the process profile). research-04 and the
author's answers to Q17, Q19 and Q20 decide what the readable form is: an **article computed on read** from ACTIVE versions selected by
a page key (process, subject, scope) at a visibility ceiling, every sentence a governed statement cited by its ref, nothing written by
the projector; stored objects are only what a person authors; a seventh tab "7 · Wiki"; model prose off by default behind a per-article
switch with a citation verifier. Desired outcome (PT1, PT2, PT8, PT12): a reader opens `#/wiki`, picks a process or subject, and reads an
article whose citations open the source span and the nugget; a PERSONAL nugget never appears in an ENTERPRISE page or wiki search; a
revoked source marks the article's statements and the page stale; a process article lists what is not yet known.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §8a The article is a projection, never a stored page (Q19) | `knowledge-acquisition.md` §8a | ⏳ decided, not built | **builds it** — state → ✅ for the read side on upload |
| §8a Visibility ceiling by construction; no wiki identity (Q1, Q4) | `knowledge-acquisition.md` §8a, §10 | ⏳ decided | **builds the ceiling**; identity not touched |
| §8a Where it sits: seventh tab, routes, tabs 1–6 unchanged (Q17) | `knowledge-acquisition.md` §8a | ⏳ decided | **builds the tab and the reader routes**; editor/review routes are plans 26/28 |
| §8a Model prose off by default + verifier (Q20) | `knowledge-acquisition.md` §8a | ⏳ decided | **builds the switch and the verifier** |
| §8 The process profile is a query, never a stored object | `knowledge-acquisition.md` §8 | ✅ built | **reused** — process articles render `ProcessProfile` |
| Invariant 1 (no runtime retrieval) | `ka/runtime_guard.py` | ✅ built | **not touched** — the wiki is a console read like Processes |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R14)

Source: [research-04](../research/research-04.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1, R7, R10, R11, R12 | ✅ decided | Q19, Q18, Q17, Q1/Q4, Q20 — R10 and R12 are BUILT here (tab, reader routes, prose switch) |
| R2 objects | ✅ in scope | Phase 1 — all four models; drafts and proposals are used by plans 26–28 |
| R3 projection | ✅ in scope | Phase 1 |
| R4 ceiling | ✅ in scope | Phase 1 |
| R9 staleness | ✅ in scope | Phase 1 (digest) |
| R13 cost measurement | ✅ in scope | Phase 3 (benchmark row) |
| R5 editor | ⏭️ deferred | plan-26 |
| R6 reconciliation | ⏭️ deferred | plan-27 (with R7's build) |
| R8 review/publication, R14 gate | ⏭️ deferred | plan-28 |

**Covered here: 5 of 14** (+2 decided rows built). Deferred: 4.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 five nuggets from three sources → one article, every sentence cited, citation opens span and nugget | R1, R3 | **GREEN** |
| PT2 PERSONAL nugget never in an ENTERPRISE page or wiki search | R4 | **GREEN** |
| PT8 revoked source marks statements and the page stale | R9 | **GREEN** (the flags; re-review itself is plan-10) |
| PT12 process article from the profile with "not yet known" | R3 | **GREEN** |
| PT10 existing routes unchanged | R14 | still RED — the gate is plan-28's (this plan must not break it) |

## Scope

In: `ka/model.py` (`WikiPage`, `WikiDraft`, `WikiEditProposal`, `WikiPublication`), `ka/repository.py` (four collections), `ka/wiki.py` (new:
`WikiService` — page keys, selection at the ceiling, rendering to blocks, digest, search, prose switch + verifier), `ka/service.py` (wiring),
`ka/api.py` (`GET /wiki/pages`, `GET /wiki/pages/{key}`, `GET /wiki/pages/{key}/evidence`, `GET /wiki/search`), `ka/console/app.js` (tab 7,
`#/wiki`, `#/wiki/:key`), `ka/console/styles.css` (article typography), `tools/bench_store.py` (projection timing row), tests, flow, docs.

Out: editing (plan-26), reconciliation and retirement (plan-27), review/publication records' write path and the regression gate (plan-28),
identity.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- Page keys: `process:<canonical_key>`, `subject:<canonical_key>`, `scope:<TYPE>|<id>`; authored pages (`page:<slug>`) exist in the model and
  are listed when a `WikiPage` record exists, but are only created by plan-26's editor.
- `WikiPage` is created lazily on first read for derived keys (so layout can be attached later) with `ceiling="ENTERPRISE"`; a stored page's
  `ceiling` narrows the selection. Selection rule: `VISIBILITY_ORDER.index(v.visibility) >= VISIBILITY_ORDER.index(ceiling)`.
- Article blocks: `{id, kind: heading|paragraph|list|table|quote|note, text, refs: [ref…], level}`; a paragraph's text is one or more
  statements joined by a space, each statement followed by its citation marker; the console renders `[n]` markers linking to the nugget and
  shows the evidence sidebar from `nugget_detail`-style data (`sources`, `evidence` with span ids and offsets, `published_as`).
- Process article sections, in the note's order, from `ProcessProfile`: What it is (description + type), Activities (ordered), Actors,
  Inputs, Outputs, Entities, Rules, Events, States, Related, Sources; a section with no evidenced field is omitted; a closing "Not yet known"
  list from `coverage` rows whose status is not `evidenced`; "Pending" lists PENDING/CONFLICT assertions apart.
- Subject article: ACTIVE versions whose `subject.canonical_key` matches, grouped by `knowledge_type` then `predicate`. Scope article: ACTIVE
  versions in the scope, grouped by subject then knowledge type; versions without a subject under "General".
- Digest: sha256 over the sorted `(ref, status, visibility)` tuples of the selection plus the layout revision; `stale = published_digest !=
  digest(now)` when a `WikiPublication` exists, else `never published`.
- Revoked flags: a version with `analysis.source_revoked` renders with a "source revoked · re-review pending" marker; the Sources section marks
  revoked sources.
- Wiki search: lexical over page titles and projected text at each page's ceiling, over derived keys that have ACTIVE content; it never calls
  `SearchService` for nugget bodies.
- Prose switch: `?prose=llm` on the page route (default deterministic). When on, each section's statements go to the provider with Q10's
  structure; the verifier splits the output into sentences, keeps a sentence only if it contains at least one `[[ref]]` marker from the
  section's input refs, and labels the block `synthesized`; with the stub provider the output is the deterministic text (verifier still runs).
- R13: `tools/bench_store.py` gains a `wiki scope article` timing (projection of the largest scope) and a row is appended to the benchmarks
  file at 10k and 100k.

## Phases

### Phase 1 - Objects, service, routes
- `ka/model.py`, `ka/repository.py`, `ka/wiki.py`, `ka/service.py`, `ka/api.py`.
- **Protected-code touched:** none

### Phase 2 - Console
- tab 7, `#/wiki` (tree by scope → processes / subjects, search box), `#/wiki/:key` (article + evidence sidebar + prose switch + stale line).
- **Protected-code touched:** none

### Phase 3 - Tests, flow, benchmark, docs
- `ka/tests/test_plan25_wiki_read.py`; `e2e/plan25_wiki_flow.py`; `tools/bench_store.py` row; architecture §8a state; README tab list.
- **Protected-code touched:** none

## Code blocks (B1..B7)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/wiki.py` | the service |
| B2 | `ka/model.py` | four wiki models |
| B3 | `ka/repository.py` | four collections |
| B4 | `ka/service.py`, `ka/api.py` | wiring; routes (one block each) |
| B5 | `ka/console/app.js` | tab, routes, two views |
| B6 | `ka/console/styles.css` | article typography |
| B7 | `tools/bench_store.py` | projection timing |

## Deliverables (D1..D9)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `WikiPage`, `WikiDraft`, `WikiEditProposal`, `WikiPublication`; collections | `ka/model.py`, `ka/repository.py` | 1 |
| D2 | `WikiService.select(key, ceiling)` and `article(key, *, prose)` → blocks with refs; process/subject/scope kinds | `ka/wiki.py` | 1 |
| D3 | visibility ceiling applied in `select`; `page_ceiling(key)` | `ka/wiki.py` | 1 |
| D4 | `digest(key)` and `stale(key)`; revoked markers | `ka/wiki.py` | 1 |
| D5 | `WikiService.search(q)` at the ceiling; `list_pages(scope)` tree | `ka/wiki.py` | 1 |
| D6 | prose switch with the citation verifier (`synthesize(section)`) | `ka/wiki.py` | 1 |
| D7 | routes `GET /wiki/pages`, `GET /wiki/pages/{key}`, `GET /wiki/pages/{key}/evidence`, `GET /wiki/search` | `ka/api.py` | 1 |
| D8 | console tab 7 and two views; styles | `ka/console/app.js`, `styles.css` | 2 |
| D9 | benchmark row (R13); live flow; docs | `tools/bench_store.py`, `e2e/`, docs | 3 |

**Total deliverables: 9.**

## Positive Test Cases (P1..P8)
- **P1** — PT1: five ACTIVE nuggets from three sources on one subject → one article; every paragraph's refs resolve to ACTIVE versions; the evidence route returns span ids, offsets and source titles for each ref.
- **P2** — PT12: a process with description, activities, actors and one unevidenced required slot → sections in order, missing sections omitted, "Not yet known" names the slot; pending assertions listed apart.
- **P3** — scope article groups by subject then knowledge type; a version without subject lands under "General"; scope key `scope:DOMAIN|x`.
- **P4** — digest changes when a version is approved or superseded; `stale` is false right after a `WikiPublication` with the current digest and true after a change; never-published reports so.
- **P5** — a revoked source's derived versions render with the revoked marker and the Sources section marks the source.
- **P6** — wiki search finds a page by title and by a statement word; results carry key, kind, title, snippet.
- **P7** — `?prose=llm` with the stub provider: blocks are labelled `synthesized`, every sentence carries a ref from the section, the verifier dropped a planted uncited sentence (a provider double returns one).
- **P8** — live flow: tab 7 present, tree lists the process, the article renders with `[n]` citations, clicking one opens the nugget page, the evidence sidebar shows the span; no JS errors.

## Negative Test Cases (N1..N5)
- **N1** — PT2: a PERSONAL nugget on the subject is absent from the ENTERPRISE page, from `/wiki/pages/{key}/evidence` and from wiki search; a page with `ceiling=PERSONAL` includes it.
- **N2** — a PENDING_REVIEW or SUPERSEDED version never enters an article's paragraphs (pending appears only in the "Pending" list).
- **N3** — the projector writes nothing: a read creates at most the lazy `WikiPage` record and no nugget file changes (byte-compare); no `WikiPublication` is created by reading.
- **N4** — unknown key → 404; a key for a subject with no ACTIVE versions → 404 with "no governed knowledge yet"; malformed key → 400.
- **N5** — tabs 1–6 and the existing routes array prefix are unchanged (compare `TAB_LABELS` keys and the first 14 route regexes against HEAD).

## Plan totals

**Research points covered: 5 of 14 · Deliverables: 9 · Positive cases: 8 · Negative cases: 5 · Test cases total: 13 ·
Product tests served: 4 of 12 (PT1, PT2, PT8, PT12 turn green here).**

## Implementation Notes
- Written against `0fb9beb`. No protected code. The live service gets the new tab on restart; the flow runs on a second server.
