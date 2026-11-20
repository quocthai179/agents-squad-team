#!/usr/bin/env node
// ui_check.mjs — look at a running UI the way a user would, and collect evidence an agent can cite.
//
// For every route × viewport × theme it records: a screenshot, an ARIA snapshot, console errors,
// uncaught page errors, failed requests (status >= 400 or network failure), horizontal overflow
// (with the elements that cause it) and axe-core accessibility violations (WCAG 2.2 A/AA + best
// practices). Writes report.json + report.md next to the screenshots and exits non-zero when the
// --fail-on conditions are met, so it works for agents and in CI alike.
//
// Needs `playwright` (or `@playwright/test`) and, for the a11y scan, `axe-core`. They are resolved
// from the current project first, then from the global npm root. Nothing is installed automatically.
//
// Examples:
//   node ui_check.mjs --base-url http://localhost:3000 --routes /,/settings
//   node ui_check.mjs --base-url http://localhost:3000 --routes /login --viewports 375x812 \
//        --themes light,dark --dark-mode class --fail-on serious --fail-on-console
//   node ui_check.mjs --base-url https://preview-123.example.dev --routes / --wait-server 0

import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const HELP = `usage: node ui_check.mjs --base-url URL [options]
  --routes /a,/b            routes to check (default /)
  --viewports WxH,...       default 375x812,768x1024,1440x900
  --themes light,dark       default light
  --dark-mode media|class   how to switch to dark: prefers-color-scheme (default) or <html class="dark">
  --out DIR                 output dir (default .squad/ui/shots/<timestamp>)
  --wait-server SECONDS     wait until the base URL answers (default 60; 0 = no wait)
  --wait-for SELECTOR       wait for this selector after load
  --settle-ms N             extra wait after load for animations/fonts (default 300)
  --full-page               full-page screenshots
  --no-axe                  skip the accessibility scan
  --no-aria                 skip ARIA snapshots
  --header "Name: value"    extra request header (repeatable; values are never written to reports)
  --storage-state FILE      Playwright storage state (logged-in session)
  --fail-on LEVEL           none|minor|moderate|serious|critical (default serious): exit 1 if any axe
                            violation at or above LEVEL
  --fail-on-console         also exit 1 on console errors, page errors or failed requests
  --fail-on-overflow        also exit 1 on horizontal overflow
  --timeout MS              navigation timeout (default 30000)`;

const IMPACT = { minor: 1, moderate: 2, serious: 3, critical: 4 };

function parseArgs(argv) {
  const a = { routes: ["/"], viewports: ["375x812", "768x1024", "1440x900"], themes: ["light"], darkMode: "media",
    waitServer: 60, settleMs: 300, axe: true, aria: true, headers: [], failOn: "serious", timeout: 30000 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = () => { if (i + 1 >= argv.length) die(`${k} needs a value`); return argv[++i]; };
    switch (k) {
      case "--base-url": a.baseUrl = v(); break;
      case "--routes": a.routes = v().split(",").map((s) => s.trim()).filter(Boolean); break;
      case "--viewports": a.viewports = v().split(",").map((s) => s.trim()).filter(Boolean); break;
      case "--themes": a.themes = v().split(",").map((s) => s.trim()).filter(Boolean); break;
      case "--dark-mode": a.darkMode = v(); break;
      case "--out": a.out = v(); break;
      case "--wait-server": a.waitServer = Number(v()); break;
      case "--wait-for": a.waitFor = v(); break;
      case "--settle-ms": a.settleMs = Number(v()); break;
      case "--full-page": a.fullPage = true; break;
      case "--no-axe": a.axe = false; break;
      case "--no-aria": a.aria = false; break;
      case "--header": a.headers.push(v()); break;
      case "--storage-state": a.storageState = v(); break;
      case "--fail-on": a.failOn = v(); break;
      case "--fail-on-console": a.failOnConsole = true; break;
      case "--fail-on-overflow": a.failOnOverflow = true; break;
      case "--timeout": a.timeout = Number(v()); break;
      case "-h": case "--help": console.log(HELP); process.exit(0); break;
      default: die(`unknown option ${k}\n${HELP}`);
    }
  }
  if (!a.baseUrl) die(`--base-url is required\n${HELP}`);
  let u;
  try { u = new URL(a.baseUrl); } catch { die(`invalid --base-url ${a.baseUrl}`); }
  if (!["http:", "https:"].includes(u.protocol)) die("--base-url must be http(s)");
  if (!["media", "class"].includes(a.darkMode)) die("--dark-mode must be media or class");
  if (a.failOn !== "none" && !IMPACT[a.failOn]) die("--fail-on must be none|minor|moderate|serious|critical");
  for (const vp of a.viewports) if (!/^\d+x\d+$/.test(vp)) die(`bad viewport ${vp} (use WxH)`);
  for (const t of a.themes) if (!["light", "dark"].includes(t)) die(`bad theme ${t}`);
  a.out ??= path.join(".squad", "ui", "shots", new Date().toISOString().replace(/[:.]/g, "-"));
  return a;
}

function die(msg, code = 2) { console.error(msg); process.exit(code); }

function resolveFrom(name) {
  const bases = [path.join(process.cwd(), "noop.js")];
  try { bases.push(path.join(execSync("npm root -g", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim(), "noop.js")); } catch {}
  for (const base of bases) {
    try { return createRequire(base).resolve(name); } catch {}
  }
  return null;
}

async function loadPlaywright() {
  for (const name of ["playwright", "@playwright/test"]) {
    const p = resolveFrom(name);
    if (p) { const m = await import(p.startsWith("/") ? `file://${p}` : p); return m.chromium ?? m.default?.chromium; }
  }
  die("Playwright not found. Ask the user before installing: npm i -D playwright && npx playwright install chromium");
}

async function waitForServer(url, seconds) {
  if (!seconds) return;
  const deadline = Date.now() + seconds * 1000;
  let last = "";
  while (Date.now() < deadline) {  // bounded readiness probe inside the tool, not an agent polling loop
    try { const r = await fetch(url, { redirect: "manual" }); if (r.status < 500) return; last = `HTTP ${r.status}`; }
    catch (e) { last = e.cause?.code || e.message; }
    await new Promise((r) => setTimeout(r, 1000));
  }
  die(`server at ${url} did not answer within ${seconds}s (${last}). Is the dev server running?`);
}

const slug = (route) => (route.replace(/^\/+|\/+$/g, "").replace(/[^A-Za-z0-9._-]+/g, "_") || "root");

async function checkPage(browser, a, route, vp, theme, axePath) {
  const [width, height] = vp.split("x").map(Number);
  const extraHTTPHeaders = Object.fromEntries(a.headers.map((h) => { const i = h.indexOf(":"); return [h.slice(0, i).trim(), h.slice(i + 1).trim()]; }));
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme === "dark" && a.darkMode === "media" ? "dark" : "light",
    reducedMotion: "reduce", extraHTTPHeaders, ...(a.storageState ? { storageState: a.storageState } : {}) });
  const page = await ctx.newPage();
  const consoleErrors = [], pageErrors = [], failedRequests = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300)); });
  page.on("pageerror", (e) => pageErrors.push(String(e.message || e).slice(0, 300)));
  page.on("requestfailed", (r) => failedRequests.push({ url: r.url().slice(0, 200), error: r.failure()?.errorText || "failed" }));
  page.on("response", (r) => { if (r.status() >= 400) failedRequests.push({ url: r.url().slice(0, 200), status: r.status() }); });

  const url = new URL(route, a.baseUrl).toString();
  const res = { route, viewport: vp, theme, url, status: null };
  try {
    const resp = await page.goto(url, { waitUntil: "load", timeout: a.timeout });
    res.status = resp?.status() ?? null;
    try { await page.waitForLoadState("networkidle", { timeout: 5000 }); } catch {}
    if (a.waitFor) await page.waitForSelector(a.waitFor, { timeout: a.timeout });
    if (theme === "dark" && a.darkMode === "class") await page.evaluate(() => document.documentElement.classList.add("dark"));
    if (a.settleMs) await page.waitForTimeout(a.settleMs);

    res.overflow = await page.evaluate(() => {
      const de = document.documentElement, vw = de.clientWidth;
      if (de.scrollWidth <= vw + 1) return null;
      const culprits = [];
      for (const el of document.body.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        if (r.width && r.right > vw + 1) {
          const id = el.id ? `#${el.id}` : "";
          const cls = typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
          culprits.push(`${el.tagName.toLowerCase()}${id}${cls} (right=${Math.round(r.right)}px)`);
          if (culprits.length >= 5) break;
        }
      }
      return { scrollWidth: de.scrollWidth, viewportWidth: vw, culprits };
    });

    const base = path.join(a.out, `${slug(route)}__${vp}__${theme}`);
    await page.screenshot({ path: `${base}.png`, fullPage: !!a.fullPage });
    res.screenshot = `${base}.png`;
    if (a.aria) {
      try { fs.writeFileSync(`${base}.aria.yml`, await page.locator("body").ariaSnapshot()); res.aria = `${base}.aria.yml`; }
      catch (e) { res.ariaError = String(e.message).slice(0, 200); }
    }
    if (axePath) {
      await page.addScriptTag({ path: axePath });
      const r = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } }));
      res.axe = r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.length,
        targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }));
    }
  } catch (e) {
    res.error = String(e.message || e).split("\n")[0].slice(0, 300);
  } finally {
    res.consoleErrors = consoleErrors; res.pageErrors = pageErrors; res.failedRequests = failedRequests;
    await ctx.close();
  }
  return res;
}

function toMarkdown(a, results, verdict) {
  const L = [`# UI check — ${a.baseUrl}`, "", `Verdict: **${verdict.fail ? "FAIL" : "PASS"}**${verdict.reasons.length ? " — " + verdict.reasons.join("; ") : ""}`, "",
    "| Route | Viewport | Theme | HTTP | Console/page errors | Failed requests | Overflow | a11y (crit/ser/mod/min) | Screenshot |",
    "|---|---|---|---|---|---|---|---|---|"];
  for (const r of results) {
    const c = { critical: 0, serious: 0, moderate: 0, minor: 0 };
    for (const v of r.axe || []) c[v.impact] = (c[v.impact] || 0) + 1;
    const a11y = r.axe ? `${c.critical}/${c.serious}/${c.moderate}/${c.minor}` : "—";
    const ov = r.overflow ? `⚠️ ${r.overflow.scrollWidth}>${r.overflow.viewportWidth}px` : "ok";
    L.push(`| ${r.route} | ${r.viewport} | ${r.theme} | ${r.error ? "ERROR" : r.status} | ${r.consoleErrors.length + r.pageErrors.length} | ` +
      `${r.failedRequests.length} | ${ov} | ${a11y} | ${r.screenshot ? `\`${r.screenshot}\`` : "—"} |`);
  }
  const details = [];
  for (const r of results) {
    const items = [];
    if (r.error) items.push(`- navigation error: ${r.error}`);
    for (const e of [...r.pageErrors, ...r.consoleErrors]) items.push(`- console/page error: ${e}`);
    for (const f of r.failedRequests) items.push(`- failed request: ${f.status ?? f.error} ${f.url}`);
    if (r.overflow) items.push(`- horizontal overflow: ${r.overflow.culprits.join(", ") || "(no single culprit found)"}`);
    for (const v of r.axe || []) items.push(`- a11y ${v.impact}: ${v.id} — ${v.help} (${v.nodes} node(s): ${v.targets.join(" | ")}) ${v.helpUrl}`);
    if (items.length) details.push(`### ${r.route} @ ${r.viewport} ${r.theme}`, ...items, "");
  }
  return [...L, "", "## Details", "", ...(details.length ? details : ["_no issues found_"])].join("\n") + "\n";
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  fs.mkdirSync(a.out, { recursive: true });
  await waitForServer(a.baseUrl, a.waitServer);
  let axePath = null;
  if (a.axe) {
    axePath = resolveFrom("axe-core/axe.min.js");
    if (!axePath) console.error("axe-core not found: accessibility scan skipped. Ask the user before installing: npm i -D axe-core");
  }
  const chromium = await loadPlaywright();
  let browser;
  try { browser = await chromium.launch(); }
  catch (e) { die(`could not launch Chromium (${String(e.message).split("\n")[0]}). Ask the user before running: npx playwright install chromium`); }
  const results = [];
  try {
    for (const route of a.routes) for (const vp of a.viewports) for (const theme of a.themes)
      results.push(await checkPage(browser, a, route, vp, theme, axePath));
  } finally { await browser.close(); }

  const reasons = [];
  const level = IMPACT[a.failOn] || 99;
  const axeHits = results.flatMap((r) => (r.axe || []).filter((v) => (IMPACT[v.impact] || 0) >= level));
  if (a.failOn !== "none" && axeHits.length) reasons.push(`${axeHits.length} a11y violation(s) at ${a.failOn}+`);
  if (results.some((r) => r.error)) reasons.push("navigation errors");
  if (a.failOnConsole && results.some((r) => r.consoleErrors.length || r.pageErrors.length || r.failedRequests.length)) reasons.push("console errors or failed requests");
  if (a.failOnOverflow && results.some((r) => r.overflow)) reasons.push("horizontal overflow");
  const verdict = { fail: reasons.length > 0, reasons };

  const report = { baseUrl: a.baseUrl, generatedAt: new Date().toISOString(), axe: !!axePath, headerNames: a.headers.map((h) => h.split(":")[0].trim()),
    verdict, results };
  fs.writeFileSync(path.join(a.out, "report.json"), JSON.stringify(report, null, 2));
  const md = toMarkdown(a, results, verdict);
  fs.writeFileSync(path.join(a.out, "report.md"), md);
  console.log(md);
  console.log(`Report: ${path.join(a.out, "report.md")}`);
  process.exit(verdict.fail ? 1 : 0);
}

main().catch((e) => die(`ui_check failed: ${e.stack || e}`));
