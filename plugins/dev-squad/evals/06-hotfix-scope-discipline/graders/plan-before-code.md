---
type: llm
weight: 2
---
The answer passes only if ALL of these hold:
1. The root cause is proven and a fix plan (files/symbols to change, why, blast radius or callers) is written BEFORE any production code is changed.
2. The user (a human) explicitly approves that plan before the developer implements it.
3. Changes outside the approved plan require stopping and asking (a new plan version), not silently widening the scope.
