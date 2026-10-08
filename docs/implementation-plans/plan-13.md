# Plan 13 - A real search provider behind the discovery seam: Brave, a key in the environment, a monthly cap (Q5)

Created: 2026-10-09 01:20 UTC

## Problem Description

Discovery (plan-07) turns a mission's questions into queries, but the only providers are `none` and a JSON fixture
(`ka/discovery.py:52-77`, `select_provider` at `:79-86`). The author decided (Q5, 2026-10-08): a paid web-search API chosen on
price, one provider class behind the existing `SearchProvider` protocol, the key in the environment and never in a stored object,
and a monthly query cap on top of the per-mission budget. research-02 §5 recommends Brave (documented JSON, free development tier).
The vendor confirmation and the key are the author's (Q12 / R8); until then the provider is verified against a recorded response
and the live product test PT5 is NOT RUN.

Desired outcome: `KA_SEARCH_PROVIDER=brave` selects `BraveSearchProvider`; with no key it fails closed to `none` with a note the
Dashboard shows; every query counts against `KA_SEARCH_MONTHLY_CAP` in a per-month meter; at the cap the provider answers nothing
and says so; `GET /research/providers` and the Dashboard report key presence (never the key), used/cap and the month.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Q5 paid web-search API behind `SearchProvider`; key in the environment; monthly cap | `knowledge-acquisition.md` §6 | ⏳ decided, not built | **builds it** — state moves to ✅ on upload |
| Discovery: canonical URLs, allow-list, robots, per-mission budget; fetch only when the gate is on | `knowledge-acquisition.md` §6 (plan-07) | ✅ built | **constrained by it** — the provider only supplies results; selection and fetching are unchanged |
| Q10 Internet sources are heuristic-only | `knowledge-acquisition.md` §3 (plan-11) | ✅ built | **relied on** — pages found by search bind `proposed` until review |
| Security: no credential in a stored object; `secret_ref` names a variable | `knowledge-acquisition.md` §2, §10 | ✅ built | **constrained by it** — the key is read at call time from `KA_SEARCH_API_KEY` and never logged or stored |
| Q12 (R8) vendor confirmation and key | `questions/knowledge-acquisition.md` Q12 | ❓ open | this plan does NOT need it to build: Brave is the recommendation; the class is fixture-verified; PT5 live is NOT RUN until the key exists |

**Open questions in the sections this plan touches:** Q12 — not blocking the build; blocks only the live product test.

## Research coverage (R1..R9)

Source: [research-02](../research/research-02.md) — **9 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1–R4 | ✅ shipped | plans 10–12 |
| R5 search provider | ✅ in scope | Phases 1–3 |
| R6, R7 | ⏭️ deferred | plan-14, plan-15 |
| R8 vendor + key | ⏭️ deferred | author decision Q12 — the build does not wait on it |
| R9 M365 registration | ⏭️ deferred | author decision Q13 |

**Covered here: 1 of 9.** Deferred: 4. Shipped earlier: 4.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT5 with a search key configured, a general-question mission yields candidates from URLs the provider returned, and the Dashboard shows queries used against the monthly cap | R5, R8 | still **NOT RUN** live — the key is the author's (Q12); the fixture-driven equivalent is GREEN here |

## Scope

In: `ka/discovery.py` (`BraveSearchProvider`, `SearchMeter`, `select_provider` for `brave`, provider notes into the run), `ka/config.py`
(`KA_SEARCH_API_KEY`, `KA_SEARCH_MONTHLY_CAP`), `ka/api.py` (providers route fields), `ka/service.py` (dashboard used/cap), `ka/console/app.js`
(Dashboard line), fixture `ka/tests/fixtures/brave_response.json`, tests, live flow (no key: the fail-closed path), `.env.example`, docs.

Out: other vendors (one more class later); a per-user quota; the key itself.

## Protected-code impact (summary)

✅ No protected code touched by any phase — discovery, config, routes, console.

## Assumptions

- `BraveSearchProvider(fetch_json=None)`: `search(query, limit)` GETs `https://api.search.brave.com/res/v1/web/search?q=…&count=…` with
  `X-Subscription-Token: <key>` through an injectable `fetch_json(url, headers) -> dict` (httpx by default); maps `web.results[]` to
  `SearchResult(url, title, description→snippet, profile.name or meta_url.hostname→publisher, page_age→published_at)`. Any HTTP or parse
  failure → `[]` with `last_note`. Before each call it asks the meter; at the cap it returns `[]` with `last_note="monthly cap reached (N/N)"`.
- `SearchMeter(path=<storage>/search_usage.json)`: `{"YYYY-MM": count}`; `used()`, `record(n=1)`, `remaining(cap)`; a new month starts at 0.
- `select_provider()`: `brave` → the provider when `KA_SEARCH_API_KEY` is set, else `NullSearchProvider` with the note
  "brave configured but KA_SEARCH_API_KEY is unset (Q12); failing closed to none". The run's `discovery.notes` carries the provider's `last_note`.
- The key is read with `config.get("KA_SEARCH_API_KEY")` at call time; the providers route returns `key_present: bool` only.

## Phases

### Phase 1 - Provider, meter, selection
- `ka/discovery.py` block additions; `ka/config.py` two settings.
- **Protected-code touched:** none

### Phase 2 - Surfaces
- `ka/api.py` providers route: `requested`, `key_present`, `monthly_cap`, `used_this_month`, `month`. `ka/service.py` dashboard research dict:
  `search_used`, `search_cap`, `search_requested`. Console Dashboard line shows them.
- **Protected-code touched:** none

### Phase 3 - Tests, flow, docs
- Fixture; `test_plan13_search_provider.py`; `e2e/plan13_search_provider_flow.py` (server with `KA_SEARCH_PROVIDER=brave`, no key → Dashboard
  says so; a mission records the note); `.env.example`; architecture §6 → ✅ built; Q12 stays open with the live test named.
- **Protected-code touched:** none

## Code blocks (B1..B5)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/discovery.py` | Brave provider, meter, selection, notes |
| B2 | `ka/config.py` | two settings |
| B3 | `ka/api.py` | providers route fields |
| B4 | `ka/service.py` | dashboard fields |
| B5 | `ka/console/app.js` | Dashboard line |

## Deliverables (D1..D7)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `BraveSearchProvider` (injectable fetch, mapping, failure → `[]` + note) | `ka/discovery.py` | 1 |
| D2 | `SearchMeter` (per-month file counter) and the cap check | `ka/discovery.py` | 1 |
| D3 | `select_provider` handles `brave`, fails closed without a key; run notes carry `last_note` | `ka/discovery.py` | 1 |
| D4 | `KA_SEARCH_API_KEY`, `KA_SEARCH_MONTHLY_CAP` | `ka/config.py` | 1 |
| D5 | providers route and dashboard fields | `ka/api.py`, `ka/service.py` | 2 |
| D6 | Dashboard line (requested provider, key presence, used/cap) | `ka/console/app.js` | 2 |
| D7 | fixture, live flow, `.env.example`, architecture §6 ✅ | tests/fixtures, `e2e/plan13_search_provider_flow.py`, docs | 3 |

**Total deliverables: 7.**

## Positive Test Cases (P1..P7)
- **P1** — the recorded Brave response maps to `SearchResult`s with url, title, snippet, publisher and published_at; rank is 1-based; `limit` is honoured.
- **P2** — `select_provider` with `brave` and a key → the Brave provider; the meter path is under the storage root.
- **P3** — the meter counts per calendar month and persists across instances; a new month starts at 0.
- **P4** — a mission with the Brave provider (patched fetch) records results with publisher in `run.discovery` and, with the gate on, fetched pages carry `publisher`/`published_at`.
- **P5** — `GET /research/providers` reports `requested=brave`, `key_present` (never the key), `monthly_cap`, `used_this_month`, `month`.
- **P6** — the Dashboard payload carries `search_used` / `search_cap` / `search_requested`.
- **P7** — PT5 fixture-driven: general question → candidates whose sources are URLs the provider returned; the live PT5 is a test that SKIPS with the reason "needs KA_SEARCH_API_KEY (Q12)".

## Negative Test Cases (N1..N5)
- **N1** — the key never appears in any stored object, audit, event or run record after a mission (grep the storage tree).
- **N2** — `brave` without a key fails closed to `none` with the Q12 note; the mission still completes.
- **N3** — an HTTP error or malformed JSON from the provider → `[]` with `last_note`; the run records the note; nothing raises.
- **N4** — at the cap (or cap 0) the provider makes no call and the run notes "monthly cap reached".
- **N5** — the per-mission budget still applies on top of the cap (more results than `KA_DISCOVERY_BUDGET` → skipped "budget").

## Plan totals

**Research points covered: 1 of 9 · Deliverables: 7 · Positive cases: 7 · Negative cases: 5 · Test cases total: 12 ·
Product tests served: 1 of 7 (0 turn green live here; PT5's fixture-driven equivalent passes).**

## Implementation Notes
- Written against `3608cac` (plan-12 upload). No protected code.
