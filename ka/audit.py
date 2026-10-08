"""§41 auditability: every state-changing operation records who/what/when/why/before/after/source/scope/
approval/affected_objects. Services call `Auditor.record`; the console reads it back per object."""
from __future__ import annotations

from typing import Any

from ka.model import AuditRecord, Scope
from ka.repository import Repository


class Auditor:
    def __init__(self, repo: Repository):
        self.repo = repo

    def record(
        self,
        *,
        who: str,
        what: str,
        why: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        source: str | None = None,
        scope: Scope | None = None,
        approval: str | None = None,
        affected: list[str] | None = None,
    ) -> AuditRecord:
        rec = AuditRecord(
            who=who, what=what, why=why, before=before, after=after, source=source,
            scope=scope, approval=approval, affected_objects=affected or [],
        )
        self.repo.append_audit(rec)
        return rec

    def for_object(self, object_id: str) -> list[AuditRecord]:
        return [r for r in self.repo.audit() if object_id in r.affected_objects]
