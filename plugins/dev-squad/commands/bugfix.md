---
description: Bug pipeline — reproduce & root-cause → fix → regression test → review
argument-hint: <bug description, error message or failing test>
---

Fix this bug with the dev-squad:

$ARGUMENTS

If this is a release blocker or a production patch where the diff must stay minimal and easy to review, use `/dev-squad:hotfix` instead: it adds an approved fix plan, a diff guard and a review packet.

1. **Root cause** — launch `dev-squad:debugger` with the full symptom (error text, stack trace, failing command, environment). It must reproduce the bug, prove the root cause with evidence, write a failing regression test, and apply a minimal fix if the fix is local. Report saved to `.squad/reports/<date>-debug-<slug>.md`.
2. **Fix (if needed)** — if the debugger stopped at root cause because the fix is larger, launch `dev-squad:developer` with the debug report as its brief (or `dev-squad:architect` first if a design change is needed).
3. **Verify** — launch `dev-squad:qa-engineer` to confirm the regression test fails without the fix and passes with it, run the surrounding suite, and check the "same pattern elsewhere" list from the debug report.
4. **Review** — launch `dev-squad:code-reviewer` on the diff. Address blocking findings.
5. Summarise for the user: root cause (one paragraph), fix, files changed, test evidence, other places with the same pattern.

Do not commit or push unless the user asks. Before any push or MR, apply the review gate from the `squad-playbook` skill: run `/dev-squad:review`, resolve or have the user defer every blocking finding, then push only after the user confirms.

End your final summary with `User actions`: what the user must decide or do now, or "none" (see the `squad-playbook` skill).
