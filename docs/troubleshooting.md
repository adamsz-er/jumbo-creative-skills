# Troubleshooting

Find the symptom, read the cause, apply the fix. Anything not covered here: ask your agent to rerun with `--debug` (before the subcommand, for `review.py`) and read the last line it prints.

## Install and setup

| Symptom | Cause | Fix |
|---|---|---|
| The skill does not trigger when you ask | The skills are not installed in this agent, or the session started before the install | Check the install table in the [README](../README.md#install). In Claude Code run `/reload-plugins` or start a new session. Then name the skill outright ("use creative-review") or say "review my Meta ads" |
| Plugin not showing after install | The plugin list is cached in the running session | Run `/reload-plugins`, or start a new session. If it still does not show, run `claude plugin marketplace add adamsz-er/jumbo-creative-skills` and `claude plugin install jumbo-creative@jumbo-creative-skills` again |
| `npx skills` says command not found | `npx` comes with Node.js, which is not installed or not on your path | Install Node.js from nodejs.org, open a new terminal and run `npx skills add adamsz-er/jumbo-creative-skills` again. Or install through the Claude Code plugin commands instead |
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

These are the failures `creative-review` stops on. Each prints a plain message and its fix, and exits with its own code.

| Symptom | Cause | Fix |
|---|---|---|
| E-NODATA: There is no ad data to review yet. | No data file and no connector | Pick one: (1) add --demo to see a sample account first; (2) connect Meta's ads connector and say 'review my Meta ads'; (3) export your ads as a daily CSV (the export recipe, steps 1 to 4: Ads tab, add the columns, Breakdown > By time > Day, Export as CSV), then pass the file |
| E-COLUMNS: the file is missing a column the review needs. | The CSV lacks a date, ad name, amount spent or impressions column | Re-export with the columns it names (each is added in Customize columns or Breakdown > By time > Day, steps 2 and 3 of the export recipe), or pass the file again once they are in |
| E-EMPTY: There are no ad rows to review in the window. | The date range does not overlap the file, or a `--where` filter kept nothing | Re-export with a date range that overlaps your window (step 1 of the export recipe), or drop --from and --to. For a filter, check the field and value against your data, or drop --where |
| E-RECONCILE: The pull is incomplete. | The connector pull is short against the account totals | Re-run the pull with pagination so every ad is fetched (including archived ads that delivered in the window); see data-inputs.md steps 3 to 7. Then run the pull again |
| E-CURRENCY: The data does not say which currency the money is in. | The spend header has no currency code | Pass --currency followed by your three-letter code (for example --currency USD), or add 'currency: USD' to the Script settings of your creative-profile.md |
| E-SKILL: A skill is not installed next to creative-review. | Only some of the skills were installed | Install the whole package: claude plugin install jumbo-creative@jumbo-creative-skills (or npx skills add adamsz-er/jumbo-creative-skills) |
| E-PROFILE: The profile could not be read. | A line in `creative-profile.md` is malformed | Fix the line named in the message, or pass a different --profile |
| E-TARGET: A `--target` value is not valid. | Targets were not written as metric=number | Write targets as metric=number, for example --target cpa=40,roas=3. The message lists the accepted metrics |
| E-REPORT: The dashboard did not pass its own structure check. | The built page is missing a part | Run the review again; if it repeats, rerun with --debug and report the line above |
| E-ANALYSIS: An analysis step stopped. | One step (grade, verdicts, mix or report) hit an error | Fix what the line says and run the review again. Everything before this step is kept in the run folder it names |

## Using the output

| Symptom | Cause | Fix |
|---|---|---|
| `colour-grade` says it needs Pillow | The image is not a PNG, and reading JPEG, WebP and other formats needs the optional Pillow library | Run `pip install pillow`, or export the image as PNG and run it again. PNG works without Pillow |
| Report fonts look different when offline | The page loads its typeface from Google Fonts, and falls back to a system font if it cannot | Nothing is wrong. Open the report with a connection to see the intended fonts |
| The report shows placeholders instead of ad images | The connector returns links, not image files | Save screenshots as `<ad_id>.png` in a folder and rebuild with `--previews <folder>` |
| A tile says "Totals not checked" | No reconcile was run (a CSV export has none) | Pull the account totals for the same window and pass `--expect-spend` and `--expect-impressions` to the pull, then `--completeness reconciled` only if it reconciled |
