# Research Tracker

**The ship ledger.** One row per research point and per plan, carried from `OPEN` through `UPLOADED`.
This file is a CLAIM, not evidence. The tree is the evidence; where they disagree, the tree wins.

Written by `create-research-report`, `create-implementation-plan`, `implement`, `verify` and `upload`.

## Active

| Research | Point | Plan | State | SHA | Notes |
|---|---|---|---|---|---|
| research-01 | R10 — ka/connectors/ with Connector protocol; local folder first; providers decision (MAJOR) | plan-08 | OPEN | — | From research-01; Decision parked as Q6 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R11 — Decide: EOS routes found_new/grow_existing through KA gap request; grow GapIn (MAJOR) | plan-09 | OPEN | — | From research-01; Decision parked as Q7 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R13 — Decide console shape: four tabs + Images + Processes vs note's five pages (MINOR) | — | OPEN | — | From research-01; Decision parked as Q8 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R14 — Decide re-pin of EOS console frontend (Q418) for process evidence panel (MINOR) | — | OPEN | — | From research-01; Decision parked as Q9 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R15 — Events as outbox: seq/version on events.jsonl, GET /events?after= (MINOR) | plan-09 | OPEN | — | From research-01; see `docs/research/research-01.md` §Research points. |
| research-01 | R16 — Investigate store at 10k/100k; layout extras (span ids, row locators, extraction_version, OCR) (MINOR) | plan-04/09 | OPEN (layout half UPLOADED in plan-04; benchmark half for plan-09) | — | From research-01; verify: layout extras recounted with plan-04; benchmark half still OPEN for plan-09; plan-04 built the layout extras; the store benchmark stays with plan-09; see `docs/research/research-01.md` §Research points. |

## Closed

| Research | Point | Plan | State | SHA | Notes |
|---|---|---|---|---|---|
| research-01 | R9 — DiscoveryAgent ahead of Internet agent; search provider decision; robots/allowlist budget (MAJOR) | plan-07 | UPLOADED | 02e2ce0 | From research-01; verify: 9/9 D, 9/9 P, 7/7 N; 165 passed; live flow 5/5; PT7 GREEN; plan-07 built 9/9 deliverables, 16/16 cases; provider itself parked as Q5; Decision parked as Q5 (docs/questions/knowledge-acquisition.md); see `docs/research/research-01.md` §Research points. |
| research-01 | R12 — Processes tab (profile view) in KA console (MAJOR) | plan-06 | UPLOADED | 31a4673 | From research-01; verify: 7/7 D, 8/8 P, 7/7 N; 150 + 7 EOS-path passed; live flow 6/6; lineage correction under protocol (00fd176); Q11 parked; plan-06 built 7/7 deliverables, 15/15 cases (incl. lineage correction N6 — characterization 00fd176 — and duplicate composition N7; Q11 parked); see `docs/research/research-01.md` §Research points. |
| research-01 | R1 — Retire KA compiler; emit EOS ChangeOps via propose_instance_change / propose_promotion(base_version) (MAJOR) | plan-05 | UPLOADED | 282b8f1 | From research-01; verify: 10/10 D, 12/12 P, 9/9 N; 136 + 7 EOS-path passed; live flow 4/4; PT2, PT3, PT4 GREEN; plan-05 built 10/10 deliverables, 21/21 cases (characterization 60ed811; EOS path 7/7 from the EOS interpreter); see `docs/research/research-01.md` §Research points. |
| research-01 | R7 — Idempotency: KA content key; propose base key on EOS propose_instance_change (MAJOR) | plan-05 | UPLOADED | 282b8f1 | From research-01; verify: 10/10 D, 12/12 P, 9/9 N; 136 + 7 EOS-path passed; live flow 4/4; PT2, PT3, PT4 GREEN; plan-05 built 10/10 deliverables, 21/21 cases (characterization 60ed811; EOS path 7/7 from the EOS interpreter); see `docs/research/research-01.md` §Research points. |
| research-01 | R3 — Second extraction pass for process knowledge with EOS closed type/slot lists (MAJOR) | plan-04 | UPLOADED | 0ddf147 | From research-01; verify: 11/11 D, 11/11 P, 8/8 N; 122 passed; live flow 4/4; PT1 GREEN; plan-04 built 11/11 deliverables, 19/19 cases (characterization f94b0f3); see `docs/research/research-01.md` §Research points. |
| research-01 | R2 — subject/predicate/object + versioned GrammarBinding on nuggets; canonical subject keys replace slug ids (MAJOR) | plan-03 | UPLOADED | 27d187d | From research-01; verify: 12/12 D, 12/12 P, 9/9 N recounted; 104 passed; live flow e2e/plan03_binding_flow.py 6/6; PT1/PT3 still red (plans 04/05); plan-03 built 12/12 deliverables, 21/21 cases (characterization dd06520); see `docs/research/research-01.md` §Research points. |
| research-01 | R8 — EOS read-only grammar + type table with sha256; KA caches by version+digest, fails closed (MAJOR) | plan-03 | UPLOADED | 27d187d | From research-01; verify: 12/12 D, 12/12 P, 9/9 N recounted; 104 passed; live flow e2e/plan03_binding_flow.py 6/6; PT1/PT3 still red (plans 04/05); plan-03 built 12/12 deliverables, 21/21 cases (characterization dd06520); see `docs/research/research-01.md` §Research points. |
| research-01 | R4 — Security step 1 (loopback containment, KA↔EOS service token) + step 2 decide (IdP, tenant, retention) (MAJOR) | plan-02 | UPLOADED | 7388f52 | From research-01; verify: 10/10 D, 9/9 P, 9/9 N recounted; 84 passed; live flow e2e/plan02_access_visibility_flow.py PASS; PT5, PT6 green; plan-02 built 10/10 deliverables, 18/18 cases (characterization 91325a4); see `docs/research/research-01.md` §Research points. |
| research-01 | R5 — Fix: upload body cap; SSRF guard on link() and Internet agent (MAJOR) | plan-02 | UPLOADED | 7388f52 | From research-01; verify: 10/10 D, 9/9 P, 9/9 N recounted; 84 passed; live flow e2e/plan02_access_visibility_flow.py PASS; PT5, PT6 green; plan-02 built 10/10 deliverables, 18/18 cases (characterization 91325a4); see `docs/research/research-01.md` §Research points. |
| research-01 | R6 — Fix: re-check visibility on promotion and CHANGE_SCOPE (MAJOR) | plan-02 | UPLOADED | 7388f52 | From research-01; verify: 10/10 D, 9/9 P, 9/9 N recounted; 84 passed; live flow e2e/plan02_access_visibility_flow.py PASS; PT5, PT6 green; plan-02 built 10/10 deliverables, 18/18 cases (characterization 91325a4); see `docs/research/research-01.md` §Research points. |
| — | Knowledge Acquisition spec (`knowledge-acquisition-requirements.md`) | plan-01 | UPLOADED | 7d9504c | Phases 1–6 of §44 built as the `ka` package; verified 67 tests; see `docs/implementation-plans/plan-01.md` and checkpoint 2026-10-08. |

## Backlog

| Topic | Note | State |
|---|---|---|
