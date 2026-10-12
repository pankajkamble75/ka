# Plan 35 - NEXOS: close KA's public plain-HTTP exposure (VPN-only bind)

Created: 2026-10-12 01:00 UTC

## Problem Description

Priority 1 of the NEXOS ChatGPT review (relayed by AgentX, approved by KA's author 2026-10-12): KA listened on `0.0.0.0:8011`, so it
answered on the public IP 2.25.98.235 over plain HTTP. WireGuard is up (`srv1886827` = 10.77.0.2, `srv2050509` = 10.77.0.1). KA must
listen only on the WireGuard address and loopback before any cross-VPS credential is used. The bind address was hard-coded
(`ka/__main__.py`).

## Architecture and decisions this plan obeys

| decision | where | state | what this plan does about it |
|---|---|---|---|
| VPN-only API listeners; preserve loopback and rollback | NEXOS architecture decisions (user, 2026-10-12, relayed) | — | **builds it** for KA |
| Operator-controlled secret transfer; no temporary receivers; never log or commit secrets | same | — | **obeyed** — a root-only file for the operator's SSH copy |
| Auth unchanged (AgentX bearer; console token from other hosts) | plan-34 | ✅ built | **constrained by it** |

**Research coverage:** none — a security directive. **Protected-code impact:** ✅ none.

## Code blocks (B1..B2)

| # | File | What the block contains |
|---|---|---|
| B1 | `ka/__main__.py` | `bind_hosts`, `_listen`; serve on each configured address |
| B2 | `ka/config.py` | `KA_BACKEND_HOST` (default `0.0.0.0`, unchanged behaviour) |

## Deliverables (D1..D4)

| # | Deliverable | File |
|---|---|---|
| D1 | `KA_BACKEND_HOST` (comma list) and multi-address serving | `ka/__main__.py`, `ka/config.py` |
| D2 | rollback procedure | `docs/user-notes/nexos-integration-v1/ROLLBACK-bind.md` |
| D3 | live verification evidence | `docs/user-notes/nexos-integration-v1/evidence/bind-vpn-only.txt` |
| D4 | handoff updated | `CHATGPT-HANDOFF.md` |

## Test cases

- **P1** — `bind_hosts` parses a list, de-duplicates, and defaults to `0.0.0.0`.
- **P2** — a real `python -m ka serve` with two addresses serves `/healthz` on both, and nothing is bound to `0.0.0.0`.
- **N1 (live)** — after the rebind, `2.25.98.235:8011` refuses connections; `10.77.0.2` with the bearer → 200, without → 401.

## Plan totals

**Deliverables: 4 · Positive cases: 2 · Negative cases: 1 (live) · Test cases total: 3.**
