# Implementation report — KA, NEXOS integration v1

2026-10-11 · `pankajkamble75/ka` · plan [`plan-34`](../../implementation-plans/plan-34.md) on top of research-05 (plans 29–33, 12/12 shipped).
Only this repository was changed. No other repository, no Enterprise OS directory and no PROD was touched. The KA DEV service on
`srv1886827` was restarted onto this repository's code.

## What already existed and was reused

Nearly all of KA's NEXOS role was already built and verified in plans 29–33 (research-05):

- the `agentx-services/v1` surface (`ka/agentx/`): seven capabilities, durable operations, idempotency, AgentX's error envelope,
  `awaiting_input` interactions with AgentX's UiSchema, `/v1/tasks`, push registration and callbacks through KA's outbox, and `/v1/events`;
- Knowledge Worker over HTTP (`ka/knowledge_worker/`, `KnowledgeWorkerHTTPAdapter`), aligned with KW's `knowledge-worker/v1` envelope and
  its real graph-versions shape;
- the real Data Platform `/v1` (`ka/data_platform/v1.py`);
- the governance pipeline, versioned nuggets, the wiki, provenance and the specialist console (unchanged).

It wasn't rewritten to match the mockup. The mockup's six screens map onto the existing console screens instead.

## What was missing and is now built (plan-34)

| # | change | why (NEXOS) | files |
|---|---|---|---|
| 1 | **Only actually available capabilities.** With no Knowledge Worker attached, `knowledge.publish` is omitted from `/v1/capabilities` and from push registration (so AgentX deactivates it), listed with its reason in `/healthz` `checks.capabilities_unavailable`, and refused on invoke with `{"error":{"code":"unavailable","retryable":false}}` (503) | requirements §3 | `ka/agentx/availability.py`, `ka/agentx/router.py`, `ka/service.py` |
| 2 | **Screen manifest.** `GET /v1/screens` in KW's exact shape, ids `ka.sources`, `ka.research`, `ka.wiki`, `ka.nuggets`, `ka.reviews`, `ka.publications`, each pointing at an EXISTING console route; `KA_PUBLIC_BASE_URL` sets the host AgentX launches | requirements §5 (preserve the specialist UI; AgentX links) | `ka/agentx/screens.py` |
| 3 | **`/healthz` accepts AgentX's token.** Found by the live probe: AgentX's token got 401 from another host. AgentX's token opens `/healthz` and nothing else of the console API | blueprint (health per service), G0/G1 | `ka/api.py` |
| 4 | **Dedicated AgentX token** `KA_AGENTX_TOKEN` in the gitignored `.env`, separate from the console admin token | least privilege | `.env` (not committed) |
| 5 | **Evidence tooling.** `tools/nexos_evidence.py` (live conformance probe that writes `api-matrix.md`) and `tools/nexos_screenshots.py` (real screenshots of the screens the manifest lists) | AGENT-INSTRUCTIONS step 6 | `tools/` |
| 6 | Suite default `KA_AGENTX_LOCAL_PUBLISH=1` in a repository-level `conftest.py`, because `ka/tests/conftest.py` is pinned by plan-28's gate. The suite publishes to the in-memory graph on purpose; plan-34's tests turn it off | — | `conftest.py` |

## Coordination with AgentX (2026-10-11)

- **G0:** AgentX recorded KA as `pankajkamble75/ka@295f185` on `srv1886827:8011`, unreachable from `srv2050509` until an operator adds
  WireGuard or a TLS endpoint. It will show KA as "unavailable/unverified" until then and won't use insecure remote calls.
- **Unavailable capabilities:** AgentX confirmed the shape: omit from discovery and push, `checks.capabilities_unavailable`, and invoke →
  `unavailable`.
- **Screens:** AgentX asked for KW's manifest shape and the six ids. Done.
- **Publish duration:** earlier, AgentX raised its per-run deadline to cover KA's 7-day `knowledge.publish` operation timeout (AgentX
  `af6f08b`).

## NEXOS gates — KA's part

| gate | KA's part | state | evidence |
|---|---|---|---|
| G0 | source SHA, port, health, auth, active KA location | ✅ PASS | [`source-audit.md`](source-audit.md) |
| G0 | reachable from AgentX's VPS | ⛔ **BLOCKED**: no private network or TLS between `srv1886827` and `srv2050509` | source-audit, Known gaps |
| G1 | contract and schema conformance (`agentx-services/v1`) | ✅ PASS, 15/15 on the live service | [`api-matrix.md`](api-matrix.md) |
| G2 | real AgentX → KA routing ("KA conditional") | ⛔ BLOCKED (network); verified with a MOCK AgentX over HTTP, 11/11 | [`test-results.md`](test-results.md) row 6 |
| G2 | KA → DP | ✅ PASS against the REAL Data Platform (8/8) | row 5 |
| G3 | approval enforced, traceable execution | ✅ KA side: approval only by a named person through `decide`; agents and anonymous callers refused; lineage on every graph op; events with ids. Live end-to-end with real AgentX: BLOCKED | rows 2, 6 |
| G4 | restart recovery | ✅ PASS on the live service | row 4 |
| G4 | repeat/reuse | ✅ idempotent invoke replay (live, api-matrix row 6) | |
| G4 | tenant isolation | ◐ single tenant (`KA_TENANT_ID`); a mismatched tenant in input is refused (plan-29); no multi-tenant run | |
| G4 | two-VPS communication | ⛔ BLOCKED (network) | |

## To unblock (operator decisions, not code)

1. **Network between the VPSes.** Either WireGuard between `srv1886827` and `srv2050509` (KA then binds to the private address), or a TLS
   reverse proxy with a certificate in front of `:8011`. Then set `KA_PUBLIC_BASE_URL` to that origin.
2. **AgentX's token.** Copy `KA_AGENTX_TOKEN` from `/root/ka/.env` into AgentX's `AGENTX_KNOWLEDGE_ACQUISITION_TOKEN`, and point
   `AGENTX_KNOWLEDGE_ACQUISITION_URL` at `https://<ka-origin>/api/knowledge-acquisition`.
3. **Knowledge Worker.** Make KW reachable from this host the same way, put KW's token for KA in `.env` as `KA_KW_TOKEN`, and set
   `KA_KW_URL` and `KA_GRAMMAR_URL`. KW's DEV setting `KW_HOTL_MODE=auto` applies KA's changes at once and pushes them to its `graphs/dev`
   branch; choose `human` to hold them for a person. After a restart, `knowledge.publish` reappears in `/v1/capabilities` automatically.
4. Optional: `KA_STORAGE_BACKEND=data_platform` once a Data Platform runs on this host's `:8100`.

Then rerun `tools/nexos_evidence.py` with `--public https://<ka-origin>` for the cross-host G2/G4 evidence.
