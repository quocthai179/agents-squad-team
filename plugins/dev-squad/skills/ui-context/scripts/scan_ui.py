#!/usr/bin/env python3
"""scan_ui — inventory a frontend codebase and draft `.squad/ui/DESIGN.md` (stdlib only, read-only).

Finds what UI work must stay consistent with:
  - framework, styling approach, component library, icon set, form/i18n/chart libraries, test and Storybook setup
  - design tokens: CSS custom properties in :root / .dark / Tailwind v4 @theme blocks, Tailwind config theme keys,
    fonts loaded with next/font
  - existing components (the "use these first" list) and routes/pages (inputs for ui_check.mjs)

The output is a DRAFT: sections that need judgement (patterns, do/don't, aesthetic direction) are left as TODO
for the agent or the user to fill in from the code.

Examples:
  python scan_ui.py                          # current repo
  python scan_ui.py --root ../web --app apps/dashboard --md .squad/ui/DESIGN.md --json .squad/ui/inventory.json
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict

SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "out", ".turbo", ".nuxt", ".svelte-kit", "coverage",
             ".squad", "storybook-static", ".vercel", "target", ".angular"}

FRAMEWORKS = OrderedDict([("next", "Next.js"), ("nuxt", "Nuxt"), ("@sveltejs/kit", "SvelteKit"), ("@remix-run/react", "Remix"),
                          ("astro", "Astro"), ("@angular/core", "Angular"), ("vue", "Vue"), ("svelte", "Svelte"),
                          ("solid-js", "Solid"), ("react", "React")])
COMPONENT_LIBS = OrderedDict([("@mui/material", "MUI"), ("antd", "Ant Design"), ("@chakra-ui/react", "Chakra UI"),
                              ("@mantine/core", "Mantine"), ("primereact", "PrimeReact"), ("primevue", "PrimeVue"),
                              ("primeng", "PrimeNG"), ("vuetify", "Vuetify"), ("@angular/material", "Angular Material"),
                              ("element-plus", "Element Plus"), ("@headlessui/react", "Headless UI"),
                              ("react-bootstrap", "React Bootstrap"), ("bootstrap", "Bootstrap"),
                              ("@fluentui/react-components", "Fluent UI"), ("@carbon/react", "Carbon"),
                              ("@nextui-org/react", "NextUI"), ("daisyui", "daisyUI")])
STYLING = OrderedDict([("tailwindcss", "Tailwind CSS"), ("styled-components", "styled-components"),
                       ("@emotion/react", "Emotion"), ("sass", "Sass"), ("@vanilla-extract/css", "vanilla-extract"),
                       ("@stitches/react", "Stitches"), ("class-variance-authority", "cva variants"),
                       ("tailwind-merge", "tailwind-merge")])
ICONS = OrderedDict([("lucide-react", "Lucide"), ("lucide-vue-next", "Lucide"), ("@heroicons/react", "Heroicons"),
                     ("@tabler/icons-react", "Tabler"), ("react-icons", "react-icons"), ("@mui/icons-material", "MUI icons"),
                     ("@fortawesome/fontawesome-svg-core", "Font Awesome"), ("@iconify/react", "Iconify"),
                     ("@radix-ui/react-icons", "Radix icons"), ("primeicons", "PrimeIcons")])
OTHER = OrderedDict([("react-hook-form", "react-hook-form"), ("zod", "zod"), ("formik", "Formik"), ("next-intl", "next-intl"),
                     ("react-i18next", "react-i18next"), ("vue-i18n", "vue-i18n"), ("@ngx-translate/core", "ngx-translate"),
                     ("recharts", "Recharts"), ("chart.js", "Chart.js"), ("echarts", "ECharts"), ("@tanstack/react-table", "TanStack Table"),
                     ("@tanstack/react-query", "TanStack Query"), ("next-themes", "next-themes"), ("framer-motion", "Framer Motion"),
                     ("motion", "Motion"), ("sonner", "sonner (toasts)")])
TESTING = OrderedDict([("@playwright/test", "Playwright Test"), ("playwright", "Playwright"), ("cypress", "Cypress"),
                       ("@testing-library/react", "Testing Library"), ("vitest", "Vitest"), ("jest", "Jest"),
                       ("axe-core", "axe-core"), ("@axe-core/playwright", "@axe-core/playwright"),
                       ("@storybook/react", "Storybook"), ("@storybook/vue3", "Storybook"), ("@storybook/angular", "Storybook"),
                       ("chromatic", "Chromatic")])
COMPONENT_DIRS = ["components/ui", "src/components/ui", "components", "src/components", "app/components",
                  "src/app/components", "src/lib/components", "lib/components", "src/shared/components", "src/app/shared"]
COMPONENT_EXT = (".tsx", ".jsx", ".vue", ".svelte", ".ts")
CSS_EXT = (".css", ".scss", ".sass", ".less", ".pcss")
CSS_VAR = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);")
BLOCK = re.compile(r"(:root|\.dark|\[data-theme[^\]]*\]|html\.dark|@theme(?:\s+inline)?)\s*\{([^{}]*)\}", re.S)
NEXT_FONT = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]next/font/(google|local)['\"]")


def walk(root, max_depth=6):
    root_depth = root.rstrip(os.sep).count(os.sep)
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".") or x == ".storybook"]
        if d.count(os.sep) - root_depth >= max_depth:
            dirs[:] = []
        yield d, files


def read(path, limit=400_000):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def load_pkg(app):
    p = os.path.join(app, "package.json")
    try:
        with open(p, encoding="utf-8") as fh:
            pkg = json.load(fh)
    except (OSError, ValueError):
        return None
    deps = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(pkg.get(k) or {})
    return {"name": pkg.get("name"), "scripts": pkg.get("scripts") or {}, "deps": deps}


def frontend_candidates(root):
    found = []
    for d, files in walk(root, max_depth=4):
        if "package.json" in files:
            pkg = load_pkg(d)
            if pkg and any(k in pkg["deps"] for k in FRAMEWORKS):
                found.append(os.path.relpath(d, root))
        if "angular.json" in files and os.path.relpath(d, root) not in found:
            found.append(os.path.relpath(d, root))
    return sorted(found)


def pick(deps, table):
    out = []
    for key, label in table.items():
        hit = key in deps or (key.endswith("/") and any(d.startswith(key) for d in deps))
        if hit and label not in out:
            out.append(f"{label} ({deps.get(key, '')})" if deps.get(key) else label)
    return out


def scan(app, root):
    pkg = load_pkg(app) or {"name": None, "scripts": {}, "deps": {}}
    deps = pkg["deps"]
    inv = OrderedDict()
    inv["app"] = os.path.relpath(app, root)
    inv["package"] = pkg["name"]
    inv["framework"] = pick(deps, FRAMEWORKS)[:2] or (["Angular"] if os.path.exists(os.path.join(app, "angular.json")) else [])
    inv["styling"] = pick(deps, STYLING)
    libs = pick(deps, COMPONENT_LIBS)
    radix = sorted(d for d in deps if d.startswith("@radix-ui/react-") and d != "@radix-ui/react-icons")
    shadcn = os.path.exists(os.path.join(app, "components.json"))
    if shadcn:
        libs.insert(0, "shadcn/ui (components.json)")
    if radix:
        libs.append(f"Radix primitives ({len(radix)})")
    inv["component_library"] = libs
    inv["icons"] = pick(deps, ICONS)
    inv["other_ui_libs"] = pick(deps, OTHER)
    inv["testing"] = pick(deps, TESTING)
    inv["storybook"] = os.path.isdir(os.path.join(app, ".storybook"))
    inv["scripts"] = {k: v for k, v in pkg["scripts"].items()
                      if k in ("dev", "start", "build", "lint", "test", "test:e2e", "e2e", "storybook", "typecheck")}

    shadcn_cfg = {}
    if shadcn:
        try:
            shadcn_cfg = json.loads(read(os.path.join(app, "components.json")))
        except ValueError:
            pass
    inv["shadcn"] = {k: shadcn_cfg.get(k) for k in ("style", "aliases", "tailwind", "iconLibrary") if k in shadcn_cfg}

    tokens, token_files = OrderedDict(), []
    tw_configs, fonts, dark = [], [], []
    components, routes = [], []
    for d, files in walk(app):
        rel_d = os.path.relpath(d, app)
        for f in files:
            p = os.path.join(d, f)
            rel = os.path.normpath(os.path.join(rel_d, f))
            if f.endswith(CSS_EXT):
                text = read(p)
                blocks = BLOCK.findall(text)
                if blocks:
                    token_files.append(rel)
                for selector, body in blocks:
                    scope = "dark" if "dark" in selector or "theme=" in selector else ("@theme" if selector.startswith("@theme") else "root")
                    for name, value in CSS_VAR.findall(body):
                        tokens.setdefault(name, {})[scope] = " ".join(value.split())[:80]
            elif re.match(r"tailwind\.config\.(js|cjs|mjs|ts)$", f):
                text = read(p)
                keys = sorted(set(re.findall(r"^\s{4,8}([A-Za-z][A-Za-z0-9]*)\s*:", text, re.M)) &
                              {"colors", "spacing", "fontFamily", "fontSize", "borderRadius", "boxShadow", "screens",
                               "extend", "animation", "keyframes", "container", "zIndex"})
                dm = re.search(r"darkMode\s*:\s*\[?\s*['\"]([a-z]+)['\"]", text)
                tw_configs.append({"file": rel, "theme_keys": keys, "darkMode": dm.group(1) if dm else None})
                if dm:
                    dark.append(f"tailwind darkMode: {dm.group(1)}")
            elif f.endswith((".tsx", ".jsx", ".ts", ".js")) and ("layout" in f or "_app" in f or "fonts" in f):
                for names, kind in NEXT_FONT.findall(read(p)):
                    for n in names.split(","):
                        n = n.strip().split(" as ")[0].strip()
                        if n:
                            fonts.append(f"{n} (next/font/{kind}, {rel})")
            # components: files under well-known component dirs
            norm = rel.replace(os.sep, "/")
            for cd in COMPONENT_DIRS:
                if norm.startswith(cd + "/") and f.endswith(COMPONENT_EXT) and not re.search(r"\.(test|spec|stories)\.", f) \
                        and not f.endswith(".d.ts") and f not in ("index.ts", "index.tsx"):
                    components.append(norm)
                    break
            # routes: Next app router, pages router, SvelteKit, Nuxt
            m = re.match(r"(?:src/)?app/(.*?)/?page\.(tsx|jsx|ts|js|mdx)$", norm) or re.match(r"(?:src/)?app/page\.(tsx|jsx|ts|js)$", norm)
            if m:
                seg = m.group(1) if m.lastindex and m.lastindex >= 2 else ""
                seg = "/".join(s for s in seg.split("/") if not (s.startswith("(") and s.endswith(")")))
                routes.append("/" + seg)
            m = re.match(r"(?:src/)?pages/(.+)\.(tsx|jsx|vue)$", norm)
            if m and not m.group(1).startswith(("_", "api/")):
                r = "/" + re.sub(r"(^|/)index$", "", m.group(1))
                routes.append(r or "/")
            m = re.match(r"src/routes/(.*?)/?\+page\.svelte$", norm)
            if m:
                routes.append("/" + m.group(1))
    if "next-themes" in deps:
        dark.append("next-themes (class on <html>)")
    if any(scope == "dark" for v in tokens.values() for scope in v):
        dark.append("CSS variables overridden for dark")

    inv["design_tokens"] = {"files": sorted(set(token_files)), "count": len(tokens),
                            "tokens": OrderedDict(list(tokens.items())[:120])}
    inv["tailwind_config"] = tw_configs
    inv["fonts"] = sorted(set(fonts))
    inv["dark_mode"] = sorted(set(dark))
    inv["components"] = sorted(set(components))
    inv["routes"] = sorted(set(routes), key=lambda r: (r.count("/"), r))
    return inv


def to_markdown(inv):
    def bullet(items, empty="_none detected_"):
        return "\n".join(f"- {x}" for x in items) if items else empty

    t = inv["design_tokens"]
    token_rows = "\n".join(
        f"| `{name}` | {v.get('root', v.get('@theme', ''))} | {v.get('dark', '')} |" for name, v in t["tokens"].items())
    comps = inv["components"]
    shown = comps[:150]
    comp_list = "\n".join(f"- `{c}`" for c in shown) + (f"\n- … {len(comps) - len(shown)} more" if len(comps) > len(shown) else "")
    return f"""# DESIGN.md — UI contract for `{inv['app']}`

_Generated by `scan_ui.py`, then curated. Every UI change reads this first. When the code and this file disagree, fix one of them._

## Stack
- Framework: {', '.join(inv['framework']) or '_unknown_'}
- Styling: {', '.join(inv['styling']) or '_plain CSS / unknown_'}
- Component library: {', '.join(inv['component_library']) or '_none: custom components_'}
- Icons: {', '.join(inv['icons']) or '_none detected_'}
- Other UI libraries: {', '.join(inv['other_ui_libs']) or '_none_'}
- Tests: {', '.join(inv['testing']) or '_none detected_'} · Storybook: {'yes' if inv['storybook'] else 'no'}
- Scripts: {', '.join(f'`{k}`: `{v}`' for k, v in inv['scripts'].items()) or '_none_'}
{('- shadcn config: `' + json.dumps(inv['shadcn']) + '`') if inv['shadcn'] else ''}

## Design tokens (use these; never hard-code colors, spacing or radii)
Source files: {', '.join(f'`{f}`' for f in t['files']) or '_none found_'} · {t['count']} custom properties.

| Token | Light / default | Dark |
|---|---|---|
{token_rows or '| _none found_ | | |'}

Tailwind config: {'; '.join(f"`{c['file']}` keys {c['theme_keys']} darkMode={c['darkMode']}" for c in inv['tailwind_config']) or '_none_'}

## Typography
{bullet(inv['fonts'], '_no next/font imports found: check global CSS for font-family_')}

## Dark mode
{bullet(inv['dark_mode'], '_no dark mode detected_')}

## Existing components: reuse before creating
{comp_list or '_none found in the usual component folders_'}

## Routes (inputs for `ui_check.mjs --routes`)
{bullet([f'`{r}`' for r in inv['routes'][:60]], '_none detected_')}

## Patterns (TODO: fill in from the code)
- Layout shell and page structure:
- Forms (validation, error display, submit/loading state):
- Data display (tables, lists, empty / loading / error states):
- Feedback (toasts, dialogs, inline errors):
- Spacing scale and density:

## Do / Don't (TODO)
- Do: use tokens and existing components; follow the patterns above.
- Don't: introduce a new UI library, icon set, font or color without an ADR.

## Accessibility baseline
WCAG 2.2 AA: text contrast ≥ 4.5:1 (3:1 for large text and UI parts), every interactive element keyboard-reachable
with a visible focus ring, labels on inputs, alt text on meaningful images, no horizontal overflow at 375 px.

## Aesthetic direction (TODO: only for new products or a deliberate redesign)
Purpose, audience, tone and references. Existing products: consistency wins over novelty.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="repository root (default .)")
    ap.add_argument("--app", help="frontend app directory relative to --root (monorepos)")
    ap.add_argument("--md", help="write the DESIGN.md draft here (default: print)")
    ap.add_argument("--json", help="write the inventory JSON here")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if args.app:
        app = os.path.join(root, args.app)
    else:
        cands = frontend_candidates(root)
        if "." in cands or not cands:
            app = root
        elif len(cands) == 1:
            app = os.path.join(root, cands[0])
        else:
            sys.exit("Several frontend apps found; pick one with --app:\n  " + "\n  ".join(cands))
    if not os.path.isdir(app):
        sys.exit(f"No such app directory: {app}")
    inv = scan(app, root)
    md = to_markdown(inv)
    for path, content in ((args.md, md), (args.json, json.dumps(inv, indent=1))):
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            print(f"wrote {path}")
    if not args.md:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
