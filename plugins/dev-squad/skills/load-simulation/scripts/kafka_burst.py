#!/usr/bin/env python3
"""kafka_burst — reproduce sudden Kafka performance problems on a local/test cluster.

  produce  Fire a burst of messages with a load profile. Compare acks, batching,
           compression, sync-vs-async sends, key skew (hot partitions), poison messages.
  consume  Run a consumer that simulates real processing: slow handlers, poison messages,
           nack/seek retry loops, DLQ, commit strategies, max.poll.interval breaches.
           Prints throughput, consumer lag, redeliveries and rebalances every second.
  lag      Watch per-partition lag of a consumer group.

Requires: pip install confluent-kafka

Examples:
  # Burst: 50 msg/s baseline, 5,000 msg/s for 20s; compare --sync vs async and acks
  python kafka_burst.py produce --bootstrap localhost:9092 --topic orders \\
      --shape spike --base 50 --peak 5000 --hold 20s --acks all
  python kafka_burst.py produce ... --sync          # send().get() per message anti-pattern

  # Hot partition: 90% of traffic on a handful of keys
  python kafka_burst.py produce ... --key zipf --keys 1000 --skew 1.5

  # Consumer that cannot keep up with the burst (20ms per message) -> watch lag grow and drain
  python kafka_burst.py consume --bootstrap localhost:9092 --topic orders --group sim --process-ms 20

  # Poison message + nack-style retry (seek back to the same offset) -> partition stuck, hot loop
  python kafka_burst.py produce ... --poison-every 500
  python kafka_burst.py consume ... --on-error retry-seek
  python kafka_burst.py consume ... --on-error dlq --max-retries 3   # the fix: bounded retry + DLQ

  # Rebalance storm: processing slower than max.poll.interval.ms
  python kafka_burst.py consume ... --process-ms 200 --batch 100 --max-poll-interval-ms 6000
"""

import argparse
import json
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loadkit  # noqa: E402

try:
    from confluent_kafka import Consumer, KafkaError, KafkaException, Producer, TopicPartition
except ImportError:  # pragma: no cover
    sys.exit("confluent-kafka is required: pip install confluent-kafka")


def guard_bootstrap(bootstrap, allow_remote):
    for server in bootstrap.split(","):
        host = server.strip().rsplit(":", 1)[0]
        loadkit.guard_target(host, allow_remote, "Kafka broker")


def extra_config(pairs):
    cfg = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        cfg[k.strip()] = v.strip()
    return cfg


# --------------------------------------------------------------------------- produce

def cmd_produce(args):
    guard_bootstrap(args.bootstrap, args.i_own_this_target)
    stages = loadkit.stages_from_args(args)
    conf = {
        "bootstrap.servers": args.bootstrap,
        "acks": args.acks,
        "linger.ms": args.linger_ms,
        "batch.size": args.batch_size,
        "compression.type": args.compression,
        "enable.idempotence": args.idempotence,
        "queue.buffering.max.messages": args.max_buffered,
    }
    conf.update(extra_config(args.config))
    producer = Producer(conf)
    rec = loadkit.Recorder(len(stages))
    rng = random.Random(args.seed)
    key_tpl = {
        "none": None,
        "uniform": loadkit.Template(f"k{{{{randint:1:{args.keys}}}}}"),
        "zipf": loadkit.Template(f"k{{{{zipf:{args.keys}:{args.skew}}}}}"),
        "fixed": loadkit.Template("k1"),
    }[args.key]
    pad = "x" * max(0, args.size - 80)
    stop = threading.Event()
    stage_now = {"i": 0, "t0": None}

    def poller():
        last = time.perf_counter()
        while not stop.is_set():
            producer.poll(0.1)
            now = time.perf_counter()
            if now - last >= 1 and stage_now["t0"] is not None:
                win = rec.take_window()
                st = stages[stage_now["i"]]
                print(loadkit.progress_line(now - stage_now["t0"], st, win, now - last, len(producer),
                                            "in-flight"), flush=True)
                last = now

    poll_thread = threading.Thread(target=poller, daemon=True)
    poll_thread.start()

    print(f"kafka_burst produce: topic={args.topic} acks={args.acks} linger.ms={args.linger_ms} "
          f"batch.size={args.batch_size} compression={args.compression} sync={args.sync} key={args.key}")
    start = time.perf_counter() + 0.1
    stage_now["t0"] = start
    seq = 0
    overrun = loadkit.parse_duration(args.overrun)
    gave_up = False
    try:
        for stage, offset in loadkit.arrivals(stages, args.arrival == "poisson", random.Random(args.seed)):
            stage_now["i"] = stage
            due = start + offset
            if time.perf_counter() - due > overrun:
                rec.scheduled[stage] += 1  # too far behind schedule: count the rest as not sent
                rec.dropped[stage] += 1
                gave_up = True
                continue
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            rec.scheduled[stage] += 1
            seq += 1
            poison = bool(args.poison_every and seq % args.poison_every == 0)
            value = json.dumps({"seq": seq, "ts": time.time(), "poison": poison, "pad": pad})
            key = key_tpl.render(rng, seq) if key_tpl else None

            def on_delivery(err, msg, stage=stage, due=due, sent=time.perf_counter()):
                done = time.perf_counter()
                rec.record(stage, done - due, done - sent,
                           None if err is None else f"KafkaError: {err.name()}")

            try:
                producer.produce(args.topic, value=value, key=key, on_delivery=on_delivery)
            except BufferError:
                rec.dropped[stage] += 1  # local queue full: the producer cannot keep up
                continue
            if args.sync:
                producer.flush()  # the blocking send().get()-per-message anti-pattern
            if args.max_errors and rec.total_errors >= args.max_errors:
                break
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
    remaining = producer.flush(30)
    stop.set()
    poll_thread.join(timeout=2)
    if remaining:
        print(f"WARNING: {remaining} messages still undelivered after 30s flush", file=sys.stderr)
    if gave_up:
        print(f"WARNING: fell more than {args.overrun} behind schedule; remaining sends were skipped and "
              f"counted as dropped (the producer cannot sustain this rate).", file=sys.stderr)
    loadkit.print_report("kafka_burst produce (latency = scheduled -> broker ack)", stages, rec,
                         {k: v for k, v in vars(args).items() if k != "func"}, args.json)


# --------------------------------------------------------------------------- consume

class PoisonError(Exception):
    pass


def cmd_consume(args):
    guard_bootstrap(args.bootstrap, args.i_own_this_target)
    auto = args.commit == "auto"
    conf = {
        "bootstrap.servers": args.bootstrap,
        "group.id": args.group,
        "auto.offset.reset": args.offset_reset,
        "enable.auto.commit": auto,
        "max.poll.interval.ms": args.max_poll_interval_ms,
        "session.timeout.ms": args.session_timeout_ms,
        "partition.assignment.strategy": args.assignor,
    }
    conf.update(extra_config(args.config))
    consumer = Consumer(conf)
    producer = Producer({"bootstrap.servers": args.bootstrap}) if args.on_error == "dlq" else None
    stats = {"consumed": 0, "ok": 0, "failed": 0, "redelivered": 0, "dlq": 0, "commits": 0,
             "assigned": 0, "revoked": 0, "lost": 0, "errors": {}}
    e2e = []  # end-to-end latency (now - message timestamp) in the current window
    retries = {}  # (partition, offset) -> attempts
    assignment = []
    rng = random.Random(args.seed)

    def on_assign(c, parts):
        stats["assigned"] += 1
        assignment[:] = parts

    def on_revoke(c, parts):
        stats["revoked"] += 1

    def on_lost(c, parts):
        stats["lost"] += 1

    consumer.subscribe([args.topic], on_assign=on_assign, on_revoke=on_revoke, on_lost=on_lost)

    def total_lag():
        if not assignment:
            return None
        lag = 0
        try:
            positions = consumer.position(list(assignment))
            for tp in positions:
                lo, hi = consumer.get_watermark_offsets(tp, timeout=1, cached=False)
                pos = tp.offset if tp.offset >= 0 else lo
                lag += max(0, hi - pos)
        except KafkaException:
            return None
        return lag

    def process(msg):
        payload = {}
        try:
            payload = json.loads(msg.value() or b"{}")
        except ValueError:
            pass
        work = max(0.0, rng.gauss(args.process_ms, args.process_ms * args.jitter)) / 1000
        if work:
            time.sleep(work)
        if args.fail_poison and payload.get("poison"):
            raise PoisonError(f"poison message at {msg.partition()}:{msg.offset()}")
        if args.fail_rate and rng.random() < args.fail_rate:
            raise RuntimeError("transient failure")

    print(f"kafka_burst consume: topic={args.topic} group={args.group} process≈{args.process_ms}ms "
          f"commit={args.commit} on_error={args.on_error} batch={args.batch} "
          f"max.poll.interval.ms={args.max_poll_interval_ms}")
    print(f"{'time':>7} {'consumed/s':>10} {'ok':>7} {'failed':>7} {'redeliv':>8} {'dlq':>5} {'lag':>9} "
          f"{'e2e_p95':>9} {'rebal':>6}")
    t0 = last = time.perf_counter()
    window_start = dict(stats)
    deadline = t0 + loadkit.parse_duration(args.duration) if args.duration else None
    idle_since = None
    try:
        while True:
            if deadline and time.perf_counter() >= deadline:
                break
            msgs = consumer.consume(num_messages=args.batch, timeout=0.5)
            for i, msg in enumerate(msgs):
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        key = f"KafkaError: {msg.error().name()}"
                        stats["errors"][key] = stats["errors"].get(key, 0) + 1
                    continue
                stats["consumed"] += 1
                ts_type, ts = msg.timestamp()
                try:
                    process(msg)
                    stats["ok"] += 1
                    if ts > 0:
                        e2e.append(time.time() - ts / 1000)
                except Exception as exc:
                    stats["failed"] += 1
                    k = f"{type(exc).__name__}"
                    stats["errors"][k] = stats["errors"].get(k, 0) + 1
                    pos = (msg.partition(), msg.offset())
                    retries[pos] = retries.get(pos, 0) + 1
                    if args.on_error == "retry-seek" or (args.on_error == "dlq" and retries[pos] <= args.max_retries):
                        # nack(): rewind to the failed offset. The unprocessed rest of this batch (all
                        # partitions) is rewound as well, otherwise it would be silently skipped.
                        stats["redelivered"] += 1
                        if args.retry_backoff_ms:
                            time.sleep(args.retry_backoff_ms / 1000)
                        rewind = {}
                        for m in msgs[i:]:
                            if not m.error():
                                rewind.setdefault((m.topic(), m.partition()), m.offset())
                        for (topic, part), off in rewind.items():
                            consumer.seek(TopicPartition(topic, part, off))
                        break
                    if args.on_error == "dlq":
                        producer.produce(args.dlq_topic or f"{args.topic}.DLT", value=msg.value(), key=msg.key(),
                                         headers={"x-exception": str(exc)[:200]})
                        producer.poll(0)
                        stats["dlq"] += 1
                    retries.pop(pos, None)
                    # on_error == "skip": fall through and commit past it
                if args.commit == "per-record":
                    consumer.commit(message=msg, asynchronous=False)
                    stats["commits"] += 1
            else:
                if msgs and args.commit == "batch":
                    consumer.commit(asynchronous=True)
                    stats["commits"] += 1

            now = time.perf_counter()
            if now - last >= 1:
                d = {k: stats[k] - window_start[k] for k in ("consumed", "ok", "failed", "redelivered", "dlq")}
                lat = sorted(e2e)
                e2e.clear()
                lag = total_lag()
                rebal = stats["assigned"] + stats["revoked"] + stats["lost"]
                p95 = loadkit.percentile(lat, 95)
                print(f"{now - t0:6.1f}s {d['consumed'] / (now - last):10.1f} {d['ok']:7d} {d['failed']:7d} "
                      f"{d['redelivered']:8d} {d['dlq']:5d} {('-' if lag is None else lag):>9} "
                      f"{('-' if p95 != p95 else f'{p95 * 1000:.0f}ms'):>9} {rebal:6d}", flush=True)
                window_start = dict(stats)
                last = now
                if args.exit_when_idle:
                    if lag == 0 and not msgs:
                        idle_since = idle_since or now
                        if now - idle_since >= loadkit.parse_duration(args.exit_when_idle):
                            break
                    else:
                        idle_since = None
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
    finally:
        if args.commit != "auto":
            try:
                consumer.commit(asynchronous=False)
            except KafkaException:
                pass
        consumer.close()
        if producer:
            producer.flush(10)

    elapsed = time.perf_counter() - t0
    print("\n=== kafka_burst consume summary ===")
    print(f"elapsed={elapsed:.1f}s consumed={stats['consumed']} ok={stats['ok']} failed={stats['failed']} "
          f"redelivered={stats['redelivered']} dlq={stats['dlq']} commits={stats['commits']} "
          f"rebalance_events={stats['assigned'] + stats['revoked'] + stats['lost']} "
          f"(assign={stats['assigned']} revoke={stats['revoked']} lost={stats['lost']})")
    if stats["errors"]:
        print("errors: " + ", ".join(f"{k}={v}" for k, v in sorted(stats["errors"].items(), key=lambda kv: -kv[1])))
    hints = []
    stuck = sorted(((n, pos) for pos, n in retries.items() if n >= 3), reverse=True)
    if stuck:
        n, (part, off) = stuck[0]
        hints.append(f"Stuck partition: offset {part}:{off} failed {n} times and is redelivered forever, "
                     f"blocking everything behind it on that partition (lag cannot drain). "
                     f"{len(stuck)} offset(s) affected.")
    if stats["redelivered"] > 10 * max(1, stats["dlq"]) and stats["redelivered"] > 50:
        hints.append("Redelivery loop: failed messages are re-sought/nacked without a bound. Use bounded "
                     "retries with backoff and a dead-letter topic (Spring: DefaultErrorHandler + "
                     "DeadLetterPublishingRecoverer; RabbitMQ: requeue=false + DLX).")
    if stats["lost"] or stats["revoked"] > 1:
        hints.append("Rebalances during the run: processing a poll batch takes longer than "
                     "max.poll.interval.ms or the consumer stalls. Lower max.poll.records/--batch, speed up "
                     "processing, or raise max.poll.interval.ms; use cooperative-sticky + static membership.")
    if args.commit == "per-record" and stats["commits"] > 1000:
        hints.append("Synchronous commit per record: one broker round trip per message. Commit per batch "
                     "(async) and sync-commit on shutdown/revoke.")
    for h in hints:
        print("  - " + h)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "elapsed_s": round(elapsed, 2), "hints": hints,
                       "config": {k: v for k, v in vars(args).items() if k != "func"}}, fh, indent=2, default=str)


# --------------------------------------------------------------------------- lag

def cmd_lag(args):
    guard_bootstrap(args.bootstrap, args.i_own_this_target)
    c = Consumer({"bootstrap.servers": args.bootstrap, "group.id": args.group, "enable.auto.commit": False})
    md = c.list_topics(args.topic, timeout=10)
    parts = [TopicPartition(args.topic, p) for p in sorted(md.topics[args.topic].partitions)]
    try:
        for i in range(args.count):
            committed = c.committed(parts, timeout=10)
            rows, total = [], 0
            for tp in committed:
                lo, hi = c.get_watermark_offsets(tp, timeout=5, cached=False)
                pos = tp.offset if tp.offset >= 0 else lo
                lag = max(0, hi - pos)
                total += lag
                rows.append(f"p{tp.partition}={lag}")
            print(f"{time.strftime('%H:%M:%S')} total_lag={total}  " + " ".join(rows), flush=True)
            if i + 1 < args.count:
                time.sleep(loadkit.parse_duration(args.interval))
    finally:
        c.close()


# --------------------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--bootstrap", default="localhost:9092")
        p.add_argument("--topic", required=True)
        p.add_argument("--config", action="append", help="extra client config key=value; repeatable")
        p.add_argument("--json", help="write a JSON report to this path")
        loadkit.add_safety_args(p)

    p = sub.add_parser("produce", help="fire a burst of messages")
    common(p)
    loadkit.add_profile_args(p)
    p.add_argument("--acks", default="all", choices=["0", "1", "all"])
    p.add_argument("--linger-ms", type=int, default=5)
    p.add_argument("--batch-size", type=int, default=16384)
    p.add_argument("--compression", default="none", choices=["none", "gzip", "snappy", "lz4", "zstd"])
    p.add_argument("--idempotence", action="store_true", help="enable.idempotence=true")
    p.add_argument("--sync", action="store_true", help="wait for the ack of every message (anti-pattern)")
    p.add_argument("--key", default="uniform", choices=["none", "uniform", "zipf", "fixed"],
                   help="key distribution: zipf/fixed create hot partitions")
    p.add_argument("--keys", type=int, default=10000, help="number of distinct keys")
    p.add_argument("--skew", type=float, default=1.2, help="zipf exponent for --key zipf")
    p.add_argument("--size", type=int, default=512, help="approximate message size in bytes")
    p.add_argument("--poison-every", type=int, default=0, help="mark every Nth message as poison")
    p.add_argument("--max-buffered", type=int, default=100000, help="producer local queue size")
    p.add_argument("--overrun", default="15s",
                   help="stop sending once this far behind schedule; the rest counts as dropped (default 15s)")
    p.set_defaults(func=cmd_produce)

    c = sub.add_parser("consume", help="simulate a consumer")
    common(c)
    c.add_argument("--group", required=True)
    c.add_argument("--process-ms", type=float, default=5, help="mean processing time per message")
    c.add_argument("--jitter", type=float, default=0.2, help="stddev as a fraction of --process-ms")
    c.add_argument("--batch", type=int, default=500, help="messages per poll (like max.poll.records)")
    c.add_argument("--commit", default="batch", choices=["auto", "per-record", "batch"])
    c.add_argument("--on-error", default="skip", choices=["skip", "retry-seek", "dlq"],
                   help="skip, nack-like infinite retry by seeking back, or bounded retry + DLQ")
    c.add_argument("--max-retries", type=int, default=3, help="retries before DLQ (--on-error dlq)")
    c.add_argument("--retry-backoff-ms", type=int, default=0)
    c.add_argument("--dlq-topic", help="default: <topic>.DLT")
    c.add_argument("--fail-poison", action="store_true", default=True, help="poison messages raise (default)")
    c.add_argument("--no-fail-poison", dest="fail_poison", action="store_false")
    c.add_argument("--fail-rate", type=float, default=0.0, help="probability of a transient failure")
    c.add_argument("--max-poll-interval-ms", type=int, default=300000)
    c.add_argument("--session-timeout-ms", type=int, default=45000)
    c.add_argument("--assignor", default="cooperative-sticky", choices=["range", "roundrobin", "cooperative-sticky"])
    c.add_argument("--offset-reset", default="earliest", choices=["earliest", "latest"])
    c.add_argument("--duration", help="stop after this long (e.g. 60s)")
    c.add_argument("--exit-when-idle", help="stop once lag is 0 for this long (e.g. 5s)")
    c.add_argument("--seed", type=int)
    c.set_defaults(func=cmd_consume)

    lg = sub.add_parser("lag", help="watch consumer group lag")
    lg.add_argument("--bootstrap", default="localhost:9092")
    lg.add_argument("--topic", required=True)
    lg.add_argument("--group", required=True)
    lg.add_argument("--interval", default="2s")
    lg.add_argument("--count", type=int, default=1)
    lg.add_argument("--i-own-this-target", action="store_true")
    lg.set_defaults(func=cmd_lag)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
