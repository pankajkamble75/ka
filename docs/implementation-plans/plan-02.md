# Plan 02 - Access containment, upload and URL safety, and visibility protection on scope changes

Created: 2026-10-08 14:50 UTC

## Problem Description

KA checks no caller on any route (`ka/api.py:177-196`), reads an upload body of any size (`ka/api.py:247`), follows a
pasted URL to any address including loopback and private ranges (`ka/ingestion.py:63`), and lets a PERSONAL- or
TEAM-visibility nugget be re-scoped or promoted to a domain without recording that its audience widened
(`ka/governance.py` CHANGE_SCOPE branch; `ka/promotion.py::decide`). research-01 R4 step 1, R5 and R6 ask for the
containment EOS already uses plus a bearer token for non-loopback peers, a body cap, an SSRF guard, and an explicit
visibility decision on any broadening.

Desired outcome: a request from a non-loopback peer without the configured token is refused on every KA route; the
console keeps working from the author's remote browser once a token is pasted; an oversize upload is refused with 413; a
link to an unsafe address is recorded as a blocked source and never fetched, by `link()` and by the Internet agent alike;
and no decision can widen a nugget's visibility without saying so on the decision record.

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| Security §42: visibility modelled, enforcement deferred | `knowledge-acquisition.md` §10 | ⏳ decided, not built | **builds step 1** — containment + token; state moves to ✅ (step 1) on upload; step 2 stays Q4 |
| Nugget visibility = narrowest of its sources; agents barred from sources above clearance | `knowledge-acquisition.md` §10 | ✅ built | **constrained by it** — Phase 3 extends it to scope changes, never loosens it |
| One governance pipeline; a decision is a `GovernanceDecision` with who/why | `knowledge-acquisition.md` §4 | ✅ built | **constrained by it** — the visibility widening is a field on the decision, not a second path |
| Governed versions immutable (Inv. 3) | `knowledge-acquisition.md` §4 | ✅ built | **constrained by it** — re-scoping still creates a new candidate; nothing edits a governed version |
| Q1 access policy: loopback + bearer token recommended | `questions/knowledge-acquisition.md` Q1 | ❓ open, recommendation given | **builds the recommendation as the default** (`KA_ACCESS_POLICY=token`), states it as an assumption; the author may still choose (a) or (c) by setting the variable |
| EOS precedent: loopback containment, "not an access policy", inverts behind a proxy | EOS `agent_x_mount.py:56-59` | precedent | **copied**, with the same warning in the module docstring |

**Open questions in the sections this plan touches:** Q1 — this plan builds the recommended option as a configurable
default and does NOT need it answered to proceed; Q4 (IdP, tenant, retention) — this plan does NOT need it answered.

## Research coverage (R1..R16)

Source: [research-01](../research/research-01.md) — **16 research points**.

| Research point | This plan | Where / why |
|---|---|---|
| R1 ChangeOps into EOS proposals | ⏭️ deferred | plan-05 — depends on R2's canonical keys |
| R2 subject/predicate/object + GrammarBinding | ⏭️ deferred | plan-03 |
| R3 process extraction pass | ⏭️ deferred | plan-04 |
| R4 security step 1 (containment, service token); step 2 decide | ✅ step 1 in scope | Phases 1–2; step 2 parked as Q4 |
| R5 upload cap; SSRF guard | ✅ in scope | Phase 2 |
| R6 visibility re-check on promotion and CHANGE_SCOPE | ✅ in scope | Phase 3 |
| R7 idempotency | ⏭️ deferred | plan-05 (KA half); EOS half parked Q7 |
| R8 grammar + digest | ⏭️ deferred | plan-03 (KA half); EOS half parked Q7 |
| R9 discovery agent | ⏭️ deferred | plan-07; Q5 parked |
| R10 connectors | ⏭️ deferred | plan-08; Q6 parked |
| R11 gap routing | ⏭️ deferred | plan-09 (KA half); Q7 parked |
| R12 process profile view | ⏭️ deferred | plan-06 |
| R13 console shape | ⏭️ deferred | decision Q8, parked for the author |
| R14 EOS frontend re-pin | ⏭️ deferred | decision Q9, parked for the author |
| R15 events outbox | ⏭️ deferred | plan-09 |
| R16 store benchmark; layout extras | ⏭️ deferred | plan-04 (layout extras), benchmark in plan-09 |

**Covered here: 3 of 16** (R4 step 1, R5, R6). Deferred: 13 (each with its plan or parked question above). Rejected: 0.

### Product tests this plan serves

| Product test | Proves | After this plan |
|---|---|---|
| PT5 non-loopback refused; oversize upload refused; unsafe link never fetched | R4, R5 | **GREEN** — this plan is what makes it true |
| PT6 PERSONAL knowledge cannot widen scope without a decision naming the visibility change | R6 | **GREEN** — this plan is what makes it true |

## Scope

In: `ka/security.py` (new), config declarations, `api.py` route dependency and body cap, `ingestion.link()` and the
Internet agent using the URL guard, `governance.decide(CHANGE_SCOPE)` and `promotion.decide()` visibility rule,
console token field and header, tests, `.env.example`, architecture §10 and `docs/protected.md` updates.

Out: identity provider, tenant model, per-user ACL evaluation on reads (Q4); authentication of EOS (its repo); malware
scanning; prompt-injection defences (belong with extraction, plan-04).

## Protected-code impact (summary)

⚠️ TOUCHES PROTECTED — `ka/governance/` (Inv. 3), touched by Phase 3.
HOW: `GovernanceService.decide`, the `CHANGE_SCOPE` branch (`ka/governance.py:286-296`): before creating the re-scoped
candidate, compare the candidate's visibility class with the target scope's required class; refuse unless the decision
carries `widen_visibility=True`; when it does, record `visibility_change={"from","to"}` on the `GovernanceDecision` and set
the new candidate's visibility to the target class. `GovernanceDecision` gains the optional `visibility_change` field
(`ka/model.py`, a shared dependency of the protected area).
WHY: the seam is inside `decide` — CHANGE_SCOPE is the only path that re-scopes a candidate, and the rule must hold for
every caller (console, `apply_nugget`, promotion). A wrapper outside `decide` would leave the API's direct `decide` route
unguarded.
Regression risk: every CHANGE_SCOPE decision; `apply_nugget` re-scope path (`ka/service.py`); phase2 `::test_P10`,
api `::test_P8`.
Characterization gap: no test pins that CHANGE_SCOPE preserves the candidate's visibility today, nor that promotion keeps
the lead's visibility.
Re-verify: run the governance suites (`test_plan01_phase2_governance.py`, `test_plan01_phase6_propagation.py`,
`test_plan01_api_console.py`) unmodified, then the live console: re-scope a PERSONAL note's candidate from an instance to
the domain via Apply → refused with the reason; again with the widen checkbox → applied, decision shows the change.
Bump the Verified date for `ka/governance/` in `docs/protected.md` in the same commit.

`ka/runtime_guard.py` and `ka/graph_change/` are not touched. The decision to guard the API with a dependency on the
router rather than middleware is a design choice (testable per route with `TestClient`), not protection-driven.

## Assumptions

- `KA_ACCESS_POLICY` defaults to `token`: loopback peers always pass; non-loopback peers need `Authorization: Bearer
  <KA_ACCESS_TOKEN>`. If no token is configured, non-loopback peers are refused (fail closed). `open` restores today's
  behaviour; `loopback` copies EOS exactly. This is Q1's recommended option, chosen unattended.
- The console stores the token in `localStorage['ka.token']` and sends it on every API call; the static console files
  themselves stay unauthenticated (they contain nothing but code).
- This host's `.env` (git-ignored) receives a generated `KA_ACCESS_TOKEN` so the author's remote console keeps working
  after one paste; the token is reported in the ship report, not committed.
- Visibility classes map to scope classes as: INSTANCE scope accepts PERSONAL/TEAM/INSTANCE/DOMAIN/ENTERPRISE;
  DOMAIN scope requires at least DOMAIN; PARENT_DOMAIN and STRUCTURE require ENTERPRISE. Widening sets the candidate's
  visibility to exactly the required class, never higher than needed.
- `KA_MAX_UPLOAD_MB` defaults to 25 (images already cap at 10 MB; documents are larger).
- The SSRF guard resolves the hostname and refuses loopback, link-local (incl. 169.254.169.254), private, reserved,
  multicast and unspecified addresses, and non-http(s) schemes; `KA_URL_ALLOWLIST` (comma-separated hostnames) bypasses
  the private-range check for named intranet hosts. Redirects are followed one hop at a time and each hop is re-checked.

## Phases

### Phase 1 - Access containment and token

- New `ka/security.py`: `peer_is_loopback(request)`, `require_access(request)` FastAPI dependency implementing
  `KA_ACCESS_POLICY ∈ {loopback, token, open}`; 401 with `WWW-Authenticate: Bearer` for a missing/wrong token, 403 for
  loopback-only policy; constant-time comparison; module docstring carries the EOS warning (inverts behind a proxy).
- `ka/config.py`: declare `KA_ACCESS_POLICY` (str, "token"), `KA_ACCESS_TOKEN` (str, ""), `KA_MAX_UPLOAD_MB` (int, 25),
  `KA_URL_ALLOWLIST` (str, "").
- `ka/api.py`: `router = APIRouter(prefix=PREFIX, dependencies=[Depends(require_access)])`; console static routes stay open.
- Console: "You" panel gains an "Access token" field saved to `localStorage['ka.token']`; `api()` and `form()` send
  `Authorization: Bearer …` when set; a 401 shows a toast naming the field.
- `.env.example` documents the four settings. On this host, write a generated token into `.env`.
- **Protected-code touched:** none

### Phase 2 - Upload cap and URL safety

- `ka/security.py`: `is_safe_url(url, allowlist) -> tuple[bool, str]` resolving every A/AAAA record and classifying with
  `ipaddress`; `safe_fetch(url, timeout)` that follows redirects hop by hop through the same check.
- `ka/ingestion.py::link()`: call `safe_fetch`; on refusal record the source with `extraction_status=FAILED`,
  `extraction_note="blocked: <reason>"`, no bytes fetched, audit `source.blocked`.
- `ka/research.py::InternetResearchAgent`: skip unsafe URLs, append the reason to `run.errors`.
- `ka/api.py`: `/sources/upload` and `/corrections/upload` read at most `KA_MAX_UPLOAD_MB` MiB + 1 byte and raise 413
  beyond it; the Content-Length header, when present and over the cap, is refused before reading.
- **Protected-code touched:** none

### Phase 3 - Visibility protection on CHANGE_SCOPE and promotion (protected)

1. **Declare.** `ka/governance.py::GovernanceService.decide`, CHANGE_SCOPE branch; `ka/promotion.py::PromotionService.decide`;
   `ka/model.py::GovernanceDecision.visibility_change`; `ka/vocab.py::required_visibility(scope_type)`. Why protected path:
   see summary — the seam has no non-protected entry.
2. **Characterize first** (own commit, green against unchanged code): P6 — CHANGE_SCOPE today re-creates the candidate with
   the same visibility; P7 — promotion today creates the domain candidate with the lead instance nugget's visibility.
3. **Add coverage before the change**: N4 — a wrong `by` (research agent) is still refused on CHANGE_SCOPE; P8 —
   CHANGE_SCOPE within the same scope class leaves visibility untouched.
4. **Change**: implement `required_visibility`; refuse widening without `widen_visibility=True` (`GovernanceError`, reason
   names from/to); with it, set the new candidate's visibility to the required class and record `visibility_change`.
   `apply_nugget` and the API `DecisionIn` / `ApplyIn` / `PromotionDecisionIn` gain `widen_visibility: bool = False`.
   Console: the Apply row and the re-scope form gain a "widen visibility" checkbox shown only when needed (the 409 reason
   tells the user).
5. **Existing covering tests pass UNMODIFIED**: N7.
6. **Re-verify live**: the console flow in the summary.
7. **Bump `Verified:`** for `ka/governance/` in `docs/protected.md`, same commit.
- **Protected-code touched:** ⚠️ `ka/governance/` (Inv. 3) — `decide` CHANGE_SCOPE branch; shared dependency
  `GovernanceDecision` in `ka/model.py`.

### Phase 4 - Documentation and ledgers

- `docs/architecture/knowledge-acquisition.md` §10: record step 1 as built with `path:line`, keep step 2 as Q4.
- `README.md` quick start: the token paste; `docs/trackers/RESEARCH-TRACKER.md`: R4/R5/R6 rows → IMPLEMENTED at the end of `implement`.
- **Protected-code touched:** none

## Code blocks (B1..B8)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/security.py` | access policy dependency, loopback detection, URL safety classifier and safe fetch |
| B2 | `ka/config.py` | the four new declared settings |
| B3 | `ka/api.py` | router dependency, upload caps, `widen_visibility` on decision/apply/promotion bodies |
| B4 | `ka/ingestion.py` | `link()` through `safe_fetch`, blocked-source recording |
| B5 | `ka/research.py` | Internet agent skips unsafe URLs |
| B6 | `ka/governance.py` | CHANGE_SCOPE visibility rule and decision record |
| B7 | `ka/promotion.py` | promotion visibility rule |
| B8 | `ka/console/app.js` | token field, Authorization header, 401 toast, widen checkbox |

(`ka/model.py` and `ka/vocab.py` gain one field and one function each — declared as D4/D5 below, inside B6's change set.)

## Deliverables (D1..D10)

| # | Deliverable | File | Phase |
|---|---|---|---|
| D1 | `require_access` dependency and `peer_is_loopback` | `ka/security.py` | 1 |
| D2 | settings `KA_ACCESS_POLICY`, `KA_ACCESS_TOKEN`, `KA_MAX_UPLOAD_MB`, `KA_URL_ALLOWLIST` | `ka/config.py` | 1 |
| D3 | router-level dependency; console token field + header | `ka/api.py`, `ka/console/app.js` | 1 |
| D4 | `is_safe_url`, `safe_fetch` | `ka/security.py` | 2 |
| D5 | `link()` records blocked sources; Internet agent skips them | `ka/ingestion.py`, `ka/research.py` | 2 |
| D6 | 413 on oversize upload (both upload routes) | `ka/api.py` | 2 |
| D7 | `required_visibility(scope_type)` | `ka/vocab.py` | 3 |
| D8 | `GovernanceDecision.visibility_change`; `decide(..., widen_visibility=)` rule | `ka/model.py`, `ka/governance.py` | 3 |
| D9 | `PromotionService.decide(..., widen_visibility=)` rule | `ka/promotion.py` | 3 |
| D10 | architecture §10 step 1 recorded as built; protected.md Verified date | `docs/architecture/knowledge-acquisition.md`, `docs/protected.md` | 4 |

**Total deliverables: 10.**

## Positive Test Cases (P1..P9)

- **P1** — loopback peer with no token reaches `/healthz` under policy `token`.
- **P2** — non-loopback peer with the correct bearer token reaches `/scopes`.
- **P3** — policy `open` admits a non-loopback peer without a token.
- **P4** — an upload one byte under the cap is accepted and extracted.
- **P5** — `is_safe_url` accepts `https://example.com/doc` (resolver patched to a public address) and an allow-listed intranet host.
- **P6** — characterization: CHANGE_SCOPE INSTANCE→DOMAIN of an ENTERPRISE-visibility candidate re-creates it with ENTERPRISE visibility (today's behaviour, pinned before the change).
- **P7** — characterization: promotion of three ENTERPRISE instance nuggets yields a domain candidate with ENTERPRISE visibility.
- **P8** — CHANGE_SCOPE between two INSTANCE scopes leaves a PERSONAL candidate's visibility PERSONAL.
- **P9** — CHANGE_SCOPE of a PERSONAL candidate to DOMAIN with `widen_visibility=True` succeeds, the new candidate is DOMAIN-visible, and the decision records `visibility_change={"from":"PERSONAL","to":"DOMAIN"}`.

## Negative Test Cases (N1..N9)

- **N1** — non-loopback peer, no token → 401 with `WWW-Authenticate: Bearer`; policy `token`, token configured.
- **N2** — non-loopback peer, wrong token → 401; policy `token` with NO token configured → 401 (fail closed).
- **N3** — policy `loopback`: non-loopback peer with a correct token → 403.
- **N4** — CHANGE_SCOPE by a research agent id is still refused (`GovernanceError`), before and after the change.
- **N5** — upload over the cap → 413, and no source is created; Content-Length over the cap is refused before the body is read.
- **N6** — `link()` to `http://127.0.0.1:8011/`, `http://169.254.169.254/`, `http://10.0.0.5/`, `file:///etc/passwd` and a host resolving to a private address is never fetched; the source exists with `FAILED` and note `blocked: …`; the Internet agent records the reason in `run.errors`.
- **N7** — regression gate: every test in `test_plan01_phase2_governance.py`, `test_plan01_phase6_propagation.py` and `test_plan01_api_console.py` passes UNMODIFIED after Phase 3.
- **N8** — CHANGE_SCOPE of a PERSONAL candidate to DOMAIN without `widen_visibility` → `GovernanceError` naming PERSONAL→DOMAIN; the candidate stays PENDING_REVIEW; no new candidate exists.
- **N9** — promotion whose lead nugget is TEAM-visible, approved without `widen_visibility` → refused; the proposal stays PROPOSED.

## Plan totals

**Research points covered: 3 of 16 · Deliverables: 10 · Positive cases: 9 · Negative cases: 9 · Test cases total: 18 ·
Product tests served: 2 of 8 (2 turn green here).**

## Implementation Notes

- Phase 3's characterization (P6, P7, P8, N4) lands in its own commit before any governance change, per the protocol.
- Testing non-loopback peers: `TestClient(app, client=("203.0.113.9", 12345))` sets `request.client.host`; loopback is the
  default `testclient` host — use `("127.0.0.1", 1)` explicitly for P1.
- Testing the URL guard without network: patch `ka.security._resolve` to return chosen addresses.
- The live server on this host must be restarted after Phase 1 and a token written to `.env`; the report states the token.
