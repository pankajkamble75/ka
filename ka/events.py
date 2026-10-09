"""§38 event model. In-process bus; payloads carry IDs, never content. Every event is also appended to
the repository's events.jsonl so the audit trail survives the process. Subscriber failures are logged,
never raised — an observer must not be able to break a governance step.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

from ka.ids import new_id
from ka.timeutil import now_iso

log = logging.getLogger(__name__)

EVENT_NAMES = {
    "source.ingested", "source.updated",
    "knowledge.candidate.created", "knowledge.conflict.detected", "knowledge.approved",
    "knowledge.rejected", "knowledge.superseded",
    "research.started", "research.completed",
    "correction.submitted", "correction.approved",
    "graph.impact.detected", "graph.change.proposed", "graph.change.approved",
    "graph.change.applied", "graph.change.failed",
    "graph.gap.detected", "promotion.proposed",
    # [block plan-08]
    "source.synced", "source.revoked", "source.permission_changed",
    # [/block plan-08]
    # [block plan-12]
    "graph.instance.repinned",
    # [/block plan-12]
    # [block plan-20]
    "physical.binding.available", "physical.outbox.dead",
    # [/block plan-20]
    # [block plan-21]
    "physical.event.received", "physical.binding.revoked",
    # [/block plan-21]
    # [block plan-22]
    "physical.derived.published",
    # [/block plan-22]
}

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None):
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._sink = sink
        self.history: list[dict[str, Any]] = []

    def subscribe(self, name: str, handler: Handler) -> None:
        if name != "*" and name not in EVENT_NAMES:
            raise ValueError(f"unknown event {name!r}")
        self._subs[name].append(handler)

    def emit(self, name: str, **ids: Any) -> dict[str, Any]:
        if name not in EVENT_NAMES:
            raise ValueError(f"unknown event {name!r}")
        for k, v in ids.items():
            if isinstance(v, str) and len(v) > 200:
                raise ValueError(f"event payload {k!r} looks like content, not an id (§38)")
        ev = {"event_id": new_id("event"), "name": name, "at": now_iso(), **ids}
        self.history.append(ev)
        if self._sink:
            try:
                self._sink(ev)
            except Exception:  # pragma: no cover
                log.exception("event sink failed")
        for h in self._subs.get(name, []) + self._subs.get("*", []):
            try:
                h(ev)
            except Exception:
                log.exception("event subscriber failed for %s", name)
        return ev
