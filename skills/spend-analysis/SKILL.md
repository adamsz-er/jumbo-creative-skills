---
name: spend-analysis
description: Show where a Meta ad account's money goes - by ad, concept, format, ad type, verdict and ad age - how concentrated it is, how much sits on ads judged pause or never worked, which keep and scale ads have room to grow, and the budget moves the account's own results support, each with a confidence and its evidence. Use when the user asks where the budget is going, what to cut or move, whether spend is too concentrated, or how to reallocate after a creative review. Relative to the account's own baseline; no benchmarks.
license: MIT
metadata:
  version: "0.2.0"
  role: analyse
---

# Spend analysis

Follows the money. Every share and ratio is against the account itself: a concept's return is shown as a percent of the account's own pooled return (100 means the same), never against an industry figure. Budget moves come only from `keep-or-kill` verdicts, so a move is never stronger than the call behind it.

## Before you start

1. Get the data as `creative-context` sets out: a daily Ads Manager export or a connector pull run through `from_mcp.py` (see `creative-context/references/data-inputs.md`). Say which mode you are in.
2. Run `keep-or-kill` first with `--json` so the moves have verdicts to stand on. Without them the skill still shows where the money goes, and says moves need verdicts.
3. Ask for the user's own payback target if keep-or-kill has none (`--target cpa=<their number>`): without one, a never-worked ad is "Check before cutting", not "Pause", and no money moves off it.

## Run it

```
python3 -I ../keep-or-kill/scripts/verdicts.py ads.csv --target roas=3 --json > verdicts.json   # the user's own target
python3 -I scripts/spend.py ads.csv --verdicts verdicts.json
python3 -I scripts/spend.py ads.csv --verdicts verdicts.json --json
python3 -I scripts/spend.py ads.csv --profile creative-profile.md --where market=US --verdicts verdicts.json
```

(When the skills are installed side by side the keep-or-kill script sits in its own folder; run it from there.)

`--pareto-share` (80, the common Pareto convention, not a rule), `--top-n` (3), `--age-bands` (`9,18,36` days) and `--min-impressions` (1000) are arbitrary defaults: set them from your own account. The output prints the values it used.

## What it shows

1. **The answer first:** where most of the money goes, how much sits on ads judged pause, and the top move or "no move is supported by the data".
2. **Totals** for the window, with the currency.
3. **Concentration:** the fewest ads holding the Pareto share of spend, and of purchase value, side by side. Spend more concentrated than value means money is piling onto ads that do not return in proportion.
4. **Spend by** concept, format, ad type, age band and verdict group: spend, share, purchases, value, return, cost per sale and the return as a percent of the account's.
5. **Spend on pause and never-worked ads**, with each ad's verdict sentence and the daily rate.
6. **Room to scale:** scale and keep ads with their frequency against the median of their format. Rising frequency means the same people are seeing the ad again, so more budget buys less.
7. **Budget moves:** money from pause ads to scale ads, split by the scale ads' current spend, with the lower of the two confidences and the evidence. Check-before-cutting ads move nothing. Iterate ads get a creative refresh, not a budget change.

`references/reading-spend.md` explains how to read each part and what the moves do not tell you.

## Present the result

- Lead with the three answer lines as printed. Then the moves, each with its confidence and evidence, then the tables the user asks about.
- Never give a step size for a budget increase: "raise in steps you have seen your account absorb before".
- Say when a move rests on an Early read verdict.
- **Next step:** `fatigue-planner` for ads that are wearing out, `creative-ideation` for what to make with freed budget.

## Guardrails

- Relative only: never quote a benchmark for concentration, return or cost.
- A missing value is `n/a (missing <field>)`, never 0.
- Never change a budget. These are recommendations; the skills never call a tool that edits the account.
- Platform return is a creative-level signal. Whether the business is healthy needs store revenue and margin from outside Ads Manager.

## How to use

Have ready: a daily export, keep-or-kill's `--json` output, and your own target cost per sale or return.

Try:

- "Where is my Meta budget going?"
- "How much am I spending on ads I should pause?"
- "Which ads can take more budget?"

## Common questions

- **Why no move?** No ad was judged pause, or no ad earned a scale call. Set your target and rerun keep-or-kill.
- **Is 80% a rule?** No: the Pareto share is a convention. Set your own.
- **How much should I raise a budget?** In steps your account has absorbed before; the skill does not invent one.
- **Why is frequency a warning?** Higher frequency means repeat views, so each extra unit of budget reaches fewer new people.
- More: creative-context/references/faq.md
