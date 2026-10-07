---
name: creative-grader
description: Grade Meta ad creative against your own account's baseline and name the first broken step in each ad's funnel (reach cost, hook, hold, click, post-click, payback) with one concrete action. Use when the user asks which ads are weak and why, "grade my ads", "why is this ad not converting", or wants a per-ad diagnosis from an Ads Manager export or a Meta ads connector.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Creative grader

Turns ad-level numbers into a diagnosis per ad: which step of the funnel breaks first, and what to change. Every grade is relative to the same account's own ads, within the same format. There are no universal "good" values here and you must not quote any.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** List its tools, then pull an ad-level report with a **daily** breakdown (one row per ad per day) over the last 30 days. Fetch: ad name, ad id, date, spend, impressions, reach, link clicks, 3-second video plays (the `video_view` action), ThruPlays, purchases and purchase value, adds to cart. Check which fields actually came back; a missing one means that metric is unavailable. Write the returned rows, unchanged, to a JSON file (a list of row objects, or the API's `{"data": [...]}`), then pass that file to the script.
2. **CSV or screenshots.** Ask for an Ads Manager export using `creative-context/references/export-recipe.md`. With screenshots and no code, read the numbers off the image, compute by hand from `creative-context/references/metrics.md`, and say they may contain transcription errors.
3. **No data.** Say what is needed and offer the export recipe. You may talk about what to look for, but label everything "no performance data" and grade nothing.

## Run it

```
python3 scripts/grade.py ads.csv                 # or ads.json from the connector
python3 scripts/grade.py ads.csv --group-by format,ad_type --min-impressions 2000
python3 scripts/grade.py ads.csv --json
```

`--min-impressions` (default 1000) is an arbitrary default: set it from the account's own spend per ad and tell the user what you chose. The output opens with its basis (date window, grouping, ads per group, which clicks CTR used, which conversions column fed CPA). Read it, do not retype numbers from memory.

## What the script does

- Grades hook rate, hold rate, CTR, CPM, CVR, add-to-cart rate, CPA and ROAS per ad as top quartile, middle or bottom quartile within the ad's group. A group with fewer than 5 ads falls back to the whole account, and the output says so. Costs are inverted: a low CPM is top quartile.
- Reads the funnel in order and stops at the first bottom-quartile step: reach cost, hook, hold, click, post-click, payback. Post-click is only read while CTR is healthy, because a weak CTR is already the broken step. The action for each step is in `references/diagnosis-patterns.md`.
- Ads under the impression floor are "not graded (low volume)". Missing video fields show as `n/a (missing <field>)`, the diagnosis skips that step and lists what it skipped. A skipped step is never read as healthy.

## Present the result

1. Lead with the diagnosis counts and the three ads that most need attention, each with its step and action.
2. Then the table.
3. Say what could not be graded and why.
4. Frame post-click and reach-cost findings as "check the site / the auction first", not "the creative failed". The creative owns hook, hold and click.

## Guardrails

- A group needs at least 5 comparable ads to be graded on its own (an arbitrary default, not a statistical rule); smaller groups fall back to the whole account, and the output says so.
- Relative grading only. Never invent or quote a benchmark; if asked for one, explain that this skill compares an ad with its own account.
- Say `n/a` when data is missing. Never turn a missing value into 0.
- Ad age matters: a very young ad has not settled. For a keep or kill call, use `keep-or-kill`.
- Read only. Do not change anything in the ad account.
