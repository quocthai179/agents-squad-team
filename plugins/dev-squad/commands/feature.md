---
description: Full feature pipeline — requirements → design → tasks → code → tests → review → docs
argument-hint: <feature description>
---

Deliver this feature end-to-end with the dev-squad:

$ARGUMENTS

Run the pipeline below using the Agent tool. Each agent starts cold, so every brief must include the feature description, relevant paths and the upstream artifacts to read. Derive a short kebab-case `<slug>` for the feature and use it for all artifact paths.

1. **Requirements** — `dev-squad:business-analyst`: write `.squad/requirements/<slug>.md` with user stories and Given/When/Then acceptance criteria. If it returns open questions that change scope, ask the user before continuing; otherwise proceed on its stated assumptions.
2. **Design** — `dev-squad:architect`: write `.squad/design/<slug>.md` (+ ADRs for significant decisions). Skip only if the change is small and fits an existing pattern; say so explicitly.
3. **Plan** — `dev-squad:project-manager`: break the work into tasks in `.squad/TASKS.md` with owners, estimates and dependencies.
4. **Implement** — `dev-squad:developer`: implement the tasks in dependency order (one agent per independent task group; parallelize only tasks that touch different files). Each must report verification output.
5. **Test** — `dev-squad:qa-engineer`: map every acceptance criterion to tests, run them, and write `.squad/reports/<date>-qa-<slug>.md`. If the verdict is FAIL, send defects back to `dev-squad:developer` (or `dev-squad:debugger` if the cause is unclear) and re-test. Repeat until PASS.
6. **Review** — in parallel: `dev-squad:code-reviewer` on the full diff, and `dev-squad:security-auditor` if the feature touches auth, user input, data access, secrets, payments or PII. Save their reports to `.squad/reports/`. Send blocking findings back to the developer, then re-review.
7. **Docs** — `dev-squad:tech-writer`: update README/API docs and add a CHANGELOG entry.
8. **Close** — have `dev-squad:project-manager` mark tasks done, then summarise for the user: what was built, files changed, test evidence, review verdicts, deferred items.

Do not commit or push unless the user asks.
