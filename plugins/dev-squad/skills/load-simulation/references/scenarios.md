# Sudden-load scenario catalog

Each scenario: **symptom in production → how to reproduce → what to watch → typical fixes**. Commands assume you are in the skill's `scripts/` directory (or the copy in `.squad/perf/<scenario>/`), against a local/test target.

---

## Database

### 1. Spike on a slow / unindexed query
- **Symptom**: fine at normal traffic; during a peak p95 explodes, DB CPU 100%, requests time out, and latency stays high for minutes after the peak.
- **Reproduce**: `python db_burst.py --dsn $DSN --pool 10 --observe --query "SELECT … WHERE customer_id = {{randint:1:50000}}" --shape spike --base 5 --peak 600`
- **Watch**: latency ≫ svc95 (queueing), `drop` > 0, recovery stage still slow; `EXPLAIN (ANALYZE, BUFFERS)` shows Seq Scan / rows removed by filter.
- **Fix**: index matching the filter/sort, rewrite the query, limit result size, cache. Re-run the same command: the spike should be absorbed with no drops.

### 2. Connection-pool exhaustion
- **Symptom**: errors like "Connection is not available, request timed out after 30000ms" (HikariCP), "QueuePool limit … overflow … reached" (SQLAlchemy); DB itself is not busy.
- **Reproduce**: set `--pool` to the application's pool size and add the endpoint's real queries (including slow ones): `python db_burst.py --dsn $DSN --pool 10 --query "8:SELECT …fast…" --query "2:SELECT …slow report…" --shape spike --peak 300 --observe`
- **Watch**: `pg active` ≈ pool size, latency ≫ svc95. One slow query type starving the fast ones.
- **Fix**: shorten what holds a connection (no remote calls while holding it, smaller transactions), separate pools for slow/background work, statement timeouts, right-size the pool (`connections ≈ cores × 2` on the DB side, not "as many as possible").

### 3. Connection storm (no pooling, cold pool after deploy, serverless scale-out)
- **Symptom**: right after a deploy or scale-out, DB `max_connections` reached, "too many clients", login CPU spikes.
- **Reproduce**: `python db_burst.py --dsn $DSN --connect-per-query --pool 200 --query "SELECT 1" --shape spike --peak 500 --observe`
- **Watch**: `conns=` near `max_connections`, errors `too many clients`/`FATAL`, svc95 dominated by connect time (TLS + auth).
- **Fix**: pooling in the app, PgBouncer/ProxySQL/RDS Proxy, pool min-idle/warm-up, cap instances × pool size below `max_connections`.

### 4. Hot-row lock contention
- **Symptom**: counters, balances, inventory or "last_seen" updates on a few rows; throughput collapses at peak, `lock_wait` high, deadlocks appear.
- **Reproduce** (disposable DB): `python db_burst.py --dsn $DSN --allow-write --pool 40 --observe --query "BEGIN; UPDATE accounts SET balance = balance + 1 WHERE id = {{zipf:1000:2.0}}; SELECT pg_sleep(0.02); COMMIT" --profile "10s:10,20s:300,20s:10"`
  (`pg_sleep` stands in for work done inside the transaction — e.g. an HTTP call.)
- **Watch**: `lock_wait` ≈ pool size, rate far below target, long recovery.
- **Fix**: keep transactions short (no I/O inside), atomic single-statement updates, `SELECT … FOR UPDATE SKIP LOCKED` for queues, sharded counters / append-only events + aggregation, optimistic locking with retry limits.

### 5. Batch job / report colliding with peak traffic
- **Symptom**: every day at 09:00 the API slows down — a cron export or analytics query runs at the same time.
- **Reproduce**: run two processes at once — the API mix at peak and the heavy query at low rate:
  `python db_burst.py --dsn $DSN --pool 10 --query "SELECT …api…" --shape constant --base 200 --hold 120s &`
  `python db_burst.py --dsn $DSN --pool 2 --query "SELECT …heavy report…" --profile "30s:0,60s:0.5,30s:0"`
- **Watch**: API p95 during the report window vs before/after; buffer cache eviction, I/O.
- **Fix**: move reports to a replica/warehouse, run off-peak, chunk the job, resource limits (statement timeout, `work_mem`), materialized views.

### 6. Deep OFFSET pagination / unbounded result sets under load
- **Reproduce**: `--query "SELECT … ORDER BY id LIMIT 50 OFFSET {{randint:0:500000}}"` at a spike.
- **Fix**: keyset (seek) pagination, hard `LIMIT`, avoid `COUNT(*)` per page.

### 7. N+1 amplification
- **Symptom**: one endpoint call issues 1 + N queries; at peak the DB sees N× the expected QPS.
- **Reproduce**: spike the endpoint with `http_burst.py`, then compare `calls` in `pg_stat_statements` (reset before the run) with the number of HTTP requests.
- **Fix**: eager loading / joins / batch loading (DataLoader), projections.

---

## HTTP / application

### 8. Downstream slowness exhausts the worker pool
- **Symptom**: a dependency (payment API, another service) slows to 2s; your service's threads/event loop fill up and *all* endpoints become slow, even ones that don't use that dependency.
- **Reproduce**: run a local stub of the dependency with an artificial delay (or a toxiproxy latency toxic), then `python http_burst.py --url "8:GET http://localhost:8080/api/healthy-endpoint" --url "2:GET http://localhost:8080/api/uses-dependency" --shape spike --peak 300`
- **Watch**: latency of the healthy endpoint rising together with the slow one.
- **Fix**: timeouts on every outbound call, bulkheads (separate pools), circuit breakers, async I/O, load shedding.

### 9. Cache stampede (thundering herd)
- **Symptom**: after a deploy, cache flush or TTL expiry of a hot key, hundreds of requests miss simultaneously and all hit the DB.
- **Reproduce**: flush the cache (local only), then immediately `python http_burst.py --url "http://localhost:8080/api/products/{{zipf:200:1.5}}" --shape spike --base 0 --peak 500 --warmup 1s`
- **Watch**: DB QPS spike at start, latency of the first seconds vs later.
- **Fix**: request coalescing / single-flight, stale-while-revalidate, jittered TTLs, cache warming on deploy, locks per key.

### 10. Hot keys / hot shards
- **Reproduce**: compare `{{randint:1:N}}` with `{{zipf:N:1.5}}` in the same run setup.
- **Fix**: key splitting, local in-process cache for the top keys, rate limiting per key.

### 11. Retry storm
- **Symptom**: a brief blip turns into a long outage because clients retry immediately (and every layer retries).
- **Reproduce**: build a small client with `loadkit` whose `op` retries N times without backoff on 5xx/timeouts, then compare with exponential backoff + jitter and a retry budget, against a service that fails for 10s.
- **Fix**: exponential backoff with jitter, retry budgets, retry at one layer only, idempotency keys, circuit breakers.

### 12. Connection storm on HTTP (no keep-alive, TLS everywhere)
- **Reproduce**: `python http_burst.py … --no-keepalive` vs default keep-alive.
- **Fix**: connection reuse/pooling in HTTP clients, HTTP/2, tune load balancer idle timeouts.

---

## Kafka / messaging

### 13. Synchronous producer under a burst
- **Symptom**: producing service slows to a crawl during a burst; producer throughput capped at a few hundred msg/s.
- **Reproduce**: `python kafka_burst.py produce --topic perf-orders --shape spike --base 50 --peak 3000 --sync` vs without `--sync`.
- **Watch**: async keeps up with low p95; `--sync` drops (falls behind schedule) and latency climbs to the overrun limit.
- **Fix**: async send with callbacks, batching (`linger.ms` 5–20, `batch.size`), compression (`lz4`/`zstd`), `enable.idempotence=true` instead of `max.in.flight=1`.

### 14. Consumer lag after a burst
- **Symptom**: after a campaign, events arrive minutes late; lag grows and takes hours to drain.
- **Reproduce**: `python kafka_burst.py produce --topic perf-orders --profile "10s:3000"` then `python kafka_burst.py consume --topic perf-orders --group perf-sim --process-ms 20 --exit-when-idle 5s`
- **Watch**: `consumed/s` vs produce rate, lag curve, `e2e_p95`; drain time = lag / (consume rate − produce rate).
- **Fix**: speed up the handler (batch DB writes, remove per-message remote calls), more partitions + consumers, parallel processing per key, back-pressure upstream.

### 15. Poison message + nack/seek retry loop
- **Symptom**: one partition's lag grows forever while others are fine; logs show the same offset failing repeatedly; CPU busy doing nothing useful.
- **Reproduce**: `python kafka_burst.py produce --topic perf-payments --profile "4s:2500" --poison-every 3000` then `python kafka_burst.py consume --topic perf-payments --group perf-seek --on-error retry-seek --duration 30s`
- **Watch**: "Stuck partition" hint, `failed`/`redelivered` repeating on the same offset, lag never reaching 0 (`kafka_burst.py lag`).
- **Fix** (verify with `--on-error dlq --max-retries 3`): bounded retries with backoff and a dead-letter topic — Spring Kafka `DefaultErrorHandler` + `DeadLetterPublishingRecoverer` (or non-blocking retry topics); RabbitMQ `basic.nack(requeue=false)` + DLX with `x-death` retry count; SQS redrive policy.

### 16. Rebalance storm (max.poll.interval.ms exceeded)
- **Symptom**: logs show "maximum poll interval exceeded … leaving group", constant rebalances, duplicates, throughput near zero.
- **Reproduce**: `python kafka_burst.py consume --topic perf-orders --group perf-slow --process-ms 150 --jitter 0 --batch 60 --max-poll-interval-ms 6000 --no-fail-poison --duration 30s`
- **Watch**: `_MAX_POLL_EXCEEDED` errors, `lost` partitions, the same messages processed again (lag does not move).
- **Fix**: fewer records per poll (`max.poll.records`), faster processing, higher `max.poll.interval.ms` for genuinely long work, cooperative-sticky assignor + static membership (`group.instance.id`), pause/resume partitions while processing asynchronously.

### 17. Per-record synchronous commits
- **Reproduce**: `kafka_burst.py consume … --commit per-record` vs `--commit batch`.
- **Fix**: commit per batch (async) and sync-commit on revoke/shutdown; idempotent handlers for at-least-once.

### 18. Hot partition from skewed keys
- **Reproduce**: `kafka_burst.py produce … --key zipf --keys 1000 --skew 1.5`, then `kafka_burst.py lag` — one partition's lag dominates.
- **Fix**: better partition key (add a salt/sub-key where ordering allows), more partitions, separate topic for heavy tenants.

---

## Recording results

For every scenario, keep: the exact command, environment (data volume, pool sizes, versions), the stage table for baseline / spike / after-fix, server-side evidence, and the recovery time. Store them in `.squad/reports/<YYYY-MM-DD>-perf-<slug>.md` with `--json` outputs alongside.
