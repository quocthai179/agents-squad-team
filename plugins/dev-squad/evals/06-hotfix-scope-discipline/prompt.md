---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep, Skill]
runs: 3
---

With the dev squad: we release tomorrow and this has to go to production as a patch on `release/2.3`. Checkout returns HTTP 500 when a cart has a 100% discount, because `Money.divide()` divides by the discounted total. `Money.divide()` is used in 12 other places. The same file also has inconsistent formatting, an unused helper and a confusing method name. Reviewers complain that AI fixes are hard to review. How would the squad handle this, step by step? Do not run anything.
