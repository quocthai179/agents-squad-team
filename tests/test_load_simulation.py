"""Unit tests for the load-simulation engine (stdlib only: python -m unittest discover -s tests)."""

import os
import random
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "plugins", "dev-squad", "skills", "load-simulation", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))

import db_burst  # noqa: E402
import loadkit  # noqa: E402


def counts(spec, poisson=False, seed=1):
    stages = loadkit.parse_profile(spec)
    c = [0] * len(stages)
    for i, _ in loadkit.arrivals(stages, poisson, random.Random(seed)):
        c[i] += 1
    return c


class ProfileTests(unittest.TestCase):
    def test_parse_profile(self):
        st = loadkit.parse_profile("30s:10,500ms:10->400,2m:0")
        self.assertEqual([(s.duration, s.start_rate, s.end_rate) for s in st],
                         [(30, 10, 10), (0.5, 10, 400), (120, 0, 0)])

    def test_bad_profile(self):
        for bad in ("", "10:abc", "x:10", "10s:-1"):
            with self.assertRaises(ValueError):
                loadkit.parse_profile(bad)

    def test_constant_rate_counts(self):
        self.assertEqual(counts("2s:10"), [19])

    def test_ramp_from_zero_produces_arrivals(self):
        self.assertEqual(counts("3s:0->5"), [7])

    def test_ramp_down(self):
        self.assertEqual(counts("2s:100->0"), [99])

    def test_zero_stage_is_idle(self):
        self.assertEqual(counts("2s:0,1s:10"), [0, 9])

    def test_ramp_density_follows_rate(self):
        offs = [o for _, o in loadkit.arrivals(loadkit.parse_profile("4s:0->100"))]
        self.assertLess(sum(o < 1 for o in offs), sum(o >= 3 for o in offs))

    def test_poisson_ramp_mean(self):
        total = sum(counts("2s:0->1000", poisson=True, seed=s)[0] for s in range(10)) / 10
        self.assertAlmostEqual(total, 1000, delta=60)

    def test_presets(self):
        spike = loadkit.preset_stages("spike", 10, 100, 2, 1, 2)
        self.assertEqual([s.label for s in spike], ["baseline", "spike", "recovery"])
        burst = loadkit.preset_stages("burst", 5, 50, 1, 1, 3, repeat=2, gap=1)
        self.assertEqual([s.label for s in burst], ["baseline", "burst1", "gap1", "burst2", "recovery"])


class TemplateTests(unittest.TestCase):
    def test_tokens(self):
        rng = random.Random(3)
        out = loadkit.Template("a={{randint:5:9}} b={{zipf:100:1.3}} c={{seq}}").render(rng, 42)
        parts = dict(p.split("=") for p in out.split())
        self.assertTrue(5 <= int(parts["a"]) <= 9)
        self.assertTrue(1 <= int(parts["b"]) <= 100)
        self.assertEqual(parts["c"], "42")

    def test_zipf_is_skewed(self):
        rng = random.Random(1)
        tpl = loadkit.Template("{{zipf:1000:1.5}}")
        hits = [int(tpl.render(rng, 0)) for _ in range(5000)]
        self.assertGreater(sum(h <= 10 for h in hits) / len(hits), 0.5)

    def test_weighted(self):
        self.assertEqual(loadkit.parse_weighted("3:SELECT 1"), (3.0, "SELECT 1"))
        self.assertEqual(loadkit.parse_weighted("http://x/y"), (1.0, "http://x/y"))
        self.assertEqual(loadkit.parse_weighted("SELECT '1:2'"), (1.0, "SELECT '1:2'"))


class SafetyTests(unittest.TestCase):
    def test_local_hosts_allowed(self):
        for h in ("localhost", "127.0.0.1", "::1", "[::1]"):
            loadkit.guard_target(h)

    def test_remote_refused(self):
        os.environ.pop(loadkit.ALLOW_ENV, None)
        with self.assertRaises(SystemExit):
            loadkit.guard_target("prod-db.internal")

    def test_allow_env(self):
        os.environ[loadkit.ALLOW_ENV] = "staging-db, other"
        try:
            loadkit.guard_target("staging-db")
        finally:
            os.environ.pop(loadkit.ALLOW_ENV)

    def test_read_only_detection(self):
        ok = ["SELECT * FROM t WHERE id = 1", "with x as (select 1) select * from x",
              "SELECT 'please delete me' FROM t", "-- update\nSELECT 1", "EXPLAIN SELECT 1"]
        bad = ["UPDATE t SET a = 1", "WITH x AS (DELETE FROM t RETURNING *) SELECT 1",
               "BEGIN; UPDATE t SET a=1; COMMIT", "EXPLAIN ANALYZE DELETE FROM t", "TRUNCATE t", "DROP TABLE t"]
        for q in ok:
            self.assertTrue(db_burst.is_read_only(q), q)
        for q in bad:
            self.assertFalse(db_burst.is_read_only(q), q)


class RunnerTests(unittest.TestCase):
    def test_open_model_queueing_is_measured(self):
        import time

        def op(ctx, rng, seq):
            time.sleep(0.02)
            if seq % 10 == 0:
                raise RuntimeError("boom")

        stages = loadkit.parse_profile("1s:20,1s:200")
        rec, aborted = loadkit.run_open_model(stages, 2, lambda i: None, op, progress=False, seed=1)
        rows = loadkit.summarize(stages, rec)
        self.assertFalse(aborted)
        self.assertEqual(rows[0]["completed"], 19)
        self.assertEqual(rows[1]["completed"] + rows[1]["dropped"], 199)
        self.assertGreater(rows[1]["errors"], 0)
        # 2 workers x 20ms = ~100 ops/s capacity < 200/s: latency must exceed service time
        self.assertGreater(rows[1]["latency_ms"]["p95"], 2 * rows[1]["service_ms_p95"])
        self.assertTrue(any("queueing" in f for f in loadkit.findings(rows)))


if __name__ == "__main__":
    unittest.main()
