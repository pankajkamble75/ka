# Plan 07 - Discovery before fetching: a search-provider seam, allow-list and robots budget, provenance on every page

Created: 2026-10-08 18:00 UTC

## Problem Description

Research can only fetch URLs a mission already names (`ka/research.py::InternetResearchAgent` filters mission fields with
`startswith("http")`), behind `KA_RESEARCH_INTERNET`. A general question — "current Visa dispute processing rules" — produces
nothing from the web and only `LLM_GENERATED` candidates. research-01 R9 asks for a discovery step in front of the fetcher
(query → results → selection → fetch), honouring robots and an allowed-domain budget, with publisher, canonical URL and
retrieval time preserved on every source, and the search provider itself left as a decision (Q5).

Desired outcome: `ResearchOrchestrator` runs a `DiscoveryAgent` first; it turns the objective and questions into queries,
asks a `SearchProvider` (a protocol with a null implementation and a fixture-backed one until Q5 is answered), filters
results by the allow-list, `robots.txt` and a per-mission fetch budget, ranks them by overlap with the objective, and hands
the chosen URLs to the existing Internet agent, which fetches through plan-02's safe fetch and records
`publisher`, `canonical_url`, `retrieved_at`, `published_at`, `query` on the `Source`. The run records every query, every
result considered and every skip with its reason. PT7 turns green with the fixture provider; a real provider is one setting.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Research agents produce candidates only, through the one pipeline; agents cannot decide (§17) | `knowledge-acquisition.md` §4, §6 | ✅ built | **constrained by it** — discovery adds URLs; synthesis and governance are unchanged |
| URL safety: `is_safe_url` / `safe_fetch`; `KA_RESEARCH_INTERNET` gate | `knowledge-acquisition.md` §10 (plan-02) | ✅ built | **constrained by it** — every discovered URL goes through the same guard; the gate still governs fetching |
| Authority: fetched pages are `INTERNET_RESEARCH`; model text is `LLM_GENERATED` (§13) | `knowledge-acquisition.md` §4, §6 | ✅ built | **constrained by it** — PT7's "never a model answer presented as an internet source" holds by authority |
| Q5 — which search provider | `questions/knowledge-acquisition.md` Q5 | ❓ open | this plan does NOT need it: the provider is a protocol + setting; `null` and `fixture` implementations ship; a real one is a later, small plan |
| Research run records sources, evidence, candidates, tokens, cost, errors (§16) | `knowledge-acquisition.md` §6 | ✅ built | **extends it** — `ResearchRun.discovery` records queries, results, fetched, skipped |

**Open questions in the sections this plan touches:** Q5 — not blocking (seam built, provider deferred). None blocking.

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R8, R12 | ✅ shipped | plans 02–06 |
| R9 discovery agent; robots and allow-list budget; `KA_RESEARCH_INTERNET` kept | ✅ in scope | Phases 1–3; provider choice parked Q5 |
| R10 connectors | ⏭️ deferred | plan-08 |
| R11 gap routing | ⏭️ deferred | plan-09 |
| R13 / R14 decisions | ⏭️ deferred | Q8 / Q9 parked |
| R15 outbox; R16 benchmark half | ⏭️ deferred | plan-09 |

**Covered here: 1 of 16** (R9). Deferred: 5. Shipped earlier: 9. Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT7 a mission with a general process question, discovery enabled and the Internet gate on, yields candidates whose sources are fetched URLs with publisher and retrieval time, none of authority `LLM_GENERATED` presented as an internet source | R9 | **GREEN** — with the fixture provider and patched fetches in the suite; live against a real provider waits on Q5 |

## Scope

In: `ka/discovery.py` (new: `SearchResult`, `SearchProvider`, `NullSearchProvider`, `FixtureSearchProvider`, `select_provider`,
`RobotsCache`, `DiscoveryAgent`), `ka/research.py` (agent order; Internet agent accepts discovered URLs with their result
metadata; `ResearchRun.discovery`), `ka/model.py` (`ResearchRun.discovery`), `ka/ingestion.py` (`link()` stores provenance
metadata), `ka/config.py` (settings), `ka/api.py` (mission detail carries discovery; `GET /research/providers`), console
mission page (discovery table), tests, live flow, docs.

Out: a real search provider (Q5); crawling beyond the result URLs; paywall or login handling; content safety classification.

## Protected-code impact (summary)

✅ No protected code touched by any phase — research, discovery, ingestion metadata, model, config, API, console; `ka/governance.py`,
`ka/graph_change.py`, `ka/runtime_guard.py` and their shared dependencies are not edited.

## Assumptions

- Settings: `KA_SEARCH_PROVIDER` (`none` default | `fixture`), `KA_SEARCH_FIXTURE` (path to a JSON file `{query: [results]}`),
  `KA_ALLOWED_DOMAINS` (comma-separated; empty = any public host), `KA_DISCOVERY_BUDGET` (int, 5 fetches per mission),
  `KA_DISCOVERY_RESULTS` (int, 10 results per query), `KA_RESPECT_ROBOTS` (bool, True). The Internet gate `KA_RESEARCH_INTERNET`
  still governs every fetch; with it off, discovery still runs the search and records the results as `skipped: gate off`, so a
  reviewer sees what would have been fetched.
- `SearchResult(url, title, snippet, publisher, published_at, query, rank)`; the provider protocol is
  `search(query, *, limit) -> list[SearchResult]`. `NullSearchProvider` returns `[]` and the run notes "no search provider (Q5)".
  `FixtureSearchProvider` serves the JSON file, matching the query exactly, then by normalized-token overlap.
- Queries: the objective, then each research question; each truncated to 200 characters; duplicates removed.
- Selection: canonical URL = scheme + host + path (no fragment, no tracking params `utm_*`, `fbclid`, `gclid`); dedupe by canonical
  URL; drop hosts outside `KA_ALLOWED_DOMAINS` when set; drop URLs that fail `is_safe_url`; drop URLs `robots.txt` disallows for
  user-agent `enterprise-os-ka` (robots fetched once per host through `safe_fetch`, cached for the run; an unreachable robots file
  counts as allowed, and that is recorded); rank by token overlap of title+snippet with the objective, then provider rank; take the
  first `KA_DISCOVERY_BUDGET`.
- The Internet agent fetches the selected URLs (through `ingestion.link`, i.e. `safe_fetch`), and `link()` stores
  `metadata = {canonical_url, publisher, published_at, retrieved_at, query, discovered_rank}` on the `Source`; the finding's
  authority is `INTERNET_RESEARCH`. Publication date unknown → `published_at: null` (never guessed).
- `ResearchRun.discovery = {provider, queries: [...], results: n, selected: [...], fetched: [...], skipped: [{url, reason}]}`.

## Phases

### Phase 1 - Provider seam and settings

- `ka/discovery.py`: `SearchResult`, `SearchProvider` protocol, `NullSearchProvider`, `FixtureSearchProvider`, `select_provider()`,
  `canonical_url(url)`, `RobotsCache(fetch=safe_fetch)` with `allowed(url) -> tuple[bool, str]`.
- `ka/config.py`: the six settings.
- **Protected-code touched:** none

### Phase 2 - The discovery agent in the coordinator

- `ka/discovery.py::DiscoveryAgent(provider, robots)` with `research(ctx) -> list[Finding]` returning `[]` and setting
  `ctx.discovered` (selected `SearchResult`s) and `ctx.run.discovery`; `AgentContext` gains `discovered: list[SearchResult]`.
- `ka/research.py`: `DiscoveryAgent` first in the agent list; `InternetResearchAgent` fetches `ctx.discovered` URLs (plus explicit
  ones as before), passing result metadata to `ingestion.link(..., metadata=...)`; `ka/ingestion.py::link` accepts `metadata` and
  stamps `retrieved_at`.
- `ka/model.py`: `ResearchRun.discovery: dict`.
- **Protected-code touched:** none

### Phase 3 - API, console, docs, flow

- `ka/api.py`: `GET /research/providers` (active provider, settings, robots on/off, allow-list); mission detail already returns
  runs — `discovery` rides on the run.
- `ka/console/app.js`: mission page shows the discovery table (queries; results with rank, publisher, selected/skipped + reason;
  fetched sources link); Dashboard shows the provider.
- `docs/architecture/knowledge-acquisition.md` §6 paragraph; `.env.example`; `e2e/plan07_discovery_flow.py` (fixture provider,
  patched fetch is not possible live → the flow runs with `KA_RESEARCH_INTERNET=0` and asserts the discovery table shows results
  and "gate off" skips; the fetch path is proved by the unit tests).
- **Protected-code touched:** none

## Code blocks (B1..B6)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/discovery.py` | results, providers, canonical URL, robots cache, the agent |
| B2 | `ka/research.py` | agent order, Internet agent consuming discovered URLs, `AgentContext.discovered` |
| B3 | `ka/model.py` | `ResearchRun.discovery` |
| B4 | `ka/ingestion.py` | `link(metadata=)` with `retrieved_at` |
| B5 | `ka/config.py` | the six settings |
| B6 | `ka/api.py`, `ka/console/app.js` | providers route; discovery table and provider status (one block each) |

## Deliverables (D1..D9)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `SearchResult`, `SearchProvider`, `NullSearchProvider`, `FixtureSearchProvider`, `select_provider` | `ka/discovery.py` | 1 |
| D2 | `canonical_url`, `RobotsCache.allowed` | `ka/discovery.py` | 1 |
| D3 | the six settings | `ka/config.py` | 1 |
| D4 | `DiscoveryAgent.research` (queries → results → selection with reasons) | `ka/discovery.py` | 2 |
| D5 | `AgentContext.discovered`; Internet agent fetches discovered URLs; discovery first in the coordinator | `ka/research.py` | 2 |
| D6 | `ResearchRun.discovery` | `ka/model.py` | 2 |
| D7 | `link(metadata=)` storing canonical URL, publisher, published_at, retrieved_at, query | `ka/ingestion.py` | 2 |
| D8 | `GET /research/providers`; console discovery table and provider status | `ka/api.py`, `ka/console/app.js` | 3 |
| D9 | architecture §6 paragraph; `.env.example`; live flow | docs, `e2e/plan07_discovery_flow.py` | 3 |

**Total deliverables: 9.**

## Positive Test Cases (P1..P9)

- **P1** — `FixtureSearchProvider` answers an exact query and a near query (token overlap) from the JSON file; `NullSearchProvider` answers `[]`.
- **P2** — `canonical_url` strips fragments and `utm_*`/`fbclid`/`gclid` parameters and lowercases the host; two tracked variants dedupe to one.
- **P3** — `RobotsCache.allowed` honours `Disallow: /private` for user-agent `enterprise-os-ka` and allows `/public`; an unreachable robots file is allowed and recorded.
- **P4** — a mission with objective "Visa dispute processing rules" and one question yields two deduplicated queries, and the run's `discovery.queries` lists them.
- **P5** — selection ranks results by overlap with the objective and respects `KA_DISCOVERY_BUDGET=2`: the two best are `selected`, the rest `skipped: budget`.
- **P6** — with the gate on and `safe_fetch` patched to serve pages, the Internet agent fetches the selected URLs; each `Source` carries `metadata.canonical_url`, `publisher`, `published_at` (null when unknown), `retrieved_at`, `query`; candidates have authority `INTERNET_RESEARCH`.
- **P7** — PT7: the mission's candidates come from fetched URLs with publisher and retrieval time, and no candidate of authority `LLM_GENERATED` carries internet-source metadata (the LLM agent's sources have `channel RESEARCH`, type `research`, no `canonical_url`).
- **P8** — `GET /research/providers` reports `fixture` with its settings; the mission detail's run carries `discovery`.
- **P9** — console: the mission page shows the discovery table with queries, results and skip reasons (`e2e/plan07_discovery_flow.py`).

## Negative Test Cases (N1..N7)

- **N1** — `KA_SEARCH_PROVIDER=none`: discovery records "no search provider (Q5)", selects nothing, the Internet agent fetches nothing, the mission still completes.
- **N2** — a result on a host outside `KA_ALLOWED_DOMAINS` is `skipped: domain not allowed`; a result whose host resolves to a private address is `skipped: unsafe url` (never fetched).
- **N3** — a result `robots.txt` disallows is `skipped: robots`, never fetched; with `KA_RESPECT_ROBOTS=0` it is fetched and the run notes robots were ignored.
- **N4** — gate off (`KA_RESEARCH_INTERNET=0`): results are selected and recorded as `skipped: gate off`; no fetch happens; the run completes.
- **N5** — a provider that raises is isolated: the run records the error in `errors`, the other agents still run, status COMPLETED when any candidate exists.
- **N6** — an unknown `KA_SEARCH_PROVIDER` value fails closed to `none` with a note.
- **N7** — the fetch budget is per mission, not per query: with budget 3 and two queries returning 4 results each, exactly 3 fetches happen.

## Plan totals

**Research points covered: 1 of 16 · Deliverables: 9 · Positive cases: 9 · Negative cases: 7 · Test cases total: 16 ·
Product tests served: 1 of 8 (1 turns green here).**

## Implementation Notes

- **Re-check this plan against the tree before implementing.** Written after plan-06 landed (`31a4673`); confirm the
  Internet agent still reads only explicit URLs and `link()` has no `metadata` parameter.
- Tests patch `ka.security._resolve` (public address) and `ka.security.safe_fetch` (canned pages, canned robots) so no network is touched.
- The live flow uses the fixture provider and the gate off, so it proves discovery and the console without network.
