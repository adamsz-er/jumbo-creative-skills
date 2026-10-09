# How it works

This page explains each moving part in more depth than the [README](../README.md). You do not need it to use the skills; it is here for when you want to know why a number came out the way it did, or which setting to change.

## The three data modes

Every skill starts by working out which mode it is in and says so out loud. It never claims more than the mode supports.

| Mode | What you give it | What works | What degrades |
|---|---|---|---|
| **Connector** | Meta's Ads MCP, connected in your agent | Everything the pull returns: spend, impressions, clicks, purchases, ThruPlays, creation dates | 3-second plays are not returned per ad, so hook and hold rate are derived from the cost per 3-second view (labelled "(derived)") and refused when that cost is rounded too coarsely. Long pulls can stop short, so totals are reconciled. Ad previews are links, not images |
| **CSV or screenshots** | A daily Ads Manager export ([recipe](../skills/creative-context/references/export-recipe.md)), or screenshots of the table | Every metric, with 3-second plays as Meta reports them. Screenshots are read by hand and may contain transcription errors, which the agent says | Without daily rows there is no fatigue trend or ad age. Without the objective column every ad is judged as a sales ad, and the output says so |
| **No data** | Nothing | Ideation, hooks, personas, briefs, script breakdown, colour direction | Every grade, ranking and recommendation is labelled "no performance data" |

These skills never call a tool that changes your ad account. Your agent could, if you asked it to directly, through the Meta connector's own tools.

## The shared metrics module

Every metric id and formula is defined once, in [metrics.md](../skills/creative-context/references/metrics.md), and implemented once, in `shared/creative_metrics.py`. A skill installed on its own (from a zip, or with `npx skills add --skill`) must still run, so each skill that does arithmetic carries a synced copy of that file (and of `from_mcp.py`) in its own `scripts/` folder. `python3 tools/sync_shared.py` copies `shared/` into the skills, and `--check` fails if any copy has drifted; CI runs it.

Rules the module enforces:

- A missing field or a zero denominator is `n/a (missing <field>)`, never 0.
- Hook rate and thumb-stop rate are the same number; the skills use hook rate.
- Hold rate is ThruPlay-based. If ThruPlays or 3-second plays are missing, it is n/a.
- CTR says whether it used link clicks or all clicks.
- Scripts run under `python3 -I` (isolated mode), import only their own folder and make no network calls.

## How grading works: your own quartiles

There are no "good" values in this package. An ad is compared with other ads in the same account:

1. Take the ads of the same format and ad type (and the same campaign objective) with enough impressions to judge. This is the comparison group.
2. For each metric, find the group's quartiles: p25 (a quarter of ads are at or below it), the median, and p75 (a quarter of ads are at or above it). For cost metrics the bands are inverted, so a cheap CPM is top.
3. Place the ad: at or above p75 is the top quartile, at or below p25 is the bottom quartile, between is the middle.
4. Read the funnel in order and name the first broken step: cost of reach, hook, hold, click, post-click, payback.

A group needs at least 5 comparable ads to stand on its own. A smaller group widens to the next one (format, then the whole objective), and the output says which group each ad was graded in. A group with fewer than twice the minimum is flagged as an early read.

**Worked example (Acme Outdoor Co., made-up data).** Six UGC video ads in the UGC video / BAU (evergreen) group have these hold-rate quartiles: p25 29.7%, median 33.4%, p75 34.1%. One of them holds 28.4%. That is at or below p25, so its hold rate is in the bottom quartile of its own group. Run `python3 -I skills/creative-grader/scripts/grade.py examples/acme/ads_daily.csv` to see the same table, or read [examples/acme/grade.md](../examples/acme/grade.md). Because the group has six ads, fewer than twice the minimum of five, the output marks the grade as an early read.

Verdicts (`keep-or-kill`) use the same comparison, plus age, a learning flag and a fatigue trend (the first and last few delivery days of an ad compared). The rules are in [verdict-rules.md](../skills/keep-or-kill/references/verdict-rules.md). Two protections matter: an ad that cannot be judged is never told to iterate or pause, and the account's biggest sellers are never paused without a check. A never-worked ad is paused only when it misses a target you set; with no target it reads "Check before cutting" and asks for one.

## Defaults and the flags that change them

Every default below is arbitrary. None is a rule or a benchmark, and none is right for every account. Set each one from your own account: for example, pick the minimum impressions from your own spend per ad, and the fatigue window from how fast your own ads tire. The scripts print the settings they used on every run.

You do not have to pass the same flags to every script. Put your confirmed answers (key map, type map, targets, currency) in the `Script settings` block of `creative-profile.md` and pass `--profile creative-profile.md`; a flag on the command line still wins.

Scripts live in `skills/<skill>/scripts/`. `creative_metrics.py` and `from_mcp.py` are the synced shared modules, so each is listed once. `review.py` has two subcommands, `pull` and `run`.

| Script | Flag | Default | What it does |
|---|---|---|---|
| `beats.py` | `--json` | off | print machine-readable JSON instead of text |
| `beats.py` | `--product` | empty | product name, so the script can check it is named early |
| `creative_metrics.py` | `--json` | off | print machine-readable JSON instead of text |
| `creative_metrics.py` | `--profile` | none | profile whose Script settings fill any flag left unset (shared by grade, verdicts, mix, evidence, detect_naming) |
| `creative_metrics.py` | `--type-map` | none | the account's own ad-type words, e.g. `core=bau,drop=launch` |
| `creative_metrics.py` | `--where` | none (all ads) | keep only rows where a column or name field matches, e.g. `market=US`; repeat the flag or use commas for more values |
| `detect_naming.py` | `--json` | off | print machine-readable JSON instead of text |
| `detect_naming.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `detect_naming.py` | `--min-match-rate` | 85.0 | ask the user to confirm the convention only below this percent of names read |
| `detect_naming.py` | `--profile` | `./creative-profile.md` for `review.py run`, else none | read the Script settings block of the profile (key map, type map, targets, currency); a flag on the command line still wins |
| `detect_naming.py` | `--type-map` | none | the account's own ad-type words, e.g. `core=bau,drop=launch` |
| `evidence.py` | `--include-types` | `bau` | ad types whose top-quartile concepts seed coverage gaps (add `promo` or `launch` when briefing a sale or a drop) |
| `evidence.py` | `--json` | off | print machine-readable JSON instead of text |
| `evidence.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `evidence.py` | `--max-gaps` | 8 | coverage gaps shown |
| `evidence.py` | `--min-change` | 8.0 | percent move that counts as real for CTR, frequency and hook rate |
| `evidence.py` | `--min-impressions` | 1000 | ads below this are not judged |
| `evidence.py` | `--window` | 6 | days compared at the start and end of an ad's life when looking for fatigue |
| `from_mcp.py` | `--expect-ads` | none | text file with one expected ad id per line, to catch ads missing from the pull |
| `from_mcp.py` | `--expect-impressions` | none | account-level impressions for the same window, to reconcile the pull |
| `from_mcp.py` | `--expect-spend` | none | account-level spend for the same window, to reconcile the pull |
| `from_mcp.py` | `--level` | `ad` | level of the rows; `id` and `name` read as ad id and name only for ad rows |
| `from_mcp.py` | `--output` | required | CSV to write (also `-o`) |
| `from_mcp.py` | `--tolerance` | 0.5 | percent of the expected total a pull may fall short before it counts as incomplete |
| `grade.py` | `--group-by` | `format,ad_type` | columns to compare ads within, narrowest first; a group with fewer than 5 comparable ads widens to the next |
| `grade.py` | `--json` | off | print machine-readable JSON instead of text |
| `grade.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `grade.py` | `--min-impressions` | 1000 | ads below this are not judged |
| `mix.py` | `--group-by` | none | also show a table by these columns: a name field or any column, e.g. `market` or `format,market` |
| `mix.py` | `--json` | off | print machine-readable JSON instead of text |
| `mix.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `mix.py` | `--min-proven-spend` | 3 times the account's median ad spend | BAU spend a concept or format needs before it counts as proven for gap ranking |
| `mix.py` | `--no-family` | off | do not group `-suffix` variants of a concept into one family |
| `mix.py` | `--pattern` | `concept,format,creator,ad_type,product,tone,launch_date` | naming-convention fields, in order, for positional names |
| `palette.py` | `--json` | off | print machine-readable JSON instead of text |
| `palette.py` | `--k` | 6 | how many colours to report |
| `profile_draft.py` | `--currency` | read from the export's spend header | three-letter currency code for money |
| `profile_draft.py` | `--force` | off | overwrite the `--output` file if it already exists |
| `profile_draft.py` | `--name` | none | the brand name, if you know it |
| `profile_draft.py` | `--output` | print to screen | write the draft profile here (also `-o`) |
| `report.py` | `--account` | none | JSON file with account-level `reach` and `frequency` for the same scope |
| `report.py` | `--attribution` | not stated | attribution setting shown in the header |
| `report.py` | `--breakdowns` | none | a second Ads Manager export with age, gender, placement or region columns, for the segment tables |
| `report.py` | `--briefs` | none | JSON list of briefs written with creative-brief and hook-writer |
| `report.py` | `--changes` | none | `changes.json` from creative-review: adds "What changed since last time" |
| `report.py` | `--check` | none | check a built dashboard's structure and exit (no browser needed) |
| `report.py` | `--check-dashboard` | none | check a Claude dashboard bundle offline and exit |
| `report.py` | `--claude-dashboard` | none | also write the report as a native Claude dashboard bundle into this folder; the HTML is written as usual |
| `report.py` | `--completeness` | absent: Totals not checked | `reconciled` or `incomplete:<percent>`, only from a real reconcile |
| `report.py` | `--csv` | none | the CSV behind the JSON files, only to read the currency from its spend header |
| `report.py` | `--currency` | read from the export's spend header | three-letter currency code for money |
| `report.py` | `--grade` | none | creative-grader `--json` output |
| `report.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `report.py` | `--mix` | none | creative-mix `--json` output |
| `report.py` | `--output` | `report.html` | where to write the HTML (also `-o`) |
| `report.py` | `--pareto-share` | 80 | percent of purchase value the Pareto cut must reach; a common convention, not a rule |
| `report.py` | `--preview-budget-kb` | 3600 | stop embedding preview images past this total size |
| `report.py` | `--preview-max-kb` | 240 | skip a preview image larger than this |
| `report.py` | `--previews` | none | folder of rendered ad previews named `<ad_id>.<ext>` |
| `report.py` | `--prior` | none | CSV or JSON of the previous equal window, for change against the prior period |
| `report.py` | `--profile` | `./creative-profile.md` for `review.py run`, else none | read the Script settings block of the profile (key map, type map, targets, currency); a flag on the command line still wins |
| `report.py` | `--scope` | read from `--where` | what the data covers, shown in the title and header |
| `report.py` | `--source` | `Ads Manager export` | data source shown in the header (`Meta ads connector` for a pull) |
| `report.py` | `--thumbs` | none | folder of small thumbnails or video stills named `<ad_id>.<ext>` |
| `report.py` | `--title` | brand from the profile | account label for the title; wins over the profile |
| `report.py` | `--top-n` | 8 | ad cards shown per list before the rest collapse |
| `report.py` | `--verdicts` | none | keep-or-kill `--json` output |
| `review.py` | `--account` | none | JSON file with account-level `reach` and `frequency` (and optionally `name`) |
| `review.py` | `--attribution` | not stated | attribution setting shown in the header |
| `review.py` | `--cache-dir` | `creative-review-runs` | where run folders are kept |
| `review.py` | `--completeness` | absent: Totals not checked | `reconciled` or `incomplete:<percent>`, the word `pull` printed |
| `review.py` | `--currency` | read from the export or the profile | three-letter currency code |
| `review.py` | `--debug` | off | show the full traceback for an unexpected error (goes before the subcommand) |
| `review.py` | `--demo` | off | review the built-in Acme sample account; needs no data |
| `review.py` | `--expect-ads` | none | text file with one expected ad id per line (`pull`) |
| `review.py` | `--expect-impressions` | none | account-level impressions for the same window (`pull`) |
| `review.py` | `--expect-spend` | none | account-level spend for the same window (`pull`) |
| `review.py` | `--from` | first day in the data | first day of the window to review (YYYY-MM-DD) |
| `review.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `review.py` | `--level` | `ad` | level of the rows (`pull`) |
| `review.py` | `--output` | required for `pull` | CSV to write (also `-o`) |
| `review.py` | `--previews` | none | folder of rendered ad previews named `<ad_id>.<ext>` |
| `review.py` | `--prior` | none | CSV or JSON of the previous equal window |
| `review.py` | `--profile` | `./creative-profile.md` for `review.py run`, else none | read the Script settings block of the profile (key map, type map, targets, currency); a flag on the command line still wins |
| `review.py` | `--source` | `Ads Manager export` | data source shown in the header |
| `review.py` | `--target` | none | your own payback targets, e.g. `cpa=40,roas=3`; read by the verdicts only |
| `review.py` | `--thumbs` | none | folder of small thumbnails named `<ad_id>.<ext>` |
| `review.py` | `--to` | last day in the data | last day of the window to review (YYYY-MM-DD) |
| `review.py` | `--tolerance` | 0.5 (the adapter's default) | percent a pull may fall short before it counts as incomplete (`pull`) |
| `review.py` | `--type-map` | none | the account's own ad-type words, e.g. `core=bau,drop=launch` |
| `review.py` | `--where` | none (all ads) | keep only rows where a column or name field matches, e.g. `market=US`; repeat the flag or use commas for more values |
| `verdicts.py` | `--currency` | read from the export's spend header | three-letter currency code for money |
| `verdicts.py` | `--group-by` | `format,ad_type` | columns to compare ads within, narrowest first; a group with fewer than 5 comparable ads widens to the next |
| `verdicts.py` | `--json` | off | print machine-readable JSON instead of text |
| `verdicts.py` | `--key-map` | none | name unlabelled or private `KEY:value` segments of ad names, e.g. `PX=concept,6=tone` |
| `verdicts.py` | `--min-change` | 8.0 | percent move that counts as real for CTR, frequency and hook rate |
| `verdicts.py` | `--min-impressions` | 1000 | ads below this are not judged |
| `verdicts.py` | `--protect-top` | 3 | the account's top N ads by purchases or purchase value are never paused unchecked |
| `verdicts.py` | `--target` | none | your own payback targets, e.g. `cpa=40,roas=3` or `cpc=0.5`; a never-worked ad is paused only when it misses them |
| `verdicts.py` | `--top-n` | 3 | how many top-spend ads the concentration line counts |
| `verdicts.py` | `--window` | 6 | days compared at the start and end of an ad's life when looking for fatigue |
| `verdicts.py` | `--young-days` | 5 | ads younger than this are still learning |

## The report

`creative-report` (and `creative-review`, which calls it) builds one self-contained HTML file. It opens in any browser, works without scripts (every section is then visible), prints to PDF, and follows your light or dark setting. Its left navigation has six tabs:

| Tab | What it shows |
|---|---|
| Overview | The tiles (spend, purchases, return on ad spend and more), "What changed since last time" when there is an earlier review, and a banner for key numbers no ad can show |
| Pareto | Where the value comes from: the few ads that make most of the purchase value, and the long tail |
| Keep/kill | The verdict board, one strip per verdict with Pause first, then every ad as a card you can open for its numbers and how to improve it |
| Format | A scorecard by format, formats over time, spend share against return, hook against hold, and ad types. Industry bands appear only from cited public sources and never change a grade |
| White space | The creative mix: concept by format coverage and the gaps worth testing |
| Briefing | Ready-to-use prompts and starter briefs for the gaps |

Above the tabs a filter row lets you search, filter by verdict, format or type, group and sort. The address in your browser reopens the same view, so you can send a link to the exact filtered state. Share the single `report.html` file itself (it embeds its images, and its only outside requests are Google Fonts), or print it to PDF from the browser. Numbers are never edited by hand: if something reads wrong, fix the inputs and rebuild. `report.py --check report.html` validates the structure without a browser.

## Where things are written

`creative-review` files each run under `./creative-review-runs/<account>/<window end>_<time>/` with `ads.csv`, `grade.json`, `verdicts.json`, `mix.json`, `changes.json`, `report.html`, `summary.md` and `run.json`. The next run of the same account compares itself with the latest earlier folder. Delete the folder to start fresh.
