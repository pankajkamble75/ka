# Plan 24 - Version numbers that cannot collide: derive from the versions on disk, write the counter first, repair the live duplicate (research-03 R15)

Created: 2026-10-09 17:20 UTC

## Problem Description

plan-23's rehearsal found two `SourceVersion`s numbered v5 on one live source with different bytes (`SRV-7e9c92b7` 22:40,
`SRV-a6551e3c` 22:48 on 2026-10-08). The binding key `(tenant, source, version)` assumes the number is unique, so the backfill reports a
conflict and leaves one version unbound. Mechanism: `_ingest` and `reextract` take the number from the in-memory `src.content_version`,
write the `SourceVersion` file first and the `Source` file last (`ka/ingestion.py:170-180, 216-220; :141-147`); a process stop between the
two writes (the service was restarted several times that evening with background missions ingesting) leaves the counter un-bumped on
disk, and the next ingest after the restart reuses the number. Desired outcome: a version number is derived from the versions that exist
for the source (never lower than any of them), the counter is written before the version so a crash leaves a gap and never a duplicate,
and the live duplicate can be repaired by a rehearsed, dry-run-by-default tool — run by the user, not by this run.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §11 binding unique on `(tenant, source, version)`; a committed physical target is immutable | `knowledge-acquisition.md` §11 (plan-18) | ✅ built | **constrained by it** — the fix makes the premise true; `put_binding` is unchanged |
| plan-04: reextract is a NEW version with the same checksum and a new extractor version | `knowledge-acquisition.md` §2 | ✅ built | **constrained by it** — plan-04's tests stay unmodified |
| Storage: one JSON per object, never hand-edited | `CLAUDE.md` | — | **obeyed** — the repair is a tool, dry-run by default, rehearsed on a copy |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** none.

## Research coverage (R1..R15)

Source: [research-03](../research/research-03.md) — 14 research points + **R15 opened mid-flight by plan-23**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R7, R9, R11–R14 | ✅ shipped | plans 18–23 |
| R8, R10 | ⏭️ parked | Q15, Q16 |
| R15 duplicate version numbers | ✅ in scope | Phases 1–2 |

**Covered here: 1 of 15.** Parked: 2.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT9 backfill binds every version | R14, R15 | stays GREEN; after the user runs the repair, the rehearsal reports 0 conflicts |

## Scope

In: `ka/ingestion.py` (`_next_version(src)`; counter written first in `_ingest` and `reextract`), `tools/backfill_physical.py`
(`--repair-conflicts`: renumber later duplicates to max+1, dry-run default), `e2e/plan23_backfill_rehearsal.py` (repair on the copy, then
0 conflicts), tests, architecture §11 note.

Out: running the repair on the live `ka_storage/` (the user's call; the exact command is in the report).

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- `_next_version(src) = max(src.content_version, max(v.version for versions of src)) + 1`; `src.content_version` is set to it.
- Write order in both paths: `sources.put(src)` (counter bumped, `current_version_id` still the old one) → version → binding → `sources.put(src)`
  (current pointer). A crash after the first write leaves a gap in the numbering, which nothing depends on.
- Repair: for each `(source, version)` held by more than one `SourceVersion`, keep the earliest `created_at`, renumber the others in
  `created_at` order to `max+1…`, set `src.content_version` to the new max; bindings for renumbered versions (if any) get `ka_source_version`
  updated; the version's `id` never changes (evidence references ids, not numbers).

## Phases

### Phase 1 - Numbering and write order
- `ka/ingestion.py`.
- **Protected-code touched:** none

### Phase 2 - Repair mode, rehearsal, tests, docs
- `tools/backfill_physical.py`, `e2e/plan23_backfill_rehearsal.py`, `ka/tests/test_plan24_version_numbering.py`, architecture §11.
- **Protected-code touched:** none

## Code blocks (B1..B2)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/ingestion.py` | `_next_version` and the counter-first write order |
| B2 | `tools/backfill_physical.py` | `repair_conflicts` and the CLI flag |

## Deliverables (D1..D4)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `IngestionService._next_version(src)` used by `_ingest` and `reextract` | `ka/ingestion.py` | 1 |
| D2 | counter-first write order in both paths | `ka/ingestion.py` | 1 |
| D3 | `repair_conflicts(ka, *, apply) -> report` and `--repair-conflicts` | `tools/backfill_physical.py` | 2 |
| D4 | rehearsal repairs the copy first and reports 0 conflicts; architecture §11 note | `e2e/plan23_backfill_rehearsal.py`, docs | 2 |

**Total deliverables: 4.**

## Positive Test Cases (P1..P4)
- **P1** — changed bytes for an existing source → v2; a third change → v3; `content_version` follows (regression).
- **P2** — simulated lost counter write (the source file on disk rolled back to the previous counter after an ingest) → the next ingest gets max+1, never a duplicate; the binding key is unique.
- **P3** — the same for `reextract` after a rolled-back counter.
- **P4** — repair over a storage with a duplicate pair: dry run changes nothing; `--apply` renumbers the later version to max+1, updates the source's counter and any binding's `ka_source_version`; the version ids are unchanged; a subsequent backfill reports 0 conflicts.

## Negative Test Cases (N1..N3)
- **N1** — repair never touches a source whose numbers are unique (byte-compare its files).
- **N2** — a crash simulated after the counter write and before the version write leaves a gap: the next ingest numbers past it and nothing raises.
- **N3** — plan-04 `test_P4` and plan-18's cases pass unmodified (byte-compare the test files against HEAD).

## Plan totals

**Research points covered: 1 of 15 · Deliverables: 4 · Positive cases: 4 · Negative cases: 3 · Test cases total: 7 ·
Product tests served: 1 of 9 (PT9 stays green).**

## Implementation Notes
- Written against `b4afe8b` (plan-23). No protected code. The live storage is NOT repaired by this run.
