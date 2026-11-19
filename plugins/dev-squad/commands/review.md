---
description: Parallel code review + security audit of the current changes, a branch/commit range, or an MR/PR (URL, !iid or #number); always writes the merged report to a fixed path
argument-hint: [MR/PR URL | !iid | #number | branch | commit range | path — defaults to current changes vs. base branch]
---

Review this target with the dev-squad: $ARGUMENTS

If no target was given, review the current uncommitted changes plus the current branch compared with its base branch.

1. Identify the exact scope first, so both reviewers get the same scope in their briefs.
   - **Local changes, branch or range**: use `git status`, `git diff --stat` and the base branch.
   - **MR/PR** (a GitHub or GitLab URL, `!123`, `#123`, or "MR 123"): get the diff and metadata read-only, using the first option that works:
     1. GitHub: `gh pr view <n> --json title,body,baseRefName,headRefName,url` and `gh pr diff <n>`, or the GitHub MCP tools.
     2. GitLab: `glab mr view <iid>` and `glab mr diff <iid>`.
     3. Plain git: `git fetch origin <source-branch> <target-branch>`, then diff `origin/<target>...origin/<source>`.

     If none of these works, ask the user for the source branch. Do not guess the diff. Never post comments, approve or merge.
2. Launch in parallel with the Agent tool:
   - `dev-squad:code-reviewer` — correctness, compatibility, performance, tests, maintainability.
   - `dev-squad:security-auditor` — vulnerabilities, secrets, access control, dependencies.
   Include in both briefs the scope and any related `.squad/requirements/` or `.squad/design/` docs.
3. Save each reviewer's report to `.squad/reports/<YYYY-MM-DD>-review-<slug>.md` and `.squad/reports/<YYYY-MM-DD>-security-<slug>.md`.
   Also **always** write the merged report (step 4) to a fixed path that later steps or other tools can rely on:
   - for an MR/PR: `.squad/reports/review-mr-<id>.md`, where `<id>` is the MR iid or PR number. Overwrite it on re-review, and keep the date inside the file.
   - otherwise: `.squad/reports/<YYYY-MM-DD>-review-merged-<slug>.md`.

   Give the path in the summary, so another step (for example a comment poster) can read it.
4. Merge into one summary for the user: overall verdict, de-duplicated findings ranked by severity with `file:line`, and a suggested fix order. **Blocking** means every `code-reviewer` 🔴 item plus every `security-auditor` finding rated Critical or High. Label them 🔴 in the summary. Show security Medium findings separately; the user decides whether they block.
5. End with the gate decision, always:
   - **READY TO PUSH**: no blocking findings, or every blocking finding has been explicitly deferred by the user.
   - **NOT READY**: list the blocking findings to fix first, then re-run the review on the new diff.

This command only reviews. It never modifies source code and never pushes or opens an MR. Offer to hand blocking findings to `dev-squad:developer`, and push only after the user confirms (see the review gate in the `squad-playbook` skill).
