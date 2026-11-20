---
name: ui-context
description: Build or refresh the project's UI contract, `.squad/ui/DESIGN.md`: stack, component library, design tokens, fonts, dark mode, existing components and routes, plus the patterns and do/don'ts every UI change must follow. Use before any UI work in a repo that has no DESIGN.md yet, when the design system changed, or when asked to "document the design system / UI conventions".
---

# UI context: narrow the choice space before writing UI

AI-generated UI looks generic or inconsistent mainly because the model picks from everything it has ever seen. Tools that produce polished UI (v0, Lovable) do the opposite: they lock the stack, the component library and the tokens, and only write custom code when nothing existing fits. This skill gives every squad agent that same constraint for **your** project. The constraint is a file, `.squad/ui/DESIGN.md`.

## Build it

1. Run the scanner from the repo root. It is read-only. Its base directory is shown when this skill loads.

   ```bash
   python3 <skill>/scripts/scan_ui.py --md .squad/ui/DESIGN.md --json .squad/ui/inventory.json
   # monorepo: add --app apps/web (the script lists candidates when there are several)
   ```

   It detects:
   - framework, styling, component library (shadcn `components.json`, MUI, Ant Design, PrimeNG, Angular Material, …), icons, and form/i18n/chart libraries;
   - design tokens: CSS custom properties in `:root`, `.dark` and Tailwind v4 `@theme`, plus Tailwind config keys;
   - `next/font` fonts and dark-mode mechanisms;
   - existing components, and routes (Next app/pages router, SvelteKit).
2. **Curate** the TODO sections by reading real code. Do not invent conventions.
   - **Patterns**: open 2–3 representative pages and components and write down how the project builds:
     - the layout shell,
     - forms: validation, error display, submit/loading state,
     - data display: tables and lists with empty / loading / error states,
     - feedback: toasts, dialogs, inline errors,
     - the spacing and density it actually uses.
   - **Do / Don't**: rules that follow from the code, e.g. "buttons come from `components/ui/button.tsx` with `variant`, never raw `<button className=…>`" or "colors only through tokens".
   - **Aesthetic direction**: fill this in only for a new product or an agreed redesign. Otherwise write "match the existing product".
3. Ask the user to confirm anything you inferred from a single example (`ASSUMPTION:`).

`.squad/ui/DESIGN.md` is meant to be committed. `inventory.json` can be regenerated at any time.

## Use it

- **Read it before any UI change.** Reuse an existing component before creating one. Use tokens, never hard-coded colors, spacing, radii or fonts. Follow the listed patterns.
- When a change genuinely needs something new (a component, token, pattern or library), add it the project's way, update DESIGN.md in the same change, and name it in the report so reviewers see it.
- When code and DESIGN.md disagree, flag it. Do not silently follow either one.
- Re-run the scanner after design-system changes and diff the result against DESIGN.md.
