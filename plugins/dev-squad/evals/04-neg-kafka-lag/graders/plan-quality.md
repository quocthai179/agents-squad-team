---
type: llm
---
Binary check. PASS only if both hold:
1. The plan investigates the consumer side with evidence: lag measurement, commit/ack behaviour, rebalances, processing time or poison/redelivered messages (any two of these are enough).
2. It reproduces or measures the evening spike somewhere other than production before changing code (local, staging, a load or spike simulation), or it says production is only observed, never experimented on.
