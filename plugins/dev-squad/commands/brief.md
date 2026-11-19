---
description: Summarise the current work for a manager or stakeholder — technical but busy — in one consistent, evidence-based format
argument-hint: [audience or focus, e.g. "for my manager", "status of ABC-123", "incident yesterday"] [language]
---

Write a brief of the work in this conversation for: $ARGUMENTS

If no audience is given, write for a manager who understands programming but has no time to read code. Write in the user's language (default Vietnamese).

Run this in the main session: it relies on what has been discussed and done in this conversation, which a sub-agent cannot see.

1. **Collect facts** from this conversation and from the repository (read-only):
   - the problem or goal, and the decisions taken,
   - what was changed: `git log --oneline` / `git diff --stat` for the relevant range,
   - verification evidence: test output, measurements, review verdicts,
   - `.squad/` artifacts: reports, `TASKS.md`, incidents, `LESSONS.md`.

   Use only facts you can point to. Mark anything uncertain `chưa xác nhận` (unconfirmed); never invent numbers, dates or outcomes.
2. **Write the brief** in exactly this structure, aiming for ≤ 250 words:

   ```markdown
   # <Topic> — <status: Xong / Đang làm / Bị chặn>  (<date>)

   **Tóm tắt:** <2–3 sentences: what it is, where it stands, what it means for the team/customer>

   **Vấn đề / bối cảnh:** <1–3 bullets: why this matters, impact in user or business terms>

   **Đã làm:** <2–5 bullets: outcomes, not code; name components only when useful>

   **Kết quả & bằng chứng:** <numbers before/after, tests passing, review verdict, MR link — each with its source>

   **Rủi ro / ảnh hưởng:** <what could still go wrong, who is affected, mitigation — or "Không có rủi ro đáng kể">

   **Cần quyết định / hỗ trợ:** <decisions, approvals or help needed from the reader, with a deadline — or "Không">

   **Bước tiếp theo:** <next steps with owner and expected date>
   ```

   - No code blocks or stack traces in the brief. At most one short identifier per bullet.
   - Never include secrets, tokens, connection strings, customer personal data, or internal hostnames and IPs. Refer to them generically ("the payment DB", "a customer account").
   - Explain any jargon the reader may not know in a few words.
   - Lead with impact and decisions; leave implementation detail for the reader to ask about.
3. **Show** the brief. Offer to save it to `.squad/reports/<YYYY-MM-DD>-brief-<slug>.md`, and to shorten it to a 3-line chat version.

End with `User actions`: anything the user must confirm before sending, such as unconfirmed facts or numbers. Always include "confirm there is no sensitive data before sending".
