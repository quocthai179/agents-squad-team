---
type: llm
weight: 2
---
Binary check. PASS only if both hold:
1. The plan covers non-happy-path states of the form: it mentions at least loading and error states (empty, success or validation states may also appear).
2. The answer contains no implementation code (short component or file names are fine; code blocks with JSX, CSS or functions are not).
