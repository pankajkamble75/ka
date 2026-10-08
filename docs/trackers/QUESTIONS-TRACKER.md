# Questions Tracker

Decisions parked for the author. One row per question, `Q1`, `Q2`, … Never renumber.

| Q | Stage | Question | Options | Decision | Date |
|---|---|---|---|---|---|
| Q1 | implementation | §42: who may call the KA API? Visibility/permissions are modelled; no caller identity is checked. | add auth at the API edge / reuse enterprise-os auth / leave open for intranet | — | 2026-10-08 |
| Q2 | implementation | A domain write via EnterpriseOSGraphAdapter creates a new substructure version. Who repins instances, and when? | KA repins automatically after apply / operator repins via store `repin` / proposal lists repin as a manual step | — | 2026-10-08 |
| Q3 | implementation | Should the standalone server auto-apply low-impact Graph Change Proposals by default (`auto_approve_low_impact`)? | on / off (current) | — | 2026-10-08 |
