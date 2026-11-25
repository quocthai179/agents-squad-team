#!/usr/bin/env python3
"""diff_guard: check a hotfix diff against its approved fix plan (stdlib only).

It does not count a line budget. It reports drift from the approved plan:

  hard (exit 1)  plan changed after approval (hash mismatch), plan not approved, base moved, HEAD not
                 based on the approved base, replace refs or grafts; with --committed also: dirty tree,
                 no commit or more than one commit, merge commit, path changed only in history, tag on
                 the hotfix commit, unpublished base, artifact that is not a plain file;
                 file outside the plan, new non-test file, deleted / renamed file, mode change,
                 symlink, submodule change, binary change outside a test file, unreadable file,
                 format-only hunk, unjustified hunk, justification row much wider than its hunks,
                 unknown edit id, edit/file mismatch, forbidden category (dependency, migration,
                 ci, config), any .squad/ file that is not a known hotfix artifact
  warning        size well over the plan's estimate, reorder-, import- or comment-only hunks,
                 whitespace-only change inside a string, existing test lines removed or changed,
                 a new test recognised only by its directory, a plan 'tests' entry that does not
                 look like a test, one row covering several hunks, planned edit not touched,
                 stale row, base not pinned to a SHA, 'allow' ignored at prod; with --committed also:
                 active git hooks and the push config, listed in full for the user

The guard checks files and hunks, not symbols: the reviewer checks that each hunk stays in the
planned symbol.

Usage:
  diff_guard.py --plan .squad/hotfix/<slug>/fix-plan.json --print-plan-sha256
  diff_guard.py --plan .squad/hotfix/<slug>/fix-plan.json --plan-sha256 <hex> \
                --hunks .squad/hotfix/<slug>/hunks.md [--json out.json] [--md out.md]
  diff_guard.py ... --committed      # authoritative: the committed HEAD, clean tree required
  diff_guard.py ... --unpinned       # an agent's self-check: never reports a plain PASS

Exit codes: 0 no hard violation, 1 hard violation(s), 2 bad input or internal error.
"""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys

LEVELS = ("release", "prod")
CATEGORIES = ("dependency", "migration", "ci", "config")
DEFAULT_WARN_RATIO = 2.0
WARN_SLACK = 5         # never warn about size when the diff is within this many lines of the estimate
ROW_SLACK = 5          # a justification row may extend this many lines beyond the hunks it covers
MAX_READ = 2_000_000   # untracked files larger than this are treated as binary
MAX_TEXT = 200         # input strings echoed into the Markdown report are cut to this length

TEST_DIR_RE = re.compile(r"(^|/)(tests?|__tests__|specs?|src/test|src/androidTest|src/[A-Za-z]+Test)(/|$)")
TEST_NAME_RE = re.compile(
    r"(^|/)test_[^/]*\.py$|_test\.(py|go|rb|exs?)$|_spec\.rb$"
    r"|\.(test|spec)\.[cm]?[jt]sx?$"
    r"|[a-z0-9](Test|Tests|IT)\.(java|kt|scala|cs|groovy|swift)$"
)
PRODUCTION_ROOT_RE = re.compile(r"(^|/)src/main/")
# Paths under a test directory still count for these categories: a lockfile or a pipeline is never a test.
STRUCTURAL = ("dependency", "ci")

DEPENDENCY_NAMES = {
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.lockfile",
    "libs.versions.toml", "go.mod", "go.sum", "pyproject.toml", "poetry.lock", "pipfile", "pipfile.lock",
    "setup.py", "setup.cfg", "uv.lock", "cargo.toml", "cargo.lock", "gemfile", "gemfile.lock",
    "composer.json", "composer.lock", "packages.config", "directory.packages.props", "mix.exs", "mix.lock",
    ".gitmodules",
}
MIGRATION_RE = re.compile(
    r"(^|/)(migrations?|migrate|alembic/versions|db/changelog|liquibase|flyway)(/|$)|(^|/)schema\.prisma$"
    r"|(^|/)V\d+[_.][^/]*\.sql$"
)
CI_RE = re.compile(
    r"(^|/)\.github/workflows/|(^|/)\.gitlab-ci\.ya?ml$|(^|/)\.gitlab/ci/|(^|/)Jenkinsfile$|(^|/)\.circleci/"
    r"|(^|/)azure-pipelines\.ya?ml$|(^|/)\.buildkite/|(^|/)bitbucket-pipelines\.yml$|(^|/)\.drone\.yml$"
)
CONFIG_RE = re.compile(
    r"(^|/)application[^/]*\.(ya?ml|properties)$|(^|/)appsettings[^/]*\.json$|(^|/)\.env[^/]*$"
    r"|(^|/)(config|conf|configs|settings)/[^/]*\.(ya?ml|json|toml|ini|properties|conf|env)$"
    r"|(^|/)values[^/]*\.ya?ml$|\.tfvars$"
)
IMPORT_RE = re.compile(
    r"^\s*(import\b|from\s+\S+\s+import\b|#\s*include\b|using\s+[\w.]+\s*;|package\s+[\w.]+\s*;?$"
    r"|(const|let|var)\s[^=]*=\s*require\(|require\s*\(|use\s+[\w:\\]+)"
)
COMMENT_RE = re.compile(r"^\s*(//|/\*|\*\s|\*/|#(?!\s*include)|<!--|;;)")
INDENT_SENSITIVE_RE = re.compile(r"\.(py|pyi|ya?ml|haml|pug|jade|coffee|sass|styl|nim|fs|fsx)$|(^|/)(Makefile|[^/]*\.mk)$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
ROW_REF_RE = re.compile(r"^`?(?P<path>[^`|]+?)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?`?$")
ARTIFACT_NAMES = re.compile(r"^(fix-plan\.(md|json)|hunks\.md|deferred\.md|guard\.(md|json)|REVIEW-PACKET\.md)$")
IGNORED_SQUAD = (".squad/tmp/", ".squad/reports/")
# Set from the --plan path: only this hotfix's own artifacts are ignored.
SLUG_DIR = {"value": None}


class InputError(Exception):
    pass


# ---------------------------------------------------------------- classification

def is_artifact(path):
    slug = SLUG_DIR["value"]
    if slug is None:  # the plan is not in .squad/hotfix/<slug>/: exempt nothing
        return False
    return os.path.dirname(path) == slug and bool(ARTIFACT_NAMES.match(os.path.basename(path)))


def is_ignored(path, committed=False):
    """Uncommitted scratch (.squad/tmp, .squad/reports) is ignored only in the working tree, never in a commit."""
    return is_artifact(path) or (not committed and path.startswith(IGNORED_SQUAD))


def record_ignored(f, committed=False):
    """A record is skipped only when both sides are ignored: a rename into an artifact is a change."""
    return is_ignored(f["path"], committed) and is_ignored(f["old_path"], committed)


def test_kind(path, extra=()):
    """'name' (test by file name), 'dir' (only by directory), 'plan' (listed in the plan) or None."""
    if PRODUCTION_ROOT_RE.search(path):
        return "plan" if path in extra else None
    if TEST_NAME_RE.search(path):
        return "name"
    if TEST_DIR_RE.search(path):
        return "dir"
    if path in extra:
        return "plan"
    return None


def is_test(path, extra=()):
    return test_kind(path, extra) is not None


def category(path):
    name = os.path.basename(path).lower()
    if name in DEPENDENCY_NAMES or (name.startswith("requirements") and name.endswith((".txt", ".in"))) \
            or name.endswith((".csproj", ".fsproj", ".vbproj")):
        return "dependency"
    if MIGRATION_RE.search(path):
        return "migration"
    if CI_RE.search(path):
        return "ci"
    if CONFIG_RE.search(path):
        return "config"
    return None


def norm(line, keep_indent=False):
    body = "".join(line.split())
    if keep_indent and body:
        return line[:len(line) - len(line.lstrip())] + body
    return body


def hunk_kind(removed, added, indent_sensitive=False):
    """Classify a hunk: format, string-space, reorder, import, comment or None (a real change)."""
    if "".join(norm(x, indent_sensitive) for x in removed) == "".join(norm(x, indent_sensitive) for x in added):
        changed = [x for x in removed + added if x.strip()]
        if removed and added and any(q in x for x in changed for q in "\"'`") \
                and not all(COMMENT_RE.match(x) for x in changed):
            return "string-space"  # whitespace may sit inside a string literal: a real change
        return "format"
    r = [norm(x, indent_sensitive) for x in removed if norm(x)]
    a = [norm(x, indent_sensitive) for x in added if norm(x)]
    if r and sorted(r) == sorted(a):
        return "reorder"
    changed = [x for x in removed + added if x.strip()]
    if changed and all(IMPORT_RE.match(x) for x in changed):
        return "import"
    if changed and all(COMMENT_RE.match(x) for x in changed):
        return "comment"
    return None


def one_line(value):
    """Neutralise an input string before it goes into Markdown prose."""
    text = " ".join(str(value).split())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"([\\`|*_\[\]#])", r"\\\1", text)
    return text[:MAX_TEXT] + ("…" if len(text) > MAX_TEXT else "")


def code(value, limit=MAX_TEXT):
    """Neutralise an input string before it goes into a Markdown code span (limit=None: never cut)."""
    text = str(value).replace("\n", "\\n").replace("\t", " ").replace("`", "'")
    if limit is None:
        return "`" + text + "`"
    text = " ".join(text.split())
    return "`" + text[:limit] + ("…" if len(text) > limit else "") + "`"


# ---------------------------------------------------------------- diff parsing

C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def unquote(path):
    """Undo git's C-style quoting of unusual paths ("a\\303\\251.txt"), working on bytes."""
    if not (len(path) >= 2 and path[0] == '"' and path[-1] == '"'):
        return path
    inner, out, i = path[1:-1], bytearray(), 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if re.fullmatch(r"[0-7]{3}", inner[i + 1:i + 4]):
                out.append(int(inner[i + 1:i + 4], 8))
                i += 4
                continue
            if nxt in C_ESCAPES:
                out.append(C_ESCAPES[nxt])
                i += 2
                continue
        out += ch.encode("utf-8")
        i += 1
    return out.decode("utf-8", "replace")


def clean(path):
    path = path.strip()
    return path[2:] if path.startswith("./") else path


def strip_prefix(path):
    path = unquote(path.strip())
    return path[2:] if path[:2] in ("a/", "b/") else path


def new_record(path):
    return {"path": path, "old_path": path, "status": "modified", "binary": False, "mode_change": False,
            "symlink": False, "submodule": False, "unreadable": False, "hunks": []}


def parse_diff(text):
    """Parse a unified diff with a/ and b/ prefixes into file records.

    Hunks are split at context lines, so each record hunk covers only changed lines whatever the
    context size, and every header's line counts are checked against its body.
    """
    files = []
    cur = None
    state = None  # current @@ block: next old/new line, remaining counts, open sub-hunk

    def close_block():
        if state is None:
            return
        flush()
        if state["old_left"] != 0 or state["new_left"] != 0:
            raise InputError(f"malformed diff: a hunk in {cur['path']} does not match its @@ line counts")

    def flush():
        sub = state["sub"]
        if sub is None:
            return
        sub["new_start"] = sub["n0"] if sub["added"] else sub["n0"] - 1
        sub["old_start"] = sub["o0"] if sub["removed"] else sub["o0"] - 1
        sub["new_count"], sub["old_count"] = len(sub["added"]), len(sub["removed"])
        cur["hunks"].append(sub)
        state["sub"] = None

    def open_sub():
        if state["sub"] is None:
            state["sub"] = {"o0": state["o"], "n0": state["n"], "removed": [], "added": []}
        return state["sub"]

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line in lines:  # not splitlines(): form feeds and Unicode separators are part of a line
        if line.startswith("diff --git "):
            close_block()
            state = None
            rest = line[len("diff --git "):]
            half = len(rest) // 2
            guess = strip_prefix(rest[half + 1:]) if rest[:half] == rest[half + 1:].replace("b/", "a/", 1) else ""
            cur = new_record(guess)
            files.append(cur)
            continue
        if cur is None:
            continue
        in_body = state is not None and (state["old_left"] > 0 or state["new_left"] > 0)
        if in_body and line[:1] in ("+", "-", " ", "\\", ""):
            if line.startswith("\\"):
                continue
            if line.startswith("+"):
                open_sub()["added"].append(line[1:])
                state["n"] += 1
                state["new_left"] -= 1
            elif line.startswith("-"):
                open_sub()["removed"].append(line[1:])
                state["o"] += 1
                state["old_left"] -= 1
            else:  # context line (an empty line is a context line whose space was stripped)
                flush()
                state["o"] += 1
                state["n"] += 1
                state["old_left"] -= 1
                state["new_left"] -= 1
            if state["old_left"] < 0 or state["new_left"] < 0:
                raise InputError(f"malformed diff: a hunk in {cur['path']} is longer than its @@ line counts")
            continue
        m = HUNK_RE.match(line)
        if m:
            close_block()
            old_start, new_start = int(m.group(1)), int(m.group(3))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            state = {"o": old_start if old_count else old_start + 1, "n": new_start if new_count else new_start + 1,
                     "old_left": old_count, "new_left": new_count, "sub": None}
            continue
        if line.startswith(("+", "-")) and not line.startswith(("+++ ", "--- ")):
            raise InputError(f"malformed diff: a change line in {cur['path']} outside any hunk")
        if line.startswith("new file mode"):
            cur["status"] = "added"
            cur["executable"] = line.endswith("100755")
            cur["symlink"] |= line.endswith("120000")
            cur["submodule"] |= line.endswith("160000")
        elif line.startswith("deleted file mode"):
            cur["status"] = "deleted"
            cur["submodule"] |= line.endswith("160000")
        elif line.startswith(("old mode", "new mode")):
            cur["mode_change"] = True
            cur["symlink"] |= line.endswith("120000")
            cur["submodule"] |= line.endswith("160000")
        elif line.startswith("index "):
            cur["symlink"] |= line.endswith(" 120000")
            cur["submodule"] |= line.endswith(" 160000")
        elif line.startswith("rename from "):
            cur["status"] = "renamed"
            cur["old_path"] = unquote(line[len("rename from "):])
        elif line.startswith("rename to "):
            cur["path"] = unquote(line[len("rename to "):])
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            cur["binary"] = True
        elif line.startswith("--- "):
            if line[4:] != "/dev/null":
                cur["old_path"] = strip_prefix(line[4:])
        elif line.startswith("+++ "):
            cur["path"] = strip_prefix(line[4:]) if line[4:] != "/dev/null" else cur["old_path"]
    if cur is not None:
        close_block()
    for f in files:
        if any("\0" in x for h in f["hunks"] for x in h["added"] + h["removed"]):
            f["binary"] = True
    return files


def untracked_as_added(paths, root="."):
    """Turn untracked files into 'added' records without following symlinks or reading huge files."""
    out = []
    for path in paths:
        rec = new_record(path.rstrip("/"))
        rec["status"] = "added"
        full = os.path.join(root, path)
        if path.endswith("/") or os.path.isdir(os.path.join(full, ".git")):
            rec["submodule"] = True  # a nested repository: `git add` records it as a gitlink
            out.append(rec)
            continue
        try:
            st = os.lstat(full)
            if os.path.islink(full):
                rec["symlink"] = True
            elif not os.path.isfile(full) or st.st_size > MAX_READ:
                rec["binary"] = True
            else:
                rec["executable"] = bool(st.st_mode & 0o111)
                with open(full, "rb") as fh:
                    data = fh.read(MAX_READ + 1)
                if b"\0" in data:
                    rec["binary"] = True
                else:
                    lines = data.decode("utf-8", "replace").split("\n")
                    if lines and lines[-1] == "":
                        lines.pop()
                    if lines:
                        rec["hunks"] = [{"old_start": 0, "old_count": 0, "new_start": 1, "new_count": len(lines),
                                         "removed": [], "added": lines}]
        except OSError:
            rec["unreadable"] = True
        out.append(rec)
    return out


# Settings that change what `git diff` shows. Repository config and the environment are writable
# by the agents this guard checks, so they are overridden or dropped.
GIT_PINNED = ["-c", "core.quotepath=false", "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
              "-c", "diff.relative=false", "-c", "color.diff=false", "-c", "diff.interHunkContext=0",
              "-c", "diff.ignoreSubmodules=none", "-c", "diff.submodule=short", "-c", "diff.renames=true",
              "-c", "diff.suppressBlankEmpty=false", "-c", "core.attributesFile=" + os.devnull,
              "-c", "core.useReplaceRefs=false", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
              "-c", "core.commitGraph=false", "-c", "advice.graftFileDeprecated=false"]


def git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS="1",
               GIT_GRAFT_FILE=os.devnull)
    return env


def git(*args, cwd=None, raw=False):
    res = subprocess.run(["git", *GIT_PINNED, *args], capture_output=True, cwd=cwd, env=git_env())
    if res.returncode != 0:
        raise InputError(f"git {' '.join(args)} failed: {res.stderr.decode('utf-8', 'replace').strip()}")
    return res.stdout if raw else res.stdout.decode("utf-8", "replace")


def resolve_base(base):
    if not base or base.startswith("-") or any(c.isspace() for c in base):
        raise InputError(f"invalid base ref {base!r}")
    try:
        return git("rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}").strip()
    except InputError as exc:
        hint = (" (git refuses this repository: global config, including safe.directory, is ignored by the guard;"
                " run it as the repository's owner)") if "dubious ownership" in str(exc) else ""
        raise InputError(f"base ref {base!r} does not name a commit{hint}: {exc}")


DIFF_FLAGS = ["--no-color", "--no-ext-diff", "--no-textconv", "--text", "--src-prefix=a/", "--dst-prefix=b/",
              "--ignore-submodules=none", "--submodule=short", "-U0", "-M"]


def names(root, *args):
    raw = git("diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=none", *args, cwd=root, raw=True)
    return {os.fsdecode(p) for p in raw.split(b"\0") if p}


def collect_diff(base_sha, committed=False, base_name=None):
    """Diff the approved base against HEAD (committed=True) or against the working tree.

    Returns (file records, meta); meta["hard"] holds repository-level violations.
    """
    root = git("rev-parse", "--show-toplevel").strip()
    hard = []
    if git("for-each-ref", "--format=%(refname)", "refs/replace/", cwd=root).strip():
        hard.append(("replace-refs", None, "refs/replace/ exists: local git output (yours and the reviewer's) can show fake history"))
    common = git("rev-parse", "--git-common-dir", cwd=root).strip()  # --git-path would honour GIT_GRAFT_FILE
    if os.path.exists(os.path.join(root, common, "info", "grafts")):
        hard.append(("replace-refs", None, "info/grafts exists: local git output can show fake history"))
    head = git("rev-parse", "--verify", "HEAD", cwd=root).strip()
    try:
        merge_base = git("merge-base", base_sha, "HEAD", cwd=root).strip()
    except InputError:
        raise InputError(f"HEAD and the approved base {base_sha[:12]} share no history")
    if merge_base != base_sha:
        hard.append(("not-based-on-approved-base", None,
                     f"HEAD does not descend from the approved base {base_sha[:12]} (merge base {merge_base[:12]})"))
    if committed:
        raw = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none", cwd=root, raw=True)
        dirty, parts = [], raw.split(b"\0")
        i = 0
        while i < len(parts):
            entry = parts[i]
            i += 1
            if not entry:
                continue
            path = os.fsdecode(entry[3:])
            if entry[:1] in (b"R", b"C"):
                i += 1  # the original path follows a rename or copy
            if not is_ignored(path):  # uncommitted scratch is not pushed, so it does not make the tree dirty
                dirty.append(path)
        for path in dirty:
            hard.append(("dirty-tree", path, "uncommitted change: --committed checks HEAD, so commit or remove it first"))
        # read the trees from the commit objects themselves, not from any cache
        trees = [tree_of(root, c) for c in (merge_base, head)]
        text = git("diff", *DIFF_FLAGS, trees[0], trees[1], "--", cwd=root)
        files = parse_diff(text)
        count = int(git("rev-list", "--count", f"{merge_base}..{head}", cwd=root).strip() or 0)
        if count == 0:
            hard.append(("no-commits-since-base", None, "HEAD is the base: there is nothing committed to push"))
        elif count > 1:
            hard.append(("multiple-commits", None, f"{count} commits since the base: squash them into one, because"
                                                   " intermediate commits are pushed too and may hold content the final diff no longer shows"))
        if git("rev-list", "--merges", f"{merge_base}..{head}", cwd=root).strip():
            hard.append(("merge-commit", None, "merge commits since the base: a hotfix is a linear series of commits"))
        final = {f["path"] for f in files} | {f["old_path"] for f in files}
        raw = git("log", "--format=", "--name-only", "-z", "--no-renames", "-m", f"{merge_base}..{head}", cwd=root, raw=True)
        for path in sorted({os.fsdecode(p.strip(b"\n")) for p in raw.split(b"\0") if p.strip(b"\n")} - final):
            if not is_ignored(path, committed=True):
                hard.append(("history-only-change", path, "changed in an intermediate commit but not in the final diff: "
                                                          "it is still pushed in the history"))
        # Hooks run under the user's real config (global and system included), so read them with it.
        def real_git(*a):
            return subprocess.run(["git", *a], capture_output=True, text=True, cwd=root).stdout.strip()
        hooks_dir = real_git("rev-parse", "--git-path", "hooks")
        hooks_dir = os.path.join(root, hooks_dir) if not os.path.isabs(hooks_dir) else hooks_dir
        hooks_path = real_git("config", "--get", "core.hooksPath")
        # Everything in the repository's own config (agents can write it), plus push-related keys from any scope.
        # Parsed with -z: a value may hold newlines or other separators that would hide the rest of a command.
        raw_cfg = subprocess.run(["git", "config", "--show-origin", "--show-scope", "-z", "--list"],
                                 capture_output=True, cwd=root).stdout.decode("utf-8", "replace").split("\0")
        push_config = []
        for i in range(0, len(raw_cfg) - 2, 3):
            scope, origin, entry = raw_cfg[i], raw_cfg[i + 1], raw_cfg[i + 2]
            key, _, value = entry.partition("\n")
            if scope in ("local", "worktree") or PUSH_KEY_RE.fullmatch(key):
                push_config.append(f"{scope} {origin} {key}={redact(key, value)}")
        tags = git("for-each-ref", "--format=%(refname)", f"--points-at={head}", "refs/tags/", cwd=root).split()
        for t in tags:
            hard.append(("tag-on-hotfix", t, "a tag points at the hotfix commit: a push with followTags would send it;"
                                             " delete the tag"))
        published = f"refs/remotes/origin/{base_name}" if base_name else "refs/remotes/"
        if not git("for-each-ref", "--count=1", f"--contains={base_sha}", "--format=%(refname)", published, cwd=root).strip():
            hard.append(("base-not-published", None, f"the approved base {base_sha[:12]} is on no remote-tracking branch:"
                                                     " unpublished commits below it would be pushed too (fetch, and take the base from origin/<branch>)"))
        # The remote-tracking ref is local data an agent can write: hotfix.md also checks `git ls-remote` before the push.
        active = sorted(n for n in (os.listdir(hooks_dir) if os.path.isdir(hooks_dir) else [])
                        if not n.endswith(".sample") and os.access(os.path.join(hooks_dir, n), os.X_OK))
    else:
        text = git("diff", *DIFF_FLAGS, merge_base, "--", cwd=root)
        raw = git("ls-files", "-z", "--others", "--exclude-standard", cwd=root, raw=True)
        untracked = [os.fsdecode(p) for p in raw.split(b"\0") if p]
        files = parse_diff(text) + untracked_as_added(untracked, root)
        seen = {f["path"] for f in files} | {f["old_path"] for f in files}
        for path in sorted((names(root, merge_base, "HEAD") | names(root, "--cached", merge_base)) - seen):
            if not is_ignored(path):
                hard.append(("hidden-change", path, "changed in a commit or the index but not in the working tree: "
                                                    "the guard would not see what gets committed"))
        for path in sorted(names(root, "--cached", "HEAD") & names(root)):
            if not is_ignored(path):
                hard.append(("index-worktree-mismatch", path, "staged content differs from the working tree"))
        flags = git("ls-files", "-v", "-z", cwd=root, raw=True)
        for entry in flags.split(b"\0"):
            if entry and (entry[:1].islower() or entry[:1] == b"S"):
                path = os.fsdecode(entry[2:])
                if not is_ignored(path):
                    hard.append(("hidden-flag", path, "assume-unchanged or skip-worktree hides this file from git diff"))
    ahead = git("rev-list", "--count", f"{merge_base}..HEAD", cwd=root).strip()
    meta = {"mode": "committed" if committed else "worktree", "head_sha": head, "base_sha": base_sha,
            "merge_base": merge_base, "commits_since_base": int(ahead or 0), "hard": hard}
    if committed:
        meta["hooks"] = {"hooks_path": hooks_path or None, "dir": hooks_dir, "active": active}
        meta["push_config"] = push_config
    return files, meta


PUSH_KEY_RE = re.compile(r"core\.(hookspath|sshcommand|askpass|gitproxy)|remote\..+\.(url|pushurl|receivepack|uploadpack"
                         r"|vcs|proxy|push)|url\..+\.(pushinsteadof|insteadof)|credential\..+|protocol\..+"
                         r"|http\..+|push\..+", re.I | re.S)
SECRET_KEY_RE = re.compile(r"extraheader$|\.(password|token|secret|cookiefile)$|^credential\..*helper$", re.I | re.S)
SECRET_VALUE_RE = re.compile(r"authorization:|bearer\s|basic\s|password=|token=|ghp_|gho_|github_pat_|glpat-|xox[abpr]-|AKIA", re.I)


def redact(key, value):
    """Hide credentials before a config value goes into a report; escape control and separator characters.

    URL userinfo is masked up to the last '@' in the value (greedy, so a password holding '/' or '@' is masked too).
    """
    if SECRET_KEY_RE.search(key) or SECRET_VALUE_RE.search(value):
        return f"<redacted, {len(value)} chars>"
    value = re.sub(r"(://)[^\s]*@", r"\1***@", value)
    return "".join(c if c.isprintable() or c == " " else f"\\x{ord(c):02x}" if ord(c) < 256 else f"\\u{ord(c):04x}"
                   for c in value)


def tree_of(root, commit):
    for line in git("cat-file", "commit", commit, cwd=root).splitlines():
        if line.startswith("tree "):
            return line[5:].strip()
        if not line:
            break
    raise InputError(f"commit {commit[:12]} has no tree line")


# ---------------------------------------------------------------- plan and justifications

def estimate_of(edit):
    value = edit.get("estimate_lines")
    if value is None or value == "":
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InputError(f"{edit['id']}: estimate_lines must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise InputError(f"{edit['id']}: estimate_lines must be finite")
    if isinstance(value, (int, float)):
        if value < 0:
            raise InputError(f"{edit['id']}: estimate_lines must not be negative")
        return int(value)
    m = re.search(r"\d+", value)
    if not m:
        raise InputError(f"{edit['id']}: estimate_lines must be a number, got {value!r}")
    return int(m.group(0))


def load_plan(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        plan = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot read plan {path}: {exc}")
    return validate_plan(plan, raw)


def no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise ValueError(f"duplicate keys {dupes}")
    return dict(pairs)


def scope_summary(plan):
    """The enforced scope, as the user must see it before approving."""
    return json.dumps({k: plan.get(k) for k in ("level", "base", "base_sha", "allow", "tests")} |
                      {"edits": [{"id": e["id"], "file": e["file"]} for e in plan["edits"]]}, indent=2)


def validate_plan(plan, raw):
    """Check types and normalise a parsed plan; raw is the file's bytes, hashed for approval pinning."""
    if not isinstance(plan, dict) or not isinstance(plan.get("edits"), list) or not plan["edits"]:
        raise InputError("plan must be an object with a non-empty 'edits' list")
    level = plan.get("level", "prod")
    if level not in LEVELS:
        raise InputError(f"plan level must be one of {LEVELS}, got {level!r}")
    ids = set()
    for edit in plan["edits"]:
        if not isinstance(edit, dict) or not isinstance(edit.get("id"), str) or not isinstance(edit.get("file"), str) \
                or not edit["id"].strip() or not edit["file"].strip():
            raise InputError("every edit needs a string 'id' and a string 'file'")
        if edit["id"] in ids:
            raise InputError(f"duplicate edit id {edit['id']!r}")
        ids.add(edit["id"])
        edit["file"] = clean(edit["file"])
        edit["estimate"] = estimate_of(edit)
    for key in ("tests", "allow"):
        value = plan.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise InputError(f"'{key}' must be a list of strings")
    if any(a not in CATEGORIES for a in plan.get("allow", [])):
        raise InputError(f"'allow' may only list {CATEGORIES}")
    plan["tests"] = [clean(t) for t in plan.get("tests", [])]
    ratio = plan.get("warn_ratio", DEFAULT_WARN_RATIO)
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio <= 0:
        raise InputError("'warn_ratio' must be a positive number")
    for key in ("base", "base_sha"):
        if key in plan and not isinstance(plan[key], str):
            raise InputError(f"'{key}' must be a string")
    if plan.get("base_sha") and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", plan["base_sha"]):
        raise InputError("'base_sha' must be a full commit SHA")
    plan["_sha256"] = hashlib.sha256(raw).hexdigest()
    return plan


def parse_justifications(text):
    """Read `| path:start-end | E1 | reason | risk |` rows from hunks.md (one range per row)."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= set("-: "):
            continue
        m = ROW_REF_RE.match(cells[0])
        if not m or not m.group("path") or m.group("path").lower() in ("hunk", "file", "file:lines", "location"):
            continue
        start = int(m.group("start")) if m.group("start") else None
        end = int(m.group("end")) if m.group("end") else start
        if start is not None and end < start:
            start, end = end, start
        rows.append({"path": clean(m.group("path")), "start": start, "end": end, "edit": cells[1].strip("` "),
                     "reason": cells[2], "line": line})
    return rows


def hunk_span(h):
    if h["new_count"] == 0:  # pure deletion: git points at the line before the gap
        return max(h["new_start"], 1), h["new_start"] + 1
    return h["new_start"], h["new_start"] + h["new_count"] - 1


# ---------------------------------------------------------------- the check

def check(plan, files, rows, approved_sha=None, meta=None, unpinned=False):
    level = plan.get("level", "prod")
    allow = set(plan.get("allow", [])) if level == "release" else set()
    extra_tests = set(plan.get("tests", []))
    edits = {e["id"]: e for e in plan["edits"]}
    planned_files = {e["file"] for e in plan["edits"]}
    hard, warn = [], []
    used_rows, touched_files, test_files = {}, set(), []
    code_lines = test_lines = 0

    def add(bucket, kind, path, msg, line=None):
        bucket.append({"kind": kind, "file": path, "line": line, "message": msg})

    if approved_sha is not None and approved_sha.lower() != plan["_sha256"]:
        add(hard, "plan-changed-after-approval", None,
            f"fix-plan.json sha256 {plan['_sha256'][:12]}… does not match the approved {approved_sha[:12]}…: the plan was edited after approval")
    if not str(plan.get("approved_by", "")).strip():
        add(hard, "plan-not-approved", None, "fix-plan.json has no 'approved_by': the user must approve the plan first")
    if not plan.get("base_sha"):
        add(warn, "base-not-pinned", None, "the plan has no 'base_sha': record the base commit when the user approves")
    for kind, path, msg in (meta or {}).get("hard", []):
        add(hard, kind, path, msg)
    hooks = (meta or {}).get("hooks")
    if hooks and (hooks["hooks_path"] or hooks["active"]):
        add(warn, "active-hooks", None, f"git hooks will run on commit and push (hooksPath: {hooks['hooks_path'] or 'default'};"
                                        f" active: {', '.join(hooks['active']) or 'none'}): show them to the user before the push")
    if (meta or {}).get("push_config"):
        add(warn, "push-config", None, f"{len(meta['push_config'])} git config entries decide where and how the push runs;"
                                       " they are listed in full in the report: show them to the user before the push")
    committed = (meta or {}).get("mode") == "committed"
    if meta and meta.get("base_moved"):
        add(hard, "base-moved", None, f"--base resolves to {meta['base_moved'][:12]}, not the approved base_sha {plan['base_sha'][:12]}")
    if level == "prod" and plan.get("allow"):
        add(warn, "allow-ignored-at-prod", None, "'allow' is ignored at level prod")
    for t in sorted(extra_tests):
        if test_kind(t) is None:
            add(warn, "plan-declared-test", t, "the plan lists this as a test, but its name and directory do not look like a test")

    for f in files:
        path = f["path"]
        if record_ignored(f, committed):
            plain = not (f["binary"] or f["symlink"] or f["submodule"] or f["mode_change"] or f["unreadable"]
                         or f.get("executable"))
            if plain or f["status"] == "deleted":
                continue
            add(hard, "squad-file", f["path"], "hotfix artifact is not a plain text file (symlink, binary, gitlink, executable or mode change)")
            continue
        touched_files.add(path)
        tkind = test_kind(path, extra_tests)
        test = tkind is not None
        if test:
            test_files.append(path)
        size = sum(len(h["added"]) + len(h["removed"]) for h in f["hunks"])
        if test:
            test_lines += size
        else:
            code_lines += size

        if path.startswith(".squad/"):
            add(hard, "squad-file", path, "squad workspace file changed: not part of a hotfix")
        if f["unreadable"]:
            add(hard, "unreadable-file", path, "untracked file could not be read: check it by hand")
        if f["status"] == "deleted":
            add(hard, "deleted-file", path, "file deleted: not allowed in a hotfix")
        elif f["status"] == "renamed":
            add(hard, "renamed-file", path, f"renamed from {f['old_path']}: not allowed in a hotfix")
        elif f["status"] == "added" and not test:
            add(hard, "new-file", path, "new non-test file: a hotfix may only add test files")
        if tkind in ("dir", "plan") and f["status"] in ("added", "modified"):
            add(warn, "test-by-directory", path, "counted as a test only because of its directory or the plan's 'tests' list: check it is a test")
        if f["mode_change"]:
            add(hard, "mode-change", path, "file mode changed: not allowed in a hotfix")
        if f["symlink"]:
            add(hard, "symlink", path, "symlink added or changed: not allowed in a hotfix")
        if f["submodule"]:
            add(hard, "submodule", path, "submodule commit changed: that is a dependency change")
        if not test and path not in planned_files:
            add(hard, "outside-plan", path, "file is not in the approved fix plan")
        cat = category(path)
        if cat and test and cat not in STRUCTURAL:
            cat = None  # a config file or migration under a test directory is a fixture
        if cat and cat not in allow:
            hint = ("allowed only at level 'release' with the category in the plan's 'allow' list"
                    if level == "release" else "forbidden at level 'prod': use /dev-squad:db-change, /dev-squad:upgrade or /dev-squad:feature")
            add(hard, f"forbidden-{cat}", path, f"{cat} file changed: {hint}")

        file_rows = [i for i, r in enumerate(rows) if r["path"] == path]
        if f["binary"]:
            whole = [i for i in file_rows if rows[i]["start"] is None and rows[i]["reason"]]
            if test and whole:
                add(warn, "binary-file", path, "binary test file: review it by hand")
                for i in whole:
                    used_rows.setdefault(i, [])
            else:
                add(hard, "binary-file", path, "binary change outside a justified test file: not allowed in a hotfix")
            continue

        indent = bool(INDENT_SENSITIVE_RE.search(path))
        for h in f["hunks"]:
            start, end = hunk_span(h)
            kind = hunk_kind(h["removed"], h["added"], indent)
            if kind == "format":
                add(hard, "format-only", path, f"lines {start}-{end} only change whitespace or line wrapping: revert", start)
                continue
            if kind == "string-space":
                add(warn, "whitespace-in-string", path,
                    f"lines {start}-{end} only change whitespace, inside a string: keep only if the fix needs it", start)
            elif kind in ("reorder", "import", "comment"):
                add(warn, f"{kind}-only", path, f"lines {start}-{end} are {kind}-only: keep only if the fix needs it", start)
            if test and f["status"] == "modified" and h["removed"]:
                add(warn, "existing-test-modified", path,
                    f"lines {start}-{end} remove or change existing test lines: assertions must not be weakened", start)
            match = None
            for i in file_rows:
                r = rows[i]
                whole_new_test = r["start"] is None and test and f["status"] == "added"
                if whole_new_test or (r["start"] is not None and r["start"] <= end and r["end"] >= start):
                    match = i
                    break
            if match is None or not rows[match]["reason"]:
                add(hard, "unjustified-hunk", path, f"lines {start}-{end} have no row with a reason in hunks.md", start)
                continue
            used_rows.setdefault(match, []).append((start, end))
            ref = rows[match]["edit"]
            if ref in edits:
                if edits[ref]["file"] != path:
                    add(hard, "edit-file-mismatch", path,
                        f"lines {start}-{end} cite {ref}, which the plan scopes to {edits[ref]['file']}", start)
            elif ref.lower() == "test" or re.fullmatch(r"T\d+", ref):
                if not test:
                    add(hard, "edit-file-mismatch", path, f"lines {start}-{end} cite a test id but this is not a test file", start)
            else:
                add(hard, "unknown-edit", path, f"lines {start}-{end} cite {ref!r}, which is not an edit id in the plan", start)

    for i, r in enumerate(rows):
        spans = used_rows.get(i)
        if spans is None:
            add(warn, "stale-justification", r["path"], f"hunks.md row matches no changed hunk: {r['line']}")
            continue
        if r["start"] is None or not spans:
            continue
        spans = sorted(spans)
        lo, hi = spans[0][0], max(e for _, e in spans)
        gap = max((b[0] - a[1] for a, b in zip(spans, spans[1:])), default=0)
        if r["start"] < lo - ROW_SLACK or r["end"] > hi + ROW_SLACK or gap > ROW_SLACK:
            add(hard, "wide-justification", r["path"],
                f"row {r['start']}-{r['end']} spans more than the hunks it covers ({lo}-{hi}, largest gap {gap}): one row per hunk", r["start"])
        elif len(spans) > 1:
            add(warn, "row-covers-many-hunks", r["path"], f"row {r['start']}-{r['end']} covers {len(spans)} hunks: prefer one row per hunk", r["start"])
    for e in plan["edits"]:
        if e["file"] not in touched_files:
            add(warn, "planned-edit-unused", e["file"], f"{e['id']} is in the plan but its file is unchanged")

    estimate = sum(e["estimate"] for e in plan["edits"])
    ratio = float(plan.get("warn_ratio", DEFAULT_WARN_RATIO))
    if estimate and code_lines > estimate * ratio and code_lines - estimate > WARN_SLACK:
        add(warn, "size-over-estimate", None,
            f"{code_lines} changed non-test lines vs an estimate of {estimate} (> x{ratio:g}): explain the difference in the review packet")

    mode = (meta or {}).get("mode", "diff-file")
    if hard:
        result = "FAIL"
    elif unpinned:
        result = "PASS (unpinned self-check)"
    else:
        result = "PASS" if mode == "committed" else f"PASS ({mode}; not the push check)"
    return {
        "result": result, "passed": not hard, "pinned": not unpinned,
        "slug": plan.get("slug"), "plan_version": plan.get("version"), "level": level,
        "plan_sha256": plan["_sha256"], "approved_sha256": approved_sha, "git": meta or {},
        "stats": {"files": len(touched_files), "code_lines_changed": code_lines, "test_lines_changed": test_lines,
                  "estimate_lines": estimate},
        "test_files": sorted(test_files), "allow": sorted(allow),
        "violations": hard, "warnings": warn,
    }


def to_markdown(report):
    s = report["stats"]
    g = report["git"]
    pinned = report["approved_sha256"] and report["approved_sha256"].lower() == report["plan_sha256"]
    out = [f"Result: **{report['result']}** (diff_guard; the JSON report and the exit code are authoritative)", "",
           f"# diff_guard: {one_line(report.get('slug') or 'hotfix')} (plan v{one_line(report.get('plan_version') or '?')},"
           f" level {report['level']})", "",
           f"- Plan sha256: `{report['plan_sha256']}` ({'matches the approved hash' if pinned else 'NOT pinned'})"]
    if g:
        out.append(f"- Mode: {g['mode']} · HEAD `{g['head_sha'][:12]}` · base `{g['base_sha'][:12]}`"
                   f" · merge base `{g['merge_base'][:12]}` · {g['commits_since_base']} commit(s) since base")
    out += [f"- Files: {s['files']} · changed lines: {s['code_lines_changed']} code + {s['test_lines_changed']} test"
            f" · plan estimate: {s['estimate_lines'] or 'n/a'} (information only, not a budget)",
            f"- Treated as tests: {', '.join(code(p) for p in report['test_files']) or 'none'}",
            f"- Allowed categories: {', '.join(report['allow']) or 'none'}", ""]
    for title, items in (("Violations (must fix or get the user's decision)", report["violations"]),
                         ("Warnings (explain in the review packet)", report["warnings"])):
        out.append(f"## {title}")
        if not items:
            out.append("- none")
        for it in items:
            where = code(f"{it['file']}{':' + str(it['line']) if it['line'] else ''}") + " " if it["file"] else ""
            out.append(f"- **{it['kind']}** {where}— {one_line(it['message'])}")
        out.append("")
    hooks, push = g.get("hooks"), g.get("push_config")
    if hooks is not None or push is not None:
        out.append("## What the push will run and where it goes (show all of it to the user)")
        if hooks is not None:
            out.append(f"- hooksPath: {code(hooks['hooks_path'] or 'default')} · hooks dir: {code(hooks['dir'])}"
                       f" · active hooks: {', '.join(code(h) for h in hooks['active']) or 'none'}")
        for line in push or []:
            out.append(f"- {code(line, limit=None)}")
        out.append("")
    return "\n".join(out)


def find_input(path):
    """Accept --plan / --hunks relative to the cwd or to the repository root."""
    if os.path.exists(path) or os.path.isabs(path):
        return path
    try:
        root = git("rev-parse", "--show-toplevel").strip()
    except (InputError, OSError):
        return path
    return os.path.join(root, path)


def write_out(path, text):
    """Write a report without following a symlink planted at the destination."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True, help="fix-plan.json")
    ap.add_argument("--print-plan-sha256", action="store_true", help="print the plan's sha256 (record it when the user approves) and exit")
    ap.add_argument("--plan-sha256", help="sha256 of the plan as the user approved it (required unless --unpinned)")
    ap.add_argument("--unpinned", action="store_true", help="self-check without the approved hash; never reports a plain PASS")
    ap.add_argument("--committed", action="store_true",
                    help="check the committed HEAD tree-to-tree and require a clean tree: the check before a push")
    ap.add_argument("--hunks", help="hunks.md with one justification row per hunk")
    ap.add_argument("--base", help="base ref; must resolve to the plan's base_sha when that is set")
    ap.add_argument("--diff-file", help="read a unified diff (with a/ and b/ prefixes) from this file instead of running git")
    ap.add_argument("--json", help="also write the report as JSON to this path")
    ap.add_argument("--md", help="also write the Markdown report to this path")
    args = ap.parse_args(argv)
    try:
        plan_path = find_input(args.plan)
        plan = load_plan(plan_path)
        try:
            root = git("rev-parse", "--show-toplevel").strip()
            rel = os.path.relpath(os.path.dirname(os.path.realpath(plan_path)), os.path.realpath(root)).replace(os.sep, "/")
            SLUG_DIR["value"] = rel if re.fullmatch(r"\.squad/hotfix/[^/]+", rel) else None
        except (InputError, OSError):
            SLUG_DIR["value"] = None
        if args.print_plan_sha256:
            print(plan["_sha256"])
            print(scope_summary(plan), file=sys.stderr)
            return 0
        if not args.hunks:
            raise InputError("--hunks is required")
        if args.committed and (args.unpinned or args.diff_file):
            raise InputError("--committed needs --plan-sha256 and cannot be combined with --unpinned or --diff-file")
        if args.plan_sha256 is None and not args.unpinned:
            raise InputError("--plan-sha256 is required (the hash recorded when the user approved the plan); "
                             "use --unpinned only for a self-check")
        if args.plan_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", args.plan_sha256):
            raise InputError("--plan-sha256 must be 64 hex characters")
        try:
            with open(find_input(args.hunks), encoding="utf-8") as fh:
                rows = parse_justifications(fh.read())
        except (OSError, ValueError) as exc:
            raise InputError(f"cannot read {args.hunks}: {exc}")
        meta = None
        if args.diff_file:
            with open(args.diff_file, "rb") as fh:
                files = parse_diff(fh.read().decode("utf-8", "replace"))
        else:
            if plan.get("base_sha"):
                base_sha = resolve_base(plan["base_sha"])
                moved = resolve_base(args.base) if args.base else base_sha
            else:
                base_sha = moved = resolve_base(args.base or plan.get("base"))
            files, meta = collect_diff(base_sha, committed=args.committed, base_name=plan.get("base"))
            meta["base"] = args.base or plan.get("base") or plan.get("base_sha")
            if moved != base_sha:
                meta["base_moved"] = moved
        report = check(plan, files, rows, args.plan_sha256, meta, unpinned=args.plan_sha256 is None)
        md = to_markdown(report)
        print(md)
        if args.json:
            write_out(args.json, json.dumps(report, indent=2))
        if args.md:
            write_out(args.md, md + "\n")
    except (InputError, OSError) as exc:
        print(f"diff_guard: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # never let a crash look like a violation (exit 1)
        print(f"diff_guard: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
