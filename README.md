# Agents Squad Team 🧑‍💻🤖

Bộ plugin **Claude Code** cung cấp một "đội dev" gồm **12 agent chuyên biệt** (1 trưởng nhóm điều phối + 11 chuyên gia) và **8 lệnh workflow** giúp bạn đi trọn vòng đời phát triển phần mềm: phân tích yêu cầu → thiết kế → chia task → code → test → review → bảo mật → performance → tài liệu → release.

## Đội hình

| Agent | Vai trò | Khi nào dùng | Quyền |
|---|---|---|---|
| 🟣 `orchestrator` | Tech lead / điều phối | Yêu cầu nhiều bước, mơ hồ, cần nhiều vai trò phối hợp | Toàn quyền (kế thừa) |
| 🩵 `business-analyst` | BA | Làm rõ yêu cầu, user story, acceptance criteria (Given/When/Then) | Đọc + viết tài liệu |
| 🟡 `project-manager` | PM / Scrum master | Chia task, ước lượng, dependency, `TASKS.md`, standup, rủi ro | Đọc + viết tài liệu + git read-only |
| 🔵 `architect` | Kiến trúc sư | Thiết kế module/API/data model, ADR, so sánh công nghệ | Đọc + viết tài liệu thiết kế |
| 🟢 `developer` | Senior full-stack dev | Implement feature, refactor, fix bug, viết unit test | Đọc/ghi code + chạy lệnh |
| 🟠 `qa-engineer` | QA / test automation | Test plan, viết & chạy unit/integration/e2e test, báo cáo bug | Đọc/ghi test + chạy lệnh |
| 🔴 `code-reviewer` | Reviewer | Review diff trước khi merge (correctness, performance, test…) | **Chỉ đọc** |
| 🩷 `debugger` | Chuyên gia debug | Lỗi, stack trace, test fail, flaky, "chạy local được mà CI thì không" | Đọc/ghi code + chạy lệnh |
| 🩵 `devops-engineer` | DevOps | CI/CD, Docker, K8s, Terraform, checklist trước deploy | Đọc/ghi config + chạy lệnh |
| 🔴 `security-auditor` | Bảo mật | Audit OWASP/CWE, secrets, authz, dependency có lỗ hổng | **Chỉ đọc** |
| 🟡 `performance-engineer` | Chuyên gia performance | Query chậm, N+1, thiếu index, lock, connection pool; Kafka/RabbitMQ lag, ack/nack/commit sai, redelivery loop, rebalance; profiling CPU/memory | Đọc/ghi code + chạy lệnh (đo trước/sau) |
| 🔵 `tech-writer` | Technical writer | README, API docs, CHANGELOG, runbook, hướng dẫn | Đọc/ghi tài liệu |

Mỗi agent đều:
- tự đọc codebase và tuân theo convention có sẵn của dự án,
- trả lời bằng **ngôn ngữ bạn dùng** (tiếng Việt → tiếng Việt), còn code/identifier giữ tiếng Anh,
- lưu kết quả vào thư mục chung `.squad/` để agent sau đọc tiếp,
- kết thúc bằng khối **Handoff** (trạng thái, artifact, agent tiếp theo, rủi ro).

## Lệnh workflow (slash commands)

| Lệnh | Pipeline |
|---|---|
| `/dev-squad:squad <yêu cầu>` | Orchestrator tự phân tích, lập kế hoạch và giao việc cho agent phù hợp |
| `/dev-squad:feature <mô tả>` | BA → Architect → PM → Developer → QA (lặp tới khi PASS) → Reviewer ∥ Security → Tech writer |
| `/dev-squad:bugfix <lỗi>` | Debugger → (Developer) → QA regression test → Reviewer |
| `/dev-squad:review [target]` | Code reviewer ∥ Security auditor chạy song song, gộp báo cáo |
| `/dev-squad:sprint-plan <mục tiêu>` | BA → (Architect) → PM, tạo board `.squad/TASKS.md` |
| `/dev-squad:standup [khoảng thời gian]` | PM tổng hợp từ git log + task board |
| `/dev-squad:ship [version]` | DevOps ∥ Security ∥ QA → Tech writer → kết luận GO / NO-GO |
| `/dev-squad:perf <vấn đề>` | Performance engineer đo baseline & tìm bottleneck → Developer fix → QA ∥ đo lại trước/sau → Reviewer |

Ngoài ra skill `squad-playbook` giúp Claude tự biết nên gọi agent nào khi bạn nói kiểu *"dùng squad làm…"*.

## Cài đặt

### Cách 1 — qua marketplace (khuyến nghị)

Trong Claude Code:

```
/plugin marketplace add quocthai179/agents-squad-team
/plugin install dev-squad@agents-squad-team
```

Sau đó khởi động lại session (hoặc chạy `/reload-plugins` nếu bản Claude Code của bạn hỗ trợ).

### Cách 2 — chạy trực tiếp từ thư mục (dev / thử nghiệm)

```bash
git clone https://github.com/quocthai179/agents-squad-team.git
claude --plugin-dir ./agents-squad-team/plugins/dev-squad
```

### Cách 3 — bật cho cả team qua `.claude/settings.json` của repo

```json
{
  "extraKnownMarketplaces": {
    "agents-squad-team": {
      "source": { "source": "github", "repo": "quocthai179/agents-squad-team" }
    }
  },
  "enabledPlugins": {
    "dev-squad@agents-squad-team": true
  }
}
```

## Cách dùng

**Giao cả quy trình bằng lệnh:**

```
/dev-squad:feature Thêm chức năng đặt lại mật khẩu qua email, link hết hạn sau 30 phút
/dev-squad:bugfix  TypeError: Cannot read properties of undefined (reading 'id') ở OrderService.create
/dev-squad:review  origin/main...HEAD
/dev-squad:sprint-plan Xây module quản lý kho, capacity 30 points
/dev-squad:perf    Consumer topic order-events lag tăng liên tục, có log nack lặp lại cùng offset
/dev-squad:perf    API GET /orders p95 = 2s, target 300ms
```

**Gọi đích danh một agent:**

```
Dùng agent business-analyst viết user story cho tính năng xuất báo cáo PDF
@dev-squad:qa-engineer viết test cho src/services/payment.ts
```

**Dùng orchestrator làm agent chính của cả session** (khi đó nó có thể tự spawn các agent khác):

```bash
claude --agent dev-squad:orchestrator
```

> ℹ️ Trong Claude Code, subagent không thể tự gọi subagent khác. Vì vậy việc điều phối nhiều agent được thực hiện ở session chính — qua các lệnh `/dev-squad:*`, hoặc bằng cách chạy orchestrator làm agent chính như trên. Nếu orchestrator được gọi như một subagent, nó sẽ trả về kế hoạch + brief cho từng bước để session chính thực thi.

## Thư mục làm việc chung `.squad/`

Các agent trao đổi qua file để agent sau có đủ ngữ cảnh:

```
.squad/
├── requirements/<feature>.md        # business-analyst
├── design/<feature>.md              # architect
├── adr/0001-<quyet-dinh>.md         # architect
├── TASKS.md                         # project-manager (nguồn sự thật về task)
└── reports/<ngày>-<loại>-<slug>.md  # qa / review / security / debug / perf
```

Bạn có thể commit `.squad/` để lưu lịch sử planning cho cả team, hoặc thêm vào `.gitignore` nếu chỉ muốn dùng cá nhân.

## Tuỳ biến

- **Model**: mỗi agent khai báo `model` trong frontmatter (`architect`, `security-auditor`, `performance-engineer` dùng `opus`; `orchestrator` dùng `inherit`; còn lại `sonnet`). Đổi thành `opus`, `sonnet`, `haiku` hoặc `inherit` tuỳ ngân sách.
- **Quyền công cụ**: sửa trường `tools`. `code-reviewer` và `security-auditor` cố ý không có `Write`/`Edit` để đảm bảo chỉ đọc.
- **Thêm agent**: tạo file `plugins/dev-squad/agents/<ten>.md` theo mẫu có sẵn, thêm vào bảng trong `orchestrator.md` và `skills/squad-playbook/SKILL.md`.
- **Ghi đè cho 1 dự án**: copy file agent vào `.claude/agents/` của dự án rồi sửa — agent cấp project được ưu tiên hơn agent của plugin.

## Cấu trúc repo

```
agents-squad-team/
├── .claude-plugin/marketplace.json     # khai báo marketplace
├── .github/workflows/validate.yml      # CI: claude plugin validate --strict
└── plugins/dev-squad/
    ├── .claude-plugin/plugin.json      # manifest plugin
    ├── agents/                         # 12 agent
    ├── commands/                       # 8 lệnh workflow
    └── skills/squad-playbook/SKILL.md  # playbook điều phối
```

## Kiểm tra

```bash
claude plugin validate --strict .
claude plugin validate --strict plugins/dev-squad
claude --plugin-dir plugins/dev-squad plugin details dev-squad
```

## License

MIT
