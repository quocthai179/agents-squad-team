---
description: Audit the agent squads (dev-squad, lab) from real work history — missing/weak/overlapping agents, evidence-backed fixes, action plan and follow-up metrics
argument-hint: [dev-squad | lab | both] [window, e.g. "30 days" or "since 2026-10-01"] [repo filter]
---

Audit the user's agent squad(s) with `dev-squad:squad-auditor`.

Arguments: $ARGUMENTS

1. **Clarify (at most 3 questions, only if needed).** If the scope (`dev-squad` | `lab` | both) or the time window is missing from the arguments, ask the user with AskUserQuestion. Ask at most 3 questions in total: scope, window, and, only if several unrelated projects appear in `~/.claude/projects`, which repositories to include. If the user prefers not to answer, use the defaults: both squads, the last 30 days, all projects.
2. **Run the audit.** Launch `dev-squad:squad-auditor`. Its brief must include:
   - scope, window and repository filter,
   - the current repository path,
   - where the plugin definitions live: `~/.claude/plugins`, plus the local `plugins/` folder if this repository is a plugin repository. Tell it to pass each location as its own `--plugins-root`, and to pass `--scope dev-squad --scope lab` for both squads. Without `--scope`, the miner audits every installed plugin.
   - an instruction to follow its `squad-audit` skill and write `.squad/audit/<YYYY-MM-DD>/squad-audit.md`, with drafts in `drafts/` and evidence in `evidence/`.
3. **Present** the TL;DR, the action plan and the paths to the report and drafts. Mark clearly which findings rest on "không có dữ liệu" sources.
4. **Offer, don't apply.** Ask which quick wins or proposals the user wants applied. Only then edit agents, skills or commands, as a separate change through `dev-squad:developer` or directly, and validate it with `claude plugin validate --strict` when the plugin source is in this repository.
5. Suggest re-running `/dev-squad:audit` in 2–4 weeks with the same window length, and comparing the metrics table.

Never commit evidence files: they contain redacted conversation snippets. Do not commit or push unless the user asks. Before any push or MR, apply the review gate from the `squad-playbook` skill: run `/dev-squad:review`, resolve or have the user defer every blocking finding, then push only after the user confirms.
