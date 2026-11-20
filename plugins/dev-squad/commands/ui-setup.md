---
description: Check what this machine/repo has for UI verification (Playwright, Chromium, axe-core, Storybook, MCP servers) and suggest — never apply — what is missing
argument-hint: [focus, e.g. "figma", "devtools", "ci"]
---

Check the UI tooling for this repository and machine. Focus: $ARGUMENTS

1. **Detect.** Install nothing. Some checks run project code (the project's Playwright) or may start configured MCP servers, so say which ones you ran:
   - Node and npm: `node --version`.
   - Playwright and axe-core in the project: `npm ls playwright @playwright/test axe-core @axe-core/playwright --depth=0`. Also check globally: `npm ls -g playwright --depth=0`.
   - Chromium launches: `node -e "import('playwright').then(p => p.chromium.launch()).then(b => b.close()).then(() => console.log('chromium ok'))"`. Run it from the project root, so the project's Playwright is used.
   - Storybook: does `.storybook/` exist?
   - Existing visual or a11y tests: grep for `toHaveScreenshot`, `AxeBuilder` and `axe-core` under the test folders.
   - MCP servers: `claude mcp list`, if available, plus any `.mcp.json`. Look for playwright, chrome-devtools, figma and storybook.
   - Whether `.squad/ui/DESIGN.md` exists.
2. **Report** a table of `capability | status | what it enables | how to add`. Use the `visual-verify` skill's `references/integrations.md` and `references/ci-visual.md` for the "how to add" column.
3. **Recommend the minimum.**
   - Baseline: `playwright` + `axe-core` as dev dependencies, plus Chromium. That is enough for `ui_check.mjs`.
   - DESIGN.md, if it is missing.
   - Screenshot and axe tests in CI, if the project has e2e tests.
   - MCP servers only for a concrete need: interactive flows, performance traces, Figma design-to-code or Storybook context. Each one adds always-on context.
4. **Change nothing.** Don't install packages, add MCP servers or edit config files unless the user confirms each step.

End your final summary with `User actions`: what the user must decide or do now, or "none" (see the `squad-playbook` skill).
