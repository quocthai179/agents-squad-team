---
description: Generate a standup / status report from git activity and the .squad task board
argument-hint: [period, e.g. "since yesterday" or "this week"]
---

Launch `dev-squad:project-manager` to produce a standup report for this period: $ARGUMENTS

If no period was given, use the last 24 hours.

The brief must tell it to:
- read `.squad/TASKS.md` and recent `.squad/reports/` (if they exist),
- collect evidence with read-only git commands (`git log --since=... --stat`, `git status`, `git diff --stat`),
- update task statuses on the board only where the evidence supports it,
- output **Yesterday / Today / Blockers / Progress** with task IDs and commit references.

Show the report to the user as-is.
