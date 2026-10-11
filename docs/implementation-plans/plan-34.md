# Plan 34 - NEXOS integration v1: honest capability availability, the screen manifest, live G0/G1 evidence

Created: 2026-10-11 20:30 UTC

## Problem Description

The NEXOS v1 handoff (`docs/user-notes/nexos-integration-v1/handoff/`, from `pankajkamble75/knowledge-acquisition@4c579c0e`) assigns KA:
locate and verify the active KA (G0), conform to `agentx-services/v1` with real evidence (G1), register **only actually available**
capabilities, surface KA work in AgentX Growth and Human Tasks, preserve the specialist nugget/wiki UI and let AgentX link or embed it, and
save evidence under `docs/user-notes/nexos-integration-v1/`. Plans 29–33 built the AgentX surface. The live service ran pre-`/v1` code
until 2026-10-11 20:08 UTC (restarted on `295f185`). Two gaps remain against the handoff:

1. `/v1/capabilities` advertises `knowledge.publish` even when KA has no Knowledge Worker (graph mode `memory`), where a publication only
   updates KA's shadow graph. That is not an available capability in NEXOS terms.
2. AgentX reads a screen manifest from each service (KW's shape) to link or embed specialist UIs; KA has none.

Contract agreed with the AgentX session (2026-10-11): an unavailable capability is omitted from `/v1/capabilities` (push registration then
deactivates it), listed in `/healthz` `checks.capabilities_unavailable {id: reason}`, and an invoke returns `{"error":{"code":"unavailable",
…,"retryable":false}}` (503). Screens: `GET /v1/screens` → `{"screens":[{id, title, path, launch_url, embed_url|null, deep_link_params,
requires, provided_by}]}`, ids `ka.sources`, `ka.research`, `ka.wiki`, `ka.nuggets`, `ka.reviews`, `ka.publications`.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| KA as a service; AgentX PROPOSED v1 adopted | `knowledge-acquisition.md` §13 | ✅ built | **extends it** — availability and screens |
| One governance pipeline; a person decides | §4 | ✅ built | **obeyed** |
| Semantic capability truth lives in KW's Process Graph; AgentX's registry is technical only | NEXOS blueprint | — | **obeyed** — KA registers technical capabilities only |
| Preserve existing specialist UIs; AgentX links, not duplicates | NEXOS requirements §5 | — | **obeyed** — the manifest points at the existing console |

**Open questions:** none blocking. Cross-VPS reachability (WireGuard or TLS) is an operator decision, recorded as BLOCKED in the evidence.

## Research coverage

No research report — problem statement supplied by the NEXOS handoff; research-05 (12/12 shipped) is the base.

## Scope

In: `ka/agentx/availability.py` (new), `ka/agentx/screens.py` (new), `ka/agentx/router.py`, `ka/service.py` (push uses the available set),
`ka/config.py` (`KA_AGENTX_LOCAL_PUBLISH`, `KA_PUBLIC_BASE_URL`), `ka/tests/conftest.py` (suite default), tests, `tools/nexos_evidence.py`,
`tools/nexos_screenshots.py`, the evidence documents.
Out: networking between the VPSes (operator); AgentX/KW/DP repositories; PROD.

## Protected-code impact (summary)

✅ No protected code touched.

## Assumptions

- `knowledge.publish` is available when graph mode is `kw` (a real Knowledge Worker) or `eos-local` (legacy real import). In `memory` it is
  unavailable unless `KA_AGENTX_LOCAL_PUBLISH=1` (development and the test suite, which publishes to the in-memory graph on purpose).
- `launch_url` = `KA_PUBLIC_BASE_URL` (default: the request's own base) + `/console/#/…`; `embed_url` is `null` until KA sets
  `frame-ancestors` for AgentX's origins (not in this plan).

## Code blocks (B1..B5)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/agentx/availability.py` | which capabilities are available and why not |
| B2 | `ka/agentx/screens.py` | the screen manifest |
| B3 | `ka/agentx/router.py` | filtered capabilities, unavailable invoke, `/v1/screens`, health field |
| B4 | `ka/service.py` | push the available set |
| B5 | `ka/config.py` | two settings |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `unavailable(ka)` | `ka/agentx/availability.py` | 1 |
| D2 | filtered `/v1/capabilities`, push, invoke → `unavailable`, `checks.capabilities_unavailable` | `ka/agentx/router.py`, `ka/service.py` | 1 |
| D3 | `GET /v1/screens` in KW's shape | `ka/agentx/screens.py`, router | 1 |
| D4 | live evidence probe (G0/G1) writing `evidence/*.json` and `api-matrix.md` | `tools/nexos_evidence.py` | 2 |
| D5 | real screenshots of the six screens | `tools/nexos_screenshots.py`, `screenshots/` | 2 |
| D6 | `source-audit.md`, `implementation-report.md`, `test-results.md` | `docs/user-notes/nexos-integration-v1/` | 2 |
| D7 | the handoff copied beside the evidence | `docs/user-notes/nexos-integration-v1/handoff/` | 2 |

## Positive Test Cases (P1..P6)
- **P1** — graph mode `kw` → `/v1/capabilities` lists `knowledge.publish`; health has no unavailable capabilities.
- **P2** — `KA_AGENTX_LOCAL_PUBLISH=1` in memory mode → publish listed (the suite's default).
- **P3** — `/v1/screens` returns the six screens in KW's shape, every `launch_url` http(s), `provided_by` `knowledge-acquisition`, `embed_url` null.
- **P4** — journey (MOCK KW): acquire → review by a person → publish → KW proposal with lineage → the nugget ACTIVE and APPLIED.
- **P5** — duplicate delivery: the same invoke `Idempotency-Key` returns the same operation; replayed events keep their `event_id`.
- **P6** — missing Data Platform: `KA_STORAGE_BACKEND=data_platform` with an unreachable DP → the upload is `pending` (retryable), not lost and not falsely available.

## Negative Test Cases (N1..N5)
- **N1** — memory mode, default → publish omitted, `checks.capabilities_unavailable["knowledge.publish"]` names the reason.
- **N2** — invoking an omitted capability → 503 `{"error":{"code":"unavailable","retryable":false}}`, nothing recorded.
- **N3** — push registration in memory mode sends six capabilities (publish deactivated on AgentX).
- **N4** — rejected change: a reviewer rejects → the nugget is REJECTED, no graph change, no publication event.
- **N5** — conflicting versions: a contradicting candidate opens a conflict; resolve_conflict waits for a person.

## Plan totals

**Research points covered: n/a (NEXOS handoff) · Deliverables: 7 · Positive cases: 6 · Negative cases: 5 · Test cases total: 11.**

## Implementation Notes
- Written against `295f185`. Live service restarted on `295f185` at 2026-10-11 ~20:08 UTC after backing up `ka_storage`
  (`/root/ka-storage-backup-20261011T200721Z.tgz`, outside the repository).
