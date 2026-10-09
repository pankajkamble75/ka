# Plan 26 - The wiki editor: drafts in a Markdown subset parsed into blocks, no HTML ever, an optimistic lock, authored pages (research-04 R5)

Created: 2026-10-09 22:20 UTC

## Problem Description

plan-25 made every article readable and computed. research-04 §4 and the author's answers decide how a person edits one: a draft is a
block list whose text carries an inline Markdown subset, parsed server-side (headings, paragraphs, lists, quotes, tables; bold, italics,
`http(s)` links, `[[ref]]` citations); raw HTML, scripts, data URLs and unknown constructs are refused; the console renders blocks only
through its escaping helper, so there is nothing to sanitize. Saves carry an expected revision and are refused with 409 when stale; a
second draft on a page is allowed and visible; submitting while another draft is under review is refused with a named reason. Editing
never changes an ACTIVE nugget, the article or a graph (PT3's first half, PT9). Authored pages (`page:<slug>`) are created here.

Reconciliation of a submitted draft into governance operations is plan-27; review and publication are plan-28. This plan's "submit"
moves a draft to SUBMITTED and records the block diff against the article the editor started from.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §8a No HTML: block lists with an inline Markdown subset parsed server-side; render through `esc` | `knowledge-acquisition.md` §8a | ⏳ decided | **builds it** |
| §8a Edits are governance proposals; editing changes nothing until governance | `knowledge-acquisition.md` §8a; Invariant 3 | ⏳ decided | **obeyed** — drafts touch no nugget; submission is recorded, reconciled by plan-27 |
| §8a No wiki identity; editors recorded as `by` is today (Q1, Q4, R11) | `knowledge-acquisition.md` §8a, §10 | ✅ decided | **obeyed** — `editor` is the typed name; the lock, not identity, prevents lost updates |
| §8a Where it sits: `#/wiki/:key/edit` (Q17) | `knowledge-acquisition.md` §8a | ✅ built (tab) | **adds the edit route**; tabs 1–6 unchanged |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R14)

Source: [research-04](../research/research-04.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1, R7, R10, R11, R12 | ✅ decided | — |
| R2, R3, R4, R9, R13 | ✅ shipped | plan-25 |
| R5 editor | ✅ in scope | Phases 1–2 |
| R6 reconciliation | ⏭️ deferred | plan-27 (with R7's build) |
| R8 review/publication, R14 gate | ⏭️ deferred | plan-28 |

**Covered here: 1 of 14.** Deferred: 3.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT3 editing creates a candidate while the article, ACTIVE nuggets and graph are unchanged | R5, R6 | still RED — the "unchanged" half lands here, the candidate half is plan-27 |
| PT9 stale expected revision → 409; submit while another draft is under review → refused with a reason | R5 | **GREEN** |

## Scope

In: `ka/wiki_markdown.py` (new: `parse(text) -> blocks`, `to_markdown(blocks)`, `block_diff(old, new)`, refusal errors), `ka/wiki.py`
(`WikiEditor` methods on the service: `start_draft`, `save_draft`, `preview`, `diff`, `submit_draft`, `close_draft`, `create_page`),
`ka/api.py` (`POST /wiki/pages`, `GET /wiki/pages/{key}/drafts`, `POST /wiki/pages/{key}/drafts`, `GET/PUT /wiki/drafts/{id}`,
`POST /wiki/drafts/{id}/preview`, `GET /wiki/drafts/{id}/diff`, `POST /wiki/drafts/{id}/submit`, `POST /wiki/drafts/{id}/close`),
`ka/console/app.js` (`#/wiki/:key/edit`, inline-mark renderer, "Edit" and "New page" entries, drafts list on the article), `ka/events.py`
(`wiki.draft.saved`, `wiki.draft.submitted`), tests, flow, docs.

Out: turning a submission into candidates (plan-27); review screen, publication, layout apply (plan-28); real-time collaboration; images
beyond referencing the existing image store by number.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- Block ids are stable: a draft started from an article keeps the article's block ids (`b1…`); new blocks get `n<k>` ids; the editor's
  Markdown carries a hidden id comment per block (`<!-- b3 -->` on its own line) that the parser reads and strips — the ONE comment form
  allowed, matched exactly, never emitted to the console. Blocks without an id comment are new.
- Parser grammar: `#`/`##`/`###` headings; `- ` and `1. ` lists (one block per list); `> ` quotes; `|` tables (header row + `---` row +
  rows); blank-line-separated paragraphs. Inline: `**bold**`, `*em*`, `[text](https://…)`, `[[REF]]` and image references `![alt](image:12)`.
  Refused with a 400 naming the line: any `<…>` tag, `javascript:` or `data:` or non-`http(s)` link, any `<!--` other than the id form, and
  lines over 4,000 characters.
- Stored block text is the inline-Markdown plain text; the console renders inline marks after `esc`: bold, italics, links whose href
  matches `^https?://`, images as `<img>` to `/images/{n}` only, citations as in plan-25.
- Draft lifecycle: DRAFT → SUBMITTED → CLOSED (closed by the editor, or by plan-28 on resolution). `rev` increments on every save;
  `PUT` requires `expected_rev == rev` else 409 `{"detail": "...", "rev": current}`. Multiple DRAFT drafts per page are allowed; `submit` is
  refused (409) while another draft on the page is SUBMITTED, naming it.
- `submit_draft` records `diff = block_diff(base_blocks, draft_blocks)` on the draft (`note` field holds the editor's message) and emits
  `wiki.draft.submitted`; plan-27 subscribes to it. Nothing else happens.
- `create_page(slug, title, scope, ceiling, by)` writes a `WikiPage(kind="page", layout={"blocks": []})` and returns a first draft; slug
  `^[a-z0-9][a-z0-9-]{1,60}$`, unique.
- The base for a derived page's draft is `to_markdown(article(key).blocks)`; for an authored page it is the layout's blocks.

## Phases

### Phase 1 - Parser, diff, editor service, routes
- `ka/wiki_markdown.py`, `ka/wiki.py`, `ka/api.py`, `ka/events.py`.
- **Protected-code touched:** none

### Phase 2 - Console
- `#/wiki/:key/edit` (textarea with the Markdown, Save / Preview / Diff / Submit / Cancel, current rev, unsaved marker, other-drafts notice),
  article page "Edit" link and drafts list, index "New page" form, inline-mark renderer.
- **Protected-code touched:** none

### Phase 3 - Tests, flow, docs
- `ka/tests/test_plan26_wiki_editor.py`; `e2e/plan26_wiki_editor_flow.py`; architecture §8a state.
- **Protected-code touched:** none

## Code blocks (B1..B5)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/wiki_markdown.py` | parser, serializer, diff |
| B2 | `ka/wiki.py` | editor methods |
| B3 | `ka/api.py` | draft routes |
| B4 | `ka/console/app.js` | editor view, inline renderer, entries |
| B5 | `ka/events.py` | two names |

## Deliverables (D1..D8)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `parse(text) -> list[block]` with the grammar and refusals; `to_markdown(blocks)` round-trips | `ka/wiki_markdown.py` | 1 |
| D2 | `block_diff(old, new) -> [{block_id, op, before, after}]` with insert/update/delete/move by stable id | `ka/wiki_markdown.py` | 1 |
| D3 | `start_draft`, `save_draft` (expected_rev), `preview`, `diff`, `close_draft` | `ka/wiki.py` | 1 |
| D4 | `submit_draft` (refused while another is SUBMITTED; records diff; emits) | `ka/wiki.py` | 1 |
| D5 | `create_page` for authored pages; `page:` articles render layout blocks | `ka/wiki.py` | 1 |
| D6 | routes (nine) | `ka/api.py` | 1 |
| D7 | console editor route and entries; inline-mark renderer through `esc` | `ka/console/app.js` | 2 |
| D8 | live flow; architecture §8a state | `e2e/`, docs | 3 |

**Total deliverables: 8.**

## Positive Test Cases (P1..P7)
- **P1** — `parse` handles headings, paragraphs, ordered/unordered lists, quotes, tables, bold/italics/links/citations/image refs; `to_markdown(parse(t))` round-trips a representative text; ids survive via the id comment.
- **P2** — `start_draft` on a derived page copies the article's blocks with their ids and the current digest; on an authored page it copies the layout.
- **P3** — `save_draft` with the right `expected_rev` bumps `rev`, re-parses, keeps ids; `preview` returns blocks without writing.
- **P4** — `diff`: edited paragraph → `update` with before/after; new paragraph → `insert`; removed → `delete`; reordered → `move`; unaffected blocks absent from the diff.
- **P5** — `submit_draft` → SUBMITTED, diff recorded, `wiki.draft.submitted` emitted; `close_draft` → CLOSED.
- **P6** — `create_page` → `page:<slug>` article renders the authored blocks with `origin: authored`; listed under "Authored pages".
- **P7** — live flow: open an article, Edit, change a paragraph, Save (rev 1), Preview shows it, Diff shows one update, Submit → SUBMITTED banner; the article text is unchanged; no JS errors.

## Negative Test Cases (N1..N6)
- **N1** — PT9a: a save with a stale `expected_rev` → 409 with the current rev; the draft is unchanged.
- **N2** — PT9b: a second draft on the page saves fine; submitting it while the first is SUBMITTED → 409 naming the first draft.
- **N3** — `<script>`, `<img onerror>`, `javascript:` links, `data:` images and a foreign comment are each refused with 400 naming the line; nothing is stored.
- **N4** — PT3-half: after start/save/submit, every nugget file, the article's blocks and the graph proposals are byte-identical to before.
- **N5** — a draft on an unknown key → 404; a slug collision or malformed slug → 400/409; `by` is required.
- **N6** — the console never receives HTML in block text: the stored text of a saved draft contains no `<`.

## Plan totals

**Research points covered: 1 of 14 · Deliverables: 8 · Positive cases: 7 · Negative cases: 6 · Test cases total: 13 ·
Product tests served: 2 of 12 (PT9 turns green here; PT3 half).**

## Implementation Notes
- Written against `d243128` (plan-25). No protected code. Re-checked against the tree: plan-25's block shape (`id, kind, text, refs, level, items`) is the parser's target.
