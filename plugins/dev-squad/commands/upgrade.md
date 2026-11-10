---
description: Dependency/framework upgrade pipeline — inventory → migration plan → stepwise upgrade with tests → security & perf checks → review
argument-hint: <target, e.g. "Spring Boot 3.3 + Java 21", "Node 22", "fix all high CVEs", "React 19">
---

Upgrade with the dev-squad:

$ARGUMENTS

1. **Inventory & plan** — launch `dev-squad:dependency-upgrader` to inventory current versions, outdated and vulnerable dependencies, read the official migration guides between current and target versions, grep the codebase for every breaking change that applies, and write the step plan to `.squad/reports/<YYYY-MM-DD>-upgrade-<slug>.md` (one major at a time, codemods/OpenRewrite recipes to use, risks). It must stop after planning.
2. **Confirm** — show the plan to the user (steps, notable breaking/behaviour changes, license or abandoned-package flags) and get agreement on scope before changing code.
3. **Execute** — launch `dev-squad:dependency-upgrader` again to carry out the agreed steps one at a time, verifying build, tests and startup after each step. If a step fails in a way it cannot resolve after two focused attempts, route it to `dev-squad:debugger`.
4. **Verify** — in parallel:
   - `dev-squad:qa-engineer` runs the full test suite and a smoke test of the main flows,
   - `dev-squad:security-auditor` re-runs dependency vulnerability checks on the result,
   - `dev-squad:performance-engineer` does a quick before/after check if the runtime, ORM, HTTP client, JSON library or connection pool changed major versions.
5. **Review** — `dev-squad:code-reviewer` reviews the diff, step by step.
6. **Document** — `dev-squad:tech-writer` adds a CHANGELOG entry and notes for developers (new minimum runtime, changed config properties, changed defaults).

Do not commit, push or publish unless the user asks.
