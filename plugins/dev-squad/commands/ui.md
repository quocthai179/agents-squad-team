---
description: UI pipeline — design-system context → ui-engineer builds and verifies in a browser → design-reviewer ∥ code-reviewer → qa-engineer adds visual/a11y tests
argument-hint: <UI change, e.g. "settings page with profile form and danger zone", "fix table overflow on mobile">
---

Deliver this UI change with the dev-squad:

$ARGUMENTS

1. **Context**
   - If `.squad/ui/DESIGN.md` is missing, build it first with the `ui-context` skill, i.e. `/dev-squad:ui-init`. Show the user the detected stack and tokens and the inferred patterns, and confirm anything marked `ASSUMPTION:`.
   - If the request is vague about behaviour, launch `dev-squad:business-analyst` for user stories and acceptance criteria first. Every state counts: loading, empty, error, success.
2. **Build.** Launch `dev-squad:ui-engineer` with this brief:
   - the request and the acceptance criteria,
   - the DESIGN.md path,
   - the routes and components involved,
   - whether this is an existing product (consistency) or a new product or agreed redesign (aesthetic direction),
   - an instruction to verify in a browser with `visual-verify` and report screenshot and `report.md` paths.
3. **Review in parallel.**
   - `dev-squad:design-reviewer` reviews the running result against DESIGN.md. Give it the preview URL, or let it start the dev server.
   - `dev-squad:code-reviewer` reviews the diff.
   - Send Blocker or High design findings and 🔴 code findings back to `dev-squad:ui-engineer`, then re-review the changed screens.
4. **Lock it in.** Launch `dev-squad:qa-engineer` to add tests for the new states. Where the project supports it, also add Playwright screenshot baselines and `@axe-core/playwright` checks for the changed routes (see the `visual-verify` CI reference).
5. **Summarise** for the user:
   - what changed,
   - screenshot paths for mobile and desktop, light and dark,
   - the accessibility result,
   - the review verdicts,
   - design-system additions,
   - anything not visually verified.

Do not commit or push unless the user asks. Before any push or MR, apply the review gate from the `squad-playbook` skill: run `/dev-squad:review`, resolve or have the user defer every blocking finding, then push only after the user confirms.

End your final summary with `User actions`: what the user must decide or do now, or "none" (see the `squad-playbook` skill).
