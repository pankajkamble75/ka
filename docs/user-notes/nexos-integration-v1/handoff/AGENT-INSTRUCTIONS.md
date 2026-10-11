# Coding Agent Handoff — NEXOS Integration v1

**Repository:** `pankajkamble75/knowledge-acquisition`

## Read in this order
1. `docs/user-notes/nexos-integration-v1/blueprint.md` — cross-service architecture and gates.
2. `docs/user-notes/nexos-integration-v1/requirements.md` — this repository's tasks.
3. `docs/user-notes/nexos-integration-v1/ui-design/mockup.html` — navigable conceptual UI.
4. Existing repository README, API contracts, tests, runbooks and earlier Requirement V2 (where applicable).

## Assignment
First locate the authoritative KA implementation; if not found report BLOCKED with evidence, do not generate a substitute. Then implement governed KA contract and publish workflow.

## Execution sequence
1. Pull latest main and pin SHA; inventory existing functionality and **separate already-implemented from missing**. Do not rewrite working modules merely to match mockups.
2. Verify runtime on Hostinger, port and auth. Produce endpoint-by-endpoint contract matrix with real evidence. If the service runs on another VPS, use private authenticated networking, not loopback.
3. Coordinate contract changes with AgentX agent **before** implementation. Keep old compatible routes; use adapters.
4. Implement smallest end-to-end vertical slice; run unit, contract and real cross-service tests. Mock-only tests must be labeled mock.
5. Implement UI using mockup as layout reference. **Preserve existing working specialist UIs**, and AgentX must preserve 5176 Console and 5175 Demo. Never show illustrative numbers as live.
6. Save `source-audit.md`, `api-matrix.md`, `implementation-report.md`, `test-results.md`, real screenshots under `docs/user-notes/nexos-integration-v1/`. Report BLOCKED explicitly when external service is absent.
7. Commit verified changes to **this repository only**; do not modify other agents' repos, either old Enterprise OS directory, or PROD.

## Acceptance
Evidence for your assigned G0–G4 integration gates; honest service states, authenticated API conformance, traceable execution, human approval enforcement, no duplicate semantic capability registry, no fabricated completion.
