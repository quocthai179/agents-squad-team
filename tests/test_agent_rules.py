"""Lint the squad's prompts for rules that must not drift (stdlib only)."""

import glob
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN = os.path.join(ROOT, "plugins", "dev-squad")
NEVER_PUSH = "Never push, tag, or open/update an MR/PR"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


class AgentRulesTest(unittest.TestCase):
    def agents(self):
        for path in sorted(glob.glob(os.path.join(PLUGIN, "agents", "*.md"))):
            yield os.path.basename(path)[:-3], read(path)

    def test_every_bash_capable_subagent_never_pushes(self):
        for name, text in self.agents():
            if name == "orchestrator":  # may push as the main agent, after the review gate
                continue
            tools = re.search(r"^tools:\s*(.*)$", frontmatter(text), re.M)
            if tools and "Bash" not in tools.group(1):
                continue
            with self.subTest(agent=name):
                self.assertIn(NEVER_PUSH, text)

    def test_no_subagent_allows_push_when_asked(self):
        for name, text in self.agents():
            if name == "orchestrator":  # covered by the gate test below
                continue
            with self.subTest(agent=name):
                # git pushes only: `docker push` is a deploy action governed by the explicit-request rule
                self.assertNotRegex(text, r"(?i)(?<!docker )\bpush\b[^.\n]*\bunless\b[^.\n]*\b(ask|request)")

    def test_orchestrator_applies_gate_and_never_pushes_as_subagent(self):
        text = read(os.path.join(PLUGIN, "agents", "orchestrator.md"))
        self.assertIn("review gate", text)
        self.assertIn("When running as a sub-agent, never push", text)

    def test_agents_that_build_images_check_dockerignore(self):
        for name in ("developer", "devops-engineer"):
            with self.subTest(agent=name):
                text = read(os.path.join(PLUGIN, "agents", f"{name}.md"))
                self.assertRegex(text, r"\.dockerignore`? excludes `\.squad/`")

    def test_developer_never_waits_by_polling(self):
        text = read(os.path.join(PLUGIN, "agents", "developer.md"))
        self.assertIn("Never** wait with `sleep`", text)
        self.assertIn("Never re-run a build just to avoid waiting", text)
        self.assertIn("Requirements checklist", text)
        self.assertIn(".squad/tmp/.gitignore", text)


class AuditUpgradesTest(unittest.TestCase):
    """Rules adopted from the squad audit (R1-R12)."""

    def agent(self, name):
        return read(os.path.join(PLUGIN, "agents", f"{name}.md"))

    def description(self, name):
        return re.search(r"^description: (.*)$", self.agent(name), re.M).group(1)

    def test_every_agent_has_working_contract_lessons_and_user_actions(self):  # R10, R11
        for path in sorted(glob.glob(os.path.join(PLUGIN, "agents", "*.md"))):
            text = read(path)
            with self.subTest(agent=os.path.basename(path)):
                self.assertIn("**Working contract**", text)
                self.assertIn(".squad/LESSONS.md", text)
                self.assertIn("  - User actions:", text)

    def test_playbook_defines_contract_lessons_and_user_actions(self):  # R10, R11
        text = read(os.path.join(PLUGIN, "skills", "squad-playbook", "SKILL.md"))
        for needle in ("## Working contract", "## Lessons (`.squad/LESSONS.md`)", "- User actions:", "Việc bạn cần làm"):
            self.assertIn(needle, text)

    def test_reviewers_keep_status_to_three_words(self):  # R3
        for name in ("code-reviewer", "security-auditor"):
            with self.subTest(agent=name):
                self.assertIn("only these three words", self.agent(name))
        self.assertIn("Do NOT use for audits", self.description("code-reviewer"))

    def test_descriptions_route_the_right_work(self):  # R5, R6, R7, R8
        self.assertIn("realistic performance or load test", self.description("performance-engineer"))
        self.assertIn("CrashLoopBackOff", self.description("sre-incident-responder"))
        self.assertIn("**Always write one.**", self.agent("sre-incident-responder"))
        self.assertIn("Do NOT use for manual, exploratory or browser-driven", self.description("qa-engineer"))
        self.assertIn("Do NOT launch it as a sub-agent", self.description("orchestrator"))
        self.assertNotIn("Use PROACTIVELY", self.description("orchestrator"))

    def test_image_build_rule_covers_all_builders(self):  # R12
        for name in ("developer", "devops-engineer"):
            with self.subTest(agent=name):
                text = self.agent(name)
                self.assertIn("Before any image build", text)
                for builder in ("docker buildx build", "docker compose build", "podman build"):
                    self.assertIn(builder, text)

    def test_commit_msg_and_brief_commands(self):  # R1, R9
        commit = read(os.path.join(PLUGIN, "commands", "commit-msg.md"))
        self.assertIn("[A-Za-z][A-Za-z0-9]{1,9}[-_][0-9]{2,}", commit)
        self.assertIn("If the two differ, stop and ask", commit)
        self.assertIn("**Never push**", commit)
        brief = read(os.path.join(PLUGIN, "commands", "brief.md"))
        self.assertIn("never invent numbers", brief)
        self.assertIn("**Cần quyết định / hỗ trợ:**", brief)

    def test_review_accepts_mr_and_writes_fixed_path(self):  # R2
        text = read(os.path.join(PLUGIN, "commands", "review.md"))
        self.assertIn("`.squad/reports/review-mr-<id>.md`", text)
        self.assertIn("Never post comments, approve or merge", text)


class ReviewGateTest(unittest.TestCase):
    def test_playbook_defines_gate_and_blocking(self):
        text = read(os.path.join(PLUGIN, "skills", "squad-playbook", "SKILL.md"))
        self.assertIn("## Review gate before push / MR", text)
        self.assertIn("Critical or High", text)
        self.assertIn("Sub-agents never push", text)

    def test_review_command_maps_security_severity_and_decides(self):
        text = read(os.path.join(PLUGIN, "commands", "review.md"))
        self.assertIn("Critical or High", text)
        self.assertIn("READY TO PUSH", text)
        self.assertIn("NOT READY", text)

    def test_commands_that_mention_push_point_to_the_gate(self):
        for path in sorted(glob.glob(os.path.join(PLUGIN, "commands", "*.md"))):
            name = os.path.basename(path)
            text = read(path)
            if name == "review.md" or not re.search(r"\bpush", text):  # review.md is the gate itself
                continue
            with self.subTest(command=name):
                self.assertIn("review gate", text)
                self.assertIn("squad-playbook", text)

    def test_scratch_and_evidence_are_gitignored(self):
        ignore = read(os.path.join(ROOT, ".gitignore"))
        self.assertIn(".squad/tmp/", ignore)
        self.assertIn(".squad/audit/*/evidence/", ignore)

    def test_manifest_versions_match(self):
        plugin = json.loads(read(os.path.join(PLUGIN, ".claude-plugin", "plugin.json")))["version"]
        market = json.loads(read(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
        self.assertEqual(market["metadata"]["version"], plugin)
        self.assertEqual(market["plugins"][0]["version"], plugin)


if __name__ == "__main__":
    unittest.main()
