# Agents Squad Team 🧑‍💻🤖

Bộ plugin **Claude Code** cung cấp một "đội dev" gồm **18 agent chuyên biệt** (1 trưởng nhóm điều phối + 17 chuyên gia) và **17 lệnh workflow** giúp bạn đi trọn vòng đời phát triển phần mềm: phân tích yêu cầu → thiết kế → chia task → code → test → review → bảo mật → performance → migration DB → release → xử lý sự cố → nâng cấp dependency, kèm agent tự audit chính bộ squad.

## Đội hình

| Agent | Vai trò | Khi nào dùng | Quyền |
|---|---|---|---|
| 🟣 `orchestrator` | Tech lead / điều phối | Yêu cầu nhiều bước, mơ hồ, cần nhiều vai trò phối hợp | Toàn quyền (kế thừa) |
| 🩵 `business-analyst` | BA | Làm rõ yêu cầu, user story, acceptance criteria (Given/When/Then) | Đọc + viết tài liệu |
| 🟡 `project-manager` | PM / Scrum master | Chia task, ước lượng, dependency, `TASKS.md`, standup, rủi ro | Đọc + viết tài liệu + git read-only |
| 🔵 `architect` | Kiến trúc sư | Thiết kế module/API/data model, ADR, so sánh công nghệ | Đọc + viết tài liệu thiết kế |
| 🟢 `developer` | Senior full-stack dev | Implement feature, refactor, fix bug, viết unit test; lập checklist yêu cầu trước khi code và đánh dấu ✅/❌/⏭ kèm bằng chứng | Đọc/ghi code + chạy lệnh |
| 🟠 `qa-engineer` | QA / test automation | Test plan, viết & chạy unit/integration/e2e test, báo cáo bug | Đọc/ghi test + chạy lệnh |
| 🔴 `code-reviewer` | Reviewer | Review diff trước khi merge (correctness, performance, test…) | **Chỉ đọc** |
| 🩷 `debugger` | Chuyên gia debug | Lỗi, stack trace, test fail, flaky, "chạy local được mà CI thì không" | Đọc/ghi code + chạy lệnh |
| 🩵 `devops-engineer` | DevOps | CI/CD, Docker, K8s, Terraform, checklist trước deploy | Đọc/ghi config + chạy lệnh |
| 🔴 `security-auditor` | Bảo mật | Audit OWASP/CWE, secrets, authz, dependency có lỗ hổng | **Chỉ đọc** |
| 🟡 `performance-engineer` | Chuyên gia performance | Query chậm, N+1, thiếu index, lock, connection pool; Kafka/RabbitMQ lag, ack/nack/commit sai, redelivery loop, rebalance; profiling CPU/memory; **tự tạo tool giả lập tải đột biến** (skill `load-simulation`) | Đọc/ghi code + chạy lệnh (đo trước/sau) |
| 🟢 `database-engineer` | Kỹ sư database | Thay đổi schema/dữ liệu không downtime (expand → migrate → contract), đánh giá lock trên bảng lớn, backfill theo batch, rollback, review migration (Flyway, Liquibase, Alembic, Prisma…) | Đọc/ghi migration + chạy lệnh (chỉ DB local) |
| 🔴 `sre-incident-responder` | SRE / xử lý sự cố | Production sập hoặc chậm: đánh giá mức độ, tìm thay đổi gây lỗi, đề xuất cách giảm thiểu, timeline, status update, postmortem; SLO, alert, runbook | Production chỉ đọc; mọi thay đổi phải được bạn duyệt |
| 🟠 `dependency-upgrader` | Nâng cấp dependency | Spring Boot 2→3, Java 17→21, Node, Python, React…; vá CVE; đọc migration guide, OpenRewrite/codemod, nâng từng bước có test | Đọc/ghi code + chạy lệnh |
| 🔵 `tech-writer` | Technical writer | README, API docs, CHANGELOG, runbook, hướng dẫn | Đọc/ghi tài liệu |
| 🩵 `squad-auditor` | Squad Auditor (EM + AI-workflow coach) | Audit chính bộ squad (dev-squad, lab) từ lịch sử làm việc thật: thiếu agent nào, agent nào yếu/thừa/chồng chéo, việc cần làm | Chỉ ghi vào `.squad/audit/`; không tự sửa squad |
| 🩷 `ui-engineer` | UI engineer | Viết UI (page, component, form, bảng, dialog, responsive, dark mode) **theo design system của dự án** (`.squad/ui/DESIGN.md`), đủ các trạng thái loading/empty/error, đạt a11y WCAG 2.2 AA, **tự kiểm chứng trên trình duyệt** (screenshot và axe) trước khi bàn giao | Đọc/ghi code + chạy lệnh + trình duyệt |
| 🟣 `design-reviewer` | Design reviewer | Review **UI đang chạy thật** theo DESIGN.md: tương tác, responsive, độ hoàn thiện thị giác, a11y, độ bền với các trạng thái, console. Lỗi phân loại Blocker/High/Medium/Nit, có screenshot làm bằng chứng. Là một phần của review gate khi diff đụng UI | **Chỉ đọc** + trình duyệt |

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
| `/dev-squad:review [URL MR/PR \| !iid \| branch \| range]` | Code reviewer ∥ Security auditor chạy song song, gộp báo cáo; nhận cả URL/số MR/PR; luôn ghi báo cáo gộp ra đường dẫn cố định (`.squad/reports/review-mr-<id>.md`); kết luận READY TO PUSH / NOT READY |
| `/dev-squad:commit-msg [ngữ cảnh]` | Soạn commit message từ diff đã stage theo đúng style của repo; lấy ticket ID từ tên branch và **cảnh báo nếu ticket không khớp** (cả với các commit chưa push); chỉ commit khi bạn xác nhận |
| `/dev-squad:brief [đối tượng]` | Tóm tắt cho quản lý (hiểu lập trình nhưng không đọc code) theo một format cố định ≤250 từ: tóm tắt, vấn đề, đã làm, kết quả có bằng chứng, rủi ro, cần quyết định, bước tiếp theo |
| `/dev-squad:ui <yêu cầu UI>` | `ui-init` nếu chưa có DESIGN.md → (BA) → **UI engineer** viết và kiểm chứng trên trình duyệt → **Design reviewer** ∥ Code reviewer → QA thêm test visual/a11y |
| `/dev-squad:ui-init [app]` | Quét repo frontend và sinh `.squad/ui/DESIGN.md`: stack, token, font, dark mode, component có sẵn, route, pattern, nên/không nên |
| `/dev-squad:ui-setup [trọng tâm]` | Kiểm tra máy và repo đang có gì (Playwright, Chromium, axe-core, Storybook, MCP) và gợi ý phần còn thiếu, **không tự cài** |
| `/dev-squad:sprint-plan <mục tiêu>` | BA → (Architect) → PM, tạo board `.squad/TASKS.md` |
| `/dev-squad:standup [khoảng thời gian]` | PM tổng hợp từ git log + task board |
| `/dev-squad:ship [version]` | DevOps ∥ Security ∥ QA ∥ DB engineer (review migration) → Tech writer → kết luận GO / NO-GO |
| `/dev-squad:db-change <thay đổi>` | DB engineer lập kế hoạch migration không downtime → bạn duyệt → DB engineer ∥ Developer → QA chạy migrate up/down → Reviewer ∥ DB engineer → ghi chú rollout |
| `/dev-squad:incident <sự cố>` | SRE đánh giá & đề xuất giảm thiểu → bạn duyệt → tìm nguyên nhân gốc (Debugger / Perf / DB / DevOps) → fix → postmortem → PM tạo action items |
| `/dev-squad:upgrade <mục tiêu>` | Upgrader kiểm kê & lập kế hoạch → bạn duyệt → nâng từng bước có test → QA ∥ Security ∥ Perf → Reviewer → CHANGELOG |
| `/dev-squad:audit [dev-squad\|lab\|both] [khoảng thời gian]` | Hỏi tối đa 3 câu → Squad Auditor đọc transcript, `.squad/`, `research/`, git, định nghĩa agent → báo cáo có dẫn nguồn + bản nháp agent mới → bạn chọn cái cần áp dụng |
| `/dev-squad:perf <vấn đề>` | Performance engineer đo baseline & tìm bottleneck → Developer fix → QA ∥ đo lại trước/sau → Reviewer |

Ngoài ra skill `squad-playbook` giúp Claude tự biết nên gọi agent nào khi bạn nói kiểu *"dùng squad làm…"*.

## Skill `load-simulation` — giả lập tải đột biến

Phần lớn sự cố performance không xảy ra lúc tải bình thường, mà xảy ra khi traffic **tăng đột ngột**: chạy campaign, cron job trùng giờ cao điểm, retry storm, consumer khởi động lại với backlog lớn, cache bị flush sau deploy… Skill này được nạp sẵn cho `performance-engineer` và `sre-incident-responder` (bạn cũng có thể gọi trực tiếp bằng `/dev-squad:load-simulation`). Nó giúp agent **tự dựng tool tái hiện sự cố** ngay trong dự án của bạn, tại `.squad/perf/<kịch-bản>/`, rồi đo lại trước/sau khi sửa.

| Tool | Giả lập | Cần cài |
|---|---|---|
| `db_burst.py` | Dồn query đột biến vào PostgreSQL/MySQL/SQLite: cạn connection pool, query chậm khi chạy đồng thời, lock trên hot row, transaction dài, connection storm; theo dõi `pg_stat_activity` theo từng giây | `psycopg[binary]` / `pymysql` |
| `http_burst.py` | Traffic HTTP tăng vọt, trộn nhiều endpoint theo trọng số, cache stampede, keep-alive hoặc connection storm | chỉ thư viện chuẩn |
| `kafka_burst.py` | `produce` burst (acks, batching, nén, sync và async, key lệch → hot partition, poison message); `consume` giả lập consumer chậm, nack/seek retry vô hạn, DLQ, các kiểu commit, vượt `max.poll.interval.ms`; `lag` theo dõi lag | `confluent-kafka` |
| `spike_http.js` | Template k6 cho spike HTTP hàng nghìn req/s | `k6` |
| `loadkit.py` | Engine dùng chung để tự viết tool mới (gRPC, Redis, MongoDB, RabbitMQ…) | chỉ thư viện chuẩn |

Đặc điểm chính:
- **Mô hình open-model**: request đến theo lịch như traffic thật. Latency được đo từ thời điểm *dự kiến gửi*, nên thời gian chờ pool/worker cũng được tính, tránh lỗi coordinated omission.
- **Hình dạng tải**: `spike`, `burst`, `ramp`, `step`, `constant`, hoặc tự định nghĩa qua `--profile "30s:10,1s:10->800,60s:800,30s:10"`.
- **Phân bố key lệch** `{{zipf:N:S}}` để mô phỏng hot key / hot row.
- **Báo cáo theo từng giai đoạn** baseline / spike / recovery (p50/p95/p99, service time, drop), kèm gợi ý chẩn đoán và file JSON.
- **An toàn mặc định**: từ chối host không phải local; DB chỉ đọc trừ khi có `--allow-write`; không lưu token vào báo cáo.
- Có catalog **18 kịch bản** sự cố hay gặp kèm lệnh tái hiện và cách sửa (`references/scenarios.md`).

Ví dụ:

```bash
# Query không có index: baseline 5 q/s, sau đó tăng vọt lên 600 q/s
python db_burst.py --dsn postgresql://app:app@localhost/app --pool 10 --observe \
  --query "SELECT * FROM orders WHERE customer_id = {{randint:1:50000}}" --shape spike --base 5 --peak 600

# Poison message + nack/seek retry → partition bị kẹt; so sánh với retry giới hạn + DLQ
python kafka_burst.py produce --topic perf-payments --profile "4s:2500" --poison-every 3000
python kafka_burst.py consume --topic perf-payments --group sim --on-error retry-seek --duration 30s
python kafka_burst.py consume --topic perf-payments --group sim2 --on-error dlq --max-retries 3
```

Kết quả kiểm thử thật trên PostgreSQL 16 (bảng 600k dòng, pool 10, spike 600 q/s):

| Giai đoạn | Trước khi thêm index (p95) | Sau khi thêm index (p95) |
|---|---|---|
| baseline 5 q/s | 23 ms | 4.1 ms |
| spike 600 q/s | 15 710 ms, 835 request bị drop | 1.2 ms, 0 drop |
| recovery 5 q/s | 15 317 ms (chưa hồi phục) | 5.2 ms |

## Mảng UI: design system, đôi mắt và review design

Ba kỹ thuật được các squad AI làm UI tốt dùng nhiều nhất, áp dụng cho squad này:

1. **Thu hẹp không gian lựa chọn** (giống cách v0 khoá shadcn/ui và token).
   - `/dev-squad:ui-init` (skill `ui-context`) quét repo rồi sinh `.squad/ui/DESIGN.md`: framework, thư viện component, design token (CSS variables, Tailwind v4 `@theme`, config Tailwind), font `next/font`, dark mode, **danh sách component có sẵn** và route.
   - Mọi việc UI phải đọc file này và **dùng lại component và token có sẵn trước khi viết mới**.
2. **Cho agent "đôi mắt"** (skill `visual-verify`, script `ui_check.mjs` dùng Playwright và axe-core). Với mỗi route × viewport (375/768/1440) × theme (light/dark), script:
   - chụp screenshot và ghi ARIA snapshot;
   - thu lỗi console/JS và request hỏng;
   - phát hiện **tràn ngang** và chỉ ra phần tử gây tràn;
   - chạy **axe-core WCAG 2.2 AA**;
   - xuất `report.md` và `report.json`, kèm exit code để dùng trong CI.

   Luật: **không báo UI xong khi chưa có bằng chứng screenshot**; nếu không chạy được thì phải ghi "not visually verified".
3. **Review design trên giao diện chạy thật.**
   - `design-reviewer` review theo nhiều phase và gắn bằng chứng cho từng lỗi.
   - `/dev-squad:review` tự gọi thêm reviewer này khi diff đụng file UI. **Lỗi Blocker/High của design là blocking** trong review gate.

Thêm vào đó:
- `qa-engineer` khoá kết quả bằng baseline `toHaveScreenshot` và `@axe-core/playwright`; `devops-engineer` có template CI (GitHub Actions và GitLab, dùng Playwright image).
- `ui-engineer` có **chế độ sản phẩm mới**: chọn hướng thẩm mỹ trước khi code, để tránh kiểu "AI slop" (font Inter, gradient tím). Sản phẩm có sẵn thì ưu tiên nhất quán.
- Các tích hợp tuỳ chọn (Playwright MCP, Chrome DevTools MCP, Figma Dev Mode MCP kèm Code Connect, Storybook MCP, Chromatic/Argos) được hướng dẫn trong `/dev-squad:ui-setup`. Chúng **không bật mặc định**, vì MCP tốn context.

```bash
# thử nhanh trên dự án của bạn (cần playwright + axe-core; hỏi trước khi cài)
python3 plugins/dev-squad/skills/ui-context/scripts/scan_ui.py --md .squad/ui/DESIGN.md
node plugins/dev-squad/skills/visual-verify/scripts/ui_check.mjs --base-url http://localhost:3000 --routes /,/settings --themes light,dark
```

## Agent `squad-auditor` — tự audit bộ squad

Agent này đóng vai engineering manager kiêm AI-workflow coach, audit chính bộ squad (dev-squad, lab) dựa trên **lịch sử làm việc thật**, không dựa trên cảm tính:

1. **Thu thập bằng chứng** theo thứ tự, ghi rõ nguồn nào đọc được và nguồn nào "không có dữ liệu":
   - transcript Claude Code (`~/.claude/projects/**/*.jsonl`, gồm cả transcript của subagent),
   - `.squad/` và `research/` (TASKS, reports, incidents, LESSONS, squad-issues, retro),
   - git log,
   - định nghĩa agent, skill và command đang có.
2. **Lập danh mục công việc** (work inventory), rồi tìm tín hiệu thiếu agent:
   - việc lặp lại ≥3 lần mà làm tay,
   - prompt dài viết lại từ đầu,
   - bị sửa output ngay sau khi agent chạy,
   - chỉ dẫn lặp lại qua nhiều session,
   - handoff phải copy-paste tay,
   - agent không bao giờ được gọi,
   - bước hay bị bỏ (test, review),
   - domain riêng như SNMP/MIB, Quarkus, OVNG.
3. **Đánh giá từng agent** (giữ / sửa prompt / sửa description / gộp / bỏ) và **đề xuất tối đa 5 agent mới**, mỗi agent phải có ≥2 ví dụ thật, kèm bản nháp file. Sau đó agent **tự phản biện** để loại các đề xuất làm squad phình to không cần thiết.
4. **Báo cáo** tại `.squad/audit/<ngày>/squad-audit.md`: TL;DR, kế hoạch hành động (quick win, tuần này, tháng này) và metric để đo lại sau 2–4 tuần.

Agent dùng skill `squad-audit`, trong đó có script `mine_transcripts.py`. Script chỉ dùng thư viện chuẩn và chạy local, tự che secret và email, và mọi phát hiện đều kèm nguồn `file:dòng`. Lệnh `--show=<ref>` cho xem ngữ cảnh để kiểm chứng trước khi trích dẫn.

```bash
python plugins/dev-squad/skills/squad-audit/scripts/mine_transcripts.py --days 30 --scope dev-squad --scope lab --md usage.md
```

> Agent chỉ đề xuất, không tự sửa agent/skill/command. Thư mục `evidence/` chứa trích đoạn hội thoại (đã che secret), nên thêm `.squad/audit/*/evidence/` vào `.gitignore`. Chat trên claude.ai không nằm trên máy nên được ghi là "không có dữ liệu", trừ khi bạn export ra.

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
/dev-squad:perf    Hệ thống chậm hẳn mỗi khi chạy flash sale, cần dựng tool giả lập spike để tái hiện
/dev-squad:db-change  Thêm cột tenant_id NOT NULL vào bảng orders (80 triệu dòng), không được downtime
/dev-squad:incident   Checkout trả 5xx từ 14:05 UTC, ngay sau khi deploy v2.3.1
/dev-squad:upgrade    Spring Boot 2.7 → 3.3 và Java 17 → 21
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
├── perf/<kịch-bản>/                 # performance-engineer: tool giả lập tải chạy lại được
├── tmp/                             # developer: script và log tạm (tự gitignore)
├── LESSONS.md                       # bài học chung: mọi agent đọc, agent có quyền ghi thì ghi thêm
├── ui/DESIGN.md                     # hợp đồng UI (commit); ui/shots/ và ui/inventory.json không commit
├── incidents/<ngày>-<slug>/         # sre-incident-responder: timeline, postmortem
├── audit/<ngày>/                    # squad-auditor: squad-audit.md, drafts/, evidence/
└── reports/<ngày>-<loại>-<slug>.md  # qa / review / security / debug / perf / upgrade
```

Bạn có thể commit `.squad/` để lưu lịch sử planning cho cả team, hoặc thêm vào `.gitignore` nếu chỉ muốn dùng cá nhân.

## Quy ước làm việc của squad

- **Review gate trước mọi lần push hoặc MR** (push branch, push tag, mở hay cập nhật MR/PR):
  1. Chạy `/dev-squad:review`.
  2. Sửa hết lỗi *blocking* (🔴 từ `code-reviewer`, Critical/High từ `security-auditor`, Blocker/High từ `design-reviewer` khi diff chạm UI), hoặc bạn xác nhận hoãn từng lỗi.
  3. `/review` luôn kết thúc bằng **READY TO PUSH** hoặc **NOT READY**. Chỉ push sau khi bạn xác nhận.

  Luật được định nghĩa một chỗ trong skill `squad-playbook`, các lệnh workflow trỏ về đó. Mọi agent có quyền Bash đều có luật **không bao giờ tự push**; chỉ session chính push, sau khi bạn xác nhận.
- **`developer`:**
  - Lập **checklist yêu cầu** (R/C/V) trước khi code, và báo cáo từng mục ✅/❌/⏭ kèm bằng chứng.
  - **Không bao giờ chờ bằng `sleep`, vòng lặp chờ hay Monitor.** Build và test chạy foreground với `timeout` rõ ràng (tối đa 10 phút); log ghi ra file, chỉ đọc phần lỗi. Lý do: kiểm thử thực tế cho thấy subagent không nhận được thông báo khi lệnh chạy nền kết thúc, nên phải chạy build lại hai lần.
  - Chỉ lệnh có thể chạy quá 10 phút mới chạy nền, rồi bàn giao kèm lệnh, đường dẫn log và trạng thái "chưa kiểm chứng". Session chính (nhận được thông báo) vẫn được chạy nền.
  - Script dài (>~15 dòng hoặc có quoting phức tạp) được ghi ra file trong `.squad/tmp/` rồi chạy theo đường dẫn.
  - `.squad/tmp/` được tạo kèm `.gitignore` trước mọi thứ khác. Script tạm không chứa secret; log được coi là nhạy cảm; trước mọi lệnh build image (`docker build`, `buildx`, `compose build`, `podman`…) phải kiểm tra `.dockerignore` đã loại `.squad/`.

- **Hợp đồng làm việc** (mọi agent và mọi lệnh):
  - Không bịa đặt. Thiếu thông tin quyết định kết quả thì **hỏi** (tối đa 3 câu, `Status: needs-input`); giả định nhỏ thì ghi `ASSUMPTION:`.
  - Handoff luôn có mục **`User actions`**, và tóm tắt cuối của mọi lệnh kết thúc bằng **"Việc bạn cần làm"**.
  - `Status:` chỉ nhận `done | blocked | needs-input`; verdict để trong báo cáo.
- **Bài học chung `.squad/LESSONS.md`:** mọi agent đọc trước khi làm, rồi ghi thêm root cause, quirk môi trường hay bẫy lặp lại. Mỗi bài học là một mục ngắn có bằng chứng, không chứa secret (định dạng xem trong skill `squad-playbook`).
- **Phạm vi agent rõ hơn:**
  - `code-reviewer` chỉ review diff.
  - `qa-engineer` chỉ viết test tự động trong code; test thủ công hay qua trình duyệt trên môi trường lab thì chuyển cho squad test UI riêng.
  - `orchestrator` chỉ chạy làm agent chính hoặc qua `/dev-squad:squad`.
  - `performance-engineer` nhận cả yêu cầu "test performance thực tế / tăng tải tới khi timeout".
  - `sre-incident-responder` nhận cả "pod restart / crash loop / OOMKilled" và **luôn ghi postmortem** vào `.squad/incidents/`.

## Tuỳ biến

- **Model**: mỗi agent khai báo `model` trong frontmatter (`architect`, `security-auditor`, `performance-engineer`, `database-engineer`, `sre-incident-responder` dùng `opus`; `orchestrator` dùng `inherit`; còn lại `sonnet`). Đổi thành `opus`, `sonnet`, `haiku` hoặc `inherit` tuỳ ngân sách.
- **Quyền công cụ**: sửa trường `tools`. `code-reviewer` và `security-auditor` cố ý không có `Write`/`Edit` để đảm bảo chỉ đọc.
- **Thêm agent**: tạo file `plugins/dev-squad/agents/<ten>.md` theo mẫu có sẵn, thêm vào bảng trong `orchestrator.md` và `skills/squad-playbook/SKILL.md`.
- **Ghi đè cho 1 dự án**: copy file agent vào `.claude/agents/` của dự án rồi sửa — agent cấp project được ưu tiên hơn agent của plugin.

## Cấu trúc repo

```
agents-squad-team/
├── .claude-plugin/marketplace.json     # khai báo marketplace
├── .github/workflows/validate.yml      # CI: validate plugin + unit test
├── tests/                             # unit test: giả lập tải, miner transcript, scan_ui, ui_check, lint prompt
├── plugins/dev-squad/evals/           # eval hành vi cho `claude plugin eval` (định tuyến UI, review design)
└── plugins/dev-squad/
    ├── .claude-plugin/plugin.json      # manifest plugin
    ├── agents/                         # 18 agent
    ├── commands/                       # 17 lệnh workflow
    └── skills/
        ├── squad-playbook/SKILL.md     # playbook điều phối
        ├── squad-audit/                # skill audit squad + scripts/mine_transcripts.py
        ├── ui-context/                 # skill DESIGN.md + scripts/scan_ui.py
        ├── visual-verify/              # skill kiểm chứng trên trình duyệt + scripts/ui_check.mjs + references/ (CI, tích hợp)
        └── load-simulation/            # skill giả lập tải đột biến
            ├── SKILL.md
            ├── references/scenarios.md # 18 kịch bản sự cố + cách tái hiện
            └── scripts/                # loadkit, db_burst, http_burst, kafka_burst, spike_http.js
```

## Kiểm tra

```bash
claude plugin validate --strict .
claude plugin validate --strict plugins/dev-squad
claude --plugin-dir plugins/dev-squad plugin details dev-squad
python3 -m unittest discover -s tests
```

Test `tests/test_ui_tools.py` chạy Chromium thật nếu máy có Playwright (kể cả test chống rò header đăng nhập sang origin khác); nếu không có thì tự bỏ qua phần trình duyệt. CI hiện không cài Chromium nên phần này chỉ chạy trên máy dev: hãy chạy bộ test trên máy có Playwright trước khi push thay đổi `ui_check.mjs`.

**Eval hành vi** (`plugins/dev-squad/evals/`, 5 case): kiểm tra squad giao việc UI cho `ui-engineer` + `design-reviewer`, gate có chặn finding design, không tự nhận "đã xác minh" khi chưa chạy trình duyệt, và **không** kéo agent UI vào việc backend/Kafka. Mỗi lần chạy tốn phí model (khoảng 0,6 USD cho 1 lượt × 5 case × 2 nhánh có/không plugin), nên không chạy trong CI:

```bash
cd plugins/dev-squad
claude plugin eval . --ablation with-without --judge-model sonnet --no-publish   # mặc định 3 lượt mỗi case
```

Chỉ số chính là Δ = điểm có plugin − điểm không có plugin. Kết quả nằm ở `evals/results/` (đã gitignore).

## License

MIT
