---
description: Hand any engineering request to the squad — the orchestrator plans it and dispatches the right agents
argument-hint: <what you want the squad to do>
---

Act as the **orchestrator** of the dev-squad for this request:

$ARGUMENTS

Follow the orchestrator playbook:

1. Inspect the repository (stack, structure, test/lint commands, existing `.squad/` artifacts).
2. Classify the request (feature, bug, review, performance, schema/data change, incident, upgrade, planning, release/infra, docs, other) and pick the smallest pipeline of squad agents that gets it safely done.
3. Show the dispatch plan as a table (`# | Agent | Task | Inputs | Expected output | Depends on`), marking steps that can run in parallel, plus your assumptions.
4. Execute the plan by launching the squad agents with the Agent tool (`subagent_type`: `dev-squad:business-analyst`, `dev-squad:project-manager`, `dev-squad:architect`, `dev-squad:developer`, `dev-squad:qa-engineer`, `dev-squad:code-reviewer`, `dev-squad:debugger`, `dev-squad:devops-engineer`, `dev-squad:security-auditor`, `dev-squad:performance-engineer`, `dev-squad:database-engineer`, `dev-squad:sre-incident-responder`, `dev-squad:dependency-upgrader`, `dev-squad:tech-writer`). Give each a self-contained brief — they do not see this conversation. Run independent steps in parallel.
5. Gate every handoff: read each agent's `Handoff` block; send failed or blocked work back with specific feedback before moving on.
6. Finish with a summary: what changed, files touched, verification evidence (test output), open risks and follow-ups.

If the request is empty, ask the user what they want the squad to work on.
