"""One clock for the package so tests can pin it."""
from __future__ import annotations

from datetime import datetime, timezone

_FROZEN: datetime | None = None


def now() -> datetime:
    return _FROZEN or datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def freeze(at: datetime | None) -> None:
    """Tests only: pin the clock, or pass None to release it."""
    global _FROZEN
    _FROZEN = at


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
