---
name: squad-audit
description: Evidence-based audit of an agent squad (dev-squad, lab or any plugin agents) from the user's real work history — Claude Code transcripts, .squad/ and research/ artifacts, git history and the agent definitions — to find missing, weak, overlapping or unused agents and concrete improvements. Use when asked to audit, review or retro the squad, "which agents am I missing", "which agents are useless", "đánh giá squad", "thiếu agent gì", or to measure whether squad changes helped.
---

# Squad audit playbook

The goal is a **decision-ready audit backed by real evidence**. Every claim cites a source; anything not backed by data is labelled as a guess; sources that could not be read are reported as **"không có dữ liệu"** and lower the confidence of everything that depends on them.

Tools live in this skill's `scripts/` directory (its base directory is shown when the skill loads).

## 1. Collect evidence (in this order)

Create `.squad/audit/<YYYY-MM-DD>/` in the current project and put all evidence files in `evidence/` inside it. Evidence holds redacted conversation snippets, so **first** make sure `.squad/audit/.gitignore` exists and contains `*/evidence/`. Create it if it is missing. This stops evidence from being committed by accident.

Exclude sandboxes, smoke tests and the audit's own working copy with `--exclude-project <substring>`. Runs that are still in progress, including the current audit, are excluded from sub-agent health metrics automatically.

**1. Session transcripts.** These are in `~/.claude/projects/**/*.jsonl`, with sub-agent runs in `<session>/subagents/`.

```bash
python scripts/mine_transcripts.py --days 30 --scope dev-squad --scope lab \
  --md .squad/audit/<date>/evidence/usage.md --json .squad/audit/<date>/evidence/usage.json
# add --plugins-root <repo>/plugins when auditing a plugin checked out locally (definitions under development)
# add --project <substring> to restrict to some repositories; --since/--until for an exact window
python scripts/mine_transcripts.py --show=<ref> --radius 4   # read the context of one evidence item
```

The miner covers:
- **Work inventory**: work type and domain per prompt, and whether a squad agent or command was used in that turn.
- **Usage**: per agent, command and skill. It also lists definitions that were **never used**.
- **Corrections** right after an agent or command ran.
- **Instructions repeated** across sessions, and similar prompt openings.
- **Long prompts written from scratch**.
- **Hand-offs and pastes**: Handoff blocks pasted by the user, and large pastes.
- **Interrupted turns**.
- **Sub-agent health**: tool errors, missing Handoff, blocked or needs-input statuses, and `Next:` lines naming agents that don't exist.
- **Skipped steps**: sessions that changed code without running tests or a review.

Everything is a **keyword heuristic**. Open the source with `--show` before you cite an item, and drop false positives. For example, a "correction" may only be a follow-up question.

claude.ai chats are not on disk. Use conversation-search tools only if they are available to you; otherwise record "không có dữ liệu", or ask the user to export the relevant chats.

**2. Squad artifacts.**
- dev-squad: `.squad/TASKS.md`, `.squad/reports/`, `.squad/incidents/`, `.squad/design/`, `.squad/adr/`, `.squad/perf/`, earlier `.squad/audit/`.
- lab: `research/PROJECT.md`, `research/lessons/LESSONS.md`, `research/lessons/squad-issues.md`, `research/lessons/retros/`, `research/experiments/*/` (ledger, `FINDINGS.md`), `research/reviews/`, `research/decisions.md`.

Search for them in the projects the miner lists (overview → projects) and in the current repository.

**3. Git history.** For each relevant repository:
- `git log --since=<date> --pretty='%h %ad %an %s' --date=short`
- `git log --since=<date> --stat --format='%h %s'`
- Look for conventional-commit prefixes, reverts, "fix fix" chains, and commits co-authored by Claude.
- Read PRs and their review comments through the GitHub tools when they are available.

**4. Current definitions.** Read every agent, skill and command file the miner lists under `definitions`:
- the description, i.e. the trigger conditions,
- `tools` and `model`,
- prompt length and structure,
- the Handoff format.

Compare descriptions pairwise to find overlaps and triggers that are ambiguous.

## 2. Signals of a missing or weak agent

| Signal | Threshold | Where to look |
|---|---|---|
| Repeated work done by hand or via long from-scratch prompts | ≥3 occurrences | work inventory with `with squad = 0`, long prompts, similar openings |
| Output rewritten or instruction repeated | ≥2 corrections after the same agent, or the same instruction in ≥3 sessions | corrections by actor, repeated instructions |
| Broken hand-offs | any pasted Handoff block or large paste between agent steps; invalid `Next:` | manual hand-offs, large pastes, sub-agent table |
| Wrong trigger / never called | agent never used while its work type occurs; agent used for work outside its description | never used, work inventory × agents |
| Skipped steps | >30% of code-changing sessions without tests or review; no retro/postmortem after incidents | skipped steps, `.squad/`, `research/lessons/` |
| Domain gap | ≥3 prompts in a domain (SNMP/MIB, Quarkus, OVNG, K8s…) with corrections or long prompts | domains + corrections + long prompts |

## 3. Evidence rules

- Cite as `` `file:line` ``, `` `.squad/...` ``, `` `research/...` ``, or `` `<repo>@<sha>` ``. Quote at most one sentence, and keep secrets and personal data redacted.
- Prefix claims with **Dữ liệu cho thấy** (data shows) or **Suy đoán** (inference).
- Rate the confidence of each section (cao / trung bình / thấp) from source coverage and sample size. If there are fewer than ~10 sessions in the window, say so up front.
- **Never propose a new agent without ≥2 real examples.** Prefer editing, merging or narrowing an existing agent, skill or command first. Every new agent adds routing cost and always-on tokens.

## 4. Report template

Write `.squad/audit/<date>/squad-audit.md` in Vietnamese, keeping technical terms in English:

```markdown
# Squad audit — <scope> — <window>
Nguồn dữ liệu: transcripts (<n> sessions, <m> prompts) | .squad/ (<có/không có dữ liệu>) | research/ (…) | git (<repos>) | definitions (<n> agents) | claude.ai (không có dữ liệu …)

## 1. TL;DR (3–5 bullets)
## 2. Work inventory
| Loại việc | Số lần | Ví dụ (≤1 câu + nguồn) | Agent/command đã dùng | Kết quả |
## 3. Đánh giá agent hiện có
| Agent | Tần suất | Điểm mạnh | Lỗi lặp lại (nguồn) | Chồng chéo với | Đề xuất: giữ / sửa prompt / sửa description / gộp / bỏ |
## 4. Đề xuất agent mới (≤5, xếp theo ROI)
### <name> — ROI: cao/trung bình
- Bằng chứng (≥2): …
- Vấn đề + thời gian tiết kiệm ước tính (cách tính): …
- Vì sao không sửa agent hiện có: …
- Bản nháp: `.squad/audit/<date>/drafts/agents/<name>.md`
## 5. Cải tiến agent/skill/pipeline và hệ thống
| # | Thay đổi | Bằng chứng | Diff / đoạn thay thế | Công sức |
## 6. Kế hoạch hành động
### Quick wins (≤1 giờ) ### Tuần này ### Tháng này
## 7. Metric theo dõi (đo lại sau 2–4 tuần bằng cùng lệnh mine_transcripts.py)
| Metric | Hiện tại | Mục tiêu | Cách đo |
## 8. Giới hạn của audit
## Phụ lục: tự phản biện (đề xuất đã loại hoặc hạ ưu tiên, và lý do)
```

Good follow-up metrics come straight from the miner, so they can be re-measured with the same command:
- % of prompts that used the squad
- corrections per agent run
- number of long from-scratch prompts
- number of never-used agents
- skipped-step rate
- Handoff compliance and invalid `Next:` count
- sub-agent tool errors per run

## 5. Draft agent template

Save drafts under `.squad/audit/<date>/drafts/agents/`, never directly into a plugin:

```markdown
---
name: <kebab-case>
description: <role>. Use PROACTIVELY when <concrete trigger conditions seen in the evidence>. Do NOT use for <neighbouring agent's job>.
tools: <minimal set>
model: <sonnet|opus|haiku|inherit>
---
<Role in 1–2 sentences.>
## Process   (numbered, specific to the user's stack and the evidence)
## Rules     (what it must never do)
## Input (brief must contain) / Output (artifact path + format)
## Handoff block (same format as the rest of the squad)
```

For edits to existing agents, give the exact replacement text or a unified diff in the report.

## 6. Self-critique before concluding

Go through every proposal and answer these questions:
- Is the evidence ≥2 independent examples, verified with `--show`, or is it one noisy heuristic hit?
- Would a description fix, a checklist line, a command or a `CLAUDE.md` / `LESSONS.md` entry solve it without a new agent?
- Does it overlap an existing agent? If so, merge it instead of adding one.
- Is the saving bigger than the added coordination cost: routing ambiguity, always-on tokens, maintenance?

Remove or downgrade anything that fails, and list it in the appendix with the reason.
