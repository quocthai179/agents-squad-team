---
description: Incident response — triage & mitigate a production problem, find root cause, then blameless postmortem and follow-ups
argument-hint: <what is happening, e.g. "checkout 5xx since 14:05 UTC after deploy v2.3.1">
---

Run incident response with the dev-squad for:

$ARGUMENTS

1. **Triage & mitigate** — launch `dev-squad:sre-incident-responder` in live-incident mode with everything the user has given (symptoms, start time, alerts, dashboards, log excerpts, recent deploys). It must assess severity, check what changed, start `.squad/incidents/<YYYY-MM-DD>-<slug>/timeline.md`, propose mitigations (each with exact command, blast radius, expected effect and undo) and draft the first status update.
2. **Decide** — show the proposed mitigations to the user. Execute nothing against production unless the user explicitly approves that specific action. Relay the status update for them to post.
3. **Root cause** (once service is stable or mitigation is in progress) — launch the specialist(s) the responder recommends, in parallel when independent:
   - `dev-squad:debugger` for code defects and regressions,
   - `dev-squad:performance-engineer` for capacity, latency, DB or Kafka lag problems (reproducing with the `load-simulation` skill on a local/test environment),
   - `dev-squad:database-engineer` for migration, lock or schema problems,
   - `dev-squad:devops-engineer` for deploy, config or infrastructure problems,
   - `dev-squad:security-auditor` if a breach or data exposure is possible.
4. **Fix** — `dev-squad:developer` implements the permanent fix with a regression test; `dev-squad:code-reviewer` reviews it.
5. **Postmortem** — `dev-squad:sre-incident-responder` writes the blameless `postmortem.md` (impact, UTC timeline, root cause with evidence, detection, response, action items typed prevent/detect/mitigate/process).
6. **Follow-ups** — `dev-squad:project-manager` adds the action items to `.squad/TASKS.md` with owners and priorities. Summarise for the user: impact, root cause, fix status, open action items.

Do not commit or push unless the user asks.
