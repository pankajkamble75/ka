# KA-DEC-001 — Decisions from the 2026-10-08 question session

Author: the author (answers given in the `/questions` session, 2026-10-08). Transcribed verbatim from
`docs/questions/knowledge-acquisition.md` (✅ Decided table). This note carries no new proposal; it is the author's decisions
handed to the delivery pipeline as a set. Q7 (Enterprise OS routes `found_new` through KA) is an Enterprise OS research item
and is NOT in this set.

## Decisions to build, in severity order

1. **Q11 (PRODUCT / MAJOR) — duplicates.** "APPROVE of a candidate flagged `duplicate_of` an ACTIVE nugget auto-resolves as Keep
   Existing: the candidate closes as a duplicate (no second ACTIVE version) and its source and evidence are attached to the
   existing nugget." Protected governance.
2. **Q4 (PRODUCT / MAJOR) — re-review on revocation.** "When a source is revoked or deleted at its connector, every ACTIVE nugget
   derived from it returns to review as a candidate revision (same canonical id, new version, status PENDING_REVIEW) carrying the
   flag `source_revoked`; a person decides whether it stands on other evidence (APPROVE keeps it) or is retired (REJECT → the
   prior version becomes OBSOLETE and a graph proposal follows). Nothing is retired automatically and nothing stays silently
   live." Protected governance. The identity provider / tenant model is a two-repo plan and is NOT in this set.
3. **Q10 (PRODUCT / MAJOR) — prompt-injection defence.** "The extraction prompt separates instructions from quoted document
   content, and sources of authority INTERNET_RESEARCH or LLM_GENERATED are heuristic-only — their text may propose candidates
   but never a typed assertion that binds to the grammar without a reviewer's decision. A verifier model call is deferred."
4. **Q2 (PRODUCT / MAJOR) — repin.** "After a domain publication creates a new substructure version, KA never repins
   automatically. The graph-change page lists every instance still pinned to the old version with a Repin action; a named person
   repins each one, through the store's own `repin`, with an audit record."
5. **Q5 (PRODUCT / MAJOR) — search provider.** "A paid web-search API (the specific vendor chosen on price), implemented as one
   provider class behind the existing `SearchProvider` protocol; the key lives in the environment, never in a stored object; a
   monthly query cap (`KA_SEARCH_MONTHLY_CAP`) bounds spend on top of the per-mission budget." The vendor and key are the
   author's to supply; the class is built against the vendor's documented response shape and verified with a fixture until then.
6. **Q6 (PRODUCT / MINOR) — Microsoft 365 / SharePoint connector.** "One Microsoft Graph app registration covering OneDrive,
   SharePoint and Teams files, implemented as a `Connector` class behind the plan-08 contract; SharePoint permission lists map onto
   KA visibility; the client secret is named by `secret_ref` and read from the environment." The app registration is the
   author's to supply; the class is verified against a recorded Graph fixture until then.
7. **Q8 (PRODUCT / MINOR) — Processes tab.** "The console keeps its four tabs plus Images and gains a fifth top-level tab,
   Processes, pointing at the plan-06 process profile view."

## Constraints the author restated

- Invariant 3 holds throughout: a governed version is never edited; re-review and duplicate handling create versions or decisions.
- No credential is ever stored in a source, nugget, connection or audit record.
- Protected code (`ka/governance.py`, `ka/graph_change.py`, adapters, `ka/runtime_guard.py`) follows the seven-step protocol.
