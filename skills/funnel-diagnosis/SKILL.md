---
name: funnel-diagnosis
description: Decide whether a Meta ad's drop or weak result is the creative or the site - if hook, hold and click-through hold while landing-page view, add-to-cart or checkout rates fall or lag, it points at the page and gives a short page checklist. Reads every ad and the account as a whole against its own baseline. Use when sales drop but clicks hold, when the user asks "is it the ad or the website", before pausing an ad that may have a page problem, or when keep-or-kill says check the site.
license: MIT
metadata:
  version: "0.2.0"
  role: analyse
---

# Funnel diagnosis

A sale needs the ad to stop someone, hold them, earn the click, and then the page to load, the cart to fill and checkout to start. When results fall, the step that broke says who should fix it. This skill reads each step against the ad's own start and against similar ads in the account, and calls it: creative, site, both or neither, or says it has too little to judge.

`keep-or-kill` uses the same read: an ad it would pause whose funnel points at the site becomes "Check before cutting", with the reason.

## Before you start

1. Get daily rows with the site columns: landing page views, adds to cart and checkouts initiated (`creative-context/references/export-recipe.md`; in the connector pull these are action types). Without them the site side is unreadable, and the skill says which column to add, never that the site is fine.
2. Say which data mode you are in.

## Run it

```
python3 -I scripts/funnel.py ads.csv
python3 -I scripts/funnel.py ads.csv --ad 120000000002
python3 -I scripts/funnel.py ads.csv --group-by format,ad_type --json
python3 -I scripts/funnel.py ads.csv --profile creative-profile.md --where market=US
```

`--window` (6), `--min-change` (8) and `--min-impressions` (1000) are arbitrary defaults; set them from your own account. `--z` (1.96) is the common two-sided 95% convention from statistics, not a benchmark: raise it to call fewer steps weak.

## How it decides

The steps the ad controls: hook rate, hold rate, click-through rate. The steps on the site: landing-page view rate (page loads per link click), add-to-cart rate, cart-to-checkout rate. Purchase rate is shown beside them but decides nothing, because a weak one can be the offer or the audience as much as the page.

Each step is weak when either holds, both against the account itself:

- **Falling:** down at least `--min-change` percent from the ad's first `--window` delivery days to its last, and the fall is clear on the ad's own counts (at least `--z` standard errors).
- **Low:** in the bottom quartile of similar ads, and below their pooled rate by at least `--z` standard errors.

| Call | Means |
|---|---|
| site | a site step is weak while the ad still earns attention and clicks: check the page first |
| creative | a step the ad controls is weak while the site holds: work on the ad |
| both | weak on both sides: check the page before judging the creative |
| neither | nothing is weak against the ad's group or its own start |
| unjudged | too few delivery days and too few comparable ads to judge a step on each side: no call |
| unreadable | no site step has data: add the column it names |

The account-wide read pools every ad by day, so a problem that hits every ad (checkout, payment, shipping costs, stock) shows there first.

## Present the result

1. Lead with the counts and the first site call in one sentence: what held, what fell, what to check.
2. For each site call, the weak steps and why, then work through `references/page-checklist.md` with the user.
3. Name the columns to add for anything unreadable.
4. **Next step:** after the page is checked, `keep-or-kill` for a fresh verdict; for creative calls, `hook-writer` or `fatigue-planner`.

## Guardrails

- A missing step is `n/a (missing <field>)` and never read as healthy.
- Relative only: no benchmark conversion or page-load rates.
- The page checklist is a list of things to check, not a finding. Only the user (or their site analytics) can confirm a page problem.
- Read only: never pause, edit or change anything.

## How to use

Have ready: daily rows with landing page views, adds to cart and checkouts initiated.

Try:

- "Sales dropped but clicks look fine. Is it the ad or the site?"
- "Before I pause this ad, check whether the page is the problem."
- "Is something wrong with checkout across the account?"

## Common questions

- **Why is the site unreadable?** The export has no landing page view, add-to-cart or checkout column. The output names the one to add.
- **Why doesn't purchase rate decide?** A weak purchase rate can be the offer, price or audience, not only the page.
- **Can it see my site?** No. It reads the ad data; the checklist tells you what to look at.
- **Why "both"?** Steps on each side are weak. Fix the page first, then judge the creative on clean data.
- More: creative-context/references/faq.md
