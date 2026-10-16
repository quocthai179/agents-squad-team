#!/usr/bin/env python3
"""http_burst — simulate sudden traffic spikes against a local/test HTTP service (stdlib only).

Use it to reproduce endpoint latency blow-ups, thread/worker pool exhaustion,
cache stampedes, downstream timeouts and slow recovery after a spike. For very
high rates (thousands of req/s) prefer k6 with the spike_http.js template.

Examples:
  # 20 req/s baseline, sudden 300 req/s for 30s, 50 concurrent client connections
  python http_burst.py --url "http://localhost:8080/api/orders?customer={{randint:1:50000}}" \\
      --concurrency 50 --shape spike --base 20 --peak 300

  # Cache stampede: everyone asks for the same few hot keys right after a deploy/cache flush
  python http_burst.py --url "http://localhost:8080/api/products/{{zipf:500:1.5}}" --shape spike --peak 500

  # POST with a JSON body, weighted mix of endpoints, no keep-alive (connection storm)
  python http_burst.py --url "7:GET http://localhost:8080/api/cart" \\
      --url "3:POST http://localhost:8080/api/checkout" --body '{"cartId": {{randint:1:1000}}}' \\
      -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" --no-keepalive

Templates: {{randint:A:B}} {{zipf:N:S}} {{seq}} {{uuid}} in URLs and bodies.
"""

import argparse
import http.client
import os
import ssl
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loadkit  # noqa: E402

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def parse_target(spec):
    weight, rest = loadkit.parse_weighted(spec)
    method, url = "GET", rest
    head, _, tail = rest.partition(" ")
    if head.upper() in METHODS and tail:
        method, url = head.upper(), tail.strip()
    return weight, method, loadkit.Template(url)


_TLS = {}


def tls_context(insecure):
    # Built once and shared: loading CA certs per worker is slow and would distort timings.
    if insecure not in _TLS:
        _TLS[insecure] = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    return _TLS[insecure]


class Client:
    """One keep-alive connection per (scheme, host, port) per worker."""

    def __init__(self, timeout, keepalive, insecure):
        self.timeout, self.keepalive, self.insecure = timeout, keepalive, insecure
        self.conns = {}

    def _conn(self, scheme, netloc):
        key = (scheme, netloc)
        conn = self.conns.get(key)
        if conn is None:
            if scheme == "https":
                conn = http.client.HTTPSConnection(netloc, timeout=self.timeout, context=tls_context(self.insecure))
            else:
                conn = http.client.HTTPConnection(netloc, timeout=self.timeout)
            self.conns[key] = conn
        return key, conn

    def request(self, method, url, body, headers):
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        hdrs = dict(headers)
        if not self.keepalive:
            hdrs["Connection"] = "close"
        key, conn = self._conn(parts.scheme, parts.netloc)
        try:
            conn.request(method, path, body=body, headers=hdrs)
            resp = conn.getresponse()
            resp.read()
            status = resp.status
        except Exception:
            conn.close()
            self.conns.pop(key, None)
            raise
        if not self.keepalive or resp.will_close:
            conn.close()
            self.conns.pop(key, None)
        return status

    def close(self):
        for c in self.conns.values():
            c.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", required=True,
                    help="target URL, optionally 'METHOD URL' and/or 'WEIGHT:...'; repeatable")
    ap.add_argument("-H", "--header", action="append", default=[], help="'Name: value'; repeatable")
    ap.add_argument("--body", help="request body (templated) for POST/PUT/PATCH")
    ap.add_argument("--concurrency", type=int, default=50, help="max concurrent requests (default 50)")
    ap.add_argument("--timeout", type=float, default=30, help="request timeout seconds (default 30)")
    ap.add_argument("--ok-status", default="200-399", help="status range counted as success (default 200-399)")
    ap.add_argument("--no-keepalive", action="store_true", help="new TCP/TLS connection per request")
    ap.add_argument("--insecure", action="store_true", help="skip TLS verification (self-signed dev certs)")
    ap.add_argument("--json", help="write the report as JSON to this path")
    loadkit.add_profile_args(ap)
    loadkit.add_safety_args(ap)
    args = ap.parse_args()

    targets = [parse_target(u) for u in args.url]
    for _, _, tpl in targets:
        sample = urlsplit(tpl.text)
        if sample.scheme not in ("http", "https"):
            ap.error(f"URL must start with http:// or https://: {tpl.text}")
        loadkit.guard_target(sample.hostname, args.i_own_this_target, "HTTP host")
    headers = {}
    for h in args.header:
        name, _, value = h.partition(":")
        headers[name.strip()] = value.strip()
    body_tpl = loadkit.Template(args.body) if args.body else None
    lo, _, hi = args.ok_status.partition("-")
    ok_lo, ok_hi = int(lo), int(hi or lo)
    stages = loadkit.stages_from_args(args)

    if any(urlsplit(t.text).scheme == "https" for _, _, t in targets):
        tls_context(args.insecure)

    def make_ctx(_i):
        return Client(args.timeout, not args.no_keepalive, args.insecure)

    def op(client, rng, seq):
        _, method, tpl = loadkit.pick_weighted([(w, (w, m, t)) for w, m, t in targets], rng)
        body = body_tpl.render(rng, seq).encode() if body_tpl and method in ("POST", "PUT", "PATCH") else None
        status = client.request(method, tpl.render(rng, seq), body, headers)
        if not ok_lo <= status <= ok_hi:
            raise RuntimeError(f"HTTP {status}")

    print(f"http_burst: concurrency={args.concurrency} targets={len(targets)} "
          f"stages={', '.join(f'{s.label}={s.duration:g}s@{s.describe()}' for s in stages)}")
    t0 = time.time()
    rec, aborted = loadkit.run_open_model(
        stages, args.concurrency, make_ctx, op, close_ctx=lambda c: c.close(),
        poisson=args.arrival == "poisson", max_queue=args.max_queue, max_errors=args.max_errors, seed=args.seed)
    config = {k: v for k, v in vars(args).items() if k != "header"}
    config["header_names"] = list(headers)  # never persist header values (tokens)
    config["wall_time_s"] = round(time.time() - t0, 1)
    loadkit.print_report("http_burst" + (" — ABORTED" if aborted else ""), stages, rec, config, args.json)


if __name__ == "__main__":
    main()
