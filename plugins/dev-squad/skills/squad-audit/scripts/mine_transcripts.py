#!/usr/bin/env python3
"""mine_transcripts — extract squad-usage evidence from Claude Code session transcripts.

Reads ~/.claude/projects/**/<session>.jsonl (+ <session>/subagents/agent-*.jsonl and their
.meta.json) and the installed agent/skill/command definitions, then reports — with a source
reference (file:line) for every item:

  - work inventory: user prompts classified by work type and domain, and whether a squad
    agent / command was used in that turn
  - agent, command and skill usage, including definitions that were NEVER used
  - signals of missing or weak agents: long from-scratch prompts, instructions repeated across
    sessions, corrections right after an agent/command ran, manual hand-offs (pasted Handoff
    blocks), interrupted turns, sub-agent tool errors, Handoff blocks missing or naming
    agents that do not exist
  - skipped steps: sessions that changed code but ran no tests / no review

Stdlib only. Snippets are truncated and secrets/emails are redacted; nothing leaves the machine.

Examples:
  python mine_transcripts.py --days 30 --md /tmp/audit.md --json /tmp/audit.json
  python mine_transcripts.py --since 2026-10-01 --project my-service --scope dev-squad --scope lab
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

HOME = os.path.expanduser("~")

# --------------------------------------------------------------------------- heuristics

WORK_TYPES = [  # (category, regex) — first match wins; keep specific before generic
    ("incident", r"\b(incident|outage|sev[1-4]|prod(uction)? (is )?(down|chết|sập)|sự cố|postmortem|rollback|5\d\d (error|lỗi))"),
    ("performance", r"\b(perf(ormance)?|latency|slow|chậm|p9[59]|throughput|lag\b|bottleneck|load test|spike|n\+1|profil)"),
    ("db-migration", r"\b(migration|migrate|flyway|liquibase|alembic|schema|alter table|backfill|index\b|ddl)"),
    ("upgrade", r"\b(upgrade|nâng cấp|bump|cve|outdated|deprecat|spring boot [23]|java (17|21)|node \d\d)"),
    ("bugfix", r"\b(bug|lỗi|error|exception|stack ?trace|fail(s|ed|ing)?|broken|crash|npe|fix|sửa)"),
    ("review", r"\b(review|đánh giá code|check (my|this|the) (code|pr|diff)|code smell)"),
    ("test", r"\b(test|kiểm thử|junit|pytest|coverage|e2e|testcontainers)"),
    ("security", r"\b(security|bảo mật|vuln|owasp|secret|authz|authn|injection|xss|csrf)"),
    ("infra-devops", r"\b(k8s|kubernetes|helm|docker|compose|ci/cd|pipeline|github actions|terraform|deploy|argo)"),
    ("docs", r"\b(readme|docs?\b|document|tài liệu|changelog|runbook|viết doc)"),
    ("planning", r"\b(plan|kế hoạch|sprint|task|backlog|estimate|ước lượng|user stor|requirement|yêu cầu|standup)"),
    ("design", r"\b(design|thiết kế|architecture|kiến trúc|adr\b|api contract|data model)"),
    ("research-ml", r"\b(paper|arxiv|survey|experiment|thí nghiệm|dataset|training|fine-?tun|model\b|benchmark|llm|ml\b)"),
    ("git-pr", r"\b(mr\b|pr\b|pull request|merge request|commit|push|rebase|tạo mr|tạo pr)"),
    ("feature", r"\b(implement|add|thêm|build|create|tạo|feature|tính năng|endpoint|viết code|code)"),
    ("question", r"(\?\s*$|^(what|why|how|is|can|does|làm sao|tại sao|như thế nào|có nên|giải thích|explain))"),
]
WORK_TYPES = [(c, re.compile(p, re.I | re.M)) for c, p in WORK_TYPES]

DOMAINS = {
    "java": r"\b(java|jvm|maven|gradle|spring)\b",
    "quarkus": r"\bquarkus\b",
    "kafka": r"\b(kafka|consumer group|producer|topic|offset)\b",
    "k8s": r"\b(k8s|kubernetes|kubectl|helm|pod|deployment\.ya?ml)\b",
    "postgres": r"\b(postgres(ql)?|psql|pg_\w+)\b",
    "nextjs": r"\b(next\.?js|react|tsx|vercel)\b",
    "snmp": r"\b(snmp\w*|mib|oid|snmp4j|trap|walk)\b",
    "ovng": r"\bovng\b",
    "network": r"\b(switch|router|vlan|bgp|ospf|netconf|ssh vào|ip address)\b",
    "ml-research": r"\b(paper|arxiv|experiment|dataset|training|eval|llm)\b",
    "homelab": r"\b(homelab|proxmox|truenas|unraid|home ?assistant|raspberry)\b",
}
DOMAINS = {k: re.compile(v, re.I) for k, v in DOMAINS.items()}

CORRECTION = re.compile(
    r"(không đúng|sai rồi|chưa đúng|làm lại|không phải (vậy|thế|cái)|nhầm rồi|bị sai|vẫn sai|vẫn lỗi|"
    r"tôi đã (nói|bảo|dặn)|như (tôi )?đã nói|nhắc lại lần|lần trước đã|"
    r"\bwrong\b|\bincorrect\b|not what i (asked|wanted|meant)|\bredo\b|try again|you (forgot|missed|ignored)|"
    r"i (already )?(said|told you)|as i said|still (wrong|broken|failing)|that'?s not (it|right|what))",
    re.I)
TEST_CMD = re.compile(r"(mvnw?|gradlew?)\b.*\b(test|verify|check)\b|\bpytest\b|\bunittest\b|"
                      r"\b(npm|pnpm|yarn) (run )?test\b|\bgo test\b|\bjest\b|\bvitest\b|\bcargo test\b|"
                      r"quarkus:test|\bplaywright test\b", re.I)
CHANGE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
IN_PROGRESS_SECONDS = 2 * 3600  # an unfinished run untouched for longer than this is counted, not skipped
SLASH = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")
SLASH_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
HANDOFF = re.compile(r"###\s*Handoff", re.I)
HANDOFF_STATUS = re.compile(r"Status:\s*\**\s*(done|blocked|needs-input)", re.I)
HANDOFF_NEXT = re.compile(r"-\s*Next:\s*`?([A-Za-z][\w:-]*)`?", re.I)
NOISE_PREFIXES = ("<task-notification>", "<system-reminder>", "<local-command", "Caveat:", "<bash-",
                  "<command-message>", "[Request interrupted")

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[private-key]"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[aws-key]"),
    (re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}\b"), "[github-token]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "[slack-token]"),
    (re.compile(r"\b(sk|rk|pk)[-_](live|test|ant|proj)?[-_]?[A-Za-z0-9_-]{16,}\b"), "[api-key]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"), "[gitlab-token]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "[google-key]"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"), "[npm-token]"),
    (re.compile(r"(?i)\bauthorization\s*[:=]\s*(basic|bearer|token|digest)?\s*[^\s\"',}]+"), "authorization=[redacted]"),
    (re.compile(r"""(?i)["']?\b(password|passwd|pwd|secret|client[_-]?secret|token|access[_-]?token|refresh[_-]?token|"""
                r"""api[_-]?key|apikey|access[_-]?key|private[_-]?key)\b["']?\s*[:=]\s*["']?[^\s"',}]+["']?"""),
     r"\1=[redacted]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[jwt]"),
    (re.compile(r"(?i)\b(bearer|token|apikey|api_key|password|passwd|pwd|secret)\b\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [redacted]"),
    (re.compile(r"(?i)\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^\s@/]+@"), r"\1://[redacted]@"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "[hex]"),
]


def redact(text):
    for pat, rep in SECRET_PATTERNS:
        text = pat.sub(rep, text)
    return text


def snippet(text, n):
    text = redact(" ".join(text.split()))
    return text if len(text) <= n else text[: n - 1] + "…"


def classify(text):
    for cat, pat in WORK_TYPES:
        if pat.search(text):
            return cat
    return "other"


def domains_of(text):
    return sorted(k for k, p in DOMAINS.items() if p.search(text))


def norm_sentence(s):
    s = s.lower()
    s = re.sub(r"`[^`]*`|\S*[/\\]\S*|\d+", " ", s)  # drop code spans, paths, numbers
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


# --------------------------------------------------------------------------- definitions

def read_frontmatter_name(path):
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(4000)
    except OSError:
        return None
    m = re.match(r"---\s*\n(.*?)\n---", head, re.S)
    if m:
        n = re.search(r"^name:\s*['\"]?([\w.:-]+)", m.group(1), re.M)
        if n:
            return n.group(1)
    return None


def discover_definitions(roots, scope):
    """Return {'agents': {qualified: path}, 'skills': {...}, 'commands': {...}}."""
    defs = {"agents": {}, "skills": {}, "commands": {}}
    manifests = set()
    for root in roots:
        root = os.path.expanduser(root)
        manifests.update(glob.glob(os.path.join(root, "**", ".claude-plugin", "plugin.json"), recursive=True))
    for mf in sorted(manifests):
        base = os.path.dirname(os.path.dirname(mf))
        try:
            with open(mf, encoding="utf-8") as fh:
                plugin = json.load(fh).get("name") or os.path.basename(base)
        except (OSError, ValueError):
            plugin = os.path.basename(base)
        if scope and plugin not in scope:
            continue
        for p in glob.glob(os.path.join(base, "agents", "*.md")):
            name = read_frontmatter_name(p) or os.path.splitext(os.path.basename(p))[0]
            defs["agents"].setdefault(f"{plugin}:{name}", p)
        for p in glob.glob(os.path.join(base, "skills", "*", "SKILL.md")):
            name = read_frontmatter_name(p) or os.path.basename(os.path.dirname(p))
            defs["skills"].setdefault(f"{plugin}:{name}", p)
        for p in glob.glob(os.path.join(base, "commands", "*.md")):
            defs["commands"].setdefault(f"{plugin}:{os.path.splitext(os.path.basename(p))[0]}", p)
    for loose in (os.path.join(HOME, ".claude", "agents"), os.path.join(os.getcwd(), ".claude", "agents")):
        if not scope:
            for p in glob.glob(os.path.join(loose, "*.md")):
                name = read_frontmatter_name(p) or os.path.splitext(os.path.basename(p))[0]
                defs["agents"].setdefault(name, p)
    return defs


# --------------------------------------------------------------------------- parsing

def iter_jsonl(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                yield i, obj


def msg_of(d):
    m = d.get("message")
    return m if isinstance(m, dict) else {}


def blocks(content):
    return [x for x in content if isinstance(x, dict)] if isinstance(content, list) else []


def parse_ts(s):
    if not s:
        return None
    try:
        ts = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def has_tool_result(content):
    return isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content)


def parse_subagent(path, known_agents):
    meta = {}
    mp = path[: -len(".jsonl")] + ".meta.json"
    if os.path.exists(mp):
        try:
            with open(mp, encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            meta = {}
    info = {"file": path, "agent": meta.get("agentType") or "unknown", "finished": meta.get("finished"),
            "in_progress": bool(meta) and meta.get("finished") is None
            and (dt.datetime.now().timestamp() - os.path.getmtime(path)) < IN_PROGRESS_SECONDS,
            "description": meta.get("description", ""), "tool_uses": 0, "tool_errors": 0,
            "changed_code": False, "ran_tests": False, "last_text": "", "first_ts": None, "last_ts": None}
    for _, d in iter_jsonl(path):
        ts = parse_ts(d.get("timestamp"))
        if ts:
            info["first_ts"] = info["first_ts"] or ts
            info["last_ts"] = ts
        c = msg_of(d).get("content")
        if d.get("type") == "assistant" and isinstance(c, list):
            for x in blocks(c):
                if x.get("type") == "tool_use":
                    info["tool_uses"] += 1
                    if x.get("name") in CHANGE_TOOLS:
                        info["changed_code"] = True
                    if x.get("name") == "Bash" and TEST_CMD.search(str((x.get("input") or {}).get("command", ""))):
                        info["ran_tests"] = True
            t = text_of(c)
            if t.strip():
                info["last_text"] = t
        elif d.get("type") == "user" and isinstance(c, list):
            info["tool_errors"] += sum(1 for x in blocks(c) if x.get("type") == "tool_result" and x.get("is_error"))
    lt = info.pop("last_text")
    info["has_handoff"] = bool(HANDOFF.search(lt))
    st = HANDOFF_STATUS.search(lt)
    info["handoff_status"] = st.group(1).lower() if st else None
    nx = HANDOFF_NEXT.search(lt)
    nxt = nx.group(1) if nx else None
    info["handoff_next"] = nxt
    if nxt and known_agents:
        short = {k.split(":")[-1] for k in known_agents}
        info["handoff_next_valid"] = nxt.lower() in {"user", "none", "n/a", "-"} or nxt in short or nxt in known_agents
    else:
        info["handoff_next_valid"] = None
    dur = (info["last_ts"] - info["first_ts"]).total_seconds() if info["first_ts"] and info["last_ts"] else None
    info["duration_s"] = round(dur, 1) if dur is not None else None
    info["start"] = info.pop("first_ts")
    info.pop("last_ts")
    return info


def parse_session(path, args, known_agents):
    rel = os.path.relpath(path, os.path.expanduser(args.root))
    sess = {"file": rel, "project": None, "branch": None, "start": None, "end": None, "prompts": [],
            "agents": Counter(), "skills": Counter(), "commands": Counter(), "tool_errors": 0,
            "interrupts": 0, "changed_code": False, "ran_tests": False, "cost_usd": None, "subagents": []}
    turn = None

    def close_turn():
        if turn is not None:
            sess["prompts"].append(turn)

    for ln, d in iter_jsonl(path):
        typ = d.get("type")
        ts = parse_ts(d.get("timestamp"))
        if ts:
            sess["start"] = sess["start"] or ts
            sess["end"] = ts
        sess["project"] = sess["project"] or d.get("cwd")
        sess["branch"] = sess["branch"] or d.get("gitBranch")
        if typ == "cost-state":
            sess["cost_usd"] = d.get("totalCostUSD")
            continue
        if d.get("isSidechain"):
            continue
        c = msg_of(d).get("content")
        if typ == "user" and not d.get("isMeta") and not has_tool_result(c):
            raw = text_of(c)
            if not raw.strip():
                continue
            if raw.startswith("[Request interrupted"):
                sess["interrupts"] += 1
                if turn is not None:
                    turn["interrupted"] = True
                continue
            cmd = SLASH.search(raw[:400]) if raw.lstrip().startswith("<command-") else None
            if not cmd and raw.lstrip().startswith(NOISE_PREFIXES):
                continue
            close_turn()
            text = raw
            command = None
            if cmd:
                command = cmd.group(1)
                a = SLASH_ARGS.search(raw)
                text = f"/{command} " + (a.group(1).strip() if a else "")
                sess["commands"][command] += 1
            turn = {"ref": f"{rel}:{ln}", "ts": ts.isoformat() if ts else None, "chars": len(text),
                    "category": classify(text[:args.intent_chars]), "domains": domains_of(text[:args.intent_chars]),
                    "command": command,
                    "agents": [], "skills": [], "correction": bool(CORRECTION.search(text)) and len(text) < 1200,
                    "pasted_handoff": bool(HANDOFF.search(text)), "large_paste": len(text) > args.large_paste,
                    "changed_code": False, "ran_tests": False, "tool_errors": 0,
                    "interrupted": False, "text": snippet(text, args.snippet), "_norm": text[:20000]}
            continue
        if typ == "assistant" and isinstance(c, list):
            for x in blocks(c):
                if x.get("type") != "tool_use":
                    continue
                name, inp = x.get("name"), x.get("input") or {}
                if name in ("Agent", "Task"):
                    a = inp.get("subagent_type") or "general-purpose"
                    sess["agents"][a] += 1
                    if turn is not None:
                        turn["agents"].append(a)
                elif name == "Skill":
                    s = inp.get("skill") or inp.get("name") or "?"
                    sess["skills"][s] += 1
                    if turn is not None:
                        turn["skills"].append(s)
                elif name in CHANGE_TOOLS and turn is not None:
                    turn["changed_code"] = True
                elif name == "Bash" and turn is not None and TEST_CMD.search(str(inp.get("command", ""))):
                    turn["ran_tests"] = True
        elif typ == "user" and isinstance(c, list) and turn is not None:
            turn["tool_errors"] += sum(1 for x in blocks(c) if x.get("type") == "tool_result" and x.get("is_error"))
    close_turn()

    sub_dir = path[: -len(".jsonl")]
    for sp in sorted(glob.glob(os.path.join(sub_dir, "subagents", "*.jsonl"))):
        info = parse_subagent(sp, known_agents)
        info["file"] = os.path.relpath(sp, os.path.expanduser(args.root))
        sess["subagents"].append(info)
    return sess


def finalize_session(s):
    """Derive session flags from the in-window turns and sub-agent runs only."""
    s["changed_code"] = any(p["changed_code"] for p in s["prompts"]) or any(x["changed_code"] for x in s["subagents"])
    s["ran_tests"] = any(p["ran_tests"] for p in s["prompts"]) or any(x["ran_tests"] for x in s["subagents"])
    s["tool_errors"] = sum(p["tool_errors"] for p in s["prompts"])


# --------------------------------------------------------------------------- analysis

def analyse(sessions, defs, args):
    prompts = [p for s in sessions for p in s["prompts"]]
    agent_use, cmd_use, skill_use = Counter(), Counter(), Counter()
    for p in prompts:
        agent_use.update(p["agents"])
        skill_use.update(p["skills"])
        if p["command"]:
            cmd_use[p["command"]] += 1

    cats = defaultdict(lambda: {"count": 0, "with_squad": 0, "examples": [], "agents": Counter(), "commands": Counter()})
    for p in prompts:
        c = cats[p["category"]]
        c["count"] += 1
        used = p["agents"] or p["command"] or p["skills"]
        if used:
            c["with_squad"] += 1
        c["agents"].update(p["agents"])
        if p["command"]:
            c["commands"][p["command"]] += 1
        if len(c["examples"]) < 3:
            c["examples"].append({"ref": p["ref"], "text": p["text"]})
    domains = Counter(d for p in prompts for d in p["domains"])
    domain_examples = defaultdict(list)
    for p in prompts:
        for d in p["domains"]:
            if len(domain_examples[d]) < 3:
                domain_examples[d].append({"ref": p["ref"], "text": p["text"]})

    # instructions repeated across sessions
    sent_sessions, sent_examples = defaultdict(set), {}
    for s in sessions:
        for p in s["prompts"]:
            if p["command"]:
                continue
            for sent in re.split(r"[.!?\n]+", p["_norm"]):
                n = norm_sentence(sent)
                if len(n.split()) >= args.min_words:
                    sent_sessions[n].add(s["file"])
                    sent_examples.setdefault(n, {"ref": p["ref"], "text": snippet(sent, args.snippet)})
    repeated = sorted(([len(v), k] for k, v in sent_sessions.items() if len(v) >= args.repeat), reverse=True)
    repeated = [{"sessions": n, **sent_examples[k]} for n, k in repeated[:25]]

    # near-duplicate prompt openings (same first words) across sessions
    openings, opening_sessions = defaultdict(list), defaultdict(set)
    for s in sessions:
        for p in s["prompts"]:
            if p["command"]:
                continue
            key = " ".join(norm_sentence(p["_norm"]).split()[:8])
            if len(key.split()) >= 5:
                openings[key].append(p)
                opening_sessions[key].add(s["file"])
    similar = sorted(([len(opening_sessions[k]), k] for k in openings if len(opening_sessions[k]) >= args.repeat),
                     reverse=True)
    similar = [{"count": n, "examples": [{"ref": x["ref"], "text": x["text"]} for x in openings[k][:3]]}
               for n, k in similar[:15]]

    corrections = []
    for s in sessions:
        last_actor = None
        for p in s["prompts"]:
            if p["correction"] and last_actor:
                corrections.append({"ref": p["ref"], "after": last_actor, "text": p["text"]})
            actors = [f"agent:{a}" for a in p["agents"]] + ([f"command:{p['command']}"] if p["command"] else []) \
                + [f"skill:{k}" for k in p["skills"]]
            last_actor = ", ".join(dict.fromkeys(actors)) if actors else "main-thread"
    corrections_by_actor = Counter(c["after"] for c in corrections)

    long_prompts = sorted((p for p in prompts if p["chars"] >= args.long_prompt and not p["command"]),
                          key=lambda p: -p["chars"])
    long_prompts = [{"ref": p["ref"], "chars": p["chars"], "category": p["category"],
                     "used_squad": bool(p["agents"] or p["skills"]), "text": p["text"]} for p in long_prompts[:20]]
    manual_handoffs = [{"ref": p["ref"], "chars": p["chars"], "text": p["text"]} for p in prompts if p["pasted_handoff"]][:20]
    large_pastes = [{"ref": p["ref"], "chars": p["chars"], "category": p["category"], "text": p["text"]}
                    for p in prompts if p["large_paste"] and not p["pasted_handoff"]][:20]
    interrupted = [{"ref": p["ref"], "agents": p["agents"], "command": p["command"], "text": p["text"]}
                   for p in prompts if p["interrupted"]][:20]

    subs = [x for s in sessions for x in s["subagents"]]
    in_progress = [x for x in subs if x["in_progress"]]
    subs = [x for x in subs if not x["in_progress"]]  # still running (e.g. this very audit): would skew health metrics
    sub_stats = defaultdict(lambda: {"runs": 0, "unfinished": 0, "tool_errors": 0, "no_handoff": 0,
                                     "blocked_or_input": 0, "invalid_next": [], "durations": []})
    for x in subs:
        st = sub_stats[x["agent"]]
        st["runs"] += 1
        st["unfinished"] += 1 if x["finished"] is False else 0
        st["tool_errors"] += x["tool_errors"]
        if x["agent"].startswith("dev-squad:") and not x["has_handoff"]:  # Handoff is a dev-squad convention
            st["no_handoff"] += 1
        if x["handoff_status"] in ("blocked", "needs-input"):
            st["blocked_or_input"] += 1
        if x["handoff_next_valid"] is False:
            st["invalid_next"].append({"next": x["handoff_next"], "file": x["file"]})
        if x["duration_s"] is not None:
            st["durations"].append(x["duration_s"])
    for st in sub_stats.values():
        d = st.pop("durations")
        st["median_duration_s"] = round(statistics.median(d), 1) if d else None

    skipped = []
    for s in sessions:
        if s["changed_code"]:
            reviewed = any("code-reviewer" in a for p in s["prompts"] for a in p["agents"]) or \
                any("review" in (p["command"] or "") for p in s["prompts"])
            if not s["ran_tests"] or not reviewed:
                skipped.append({"file": s["file"], "project": s["project"], "ran_tests": s["ran_tests"],
                                "reviewed": reviewed})

    never = {}
    for kind in ("agents", "commands", "skills"):
        shorts = Counter(k.split(":")[-1] for k in defs[kind])
        unique = frozenset(n for n, c in shorts.items() if c == 1)
        never[kind] = sorted(k for k in defs[kind] if not _used(k, kind, agent_use, cmd_use, skill_use, unique))

    projects = Counter(s["project"] for s in sessions)
    return {
        "overview": {
            "sessions": len(sessions), "prompts": len(prompts), "subagent_runs": len(subs),
            "subagent_runs_in_progress": len(in_progress),
            "first": min((p["ts"] for p in prompts if p["ts"]), default=None),
            "last": max((p["ts"] for p in prompts if p["ts"]), default=None),
            "projects": projects.most_common(), "cost_usd": round(sum(s["cost_usd"] or 0 for s in sessions), 2),
            "sessions_with_squad": sum(1 for s in sessions if any(p["agents"] or p["command"] or p["skills"] for p in s["prompts"])),
        },
        "usage": {"agents": agent_use.most_common(), "commands": cmd_use.most_common(), "skills": skill_use.most_common()},
        "never_used": never,
        "definitions": {k: sorted(v) for k, v in defs.items()},
        "work_inventory": {k: {**v, "agents": v["agents"].most_common(5), "commands": v["commands"].most_common(5)}
                           for k, v in sorted(cats.items(), key=lambda kv: -kv[1]["count"])},
        "domains": {d: {"count": n, "examples": domain_examples[d]} for d, n in domains.most_common()},
        "signals": {
            "repeated_instructions": repeated, "similar_prompts": similar, "long_prompts": long_prompts,
            "corrections": corrections[:40], "corrections_by_actor": corrections_by_actor.most_common(),
            "manual_handoffs": manual_handoffs, "large_pastes": large_pastes, "interrupted_turns": interrupted,
            "skipped_steps": skipped[:40], "skipped_steps_total": len(skipped),
            "sessions_changed_code": sum(1 for s in sessions if s["changed_code"]),
        },
        "subagents": dict(sorted(sub_stats.items(), key=lambda kv: -kv[1]["runs"])),
    }


def _used(qualified, kind, agent_use, cmd_use, skill_use, unique_short=frozenset()):
    """Match by qualified name (plugin:name); a bare name also counts when only one definition has it."""
    short = qualified.split(":")[-1]
    pool = agent_use if kind == "agents" else cmd_use + skill_use  # a skill can also run as /plugin:skill
    bare_ok = ":" not in qualified or short in unique_short
    return any(u == qualified or (bare_ok and u == short) for u in pool)


# --------------------------------------------------------------------------- output

def to_markdown(r, args):
    o = r["overview"]
    L = [f"# Squad usage evidence ({args.window_label})", "",
         f"- Sessions: **{o['sessions']}** ({o['sessions_with_squad']} used a squad agent/command/skill) · "
         f"prompts: **{o['prompts']}** · sub-agent runs: **{o['subagent_runs']}** · cost of these sessions (whole-session totals): ${o['cost_usd']}",
         f"- Period covered by data: {o['first']} → {o['last']}",
         ("- ⚠️ All sub-agent runs look in progress; health metrics are empty. "
          if o['subagent_runs'] == 0 and o['subagent_runs_in_progress'] else "")
         + f"- In-progress sub-agent runs excluded from health metrics: {o['subagent_runs_in_progress']}"
         + (f" · excluded projects: {', '.join(args.exclude_project)}" if args.exclude_project else ""),
         "- Projects: " + ", ".join(f"`{p}` ({n})" for p, n in o["projects"][:10]), ""]

    L += ["## Work inventory (heuristic classification of user prompts)", "",
          "| Work type | Prompts | With squad | Agents used | Commands | Example (source) |", "|---|---|---|---|---|---|"]
    for k, v in r["work_inventory"].items():
        ex = v["examples"][0] if v["examples"] else {"ref": "", "text": ""}
        L.append(f"| {k} | {v['count']} | {v['with_squad']} | {', '.join(f'{a}×{n}' for a, n in v['agents']) or '—'} | "
                 f"{', '.join(f'/{c}×{n}' for c, n in v['commands']) or '—'} | {ex['text'][:90]} (`{ex['ref']}`) |")
    L += ["", "## Domains mentioned", "", "| Domain | Prompts | Example (source) |", "|---|---|---|"]
    for d, v in r["domains"].items():
        ex = v["examples"][0]
        L.append(f"| {d} | {v['count']} | {ex['text'][:90]} (`{ex['ref']}`) |")

    L += ["", "## Usage", "", "| Agent | Calls |", "|---|---|"]
    L += [f"| {a} | {n} |" for a, n in r["usage"]["agents"]] or ["| — | 0 |"]
    L += ["", "| Command / skill | Uses |", "|---|---|"]
    L += [f"| /{c} | {n} |" for c, n in r["usage"]["commands"]] + [f"| skill {s} | {n} |" for s, n in r["usage"]["skills"]]
    for kind in ("agents", "commands", "skills"):
        nv = r["never_used"][kind]
        L += ["", f"**Never used {kind}** ({len(nv)}/{len(r['definitions'][kind])}): " + (", ".join(f"`{x}`" for x in nv) or "none")]

    s = r["signals"]
    L += ["", "## Sub-agent runs", "", "| Agent | Runs | Unfinished | Tool errors | No Handoff | Blocked/needs-input | Invalid Next | Median s |",
          "|---|---|---|---|---|---|---|---|"]
    for a, v in r["subagents"].items():
        inv = ", ".join(sorted({x["next"] for x in v["invalid_next"]})) or "—"
        L.append(f"| {a} | {v['runs']} | {v['unfinished']} | {v['tool_errors']} | {v['no_handoff']} | "
                 f"{v['blocked_or_input']} | {inv} | {v['median_duration_s']} |")

    def section(title, items, fmt):
        L.extend(["", f"## {title} ({len(items)})", ""])
        L.extend(fmt(i) for i in items) if items else L.append("_none found_")

    section("Corrections right after an agent/command/main-thread turn", s["corrections"],
            lambda i: f"- after **{i['after']}**: {i['text']} (`{i['ref']}`)")
    L.append("") if s["corrections_by_actor"] else None
    if s["corrections_by_actor"]:
        L.append("By actor: " + ", ".join(f"{a} ×{n}" for a, n in s["corrections_by_actor"]))
    section("Instructions repeated in ≥%d sessions" % args.repeat, s["repeated_instructions"],
            lambda i: f"- {i['sessions']} sessions: {i['text']} (`{i['ref']}`)")
    section("Similar prompt openings (≥%d)" % args.repeat, s["similar_prompts"],
            lambda i: f"- ×{i['count']}: " + " | ".join(f"{e['text'][:80]} (`{e['ref']}`)" for e in i["examples"]))
    section("Long from-scratch prompts (≥%d chars)" % args.long_prompt, s["long_prompts"],
            lambda i: f"- {i['chars']} chars, {i['category']}, squad used: {i['used_squad']}: {i['text']} (`{i['ref']}`)")
    section("Manual hand-offs (Handoff blocks pasted by the user)", s["manual_handoffs"],
            lambda i: f"- {i['chars']} chars: {i['text']} (`{i['ref']}`)")
    section("Large pastes (≥%d chars: specs, logs, outputs copied in by hand)" % args.large_paste, s["large_pastes"],
            lambda i: f"- {i['chars']} chars, {i['category']}: {i['text']} (`{i['ref']}`)")
    section("Interrupted turns", s["interrupted_turns"],
            lambda i: f"- agents={i['agents'] or '—'} command={i['command'] or '—'}: {i['text']} (`{i['ref']}`)")
    L += ["", f"## Skipped steps: {s['skipped_steps_total']} of {s['sessions_changed_code']} sessions that changed code "
              "ran no tests and/or no review", ""]
    L += [f"- `{i['file']}` tests={i['ran_tests']} review={i['reviewed']}" for i in s["skipped_steps"][:15]]
    L += ["", "_All classifications are keyword heuristics: verify each item in its source before citing it._"]
    return "\n".join(L) + "\n"


def show_context(root, ref, radius, width):
    """Print a readable view of the events around `<relative file>:<line>`."""
    rel, _, line = ref.rpartition(":")
    path = os.path.join(os.path.expanduser(root), rel)
    if not rel or not line.isdigit() or not os.path.isfile(path):
        sys.exit(f"Bad ref {ref!r}: expected <file relative to --root>:<line> of an existing transcript")
    target = int(line)
    for ln, d in iter_jsonl(path):
        if ln < target - radius * 3 or ln > target + radius * 3:
            continue
        typ = d.get("type")
        if typ not in ("user", "assistant") or d.get("isMeta"):
            continue
        c = msg_of(d).get("content")
        parts = []
        if isinstance(c, list):
            for x in blocks(c):
                if x.get("type") == "text" and x.get("text", "").strip():
                    parts.append(snippet(x["text"], width))
                elif x.get("type") == "tool_use":
                    inp = x.get("input") or {}
                    brief = inp.get("subagent_type") or inp.get("skill") or inp.get("command") or inp.get("file_path") or ""
                    parts.append(f"[tool_use {x.get('name')} {snippet(str(brief), 80)}]")
                elif x.get("type") == "tool_result":
                    parts.append("[tool_result" + (" ERROR" if x.get("is_error") else "") + "]")
        else:
            parts.append(snippet(text_of(c), width))
        mark = ">>" if ln == target else "  "
        print(f"{mark} {ln:>6} {typ:<9} {(d.get('timestamp') or '')[:19]}  " + " ".join(parts))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="~/.claude/projects", help="transcripts root (default ~/.claude/projects)")
    # note: cost_usd in the overview is the whole-session total reported by Claude Code, not window-limited
    ap.add_argument("--days", type=int, default=30, help="look-back window in days (default 30)")
    ap.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    ap.add_argument("--until", help="end date YYYY-MM-DD (inclusive)")
    ap.add_argument("--project", action="append", default=[], help="only sessions whose cwd contains this; repeatable")
    ap.add_argument("--exclude-project", action="append", default=[],
                    help="skip sessions whose cwd or path contains this (sandboxes, smoke tests, the current audit run)")
    ap.add_argument("--scope", action="append", default=[], help="plugin names to audit, e.g. dev-squad, lab; repeatable")
    ap.add_argument("--plugins-root", action="append", default=[],
                    help="where plugin definitions live (default ~/.claude/plugins); repeatable")
    ap.add_argument("--long-prompt", type=int, default=1000, help="chars that count as a long prompt (default 1000)")
    ap.add_argument("--repeat", type=int, default=3, help="occurrences that count as repeated (default 3)")
    ap.add_argument("--min-words", type=int, default=6, help="min words for a repeated-instruction sentence")
    ap.add_argument("--snippet", type=int, default=160, help="max snippet length (default 160)")
    ap.add_argument("--intent-chars", type=int, default=300,
                    help="classify work type/domain from the first N chars of a prompt (default 300)")
    ap.add_argument("--large-paste", type=int, default=4000, help="chars that count as a large paste (default 4000)")
    ap.add_argument("--json", help="write full results as JSON")
    ap.add_argument("--md", help="write a Markdown summary (default: print to stdout)")
    ap.add_argument("--show", metavar="REF", help="print the conversation around a source ref and exit; use --show=REF (refs start with '-')")
    ap.add_argument("--radius", type=int, default=4, help="events before/after for --show (default 4)")
    args = ap.parse_args()
    if args.show:
        show_context(args.root, args.show, args.radius, 300)
        return

    now = dt.datetime.now(dt.timezone.utc)
    since = dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc) if args.since \
        else now - dt.timedelta(days=args.days)
    until = (dt.datetime.fromisoformat(args.until).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)) \
        if args.until else now + dt.timedelta(minutes=1)
    args.window_label = f"{since.date()} → {(until - dt.timedelta(days=1)).date() if args.until else now.date()}"

    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        sys.exit(f"No transcripts directory at {root} — report 'không có dữ liệu' for this source.")
    defs = discover_definitions(args.plugins_root or [os.path.join(HOME, ".claude", "plugins")], set(args.scope))

    sessions, skipped_old = [], 0
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        rel = os.path.relpath(path, root)
        if dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc) < since:
            skipped_old += 1
            continue
        s = parse_session(path, args, defs["agents"])
        where = (s["project"] or "", rel)
        if args.project and not any(p in w for p in args.project for w in where):
            continue
        if any(x in w for x in args.exclude_project for w in where):
            continue
        s["prompts"] = [p for p in s["prompts"] if p["ts"] and since <= dt.datetime.fromisoformat(p["ts"]) < until]
        s["subagents"] = [x for x in s["subagents"] if x["start"] is None or since <= x["start"] < until]
        if not s["prompts"] and not s["subagents"]:
            continue
        finalize_session(s)
        sessions.append(s)
    sessions.sort(key=lambda s: s["start"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))

    report = analyse(sessions, defs, args)
    report["overview"]["window"] = args.window_label
    report["overview"]["files_outside_window"] = skipped_old
    for s in sessions:
        for p in s["prompts"]:
            p.pop("_norm", None)

    md = to_markdown(report, args)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"Markdown summary: {args.md}")
    else:
        sys.stdout.write(md)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"report": report, "sessions": sessions}, fh, indent=1, default=str, ensure_ascii=False)
        print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
