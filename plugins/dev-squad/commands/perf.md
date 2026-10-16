---
description: Performance pipeline — measure / reproduce spikes → find bottleneck (DB, Kafka/RabbitMQ, runtime) → fix → re-measure → review
argument-hint: <slow endpoint/job/query/consumer, symptom and target, e.g. "GET /orders p95 2s, target 300ms">
---

Investigate and fix this performance problem with the dev-squad:

$ARGUMENTS

1. **Analyse** — launch `dev-squad:performance-engineer` with the full symptom (endpoint/job/query/topic/queue, metric, current vs. target, load, environment, any logs/traces/plans the user gave). It must establish a baseline, rank bottlenecks with evidence, and write `.squad/reports/<YYYY-MM-DD>-perf-<slug>.md`. Tell it to apply only small, local fixes itself and to return a fix spec for anything larger. It must not touch production or live brokers.
   If the problem only happens under traffic spikes or bursts, the brief must ask it to first build and run a reproduction tool with the `load-simulation` skill under `.squad/perf/<slug>/` (baseline → spike → recovery) against a local/test environment.
2. **Check trade-offs** — if any proposed fix changes delivery semantics (acks, commit/ack mode, retries, DLQ), consistency, or data schema/indexes on large tables, show it to the user and get agreement before implementing.
3. **Fix** — for fixes not already applied, launch `dev-squad:developer` with the perf report as its brief (or `dev-squad:architect` first if the fix is a design change, e.g. async processing, caching layer, partitioning).
4. **Verify** — in parallel: `dev-squad:qa-engineer` runs the test suite (behaviour must not change), and `dev-squad:performance-engineer` re-measures with the same method and load (the same `.squad/perf/<slug>/run.sh` if one was built) to produce before/after numbers.
5. **Review** — launch `dev-squad:code-reviewer` on the diff.
6. Summarise for the user: root bottleneck(s), fixes, before/after metrics, trade-offs accepted, follow-ups (monitoring, load tests in CI).

Do not commit or push unless the user asks.
