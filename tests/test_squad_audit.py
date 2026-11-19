"""Tests for the squad-audit transcript miner (stdlib only: python -m unittest discover -s tests)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins", "dev-squad", "skills",
                                      "squad-audit", "scripts", "mine_transcripts.py"))
sys.path.insert(0, os.path.dirname(SCRIPT))

import mine_transcripts as mt  # noqa: E402


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def ev(typ, ts, content, **extra):
    d = {"type": typ, "timestamp": ts, "cwd": extra.pop("cwd", "/work/billing-svc"), "gitBranch": "main",
         "isSidechain": False, "message": {"role": typ, "content": content}}
    d.update(extra)
    return d


def tool_use(name, inp):
    return [{"type": "tool_use", "id": "t", "name": name, "input": inp}]


def tool_result(err=False):
    return [{"type": "tool_result", "tool_use_id": "t", "content": "x", "is_error": err}]


class MinerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.root = os.path.join(cls.tmp.name, "projects")
        plugins = cls.plugins = os.path.join(cls.tmp.name, "plugins")
        # plugin definitions: 3 agents, 2 commands
        base = os.path.join(plugins, "dev-squad")
        os.makedirs(os.path.join(base, ".claude-plugin"))
        os.makedirs(os.path.join(base, "agents"))
        os.makedirs(os.path.join(base, "commands"))
        write(os.path.join(base, ".claude-plugin", "plugin.json"), json.dumps({"name": "dev-squad"}))
        for a in ("code-reviewer", "developer", "qa-engineer"):
            write(os.path.join(base, "agents", f"{a}.md"), f"---\nname: {a}\ndescription: x\n---\nbody\n")
        for c in ("review", "feature"):
            write(os.path.join(base, "commands", f"{c}.md"), "---\ndescription: x\n---\nbody\n")

        proj = os.path.join(root, "-work-billing-svc")
        os.makedirs(os.path.join(proj, "s1", "subagents"))
        long_spec = "Implement the SNMP trap receiver for OVNG switches. " + "Details here. " * 120
        events = [
            ev("user", "2026-11-10T09:00:00Z", "Review the Kafka consumer in BillingConsumer.java please"),
            ev("assistant", "2026-11-10T09:00:05Z", tool_use("Agent", {"subagent_type": "dev-squad:code-reviewer", "prompt": "x"})),
            ev("user", "2026-11-10T09:01:00Z", tool_result()),
            ev("assistant", "2026-11-10T09:01:05Z", [{"type": "text", "text": "Verdict: approve"}]),
            ev("user", "2026-11-10T09:02:00Z", "Không đúng, bạn bỏ qua phần commit offset. Làm lại."),
            ev("assistant", "2026-11-10T09:02:05Z", tool_use("Edit", {"file_path": "/work/billing-svc/A.java"})),
            ev("user", "2026-11-10T09:02:06Z", tool_result(err=True)),
            ev("user", "2026-11-10T09:03:00Z", "[Request interrupted by user]"),
            ev("user", "2026-11-10T09:04:00Z", "<command-message>dev-squad:review</command-message>\n"
               "<command-name>/dev-squad:review</command-name>\n<command-args>HEAD~1</command-args>"),
            ev("user", "2026-11-10T09:04:00Z", [{"type": "text", "text": "expanded command body"}], isMeta=True),
            ev("user", "2026-11-10T09:05:00Z", "<task-notification>done</task-notification>"),
            ev("user", "2026-11-10T09:06:00Z", long_spec + " token=ghp_abcdefghijklmnopqrstuvwxyz123456"),
            ev("user", "2026-11-10T09:07:00Z", "Here is the output:\n### Handoff\n- Status: done\n- Next: developer"),
            ev("user", "2026-09-01T09:00:00Z", "Old prompt outside the window about postgres"),
            {"type": "cost-state", "totalCostUSD": 1.25},
        ]
        with open(os.path.join(proj, "s1.jsonl"), "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")
        sub = os.path.join(proj, "s1", "subagents", "agent-1")
        with open(sub + ".jsonl", "w") as fh:
            fh.write(json.dumps(ev("user", "2026-11-10T09:00:05Z", "brief", isSidechain=True)) + "\n")
            fh.write(json.dumps(ev("assistant", "2026-11-10T09:00:30Z", [{"type": "text", "text":
                     "Verdict: approve\n### Handoff\n- Status: needs-input\n- Next: test-writer — add tests"}],
                     isSidechain=True)) + "\n")
        write(sub + ".meta.json", json.dumps({"agentType": "dev-squad:code-reviewer", "finished": True}))
        running = os.path.join(proj, "s1", "subagents", "agent-2")  # an audit still in progress
        with open(running + ".jsonl", "w") as fh:
            fh.write(json.dumps(ev("user", "2026-11-10T09:08:00Z", "audit brief", isSidechain=True)) + "\n")
        write(running + ".meta.json", json.dumps({"agentType": "dev-squad:squad-auditor"}))
        other = os.path.join(root, "-work-my-service")  # cwd /work/my_service: '_' is encoded as '-'
        os.makedirs(other)
        with open(os.path.join(other, "s3.jsonl"), "w") as fh:
            fh.write("[]\n\"just a string\"\n123\n{not json\n")
            fh.write(json.dumps({"type": "user", "timestamp": "2026-11-12T08:00:00Z", "message": "not-a-dict"}) + "\n")
            e = ev("user", "2026-11-12T08:01:00", "<command-message>review</command-message>\n<command-name>/review</command-name>",
                   cwd="/work/my_service")  # naive timestamp, bare command name
            fh.write(json.dumps(e) + "\n")
            e = ev("assistant", "2026-11-12T08:01:05Z", ["junk", {"type": "tool_use", "name": "Read", "input": None}],
                   cwd="/work/my_service")
            fh.write(json.dumps(e) + "\n")
        # handback sub-agent with a non-standard Status, and a forked copy of s1's first turn
        hb = os.path.join(proj, "s1", "subagents", "agent-3")
        with open(hb + ".jsonl", "w") as fh:
            fh.write(json.dumps(ev("user", "2026-11-10T09:09:00Z", "brief", isSidechain=True)) + "\n")
            fh.write(json.dumps(ev("assistant", "2026-11-10T09:09:30Z", tool_use("SubagentHandback", {"message":
                     "Verdict: REQUEST CHANGES ghp_abcdefghijklmnopqrstuvwxyz123456\n### Handoff\n- Status: request-changes\n- Next: developer — fix"}),
                     isSidechain=True)) + "\n")
        write(hb + ".meta.json", json.dumps({"agentType": "dev-squad:code-reviewer", "finished": True}))
        bt = os.path.join(proj, "s1", "subagents", "agent-4")  # backticked valid Status; "Status:" also in the body
        with open(bt + ".jsonl", "w") as fh:
            fh.write(json.dumps(ev("user", "2026-11-10T09:10:00Z", "brief", isSidechain=True)) + "\n")
            fh.write(json.dumps(ev("assistant", "2026-11-10T09:10:30Z", [{"type": "text", "text":
                     "Root cause found.\n- Status: in progress before the fix\n### Handoff\n- Status: `done`\n- Next: developer — x"}],
                     isSidechain=True)) + "\n")
        write(bt + ".meta.json", json.dumps({"agentType": "dev-squad:debugger", "finished": True}))
        fork = os.path.join(proj, "s1-fork.jsonl")
        with open(fork, "w") as fh:
            for e in events[:2]:  # copied turn: same timestamp and text as in s1
                fh.write(json.dumps(e) + "\n")
            fh.write(json.dumps(ev("user", "2026-11-10T10:00:00Z", "<command-message>model</command-message>\n"
                                   "<command-name>/model</command-name>\n<command-args>opus</command-args>")) + "\n")
            fh.write(json.dumps(ev("user", "2026-11-10T10:01:00Z", "New question only in the fork")) + "\n")
        s1_mtime = os.path.getmtime(os.path.join(proj, "s1.jsonl"))
        os.utime(fork, (s1_mtime + 60, s1_mtime + 60))
        sandbox = os.path.join(root, "-tmp-scratchpad-smoke")
        os.makedirs(sandbox)
        with open(os.path.join(sandbox, "s2.jsonl"), "w") as fh:
            fh.write(json.dumps(ev("user", "2026-11-11T10:00:00Z", "smoke test prompt", cwd="/tmp/scratchpad/smoke")) + "\n")

        cls.json_out = os.path.join(cls.tmp.name, "out.json")
        cls.md_out = os.path.join(cls.tmp.name, "out.md")
        subprocess.run([sys.executable, SCRIPT, "--root", root, "--since", "2026-11-01", "--until", "2026-11-30",
                        "--scope", "dev-squad", "--plugins-root", plugins, "--json", cls.json_out, "--md", cls.md_out],
                       check=True, capture_output=True)
        cls.data = json.loads(read(cls.json_out))
        cls.proj = os.path.join(cls.tmp.name, "proj.json")
        subprocess.run([sys.executable, SCRIPT, "--root", root, "--since", "2026-11-01", "--until", "2026-11-30",
                        "--project", "my_service", "--plugins-root", plugins, "--json", cls.proj,
                        "--md", os.path.join(cls.tmp.name, "proj.md")], check=True, capture_output=True)
        cls.excl = os.path.join(cls.tmp.name, "excl.json")
        subprocess.run([sys.executable, SCRIPT, "--root", root, "--since", "2026-11-01", "--until", "2026-11-30",
                        "--scope", "dev-squad", "--plugins-root", plugins, "--exclude-project", "scratchpad",
                        "--json", cls.excl, "--md", os.path.join(cls.tmp.name, "excl.md")], check=True, capture_output=True)
        cls.r = cls.data["report"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_window_excludes_old_prompts(self):
        texts = [p["text"] for s in self.data["sessions"] for p in s["prompts"]]
        self.assertFalse(any("Old prompt" in t for t in texts))
        self.assertEqual(self.r["overview"]["prompts"], 8)  # 5 in s1 + 1 new in the fork + /review in s3 + smoke

    def test_exclude_project(self):
        r = json.loads(read(self.excl))["report"]
        self.assertEqual(r["overview"]["sessions"], 3)
        self.assertEqual(r["overview"]["prompts"], 7)

    def test_project_filter_matches_cwd(self):
        r = json.loads(read(self.proj))["report"]
        self.assertEqual(r["overview"]["sessions"], 1)  # cwd /work/my_service although the dir is -work-my-service

    def test_malformed_lines_are_skipped_and_naive_ts_accepted(self):
        s3 = [s for s in self.data["sessions"] if s["file"].endswith("s3.jsonl")]
        self.assertEqual(len(s3), 1)
        self.assertEqual([p["command"] for p in s3[0]["prompts"]], ["review"])

    def test_redaction_shapes(self):
        cases = ['"password": "hunter2xyz"', "client_secret=abc123def456", "Authorization: Basic dXNlcjpwYXNz",
                 "sk_live_51HabcdefghijklmnopQRST", "sk-ant-api03-abcdefghijklmnopqrst", "glpat-abcdefghijklmnopqrst",
                 "AIzaSyA1234567890abcdefghijklmnopqrstu", "npm_abcdefghijklmnopqrstuvwxyz0123456789",
                 "export TOKEN='abcd1234efgh5678'", "postgresql://app:s3cret@db:5432/x"]
        leaked = ["hunter2xyz", "abc123def456", "dXNlcjpwYXNz", "51Habcdefghij", "api03-abcdefghij",
                  "abcdefghijklmnopqrst", "1234567890abcdefghij", "abcdefghijklmnopqrstuvwxyz0123456789",
                  "abcd1234efgh5678", "s3cret"]
        for text, secret in zip(cases, leaked):
            self.assertNotIn(secret, mt.snippet(text, 500), text)

    def test_in_progress_runs_excluded_from_health(self):
        self.assertEqual(self.r["overview"]["subagent_runs"], 3)  # agent-1, handback agent-3, debugger agent-4
        self.assertEqual(self.r["overview"]["subagent_runs_in_progress"], 1)
        self.assertNotIn("dev-squad:squad-auditor", self.r["subagents"])

    def test_usage_and_never_used(self):
        self.assertEqual(dict(self.r["usage"]["agents"]), {"dev-squad:code-reviewer": 1})
        self.assertEqual(dict(self.r["usage"]["commands"]), {"dev-squad:review": 1, "review": 1})
        self.assertEqual(self.r["never_used"]["agents"], ["dev-squad:developer", "dev-squad:qa-engineer"])
        self.assertEqual(self.r["never_used"]["commands"], ["dev-squad:feature"])

    def test_bare_command_counts_as_used(self):
        r = json.loads(read(self.proj))["report"]  # only s3, where the user typed the bare /review
        self.assertNotIn("dev-squad:review", r["never_used"]["commands"])

    def test_correction_attributed_to_agent(self):
        c = self.r["signals"]["corrections"]
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["after"], "agent:dev-squad:code-reviewer")
        self.assertTrue(c[0]["ref"].endswith("s1.jsonl:5"))

    def test_noise_is_not_a_prompt(self):
        texts = [p["text"] for s in self.data["sessions"] for p in s["prompts"]]
        self.assertFalse(any("task-notification" in t or "expanded command body" in t for t in texts))

    def test_interrupt_long_prompt_handoff_and_redaction(self):
        s = self.r["signals"]
        self.assertEqual(len(s["interrupted_turns"]), 1)
        self.assertEqual(len(s["long_prompts"]), 1)
        self.assertEqual(len(s["manual_handoffs"]), 1)
        self.assertNotIn("ghp_", read(self.json_out))
        self.assertIn("snmp", self.r["domains"])
        self.assertIn("ovng", self.r["domains"])

    def test_subagent_health(self):
        st = self.r["subagents"]["dev-squad:code-reviewer"]
        self.assertEqual(st["runs"], 2)
        self.assertEqual(st["blocked_or_input"], 1)
        self.assertEqual([x["next"] for x in st["invalid_next"]], ["test-writer"])

    def test_handback_report_counts_as_handoff(self):
        st = self.r["subagents"]["dev-squad:code-reviewer"]
        self.assertEqual(st["no_handoff"], 0)
        self.assertEqual(st["via_handback"], 1)
        self.assertEqual([x["status"] for x in st["invalid_status"]], ["request-changes"])
        self.assertNotIn("ghp_", read(self.json_out))  # a secret inside a handback report never reaches the output

    def test_backticked_status_is_valid_and_body_status_ignored(self):
        st = self.r["subagents"]["dev-squad:debugger"]
        self.assertEqual(st["invalid_status"], [])
        self.assertEqual(st["no_handoff"], 0)

    def test_forked_cost_is_flagged(self):
        self.assertEqual(self.r["overview"]["forked_sessions"], 1)
        self.assertIn("upper bound", read(self.md_out))

    def test_adoption_without_usage(self):
        out = os.path.join(self.tmp.name, "lab.json")
        subprocess.run([sys.executable, SCRIPT, "--root", self.root, "--since", "2026-11-01", "--until", "2026-11-30",
                        "--scope", "lab", "--plugins-root", self.plugins, "--json", out,
                        "--md", os.path.join(self.tmp.name, "lab.md")], check=True, capture_output=True)
        a = json.loads(read(out))["report"]["adoption"]["lab"]
        self.assertIsNone(a["first_use"])
        self.assertEqual(a["prompts_using"], 0)
        self.assertEqual(a["prompts_since_first_use"], 0)

    def test_fork_duplicates_and_harness_commands(self):
        o = self.r["overview"]
        self.assertEqual(o["fork_duplicate_prompts"], 1)
        self.assertEqual(dict(o["harness_commands"]), {"model": 1})
        texts = [p["text"] for s in self.data["sessions"] for p in s["prompts"]]
        self.assertEqual(sum(1 for t in texts if t.startswith("Review the Kafka consumer")), 1)
        self.assertFalse(any(t.startswith("/model") for t in texts))

    def test_totals_and_adoption(self):
        self.assertEqual(self.r["signals"]["totals"]["corrections"], 1)
        a = self.r["adoption"]["dev-squad"]
        self.assertEqual(a["prompts_using"], 3)  # code-reviewer turn, /dev-squad:review and the bare /review
        self.assertTrue(a["first_use"].startswith("2026-11-10T09:00"))

    def test_skipped_steps(self):
        sk = self.r["signals"]["skipped_steps"]
        self.assertEqual(len(sk), 1)
        self.assertFalse(sk[0]["ran_tests"])
        self.assertTrue(sk[0]["reviewed"])  # /dev-squad:review ran in the session

    def test_markdown_and_show(self):
        md = read(self.md_out)
        self.assertIn("Never used agents", md)
        out = subprocess.run([sys.executable, SCRIPT, "--root", self.root, "--show=-work-billing-svc/s1.jsonl:5"],
                             check=True, capture_output=True, text=True).stdout
        self.assertIn(">>      5 user", out)

    def test_classification(self):
        self.assertEqual(mt.classify("Consumer lag tăng liên tục, p95 chậm"), "performance")
        self.assertEqual(mt.classify("thêm cột tenant_id, viết migration flyway"), "db-migration")
        self.assertEqual(mt.classify("tạo MR cho branch này"), "git-pr")


if __name__ == "__main__":
    unittest.main()
