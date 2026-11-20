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
import unicodedata
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
# Values are bounded and stop at a newline so hostile CSS cannot make the scan quadratic; the last
# declaration of a block may omit its ";".
CSS_VAR = re.compile(r"(--[A-Za-z0-9_-]{1,100})\s*:\s*([^;{}\n]{1,200})(?:;|$)", re.M)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
BLOCK = re.compile(r"(:root|\.dark|\[data-theme[^\]{}]{0,80}\]|html\.dark|@theme(?:\s+inline)?)\s*\{([^{}]{0,20000})\}", re.S)
DARK_MEDIA = re.compile(r"@media[^{;]{0,200}?prefers-color-scheme\s*:\s*dark[^{;]{0,200}\{")
CSS_LIMIT = 200_000
NEXT_FONT = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]next/font/(google|local)['\"]")
NEXT_FONT_DEFAULT = re.compile(r"import\s+([A-Za-z_$][\w$]*)\s+from\s*['\"]next/font/local['\"]")
TW_KEYS = {"colors", "spacing", "fontFamily", "fontSize", "borderRadius", "boxShadow", "screens", "extend", "animation",
           "keyframes", "container", "zIndex"}
# Default-ignorable code points outside Cc/Cf (fillers, variation selectors): invisible to people, not to models.
IGNORABLE_EXTRA = {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180E, 0x180F, 0x3164, 0xFFA0}
SAFE_SEGMENT = re.compile(r"^(?!\.+$)[A-Za-z0-9._~\-\[\]]+$")  # never "." or ".."
# A semver range (must contain a digit), a known protocol specifier, or a dist-tag. ASCII only; checked with
# fullmatch so a trailing newline cannot slip through. Anything else is shown as "?".
SAFE_VERSION = re.compile(r"(?=.*\d)[\w.^~<>=|*@:/ -]{1,40}"
                          r"|(?:workspace|catalog|link|file|github|gitlab|npm|git\+https?|git\+ssh|https?):[\w.^~*@:/#=-]{0,60}"
                          r"|\*|[a-z][a-z0-9-]{0,19}", re.ASCII)


def walk(root, max_depth=8):
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


def code(value, limit=200):
    """Render repo-controlled text as one inline code span that cannot break out of the Markdown."""
    # Inside a code span HTML, Markdown and backslashes are literal; only backticks and table pipes need care.
    return f"`{visible(value).replace('`', chr(39)).replace('|', chr(92) + '|')[:limit]}`"


def visible(value):
    """One line without control, format (bidi, zero-width, tag) or line/paragraph separator characters."""
    return "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Cn", "Zl", "Zp") or ord(c) in IGNORABLE_EXTRA
                   or 0xFE00 <= ord(c) <= 0xFE0F or 0xE0000 <= ord(c) <= 0xE0FFF else c for c in str(value)[:2000])


def cell(value, limit=80):
    """Repo-controlled text outside a code span: inert Markdown (no table breaks, HTML, links or images)."""
    text = visible(value).replace("\\", "\\\\").replace("`", "'").replace("|", "\\|").replace("<", "&lt;")
    return re.sub(r"([\[\]!])", r"\\\1", text)[:limit]


def dark_spans(css):
    """(start, end) of every @media (prefers-color-scheme: dark) { ... } block, in one linear pass."""
    opens = {m.end() - 1: m.start() for m in DARK_MEDIA.finditer(css)}  # position of the "{" -> start of @media
    spans, stack = [], []
    for m in re.finditer(r"[{}]", css):
        if m.group() == "{":
            stack.append(opens.get(m.start()))
        elif stack:
            start = stack.pop()
            if start is not None:
                spans.append((start, m.end()))
    spans += [(start, len(css)) for start in stack if start is not None]  # unclosed blocks run to the end
    return spans


def token_scope(selector, in_dark_media):
    if selector.startswith("@theme"):
        return "@theme"
    if "[data-theme" in selector:
        value = re.search(r"data-theme\s*=\s*[\"']?([\w-]+)", selector)
        value = value.group(1) if value else ""
        if value == "dark":
            return "dark"
        return "root" if value in ("", "light") else None  # other named themes are not light/dark: skip
    if "dark" in selector or in_dark_media:
        return "dark"
    return "root"


def route_from(segments):
    """Turn file-system route segments into a URL path; None if a segment is unsafe to pass to ui_check."""
    out = []
    for seg in segments:
        if not seg or (seg.startswith("(") and seg.endswith(")")) or seg.startswith("@"):  # groups, parallel slots
            continue
        if seg.startswith("("):  # intercepting routes: (.)photo, (..)photo
            seg = re.sub(r"^(\(\.{1,3}\))+", "", seg)
        if not SAFE_SEGMENT.match(seg):
            return None
        out.append(seg)
    return "/" + "/".join(out)


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
        if key in deps and label not in out:
            version = str(deps.get(key) or "")
            version = version if SAFE_VERSION.fullmatch(version) else ("?" if version else "")
            if "://" in version:  # URLs may carry credentials: show the scheme only
                version = version.split(":", 1)[0] + ":…"
            out.append(f"{label} ({version})" if version else label)
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
                text = CSS_COMMENT.sub(" ", read(p, CSS_LIMIT))
                spans = dark_spans(text)
                found = False
                for m in BLOCK.finditer(text):
                    scope = token_scope(m.group(1), any(a <= m.start() < b for a, b in spans))
                    if scope is None:
                        continue
                    found = True
                    for name, value in CSS_VAR.findall(m.group(2)):
                        tokens.setdefault(name, {}).setdefault(scope, " ".join(value.split())[:80])  # first definition wins
                if found:
                    token_files.append(rel)
            elif re.match(r"tailwind\.config\.(js|cjs|mjs|ts)$", f):
                text = read(p)
                keys = sorted(set(re.findall(r"\b([A-Za-z][A-Za-z0-9]*)\s*:", text)) & TW_KEYS)  # best effort, any layout
                dm = re.search(r"darkMode\s*:\s*\[?\s*['\"]([a-z]+)['\"]", text)
                tw_configs.append({"file": rel, "theme_keys": keys, "darkMode": dm.group(1) if dm else None})
                if dm:
                    dark.append(f"tailwind darkMode: {dm.group(1)}")
            elif f.endswith((".tsx", ".jsx", ".ts", ".js")) and ("layout" in f or "_app" in f or "fonts" in f):
                text = read(p)
                for names, kind in NEXT_FONT.findall(text):
                    for n in names.split(","):
                        n = n.strip().split(" as ")[0].strip()
                        if n:
                            fonts.append(f"{n} (next/font/{kind}, {rel})")
                for n in NEXT_FONT_DEFAULT.findall(text):
                    fonts.append(f"{n} (next/font/local, {rel})")
            # components: files under well-known component dirs
            norm = rel.replace(os.sep, "/")
            is_test = re.search(r"\.(test|spec|stories)\.", f) or f.endswith(".d.ts") or f in ("index.ts", "index.tsx")
            if f.endswith(".component.ts") and not is_test:  # Angular components live anywhere under src/app
                components.append(norm)
            elif f.endswith(COMPONENT_EXT) and not f.endswith(".ts") and not is_test \
                    and any(norm.startswith(cd + "/") for cd in COMPONENT_DIRS):  # plain .ts here is hooks/utils/types
                components.append(norm)
            # routes: Next app router, pages router, SvelteKit
            m = re.match(r"^(?:src/)?app/(?:(.*)/)?page\.(tsx|jsx|ts|js|mdx)$", norm)
            r = None
            if m:
                r = route_from((m.group(1) or "").split("/"))
            m = re.match(r"^(?:src/)?pages/(.+)\.(tsx|jsx|vue)$", norm)
            if m and not m.group(1).startswith(("_", "api/")):
                r = route_from(re.sub(r"(^|/)index$", "", m.group(1)).split("/"))
            m = re.match(r"^src/routes/(?:(.*)/)?\+page\.svelte$", norm)
            if m:
                r = route_from((m.group(1) or "").split("/"))
            if r:
                routes.append(r)
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
        f"| {code(name, 80)} | {cell(v.get('root', v.get('@theme', '')))} | {cell(v.get('dark', ''))} |"
        for name, v in t["tokens"].items())
    comps = inv["components"]
    shown = comps[:150]
    comp_list = "\n".join(f"- {code(c)}" for c in shown) + (f"\n- … {len(comps) - len(shown)} more" if len(comps) > len(shown) else "")
    routes = [code(r) + (" (dynamic: use a real value)" if "[" in r else "") for r in inv["routes"][:60]]
    title = inv["app"] if inv["app"] != "." else (inv["package"] or "this repo")
    return f"""# DESIGN.md — UI contract for {code(title)}

_Generated by `scan_ui.py`, then curated. Every UI change reads this first. When the code and this file disagree, fix one of them._

## Stack
- Framework: {', '.join(cell(x, 120) for x in inv['framework']) or '_unknown_'}
- Styling: {', '.join(cell(x, 120) for x in inv['styling']) or '_plain CSS / unknown_'}
- Component library: {', '.join(cell(x, 120) for x in inv['component_library']) or '_none: custom components_'}
- Icons: {', '.join(cell(x, 120) for x in inv['icons']) or '_none detected_'}
- Other UI libraries: {', '.join(cell(x, 120) for x in inv['other_ui_libs']) or '_none_'}
- Tests: {', '.join(cell(x, 120) for x in inv['testing']) or '_none detected_'} · Storybook: {'yes' if inv['storybook'] else 'no'}
- Scripts (start them with `npm run <name>`, never by pasting the command): {', '.join(f'{code(k)}: {code(v)}' for k, v in inv['scripts'].items()) or '_none_'}
{('- shadcn config: ' + code(json.dumps(inv['shadcn']), 400)) if inv['shadcn'] else ''}

## Design tokens (use these; never hard-code colors, spacing or radii)
Source files: {', '.join(code(f) for f in t['files']) or '_none found_'} · {t['count']} custom properties.

| Token | Light / default | Dark |
|---|---|---|
{token_rows or '| _none found_ | | |'}

Tailwind config: {'; '.join(f"{code(c['file'])} keys {c['theme_keys']} darkMode={cell(c['darkMode'])}" for c in inv['tailwind_config']) or '_none_'}

## Typography
{bullet([cell(f, 200) for f in inv['fonts']], '_no next/font imports found: check global CSS for font-family_')}

## Dark mode
{bullet(inv['dark_mode'], '_no dark mode detected_')}

## Existing components: reuse before creating
{comp_list or '_none found in the usual component folders_'}

## Routes (inputs for `ui_check.mjs --routes`)
{bullet(routes, '_none detected_')}

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
        if not cands:
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
