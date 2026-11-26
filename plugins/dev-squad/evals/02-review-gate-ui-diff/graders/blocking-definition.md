---
type: llm
weight: 2
---
The answer passes only if ALL of these hold:
1. It names three reviewers for this UI diff: a code reviewer, a security auditor and a design reviewer.
2. It says running `/dev-squad:review` covers all three for a UI diff. It fails if it tells the user to run the design review separately or says the review command does not include it.
3. It states that blocking findings are: code-reviewer 🔴 (blocking), security Critical or High, and design-reviewer Blocker or High.
4. It says the push happens only after the user confirms a READY TO PUSH decision (or equivalent explicit confirmation).
