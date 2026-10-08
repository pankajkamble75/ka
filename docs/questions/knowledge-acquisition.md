# Knowledge Acquisition — questions and the answers that became architecture

The architecture document is [`../architecture/knowledge-acquisition.md`](../architecture/knowledge-acquisition.md).
Registry of every open question: [`../trackers/QUESTIONS-TRACKER.md`](../trackers/QUESTIONS-TRACKER.md).

## ✅ Decided

| Q | Decision | Date | Lives in |
|---|---|---|---|
| — | Console is four tabs (Add knowledge · Knowledge nuggets · Browse by scope · Dashboard) plus Images | 2026-10-08, the author in chat | architecture §8 |

## ❓ Open

Parked by the `ship research-01` run on 2026-10-08. Each sits beside the research point it blocks; the KA-side work that
does not depend on the answer continues.

### Q1 — Who may call the KA API? (R4 step 1 builds containment; this decides the policy)
**Scenario.** KA runs on a VPS bound to all interfaces, reached from the author's browser over the public address. EOS
has only loopback containment and no authentication (`agent_x_mount.py:56`). Personal and workplace documents are about
to be ingested.
**Decision required.** The access policy for `/api/knowledge-acquisition/*`.
**Big picture.** *Loopback only* copies EOS and locks the remote browser out. *Loopback + bearer token* keeps the remote
console usable and gives KA↔EOS calls an identity. *Enterprise IdP* is the real answer and is a two-repo change.
**Options.** (a) loopback only; (b) **loopback + `KA_ACCESS_TOKEN` bearer for non-loopback peers — recommended, and what
plan-02 builds as the default**; (c) open (today). **Cost.** (b) one token to paste once in the console.

### Q4 — Identity provider, tenant model, and derived knowledge after source revocation (R4 step 2)
**Scenario.** A connector's permission is revoked, or a personal document is deleted, after nuggets derived from it were
approved and compiled into an EOS graph.
**Decision required.** Which IdP and tenant boundary both repos adopt, and whether derived knowledge is retained,
re-reviewed or retired on revocation.
**Big picture.** Without a tenant model there is no cross-tenant test to pass (note REQ-008). Retention policy decides
whether revocation is a visibility change or a knowledge change (a new version with status OBSOLETE).
**Options.** retain with audit / re-review (candidate again) / retire (OBSOLETE + graph proposal). **Recommendation:**
re-review, because it keeps Invariant 3 and makes the human decide. **Cost.** a two-repo auth plan.

### Q5 — Which search provider for internet discovery (R9)
**Scenario.** A mission asks a general process question with the Internet gate on; the discovery agent needs search results.
**Decision required.** The provider (and key) KA may call. **Options.** a paid web-search API / a self-hosted meta-search /
none (URL-only, today). **Recommendation:** decide on cost; plan-07 builds the `SearchProvider` protocol, robots and
allow-list budget with a null provider so the choice is a configuration, not a rewrite. **Cost.** per-query fee.

### Q6 — First cloud and first enterprise connector (R10)
**Scenario.** Personal and workplace documents. **Decision required.** Which providers, with what consent flow.
**Options.** Microsoft 365 / SharePoint · Google Drive / Workspace · a file share. **Recommendation:** the one the business
already uses; plan-08 builds the `Connector` protocol with the local-folder connector first. **Cost.** app registration.

### Q7 — Does EOS route `found_new` / `grow_existing` through a KA acquisition request? (R11; also R7 and R8 EOS halves)
**Scenario.** EOS's `act_on_gaps` (`gap_v2/act.py:777`) founds and grows graphs itself under HOTL points that default to
`auto`. Spec §43 and Invariants 1–2 say a gap should become a KA request. Three EOS-side changes are implied: route gaps
to KA, expose the grammar read-only with a digest, accept a base key on `propose_instance_change`.
**Decision required.** Whether and when the EOS repo takes those changes. **Big picture.** Until then, KA receives gaps only
from code nobody has written, and scenario A10 of the note is unreachable. **Options.** EOS calls KA for every gap / only
for `found_new` / not yet. **Recommendation:** `found_new` first. **Cost.** an EOS research + plan under its own pipeline.

### Q8 — Console shape (R13)
**Scenario.** The author ruled four tabs plus Images; the note proposes five pages (Sources, Knowledge, Processes, Review,
Publications). **Decision required.** Add a Processes tab, or re-layout. **Recommendation:** add Processes; plan-06 builds
the process profile view inside Browse by scope so the capability exists either way. **Cost.** none.

### Q9 — Re-pin the EOS console frontend for a process evidence panel? (R14)
**Scenario.** `console/frontend/**` is frozen byte-identical by Q418 (`test_q418_frontends_unchanged.py`). An evidence
panel on the node card (`GraphPanel.tsx:1231`) is impossible without the author's re-pin. **Decision required.** Re-pin or
not. **Recommendation:** re-pin once, after plan-05 publishes real lineage worth showing. **Cost.** one fingerprint update.
