---
name: creative-report
description: Build one fixed, branded creative dashboard (overview, Pareto, keep and kill, with ad previews) as a self-contained HTML file that opens in any browser, prints to PDF and can be shared. Use when the user wants a shareable creative review, a dashboard or report for a client or team, or asks to "put this in a report". Needs ad performance data; any panel without its data shows why and how to get it.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Creative report

Packages a creative review into one branded HTML dashboard. It does not analyse on its own terms: it lays out the daily data and what `keep-or-kill` (and optionally `creative-grader` and `creative-mix`) found, leads with the answer, and shows every gap in the data instead of hiding it. Everything is graded against the account's own ads, never a benchmark.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** Call read-only tools only: never one that activates, updates or changes anything. Pull a daily, ad-level report as the analyse skills describe. Follow the numbered steps in `creative-context/references/data-inputs.md`: field catalogue first, every response saved to a JSON file, then `python3 scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total>` and use `ads.csv` wherever a CSV is named below. A `WARNING` line or exit 3 means the pull does not reconcile: re-fetch or drop duplicates the missing ads and run it again before you analyse. 3-second plays are derived per ad and shown as "(derived)"; say so when you quote a hook rate.
2. **CSV export.** An Ads Manager export (`creative-context/references/export-recipe.md`), daily rows if possible.
3. **No data.** There is nothing to report. Say so and offer the export recipe. Do not make a report from guesses.

## Recommended path: verdicts first, then the dashboard

Run keep-or-kill with `--json` (and, for the footer's grading basis and missing-data notes, creative-grader and creative-mix), then build the dashboard from the same daily data:

```
# add --completeness only as described below; this example pull was reconciled
python3 ../keep-or-kill/scripts/verdicts.py ads.csv --json > verdicts.json
python3 ../creative-grader/scripts/grade.py ads.csv --json > grade.json
python3 ../creative-mix/scripts/mix.py ads.csv --json > mix.json
python3 scripts/report.py ads.csv --verdicts verdicts.json --grade grade.json --mix mix.json \
    --profile creative-profile.md --source "Meta ads connector" --completeness reconciled \
    --previews previews/ --thumbs thumbs/ -o report.html
```

- `--source`: "Meta ads connector" for a connector pull, else leave the default "Ads Manager export".
- `--completeness`: pass it only from a real reconcile, never to make the header look better. Run `python3 scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total>` and read its last line:
  - "reconciled against the expected totals" gives `--completeness reconciled` (green "Reconciled").
  - A `WARNING: the pull does not reconcile` line (exit 3) lists the shortfall as a percent: give `--completeness incomplete:<that percent>` (red "Incomplete X%"), or re-pull and reconcile again.
  - "not reconciled: no expected totals were given", or an Ads Manager CSV export (it has no reconcile step), means leave the flag out: the header reads "Not reconciled" in amber.
- `--attribution`: the attribution setting of the pull, if known (header reads "not stated" otherwise).
- `--account account.json`: an account-level pull of `{"reach": N, "frequency": X}` for the same window. Reach and frequency do not add up across ads and days, so without this file those two tiles read "n/a (needs account-level reach)".
- `--prior prior.csv`: the previous equal window, for the change against the prior period on every tile.
- `--csv`: only used to read the currency code from the export's "Amount spent (XXX)" header. If the export does not name one, pass `--currency USD` (or your code); otherwise money reads "account currency".
- `--top-n` (default 8) sets how many ad cards each list shows before the rest collapse. `--pareto-share` (default 80) is the share of purchase value the Pareto cut must reach: a common convention, not a rule, so set it from your own account.

The paths assume the skills are installed side by side. Pass the same grouping and settings to each analysis and tell the user the values used: they are arbitrary defaults.

## Ad previews

Every ad card shows an image: a rendered preview first, then a small thumbnail or video still, then a labelled placeholder that says why there is no image. Fetch them during the run (links to them expire), save each as `<ad_id>.<ext>` and pass the folders with `--previews` and `--thumbs`.

1. Ask the Meta ads connector for the ad's rendered preview (mobile feed) and save the image. Some tools return the image inline rather than as a file: save either form. Use only read tools.
2. For anything it cannot render, save the creative thumbnail or the video still instead.
3. Do not downscale by hand unless a file is over the size cap. Images over `--preview-max-kb` (default 240) are skipped, and embedding stops once `--preview-budget-kb` (default 3600) is used. The footer states how many previews, thumbnails and placeholders there are, the reason for each placeholder, and the total size.

Images are embedded in the page once each, however many panels show that ad. Nothing is hot-linked, so the file keeps working after the links expire.

## Fallback: CSV only

```
python3 scripts/report.py ads.csv --title "Acme" -o report.html
```

Every panel that needs the verdicts says so and how to get them; the numbers, time series, funnel and Pareto panels still fill from the rows.

## What the dashboard holds

Same header, tabs and panels in the same order every run. A panel with no data is a labelled empty state, never dropped.

- **Header:** the Jumbo wordmark, a divider and "by" the Elephant Room logo (light and dark drawings), "<account> creative review", date window, data source, currency, attribution, a completeness badge (Reconciled, Incomplete X%, Not reconciled) and the tab bar.
1. **Overview analysis:** twelve key numbers with change against the prior period and a daily sparkline; performance over time; "Do these first" (top five by spend at stake, each with its preview); "Ways to improve" (ads grouped by their first weak funnel step, with the spend behind each and a link to those ads); funnel.
2. **Pareto:** ads ranked by spend with cumulative share of spend and of purchase value, the cut in words, a concentration gauge, the head gallery and a collapsed long tail.
3. **Keep / kill:** the verdict board (Scale, Keep, Iterate, Check before cutting, Pause, Too early, Can't judge), every Pause card with its check line, fatigue small multiples, an age against CTR-change plot and "All ads" (every ad, grouped, with a subtotal per group).
4. **Format, 5. White space, 6. Briefing:** shown as "not built in this version" empty states for now.
- **Filters and views (need scripts on):** a bar under the tabs with search, five smart views (Money at risk, Ready to scale, Tiring out, Can't judge yet, Biggest spenders) and facet chips for verdict, confidence, format, ad type, concept, market, funnel stage, creator and objective. A facet appears only when it has two or more values and is known for at least 3 in 5 ads (an arbitrary rule). The line under it re-adds spend, purchases, ROAS and CPA for the ads shown (ratios of sums); charts and key numbers stay account-wide. The state lives in the link, so a copied link reopens the same view. With scripts off, every ad shows, grouped by verdict.
- **Ads in detail:** each card opens ("Open this ad", or click the preview) to a large preview, graded metrics in plain words, the ad's own funnel, why it got its verdict, its age and how to improve it. Iterate, Check before cutting and Pause cards also carry a "Make the next version" prompt for the hook-writer and creative-brief skills. The All ads panel can group by verdict, format, concept, ad type, market or creator, sort by spend at stake, spend, ROAS, CPA, CTR, hook rate or age, and switch to a previews-only grid.
- **Footer:** data and method (basis, every default used, reconciliation, missing fields, the matched funnel columns), image counts, "by Elephant Room".

`references/report-design.md` documents the tokens, panel order and how to add a panel.

## Present it

1. Write the file where the user can find it and give the path. Tell them it opens in any browser, prints to PDF, and has no tracking: the only outside request is the font stylesheet, and it falls back to system fonts if blocked. The tabs need a little script; with scripts off every section is shown one after another.
2. Open it and check it yourself: nothing clipped or overlapping, logo visible in light and dark, charts labelled, text readable at phone width and when printed. Do not hand over a report you have not looked at.
3. Say what the report does not cover (missing fields, unclassified names, ads too young) in your reply, not just on the page.

## Guardrails

- Never edit a number, label or formula by hand in the HTML. Metric ids and formulas come from `creative-context/references/metrics.md`; if something reads wrong, fix the inputs and rebuild.
- Surface every `n/a (missing ...)` and never show it as 0 or as healthy.
- Do not add benchmarks, targets or "industry average" lines.
- Anything the report prints from the inputs (ad names, notes) is escaped; keep it that way if you extend the script.
- Never write a URL into the page for an image, and never commit or publish a dashboard built from a real account.
- Read only. Do not touch the ad account.
