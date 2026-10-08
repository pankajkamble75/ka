---
name: upload
description: Commit ALL current changes and push everything to the main branch, always writing a detailed dated checkpoint note first. Use whenever the user says "upload" (or invokes /upload) — that word alone is the trigger. Also use for phrasings like "upload it", "upload everything", "commit and push to main", or "push all to main".
---

# Upload

Commit every change in the working tree and push it to `main`, after recording a detailed checkpoint note.
The user runs this by saying **upload** (or `/upload`). Treat the bare word "upload" as an explicit request
to run this skill end to end.

## Required behavior

Do these steps in order. Do not skip the checkpoint note, and do not push to any branch other than `main`.

1. **Survey the changes.** Run `git status --short` and `git diff --stat HEAD` (and `git status -sb` for the
   branch/sync line). If the working tree is clean AND the branch is not ahead of `origin/main`, there is
   nothing to upload — say so and stop (do not write an empty checkpoint or an empty commit).

2. **Write a detailed checkpoint note (always).** Append a new dated entry to `docs/checkpoints/CHECKPOINTS.md`
   (create the directory and file if missing; newest entry at the TOP, under the title). The note is a
   record for later readers — make it genuinely detailed, not a one-liner. Each entry MUST include:
   - a heading with the local date and time (from the environment) and a short title;
   - **What changed** — the concrete edits, grouped by area, with file paths;
   - **Why** — the motivation / what problem it addresses;
   - **Verification** — tests or checks run and their result (name the suites + pass/fail counts); if nothing
     was run, say so plainly;
   - **Follow-ups / risks** — anything left open, known gaps, or things to watch;
   - **Decisions and questions** — **the field that connects this checkpoint to the architecture**, and it
     is `none` or it is filled, never absent:
     - a question the work ANSWERED → name it (`Q102`, `N19`) and the document it now lives in
       (`docs/architecture/<topic>.md` §N). **If the answer is not in that document yet, put it there
       before committing** — an answer that reaches only a checkpoint note is lost;
     - a question the work RAISED → name it and confirm it is in `docs/questions/<topic>.md`'s open block
       **and** registered in `docs/trackers/QUESTIONS-TRACKER.md`, per `implement` §4b;
     - a decision this work BUILT → say which, and confirm its state moved from `⏳ decided, not built`
       to `✅ built` with `path:line` in the architecture document. **A document still saying *not built*
       about code that just shipped is worse than no document**;
     - the **plan** this upload lands (`plan-NN`) and the **research points** it closes, so the checkpoint
       resolves to the ledgers rather than describing the diff twice.
   Derive the content from the actual diff (`git diff HEAD`, `git status`) and the work done this session —
   never invent results. Stage this note as part of the commit.

3. **Stage everything.** `git add -A` (this includes the checkpoint note). Respect `.gitignore`; never
   force-add ignored paths (e.g. `node_modules`, build output).

4. **Commit.** One commit with a clear, descriptive message summarizing the upload — mirror the checkpoint
   note's title + a short bullet summary. End the message with the two trailers this repo/session requires:
   ```
   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   Claude-Session: <the current session URL>
   ```

5. **Get onto `main` and push.** This project pushes directly to `main`.
   - If not already on `main`: `git checkout main` (or fast-forward `main` to include the current commit —
     do NOT abandon the just-made commit). If work was committed on another branch, merge/rebase it into
     `main` so the commit lands there.
   - `git pull --rebase origin main` first to avoid a non-fast-forward reject.
   - `git push -u origin main`. On network failure, retry up to 4 times with exponential backoff
     (2s, 4s, 8s, 16s). Never use `--force` unless the user explicitly asks.

6. **Render the SET STATUS table (required when the plan derives from a research report).** One research
   now routinely becomes many plans, and the author's rule (2026-08-20) is: **after every individual
   plan's upload, the whole research's standing is reconciled and shown.** The table is DERIVED, never
   hand-written — run the renderer for every research the plan's coverage names:

   ```
   /root/.venvs/enterprise-os/bin/python -c "
   from tracking.tests.test_set_status_table import render_set_status
   print(render_set_status(NN))"
   ```

   Paste its output verbatim into the chat report. If the table shows every row terminal, say so
   plainly — that is the moment the set is a candidate for `ship`'s final check; if rows remain OPEN or
   in flight, the table IS the list of what still stands.

7. **Report.** State the commit hash, that it was pushed to `origin/main`, the checkpoint file path,
   and the set-status table(s) from step 6. Keep the prose short — the detail lives in the checkpoint
   note, and the standing work lives in the table.

## Rules

- **A checkpoint names the DECISIONS, not only the diff.** If the work answered a question, built a decided
  one, or raised a new one, the checkpoint says so and the relevant document under
  `docs/architecture/` or `docs/questions/` is already updated at commit time — not afterwards, and never
  only in the note. The loop is
  [`docs/questions/how-a-question-becomes-architecture.md`](../../../docs/questions/how-a-question-becomes-architecture.md).

- **Always write the checkpoint note** — it is the point of this skill, not optional. No note ⇒ the skill
  did not run.
- **Update the tracker before committing** (`docs/trackers/RESEARCH-TRACKER.md`): the plan's row → `UPLOADED` with the
  commit SHA, moved to **Closed**. It rides along in this commit, so write it before `git add -A`. The
  checkpoint note is the narrative of what landed; the tracker is what is still open — they are different
  files on purpose and must not converge.
- **`main` only.** Never push to a different branch under this skill without explicit user permission.
- **Never fabricate verification.** If tests were not run this session, write "not run" — do not claim green.
- **Do not create a pull request** and do not change unrelated files.
- If a step genuinely fails (e.g. push rejected after retries, or a merge conflict on `main`), stop and
  report the failure with the exact error rather than forcing past it.
