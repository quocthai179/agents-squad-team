---
type: llm
---
The answer passes only if it gives the reviewer a way to trust the diff: a justification for every changed hunk (or every changed line) tied to the root cause, a regression test that fails before and passes after, and a summary of what was deliberately not changed. It fails if it imposes a fixed line-count budget as the main control.
