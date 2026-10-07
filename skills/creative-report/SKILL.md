---
name: creative-report
description: Turn the analyse skills' outputs (grader, keep-or-kill, mix) into one polished, self-contained HTML report that opens in any browser, prints to PDF and can be shared. Use when the user wants a shareable creative review, a report for a client or team, or asks to "put this in a report". Needs ad performance data; with only an export it builds a smaller report and says which sections are missing.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Creative report

Packages a creative review into one HTML file. It does not analyse on its own terms: it lays out what `creative-grader`, `keep-or-kill` and `creative-mix` found, leads with the answer, and shows every gap in the data instead of hiding it. Everything is graded against the account's own ads, never a benchmark.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** Pull a daily, ad-level report as the analyse skills describe, save the rows unchanged to a JSON file, and use that file wherever a CSV is named below.
2. **CSV export.** An Ads Manager export (`creative-context/references/export-recipe.md`), daily rows if possible.
3. **No data.** There is nothing to report. Say so and offer the export recipe. Do not make a report from guesses.

## Recommended path: all three analyses first

Run each analyse script with `--json`, then build the report from all three:

```
python3 ../creative-grader/scripts/grade.py ads.csv --json > grade.json
python3 ../keep-or-kill/scripts/verdicts.py ads.csv --json > verdicts.json
python3 ../creative-mix/scripts/mix.py ads.csv --json > mix.json
python3 scripts/report.py --grade grade.json --verdicts verdicts.json --mix mix.json \
    --profile creative-profile.md --csv ads.csv --title "Acme creative review" -o report.html
```

`--csv` is only used to read the currency code from the export's "Amount spent (XXX)" header. If the export does not name one, pass `--currency USD` (or your code); otherwise money columns say "account currency".

The paths assume the skills are installed side by side. If only this skill is installed, ask the agent to run the other three skills itself, or use the fallback below. Pass the same grouping and settings to each analysis, and tell the user the values used: they are arbitrary defaults.

## Fallback: CSV only

```
python3 scripts/report.py ads.csv --title "Acme creative review" -o report.html
```

This grades the ads and reads fatigue and spend from the shared metrics module. It cannot give verdicts, the concept by format grid, gaps, or the ad-type split: those sections say which skill's `--json` to add, and the notes list each one. Prefer the recommended path whenever the other skills are available.

## What the report holds

1. **What to do first:** verdict counts and the three actions that matter most.
2. **Basis:** window, grouping, which clicks and conversions columns, defaults used, and that grades are against this account's own baseline.
3. **Keep, kill, iterate, scale:** one row per ad with its reasons. The check to run before any kill is shown with it.
4. **Funnel diagnosis:** the first broken step per ad, plus a hook against hold plot for video.
5. **Creative mix:** spend by format and ad type, the concept by format grid, and gaps.
6. **Notes and missing data:** every `n/a (missing ...)` from the inputs, ads too young to judge, and sections that could not be built.

`references/report-design.md` documents the tokens and section order, for extending the report.

## Present it

1. Write the file where the user can find it and give the path. Tell them it opens in any browser, prints to PDF, and has no tracking: the only outside request is the font stylesheet, and it falls back to system fonts if blocked.
2. Open it and check it yourself: nothing clipped or overlapping, charts labelled, text readable at phone width and when printed. Do not hand over a report you have not looked at.
3. Say what the report does not cover (missing fields, unclassified names, ads too young) in your reply, not just on the page.

## Guardrails

- Never edit a number, label or formula by hand in the HTML. Metric ids and formulas come from `creative-context/references/metrics.md`; if something reads wrong, fix the inputs and rebuild.
- Surface every `n/a (missing ...)` and never show it as 0 or as healthy.
- Do not add benchmarks, targets or "industry average" lines.
- Anything the report prints from the inputs (ad names, notes) is escaped; keep it that way if you extend the script.
- Read only. Do not touch the ad account.
