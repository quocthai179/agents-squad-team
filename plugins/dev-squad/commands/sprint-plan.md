---
description: Turn a goal or epic into requirements and a sprint task board in .squad/TASKS.md
argument-hint: <sprint goal / epic description> [capacity, e.g. "20 points"]
---

Plan a sprint with the dev-squad for:

$ARGUMENTS

1. Launch `dev-squad:business-analyst` to write requirements (`.squad/requirements/<slug>.md`) with prioritized user stories (Must/Should/Could) and acceptance criteria.
2. If there are significant unknowns or technical decisions, launch `dev-squad:architect` to produce a lightweight design or spike list.
3. Launch `dev-squad:project-manager` to build or update `.squad/TASKS.md`: tasks ≤ 1 day each, estimates, dependencies, owners (squad agents), milestones, risks. If the user gave a capacity, fit the Must items within it and list what does not fit.
4. Present the plan to the user: sprint goal, committed scope, task table, critical path, risks, open questions. Do not start implementation until the user confirms.
