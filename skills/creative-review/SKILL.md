---
name: creative-review
description: One sentence in, the whole Meta ad creative review out. Use when the user says "review my ads", "review my Meta ads for the last 30 days", "creative review", "how are my ads doing" or "what should I pause". Pulls the data (Meta ads connector or an Ads Manager CSV), reconciles it, grades every ad, gives keep, fix or pause calls, maps the creative mix, builds the six-tab dashboard, and replies with three bullets and the report path. On repeat runs it also says what changed since last time. Works with no connection on a built-in sample account.
license: MIT
metadata:
  version: "0.1.0"
  role: front-door
---

# Creative review

The front door of the package. The user says one sentence; you run the whole review. Read-only: never call a Meta tool that changes anything.

If this is the first run (no `creative-profile.md` and no `creative-review-runs/` folder), show the three-line welcome in `references/first-run.md`, then continue. Ask at most one question in the whole flow.

## Flow

1. **Get the data, in this order.**
   - **Meta ads connector present:** follow the numbered steps in `creative-context/references/data-inputs.md` (read-only tools only; field catalogue first; every response saved to a file). Choose the account by the name the user gave; ask only if two accounts match. Then merge and check the totals:
     `python3 -I scripts/review.py pull page1.json page2.json --expect-spend <account total> --expect-impressions <account total> -o ads.csv`
     It prints `completeness: reconciled` or `not checked`; hand that word to `run --completeness`. A short pull stops with E-RECONCILE and the exact fix.
   - **A CSV was given:** use it.
   - **Neither:** say so and offer the sample account ("Want to see it on a sample account first?") and the export recipe (`creative-context/references/export-recipe.md`). If they say yes, run the demo (step 4 with `--demo`).
2. **Profile.** If there is no `creative-profile.md`, run `python3 -I scripts/profile_draft.py ads.csv -o creative-profile.md` (it refuses to overwrite an existing file unless you add `--force`) and show the draft in ONE message: "Here is what I could tell from your ads; correct anything or say OK." Save on OK. The draft holds only facts read from the data and leaves brand voice, offers and personas as "not stated"; never fill those in yourself.
3. **Window.** The window is whatever the data covers. If the user named one ("last 30 days"), pull that window, or pass `--from` and `--to` to `run`.
4. **Run it.**
   `python3 -I scripts/review.py run ads.csv --profile creative-profile.md --source "Meta ads connector" --completeness reconciled`
   Pass `--where market=US`, `--target cpa=<their own number>`, `--type-map`, `--key-map`, `--prior prior.csv`, `--previews dir` and `--thumbs dir` only when the user gave them. Never invent a target. `--demo` reviews the built-in sample account and labels every output "sample data".
5. **Reply** with the three bullets it printed and the report path, nothing more. Then offer the top action's next step (for the first Pause or Iterate ad, a one-change brief with `creative-brief`).

## What a run writes

Run folders made before the run record existed (no `run.json`) are ignored, so the first run after upgrading reads as a first run.

One folder per run, `creative-review-runs/<account>/<window end>_<time>/`, holding `ads.csv`, `grade.json`, `verdicts.json`, `mix.json`, `changes.json`, `report.html` and `summary.md`. The dashboard opens in any browser; its first panel on the Overview tab is "What changed since last time" (an empty state on a first run).

The summary is three bullets: the headline (spend, purchases, return on ad spend, and how that moved since the last review), the biggest action (the first "do first" ad with its spend at stake), and the biggest opportunity (the first gap in the creative mix, or "no clear gap yet").

## When something goes wrong

Every known failure prints a plain message and its exact fix, and exits with its own code, never a traceback:

| Code | Means | Fix it names |
|---|---|---|
| E-NODATA | no data file and no connector | the sample account, the connector, the export steps |
| E-COLUMNS | the CSV lacks a needed column | each missing column and the recipe step that adds it |
| E-EMPTY | no rows in the window | the window asked for and the dates the file covers |
| E-RECONCILE | the pull is short | the percent short and "re-run the pull with pagination" |
| E-CURRENCY | no currency in the header | `--currency XXX` |
| E-SKILL | a sibling skill is not installed | its name and the install command |
| E-PROFILE | the profile cannot be read | fix the line it names, or pass a different `--profile` |
| E-TARGET | a bad `--target` | the script's own message plus the accepted metrics |
| E-REPORT | the dashboard failed its structure check | its first failing line |
| E-ANALYSIS | an analysis step stopped | the step, its message, and the folder that keeps the earlier steps |

Anything else prints "Something unexpected went wrong" with a one-line error; rerun with `--debug` (before the subcommand) for the traceback.

## Rules

- Grade against the account's own ads only; never quote a benchmark.
- A missing field is "n/a (missing <field>)", never 0.
- Say the numbers' currency, and say when a figure is an arbitrary default the user should set from their own account.
- A different account under the same fallback name is not compared with the last run: the summary says so.

## How to use

Have ready: a daily Ads Manager CSV or a connected Meta ads connector. A brand profile is optional; the skill drafts one from your data.

Try:

- "Review my Meta ads for the last 28 days."
- "Show me a sample review."
- "What changed since my last review?"

## Common questions

- **Does it change my ads?** These skills never call a tool that changes your ad account. Your agent could, if you asked it to directly, through the Meta connector's own tools.
- **Where is the report?** In the run folder under `./creative-review-runs/`; the reply gives the path.
- **What if the pull is short?** It stops with E-RECONCILE and the exact fix; see the troubleshooting table.
- **Can I review one market?** Yes: add `--where market=US` (any column or name field).
- More: creative-context/references/faq.md
