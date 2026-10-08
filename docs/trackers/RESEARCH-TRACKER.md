# Research Tracker

**The ship ledger.** One row per research point and per plan, carried from `OPEN` through `UPLOADED`.
This file is a CLAIM, not evidence. The tree is the evidence; where they disagree, the tree wins.

Written by `create-research-report`, `create-implementation-plan`, `implement`, `verify` and `upload`.

## Active

| Research | Point | Plan | State | SHA | Notes |
|---|---|---|---|---|---|
| research-01 | R1 — Retire KA compiler; emit EOS ChangeOps via propose_instance_change / propose_promotion(base_version) (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R2 — subject/predicate/object + versioned GrammarBinding on nuggets; canonical subject keys replace slug ids (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R3 — Second extraction pass for process knowledge with EOS closed type/slot lists (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R4 — Security step 1 (loopback containment, KA↔EOS service token) + step 2 decide (IdP, tenant, retention) (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R5 — Fix: upload body cap; SSRF guard on link() and Internet agent (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R6 — Fix: re-check visibility on promotion and CHANGE_SCOPE (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R7 — Idempotency: KA content key; propose base key on EOS propose_instance_change (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R8 — EOS read-only grammar + type table with sha256; KA caches by version+digest, fails closed (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R9 — DiscoveryAgent ahead of Internet agent; search provider decision; robots/allowlist budget (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R10 — ka/connectors/ with Connector protocol; local folder first; providers decision (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R11 — Decide: EOS routes found_new/grow_existing through KA gap request; grow GapIn (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R12 — Processes tab (profile view) in KA console (MAJOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R13 — Decide console shape: four tabs + Images + Processes vs note's five pages (MINOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R14 — Decide re-pin of EOS console frontend (Q418) for process evidence panel (MINOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R15 — Events as outbox: seq/version on events.jsonl, GET /events?after= (MINOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R16 — Investigate store at 10k/100k; layout extras (span ids, row locators, extraction_version, OCR) (MINOR) | — | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |

## Closed

| Research | Point | Plan | State | SHA | Notes |
|---|---|---|---|---|---|
| — | Knowledge Acquisition spec (`knowledge-acquisition-requirements.md`) | plan-01 | UPLOADED | 7d9504c | Phases 1–6 of §44 built as the `ka` package; verified 67 tests; see `docs/implementation-plans/plan-01.md` and checkpoint 2026-10-08. |

## Backlog

| Topic | Note | State |
|---|---|---|
