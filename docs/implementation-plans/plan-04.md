# Plan 04 - A second extraction pass that reads processes, on evidence that can be pointed at

Created: 2026-10-08 15:30 UTC

## Problem Description

Extraction today splits a document into sentences and keeps the ones with a modal verb (`ka/extraction.py:313-330`,
`_MODAL`); with a model it asks for "discrete, independently governable statements" (`:241-256`). Neither pass produces
what plan-03 can now store: a subject in EOS terms, a predicate from the closed list, an object. A process is not a
sentence — it is a heading with numbered steps, an actor named in a lead-in, a type a document rarely states. research-01
R3 asks for a second pass over the same sections that emits assertions using EOS's closed lists (node kinds, predicates,
the ten types, the fifteen slots), with a numbered-list heuristic when there is no model, and that never fills a field the
text does not support.

That pass can only cite correctly if evidence is addressable. Evidence today has a free-text locator (`ka/model.py:94`)
and extractors emit page/heading/table-level locators (`ka/extraction.py:94,118,140`); table rows are joined into one
string (`:140-142`); a scanned PDF is `UNAVAILABLE` (`:120`); and a `SourceVersion` does not record which extractor produced
its text, so re-extraction after an upgrade would overwrite rather than version. R16's layout extras close those: stable
span ids with character offsets, row-level table locators, `extraction_version` on the version, re-extraction as a new
version, and OCR behind an optional dependency.

Desired outcome: uploading a synthetic underwriting SOP yields, besides the rule statements, a `process` subject
"Merchant underwriting" with a `description`, five `decomposes_into` assertions (one per numbered step, each a child
process subject), a `performed_by` where the text names the team, and **no** `typed_as` — because the SOP does not state
a type — every one carrying an evidence span id that resolves to exact characters of the stored text.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Raw content is evidence, not knowledge; immutable; a changed document is a new version | `knowledge-acquisition.md` §2 | ✅ built | **extends it** — re-extraction after an extractor upgrade is a new `SourceVersion` with the same bytes and a new `extraction_version`; never an overwrite |
| Process assertions: subject/predicate/object, closed `PREDICATES`, binding at birth | `knowledge-acquisition.md` §5a (plan-03) | ✅ built | **constrained by it** — pass two emits only those fields; binding happens in `ingest_candidate` as before |
| One governance pipeline; `extract_from_source` is the content channel's door | `knowledge-acquisition.md` §4 | ✅ built | **extends it** (Phase 3, protected) — pass two runs inside `extract_from_source` so both passes share source, evidence and scope |
| EOS: closed lists, "one repair, then drop and disclose" for model output | EOS `grammar-first-navigation.md` §2–§3 | precedent | **copied** — a model item with a predicate or kind outside the closed lists is dropped and counted in the extraction report, never coerced |
| EOS: untyped process is a warning; required slot missing is `incomplete` | EOS `process_types.py:349-392` | precedent | **constrained by it** — the heuristic never emits `typed_as`; the model emits it only when the text states a type (prompt rule + N-case) |
| Security: upload cap, SSRF guard | `knowledge-acquisition.md` §10 (plan-02) | ✅ built | **constrained by it** — OCR runs on bytes already accepted by the cap; no network |
| Q8 console shape | `questions/knowledge-acquisition.md` Q8 | ❓ open | not needed — this plan adds fields to the source page only |

**Open questions in the sections this plan touches:** none blocking. Q8 not needed.

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 ChangeOps into EOS proposals | ⏭️ deferred | plan-05 |
| R2 assertion model, bindings, canonical keys | ✅ shipped | plan-03 (`27d187d`); id derivation in plan-05 |
| R3 second extraction pass for process knowledge | ✅ in scope | Phases 2–3 |
| R4 / R5 / R6 security, caps, visibility | ✅ shipped | plan-02 (`7388f52`) |
| R7 idempotency | ⏭️ deferred | plan-05 |
| R8 grammar registry | ✅ shipped | plan-03 |
| R9 discovery agent | ⏭️ deferred | plan-07 |
| R10 connectors | ⏭️ deferred | plan-08 |
| R11 gap routing | ⏭️ deferred | plan-09 |
| R12 process profile view | ⏭️ deferred | plan-06 — reads what this plan extracts |
| R13 console shape | ⏭️ deferred | Q8 parked |
| R14 EOS frontend re-pin | ⏭️ deferred | Q9 parked |
| R15 events outbox | ⏭️ deferred | plan-09 |
| R16 layout extras (span ids, row locators, extraction_version, OCR) ✅ in scope — Phase 1; **store benchmark** ⏭️ deferred to plan-09 | split | the extras are a precondition for R3's evidence; the benchmark shares nothing with this plan |

**Covered here: 2 of 16** (R3; R16's layout half). Deferred: 10. Shipped earlier: 4. Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT1 synthetic underwriting SOP → process subject with description and five nested activities, each bound to a type or `unresolved`, every field with a page/section span, nothing invented | R2, R3 | **GREEN** — this plan is what makes it true (binding of activities: `unresolved`/`not_applicable` is the honest result when the SOP states no type; the test accepts that) |

## Scope

In: `ka/extraction.py` (spans, row locators, OCR hook, `EXTRACTION_VERSION`), `ka/process_extraction.py` (new),
`ka/model.py` (`Evidence.span_id/start/end`, `SourceVersion.extraction_version/extraction_report`), `ka/ingestion.py`
(`reextract`), `ka/governance.py` (`extract_from_source` pass two, protected), `ka/api.py` (`POST /sources/{id}/reextract`,
report in responses), `ka/console/app.js` (source page shows the extraction report and spans), fixture SOP, tests, docs.

Out: the process profile view (plan-06); publication (plan-05); multimodal diagram interpretation (not researched);
prompt-injection defences (named in the note, not in research-01's ledger — raised as a question, see Phase 2).

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/governance/` (Inv. 3; verified 2026-10-08 plan-03), touched by Phase 3.
HOW: `GovernanceService.extract_from_source` (`ka/governance.py:78-108`) gains `process_pass: bool = True`; after the statement
pass it calls `ProcessExtractor.extract(title, extraction)` and turns each `AssertionCandidate` into an `Evidence` (with span
fields) and a `CandidateInput` carrying subject/predicate/object with `binding_method="evidenced"`, through the existing
`ingest_candidate`. `__init__` takes a `process_extractor`. `ingest_candidate` and `decide` are not touched.
WHY: the pass must share the source's scope resolution (`_scope_from_hint`), its evidence/source refs and the one door
into governance; a separate "process channel" would be a second pipeline, which architecture §4 forbids.
Regression risk: every upload/paste/note extraction now runs two passes; the statement pass is unchanged (pinned by P-char).
Characterization gap: no test pins that `extract_from_source` creates exactly one candidate per statement and none with a
subject.
Re-verify: governance suites unmodified (phase2, phase6, api, plan02, plan03 files) + live: upload the fixture SOP in the
console and see both statement and process candidates listed with subjects. Bump the Verified date.

Not protection-driven: the process extractor is its own module (`ka/process_extraction.py`) because it has its own prompt,
closed-list validation and heuristic, and plan-07's research synthesis will call it too.

## Assumptions

- Plan-03 landed (`27d187d`): `CandidateInput` carries assertion fields, `Binder` binds at birth, the fixture grammar exists.
- `EXTRACTION_VERSION = "ka-extract/2"` names this plan's extractor; `"ka-extract/1"` is back-filled onto versions created
  before (absent field → 1 when read).
- Span ids: `s<N>` for the N-th section in reading order, `s<N>.r<M>` for table rows, `s<N>.p<M>` for PDF pages; `start`/`end`
  are character offsets into `SourceVersion.text`, which is built as the join of section texts with `"\n\n"` so offsets are
  reproducible from the stored text alone.
- OCR: `KA_OCR` (bool, default off). When on and a PDF has no text layer, `ocr_pdf(data)` tries `pdf2image` + `pytesseract`
  (new optional dependency group `ocr`); when the libraries are missing it records `UNAVAILABLE` with note
  `ocr not installed (pip install 'knowledge-acquisition[ocr]')`. Image sources follow the same hook. Tests patch the hook;
  no OCR runs in CI.
- The heuristic second pass emits: `description` (first sentence under a heading that reads as a process — contains one
  of process|procedure|workflow|handling|onboarding|underwriting|review|approval|settlement|reconciliation|dispute, or is
  followed by a numbered list), `decomposes_into` (one per numbered or lettered item, child subject = the item's first
  clause, ≤ 60 chars), `performed_by` (the phrase "by the <X> team|department|desk" or "<X> is responsible for" in the same
  section). It never emits `typed_as`, `consumes`, `produces`, `transitions_to`.
- The model pass prompt carries the closed lists from the loaded grammar (node kinds, `PREDICATES`, type names, slots) and
  the rule "only when the text states it; otherwise omit". Items with an unknown predicate or subject kind are dropped and
  listed in `extraction_report.dropped` with the item and reason; an unknown type is NOT dropped — it goes through as
  `typed_as` and binds `unresolved`, which is the honest signal.
- Re-extraction (`POST /sources/{id}/reextract`) creates a new `SourceVersion` from the stored blob with the current
  `EXTRACTION_VERSION`; same-bytes dedupe (`_ingest`) is bypassed deliberately for this path and only this path.

## Phases

### Phase 1 - Layout extras (R16)

- `ka/extraction.py`: `Span(span_id, locator, start, end)`; `TextExtraction.spans: list[Span]`; `text` built by joining
  section texts with `"\n\n"` and spans computed from that join; Word tables → one section per row (`table N row M`,
  cells joined with ` | `); xlsx → one section per row (`sheet X row M`); PDF pages keep `p.N` and get `s<N>.p<N>` ids;
  `EXTRACTION_VERSION`; `ocr_pdf(data)` / `ocr_image(data)` hooks behind `KA_OCR` and lazy imports.
- `ka/model.py`: `Evidence.span_id`, `start`, `end`; `SourceVersion.extraction_version` (default `"ka-extract/1"`),
  `extraction_report: dict`.
- `ka/ingestion.py`: `reextract(source_id, *, owner) -> Ingested` (new version from the blob, current extractor).
- `ka/config.py`: `KA_OCR` (bool, False). `pyproject.toml`: optional group `ocr = ["pdf2image", "pytesseract"]`.
- **Protected-code touched:** none

### Phase 2 - Process extraction pass (R3)

- `ka/process_extraction.py`: `AssertionCandidate(subject_kind, subject_name, predicate, object_kind, object_name, object_value,
  span_id, locator, excerpt, confidence, statement)`; `ProcessExtractor(provider, grammar)` with `extract(title, extraction) ->
  ProcessExtraction(assertions, dropped, method)`; `_prompt(...)` carrying the closed lists; `_heuristic(sections)` per the
  assumptions; `render_statement(a)` producing the canonical sentence stored as the nugget `statement`
  ("Merchant underwriting decomposes into: Collect application").
- Fixture `ka/tests/fixtures/underwriting_sop.md`: heading "Merchant underwriting", a one-sentence purpose, "performed by the
  Underwriting team", five numbered steps, a rule sentence, and a section that is NOT a process (a glossary) — the negative.
- Question raised for the author (§4b): prompt-injection defences for retrieved content are in the note (REQ-008) but not in
  research-01's ledger; this plan records **Q10** in `docs/questions/knowledge-acquisition.md` and the registry, and does not
  build them.
- **Protected-code touched:** none

### Phase 3 - Wire the pass into the content channel (protected)

1. **Declare.** `GovernanceService.extract_from_source` + `__init__(process_extractor=)`; see summary for why.
2. **Characterize first** (own commit): P8 — today `extract_from_source` on the fixture SOP yields only statement candidates,
   none with a subject, one evidence per candidate without a span id.
3. **Add coverage before the change**: N5 — `extract_from_source` on a source with empty text yields `[]` (before and after);
   P9 — the statement pass's candidates for the fixture SOP are the same set before and after the change (statement text
   equality), i.e. pass two adds, never alters.
4. **Change**: run pass two after pass one; `Evidence` with span fields; `CandidateInput` with assertion fields and
   `binding_method="evidenced"`; write `extraction_report` onto the `SourceVersion` (`statements`, `assertions`, `dropped`,
   `method`, `extraction_version`).
5. **Existing covering tests pass UNMODIFIED**: N7.
6. **Re-verify live**: upload the fixture SOP through the console; the candidates list shows subjects; the source page
   shows the report. `e2e/plan04_process_extraction_flow.py`.
7. **Bump `Verified:`** for `ka/governance/`.
- **Protected-code touched:** ⚠️ `ka/governance/` — `extract_from_source`, `__init__`.

### Phase 4 - API, console, docs

- `ka/api.py`: `POST /sources/{id}/reextract`; `GET /sources/{id}` includes `extraction_report` and spans per version;
  `_ingested` returns `extraction_report`.
- `ka/console/app.js`: source page shows the report (statements / assertions / dropped with reasons / extractor version) and
  a "Re-extract with current extractor" button; nugget evidence lines show `span_id` and offsets.
- `docs/architecture/knowledge-acquisition.md` §2 (`SourceVersion`, `Evidence` rows) and §5a (the second pass); README.
- **Protected-code touched:** none

## Code blocks (B1..B8)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/extraction.py` | spans, row-level table sections, OCR hooks, `EXTRACTION_VERSION` |
| B2 | `ka/process_extraction.py` | the second pass: prompt with closed lists, validation, heuristic, statement rendering |
| B3 | `ka/model.py` | `Evidence` span fields; `SourceVersion.extraction_version` and `extraction_report` |
| B4 | `ka/ingestion.py` | `reextract` |
| B5 | `ka/config.py` | `KA_OCR` |
| B6 | `ka/governance.py` | pass two inside `extract_from_source`; `process_extractor` wiring |
| B7 | `ka/api.py` | reextract route; report in responses |
| B8 | `ka/console/app.js` | source page report + button; evidence span display |

(`ka/service.py` constructs the `ProcessExtractor` — one line, declared here as part of B6's wiring; `pyproject.toml` gains
the `ocr` extra.)

## Deliverables (D1..D11)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `Span`, `TextExtraction.spans`, reproducible `text` join, `EXTRACTION_VERSION` | `ka/extraction.py` | 1 |
| D2 | row-level sections for Word tables and spreadsheets | `ka/extraction.py` | 1 |
| D3 | `ocr_pdf`, `ocr_image` hooks behind `KA_OCR`; `ocr` extra | `ka/extraction.py`, `ka/config.py`, `pyproject.toml` | 1 |
| D4 | `Evidence.span_id/start/end`; `SourceVersion.extraction_version/extraction_report` | `ka/model.py` | 1 |
| D5 | `IngestionService.reextract` | `ka/ingestion.py` | 1 |
| D6 | `AssertionCandidate`, `ProcessExtractor.extract`, `render_statement` | `ka/process_extraction.py` | 2 |
| D7 | fixture SOP | `ka/tests/fixtures/underwriting_sop.md` | 2 |
| D8 | Q10 recorded (questions doc + registry) | `docs/questions/knowledge-acquisition.md`, `docs/trackers/QUESTIONS-TRACKER.md` | 2 |
| D9 | `extract_from_source(process_pass=)` running both passes; report on the version | `ka/governance.py`, `ka/service.py` | 3 |
| D10 | `POST /sources/{id}/reextract`; report + spans in source and ingestion responses | `ka/api.py` | 4 |
| D11 | source page report, re-extract button, evidence span display | `ka/console/app.js` | 4 |

**Total deliverables: 11.**

## Positive Test Cases (P1..P11)

- **P1** — Markdown fixture: spans `s1..sN` cover the whole stored text in order, `text[start:end]` equals each section's text, and `extraction_version == "ka-extract/2"`.
- **P2** — a Word document with a 2×3 table yields three row sections `table 1 row 1..3` with cells joined by ` | `; a workbook yields `sheet Sheet row N` sections.
- **P3** — with `KA_OCR=1` and the hook patched to return text, a text-less PDF is `EXTRACTED` with page spans and note `ocr`.
- **P4** — `reextract(source_id)` creates version 2 with the same checksum, the current `extraction_version`, and leaves version 1 untouched.
- **P5** — heuristic pass on the fixture SOP: one `description`, five `decomposes_into` with child subjects "Collect application" … "Communicate decision", one `performed_by` "Underwriting team"; every assertion has a `span_id` whose span text contains its excerpt.
- **P6** — model pass (stub returning a JSON array with one valid item, one item with predicate `frobnicates`, one with subject kind `widget`): the valid item is kept, the two invalid are in `dropped` with reasons, and a `typed_as` item with an unknown type is kept (binds `unresolved`).
- **P7** — `render_statement` yields "Merchant underwriting decomposes into: Collect application" and "Merchant underwriting is performed by: Underwriting team".
- **P8** — characterization: today `extract_from_source` on the fixture yields statement-only candidates, no subject, no span ids (pinned before Phase 3).
- **P9** — the statement pass's set of statements for the fixture is identical before and after Phase 3 (pass two adds, never alters).
- **P10** — after Phase 3, uploading the fixture through the API returns candidates including the process subject and five children, each with evidence carrying `span_id`; the source page JSON carries `extraction_report.assertions == 7` and `dropped == []`; `GET /subjects/merchant_underwriting` lists them.
- **P11** — console live flow: upload the fixture, the candidates table shows subject keys; the source page shows the report (`e2e/plan04_process_extraction_flow.py`).

## Negative Test Cases (N1..N8)

- **N1** — the glossary section of the fixture (a heading followed by definitions, no list, no process word) yields no process assertions.
- **N2** — the heuristic never emits `typed_as`: a fixture that says "This is a decision process" still yields no `typed_as` from the heuristic (that is the model's job, and only when stated).
- **N3** — `KA_OCR=0`: a text-less PDF stays `UNAVAILABLE` with note "no text layer"; `KA_OCR=1` with the libraries absent → `UNAVAILABLE` with note naming the `ocr` extra; never an exception.
- **N4** — a span id that does not exist in the version is refused by `Evidence` construction through the pass (the extractor validates `span_id ∈ spans`), and an excerpt outside its span is corrected to the span text with a `dropped`-style note in the report.
- **N5** — `extract_from_source` on an empty-text source returns `[]` and writes an empty report (before and after Phase 3).
- **N6** — `reextract` on a source whose blob is missing → `GovernanceError`/`ValueError` with a clear message; no version created.
- **N7** — regression gate: every covering test for `ka/governance/` passes UNMODIFIED.
- **N8** — `POST /sources/{id}/reextract` on an unknown id → 404; on a blocked link source (no bytes) → 409.

## Plan totals

**Research points covered: 2 of 16 · Deliverables: 11 · Positive cases: 11 · Negative cases: 8 · Test cases total: 19 ·
Product tests served: 1 of 8 (1 turns green here).**

## Implementation Notes

- **Re-check this plan against the tree before implementing.** It was written after plan-03 landed (`27d187d`); confirm
  `extract_from_source` still creates one `Evidence` per statement with a free-text locator and no span fields.
- Phase 3's characterization (P8, N5-before, P9-before) lands in its own commit before any governance change.
- The stub provider in tests answers the process prompt with a fixed JSON array keyed on the marker "PROCESS PASS" in the
  prompt, so the model path is exercised without a key.
- PT1's wording "each activity bound to one of EOS's ten process types or marked unresolved": with the fixture stating no
  type, the honest outcome is that the five children carry `decomposes_into` bindings (edge `contains`, slot `action`,
  `bound`) and no `typed_as`; PT1 is written to accept `unresolved`/absent typing, and the plan-04 verify runs PT1 as
  `test_plan04_process_extraction.py::test_PT1_*`.
