---
name: squad-playbook
description: Playbook for working with the dev-squad agent team — which specialist agent to use for which job, standard pipelines (feature, bugfix, review, sprint, release), the shared `.squad/` workspace layout and the handoff format. Use when the user asks to "use the squad/team", wants several agents to collaborate, asks which agent fits a task, or mentions `.squad/` artifacts.
---

# Dev-squad playbook

## Roster

| Agent (`subagent_type`) | Role | Writes code? |
|---|---|---|
| `dev-squad:orchestrator` | Tech lead: plans, dispatches, gates handoffs | Coordination only |
| `dev-squad:business-analyst` | Requirements, user stories, acceptance criteria | No (docs) |
| `dev-squad:project-manager` | Task breakdown, estimates, board, standups, risks | No (docs) |
| `dev-squad:architect` | Design docs, API contracts, data model, ADRs | No (docs) |
| `dev-squad:developer` | Implementation, refactors, unit tests | Yes |
| `dev-squad:qa-engineer` | Test plans, automated tests, QA reports | Tests only |
| `dev-squad:code-reviewer` | Read-only diff review | No (read-only) |
| `dev-squad:debugger` | Reproduce, root-cause, minimal fix + regression test | Yes |
| `dev-squad:devops-engineer` | CI/CD, Docker, IaC, release readiness | Yes (infra/config) |
| `dev-squad:security-auditor` | Read-only security audit | No (read-only) |
| `dev-squad:performance-engineer` | Profiling, DB query/index tuning, Kafka/RabbitMQ lag & ack/nack issues, load/spike simulation tools (`load-simulation` skill) | Yes (targeted fixes, benchmarks, sim tools) |
| `dev-squad:database-engineer` | Zero-downtime migrations, lock impact, backfills, migration reviews | Yes (migrations, backfill jobs) |
| `dev-squad:sre-incident-responder` | Incident triage & mitigation proposals, status updates, postmortems, SLOs/alerts/runbooks | Docs/runbooks; prod changes only with approval |
| `dev-squad:dependency-upgrader` | Framework/runtime/library upgrades, CVE patches | Yes (stepwise upgrades) |
| `dev-squad:tech-writer` | README, API docs, changelog, runbooks | Docs only |

Subagents cannot launch other subagents. Orchestration (the pipelines below) therefore runs from the main session — via the `/dev-squad:*` commands or by following this playbook — or with the orchestrator as the main agent (`claude --agent dev-squad:orchestrator`).

## Pipelines

- **Feature** (`/dev-squad:feature`): BA → architect → PM → developer → QA ⟲ developer → code-reviewer ∥ security-auditor → tech-writer → PM close.
- **Bugfix** (`/dev-squad:bugfix`): debugger → (developer) → QA → code-reviewer.
- **Review** (`/dev-squad:review`): code-reviewer ∥ security-auditor.
- **Performance** (`/dev-squad:perf`): performance-engineer → (developer) → QA ∥ performance-engineer re-measure → code-reviewer.
- **Schema/data change** (`/dev-squad:db-change`): database-engineer plan → user confirms → database-engineer ∥ developer → QA (migrate up/down) → code-reviewer ∥ database-engineer → tech-writer rollout notes.
- **Incident** (`/dev-squad:incident`): sre-incident-responder triage → user approves mitigations → debugger / performance-engineer / database-engineer / devops-engineer → developer fix → postmortem → PM action items.
- **Upgrade** (`/dev-squad:upgrade`): dependency-upgrader plan → user confirms → stepwise upgrade → QA ∥ security ∥ perf → code-reviewer → tech-writer.
- **Sprint planning** (`/dev-squad:sprint-plan`): BA → (architect) → PM.
- **Standup** (`/dev-squad:standup`): PM.
- **Release** (`/dev-squad:ship`): devops ∥ security ∥ QA ∥ database-engineer → tech-writer → GO/NO-GO.
- **Anything else** (`/dev-squad:squad`): orchestrator chooses.

Skip steps that add nothing (a one-line fix needs no BA or architect), and say which steps were skipped.

## Writing briefs

Agents start with no memory of the conversation. Every brief should contain:

1. Goal and why it matters.
2. Exact scope: files, directories, diff range, task IDs.
3. Upstream artifacts to read (`.squad/requirements/<slug>.md`, `.squad/design/<slug>.md`, …).
4. Constraints (no new deps, keep API compatible, deadline, …).
5. The expected deliverable and where to save it.

## `.squad/` workspace

```
.squad/
├── requirements/<slug>.md      # business-analyst
├── design/<slug>.md            # architect
├── adr/NNNN-<decision>.md      # architect
├── TASKS.md                    # project-manager (single source of truth)
├── perf/<scenario>/            # performance-engineer: runnable load-simulation tools
├── incidents/<date>-<slug>/    # sre-incident-responder: timeline.md, postmortem.md
└── reports/<date>-<type>-<slug>.md   # qa, review, security, debug, perf, upgrade
```

Teams may commit `.squad/` (shared planning history) or add it to `.gitignore` (personal scratch space).

## Handoff block

Every agent ends with:

```
### Handoff
- Status: done | blocked | needs-input
- Artifacts: <paths>
- Next: <agent> — <task>
- Risks / open questions: <...>
```

Do not advance a pipeline past a `blocked` / `needs-input` status or a failed verdict; route it back with specific feedback.
