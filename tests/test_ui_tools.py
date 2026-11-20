"""Tests for the UI tooling: scan_ui.py (always) and ui_check.mjs (browser part skipped without Playwright/Chromium)."""

import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS = os.path.join(ROOT, "plugins", "dev-squad", "skills")
SCAN = os.path.join(SKILLS, "ui-context", "scripts", "scan_ui.py")
CHECK = os.path.join(SKILLS, "visual-verify", "scripts", "ui_check.mjs")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class ScanUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        w = cls.web = os.path.join(cls.tmp.name, "web")
        write(os.path.join(w, "package.json"), json.dumps({
            "name": "web", "scripts": {"dev": "next dev", "build": "next build", "test:e2e": "playwright test"},
            "dependencies": {"next": "15.1.0", "react": "19.0.0", "tailwindcss": "4.0.0", "lucide-react": "0.460.0",
                             "next-themes": "0.4.4", "@radix-ui/react-dialog": "1.1.2"},
            "devDependencies": {"@playwright/test": "1.49.0"}}))
        write(os.path.join(w, "components.json"), json.dumps({"style": "new-york", "aliases": {"ui": "@/components/ui"}}))
        write(os.path.join(w, "app", "globals.css"),
              ":root { --background: oklch(1 0 0); --radius: 0.625rem; }\n.dark { --background: oklch(0.145 0 0); }\n"
              "@theme inline { --font-sans: var(--font-geist-sans); }\n")
        write(os.path.join(w, "tailwind.config.ts"), 'export default {\n  darkMode: ["class"],\n  theme: {\n    extend: {\n'
                                                     '      colors: { brand: "#0f766e" },\n    },\n  },\n}\n')
        write(os.path.join(w, "app", "layout.tsx"), 'import { Geist } from "next/font/google"\n')
        write(os.path.join(w, "app", "page.tsx"), "export default function P(){return null}")
        write(os.path.join(w, "app", "(dashboard)", "settings", "page.tsx"), "export default function P(){return null}")
        for c in ("button", "card"):
            write(os.path.join(w, "components", "ui", f"{c}.tsx"), "export const X = 1")
        write(os.path.join(w, "components", "ui", "button.stories.tsx"), "x")
        write(os.path.join(w, "node_modules", "junk", "index.tsx"), "x")
        cls.inv_path = os.path.join(cls.tmp.name, "inv.json")
        cls.md_path = os.path.join(cls.tmp.name, "DESIGN.md")
        subprocess.run([sys.executable, "-I", SCAN, "--root", w, "--md", cls.md_path, "--json", cls.inv_path],
                       check=True, capture_output=True)
        with open(cls.inv_path, encoding="utf-8") as fh:
            cls.inv = json.load(fh)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stack(self):
        self.assertIn("Next.js (15.1.0)", self.inv["framework"])
        self.assertTrue(any(x.startswith("shadcn/ui") for x in self.inv["component_library"]))
        self.assertIn("Lucide (0.460.0)", self.inv["icons"])

    def test_tokens_fonts_dark_mode(self):
        tokens = self.inv["design_tokens"]["tokens"]
        self.assertEqual(tokens["--background"], {"root": "oklch(1 0 0)", "dark": "oklch(0.145 0 0)"})
        self.assertIn("--font-sans", tokens)
        self.assertTrue(any(f.startswith("Geist ") for f in self.inv["fonts"]))
        self.assertIn("tailwind darkMode: class", self.inv["dark_mode"])

    def test_components_and_routes(self):
        self.assertEqual(self.inv["components"], ["components/ui/button.tsx", "components/ui/card.tsx"])
        self.assertEqual(self.inv["routes"], ["/", "/settings"])  # route group "(dashboard)" removed

    def test_markdown_has_contract_sections(self):
        with open(self.md_path, encoding="utf-8") as fh:
            md = fh.read()
        for heading in ("## Design tokens", "## Existing components: reuse before creating", "## Accessibility baseline",
                        "## Patterns (TODO", "## Aesthetic direction"):
            self.assertIn(heading, md)

    def test_monorepo_requires_app(self):
        mono = os.path.join(self.tmp.name, "mono")
        write(os.path.join(mono, "package.json"), '{"name": "root"}')
        write(os.path.join(mono, "apps", "a", "package.json"), '{"dependencies": {"react": "18"}}')
        write(os.path.join(mono, "apps", "b", "package.json"), '{"dependencies": {"vue": "3"}}')
        r = subprocess.run([sys.executable, "-I", SCAN, "--root", mono], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("apps/a", r.stderr)
        r = subprocess.run([sys.executable, "-I", SCAN, "--root", mono, "--app", "apps/b"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Vue", r.stdout)


NODE = shutil.which("node")


def browser_available():
    if not NODE:
        return False
    probe = ("import('playwright').catch(() => import(require('child_process').execSync('npm root -g').toString().trim()"
             " + '/playwright/index.js')).then(p => (p.chromium || p.default.chromium).launch()).then(b => b.close())")
    try:
        return subprocess.run([NODE, "-e", probe], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(NODE, "node not installed")
class UiCheckArgsTest(unittest.TestCase):
    def run_check(self, *args):
        return subprocess.run([NODE, CHECK, *args], capture_output=True, text=True, timeout=60)

    def test_help_and_validation(self):
        self.assertEqual(self.run_check("--help").returncode, 0)
        self.assertEqual(self.run_check().returncode, 2)  # --base-url required
        self.assertEqual(self.run_check("--base-url", "file:///etc/passwd").returncode, 2)
        self.assertEqual(self.run_check("--base-url", "http://x", "--viewports", "wide").returncode, 2)
        self.assertEqual(self.run_check("--base-url", "http://x", "--fail-on", "sometimes").returncode, 2)


SEEDED = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seeded</title><style>.faint{color:#bbb;background:#fff}.wide{width:900px;height:40px}</style></head>
<body><main><h1>Orders</h1><p class="faint">hard to read</p><img src="/missing.png">
<button><svg width="16" height="16"><circle cx="8" cy="8" r="6"/></svg></button><div class="wide">banner</div></main>
<script>console.error("boom")</script></body></html>"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(browser_available(), "Playwright/Chromium not available")
class UiCheckBrowserTest(unittest.TestCase):
    def test_seeded_issues_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = os.path.join(tmp, "site")
            write(os.path.join(site, "index.html"), SEEDED)
            handler = functools.partial(QuietHandler, directory=site)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                out = os.path.join(tmp, "out")
                r = subprocess.run([NODE, CHECK, "--base-url", f"http://127.0.0.1:{server.server_port}",
                                    "--routes", "/index.html", "--viewports", "375x812,1440x900", "--out", out,
                                    "--fail-on-console", "--fail-on-overflow", "--wait-server", "10"],
                                   capture_output=True, text=True, cwd=tmp, timeout=180)
            finally:
                server.shutdown()
            self.assertEqual(r.returncode, 1, r.stderr)
            with open(os.path.join(out, "report.json"), encoding="utf-8") as fh:
                report = json.load(fh)
            by_vp = {x["viewport"]: x for x in report["results"]}
            self.assertIn("div.wide", " ".join(by_vp["375x812"]["overflow"]["culprits"]))
            self.assertIsNone(by_vp["1440x900"]["overflow"])
            self.assertTrue(any("boom" in e for e in by_vp["375x812"]["consoleErrors"]))
            self.assertTrue(any(f.get("status") == 404 for f in by_vp["375x812"]["failedRequests"]))
            self.assertTrue(os.path.exists(by_vp["375x812"]["screenshot"]))
            if report["axe"]:  # only when axe-core is resolvable from the project or global npm root
                ids = {v["id"] for v in by_vp["375x812"]["axe"]}
                self.assertTrue({"image-alt", "button-name", "color-contrast"} <= ids, ids)


if __name__ == "__main__":
    unittest.main()
