# Optional UI integrations (MCP servers and services)

None of these are required. The squad's default is `ui_check.mjs` plus the project's Playwright tests, which cost no always-on context. Each MCP server adds tool schemas to every session, and browser accessibility trees are large. Microsoft itself recommends the Playwright CLI with skills, rather than the MCP server, for coding agents. Add a server only for the job it is best at.

Commands change between versions: **check the vendor's current docs before configuring.** Never commit tokens. Personal servers go in user scope, shared ones in the project's `.mcp.json`.

| Integration | Best for | Typical setup | Notes |
|---|---|---|---|
| **Playwright MCP** | Interactive flows: click, type, multi-step forms, reproducing a reported UI bug | `claude mcp add playwright -- npx @playwright/mcp@<version>` (pin an exact version, e.g. `0.0.86`; `@latest` runs whatever was published last at every start) | Prefer `browser_snapshot` (text) over screenshots; one specific task per check |
| **Chrome DevTools MCP** | Performance traces, Lighthouse, network/console, CPU/network throttling, memory/heap | `claude mcp add chrome-devtools -- npx chrome-devtools-mcp@<version>` (pin, e.g. `1.13.0`), or its Claude Code plugin | Chromium only; stable 1.0 since 2026-05 |
| **Figma MCP (Dev Mode)** | Design-to-code: read frames, variables and tokens; **Code Connect** maps Figma components to your code components | Remote server `https://mcp.figma.com/mcp`, or the desktop app's local Dev Mode server | Needs a paid plan with a Dev Mode seat; check beta status. Map tokens and components first, or output drifts from your design system |
| **Storybook MCP** | Lets agents read your components, props and stories before writing UI | See storybook.js.org/ai | Most useful when Storybook is the source of truth for components |
| **Chromatic / Argos** | Hosted visual diffs with review UI across browsers | Their CLI in CI | Paid above free tiers; pixel diffs need deterministic pages |
| **Anthropic `frontend-design` skill** | New products: distinctive aesthetic direction, avoiding generic "AI look" | Install from Anthropic's official plugin marketplace (claude.com/marketplace/plugins/frontend-design), or use the copy in `anthropics/skills` | `ui-engineer` already carries its core rules for greenfield work. Don't use it to restyle an existing product |

`/dev-squad:ui-setup` checks which of these are present and suggests (never applies) the missing configuration.
