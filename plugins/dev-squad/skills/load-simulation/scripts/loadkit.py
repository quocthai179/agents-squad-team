"""Shared engine for the load-simulation tools (stdlib only).

- Load profiles: stages of `DURATION:RATE` or `DURATION:FROM->TO` (ops/sec),
  or presets (spike, burst, ramp, step, constant).
- Open-model scheduling: work arrives on a clock like real traffic, whether or
  not the system keeps up. Latency is measured from the *scheduled* time, so
  queueing (e.g. waiting for a pool connection) is included and coordinated
  omission is avoided.
- Target guard: refuses non-local targets unless explicitly allowed.
- Value templates: {{randint:A:B}}, {{zipf:N:S}}, {{seq}}, {{uuid}}.
- Live per-second progress and a per-stage report (text + JSON).
"""

import bisect
import itertools
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal", ""}
ALLOW_ENV = "LOADKIT_ALLOW_HOSTS"


# --------------------------------------------------------------------------- profiles

@dataclass
class Stage:
    duration: float
    start_rate: float
    end_rate: float
    label: str = ""

    def rate_at(self, t):
        if self.duration <= 0:
            return self.end_rate
        return self.start_rate + (self.end_rate - self.start_rate) * (t / self.duration)

    def describe(self):
        if self.start_rate == self.end_rate:
            return f"{self.start_rate:g}/s"
        return f"{self.start_rate:g}->{self.end_rate:g}/s"


_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)?$")


def parse_duration(text):
    m = _DURATION.match(text.strip())
    if not m:
        raise ValueError(f"bad duration {text!r} (use e.g. 500ms, 30s, 5m)")
    value, unit = float(m.group(1)), m.group(2) or "s"
    return value * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]


def parse_profile(text):
    """'30s:10,1s:10->500,60s:500,30s:10' -> [Stage, ...]"""
    stages = []
    for i, part in enumerate(p for p in text.split(",") if p.strip()):
        try:
            dur, rate = part.strip().split(":", 1)
            if "->" in rate:
                a, b = rate.split("->", 1)
                start, end = float(a), float(b)
            else:
                start = end = float(rate)
        except ValueError:
            raise ValueError(f"bad stage {part!r} (use DURATION:RATE or DURATION:FROM->TO)") from None
        if start < 0 or end < 0:
            raise ValueError(f"negative rate in stage {part!r}")
        stages.append(Stage(parse_duration(dur), start, end, f"s{i + 1}"))
    if not stages:
        raise ValueError("empty profile")
    return stages


def preset_stages(shape, base, peak, warmup, hold, recovery, repeat=3, gap=10.0, steps=5):
    """Common 'sudden load' shapes. Rates are ops/sec, times are seconds."""
    if shape == "constant":
        return [Stage(hold, base, base, "steady")]
    if shape == "spike":  # flat -> instant jump -> hold -> drop: does it absorb and recover?
        return [Stage(warmup, base, base, "baseline"), Stage(hold, peak, peak, "spike"),
                Stage(recovery, base, base, "recovery")]
    if shape == "burst":  # repeated short spikes: queues/pools that never drain
        stages = [Stage(warmup, base, base, "baseline")]
        for i in range(repeat):
            stages.append(Stage(hold, peak, peak, f"burst{i + 1}"))
            stages.append(Stage(gap, base, base, f"gap{i + 1}"))
        stages[-1].label = "recovery"
        stages[-1].duration = max(gap, recovery)
        return stages
    if shape == "ramp":  # linear climb: find the knee of the latency curve
        return [Stage(warmup, base, base, "baseline"), Stage(hold, base, peak, "ramp"),
                Stage(recovery, peak, peak, "peak")]
    if shape == "step":  # staircase to peak: capacity / breaking point
        stages = [Stage(warmup, base, base, "baseline")]
        for i in range(1, steps + 1):
            r = base + (peak - base) * i / steps
            stages.append(Stage(hold / steps, r, r, f"step{i}"))
        stages.append(Stage(recovery, base, base, "recovery"))
        return stages
    raise ValueError(f"unknown shape {shape!r}")


def add_profile_args(parser):
    g = parser.add_argument_group("load profile")
    g.add_argument("--profile", help="explicit stages, e.g. '30s:10,1s:10->500,60s:500,30s:10'")
    g.add_argument("--shape", default="spike", choices=["spike", "burst", "ramp", "step", "constant"],
                   help="preset shape when --profile is not given (default: spike)")
    g.add_argument("--base", type=float, default=10, help="baseline rate ops/s (default 10)")
    g.add_argument("--peak", type=float, default=200, help="peak rate ops/s (default 200)")
    g.add_argument("--warmup", default="20s", help="baseline duration before the spike (default 20s)")
    g.add_argument("--hold", default="30s", help="spike/ramp duration (default 30s)")
    g.add_argument("--recovery", default="30s", help="baseline duration after the spike (default 30s)")
    g.add_argument("--repeat", type=int, default=3, help="number of bursts for --shape burst")
    g.add_argument("--gap", default="10s", help="pause between bursts for --shape burst")
    g.add_argument("--arrival", default="uniform", choices=["uniform", "poisson"],
                   help="inter-arrival distribution (poisson = bursty, more realistic)")
    g.add_argument("--max-queue", type=int, default=10000,
                   help="client-side backlog limit; arrivals beyond it are counted as dropped")
    g.add_argument("--seed", type=int, help="random seed for reproducible runs")


def stages_from_args(args):
    if args.profile:
        return parse_profile(args.profile)
    return preset_stages(args.shape, args.base, args.peak, parse_duration(args.warmup),
                         parse_duration(args.hold), parse_duration(args.recovery),
                         args.repeat, parse_duration(args.gap))


def arrivals(stages, poisson=False, rng=None):
    """Yield (stage_index, offset_seconds) for each scheduled operation.

    Uniform mode places the k-th arrival where the integrated rate reaches k, which is
    exact for constant stages and linear ramps (including ramps from 0). Poisson mode
    uses thinning, so bursty arrivals also follow the ramp.
    """
    rng = rng or random.Random()
    origin = 0.0
    for idx, st in enumerate(stages):
        peak = max(st.start_rate, st.end_rate)
        if peak > 0 and st.duration > 0:
            if poisson:
                t = 0.0
                while True:
                    t += rng.expovariate(peak)
                    if t >= st.duration:
                        break
                    if rng.random() * peak <= st.rate_at(t):
                        yield idx, origin + t
            else:
                a = (st.end_rate - st.start_rate) / (2 * st.duration)  # N(t) = a*t^2 + b*t
                b = st.start_rate
                total = b * st.duration + a * st.duration ** 2
                k = 1
                while k <= total + 1e-9:
                    t = k / b if a == 0 else (-b + math.sqrt(max(0.0, b * b + 4 * a * k))) / (2 * a)
                    if t >= st.duration:
                        break
                    yield idx, origin + t
                    k += 1
        origin += st.duration


# --------------------------------------------------------------------------- safety

def guard_target(host, allow_remote=False, what="target"):
    """Refuse anything that is not local unless the host is explicitly allowed."""
    host = (host or "").strip("[]").lower()
    allowed = {h.strip().lower() for h in os.environ.get(ALLOW_ENV, "").split(",") if h.strip()}
    if host in LOCAL_HOSTS or host in allowed:
        return
    if allow_remote:
        print(f"WARNING: {what} '{host}' is not local; proceeding because --i-own-this-target was given.",
              file=sys.stderr)
        return
    sys.exit(
        f"Refusing to load-test non-local {what} '{host}'.\n"
        f"Only run against local/dev/test environments you own. To allow it, set "
        f"{ALLOW_ENV}={host} or pass --i-own-this-target.")


def add_safety_args(parser):
    parser.add_argument("--i-own-this-target", action="store_true",
                        help="allow a non-local target (never production without approval)")
    parser.add_argument("--max-errors", type=int, default=0,
                        help="abort after this many errors (0 = never abort)")


# --------------------------------------------------------------------------- templates

_TOKEN = re.compile(r"\{\{\s*(randint|zipf|seq|uuid)(?::([^}]*))?\s*\}\}")
_ZIPF_CACHE = {}
_ZIPF_LOCK = threading.Lock()


def _zipf_cdf(n, s):
    key = (n, s)
    with _ZIPF_LOCK:
        if key not in _ZIPF_CACHE:
            if n > 2_000_000:
                raise ValueError("zipf N is limited to 2,000,000")
            weights = (1.0 / (k ** s) for k in range(1, n + 1))
            cdf = list(itertools.accumulate(weights))
            _ZIPF_CACHE[key] = (cdf, cdf[-1])
        return _ZIPF_CACHE[key]


class Template:
    """Fill {{...}} tokens with generated integers / uuids.

    {{randint:1:100000}}  uniform integer in [1, 100000]
    {{zipf:100000:1.1}}   skewed integer in [1, 100000]; rank 1 is the hottest key
    {{seq}}               the operation sequence number
    {{uuid}}              random UUID4
    Only numbers and UUIDs are generated, so values are safe to inline in SQL.
    """

    def __init__(self, text):
        self.text = text
        self.has_tokens = bool(_TOKEN.search(text))
        for m in _TOKEN.finditer(text):  # validate early
            self._value(m, random.Random(0), 0)

    def _value(self, m, rng, seq):
        kind, arg = m.group(1), (m.group(2) or "")
        parts = [p for p in arg.split(":") if p]
        if kind == "randint":
            lo, hi = (int(parts[0]), int(parts[1])) if len(parts) == 2 else (1, int(parts[0]))
            return str(rng.randint(lo, hi))
        if kind == "zipf":
            n = int(parts[0])
            s = float(parts[1]) if len(parts) > 1 else 1.1
            cdf, total = _zipf_cdf(n, s)
            return str(bisect.bisect_left(cdf, rng.random() * total) + 1)
        if kind == "seq":
            return str(seq)
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))

    def render(self, rng, seq):
        if not self.has_tokens:
            return self.text
        return _TOKEN.sub(lambda m: self._value(m, rng, seq), self.text)


def pick_weighted(items, rng):
    """items: list of (weight, value)."""
    total = sum(w for w, _ in items)
    r = rng.random() * total
    for w, v in items:
        r -= w
        if r <= 0:
            return v
    return items[-1][1]


def parse_weighted(spec):
    """'3:SELECT ...' -> (3.0, 'SELECT ...'); plain text gets weight 1."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*:(?!:)(.*)$", spec, re.S)
    if m and not spec.lstrip().lower().startswith(("http:", "https:")):
        return float(m.group(1)), m.group(2).strip()
    return 1.0, spec.strip()


# --------------------------------------------------------------------------- stats

def percentile(sorted_values, p):
    if not sorted_values:
        return float("nan")
    k = max(0, min(len(sorted_values) - 1, math.ceil(p / 100.0 * len(sorted_values)) - 1))
    return sorted_values[k]


def _ms(v):
    return "-" if v != v else (f"{v * 1000:.0f}" if v >= 0.1 else f"{v * 1000:.1f}")


class Recorder:
    def __init__(self, n_stages):
        self.lock = threading.Lock()
        self.results = [[] for _ in range(n_stages)]  # (latency, service, ok)
        self.errors = [{} for _ in range(n_stages)]
        self.dropped = [0] * n_stages
        self.scheduled = [0] * n_stages
        self.total_errors = 0
        self._win = []  # (latency, ok) since last tick

    def record(self, stage, latency, service, error=None):
        with self.lock:
            self.results[stage].append((latency, service, error is None))
            self._win.append((latency, error is None))
            if error is not None:
                self.total_errors += 1
                key = error[:160]
                self.errors[stage][key] = self.errors[stage].get(key, 0) + 1

    def take_window(self):
        with self.lock:
            win, self._win = self._win, []
        return win


# --------------------------------------------------------------------------- runner

def progress_line(elapsed, stage, window, interval, pending, pending_label="backlog", extra=""):
    lat = sorted(x[0] for x in window)
    errs = sum(1 for x in window if not x[1])
    return (f"[{elapsed:6.1f}s] {stage.label:<9} target={stage.describe():<12} "
            f"done/s={len(window) / max(interval, 1e-9):7.1f} {pending_label}={pending:6d} "
            f"p50={_ms(percentile(lat, 50)):>6}ms p95={_ms(percentile(lat, 95)):>6}ms "
            f"p99={_ms(percentile(lat, 99)):>6}ms err={errs}{extra}")


def run_open_model(stages, workers, make_ctx, op, close_ctx=None, *, poisson=False, max_queue=10000,
                   max_errors=0, seed=None, observer=None, progress=True):
    """Drive `op(ctx, rng, seq)` on `workers` threads following the stage schedule.

    make_ctx(worker_index) -> ctx   (e.g. one DB connection per worker = pool size)
    observer() -> str               optional, sampled once per second (server-side metrics)
    """
    rec = Recorder(len(stages))
    jobs = queue.Queue()
    stop = threading.Event()
    base_rng = random.Random(seed)
    ready = threading.Barrier(workers + 1)
    start = 0.0  # set once all workers are ready, so setup cost is not measured as latency

    def worker(i):
        rng = random.Random(base_rng.random() + i)
        try:
            ctx = make_ctx(i)
        except Exception as e:  # count, then drain this worker's share as errors
            ctx, ctx_err = None, f"connect: {type(e).__name__}: {e}"
        else:
            ctx_err = None
        ready.wait()
        while True:
            job = jobs.get()
            if job is None:
                break
            stage, sched, seq = job
            t0 = time.perf_counter()
            err = ctx_err
            if err is None:
                try:
                    op(ctx, rng, seq)
                except Exception as e:
                    err = f"{type(e).__name__}: {str(e).strip().splitlines()[0] if str(e).strip() else ''}"
            t1 = time.perf_counter()
            rec.record(stage, t1 - sched, t1 - t0, err)
            if max_errors and rec.total_errors >= max_errors:
                stop.set()
        if ctx is not None and close_ctx:
            try:
                close_ctx(ctx)
            except Exception:
                pass

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
    for t in threads:
        t.start()
    ready.wait()
    start = time.perf_counter() + 0.1

    current = {"stage": 0}

    def reporter():
        last = time.perf_counter()
        while not stop.is_set():
            time.sleep(1)
            now = time.perf_counter()
            win = rec.take_window()
            extra = ""
            if observer:
                try:
                    extra = " | " + observer()
                except Exception as e:
                    extra = f" | observer error: {e}"
            if progress:
                print(progress_line(max(0.0, now - start), stages[current["stage"]], win, now - last,
                                    jobs.qsize(), "backlog", extra), flush=True)
            last = now

    rep = threading.Thread(target=reporter, daemon=True)
    rep.start()

    seq = 0
    interrupted = False
    try:
        for stage, offset in arrivals(stages, poisson, random.Random(seed)):
            if stop.is_set():
                break
            current["stage"] = stage
            due = start + offset
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            rec.scheduled[stage] += 1
            if jobs.qsize() >= max_queue:
                rec.dropped[stage] += 1
                continue
            seq += 1
            jobs.put((stage, due, seq))
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted — draining in-flight work...", file=sys.stderr)
        while True:  # discard queued, not-yet-started work
            try:
                jobs.get_nowait()
            except queue.Empty:
                break
    for _ in threads:
        jobs.put(None)
    for t in threads:
        t.join()
    stop.set()
    rep.join(timeout=2)
    return rec, interrupted or (max_errors and rec.total_errors >= max_errors)


# --------------------------------------------------------------------------- report

def summarize(stages, rec):
    rows = []
    for i, st in enumerate(stages):
        res = rec.results[i]
        lat = sorted(r[0] for r in res)
        svc = sorted(r[1] for r in res)
        ok = sum(1 for r in res if r[2])
        rows.append({
            "stage": st.label,
            "duration_s": round(st.duration, 3),
            "target_rate": st.describe(),
            "scheduled": rec.scheduled[i],
            "completed": len(res),
            "ok": ok,
            "errors": len(res) - ok,
            "dropped": rec.dropped[i],
            "achieved_rate": round(len(res) / st.duration, 2) if st.duration else None,
            "latency_ms": {p: round(percentile(lat, q) * 1000, 2) if lat else None
                           for p, q in (("p50", 50), ("p95", 95), ("p99", 99), ("max", 100))},
            "service_ms_p95": round(percentile(svc, 95) * 1000, 2) if svc else None,
            "top_errors": sorted(rec.errors[i].items(), key=lambda kv: -kv[1])[:5],
        })
    return rows


def findings(rows):
    """Heuristic hints to point the investigation in the right direction."""
    notes = []
    if not rows:
        return notes
    base = rows[0]["latency_ms"]["p95"]
    for r in rows[1:]:
        p95, svc = r["latency_ms"]["p95"], r["service_ms_p95"]
        if base and p95 and p95 > 3 * base:
            notes.append(f"{r['stage']}: p95 {p95:.0f}ms is {p95 / base:.1f}x the baseline ({base:.0f}ms).")
        if p95 and svc and p95 > 2 * svc and p95 - svc > 50:
            notes.append(f"{r['stage']}: latency p95 {p95:.0f}ms >> service time p95 {svc:.0f}ms -> work is "
                         f"queueing for a worker/connection (pool or concurrency limit saturated).")
    for r in rows:
        if r["dropped"]:
            notes.append(f"{r['stage']}: {r['dropped']} arrivals dropped — client backlog limit hit (--max-queue / --overrun); "
                         f"the system could not keep up.")
        if r["errors"]:
            top = r["top_errors"][0][0] if r["top_errors"] else "?"
            notes.append(f"{r['stage']}: {r['errors']} errors (top: {top}).")
    last = rows[-1]
    if len(rows) > 2 and base and last["latency_ms"]["p95"] and last["latency_ms"]["p95"] > 2 * base:
        notes.append(f"{last['stage']}: latency did not recover after the load dropped "
                     f"(p95 {last['latency_ms']['p95']:.0f}ms vs baseline {base:.0f}ms) — look for backlog, "
                     f"leaked connections, lock queues, GC or cache that stays cold.")
    if not notes:
        notes.append("No saturation detected at this load. Increase --peak or shorten --hold to find the knee.")
    return notes


def print_report(title, stages, rec, config=None, json_path=None):
    rows = summarize(stages, rec)
    print(f"\n=== {title} ===")
    hdr = (f"{'stage':<10}{'target':>14}{'sched':>8}{'done':>8}{'err':>7}{'drop':>7}{'rate/s':>9}"
           f"{'p50':>8}{'p95':>8}{'p99':>8}{'max':>9}{'svc95':>8}")
    print(hdr + "   (latency in ms, measured from scheduled time)")
    print("-" * len(hdr))
    for r in rows:
        lm = r["latency_ms"]
        f = lambda v: "-" if v is None else f"{v:.0f}" if v >= 10 else f"{v:.1f}"
        print(f"{r['stage']:<10}{r['target_rate']:>14}{r['scheduled']:>8}{r['completed']:>8}{r['errors']:>7}"
              f"{r['dropped']:>7}{(r['achieved_rate'] or 0):>9.1f}{f(lm['p50']):>8}{f(lm['p95']):>8}"
              f"{f(lm['p99']):>8}{f(lm['max']):>9}{f(r['service_ms_p95']):>8}")
    notes = findings(rows)
    print("\nFindings:")
    for n in notes:
        print(f"  - {n}")
    if json_path:
        os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump({"title": title, "config": config or {}, "stages": rows, "findings": notes,
                       "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, fh, indent=2, default=str)
        print(f"\nJSON report written to {json_path}")
    return rows
