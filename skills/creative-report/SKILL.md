---
name: creative-report
description: Build one fixed, branded creative dashboard (overview, Pareto, keep and kill, with ad previews) as a self-contained HTML file that opens in any browser, prints to PDF and can be shared. Use when the user wants a shareable creative review, a dashboard or report for a client or team, or asks to "put this in a report". Needs ad performance data; any panel without its data shows why and how to get it.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Creative report

Packages a creative review into one branded HTML dashboard. It does not analyse on its own terms: it lays out the daily data and what `keep-or-kill` (and optionally `creative-grader` and `creative-mix`) found, leads with the answer, and shows every gap in the data instead of hiding it. Everything is graded against the account's own ads. Public industry figures appear only as cited context beside a chart, never as a grade.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** Call read-only tools only: never one that activates, updates or changes anything. Pull a daily, ad-level report as the analyse skills describe. Follow the numbered steps in `creative-context/references/data-inputs.md`: field catalogue first, every response saved to a JSON file, then `python3 -I scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total> --expect-ads ids.txt` (list archived ads that delivered in the window too, step 3 there) and use `ads.csv` wherever a CSV is named below. A `WARNING` line or exit 3 means the pull does not reconcile: re-fetch or drop duplicates the missing ads and run it again before you analyse. 3-second plays are derived per ad and shown as "(derived)"; say so when you quote a hook rate. When the connector's cost per 3-second view is too coarsely rounded they are not derived, and hook and hold rate are n/a: say why and point to an Ads Manager export for them. Read the adapter's connector notes and "fields no row carries" line before you analyse.
2. **CSV export.** An Ads Manager export (`creative-context/references/export-recipe.md`), daily rows if possible.
3. **No data.** There is nothing to report. Say so and offer the export recipe. Do not make a report from guesses.

## Recommended path: verdicts first, then the dashboard

Run keep-or-kill with `--json` (and, for the footer's grading basis and missing-data notes, creative-grader and creative-mix), then build the dashboard from the same daily data:

```
# add --completeness only as described below; this example pull was reconciled
# --profile carries the key map, type map, targets and currency; --where keeps one scope (drop it for the whole account)
python3 -I ../keep-or-kill/scripts/verdicts.py ads.csv --profile creative-profile.md --where market=US --json > verdicts.json
python3 -I ../creative-grader/scripts/grade.py ads.csv --profile creative-profile.md --where market=US --json > grade.json
python3 -I ../creative-mix/scripts/mix.py ads.csv --profile creative-profile.md --where market=US --json > mix.json
python3 -I scripts/report.py ads.csv --verdicts verdicts.json --grade grade.json --mix mix.json \
    --profile creative-profile.md --where market=US --source "Meta ads connector" --completeness reconciled \
    --previews previews/ --thumbs thumbs/ -o report.html
python3 -I scripts/report.py --check report.html
```

Two optional files fill more of tabs 5 and 6: `--breakdowns breakdowns.csv` (a second Ads Manager export broken down by age, gender, placement, platform, region or country) and `--briefs briefs.json` (briefs you wrote with the creative-brief and hook-writer skills).

- `--where`: the same filter you gave the analyses, so the page and the verdicts cover the same ads. The scope it keeps is shown in the title, the header and the footer. `--scope "market US"` sets that wording yourself.
- `--title`: the account label in the title; it wins over the brand in `--profile`, so a scoped or renamed report says what it is.
- `--key-map` and `--type-map`: the same naming settings as the analyses (or let `--profile` supply them), so the report's facets read creator, tone and type the same way.
- `--source`: "Meta ads connector" for a connector pull, else leave the default "Ads Manager export".
- `--completeness`: pass it only from a real reconcile, never to make the header look better. Run `python3 -I scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total> --expect-ads ids.txt` (list archived ads that delivered in the window too, step 3 there) and read its last line:
  - "reconciled against the expected totals" gives `--completeness reconciled` (green "Reconciled").
  - A `WARNING: the pull does not reconcile` line (exit 3) lists the shortfall as a percent: give `--completeness incomplete:<that percent>` (amber "Totals don't match (X% short)"), or re-pull and reconcile again.
  - "not reconciled: no expected totals were given", or an Ads Manager CSV export (it has no reconcile step), means leave the flag out: the header reads "Totals not checked" in neutral grey, with a tip to pull the account totals for the same window. Never pass `reconciled` to make a showcase look better: the committed Acme example leaves it out on purpose.
- `--attribution`: the attribution setting of the pull, if known (header reads "not stated" otherwise). The connector does not return the setting it used, so on a connector pull pass what you asked for, or "account default (not stated by connector)"; never imply it was checked.
- `--account account.json`: an account-level pull of `{"reach": N, "frequency": X}` for the same window. Reach and frequency do not add up across ads and days, so without this file those two tiles read "n/a" and one note at the top of Overview says why. For a one-market page, a whole-account figure is the wrong number: see "Reach and frequency for one scope" in `creative-context/references/data-inputs.md`.
- `--prior prior.csv`: the previous equal window, for the change against the prior period on every tile. A full daily pull roughly doubles the connector work, so say so and ask; one ad-level totals row per ad for the previous window (no time increment) is enough for the tiles. `--where` filters it the same way.
- `--csv`: only used to read the currency code from the export's "Amount spent (XXX)" header. If the export does not name one, pass `--currency USD` (or your code); otherwise money reads "account currency".
- `--top-n` (default 8) sets how many ad cards each list shows before the rest collapse, and how many ads the All ads gallery shows as cards before the rest become a compact list. `--pareto-share` (default 80) is the share of purchase value the Pareto cut must reach: a common convention, not a rule, so set it from your own account.
- `--pareto-share`, `--top-n`, `--account`, `--breakdowns`, `--briefs`, `--verdicts`, `--grade` and `--mix` are the flags the page itself points to in plain words ("add it when you rebuild this report"). The page never prints a command flag: this file is where readers of the page, and you, find them. `creative-mix` takes its own `--min-proven-spend`, `--pattern` and `--key-map`.

The paths assume the skills are installed side by side. Pass the same grouping and settings to each analysis and tell the user the values used: they are arbitrary defaults.

## Ad previews

Every ad card shows an image: a rendered preview first, then a small thumbnail or video still, then a labelled placeholder that says why there is no image. Fetch them during the run (links to them expire), save each as `<ad_id>.<ext>` and pass the folders with `--previews` and `--thumbs`.

1. Ask the Meta ads connector for the ad's rendered preview (mobile feed) and save the image. Some tools return the image inline rather than as a file: save either form. Use only read tools.
2. For anything it cannot render, save the creative thumbnail or the video still instead.
3. If neither gives a usable image, say so and offer the user a manual route: they save screenshots of the ads they care about as `<ad_id>.png` in a folder you pass with `--previews`. As of this writing the hosted Meta connector returns preview links and one-time screenshot tokens for its own app rather than an image file, and creative thumbnails are 64×64 crops, so in connector mode most cards show a labelled placeholder (check in your own session).
4. Do not downscale by hand unless a file is over the size cap. Images over `--preview-max-kb` (default 240) are skipped, and embedding stops once `--preview-budget-kb` (default 3600) is used. The footer states how many previews, thumbnails and placeholders there are, the reason for each placeholder, and the total size.

Images are embedded in the page once each, however many panels show that ad. Nothing is hot-linked, so the file keeps working after the links expire. When some ads have no image, "Previews for N of M ads" sits under the scope bar. The Acme example ships with invented mock previews (`python3 tests/fixtures/make_previews.py` rewrites them, then rebuild the example with `--previews examples/acme/previews`).

## Fallback: CSV only

```
python3 -I scripts/report.py ads.csv --title "Acme" -o report.html
```

Every panel that needs the verdicts says so and how to get them; the numbers, time series, funnel and Pareto panels still fill from the rows.

## What the dashboard holds

Same header, tabs and panels in the same order every run. A panel with no data is a labelled empty state, never dropped.

- **Frame:** a top bar with the Jumbo wordmark, a divider and "by" the Elephant Room logo (light and dark drawings), "<account> · <scope> creative review", the completeness badge (Reconciled, Totals don't match, Totals not checked) and a light/dark toggle (scripts on). Under it a dark scope bar reads the window, currency, source and attribution. The six tabs sit in a sticky left sub-nav with an icon each (a segmented control under 1024 px). Light is the default; dark follows the system unless the toggle has set it.
1. **Overview analysis:** a "Not in this pull" note at the top naming each key number no ad can show, why and how to get it (reach and frequency too, without an account-level figure; the tiles read a plain n/a), then twelve key numbers with a change pill against the prior period and a daily sparkline with a faint 7-day average and a hover for each day; performance over time (a switcher between spend, ROAS, CPA, CTR, CPM and hook rate, each a daily line with a 7-day average over faint spend bars); where the money went, by format (a 100% stacked area of daily spend share); "Do these first" (top five by spend at stake, each with its preview); "Ways to improve" (ads grouped by their first weak funnel step, with the spend behind each and a link to those ads); funnel.
2. **Pareto:** ads ranked by spend with cumulative share of spend and of purchase value, the cut in words, a concentration gauge, the head gallery and a collapsed long tail.
3. **Keep / kill:** the verdict board (Scale, Keep, Iterate, Check before cutting, Pause, Too early, Can't judge), every Pause card with its check line, fatigue small multiples, an age against CTR-change plot, performance by ad age (spend share per age bucket with ROAS or CTR on a second axis), new ads launched per week by format and "All ads" (every ad, grouped, with a subtotal per group).
4. **Format:** a scorecard with one row per format (ads, spend share, CTR, CPM, CPA, ROAS, hook and hold rate for video) graded in plain words against your other formats (only with 3 or more formats; ties are marked) and a strip of its top ads; format benchmarks (a switcher between CTR, CPM, ROAS, CR and hook rate: a dot per format for your value, a line at your median across formats and, only where a cited public source gives one for that format and measures it the same way, a shaded industry band with its source under the chart; hold rate has no band because the public definition differs); formats over time (small charts of CTR, CPM, ROAS and hook rate by week, one line per format and a dashed all-formats line); spend share against return (a bubble per format); a hook-against-hold bubble chart with four named quadrants; a retention chart of raw counts of people still watching at 3 seconds and each quartile, plus average watch time; and one table per ad type, never blended, with the format mix inside it.
5. **White space:** a concept-by-format heatmap (shade is spend, the number is ads, empty cells are hatched, gaps are outlined and numbered); a funnel-stage heatmap when names carry a stage; ad types with no creative; markets (thin coverage flagged) and, from `--breakdowns`, age, gender or placement segments; and the numbered gap list with a plain "why test this" for each.
6. **Briefing:** finished briefs from `--briefs` (a missing key reads "not stated", an unknown metric id is flagged), or up to five brief starters (top gaps and top Iterate ads, at most two in any one format, each with the concept's best ads from other formats and the format's best ad as references) that never invent a hook; the call-to-action table and opening lines when the data carries ad copy; and three copy buttons (creative-ideation, hook-writer, creative-brief) whose prompts hold names only, no figures.
- **Filters and views (need scripts on):** one sticky row above the content with search, a "Filters (n)" button, Clear (only when a filter is on), "N of M ads", and group, sort and previews-only controls for the All ads gallery. The button opens the five smart views (Money at risk, Ready to scale, Tiring out, Can't judge yet, Biggest spenders) and facet chips for verdict, confidence, format, ad type, concept, market, funnel stage, creator and objective. A facet appears only when it has two or more values and is known for at least 3 in 5 ads (an arbitrary rule). The line under the row re-adds spend, purchases, ROAS and CPA for the ads shown (ratios of sums over every ad shown; an ad with no recorded purchases counts as none, so the line matches the key numbers when nothing is filtered, and it adds "value recorded on k of n ads" when only some ads carry it); charts and key numbers stay account-wide. The state lives in the link, so a copied link reopens the same view. With scripts off, every ad shows, grouped by verdict.
- **Ad cards:** one card everywhere an ad appears: a 3:4 preview with its format and a tinted verdict chip (hover for what the verdict means), a label that tells the ad apart from its lookalikes (the raw ad name is on hover), spend, ROAS, CPA, CTR and hook rate or CPM as pills tinted by where the ad ranks on the page, and a green, amber or red edge for Scale, Iterate or tiring, and Pause. The All ads panel switches between a grid of cards and a table.
- **Ads in detail:** each card opens ("Open this ad", or click the preview) to a dialog with a large preview beside the ad's numbers, graded metrics in plain words, the ad's own funnel, why it got its verdict, its age and how to improve it. Every judged card says how many similar ads it was compared with, and flags a small group. Iterate, Check before cutting and Pause cards also carry a "Make the next version" prompt for the hook-writer and creative-brief skills. The All ads panel can group by verdict, format, concept, ad type, market or creator, sort by spend at stake, spend, ROAS, CPA, CTR, hook rate or age, and switch to a previews-only grid.
- **Footer:** data and method (basis, every default used, reconciliation, missing fields, the matched funnel columns), image counts, "by Elephant Room".

`references/report-design.md` documents the tokens, panel order and how to add a panel.

## Present it

1. Write the file where the user can find it and give the path. Tell them it opens in any browser, prints to PDF, and has no tracking: the only outside request is the font stylesheet, and it falls back to system fonts if blocked. The tabs need a little script; with scripts off every section is shown one after another.
2. Run `python3 -I scripts/report.py --check report.html` and fix anything it names. It checks every tab and panel is present in order with a known state, the completeness badge and the Scope line, that the only outside request is the font stylesheet, that no script loads from a file, that no missing value reads as 0, and the file size. It is a floor, not a visual check.
3. Then open it and look: nothing clipped or overlapping, logo visible in light and dark, charts labelled, text readable at phone width and when printed. Do not hand over a report you have not looked at. If no browser you are allowed to use is available, say so plainly, give the `--check` result, and ask the user to look.
4. Say what the report does not cover (missing fields, unclassified names, ads too young, the scope) in your reply, not just on the page.

## Guardrails

- Never edit a number, label or formula by hand in the HTML. Metric ids and formulas come from `creative-context/references/metrics.md`; if something reads wrong, fix the inputs and rebuild.
- Surface every `n/a (missing ...)` and never show it as 0 or as healthy.
- Do not add targets, and do not add an industry figure unless it is in `references/benchmarks.json` with its source, URL, year and sample. A figure is context, never a grade: it must not change a verdict, a grade or the order of "Do these first". Money figures show only when the report currency matches the source's. Each entry says how its definition compares with ours: `matches` (band drawn), `not_stated` (the source does not say, for example link or all clicks: band drawn with that caveat printed under it) or `differs` (no band, as for hold rate).
- Anything the report prints from the inputs (ad names, notes) is escaped; keep it that way if you extend the script.
- Never write a URL into the page for an image, and never commit or publish a dashboard built from a real account.
- Read only. Do not touch the ad account.

## How to use

Have ready: the daily data, and ideally the grade, verdict and mix JSON from the analyse skills (creative-review does all of it).

Try:

- "Put this review in a report I can share."
- "Rebuild the report for my US ads."
- "Add last month for comparison."

## Common questions

- **How do I share it?** Send `report.html`; print to PDF from a browser.
- **Why Totals not checked?** No reconcile ran; pass `--completeness` only from a real one.
- **Why placeholders instead of images?** The connector returns links; pass `--previews` with `<ad_id>.png` files.
- **Can I edit a number?** No; fix the inputs and rebuild.
- More: creative-context/references/faq.md
