# [block plan-33]
"""research-05 R6: the note's event vocabulary as a READ of KA's one event log (`ka/repository.py` events outbox, plan-09) — no second log.
Each v1 event keeps KA's `event_id` (stable across replays, so a consumer de-duplicates by it), its `seq` (replay with `after=`), a schema
version and provenance naming the KA event it came from. Events outside the map stay in `/events` only."""
from __future__ import annotations

from typing import Any

from ka import __version__, config

SCHEMA = "ka.v1"
V1_NAMES = {
    "knowledge.acquisition.completed": "knowledge.acquisition.completed",
    "knowledge.candidate.created": "knowledge.review.required",
    "correction.submitted": "knowledge.revision.proposed",
    "wiki.draft.submitted": "knowledge.revision.proposed",
    "knowledge.conflict.detected": "knowledge.conflict.detected",
    "graph.change.approved": "knowledge.publication.approved",
    "graph.change.applied": "knowledge.publication.completed",
    "wiki.published": "knowledge.publication.completed",
}
_ENVELOPE = {"event_id", "name", "at", "seq", "version"}


def to_v1(ev: dict[str, Any]) -> dict[str, Any] | None:
    t = V1_NAMES.get(ev.get("name", ""))
    if t is None:
        return None
    subject = {k: v for k, v in ev.items() if k not in _ENVELOPE}
    return {"event_id": ev.get("event_id") or f"seq-{ev['seq']}", "type": t, "schema_version": SCHEMA, "seq": ev["seq"], "occurred_at": ev.get("at"),
            "subject": subject, "provenance": {"service_id": config.get("KA_SERVICE_ID"), "source_event": ev.get("name"),
                                               "ka_version": __version__, "log_version": ev.get("version")}}


def v1_events(ka, *, after: int = 0, limit: int = 200) -> dict[str, Any]:
    raw = ka.repo.events(after=after)
    out: list[dict[str, Any]] = []
    last = after
    for ev in raw:
        last = ev["seq"]
        v = to_v1(ev)
        if v is not None:
            out.append(v)
            if len(out) >= limit:
                break
    return {"events": out, "next_after": last, "schema_version": SCHEMA}
# [/block plan-33]
