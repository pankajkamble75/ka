# Plan 23 - Asset families, the finished architecture section, and the backfill rehearsal with the local backend as rollback (research-03 R12, R13, R14)

Created: 2026-10-09 16:10 UTC

## Problem Description

Plans 18–22 built the Data Platform integration piece by piece. Three things remain for research-03 to be delivered: the decision on
**asset families** (R12: KA's `source_document` / `extracted_text` / `nugget_version` beside EOS's instance data assets, shared lineage
ids, KA never stores rows, EOS never reads documents as data) recorded as a rule; the **architecture section** (R13) completed, its state
moved to built, the duplicate §11 heading fixed and the contract indexed; and the **backfill rehearsal** (R14): one script that binds every
legacy `SourceVersion` to DP with SHA-256 verification, `failed` bindings for byte-less versions, derived publication of ACTIVE nuggets,
idempotent on re-run, dry-run by default — rehearsed over a copy of the live storage against the fake, with `KA_STORAGE_BACKEND=local`
staying in the code as the rollback.

Desired outcome (PT9): the rehearsal binds every legacy version (available or `failed` with a reason) with SHA-256 verified, and the suite
stays green with the backend set to local.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| §11 port, binding, outbox, events, derived artefacts (plans 18–22) | `knowledge-acquisition.md` §11 | ✅ built | **completes it** — asset families, state → built, index |
| EOS puts instance physical data on the Data Platform; KA's bytes are documents | `data-layer.md` §3 (EOS); research-03 §12 | ⏳ decided | **records it** as a rule in §11 (R12) |
| Invariant 2 lineage vocabulary is the join between a graph node and a DP asset's provenance | `knowledge-acquisition.md` §5 | ✅ built | **constrained by it** — the derived payload already carries the ids (plan-22) |
| research-03 §10: migration is one script, rehearsed; local backend is the rollback, removed only from configuration | `research-03.md` §10 | ⏳ decided | **builds it** |
| Protected code | `docs/protected.md` | — | **not touched** |

**Open questions in the sections this plan touches:** Q15, Q16 — parked, not blocking.

## Research coverage (R1..R14)

Source: [research-03](../research/research-03.md) — **14 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 | ✅ decided | — |
| R2–R7, R9, R11 | ✅ shipped | plans 18–22 |
| R8, R10 | ⏭️ parked | Q15, Q16 — the author's |
| R12 asset families | ✅ in scope | Phase 1 (recorded as a rule; the store already sends `source_document`, derived sends `nugget_version`) |
| R13 architecture §11 | ✅ in scope | Phase 1 |
| R14 backfill rehearsal | ✅ in scope | Phases 2–3 |

**Covered here: 3 of 14.** Parked: 2 (Q15, Q16).

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT9 backfill binds every legacy version with SHA verified; suite green on local | R14 | **GREEN** |

## Scope

In: `docs/architecture/knowledge-acquisition.md` (§11 completed, asset families, state; "§11 What is deliberately not here" → §12),
`docs/architecture/architecture-index-lookup.md` (contract row; questions row Q1–Q16), `tools/backfill_physical.py` (new),
`ka/physical.py` (`ASSET_FAMILIES` constant used by the store and the publisher), `e2e/plan23_backfill_rehearsal.py`, tests, `.env.example`.

Out: running the backfill against production (there is no DP yet; the rehearsal runs against the fake over a COPY of the live storage);
removing the local backend.

## Protected-code impact (summary)

✅ No protected code touched by any phase.

## Assumptions

- `tools/backfill_physical.py --storage <root> [--apply] [--publish-active]`: dry-run by default prints what WOULD happen; `--apply` writes
  bindings; for each `SourceVersion` without an `available` binding for the configured backend: bytes present → `physical.put` with the
  ingestion key shape → SHA check (mismatch → `failed` "sha mismatch", never available) → binding `available`; no bytes → `failed` with the
  version's extraction note or "no bytes (blocked or empty)". `--publish-active` calls `derived.publish` for every ACTIVE nugget version
  and drains the outbox. Exit code 0; a JSON report on stdout (`versions, bound, available, failed, skipped, published, sha_mismatch`).
- Idempotent: a re-run finds the bindings and skips them; the fake receives no second asset version (replay by key).
- Rehearsal copies `ka_storage/` to a temp dir (never writes the live storage), runs the fake over HTTP, runs the tool with `--apply
  --publish-active`, then starts a KA server on the copy with the DP backend and checks the Dashboard.
- Live numbers at rehearsal time are reported as measured (the research counted 69/4 on 2026-10-09 morning; the storage has grown since).

## Phases

### Phase 1 - Architecture and asset families
- §11 completion; §12 renumber; index rows; `ASSET_FAMILIES` in `ka/physical.py` used by the store (`source_document`) and the publisher (`nugget_version`).
- **Protected-code touched:** none

### Phase 2 - The backfill tool
- `tools/backfill_physical.py`.
- **Protected-code touched:** none

### Phase 3 - Tests and the rehearsal
- `ka/tests/test_plan23_backfill.py`; `e2e/plan23_backfill_rehearsal.py`; `.env.example` note.
- **Protected-code touched:** none

## Code blocks (B1..B3)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/physical.py` | `ASSET_FAMILIES` |
| B2 | `ka/data_platform/store.py`, `ka/derived.py` | use the constant (one block each) |
| B3 | `tools/backfill_physical.py` | the tool |

## Deliverables (D1..D6)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | §11 complete: asset families rule (R12), state `✅ built`, contract and tool named; §12 renumbered | `docs/architecture/knowledge-acquisition.md` | 1 |
| D2 | index rows for the contract and the questions range | `docs/architecture/architecture-index-lookup.md` | 1 |
| D3 | `ASSET_FAMILIES` constant used by the store and the publisher | `ka/physical.py`, `ka/data_platform/store.py`, `ka/derived.py` | 1 |
| D4 | `backfill(ka, *, apply, publish_active) -> report` and the CLI | `tools/backfill_physical.py` | 2 |
| D5 | rehearsal flow over a copy of the live storage against the fake over HTTP | `e2e/plan23_backfill_rehearsal.py` | 3 |
| D6 | `.env.example` rollback note | `.env.example` | 3 |

**Total deliverables: 6.**

## Positive Test Cases (P1..P7)
- **P1** — dry run over a storage with 3 versions (one byte-less) writes nothing and reports `would_bind=3`.
- **P2** — `--apply`: 2 `available` with DP ids and SHA equal to the version checksum; 1 `failed` with the note; `version_available` true for the two.
- **P3** — `--publish-active`: every ACTIVE nugget version has an `available` `nugget_version` artefact in the fake after the run.
- **P4** — a second run binds nothing new and the fake holds the same number of asset versions (idempotent by key).
- **P5** — the store sends `source_document` and the publisher `nugget_version`, both from `ASSET_FAMILIES`; the fake records those types.
- **P7** — the derived payload carries the grammar binding (status, digest, grammar version, process type, edge, method) when one exists — found by the rehearsal, which met the live storage's bindings. *(added during implementation)*
- **P6** — rehearsal (live copy): every version bound, counts reported, Dashboard on the copy shows the DP backend with the binding count; the live `ka_storage/` is byte-identical before and after.

## Negative Test Cases (N1..N5)
- **N1** — a SHA mismatch from the store yields a `failed` binding with "sha mismatch" and the version is not available.
- **N2** — a version with an existing `available` binding is skipped, never re-uploaded.
- **N3** — the tool on the local backend refuses `--apply` (nothing to migrate to) with a clear message and exit 2.
- **N5** — a duplicate `(source, version)` with different bytes (found in the live storage during the rehearsal) is reported as a conflict by id, left unbound, and never raises. *(added during implementation)*
- **N4** — PT9 rollback: with `KA_STORAGE_BACKEND=local` the same storage serves its legacy versions through `stored_path` (reextract works) and no worker runs.

## Plan totals

**Research points covered: 3 of 14 · Deliverables: 6 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 1 of 9 (PT9 turns green here).**

## Implementation Notes
- Written against `1458626` (plan-22). No protected code. The live service stays on the local backend; the rehearsal never touches `ka_storage/`.
