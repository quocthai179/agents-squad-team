# Visual regression and accessibility gating in code and CI

`ui_check.mjs` is for looking at a change while you work. For regressions that must never come back, put checks **in the project's test suite**, so they run on every PR without an agent.

## Playwright: screenshot baselines + axe

```ts
// e2e/visual.spec.ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pages = ["/", "/settings"];  // take these from .squad/ui/DESIGN.md "Routes"

for (const path of pages) {
  test(`visual + a11y ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot(`${path.replace(/\W+/g, "_") || "root"}.png`, {
      fullPage: true,
      animations: "disabled",
      mask: [page.locator("[data-testid=clock], [data-dynamic]")],  // dates, avatars, random data
      maxDiffPixelRatio: 0.01,
    });
    const a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(a11y.violations.filter(v => ["critical", "serious"].includes(v.impact ?? ""))).toEqual([]);
  });
}
```

`playwright.config.ts`: add `projects` for `{ viewport: { width: 375, height: 812 } }` and `{ viewport: { width: 1440, height: 900 } }`, plus `colorScheme: "dark"` if the product supports it.

Rules:
- **Baselines are platform-specific.** Generate and compare them in the same environment, i.e. the CI image (the Playwright Docker image), not a laptop. The command is `npx playwright test --update-snapshots`.
- **Update baselines only for intended changes.** The PR must say which screens changed and why. A reviewer looks at the diff images.
- **Make pages deterministic.** Fixed test data, mocked time, masked dynamic regions, animations disabled.
- **Keep the gate on critical/serious axe violations.** List known moderate issues in `.squad/ui/DESIGN.md` until they are fixed. Never silence a rule globally.

## Storybook projects

If the project has Storybook, prefer component-level checks:
- `@storybook/test-runner` with the a11y addon (axe) gives per-story accessibility checks;
- Chromatic or Argos give hosted visual diffs with review UIs. Both are paid above their free tiers, so ask before adding them.

## CI templates

- Start the app in the Playwright config's `webServer` block (`command: "npm run start"`, `url`, `reuseExistingServer: !process.env.CI`), not in CI shell scripts.
- Pin the Playwright image to the project's `@playwright/test` version. For supply-chain safety, pin by digest (`image@sha256:…`, keeping the tag in a comment) and pin actions to commit SHAs. Dependabot or Renovate can keep them current.
- Run visual jobs on `pull_request`, never `pull_request_target`: fork code must not run with your secrets.
- Failure artifacts (traces, screenshots) can contain data. Keep retention short.

**GitHub Actions**

```yaml
visual:            # under jobs:
  runs-on: ubuntu-latest
  permissions:
    contents: read
  container: mcr.microsoft.com/playwright:v1.49.0-noble   # match @playwright/test
  steps:
    - uses: actions/checkout@v4
    - run: npm ci
    - run: npm run build
    - run: npx playwright test e2e/visual.spec.ts
    - uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: playwright-report
        retention-days: 7
        path: |
          playwright-report/
          test-results/
```

**GitLab CI**

```yaml
visual:
  image: mcr.microsoft.com/playwright:v1.49.0-noble   # match @playwright/test
  script:
    - npm ci
    - npm run build
    - npx playwright test e2e/visual.spec.ts
  artifacts:
    when: on_failure
    expire_in: 7 days
    paths: [playwright-report/, test-results/]
```
