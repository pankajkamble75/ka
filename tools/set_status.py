"""Derived SET STATUS table for one research report, rendered from docs/trackers/RESEARCH-TRACKER.md.

    python tools/set_status.py 01

Never hand-written: it reads the tracker rows whose Research column is `research-NN` (Active and Closed) and prints
one line per research point with its plan, state and SHA. Terminal states: UPLOADED, REJECTED, DEFERRED (user only).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TERMINAL = {"UPLOADED", "REJECTED", "DEFERRED", "HALTED"}


def render_set_status(nn: str | int, tracker: Path | None = None) -> str:
    nn = f"{int(nn):02d}"
    path = tracker or Path(__file__).resolve().parent.parent / "docs" / "trackers" / "RESEARCH-TRACKER.md"
    rows = []
    section = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|") or section not in {"Active", "Closed"}:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0] != f"research-{nn}":
            continue
        m = re.match(r"(R\d+)", cells[1])
        rows.append((m.group(1) if m else cells[1][:6], cells[1], cells[2], cells[3], cells[4], section))
    if not rows:
        return f"research-{nn}: no tracker rows"
    rows.sort(key=lambda r: int(r[0][1:]) if r[0][1:].isdigit() else 999)
    width = max(len(r[1]) for r in rows)
    out = [f"SET STATUS — research-{nn}", f"{'pt':4} {'point':{min(width, 70)}} {'plan':9} {'state':12} {'sha':9} section"]
    for pt, point, plan, state, sha, sec in rows:
        out.append(f"{pt:4} {point[:70]:{min(width, 70)}} {plan:9} {state:12} {sha:9} {sec}")
    terminal = sum(1 for r in rows if r[3] in TERMINAL or r[3].startswith("DECIDED"))   # a decide row with its answer on record is terminal
    out.append(f"{terminal}/{len(rows)} terminal" + (" — SET SHIPPED" if terminal == len(rows) else ""))
    return "\n".join(out)


if __name__ == "__main__":
    print(render_set_status(sys.argv[1] if len(sys.argv) > 1 else "01"))
