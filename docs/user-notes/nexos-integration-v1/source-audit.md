# Source audit — the active Knowledge Acquisition (NEXOS v1, G0)

**Result: FOUND and VERIFIED RUNNING.** The NEXOS blueprint marks KA "BLOCKED: locate actual KA source". It isn't blocked: the active KA is
**`pankajkamble75/ka`** (this repository). The author decided this on 2026-10-10 (research-05 R1).
`pankajkamble75/knowledge-acquisition` holds only the requirements notes: its README scaffold, the AgentX requirements note and this NEXOS
handoff (copied to [`handoff/`](handoff/)). `knowledge-acquisition-2` is not the active source; nothing in this audit depends on it.

Audit taken 2026-10-11 on `srv1886827` (public IP 2.25.98.235, Hostinger DEV).

## Source

| item | value | evidence |
|---|---|---|
| repository | `pankajkamble75/ka`, branch `main` | `git remote -v` |
| code SHA | `295f185` before this work; plan-34's commit after it | `git rev-parse` |
| history | plans 01–34 since 2026-10-08 (`7d9504c`) | `docs/implementation-plans/`, `docs/checkpoints/CHECKPOINTS.md` |
| language / stack | Python 3.11, FastAPI, file-per-object JSON storage | `pyproject.toml`, `ka/repository.py` |
| modules | 44 in `ka/`, plus `ka/agentx/`, `ka/knowledge_worker/`, `ka/data_platform/`, `ka/connectors/`, `ka/console/` | `ls ka` |
| HTTP routes | 102 console/API routes plus 17 service routes (`/v1/*`, `/healthz`) | `ka/api.py`, [`../../integration/openapi-v1.json`](../../integration/openapi-v1.json) |
| tests | 46 test files; 499 passed, 2 skipped (stub LLM, in-memory graph) | [`evidence/suite.txt`](evidence/suite.txt) |
| live flows | 31 scripts under `e2e/` | `ls e2e` |
| inventory and ownership map | [`../../integration/source-inventory.md`](../../integration/source-inventory.md) | |

## Runtime

| item | value | evidence |
|---|---|---|
| process | systemd unit `enterprise-os-ka`, `python -m ka serve` from `/root/ka` with `/root/ka/.env` | `systemctl show enterprise-os-ka` |
| bind | `0.0.0.0:8011`, prefix `/api/knowledge-acquisition` | `ss -ltnp` |
| health | `GET /healthz` → `status: ok`, `checks: storage ok, provider anthropic, grammar ok, graph memory`, `capabilities_unavailable: {knowledge.publish: …}` | [`api-matrix.md`](api-matrix.md) row 1 |
| auth (console) | `KA_ACCESS_POLICY=token`: callers on this machine pass; any other host needs `KA_ACCESS_TOKEN` (verified 401 without, 200 with, via the public IP) | api-matrix rows 10, 15 |
| auth (AgentX) | `KA_AGENTX_TOKEN`, a dedicated token added 2026-10-11 and separate from the console token, required on every `/v1` call and accepted on `/healthz` | api-matrix rows 2–14 |
| store (DEV) | `ka_storage/`: 998 nuggets (51 ACTIVE, 927 PENDING_REVIEW, 17 REJECTED, 3 OBSOLETE), 66 sources | `GET /nuggets`, `GET /sources` |
| LLM | Anthropic (real key, verified 2026-10-11) | `/healthz` `checks.provider` |
| bytes | local storage; the real Data Platform `/v1` client is built and verified (8/8) but not enabled on the live service | [`evidence/dp-real.txt`](evidence/dp-real.txt) |
| graph | `memory`: no Knowledge Worker reachable from this host, so `knowledge.publish` is not advertised | api-matrix row 14 |

**Was it running stale code?** Yes, until today. The service had been up since 2026-10-09 10:39 UTC on pre-`/v1` code, so AgentX never saw
`/v1`. It was restarted on current code at 20:08, 20:13 and 20:14 UTC on 2026-10-11. `ka_storage` was backed up first to
`/root/ka-storage-backup-20261011T200721Z.tgz`, outside the repository.

## What is implemented and what is missing

| NEXOS requirement (requirements.md) | state | where |
|---|---|---|
| 1. source audit | ✅ this document | |
| 2. `agentx-services/v1`: health, discovery, invoke, status, input, cancel, typed errors, idempotency | ✅ built (plans 29–30); verified live, 15/15 checks against AgentX's schemas | `ka/agentx/`, [`api-matrix.md`](api-matrix.md) |
| 3. register search, acquire, review, revise, publish, conflict resolution, **only if actually available**; durable operation ids | ✅ seven capabilities; publish omitted while no Knowledge Worker is attached (plan-34); acquisition and research return durable `AXO-…` ids | `ka/agentx/availability.py` |
| 4. Data Platform for bytes; Knowledge Worker graph-change proposals with lineage | ✅ built and verified (DP real, 8/8; KW against its contract fake). ⛔ live KW not reachable from this host | plans 31–32 |
| 5. KA work in AgentX Growth and Human Tasks; preserve specialist UI, AgentX links | ✅ `/v1/tasks`, review interactions, `/v1/events`; `/v1/screens` in KW's manifest shape → the existing console (6 screens, real screenshots) | plan-34, [`screenshots/`](screenshots/index.md) |
| 6. acquisition → review → publication → KW proposal → visible improvement; rejected, conflicting, duplicate event, missing DP | ✅ tested; the KW step against a **mock** KW only. "Visible process improvement" in KW is not verifiable from here | [`test-results.md`](test-results.md) |

## Known gaps (honest)

- **Cross-VPS reachability (BLOCKED).** AgentX runs on `srv2050509` (179.236.69.69). There is no private network between the hosts, KA
  serves plain HTTP only, and AgentX rightly refuses insecure remote calls. An operator must add WireGuard between the VPSes or a TLS
  endpoint in front of KA's port 8011.
- **Knowledge Worker (BLOCKED from this host).** KW's intake is live on its own host (`pankajkamble75/knowledge-worker@064bdf4`), but it is
  not reachable from here and its token isn't on this host. The live KA stays in `memory` graph mode, with publish honestly unavailable.
- **DEV data hygiene.** The live store holds leftover records from earlier end-to-end runs against the live service, such as wiki
  processes named `Repin process flow…` and `Web onboarding flow…`, plus 927 pending candidates, most of them research output. They are
  real DEV data, not fabricated, but they are noise for a demo.
- **Publications screen.** There is no dedicated list of graph change proposals yet; `ka.publications` opens the active-nuggets view, and
  one proposal opens at `#/change/{id}`.
- **Embedding.** `embed_url` is `null`: KA doesn't yet send `frame-ancestors` for AgentX's origins, so AgentX links rather than embeds.
