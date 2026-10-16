---
name: load-simulation
description: Build and run tools that simulate sudden load to reproduce unexpected performance problems — bursts of DB queries, HTTP traffic spikes, Kafka message floods, slow or stuck consumers, poison messages and nack/retry loops, rebalance storms, connection storms, hot keys/rows and cache stampedes — on local/test environments, with before/after measurements. Use when a problem "only happens under load / after a traffic spike", to reproduce a performance incident, to verify a performance fix, or when asked to create a load, spike, stress or soak test tool.
---

# Load simulation: reproduce sudden performance problems

Performance incidents rarely happen at steady load. They happen when traffic **jumps**: a campaign, a cron job colliding with peak, a retry storm, a consumer restarting with a backlog, a cache flush after deploy. This skill gives you an engine and ready-made tools to recreate those moments locally, observe what breaks, and prove a fix with the same command before and after.

Bundled tools live in this skill's `scripts/` directory (its base directory is shown when the skill loads):

| Tool | Simulates | Needs |
|---|---|---|
| `db_burst.py` | SQL query bursts against PostgreSQL / MySQL / SQLite; pool exhaustion, slow queries under concurrency, hot-row locks, long transactions, connection storms; live `pg_stat_activity` / MySQL thread sampling | `psycopg[binary]` or `psycopg2-binary`, or `pymysql` |
| `http_burst.py` | HTTP traffic spikes with weighted endpoints, templated URLs/bodies, keep-alive or connection storms | stdlib only |
| `kafka_burst.py` | `produce` bursts (acks, batching, compression, sync vs async, key skew, poison messages); `consume` simulation (slow handlers, commit modes, nack/seek retry loops, DLQ, max.poll.interval breaches); `lag` watcher | `confluent-kafka` |
| `spike_http.js` | k6 template for high-rate HTTP spikes (thousands of req/s) | `k6` |
| `loadkit.py` | Shared engine to build **new** tools (gRPC, Redis, MongoDB, RabbitMQ, internal SDKs…) | stdlib only |

`scripts/requirements.txt` lists the optional Python drivers. Run `python <tool> --help` for every flag.

## Safety rules (non-negotiable)

1. **Local, dev or dedicated test environments only.** All tools refuse non-local hosts unless `LOADKIT_ALLOW_HOSTS=<host>` or `--i-own-this-target` is set. Never set either for production or shared staging without explicit user approval in this conversation.
2. `db_burst.py` is **read-only by default**: it rejects DML/DDL and opens read-only sessions. Use `--allow-write` only against a disposable local database.
3. Never reset consumer-group offsets, change topic/broker config, or produce to topics used by real consumers. Create dedicated topics/groups (e.g. `perf-orders`, `perf-sim`).
4. Never put secrets in generated files; read them from environment variables. Reports never store header values.
5. Start small (low `--peak`, short `--hold`) and scale up; stop with Ctrl+C — tools drain and still print a report.

## Workflow

1. **Classify the symptom** and pick a scenario from [references/scenarios.md](references/scenarios.md) (spike on a slow query, pool exhaustion, lock contention, cache stampede, consumer lag, poison message loop, rebalance storm, retry storm, …).
2. **Find the real workload in the code**: the hot endpoints, the exact SQL your ORM generates (enable SQL logging or read repositories), topics, keys, message sizes, pool sizes and timeouts from config. Simulating the wrong query proves nothing.
3. **Prepare a realistic environment**: production-like data volume (an index problem is invisible on 1,000 rows), realistic key distribution (`{{zipf:N:S}}` for hot keys), the same pool sizes/timeouts as production config. Reuse the project's docker-compose or seed scripts if they exist.
4. **Build a project-specific tool** under `.squad/perf/<scenario-slug>/`:
   - `run.sh` (or `run.ps1`) with the exact commands, profile and flags; secrets via env vars,
   - copies of the bundled scripts it needs, or a custom tool on top of `loadkit.py` (see below),
   - `README.md`: what it reproduces, prerequisites, how to run, what to watch, expected "bad" vs "good" numbers.
   Prefer the project's existing load tool (k6, Gatling, JMeter, Locust) if it already has one.
5. **Baseline**: run at normal load and record the numbers.
6. **Spike**: run the scenario while observing the server side (see "Observe" below). Keep the console output — it is the evidence.
7. **Diagnose** with the `performance-engineer` checklists (query plans, locks, pool metrics, lag, profiles).
8. **Fix and re-run the identical command**. Report before/after per stage in `.squad/reports/<date>-perf-<slug>.md`, attaching `--json` outputs.

## Load profiles

All tools share the same profile options (open model — arrivals keep coming even when the system slows down, like real users):

```
--shape spike    --base 10 --peak 400 --warmup 20s --hold 30s --recovery 30s   # flat -> instant jump -> back
--shape burst    --base 10 --peak 400 --hold 5s --gap 10s --repeat 5           # repeated short spikes
--shape ramp     --base 10 --peak 1000 --hold 120s                             # find the knee
--shape step     --base 10 --peak 1000 --hold 100s                             # staircase to the breaking point
--profile "30s:10,1s:10->800,60s:800,30s:10"                                    # explicit DURATION:RATE[->RATE] stages
--arrival poisson                                                               # bursty arrivals instead of uniform
```

Value templates for URLs, SQL, bodies and keys: `{{randint:1:50000}}`, `{{zipf:10000:1.2}}` (rank 1 = hottest), `{{seq}}`, `{{uuid}}`. Weight mixes with a prefix: `--query "8:SELECT …" --query "2:SELECT …"`.

## Quick reference (most common scenarios — full catalog in references/scenarios.md)

| Scenario | Command (local/test target) |
|---|---|
| Spike on a slow query | `db_burst.py --dsn $DSN --pool 10 --observe --query "SELECT … {{randint:1:50000}}" --shape spike --base 5 --peak 600` |
| Pool exhaustion (fast + slow mix) | `db_burst.py --dsn $DSN --pool <app pool size> --query "8:SELECT …fast…" --query "2:SELECT …slow…" --shape spike --peak 300 --observe` |
| Connection storm | `db_burst.py --dsn $DSN --connect-per-query --pool 200 --query "SELECT 1" --peak 500 --observe` |
| Hot-row locks / long transaction | `db_burst.py --dsn $DSN --allow-write --pool 40 --observe --query "BEGIN; UPDATE t SET n = n + 1 WHERE id = {{zipf:1000:2.0}}; SELECT pg_sleep(0.02); COMMIT" --profile "10s:10,20s:300,20s:10"` |
| HTTP spike / cache stampede | `http_burst.py --url "http://localhost:8080/api/items/{{zipf:500:1.5}}" --concurrency 50 --shape spike --base 0 --peak 500 --warmup 1s` |
| Sync vs async producer | `kafka_burst.py produce --topic perf-x --shape spike --base 50 --peak 3000 [--sync] [--acks all] [--linger-ms 10 --compression lz4]` |
| Hot partition | `kafka_burst.py produce --topic perf-x --key zipf --keys 1000 --skew 1.5 …` then `kafka_burst.py lag --topic perf-x --group G` |
| Consumer lag after burst | `kafka_burst.py produce --topic perf-x --profile "10s:3000"` then `kafka_burst.py consume --topic perf-x --group perf-sim --process-ms 20 --exit-when-idle 5s` |
| Poison message + nack loop | `kafka_burst.py produce --topic perf-x --profile "4s:2500" --poison-every 3000` then `kafka_burst.py consume --topic perf-x --group g1 --on-error retry-seek --duration 30s`; fix check: `--on-error dlq --max-retries 3` (new group) |
| Rebalance storm | `kafka_burst.py consume --topic perf-x --group g2 --process-ms 150 --jitter 0 --batch 60 --max-poll-interval-ms 6000 --no-fail-poison --duration 30s` |
| Per-record commits | `kafka_burst.py consume … --commit per-record` vs `--commit batch` |

Other useful flags: `--json <path>` (all tools), `--max-errors N`, `--arrival poisson`, `--seed N`; `db_burst.py --timeout-ms`, `--query-file`; `http_burst.py -H "Name: value" --body '…' --no-keepalive`; `kafka_burst.py consume --fail-rate 0.01 --retry-backoff-ms 100 --commit auto|per-record|batch --assignor range|cooperative-sticky`; `kafka_burst.py produce --overrun 15s`.

## Reading the results

Each run prints a per-second live line and a per-stage table:

- **latency** is measured from the *scheduled* time, so time spent waiting for a free connection/worker is included (no coordinated omission). **svc95** is the time of the operation itself.
- latency ≫ service time → work is **queueing** (pool too small, worker/thread limit, single-threaded consumer). Service time rising too → the **backend itself** is slowing (CPU, locks, I/O).
- **drop** > 0 → the client backlog limit was hit: the system could not absorb the spike.
- **recovery** stage still slow after load drops → backlog draining, leaked connections, lock queues, GC, or caches that stay cold. Recovery time is often the most important number.
- The tool prints heuristic *Findings*; confirm each with server-side evidence before concluding.

## Observe the server side during the run

- PostgreSQL: `db_burst.py --observe` (active, lock waits, idle-in-transaction, connections vs `max_connections`); `pg_stat_statements` (reset before the run), `pg_locks`, `EXPLAIN (ANALYZE, BUFFERS)` of the hottest statement.
- MySQL: `--observe` (Threads_running, row lock waits), `SHOW PROCESSLIST`, `performance_schema`, slow query log.
- Kafka: `kafka_burst.py lag --group … --count 30 --interval 2s`, or `kafka-consumer-groups --describe`; consumer logs for `MAXPOLL`/rebalance.
- Application: pool metrics (HikariCP, SQLAlchemy, pgx…), thread/worker pool usage, GC logs or JFR/`py-spy`/`pprof` profiles, container CPU/memory (`docker stats`).

## Building a new tool with loadkit

When the bundled tools do not fit (gRPC, Redis, MongoDB, RabbitMQ, an internal client library), write a small script on top of the engine. You get profiles, open-model scheduling, live progress, safety guard and the report for free:

```python
import argparse, sys
sys.path.insert(0, "<path to this skill>/scripts")   # or copy loadkit.py next to the tool
import loadkit
import redis  # example client

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="localhost")
loadkit.add_profile_args(ap); loadkit.add_safety_args(ap)
args = ap.parse_args()
loadkit.guard_target(args.host, args.i_own_this_target, "Redis")
key = loadkit.Template("product:{{zipf:100000:1.2}}")
stages = loadkit.stages_from_args(args)

def make_ctx(worker):            # one client/connection per worker = pool size
    return redis.Redis(host=args.host)

def op(client, rng, seq):        # one simulated operation; raise on failure
    if client.get(key.render(rng, seq)) is None:
        raise RuntimeError("cache miss")

rec, _ = loadkit.run_open_model(stages, 50, make_ctx, op, close_ctx=lambda c: c.close(),
                                max_queue=args.max_queue, seed=args.seed)
loadkit.print_report("redis hot keys", stages, rec)
```

`run_open_model(..., observer=fn)` accepts a function returning a short string sampled every second — use it to print server-side metrics next to client-side latency.

## Deliverables

- `.squad/perf/<scenario-slug>/` — the runnable tool (`run.sh`, scripts, `README.md`), committed with the fix so the scenario can be re-run in the future or in CI.
- `.squad/reports/<YYYY-MM-DD>-perf-<slug>.md` — baseline vs spike vs after-fix tables, server-side evidence, root cause, trade-offs.
