# NEXOS — Five-Service Development Blueprint v1

**Environment:** Hostinger DEV across two VPS machines. **No GCP/PROD work.** **Orchestrator:** AgentX.

## Repository review snapshot (2026-10-11)
| Service | Verified from GitHub | Integration status |
|---|---|---|
| AgentX | Independent frontend/backend, execution graph, service registry, mock end-to-end, ports 8765 / Console 5176 / Demo 5175 | Real multi-service flow not yet verified |
| Knowledge Worker | V2 graphs, Pipeline C, eight-screen UI on 5177, API 8101 | Contract exists; live AgentX path to verify |
| Knowledge Acquisition | Main branch only scaffold README; another repo knowledge-acquisition-2 exists | **BLOCKED: locate actual KA source** |
| Data Platform | Local JSON/CSV storage, API 8100, AgentX adapter with 14 declared capabilities | Live AgentX conformance to verify |
| final-sdlc | Herdr/Claude controller, FastAPI 8020, approval-gated builds, signed app registration | Live build-and-registration to verify |

The above are repository/document observations, not proof that all services are currently running together.

## Architecture

```
USER → AgentX NEXOS Shell / Execution Graph / Human Tasks
              │
              ├─ Knowledge Worker: Process Graph, Pipeline C, readiness
              ├─ Knowledge Acquisition: governed knowledge (source unverified)
              ├─ Data Platform: connectors, mapping, data, queries
              ├─ final-sdlc: verified build, approval, deploy
              └─ Operational Applications: executable business work + UI schema
                  ↑ outcomes and evidence → AgentX → governed process readiness
```

**Semantic capability truth** lives in the Knowledge Worker Process Graph. AgentX's technical registry only stores endpoint/schema/permission/health and executable bindings. No second business-capability ontology.

## Common integration contract
- Adopt AgentX `docs/contracts/agentx-services-v1.md` for technical capability calls. Respect KW's `knowledge-worker/v1` envelope and DP's existing `/agentx` prefix; use adapters rather than breaking rewrites.
- Every service publishes health, capability manifest, invoke, operation polling, input/cancel where relevant, JSON Schemas, permissions and typed errors.
- Use correlation, run/step, tenant/user, instance/process, graph digest, operation and artifact IDs consistently. Preserve provenance and stable references.
- Long tasks return durable operation IDs; approval requests become AgentX Human Tasks; success is confirmed only by the owner service.
- Authenticated service calls, least-privilege scopes, idempotency and retries; cross-VPS communication via private authenticated network. Never use localhost to reach a different VPS.
- Business process execution binding: process ID + instance ID + graph digest → deployed app capability/version + evidence + approval status. KW governs graph changes; SDLC deployment is not an automatic graph edit.
- Gap classes: missing graph/process knowledge, missing data, missing operational app, missing human input, or ready. No blanket build for every question.

## First integration journey: Coffee shop menu pricing
1. User: "Help me manage profitable drink prices and give me a usable pricing workflow."
2. AgentX asks KW to find the process and return grounded process slots and missing requirements.
3. Data Platform assesses available menu, ingredient, labor and sales data by logical IDs. Missing sources trigger governed connector/mapping tasks.
4. KA acquires/reviews missing process knowledge if actually available; otherwise display blocked/unavailable, not pretend success.
5. When an ongoing workflow/human input is needed and no app exists, AgentX commissions final-sdlc with a bounded spec, tests and approval gate.
6. final-sdlc verifies, receives human release approval, deploys and registers via signed callback or pull. AgentX validates and shows the app in My Applications.
7. User runs the app; it confirms results. AgentX records outcome and asks KW to govern process implementation readiness.
8. Repeat request: reuse capability rather than rebuild. Test denial, unavailable service and stale graph digest.

## Development gates
G0: source SHAs, ports, health, auth and active KA location.
G1: cross-service contract/schema conformance.
G2: real AgentX→KW routing, AgentX→DP data assessment, AgentX→SDLC job request; KA conditional.
G3: end-to-end approval, deployment, app registration, launch and audit.
G4: repeat/reuse, restart recovery, tenant isolation and two-VPS communication.

## NEXOS UI ownership
AgentX shell: Workspace, My Business, Operations, My Applications, Growth, Human Tasks, Services. Preserve Console 5176 and Demo 5175 **unchanged**. KW keeps eight V2 specialist screens at 5177, exposed via screen manifest. Other services retain their own specialist/admin tools, linked from AgentX.

## Delivery rules
Each agent changes **only its own repository** and commits tests/evidence under `docs/user-notes/nexos-integration-v1/`. Contract changes require coordination and compatible versions. No changes to archived Enterprise OS or PROD. No claimed integration success without real HTTP evidence.
