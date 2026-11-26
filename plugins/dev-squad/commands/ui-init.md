---
description: Build or refresh `.squad/ui/DESIGN.md` — the UI contract (stack, tokens, components, routes, patterns) every UI change follows
argument-hint: [app directory in a monorepo, e.g. apps/web] [refresh]
---

Build or refresh the UI contract for this repository with the `ui-context` skill. Arguments: $ARGUMENTS

1. Run the skill's scanner, read-only:
   `python3 <ui-context skill>/scripts/scan_ui.py --md .squad/ui/DESIGN.md --json .squad/ui/inventory.json`
   Add `--app <dir>` if one was given, or if the scanner lists several apps. In that case ask the user which app.
2. If DESIGN.md already exists, write the new draft to `.squad/ui/DESIGN.draft.md` instead. Show the user the differences, such as new or removed tokens and components, and merge only what they confirm. Never overwrite curated sections.
3. Curate the TODO sections from real code, following the skill: patterns, do/don't, and aesthetic direction (only for new products). Mark anything inferred from a single example as `ASSUMPTION:`.
4. Show the user a short summary of what the squad will now follow:
   - stack,
   - token count,
   - number of components to reuse,
   - routes,
   - key patterns and rules.

Do not commit unless the user asks. DESIGN.md is meant to be committed; `inventory.json` and screenshots are not.

End your final summary with `User actions`: what the user must decide or do now, or "none" (see the `squad-playbook` skill).
