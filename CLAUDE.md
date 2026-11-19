# agents-squad-team

Claude Code plugin marketplace. The plugin source is `plugins/dev-squad/`: agents, commands and skills, with scripts in `skills/*/scripts/`.

## Rules

- **Review gate before push / MR.** Before pushing commits for a merge request, or opening or updating an MR/PR:
  1. Run `/dev-squad:review` on the branch diff against `main`.
  2. Fix every 🔴 blocking finding, or get the user's explicit decision to defer it.
  3. Show the verdict and ask the user to confirm.
  4. Push or open the MR only after confirmation. Re-run the review if the code changed afterwards.
- Never commit transcript evidence (`.squad/audit/*/evidence/`) or scratch files (`.squad/tmp/`).
- Agent prompts are written in English; user-facing docs (`README.md`) are in Vietnamese.
- When adding or changing an agent, command or skill, also update the orchestrator roster, `skills/squad-playbook/SKILL.md`, `README.md` and the version in both manifests.

## Checks (run before asking to push)

```bash
claude plugin validate --strict .
for p in plugins/dev-squad plugins/dev-squad/agents plugins/dev-squad/commands plugins/dev-squad/skills; do claude plugin validate --strict "$p"; done
python3 -m unittest discover -s tests
claude --plugin-dir plugins/dev-squad plugin details dev-squad   # inventory: agents, commands, skills
```
