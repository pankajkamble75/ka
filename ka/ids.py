"""Readable, prefixed identifiers. `KN-983` is a canonical nugget id; `KN-983:v3` names one version."""
from __future__ import annotations

import secrets

PREFIXES = {
    "source": "SRC",
    "source_version": "SRV",
    "evidence": "EV",
    "nugget": "KN",
    "relationship": "REL",
    "decision": "GD",
    "correction": "COR",
    "mission": "RM",
    "run": "RR",
    "dependency": "DEP",
    "proposal": "GCP",
    "execution": "GCX",
    "event": "EVT",
    "audit": "AUD",
    "promotion": "PRO",
    "request": "KAR",
    "binding": "GB",
    "connection": "CON",
}


def new_id(kind: str) -> str:
    prefix = PREFIXES[kind]
    return f"{prefix}-{secrets.token_hex(4)}"


def version_ref(canonical_id: str, version: int) -> str:
    return f"{canonical_id}:v{version}"


def split_version_ref(ref: str) -> tuple[str, int]:
    canonical, _, v = ref.rpartition(":v")
    if not canonical or not v.isdigit():
        raise ValueError(f"not a version ref: {ref!r}")
    return canonical, int(v)
