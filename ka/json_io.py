"""Atomic JSON / JSONL file helpers (same shape as enterprise-os json_io / jsonl_io)."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    # A crash mid-append can leave a torn last line; start on a fresh line so the new record is never glued onto it.
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as r:
            r.seek(-1, os.SEEK_END)
            if r.read(1) != b"\n":
                line = "\n" + line
    with path.open("ab") as f:
        f.write(line.encode("utf-8"))


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # a torn line from an interrupted append; skipping it keeps every record before and after it readable
                log.warning("skipping unreadable line in %s: %.80r", path, line)
