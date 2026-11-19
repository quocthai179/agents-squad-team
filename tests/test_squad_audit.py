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
    d = {"type": typ, "timestamp": ts, "cwd": "/work/billing-svc", "gitBranch": "main", "isSidechain": False,
         "message": {"role": typ, "content": content}}
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

        cls.json_out = os.path.join(cls.tmp.name, "out.json")
        cls.md_out = os.path.join(cls.tmp.name, "out.md")
        subprocess.run([sys.executable, SCRIPT, "--root", root, "--since", "2026-11-01", "--until", "2026-11-30",
                        "--scope", "dev-squad", "--plugins-root", plugins, "--json", cls.json_out, "--md", cls.md_out],
                       check=True, capture_output=True)
        cls.data = json.loads(read(cls.json_out))
        cls.r = cls.data["report"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_window_excludes_old_prompts(self):
        texts = [p["text"] for s in self.data["sessions"] for p in s["prompts"]]
        self.assertFalse(any("Old prompt" in t for t in texts))
        self.assertEqual(self.r["overview"]["prompts"], 5)  # review, correction, /review, spec, pasted handoff

    def test_usage_and_never_used(self):
        self.assertEqual(dict(self.r["usage"]["agents"]), {"dev-squad:code-reviewer": 1})
        self.assertEqual(dict(self.r["usage"]["commands"]), {"dev-squad:review": 1})
        self.assertEqual(self.r["never_used"]["agents"], ["dev-squad:developer", "dev-squad:qa-engineer"])
        self.assertEqual(self.r["never_used"]["commands"], ["dev-squad:feature"])

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
        self.assertEqual(st["runs"], 1)
        self.assertEqual(st["blocked_or_input"], 1)
        self.assertEqual([x["next"] for x in st["invalid_next"]], ["test-writer"])

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
