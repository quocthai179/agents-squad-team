#!/usr/bin/env python3
"""db_burst — simulate sudden bursts of SQL queries against a local/test database.

Reproduces "it was fine until traffic jumped" problems: pool exhaustion, slow
queries that only hurt under concurrency, lock contention on hot rows,
connection storms, and latency that does not recover after the spike.

Drivers (install the one you need):
  PostgreSQL  postgresql://user:pass@host:5432/db   pip install "psycopg[binary]"  (or psycopg2-binary)
  MySQL       mysql://user:pass@host:3306/db        pip install pymysql
  SQLite      sqlite:///path/to/file.db             (stdlib)

Examples:
  # 10 q/s baseline, then a sudden 400 q/s spike for 30s, with 20 pooled connections
  python db_burst.py --dsn postgresql://app:app@localhost/app --pool 20 \\
      --query "SELECT * FROM orders WHERE customer_id = {{randint:1:50000}}" \\
      --shape spike --base 10 --peak 400 --observe

  # Hot-row lock contention (writes need --allow-write; local DB only)
  python db_burst.py --dsn postgresql://app:app@localhost/app --allow-write --pool 50 \\
      --query "UPDATE accounts SET balance = balance + 1 WHERE id = {{zipf:1000:1.3}}" \\
      --shape burst --base 5 --peak 300 --hold 10s

  # Connection storm: no pooling, a new connection per query
  python db_burst.py --dsn ... --connect-per-query --pool 200 --query "SELECT 1" --peak 500

Templates: {{randint:A:B}} {{zipf:N:S}} {{seq}} {{uuid}} (numbers/uuids only, safe to inline).
Weight queries with a prefix: --query "8:SELECT ..." --query "2:SELECT ...".
"""

import argparse
import os
import re
import sys
import time
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loadkit  # noqa: E402

WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|merge|upsert|replace|truncate|drop|alter|create|grant|revoke|vacuum|"
    r"reindex|cluster|copy|call|do|lock|refresh|set\s+role)\b", re.I)
COMMENTS = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.S)


def is_read_only(sql):
    body = COMMENTS.sub(" ", sql)
    body = re.sub(r"'(?:[^']|'')*'", "''", body)  # ignore string literals
    first = body.strip().split(None, 1)[0].lower() if body.strip() else ""
    return first in {"select", "with", "explain", "show", "values", "table", "describe", "desc"} \
        and not WRITE_WORDS.search(body)


# --------------------------------------------------------------------------- drivers

def driver_for(dsn):
    scheme = urlparse(dsn).scheme.split("+")[0].lower()
    if scheme in ("postgres", "postgresql"):
        return "postgres"
    if scheme in ("mysql", "mariadb"):
        return "mysql"
    if scheme == "sqlite":
        return "sqlite"
    sys.exit(f"Unsupported DSN scheme '{scheme}'. Use postgresql://, mysql:// or sqlite:///")


def connect(dsn, kind, read_only, timeout_ms):
    if kind == "postgres":
        clean = dsn.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
        try:
            import psycopg
            conn = psycopg.connect(clean, autocommit=True)
        except ImportError:
            try:
                import psycopg2
            except ImportError:
                sys.exit('PostgreSQL driver missing: pip install "psycopg[binary]"  (or psycopg2-binary)')
            conn = psycopg2.connect(clean)
            conn.autocommit = True
        with conn.cursor() as cur:
            if read_only:
                cur.execute("SET default_transaction_read_only = on")
            if timeout_ms:
                cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
        return conn
    if kind == "mysql":
        try:
            import pymysql
        except ImportError:
            sys.exit("MySQL driver missing: pip install pymysql")
        u = urlparse(dsn)
        conn = pymysql.connect(host=u.hostname or "localhost", port=u.port or 3306,
                               user=unquote(u.username or ""), password=unquote(u.password or ""),
                               database=(u.path or "/").lstrip("/") or None, autocommit=True)
        with conn.cursor() as cur:
            if read_only:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            if timeout_ms:
                cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")
        return conn
    import sqlite3
    path = dsn[len("sqlite:///"):] if dsn.startswith("sqlite:///") else urlparse(dsn).path
    mode = "ro" if read_only else "rw"
    conn = sqlite3.connect(f"file:{path}?mode={mode}", uri=True, check_same_thread=False,
                           timeout=(timeout_ms or 5000) / 1000, isolation_level=None)
    return conn


def run_query(conn, sql, fetch):
    cur = conn.cursor()
    try:
        cur.execute(sql)
        if fetch and cur.description is not None:
            cur.fetchall()
    finally:
        cur.close()


# --------------------------------------------------------------------------- observers

def make_observer(dsn, kind, timeout_ms):
    """Server-side view sampled each second: active sessions, lock waits, etc."""
    if kind == "sqlite":
        return None
    conn = connect(dsn, kind, True, timeout_ms)
    if kind == "postgres":
        sql = ("SELECT count(*) FILTER (WHERE state = 'active'), "
               "count(*) FILTER (WHERE state = 'idle in transaction'), "
               "count(*) FILTER (WHERE wait_event_type = 'Lock'), count(*), "
               "current_setting('max_connections')::int "
               "FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()")

        def observe():
            cur = conn.cursor()
            cur.execute(sql)
            active, idle_tx, lock_wait, total, max_conn = cur.fetchone()
            cur.close()
            return (f"pg active={active} lock_wait={lock_wait} idle_in_tx={idle_tx} "
                    f"conns={total}/{max_conn}")
        return observe

    def observe():
        cur = conn.cursor()
        cur.execute("SHOW GLOBAL STATUS WHERE Variable_name IN "
                    "('Threads_running','Threads_connected','Innodb_row_lock_current_waits')")
        vals = {k: v for k, v in cur.fetchall()}
        cur.close()
        return (f"mysql running={vals.get('Threads_running')} connected={vals.get('Threads_connected')} "
                f"row_lock_waits={vals.get('Innodb_row_lock_current_waits')}")
    return observe


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", required=True, help="database URL (see above)")
    ap.add_argument("--query", action="append", default=[], help="SQL to run; repeatable; 'W:SQL' sets a weight")
    ap.add_argument("--query-file", help="file with one query per line (blank lines and # comments ignored)")
    ap.add_argument("--pool", type=int, default=10, help="concurrent connections = app pool size (default 10)")
    ap.add_argument("--connect-per-query", action="store_true",
                    help="open/close a connection for every query (simulates no pooling / connection storms)")
    ap.add_argument("--allow-write", action="store_true", help="permit DML/DDL (local/test databases only)")
    ap.add_argument("--timeout-ms", type=int, default=0, help="per-statement timeout (0 = none)")
    ap.add_argument("--no-fetch", action="store_true", help="do not fetch result rows")
    ap.add_argument("--observe", action="store_true", help="sample server-side activity every second")
    ap.add_argument("--json", help="write the report as JSON to this path")
    loadkit.add_profile_args(ap)
    loadkit.add_safety_args(ap)
    args = ap.parse_args()

    specs = list(args.query)
    if args.query_file:
        with open(args.query_file, encoding="utf-8") as fh:
            specs += [ln for ln in (x.strip() for x in fh) if ln and not ln.startswith("#")]
    if not specs:
        ap.error("give at least one --query or --query-file")
    queries = [(w, loadkit.Template(q)) for w, q in map(loadkit.parse_weighted, specs)]

    if not args.allow_write:
        bad = [t.text for _, t in queries if not is_read_only(t.text)]
        if bad:
            sys.exit("Write or non-SELECT statement(s) found; pass --allow-write (local/test DB only):\n  "
                     + "\n  ".join(bad))

    kind = driver_for(args.dsn)
    if kind != "sqlite":
        loadkit.guard_target(urlparse(args.dsn).hostname, args.i_own_this_target, "database")
    read_only = not args.allow_write
    stages = loadkit.stages_from_args(args)

    def make_ctx(_i):
        return None if args.connect_per_query else connect(args.dsn, kind, read_only, args.timeout_ms)

    def op(conn, rng, seq):
        sql = loadkit.pick_weighted(queries, rng).render(rng, seq)
        if conn is None:
            c = connect(args.dsn, kind, read_only, args.timeout_ms)
            try:
                run_query(c, sql, not args.no_fetch)
            finally:
                c.close()
        else:
            run_query(conn, sql, not args.no_fetch)

    observer = make_observer(args.dsn, kind, args.timeout_ms) if args.observe else None
    print(f"db_burst: {kind} pool={args.pool} queries={len(queries)} "
          f"stages={', '.join(f'{s.label}={s.duration:g}s@{s.describe()}' for s in stages)}")
    t0 = time.time()
    rec, aborted = loadkit.run_open_model(
        stages, args.pool, make_ctx, op, close_ctx=lambda c: c.close(),
        poisson=args.arrival == "poisson", max_queue=args.max_queue, max_errors=args.max_errors,
        seed=args.seed, observer=observer)
    config = {k: v for k, v in vars(args).items() if k != "dsn"}
    config["dsn_host"] = urlparse(args.dsn).hostname
    config["wall_time_s"] = round(time.time() - t0, 1)
    loadkit.print_report(f"db_burst ({kind})" + (" — ABORTED" if aborted else ""), stages, rec, config, args.json)


if __name__ == "__main__":
    main()
