# Questions Tracker

Decisions parked for the author. One row per question, `Q1`, `Q2`, … Never renumber.

| Q | Stage | Question | Options | Decision | Date |
|---|---|---|---|---|---|
| Q1 | implementation | §42: who may call the KA API? Visibility/permissions are modelled; no caller identity is checked. | add auth at the API edge / reuse enterprise-os auth / leave open for intranet | — | 2026-10-08 |
| Q2 | implementation | A domain write via EnterpriseOSGraphAdapter creates a new substructure version. Who repins instances, and when? | KA repins automatically after apply / operator repins via store `repin` / proposal lists repin as a manual step | — | 2026-10-08 |
| Q3 | implementation | Should the standalone server auto-apply low-impact Graph Change Proposals by default (`auto_approve_low_impact`)? | on / off (current) | — | 2026-10-08 |
| Q4 | research | R4 step 2: identity provider, tenant model, derived knowledge after revocation. | retain with audit / re-review / retire | — (parked by ship research-01) | 2026-10-08 |
| Q5 | research | R9: which search provider may the discovery agent call? | paid web-search API / self-hosted meta-search / none | — (parked) | 2026-10-08 |
| Q6 | research | R10: first cloud and first enterprise connector providers. | M365 / Google Workspace / file share | — (parked) | 2026-10-08 |
| Q7 | research | R11 (+R7, R8 EOS halves): does EOS route found_new/grow_existing through a KA request; expose grammar with digest; accept base key? | every gap / found_new only / not yet | — (parked; EOS repo) | 2026-10-08 |
| Q8 | research | R13: console shape — add a Processes tab or adopt the note's five pages? | add Processes (recommended) / five pages | — (parked) | 2026-10-08 |
| Q9 | research | R14: re-pin the EOS console frontend (Q418) for a process evidence panel? | re-pin after plan-05 / not | — (parked; author only) | 2026-10-08 |
