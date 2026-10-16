---
description: Parallel code review + security audit of the current changes (or a given target)
argument-hint: [branch | path | commit range — defaults to current changes vs. base branch]
---

Review this target with the dev-squad: $ARGUMENTS

If no target was given, review the current uncommitted changes plus the current branch compared with its base branch.

1. Identify the exact scope first (`git status`, `git diff --stat`, base branch) so both reviewers get the same scope in their briefs.
2. Launch in parallel with the Agent tool:
   - `dev-squad:code-reviewer` — correctness, compatibility, performance, tests, maintainability.
   - `dev-squad:security-auditor` — vulnerabilities, secrets, access control, dependencies.
   Include in both briefs the scope and any related `.squad/requirements/` or `.squad/design/` docs.
3. Save each report to `.squad/reports/<YYYY-MM-DD>-review-<slug>.md` and `.squad/reports/<YYYY-MM-DD>-security-<slug>.md`.
4. Merge into one summary for the user: overall verdict, de-duplicated findings ranked by severity (blocking first) with `file:line`, and a suggested fix order.

Do not modify source code in this command. Offer to hand blocking findings to `dev-squad:developer`.
