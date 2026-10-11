# Test results — KA, NEXOS integration v1

Every row says what the counterpart was: **REAL** (the actual service), **LIVE** (KA's own running DEV service), or **MOCK** (a wire-level
stand-in that follows the counterpart's published contract). Taken 2026-10-11 on `srv1886827`.

| # | suite or run | counterpart | result | evidence |
|---|---|---|---|---|
| 1 | full unit and contract suite (stub LLM, in-memory graph; the three suites that need an Enterprise OS checkout are excluded) | in-process | **499 passed, 2 skipped** | [`evidence/suite.txt`](evidence/suite.txt) |
| 2 | plan-34 tests: availability, screens, journey, duplicate, missing DP, rejected, conflict, healthz auth | in-process, MOCK KW in N4 | **12/12** | [`evidence/plan34-tests.txt`](evidence/plan34-tests.txt) |
| 3 | API conformance of the RUNNING KA against AgentX's `agentx-services/v1` schemas, read-only invocations | **LIVE** KA, real HTTP, loopback and public IP | **15/15** (first run 14/15; see below) | [`api-matrix.md`](api-matrix.md), `evidence/live-*.json` |
| 4 | restart recovery: an operation created before a service restart is served after it | **LIVE** KA | **PASS** (`AXO-8de82d44`, created 20:13:43, restart 20:14:52) | [`evidence/restart-recovery.json`](evidence/restart-recovery.json) |
| 5 | KA ↔ Data Platform: upload commits, knowledge binding, read back, nugget as a derived asset with its parent | **REAL** Data Platform `d5eefbd`, started on :8110 with a fresh root, then stopped | **8/8** | [`evidence/dp-real.txt`](evidence/dp-real.txt) |
| 6 | two-process journey: registration push, acquire and callback, review by a named person (anonymous refused), publish after KW applies, events replay | MOCK AgentX + MOCK KW over real HTTP; KA a separate process with no EOS checkout | **11/11** | [`evidence/two-process-mock-peers.txt`](evidence/two-process-mock-peers.txt) |
| 7 | publication confirmed by KW: running until KW applies, one proposal, lineage on every op | MOCK KW over real HTTP | **7/7** | [`evidence/kw-publish-mock-kw.txt`](evidence/kw-publish-mock-kw.txt) |
| 8 | real LLM: extraction through `/v1` on the real Anthropic key | **REAL** Anthropic | **12/12** (2026-10-11, run `FLOW_LIVE_LLM=1 e2e/plan33_two_process_flow.py`) | commit `b3ecb78` |
| 9 | real research: Brave search (1 query, 2 pages) plus Claude, 58 candidates, all PENDING_REVIEW | **REAL** Anthropic + Brave | **PASS** (2026-10-11, `e2e/live_keys_research_flow.py`) | commit `295f185` |
| 10 | real screenshots of the six specialist screens from the running service | **LIVE** KA console | **6/6 rendered, 0 JS errors** | [`screenshots/index.md`](screenshots/index.md) |

## NEXOS requirement 6 scenarios

| scenario | test | result |
|---|---|---|
| acquisition → human review → approved publication → KW proposal | plan-34 P4 (MOCK KW); two-process flow (MOCK peers) | PASS |
| "visible process knowledge improvement" in KW | — | **NOT VERIFIED.** It needs the real KW, which is unreachable from this host |
| rejected change | plan-34 N4: REJECTED, no graph change proposal, no publication event | PASS |
| conflicting versions | plan-34 N5: resolve_conflict waits for a person, and an answer with no person is refused | PASS |
| duplicate event | plan-34 P5: the same Idempotency-Key gives the same operation; replay keeps `event_id`s | PASS |
| missing Data Platform | plan-34 P6: DP unreachable → upload `pending`, bytes spooled, outbox retry, never `available` | PASS |

## What the live probe caught

The first live conformance run failed one check: AgentX's token got **401 on `/healthz` over the public interface**. `/healthz` sat behind
the console's admin-token check. AgentX polls `{base}/healthz`, so from its host KA would always have looked down. The fix (plan-34) puts
`/healthz` on its own router that accepts AgentX's token, and that token opens nothing else (test N6). The second run passed 15/15. Both
evidence files are kept.

## Not run, and why

- **Real AgentX → KA, and KA → real Knowledge Worker:** different VPS, no private network or TLS. BLOCKED (see
  [`implementation-report.md`](implementation-report.md)).
- **Enterprise OS adapter suites** (`test_plan01`, `test_plan05_eos_publication`, `test_plan12_eos_repin`): they need the archived Enterprise
  OS checkout, which NEXOS says not to depend on.
