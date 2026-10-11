# [block plan-34]
"""NEXOS v1: register ONLY actually available capabilities (requirements §3). A capability whose owner service is not attached is omitted
from `/v1/capabilities` and from push registration (AgentX then deactivates it), reported in `/healthz` `checks.capabilities_unavailable`,
and refused on invoke with `unavailable` (contract agreed with the AgentX session, 2026-10-11)."""
from __future__ import annotations

from ka import config


def unavailable(ka) -> dict[str, str]:
    out: dict[str, str] = {}
    mode = getattr(ka, "graph_mode", "custom")
    if mode == "memory" and not config.get("KA_AGENTX_LOCAL_PUBLISH"):
        out["knowledge.publish"] = ("no Knowledge Worker is attached (graph mode memory): a publication would only update KA's own shadow "
                                    "graph, not propose a graph change to Knowledge Worker; set KA_KW_URL and KA_KW_TOKEN")
    return out
# [/block plan-34]
