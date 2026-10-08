---
name: permission-audit
description: Study the permission log at .claude/permission-log.jsonl and propose allowlist entries that would stop the repeated prompts. Use when the user says "permission audit", asks why they are still clicking approve so often, asks which commands should go in the allowlist, or wants to review what the PermissionRequest hook has recorded. Reports evidence and proposes rules; adding them to .claude/settings.json is the user's call.
---

# Permission Audit

Turn the recorded permission traffic into a small number of allowlist rules, so the user stops approving
the same command shapes over and over.

The user's standing rule is the yardstick for every decision here: **prompts are for deleting files and
for writing outside the project directory.** Anything else that prompts repeatedly is friction to remove,
and anything matching those two categories stays prompting no matter how often it appears.

## How the data gets there

A `PermissionRequest` hook in `.claude/settings.json` runs
`python .claude/hooks/log-permission-request.py` on every tool call, appending one JSON line to
`.claude/permission-log.jsonl`.

**The hook fires on every call, not only on the ones that actually prompt** — verified by observation, not
assumed. Auto-approved calls land in the log too. That is why the analysis is built around subtracting
what the allowlist already covers: the uncovered remainder is the set that is (or would be) costing
clicks. Never present a raw log count as "prompts the user answered" — it is not that number.

## Running it

```
python .claude/skills/permission-audit/audit.py            # the report
python .claude/skills/permission-audit/audit.py --json     # same, machine-readable
```

The script does the matching, deliberately — `Bash(git *)` covers `git status` but not `cd x && git
status`, and a proposal built on a bad match adds allowlist surface that buys nothing. Do not eyeball the
globs yourself; run the script and read what it found.

### The finding to look for first

**`PROMPTED ONLY BECAUSE OF A LEADING cd`.** An allow rule is anchored at the start of the command string,
so `Bash(python *)` does not match `cd /repo` + newline + `python -c ...`. The allowlist can look
comprehensive — 146 entries — and still prompt constantly, because so many commands are written with a
`cd` prefix.

If this bucket is large, **it is the answer**, and adding more rules is not. The fixes, in order of
preference: run from the project root and drop the `cd`; use a tool's own working-directory support; or,
last and least, accept that those specific calls prompt. Do **not** propose `Bash(cd * )` — it would allow
anything at all after the `&&`, which is a far bigger grant than the prompts it removes.

It sorts everything else uncovered into four buckets:

| Bucket | What it means | What to do |
|---|---|---|
| **Proposed allow entries** | A safe command prefix, with the number of calls it would have covered | The candidates. Rank by count. |
| **File edits inside the project** | `Write`/`Edit` under the repo root | Should not be prompting at all — the standing rule says so. |
| **File edits outside the project** | Everything else | Leave prompting. This is the rule working. |
| **Still prompting deliberately** | Destructive, or overlapping a deny rule | **Never** propose these. Say plainly that they are excluded. |

## Reading the result honestly

- **A high count is evidence, not a decision.** `47x Bash(python -c *)` says the shape is common; whether
  it should be blanket-allowed is still a judgement about what `python -c` can do.
- **Prefer few, specific rules over many broad ones.** One `Bash(npx vitest *)` beats six variants. But a
  rule so broad it swallows unrelated commands is worse than the prompts it removes.
- **Never propose a rule that overlaps the deny list.** The script filters these, but say out loud when it
  did, so a reader can see the deny list held rather than assuming nothing matched.
- **Say how much data you have.** Proposals from 12 recorded calls are a hint; from 400 they are a
  pattern. Report the total.

## Applying the proposals

Adding to `.claude/settings.json` is a security decision and stays the user's call — propose, then apply
what they accept.

When they do accept, the project convention (see the `update-config` skill) is:

1. **Read** `.claude/settings.json` first.
2. **Merge** into the existing `permissions.allow` array — never replace it. It currently holds ~144
   entries and a clobbered allowlist is a bad afternoon.
3. **Validate** the JSON after writing, and confirm the allow/deny counts moved by exactly what you added.
4. Note that the user's phrasing "allow X" is itself an instruction to persist the pattern into
   `.claude/settings.json`, not merely to approve one call.

## Maintenance

The log grows without bound. It is plain JSONL — truncating it after a round of allowlist tuning is
normal and starts a clean measurement window. Say when you truncate it and why; do not do it silently,
because the counts are the evidence for the last set of proposals.

## Rules

- **Never edit `settings.json` from this skill without the user agreeing to the specific entries.**
- **Never propose a destructive or deny-listed pattern**, however often it appears.
- **Never report the raw log count as the number of prompts answered** — the hook records more than that.
- Run the script rather than reasoning about glob matching by hand.
