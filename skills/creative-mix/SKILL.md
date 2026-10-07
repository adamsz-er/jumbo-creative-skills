---
name: creative-mix
description: Map a Meta ad account's creative portfolio - concept by format coverage, ad-type split, funnel-stage fit and spend concentration - and find the gaps worth testing and the over-reliance to fix. Use when the user asks what creative they are missing, whether they lean too hard on one concept or format, wants a coverage grid, or a portfolio review from an Ads Manager export or a Meta ads connector.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Creative mix

Shows what the account is running, not how each ad performs one by one (that is `creative-grader`). It reads ad names with the naming convention in `creative-context`, so it works best when names carry concept, format and ad type.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** Call read-only tools only: never one that activates, updates or changes anything. Pull an ad-level report over the window you analyse (several weeks or more); daily rows are fine, the script sums them. Follow the numbered steps in `creative-context/references/data-inputs.md`: field catalogue first, every response saved to a JSON file, then `python3 scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total>` and use `ads.csv` wherever a CSV is named below. A `WARNING` line or exit 3 means the pull does not reconcile: re-fetch or drop duplicates the missing ads and run it again before you analyse. 3-second plays are derived per ad and shown as "(derived)"; say so when you quote a hook rate.
2. **CSV or screenshots.** Ask for an Ads Manager export (`creative-context/references/export-recipe.md`). With screenshots, tally ads by format and concept by hand and say so.
3. **No data.** Ask the user to list their live ads by concept and format; build the grid from that and label everything "no performance data". Offer the export recipe.

## Run it

```
python3 scripts/mix.py ads.csv                # ads.csv from the connector: see step 1
python3 scripts/mix.py ads.csv --no-family
python3 scripts/mix.py ads.csv --min-proven-spend 900     # set the floor from your own account
python3 scripts/mix.py ads.csv --pattern concept,format,creator,ad_type,product,tone,funnel_stage
```

Names that do not match the convention go to an `unclassified` bucket that is counted and listed, never dropped. Report that count first: a large unclassified share means the grid describes only part of the account, and the right next step is agreeing a naming convention (`creative-context/references/naming-convention.md`).

`--min-proven-spend` is the BAU spend a concept or format needs before it counts as proven for gap ranking (arbitrary default: three times the account's median ad spend; set it from your own account and tell the user what you chose). A concept below it can still be top quartile on ROAS, but it never leads the "worth testing" list, because a result from negligible spend is noise.

`--pattern` is for accounts whose names carry other fields in another order, such as a funnel stage. Confirm the mapping with the user before relying on it.

## How to read it

`references/mix-reading.md` explains the tables and the read-outs. In short: gaps are hypotheses to test, not results; over-reliance and near-duplicates are about risk; promo and BAU are always read separately.

## Present the result

1. Lead with the unclassified count, then the biggest finding: an over-reliance flag, or the strongest gaps.
2. Then the format, concept, ad-type and grid tables.
3. Explain the families: the output lists which ads were grouped into each, so the user can see and override the grouping.
4. Say plainly when performance could not be ranked (too few concepts or formats) or the funnel view is absent.

## Guardrails

- Relative reading only: "top quartile" means top quartile of this account's own BAU concepts or formats on pooled ROAS. No benchmarks, no "ideal split".
- A gap is a place with no evidence, not a place that will win. Say "worth testing". Only gaps beside a proven concept or format (enough spend) are listed.
- The 60% over-reliance line and the minimum of 5 concepts or formats before ranking are arbitrary defaults, not statistical rules. Ask the user what concentration is normal for their account.
- Read only. Do not change anything in the ad account.
