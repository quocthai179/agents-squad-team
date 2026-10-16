---
description: Safe database change pipeline — zero-downtime migration plan → implement → test up/down → review → rollout notes
argument-hint: <schema/data change, e.g. "rename users.fullname to display_name" or "add NOT NULL tenant_id to orders (80M rows)">
---

Make this database change safely with the dev-squad:

$ARGUMENTS

1. **Plan** — launch `dev-squad:database-engineer` to inspect the engine/version, migration tool, ORM models, table sizes and the code that touches the affected tables, then write `.squad/design/db-<slug>.md`: deployable steps (expand → migrate → contract), lock/rewrite impact and estimated duration per statement, app-version compatibility per step, backfill plan, monitoring and rollback.
2. **Confirm** — show the user the step table. Get explicit agreement before any destructive step (drops, irreversible type changes, data deletion) and on the release split (which steps ship in which release).
3. **Implement** — in parallel where files don't overlap:
   - `dev-squad:database-engineer` writes the migrations for the current release only (following the project's conventions; never editing applied migrations) and any backfill job/script,
   - `dev-squad:developer` makes the application changes for the same release (dual-write / read-fallback, entity/model updates).
4. **Verify** — `dev-squad:qa-engineer` runs the migrations up (and down/undo if supported) on a local/disposable database with representative data, runs the application test suite, and checks the backfill is idempotent and resumable. If the change touches a hot path, ask `dev-squad:performance-engineer` to measure the query plans before/after.
5. **Review** — in parallel: `dev-squad:code-reviewer` on the full diff and `dev-squad:database-engineer` reviewing the migrations against its migration-PR checklist.
6. **Rollout notes** — `dev-squad:tech-writer` turns the plan into deploy notes: order of operations, commands humans run, what to monitor (locks, replica lag, errors), rollback, and the follow-up "contract" task, which `dev-squad:project-manager` adds to `.squad/TASKS.md`.

Never run migrations against production or shared databases. Do not commit or push unless the user asks.
