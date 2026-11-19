---
description: Draft a commit message from the staged diff in the repo's own style, and catch ticket IDs that don't match the branch
argument-hint: [extra context, e.g. "why: customer report", or a ticket ID to use]
---

Write a commit message for the current staged changes. Extra context from the user: $ARGUMENTS

Run this in the main session; it needs the working tree, not a sub-agent.

1. **Gather facts** (read-only):
   - Staged changes: `git diff --cached --stat` and `git diff --cached`. If nothing is staged, show `git status --short` and ask what to stage. Do not stage anything yourself.
   - Branch: `git rev-parse --abbrev-ref HEAD`.
   - House style from recent history: `git log -n 30 --no-merges --pretty=%s`. Look for:
     - Conventional Commits prefixes (`feat:`, `fix(scope):`),
     - the ticket position (`ABC-123: …`, `[ABC-123] …`, `… (ABC-123)`),
     - language and capitalisation,
     - typical subject length.
2. **Ticket ID**:
   - From the branch: `git rev-parse --abbrev-ref HEAD | grep -oE '[A-Za-z][A-Za-z0-9]{1,9}[-_][0-9]{2,}' | head -1 | tr 'a-z_' 'A-Z-'`. For example `abc_29170_fix` becomes `ABC-29170` and `feature/ABC-123-x` becomes `ABC-123`.
   - From the user's arguments, if they gave one.
   - **If the two differ, stop and ask which is right.** Never pick one silently.
   - If neither exists and the history shows the repo uses ticket IDs, ask for one. Otherwise continue without.
3. **Check commits not yet pushed.**
   - List them with `git log --pretty='%h %s' @{upstream}..HEAD`. If there is no upstream, use `<base>..HEAD`, where the base is `main`, `master` or `develop`.
   - Any subject carrying a different ticket ID than the branch is a mismatch. Warn and show how to fix it before pushing. For the last commit that is `git commit --amend`; for older ones, an interactive rebase that the user runs. Do not rewrite history yourself.
4. **Draft the message** in the house style:
   - **Subject**: ≤ 72 characters, imperative mood, the ticket in the house position, and what changed from the user's point of view. Not "update files".
   - **Body**, only when it adds value: why the change was needed, what changed at a high level, and any risk or follow-up. Wrap at 72 characters. Add a blank line, then trailers (e.g. `Refs: ABC-123`, `BREAKING CHANGE: …`) if the house style uses them.
   - Describe only what is in the staged diff. Never invent behaviour, tests or results.
5. **Show** the message in a code block, with one line saying which ticket ID was used and where it came from (branch, argument or history). Offer exactly one action: `git commit -F <file>`, writing the message to `.squad/tmp/commit-msg.txt` first.
6. Commit only after the user confirms. **Never push**: pushing goes through the review gate in the `squad-playbook` skill.

End with `User actions`: confirm or edit the message, plus any mismatch fix from step 3.
