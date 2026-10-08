# Research Tracker

**The ship ledger.** One row per research point and per plan, carried from `OPEN` through `UPLOADED`.
This file is a CLAIM, not evidence. The tree is the evidence; where they disagree, the tree wins.

Written by `create-research-report`, `create-implementation-plan`, `implement`, `verify` and `upload`.

## Active

| Research | Point | Plan | State | SHA | Notes |
|---|---|---|---|---|---|
| research-01 | R1 — Retire KA compiler; emit EOS ChangeOps via propose_instance_change / propose_promotion(base_version) (MAJOR) | plan-05 | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R3 — Second extraction pass for process knowledge with EOS closed type/slot lists (MAJOR) | plan-04 | PLANNED | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R7 — Idempotency: KA content key; propose base key on EOS propose_instance_change (MAJOR) | plan-05 | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R9 — DiscoveryAgent ahead of Internet agent; search provider decision; robots/allowlist budget (MAJOR) | plan-07 | OPEN | — | From research-01; Decision parked as Q5 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R10 — ka/connectors/ with Connector protocol; local folder first; providers decision (MAJOR) | plan-08 | OPEN | — | From research-01; Decision parked as Q6 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R11 — Decide: EOS routes found_new/grow_existing through KA gap request; grow GapIn (MAJOR) | plan-09 | OPEN | — | From research-01; Decision parked as Q7 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R12 — Processes tab (profile view) in KA console (MAJOR) | plan-06 | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R13 — Decide console shape: four tabs + Images + Processes vs note's five pages (MINOR) | — | OPEN | — | From research-01; Decision parked as Q8 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R14 — Decide re-pin of EOS console frontend (Q418) for process evidence panel (MINOR) | — | OPEN | — | From research-01; Decision parked as Q9 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R15 — Events as outbox: seq/version on events.jsonl, GET /events?after= (MINOR) | plan-09 | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R16 — Investigate store at 10k/100k; layout extras (span ids, row locators, extraction_version, OCR) (MINOR) | plan-04/09 | PLANNED | — | From research-01; see `docs/research/research-01.md` §Research points. |

## Closed

| Research | Point | Plan | State | SHA | Notes |
|---|---|---|---|---|---|
| research-01 | R2 — subject/predicate/object + versioned GrammarBinding on nuggets; canonical subject keys replace slug ids (MAJOR) | plan-03 | UPLOADED | 27d187d | From research-01; verify: 12/12 D, 12/12 P, 9/9 N recounted; 104 passed; live flow e2e/plan03_binding_flow.py 6/6; PT1/PT3 still red (plans 04/05); plan-03 built 12/12 deliverables, 21/21 cases (characterization dd06520); see `docs/research/research-01.md` §Research points. |
| research-01 | R8 — EOS read-only grammar + type table with sha256; KA caches by version+digest, fails closed (MAJOR) | plan-03 | UPLOADED | 27d187d | From research-01; verify: 12/12 D, 12/12 P, 9/9 N recounted; 104 passed; live flow e2e/plan03_binding_flow.py 6/6; PT1/PT3 still red (plans 04/05); plan-03 built 12/12 deliverables, 21/21 cases (characterization dd06520); see `docs/research/research-01.md` §Research points. |
| research-01 | R4 — Security step 1 (loopback containment, KA↔EOS service token) + step 2 decide (IdP, tenant, retention) (MAJOR) | plan-02 | UPLOADED | 7388f52 | From research-01; verify: 10/10 D, 9/9 P, 9/9 N recounted; 84 passed; live flow e2e/plan02_access_visibility_flow.py PASS; PT5, PT6 green; plan-02 built 10/10 deliverables, 18/18 cases (characterization 91325a4); see `docs/research/research-01.md` §Research points. |
| research-01 | R5 — Fix: upload body cap; SSRF guard on link() and Internet agent (MAJOR) | plan-02 | UPLOADED | 7388f52 | From research-01; verify: 10/10 D, 9/9 P, 9/9 N recounted; 84 passed; live flow e2e/plan02_access_visibility_flow.py PASS; PT5, PT6 green; plan-02 built 10/10 deliverables, 18/18 cases (characterization 91325a4); see `docs/research/research-01.md` §Research points. |
| research-01 | R6 — Fix: re-check visibility on promotion and CHANGE_SCOPE (MAJOR) | plan-02 | UPLOADED | 7388f52 | From research-01; verify: 10/10 D, 9/9 P, 9/9 N recounted; 84 passed; live flow e2e/plan02_access_visibility_flow.py PASS; PT5, PT6 green; plan-02 built 10/10 deliverables, 18/18 cases (characterization 91325a4); see `docs/research/research-01.md` §Research points. |
| — | Knowledge Acquisition spec (`knowledge-acquisition-requirements.md`) | plan-01 | UPLOADED | 7d9504c | Phases 1–6 of §44 built as the `ka` package; verified 67 tests; see `docs/implementation-plans/plan-01.md` and checkpoint 2026-10-08. |

## Backlog

| Topic | Note | State |
|---|---|---|
