---
name: visual-verify
description: Look at a running UI in a real browser and collect evidence — screenshots at mobile/tablet/desktop in light/dark, ARIA snapshots, console and network errors, horizontal overflow and axe-core accessibility violations — with `ui_check.mjs`. Use before calling any UI change done, when reviewing a UI change, or to reproduce a visual bug. A UI change is never "done" without this evidence.
---

# Visual verify: give the agent eyes

Tests and type checks pass on UI that is visibly broken. A screen can overflow on mobile, be unreadable in dark mode, or have buttons with no accessible name, and the checks will still be green. Teams that get good UI from agents close the loop the way a human would: they look at the page. The default tool is the accessibility (ARIA) snapshot, which is a few KB. Screenshots are checkpoints, at 1–2 MB each.

The checker lives in this skill's `scripts/` directory; its base directory is shown when the skill loads.

## 1. Get a running app

- If the user gave a URL (a preview deployment or a running dev server), use it.
- Otherwise start the dev server **detached**, logging to a file, then let the checker wait for it. Do not write your own wait loop.

  ```bash
  mkdir -p .squad/tmp && { [ -f .squad/tmp/.gitignore ] || printf '*\n' > .squad/tmp/.gitignore; }
  nohup npm run dev -- --port 3100 > .squad/tmp/dev-server.log 2>&1 &
  echo $! > .squad/tmp/dev-server.pid
  ```

  Use the project's own dev command and port, taken from `package.json` scripts or `.squad/ui/DESIGN.md`. The checker's `--wait-server` waits until the URL answers.
- When you are finished, stop it: `kill "$(cat .squad/tmp/dev-server.pid)"`.
- Never point the checker at production unless the user explicitly asks.

## 2. Run the checker

```bash
node <skill>/scripts/ui_check.mjs --base-url http://localhost:3100 --routes /,/settings \
  --themes light,dark --out .squad/ui/shots/<slug> --fail-on serious --fail-on-console
```

- **Defaults:**
  - viewports `375x812,768x1024,1440x900`,
  - theme `light`; switching to dark uses `prefers-color-scheme`, or `--dark-mode class` to set `<html class="dark">`,
  - reduced motion,
  - axe tags WCAG 2.0/2.1/2.2 A and AA plus best-practice.
- **Pages behind a login:** `--storage-state <file>` (a Playwright storage state) or `--header "Authorization: …"`. Header values are never written to reports.
- **Exit codes:**
  - 0 = pass,
  - 1 = a `--fail-on` condition was met (axe level, console errors, overflow),
  - 2 = setup problem (no Playwright or Chromium, or the server never answered).
- **Dependencies:** `playwright` (or `@playwright/test`) and `axe-core`, resolved from the project and then the global npm root. If they are missing, the checker says so. **Ask the user before installing anything** (`npm i -D playwright axe-core && npx playwright install chromium`).

Outputs land in `--out`: one `<route>__<viewport>__<theme>.png` and `.aria.yml` per combination, plus `report.md` and `report.json`. Add `.squad/ui/shots/` to `.gitignore`. Screenshots can contain data.

## 3. Read the evidence

1. Read `report.md` first, then **look at** the screenshots that matter: the changed screens at 375px and in dark mode. A green report does not mean the page looks right.
2. Use the `.aria.yml` snapshot to check headings, landmarks, labels and focus order without spending context on images.
3. Treat these as defects:
   - axe **critical/serious** (contrast, missing names or labels, alt text),
   - console or page errors,
   - failed requests,
   - horizontal overflow at any viewport (the report names the culprit elements),
   - broken layout, clipped text or wrong states visible in the screenshots.
4. For a specific suspicion, inspect that route and viewport only, e.g. "does the table overflow at 375px?". Re-running everything for a vague "check the UI" wastes time.

## 4. Report it

- Cite the evidence: `report.md` path, screenshot paths, and violation ids with their targets.
- "Looks fine" needs a screenshot path. "Accessible" needs the axe result.
- If you could not run the checker (no app, no browser, no permission), say **"not visually verified"** and why. Never imply you looked.

## Optional deeper tools

Use these when they are installed and the user wants them:
- **Playwright MCP**: interactive clicking and typing flows.
- **Chrome DevTools MCP**: performance traces, Lighthouse, network and memory.
- **Storybook test-runner**: component-level checks.
- **Chromatic or Argos**: hosted visual diffs.

See `references/integrations.md`. CI templates for screenshot baselines and a11y gating are in `references/ci-visual.md`.
