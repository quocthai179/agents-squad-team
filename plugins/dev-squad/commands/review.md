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
4. Merge into one summary for the user: overall verdict, de-duplicated findings ranked by severity with `file:line`, and a suggested fix order. **Blocking** means every `code-reviewer` 🔴 item plus every `security-auditor` finding rated Critical or High. Label them 🔴 in the summary. Show security Medium findings separately; the user decides whether they block.
5. End with the gate decision, always:
   - **READY TO PUSH**: no blocking findings, or every blocking finding has been explicitly deferred by the user.
   - **NOT READY**: list the blocking findings to fix first, then re-run the review on the new diff.

This command only reviews. It never modifies source code and never pushes or opens an MR. Offer to hand blocking findings to `dev-squad:developer`, and push only after the user confirms (see the review gate in the `squad-playbook` skill).
