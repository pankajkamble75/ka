# [block plan-34]
"""NEXOS v1 screen manifest (requirements §5: preserve the specialist nugget/wiki UI; AgentX links or embeds, never duplicates). The shape is
Knowledge Worker's, so one AgentX reader serves every service (AgentX session, 2026-10-11). Every screen is an EXISTING console route; the
six ids follow the NEXOS mockup's six screens. `embed_url` is null: KA does not yet send `frame-ancestors` for AgentX's origins."""
from __future__ import annotations

from typing import Any

from ka import config

SCREENS = [
    ("ka.sources", "Sources", "/console/#/add", [], ["knowledge.acquire"],
     "Add sources (upload, paste, note, link, connectors); each source's versions, provenance and evidence at #/source/{source_id}."),
    ("ka.research", "Research", "/console/#/add", ["mission_id"], ["knowledge.acquire"],
     "Start a research mission for a knowledge gap; a mission's runs, sources and candidates at #/mission/{mission_id}."),
    ("ka.wiki", "Knowledge Wiki", "/console/#/wiki", ["page_key"], ["knowledge.read"],
     "Readable articles computed from governed nuggets; edits become governance proposals."),
    ("ka.nuggets", "Nuggets", "/console/#/nuggets?view=active", ["nugget_ref"], ["knowledge.read"],
     "Governed knowledge nuggets with versions, lineage and provenance; one nugget at #/nugget/{nugget_ref}."),
    ("ka.reviews", "Reviews", "/console/#/nuggets?view=pending", ["nugget_ref"], ["knowledge.review"],
     "Candidates waiting for a person; conflicts at #/nuggets?view=conflicts and #/conflict/{nugget_ref}."),
    ("ka.publications", "Publications", "/console/#/nuggets?view=active", ["proposal_id"], ["knowledge.publish"],
     "Approved knowledge and its graph change proposals; one proposal at #/change/{proposal_id}. No dedicated list screen yet."),
]


def manifest(base_url: str) -> dict[str, Any]:
    base = (config.get("KA_PUBLIC_BASE_URL") or base_url).rstrip("/")
    return {"screens": [{"id": i, "title": t, "path": p, "launch_url": base + p, "embed_url": None, "deep_link_params": d, "requires": r,
                         "provided_by": config.get("KA_SERVICE_ID"), "description": desc} for i, t, p, d, r, desc in SCREENS]}
# [/block plan-34]
