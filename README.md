# Agents Squad Team 🧑‍💻🤖

![Agents Squad Team — 16 specialized agents and 14 workflow commands for Claude Code](assets/marketing/hero-banner.png)

A **Claude Code** plugin that gives you a development squad of **16 specialized agents** (one coordinating lead and 15 specialists) and **14 workflow commands** covering the software development lifecycle: requirements → design → task planning → implementation → testing → review → security → performance → database migrations → release → incident response → dependency upgrades. It also includes an agent that audits the squad itself.

## Meet the squad

![One orchestrator and 15 specialists sharing artifacts and handoffs through the .squad directory](assets/marketing/specialists-shared-context.png)

*The illustration shows a selection of roles. The full roster is listed below.*

| Agent | Role | When to use it | Permissions |
|---|---|---|---|
| 🟣 `orchestrator` | Tech lead / coordinator | Ambiguous or multi-step requests that require several roles to work together | Full access (inherited) |
| 🩵 `business-analyst` | Business analyst | Clarify requirements, write user stories and acceptance criteria (Given/When/Then) | Read + write documentation |
| 🟡 `project-manager` | PM / Scrum master | Break down tasks, estimate work, track dependencies, maintain `TASKS.md`, prepare standups, and identify risks | Read + write documentation + read-only Git |
| 🔵 `architect` | Software architect | Design modules, APIs, and data models; write ADRs; compare technologies | Read + write design documentation |
| 🟢 `developer` | Senior full-stack developer | Implement features, refactor, fix bugs, and write unit tests; create a requirements checklist before coding and mark each item ✅/❌/⏭ with evidence | Read/write code + run commands |
| 🟠 `qa-engineer` | QA / test automation | Plan tests, write and run unit/integration/end-to-end tests, and report bugs | Read/write tests + run commands |
| 🔴 `code-reviewer` | Code reviewer | Review diffs before merging for correctness, performance, test coverage, and more | **Read-only** |
| 🩷 `debugger` | Debugging specialist | Investigate errors, stack traces, failing or flaky tests, and “works locally but fails in CI” problems | Read/write code + run commands |
| 🩵 `devops-engineer` | DevOps engineer | Work on CI/CD, Docker, Kubernetes, Terraform, and deployment checklists | Read/write configuration + run commands |
| 🔴 `security-auditor` | Security auditor | Audit OWASP/CWE issues, secrets, authorization, and vulnerable dependencies | **Read-only** |
| 🟡 `performance-engineer` | Performance specialist | Investigate slow queries, N+1 queries, missing indexes, locks, and connection pools; Kafka/RabbitMQ lag, incorrect ack/nack/commit handling, redelivery loops, and rebalances; profile CPU/memory; **build tools to simulate sudden load spikes** with the `load-simulation` skill | Read/write code + run commands (measure before/after) |
| 🟢 `database-engineer` | Database engineer | Plan zero-downtime schema/data changes (expand → migrate → contract), assess locks on large tables, batch backfills, rollbacks, and migration reviews (Flyway, Liquibase, Alembic, Prisma, and more) | Read/write migrations + run commands (local databases only) |
| 🔴 `sre-incident-responder` | SRE / incident responder | Handle production outages or degradation: assess severity, identify triggering changes, propose mitigations, maintain timelines and status updates, write postmortems, and work on SLOs, alerts, and runbooks | Read-only in production; every production change requires your approval |
| 🟠 `dependency-upgrader` | Dependency upgrade specialist | Upgrade Spring Boot 2→3, Java 17→21, Node, Python, React, and more; patch CVEs; follow migration guides; use OpenRewrite/codemods; upgrade incrementally with tests | Read/write code + run commands |
| 🔵 `tech-writer` | Technical writer | Write READMEs, API documentation, CHANGELOGs, runbooks, and guides | Read + write documentation |
| 🩵 `squad-auditor` | Squad auditor (engineering manager + AI workflow coach) | Audit the squad itself (`dev-squad`, `lab`) using real work history to identify missing, weak, redundant, or overlapping agents and recommend actions | Write only to `.squad/audit/`; never modifies the squad automatically |

Every agent:

- Reads the codebase and follows the project's existing conventions.
- Responds in **your language** (for example, Vietnamese in → Vietnamese out), while keeping code and identifiers in English.
- Saves artifacts in the shared `.squad/` directory so the next agent can continue with the right context.
- Ends with a **Handoff** block containing status, artifacts, the next agent, and risks.

## Workflow commands

![Feature workflow: clarify requirements, design, plan tasks, implement, test, review, document, and close tasks](assets/marketing/feature-workflow.png)

*Overview of `/dev-squad:feature`: failed QA checks return to implementation and testing; security auditing applies when relevant to the feature.*

| Command | Pipeline |
|---|---|
| `/dev-squad:squad <request>` | The orchestrator analyzes the request, plans the work, and delegates to the appropriate agents |
| `/dev-squad:feature <description>` | BA → Architect → PM → Developer → QA (repeat until PASS) → Reviewer ∥ Security → Tech writer |
| `/dev-squad:bugfix <bug>` | Debugger → (Developer) → QA regression tests → Reviewer |
| `/dev-squad:review [MR/PR URL \| !iid \| branch \| range]` | Code reviewer ∥ Security auditor run in parallel and produce a merged report; accepts MR/PR URLs or numbers; always saves the merged report to a fixed path (`.squad/reports/review-mr-<id>.md` for an MR/PR); concludes with READY TO PUSH / NOT READY |
| `/dev-squad:commit-msg [context]` | Drafts a commit message from the staged diff using the repository's style; extracts the ticket ID from the branch name and **warns about mismatched ticket IDs**, including in unpushed commits; commits only after your confirmation |
| `/dev-squad:brief [audience]` | Produces a fixed-format summary of no more than 250 words for a manager who understands programming but does not read the code: summary, problem, work completed, evidence-backed results, risks, decisions needed, and next steps |
| `/dev-squad:sprint-plan <goal>` | BA → (Architect) → PM; creates the board at `.squad/TASKS.md` |
| `/dev-squad:standup [time range]` | PM summarizes the Git log and task board |
| `/dev-squad:ship [version]` | DevOps ∥ Security ∥ QA ∥ DB engineer (migration review) → Tech writer → GO / NO-GO |
| `/dev-squad:db-change <change>` | DB engineer plans a zero-downtime migration → you approve → DB engineer ∥ Developer → QA tests migration up/down → Reviewer ∥ DB engineer → rollout notes |
| `/dev-squad:incident <incident>` | SRE assesses the incident and proposes mitigations → you approve → root cause investigation (Debugger / Perf / DB / DevOps) → fix → postmortem → PM creates action items |
| `/dev-squad:upgrade <target>` | Upgrader inventories dependencies and prepares a plan → you approve → incremental upgrades with tests → QA ∥ Security ∥ Perf → Reviewer → CHANGELOG |
| `/dev-squad:audit [dev-squad\|lab\|both] [time range]` | Asks up to three questions → Squad auditor reads transcripts, `.squad/`, `research/`, Git history, and agent definitions → evidence-backed report + draft agents → you choose what to adopt |
| `/dev-squad:perf <problem>` | Performance engineer measures a baseline and identifies bottlenecks → Developer fixes them → QA ∥ before/after measurements → Reviewer |

The `squad-playbook` skill also helps Claude choose the right agents when you say something like *“use the squad to…”*.

## `load-simulation` skill — reproduce sudden load spikes

Many performance incidents occur when traffic **rises suddenly**: a campaign launches, scheduled jobs coincide with peak traffic, retries cascade, a consumer restarts with a large backlog, or a deployment flushes the cache. This skill is preloaded for `performance-engineer` and `sre-incident-responder` (you can also invoke it directly with `/dev-squad:load-simulation`). It helps agents **build tools that reproduce the incident** inside your project at `.squad/perf/<scenario>/`, then compare measurements before and after a fix.

| Tool | What it simulates | Requirements |
|---|---|---|
| `db_burst.py` | Bursts of queries against PostgreSQL/MySQL/SQLite: connection pool exhaustion, slow concurrent queries, hot-row locks, long transactions, and connection storms; monitors `pg_stat_activity` every second | `psycopg[binary]` / `pymysql` |
| `http_burst.py` | Sudden HTTP traffic spikes, weighted endpoint mixes, cache stampedes, keep-alive traffic, or connection storms | Standard library only |
| `kafka_burst.py` | `produce` bursts (acks, batching, compression, sync/async, skewed keys → hot partitions, poison messages); `consume` simulates slow consumers, endless nack/seek retries, DLQs, commit strategies, and exceeding `max.poll.interval.ms`; `lag` monitors consumer lag | `confluent-kafka` |
| `spike_http.js` | A k6 template for HTTP spikes reaching thousands of requests per second | `k6` |
| `loadkit.py` | A shared engine for building additional tools (gRPC, Redis, MongoDB, RabbitMQ, and more) | Standard library only |

Key features:

- **Open-model load generation**: requests arrive on a schedule, like real traffic. Latency is measured from the *scheduled send time*, including time waiting for pools or workers, to avoid coordinated omission.
- **Load shapes**: `spike`, `burst`, `ramp`, `step`, `constant`, or custom profiles such as `--profile "30s:10,1s:10->800,60s:800,30s:10"`.
- **Skewed key distributions** with `{{zipf:N:S}}` to simulate hot keys and hot rows.
- **Per-phase reporting** for baseline / spike / recovery (p50/p95/p99, service time, drops), with diagnostic suggestions and JSON output.
- **Safe defaults**: rejects non-local hosts; database access is read-only unless `--allow-write` is set; tokens are not saved in reports.
- A catalog of **18 common incident scenarios**, including reproduction commands and fixes (`references/scenarios.md`).

Examples:

```bash
# Query without an index: baseline of 5 queries/s, then a spike to 600 queries/s
python db_burst.py --dsn postgresql://app:app@localhost/app --pool 10 --observe \
  --query "SELECT * FROM orders WHERE customer_id = {{randint:1:50000}}" --shape spike --base 5 --peak 600

# Poison message + nack/seek retries stall a partition; compare bounded retries + DLQ
python kafka_burst.py produce --topic perf-payments --profile "4s:2500" --poison-every 3000
python kafka_burst.py consume --topic perf-payments --group sim --on-error retry-seek --duration 30s
python kafka_burst.py consume --topic perf-payments --group sim2 --on-error dlq --max-retries 3
```

Recorded test results on PostgreSQL 16 (600,000-row table, pool size 10, spike of 600 queries/s):

| Phase | Before adding an index (p95) | After adding an index (p95) |
|---|---|---|
| Baseline: 5 queries/s | 23 ms | 4.1 ms |
| Spike: 600 queries/s | 15,710 ms; 835 requests dropped | 1.2 ms; 0 drops |
| Recovery: 5 queries/s | 15,317 ms (not yet recovered) | 5.2 ms |

## `squad-auditor` agent — audit the squad itself

This agent acts as an engineering manager and AI workflow coach. It audits the squads (`dev-squad`, `lab`) using **real work history**:

1. **Gather evidence** in the following order, stating which sources are accessible and which have “no data”:
   - Claude Code transcripts (`~/.claude/projects/**/*.jsonl`, including subagent transcripts).
   - `.squad/` and `research/` (TASKS, reports, incidents, LESSONS, squad-issues, retro).
   - Git history.
   - Existing agent, skill, and command definitions.
2. **Build a work inventory** and look for signs that an agent is missing:
   - Manual work repeated at least three times.
   - Long prompts rewritten from scratch.
   - Outputs corrected immediately after an agent runs.
   - Instructions repeated across sessions.
   - Handoffs copied and pasted manually.
   - Agents that are never invoked.
   - Frequently skipped steps, such as testing or review.
   - Domain-specific work, such as SNMP/MIB, Quarkus, or OVNG.
3. **Assess each agent** (keep / revise prompt / revise description / merge / remove) and **propose up to five new agents**. Each proposal needs at least two real examples and a draft agent file. The auditor then **challenges its own proposals** to avoid unnecessary squad growth.
4. **Write a report** to `.squad/audit/<date>/squad-audit.md`: TL;DR, an action plan (quick wins, this week, this month), and metrics to revisit after 2–4 weeks.

The agent uses the `squad-audit` skill, which includes `mine_transcripts.py`. This script uses only the standard library, runs locally, automatically redacts secrets and email addresses, and attaches a `file:line` source to every finding. Use `--show=<ref>` to inspect the context before citing a finding.

```bash
python plugins/dev-squad/skills/squad-audit/scripts/mine_transcripts.py --days 30 --scope dev-squad --scope lab --md usage.md
```

> The agent only makes recommendations; it never changes agent, skill, or command definitions automatically. The `evidence/` directory contains redacted conversation excerpts, so add `.squad/audit/*/evidence/` to `.gitignore`. Conversations on claude.ai are marked as “no data” unless you export them to a local file.

## Installation

### Option 1 — install through the marketplace (recommended)

In Claude Code:

```text
/plugin marketplace add quocthai179/agents-squad-team
/plugin install dev-squad@agents-squad-team
```

Restart the session afterward, or run `/reload-plugins` if your version of Claude Code supports it.

### Option 2 — load directly from a local directory (development / testing)

```bash
git clone https://github.com/quocthai179/agents-squad-team.git
claude --plugin-dir ./agents-squad-team/plugins/dev-squad
```

### Option 3 — enable for the whole team through the repository's `.claude/settings.json`

```json
{
  "extraKnownMarketplaces": {
    "agents-squad-team": {
      "source": { "source": "github", "repo": "quocthai179/agents-squad-team" }
    }
  },
  "enabledPlugins": {
    "dev-squad@agents-squad-team": true
  }
}
```

## Usage

**Delegate an entire workflow with a command:**

```text
/dev-squad:feature Add email-based password resets with links that expire after 30 minutes
/dev-squad:bugfix  TypeError: Cannot read properties of undefined (reading 'id') in OrderService.create
/dev-squad:review  origin/main...HEAD
/dev-squad:sprint-plan Build an inventory management module with a capacity of 30 points
/dev-squad:perf    Consumer lag on order-events keeps growing, with repeated nacks at the same offset
/dev-squad:perf    API GET /orders p95 = 2s, target 300ms
/dev-squad:perf    The system slows down during flash sales; build a spike simulator to reproduce it
/dev-squad:db-change  Add a NOT NULL tenant_id column to orders (80 million rows), with zero downtime
/dev-squad:incident   Checkout started returning 5xx at 14:05 UTC, immediately after deploying v2.3.1
/dev-squad:upgrade    Spring Boot 2.7 → 3.3 and Java 17 → 21
```

**Invoke a specific agent:**

```text
Use the business-analyst agent to write user stories for a PDF export feature
@dev-squad:qa-engineer write tests for src/services/payment.ts
```

**Use the orchestrator as the main agent for the entire session**, allowing it to spawn other agents:

```bash
claude --agent dev-squad:orchestrator
```

> ℹ️ In Claude Code, a subagent cannot invoke other subagents. Multi-agent orchestration therefore runs in the main session through `/dev-squad:*` commands, or by running the orchestrator as the main agent as shown above. If invoked as a subagent, the orchestrator returns a plan and a brief for each step for the main session to execute.

## Shared workspace: `.squad/`

Agents exchange files so the next agent has the context it needs:

```text
.squad/
├── requirements/<feature>.md        # business-analyst
├── design/<feature>.md              # architect
├── adr/0001-<decision>.md            # architect
├── TASKS.md                         # project-manager: source of truth for tasks
├── perf/<scenario>/                 # performance-engineer: reusable load simulation tools
├── tmp/                             # developer: temporary scripts and logs (automatically gitignored)
├── LESSONS.md                       # shared lessons: every agent reads; write-enabled agents contribute
├── incidents/<date>-<slug>/         # sre-incident-responder: timeline, postmortem
├── audit/<date>/                    # squad-auditor: squad-audit.md, drafts/, evidence/
└── reports/<date>-<type>-<slug>.md   # qa / review / security / debug / perf / upgrade
```

You can commit `.squad/` to share planning history with your team, or add it to `.gitignore` for personal use.

## Squad working conventions

- **Review gate before every push or MR/PR**, including branch pushes, tag pushes, and opening or updating an MR/PR:
  1. Run `/dev-squad:review`.
  2. Fix every *blocking* finding (🔴 from `code-reviewer`, Critical/High from `security-auditor`), or explicitly approve deferring each finding.
  3. `/review` always ends with **READY TO PUSH** or **NOT READY**. Push only after your confirmation.

  The rule is defined centrally in the `squad-playbook` skill; workflow commands refer to it. Every agent with Bash access follows the **never push automatically** rule. Only the main session may push, after your confirmation.
- **`developer`:**
  - Create a **requirements checklist** (R/C/V) before coding, and report each item as ✅/❌/⏭ with evidence.
  - **Never wait using `sleep`, polling loops, or Monitor.** Run builds and tests in the foreground with an explicit `timeout` (up to 10 minutes). Save logs to a file and inspect only the errors. Practical testing showed that subagents did not receive background-completion notifications, which caused builds to run twice.
  - Only commands expected to take more than 10 minutes may run in the background. Hand them off with the command, log path, and an “unverified” status. The main session can still run background commands because it receives completion notifications.
  - Put long scripts (more than approximately 15 lines) or scripts with complex quoting in `.squad/tmp/`, then execute them by path.
  - Create `.squad/tmp/` with its own `.gitignore` before writing temporary files. Keep secrets out of temporary scripts and treat logs as sensitive. Before any image build (`docker build`, `buildx`, `compose build`, `podman`, and similar tools), verify that `.dockerignore` excludes `.squad/`.

- **Working contract** for every agent and command:
  - Do not fabricate information. **Ask** when missing information could change the result (up to three questions; `Status: needs-input`). Mark minor assumptions as `ASSUMPTION:`.
  - Every handoff includes **`User actions`**, and every command's final summary ends with **“User actions”** (or its equivalent in the user's language).
  - `Status:` accepts only `done | blocked | needs-input`; put verdicts in the report.
- **Shared lessons in `.squad/LESSONS.md`:** every agent reads them before starting, then write-enabled agents add root causes, environment quirks, and recurring pitfalls. Keep each lesson short, evidence-backed, and free of secrets; see the format in the `squad-playbook` skill.
- **Clear agent boundaries:**
  - `code-reviewer` reviews diffs only.
  - `qa-engineer` writes automated tests in code. Manual or browser-based tests in the lab environment belong to the separate UI test squad.
  - `orchestrator` runs only as the main agent or through `/dev-squad:squad`.
  - `performance-engineer` also handles requests to test real performance or increase load until timeouts occur.
  - `sre-incident-responder` also handles pod restarts, crash loops, and OOMKilled incidents, and **always writes a postmortem** to `.squad/incidents/`.

## Customization

- **Models:** each agent declares `model` in its frontmatter. `architect`, `security-auditor`, `performance-engineer`, `database-engineer`, and `sre-incident-responder` use `opus`; `orchestrator` uses `inherit`; the others use `sonnet`. Choose `opus`, `sonnet`, `haiku`, or `inherit` to match your budget.
- **Tool permissions:** edit the `tools` field. `code-reviewer` and `security-auditor` deliberately lack `Write`/`Edit` access to enforce read-only behavior.
- **Add an agent:** create `plugins/dev-squad/agents/<name>.md` using an existing agent as a template, then add it to the roster in `orchestrator.md` and `skills/squad-playbook/SKILL.md`.
- **Override an agent for one project:** copy its file to the project's `.claude/agents/` directory and customize it. Project-level agents take precedence over plugin agents.

## Repository layout

```text
agents-squad-team/
├── .claude-plugin/marketplace.json     # marketplace definition
├── .github/workflows/validate.yml      # CI: plugin validation + unit tests
├── tests/                             # load simulation engine + transcript miner unit tests
└── plugins/dev-squad/
    ├── .claude-plugin/plugin.json      # plugin manifest
    ├── agents/                         # 16 agents
    ├── commands/                       # 14 workflow commands
    └── skills/
        ├── squad-playbook/SKILL.md     # orchestration playbook
        ├── squad-audit/                # audit skill + scripts/mine_transcripts.py
        └── load-simulation/            # sudden load spike simulation
            ├── SKILL.md
            ├── references/scenarios.md # 18 incident scenarios with reproduction steps
            └── scripts/                # loadkit, db_burst, http_burst, kafka_burst, spike_http.js
```

## Validation

```bash
claude plugin validate --strict .
claude plugin validate --strict plugins/dev-squad
claude --plugin-dir plugins/dev-squad plugin details dev-squad
python3 -m unittest discover -s tests
```

## Marketing assets

- [Social preview image](assets/marketing/social-preview.png)
- [Workflow diagram in SVG format](assets/marketing/feature-workflow.svg)
- [Asset usage guide and original prompts (Vietnamese)](docs/marketing/README.md)

## License

MIT
