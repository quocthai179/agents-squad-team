---
description: Release readiness — CI/deploy checklist, security pass and release notes
argument-hint: [version or release name]
---

Prepare a release with the dev-squad: $ARGUMENTS

If no version was given, treat it as the next release.

1. Launch in parallel:
   - `dev-squad:devops-engineer` — run the deployment readiness checklist against this repo (CI config, build, migrations, config/secrets, feature flags, monitoring, rollback plan). Validate locally only; do **not** deploy or change live infrastructure.
   - `dev-squad:security-auditor` — audit changes since the last release tag (`git describe --tags --abbrev=0` → `<tag>..HEAD`) plus dependency vulnerabilities.
   - `dev-squad:qa-engineer` — run the full test suite and report results.
   - `dev-squad:database-engineer` — review migrations added since the last release tag: lock/rewrite impact on large tables, compatibility with the version still running during rollout, ordering, backfills and rollback.
2. Then launch `dev-squad:tech-writer` to draft CHANGELOG / release notes for `<last tag>..HEAD`, breaking changes first.
3. Report a **GO / NO-GO** to the user with: checklist results, blocking issues (with owners), test results, security findings, and the draft release notes.

Never tag, push, publish or deploy unless the user explicitly asks.
