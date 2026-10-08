# Troubleshooting

Find the symptom, read the cause, apply the fix. Anything not covered here: ask your agent to rerun with `--debug` (before the subcommand, for `review.py`) and read the last line it prints.

## Install and setup

| Symptom | Cause | Fix |
|---|---|---|
| The skill does not trigger when you ask | The skills are not installed in this agent, or the session started before the install | Check the install table in the [README](../README.md#install). In Claude Code, start a new session. Then name the skill outright ("use creative-review") or say "review my Meta ads" |
| Plugin not showing after install | The plugin list is cached in the running session | Start a new Claude Code session. If it still does not show, run `claude plugin marketplace add adamsz-er/jumbo-creative-skills` and `claude plugin install jumbo-creative@jumbo-creative-skills` again |
| `npx skills` says command not found | `npx` comes with Node.js, which is not installed or not on your path | Install Node.js from nodejs.org, open a new terminal and run the install command from the README again. Or install through the Claude Code plugin commands instead |
| A zip is rejected when you upload it to claude.ai or Claude desktop | The upload needs the skill folder at the top of the zip, a `SKILL.md` with `name` matching the folder (lowercase letters, digits and single hyphens) and a `description`, and code execution turned on | Rebuild with `python3 tools/build_zips.py`, which validates every skill first, or download the zips from the latest Release. Turn on code execution in settings, then upload again |

## Getting your data in

| Symptom | Cause | Fix |
|---|---|---|
| The Meta MCP asks you to authenticate | The connector is added but not signed in | Sign in with Meta through OAuth. In Claude Code, run `/mcp` and authenticate `meta-ads`. If the connector says ads MCP is not enabled for the account, use a CSV export instead |
| The MCP returns no video fields, or hook and hold rate read n/a | 3-second plays exist only at ad set level and above, and the cost per 3-second view is too coarsely rounded to derive them safely | Export from Ads Manager with the 3-second video plays and ThruPlays columns ([recipe](../skills/creative-context/references/export-recipe.md)). The other metrics are unaffected |
| Totals do not match Ads Manager | The pull is short (often archived ads that delivered in the window), or the date range, attribution setting or currency differs | Check the line `from_mcp.py` or `review.py pull` printed: "reconciled", or a shortfall in percent. List archived ads too, re-pull missing ads in smaller batches, and compare like for like: same dates, same attribution setting |
| CSV columns are not recognised | Meta renamed a column, or the export is not daily and ad-level | Column names are matched loosely and case-insensitively; the accepted headers are listed in [data-inputs.md](../skills/creative-context/references/data-inputs.md) (the "Canonical field" table, mode 2). Rename the header to the closest typical one, or follow the export recipe again |
| Every ad is "not graded (low volume)" | No ad reaches the minimum number of impressions (`--min-impressions`), or the window is too short | Widen the date range. If your ads are small, lower `--min-impressions` from your own spend per ad. It is an arbitrary default, not a rule |
| Every ad is "unclassified" in creative-mix | The ad names do not match a convention the detector knows, so concept and ad type cannot be read | Run `python3 -I skills/creative-context/scripts/detect_naming.py ads.csv` on all names, then pass `--key-map` and `--type-map` (or save them in the profile's `Script settings`) and rerun |

## Known failures and their exact fixes

These are the failures `creative-review` stops on. Each message and fix below is quoted from the program, with the example values it fills in (a file name, a number of columns, a percent). Each prints with its own exit code.

| Symptom | Cause | Fix |
|---|---|---|
| E-NODATA There is no ad data to review yet. | No data file and no connector | Pick one: (1) add --demo to see a sample account first; (2) connect Meta's ads connector and say 'review my Meta ads'; (3) export your ads as a daily CSV: creative-context/references/export-recipe.md steps 1 to 4 (Ads tab, add the columns, Breakdown > By time > Day, Export as CSV), then pass the file. |
| E-COLUMNS ads.csv is missing 2 columns the review needs: date, impressions. | The CSV lacks a column the review needs (date, ad name, amount spent or impressions) | Set Breakdown to By time > Day (step 3 of creative-context/references/export-recipe.md). Add Impressions in Customize columns (step 2 of creative-context/references/export-recipe.md). Re-export with those columns, or pass the file again once they are in. |
| E-EMPTY There are no ad rows to review in 2026-03-01 to 2026-03-30. The file covers 2026-04-01 to 2026-04-28. | The date range does not overlap the file, or a `--where` filter kept nothing | Re-export with a date range that overlaps your window (step 1 of creative-context/references/export-recipe.md), or drop --from and --to. |
| E-EMPTY Your filter market=ZZ kept no ads. | The date range does not overlap the file, or a `--where` filter kept nothing | Check the field and value against your data, or drop --where. |
| E-RECONCILE The pull is incomplete: spend is 3.2% short. | The connector pull is short against the account totals | Re-run the pull with pagination so every ad is fetched (including archived ads that delivered in the window); see creative-context/references/data-inputs.md steps 3 to 7. Then run the pull again. |
| E-CURRENCY The data does not say which currency the money is in. | The spend header has no currency code, or a hand-written profile's currency is only read from its Script settings block | Pass --currency followed by your three-letter code (for example --currency USD), or add 'currency: USD' to the Script settings of your creative-profile.md. |
| E-MIXED-CURRENCY The pull mixes currencies: EUR, USD. | The saved responses state more than one currency code for spend | Pull each currency separately (one ad account per pull), then run the pull and the review on each file on its own. |
| E-SKILL The skill 'creative-mix' is not installed next to creative-review, and the review needs it. | Only some of the skills were installed | Install the whole package: claude plugin install jumbo-creative@jumbo-creative-skills (or npx skills add adamsz-er/jumbo-creative-skills). |
| E-PROFILE The profile creative-profile.md could not be read: line 4 is not key: value. | A line in `creative-profile.md` is malformed | Fix the line named above in creative-profile.md, or pass a different --profile. |
| E-TARGET cpa=high is not a number | A `--target` value was not written as metric=number | Write targets as metric=number, for example --target cpa=40,roas=3. Accepted metrics: cpa, roas, cpc. |
| E-REPORT The dashboard was written but did not pass its own structure check: no tabs found. | The built dashboard is missing a part | Run the review again; if it repeats, rerun with --debug and report the line above. |
| E-ANALYSIS The grade step stopped: no rows. | One step (grade, verdicts, mix or report) hit an error | Fix what that line says and run the review again. Everything before this step is kept in creative-review-runs/acme/latest. |

## Using the output

| Symptom | Cause | Fix |
|---|---|---|
| `colour-grade` says it needs Pillow | The image is not a PNG, and reading JPEG, WebP and other formats needs the optional Pillow library | Run `pip install pillow`, or export the image as PNG and run it again. PNG works without Pillow |
| Report fonts look different when offline | The page loads its typeface from Google Fonts, and falls back to a system font if it cannot | Nothing is wrong. Open the report with a connection to see the intended fonts |
| The report shows placeholders instead of ad images | The connector returns links, not image files | Save screenshots as `<ad_id>.png` in a folder and rebuild with `--previews <folder>` |
| A tile says "Totals not checked" | No reconcile was run (a CSV export has none) | Pull the account totals for the same window and pass `--expect-spend` and `--expect-impressions` to the pull, then `--completeness reconciled` only if it reconciled |
