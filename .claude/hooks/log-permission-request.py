"""Append every permission-gated tool call to a JSONL log, for later allowlist tuning.

Wired to the `PermissionRequest` hook event in `.claude/settings.json`, which fires as Claude Code decides
whether a tool call needs the user's approval. The point is the pattern, not the individual line: after a
few sessions `/permission-audit` reads this log, drops everything the allowlist already covers, and the
remainder is exactly the set of prompts that are costing the user clicks.

THIS HOOK NEVER BLOCKS. It has no opinion about whether a call should be allowed — it observes and exits 0.
Every failure path is swallowed deliberately: a logger that can break a tool call is worse than no logger.
That is also why it writes with a plain append (one `write` of one line, opened per call) rather than
holding a handle — concurrent tool calls interleave lines instead of corrupting each other.

The log is `.claude/permission-log.jsonl`, resolved relative to THIS FILE rather than the cwd, because a
hook's working directory is not guaranteed to be the project root.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "permission-log.jsonl"

# Where the interesting payload lives, per tool. Anything not listed still gets a row — with `target: null`
# — because a tool that starts prompting and is NOT in this map is itself a thing worth noticing.
TARGET_KEYS = {
    "Bash": "command",
    "PowerShell": "command",
    "Write": "file_path",
    "Edit": "file_path",
    "NotebookEdit": "notebook_path",
    "Read": "file_path",
    "WebFetch": "url",
}


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)

        tool = payload.get("tool_name") or "unknown"
        tool_input = payload.get("tool_input") or {}
        target = tool_input.get(TARGET_KEYS.get(tool, ""), None)

        row = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "target": target,
            "session": payload.get("session_id"),
            # `cwd` disambiguates a relative path or a bare command between working directories.
            "cwd": payload.get("cwd"),
        }

        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        # Deliberately silent. Anything printed on stderr here would surface as hook noise on a tool call
        # the user is already waiting on, and a logging bug must never be mistaken for a permission problem.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
