"""Read the permission log, drop what the allowlist already covers, and propose the rules that would help.

The mechanical half of the `permission-audit` skill. It exists as a script rather than as instructions
because glob-vs-command matching is exactly the kind of thing that looks right when eyeballed and is wrong:
`Bash(git *)` covers `git status` but not `cd x && git status`, and a proposal built on a bad match is
worse than no proposal — it adds allowlist surface that buys nothing.

Usage:
    python .claude/skills/permission-audit/audit.py            # report
    python .claude/skills/permission-audit/audit.py --json     # same, machine-readable

It NEVER edits settings.json. Widening the allowlist is a security decision and stays the user's call;
this only tells them what the evidence says.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections import Counter
from pathlib import Path

# The Windows console is cp1252 and logged commands are arbitrary text. Without this, a single non-ASCII
# character in a command turns the whole report into a UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / ".claude" / "permission-log.jsonl"
SETTINGS = ROOT / ".claude" / "settings.json"

# The user's standing rule: prompts are for DELETION and for writes OUTSIDE the project. A candidate that
# looks like either is reported separately and never proposed — the whole point is that those keep asking.
DESTRUCTIVE = re.compile(
    r"\b(rm|rmdir|del|Remove-Item|Clear-Content|git\s+clean|git\s+reset\s+--hard|"
    r"git\s+push\s+(--force|-f)|Stop-Process|kill|truncate|shred|drop\s+table)\b",
    re.IGNORECASE,
)


def is_inside_project(path: str) -> bool:
    """True if `path` resolves under the repo root. Case-insensitive and separator-agnostic, because the
    log mixes `C:/...` and `c:\\...` forms depending on which tool produced the call."""
    try:
        p = Path(path.replace("\\", "/")).resolve()
        return str(p).lower().startswith(str(ROOT).lower())
    except (OSError, ValueError):
        return False


def shorten(path: str, keep: int = 3) -> str:
    """Last few segments — enough to recognise the file without a full absolute path per line."""
    parts = Path(path.replace("\\", "/")).parts
    return "/".join(parts[-keep:]) if len(parts) > keep else path


def load_rules() -> tuple[list[str], list[str]]:
    d = json.loads(SETTINGS.read_text(encoding="utf-8"))
    p = d.get("permissions", {})
    return p.get("allow", []), p.get("deny", [])


def parse_rule(rule: str) -> tuple[str, str | None]:
    """`Bash(git *)` -> ('Bash', 'git *');  `Read` -> ('Read', None) meaning every call of that tool."""
    m = re.fullmatch(r"([A-Za-z_]+)\((.*)\)", rule, re.DOTALL)
    return (m.group(1), m.group(2)) if m else (rule, None)


def covered_by(tool: str, target: str | None, rules: list[str]) -> str | None:
    """Return the first rule covering this call, or None. Approximates Claude Code's own matching."""
    for rule in rules:
        rtool, pat = parse_rule(rule)
        if rtool != tool:
            continue
        if pat is None:                      # tool-only rule covers every call
            return rule
        if target is None:
            continue
        if fnmatch.fnmatchcase(target, pat) or fnmatch.fnmatchcase(target, pat + "*"):
            return rule
    return None


def strip_cd(cmd: str) -> str:
    """Drop leading `cd <dir> &&` / `cd <dir>\\n` wrappers and return the command that actually runs."""
    cmd = cmd.strip()
    while True:
        m = re.match(r"^cd\s+\S+\s*(?:&&|;)?\s*(.+)$", cmd, re.DOTALL)
        if not m:
            return cmd
        cmd = m.group(1).strip()


def candidate(tool: str, target: str) -> str | None:
    """The rule that WOULD have covered this call. Conservative: a short, readable prefix, never a bare `*`."""
    if tool not in ("Bash", "PowerShell"):
        return None
    cmd = target.strip()
    # `cd somewhere && real-command`, and — far more common in practice — `cd somewhere\nreal-command`.
    # The leading cd is noise; the command after it is the thing worth a rule. Measured, not assumed: every
    # multi-line Bash call in this repo's log separates them with a newline, so a `&&`-only strip proposed
    # the useless `Bash(cd /c/Pankaj/... *)` until this was fixed.
    while True:
        m = re.match(r"^cd\s+\S+\s*(?:&&|;)?\s*(.+)$", cmd, re.DOTALL)
        if not m:
            break
        cmd = m.group(1).strip()

    # Only ever pattern on the FIRST line; a heredoc or a multi-line script body is not a prefix.
    toks = cmd.splitlines()[0].split() if cmd.splitlines() else []
    if not toks:
        return None

    def word(t: str) -> bool:
        return bool(re.fullmatch(r"[\w./\\@-]+", t)) and not t.startswith("-")

    # Two tokens is usually the right grain (`git status`, `python -c`). Three only when both following
    # tokens are plain words — so `npx vitest run` extends, while `python -c "` stops at two.
    n = 1
    if len(toks) >= 2 and word(toks[1]):
        n = 2
        if len(toks) >= 3 and word(toks[2]):
            n = 3
    elif len(toks) >= 2:
        n = 2                                   # a flag like `-c` / `-m` still belongs in the prefix
    prefix = " ".join(toks[:n])
    if not prefix or any(c in prefix for c in '"\'`\n'):
        return None                             # never emit a rule containing a quote — it would not match
    return f"{tool}({prefix} *)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not LOG.exists():
        print("No permission log yet — the hook has not recorded anything.")
        print(f"Expected at: {LOG}")
        return 0

    allow, deny = load_rules()
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # a torn line from a concurrent append; skip rather than abort

    already, uncovered, cd_defeated = Counter(), [], Counter()
    for r in rows:
        tool, target = r.get("tool", "unknown"), r.get("target")
        hit = covered_by(tool, target, allow)
        if hit:
            already[hit] += 1
            continue
        # THE BIG ONE. A command like `cd /repo\npython -c ...` is not matched by `Bash(python *)`,
        # because the rule is anchored at the start of the command string and the string starts with `cd`.
        # The allowlist looks comprehensive and still prompts. Surfacing this separately matters more than
        # any individual proposal: the fix is a habit change (or one `Bash(cd * )`-shaped decision), not
        # 40 more rules.
        if target and tool in ("Bash", "PowerShell"):
            inner = strip_cd(target)
            if inner != target.strip():
                inner_hit = covered_by(tool, inner, allow)
                if inner_hit:
                    cd_defeated[inner_hit] += 1
                    continue
        uncovered.append(r)

    proposals, skipped_destructive, no_pattern = Counter(), Counter(), Counter()
    in_project, outside = Counter(), Counter()
    for r in uncovered:
        tool, target = r.get("tool", "unknown"), r.get("target") or ""
        if DESTRUCTIVE.search(target):
            skipped_destructive[f"{tool}: {target[:70]}"] += 1
            continue
        # File tools split on the user's actual rule: writes INSIDE the project should not be costing
        # clicks; writes OUTSIDE it are supposed to keep asking. Lumping both into "no pattern" hid the
        # only distinction that matters here.
        if tool in ("Write", "Edit", "NotebookEdit", "Read") and target:
            (in_project if is_inside_project(target) else outside)[f"{tool}: {shorten(target)}"] += 1
            continue
        c = candidate(tool, target)
        if c is None:
            no_pattern[f"{tool}: {(target or '(no target)')[:70]}"] += 1
        elif covered_by(*parse_rule(c)[0:1], None, deny) or any(  # never propose over a deny rule
            parse_rule(c)[1] and parse_rule(d)[1] and parse_rule(c)[0] == parse_rule(d)[0]
            and fnmatch.fnmatchcase(parse_rule(c)[1].rstrip("* "), parse_rule(d)[1]) for d in deny
        ):
            skipped_destructive[f"{c}  (overlaps a deny rule)"] += 1
        else:
            proposals[c] += 1

    out = {
        "log": str(LOG),
        "total_recorded": len(rows),
        "already_allowed": sum(already.values()),
        "cd_prefix_defeated_rule": cd_defeated.most_common(),
        "uncovered": len(uncovered),
        "proposals": proposals.most_common(),
        "kept_prompting": skipped_destructive.most_common(),
        "file_writes_in_project": in_project.most_common(),
        "file_writes_outside_project": outside.most_common(),
        "no_pattern": no_pattern.most_common(),
        "top_existing_rules": already.most_common(8),
    }
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    print(f"Permission log: {len(rows)} calls recorded")
    print(f"  {out['already_allowed']:>4} already covered by an allow rule")
    print(f"  {sum(cd_defeated.values()):>4} would be covered BUT the command starts with `cd`")
    print(f"  {out['uncovered']:>4} NOT covered — these are what cost clicks\n")

    if cd_defeated:
        print("PROMPTED ONLY BECAUSE OF A LEADING `cd` — the rule exists and the prefix defeats it:")
        for rule, n in cd_defeated.most_common():
            print(f"  {n:>4}x  {rule}")
        print("  Fix the habit (run from the project root, or use a tool's own cwd) rather than adding")
        print("  rules — a `Bash(cd * )` rule would allow anything after the `&&` and is not the answer.\n")

    if proposals:
        print("PROPOSED allow entries (count = calls it would have covered):")
        for rule, n in proposals.most_common():
            print(f"  {n:>4}x  {rule}")
    else:
        print("No proposals — nothing uncovered that is safe to generalise.")

    if in_project:
        total = sum(in_project.values())
        print(f"\nFile edits INSIDE the project ({total} calls) — these should not be costing clicks:")
        for k, n in in_project.most_common(10):
            print(f"  {n:>4}x  {k}")

    if outside:
        print("\nFile edits OUTSIDE the project — by your standing rule these KEEP prompting:")
        for k, n in outside.most_common(10):
            print(f"  {n:>4}x  {k}")

    if skipped_destructive:
        print("\nDELIBERATELY still prompting (destructive or deny-listed — do NOT allowlist):")
        for k, n in skipped_destructive.most_common():
            print(f"  {n:>4}x  {k}")

    if no_pattern:
        print("\nUncovered, but no safe pattern inferred (decide individually):")
        for k, n in no_pattern.most_common(12):
            print(f"  {n:>4}x  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
