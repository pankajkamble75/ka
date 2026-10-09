# Architecture index

| Document | What it answers |
|---|---|
| `../../knowledge-acquisition-requirements.md` | The source specification for the Knowledge Acquisition subsystem (§1–§48). |
| `knowledge-acquisition.md` | How the `ka` package realises the specification: modules, objects, invariants, integration seams. |
| `../questions/knowledge-acquisition.md` | The questions behind the decisions, and the ones parked for the author (Q1–Q16). |
| `../research/research-01.md` | Review of KA-ENH-001: bind to EOS grammar, publish through EOS proposals; R1–R16. |
| `../research/research-02.md` | Grounding of the author's 2026-10-08 decisions (Q2, Q4, Q5, Q6, Q8, Q10, Q11) in the code; R1–R9. |
| `../research/research-03.md` | Data Platform as KA's physical store: the real seams in this repository, the contract KA needs from DP, what must not move; R1–R14. |
| `../contracts/data-platform-v1-ka-subset.md` | The DP v1 subset KA needs (ten calls, six events, error envelope), mirrored by executable fixtures and `FakeDataPlatform`; owned by §11 of `knowledge-acquisition.md`. |
