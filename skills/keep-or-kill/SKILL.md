---
name: keep-or-kill
description: Give every Meta ad a keep, kill, iterate or scale verdict from its own performance, age and fatigue trend, with the reasons shown. Use when the user asks which ads to pause, scale or refresh, runs a weekly creative review, asks "is this ad fatiguing", or wants a keep-or-kill call from an Ads Manager export or a Meta ads connector.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Keep or kill

One verdict per ad, with the evidence behind it. Grades are relative to the same account's own ads in the same format. No benchmarks.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** List its tools, then pull an ad-level report with a **daily** breakdown (one row per ad per day) for at least 30 days, so fatigue can be read. Fetch: ad name, ad id, date, spend, impressions, reach, link clicks, 3-second video plays (the `video_view` action), ThruPlays, purchases and purchase value. Paused ads that delivered in the window must be included. Write the returned rows, unchanged, to a JSON file (a list of row objects, or `{"data": [...]}`) and pass it to the script.
2. **CSV or screenshots.** Ask for a daily-breakdown Ads Manager export (`creative-context/references/export-recipe.md`). Screenshots cannot show a trend: say fatigue is unreadable and give weaker, clearly labelled calls.
3. **No data.** Say what is needed and offer the export recipe. Give no verdicts: label anything you say "no performance data".

## Run it

```
python3 scripts/verdicts.py ads.csv                    # or ads.json from the connector
python3 scripts/verdicts.py ads.csv --young-days 5 --window 6 --min-change 8 --top-n 3
python3 scripts/verdicts.py ads.csv --json
```

`--young-days` (5), `--window` (6), `--min-impressions` (1000) and `--min-change` (8) are arbitrary defaults, as is `--top-n` (3, how many top-spend ads the concentration line counts), and so is the minimum of 5 comparable ads needed to grade within a group. Set them from the account: how long its ads take to settle, how many days make a fair comparison, and how much ctr, frequency and hook rate move from one week to the next when nothing is wrong. `--min-change` is a materiality size, not a fatigue benchmark. The output states the values used. The rules are in `references/verdict-rules.md`.

## Present the result

1. Lead with the verdict counts and the ads that need a decision now (kills, iterations, scale candidates).
2. For each, give the verdict and its reasons from the output, not a paraphrase.
3. Before any kill, state the check line the script prints: rule out tracking, site or audience problems first. Only fatigue and never-worked are creative decisions.
4. Name the ads that are too young to judge, and the spend concentration line.
5. Say when fatigue could not be read (fewer than two windows of delivery days) and that such an ad is held, not scaled.

## Guardrails

- Relative grading only. Never invent or quote a benchmark.
- Say `n/a` when data is missing. Never treat a missing value as 0 or as "fine".
- Never pause, edit or scale anything in the account. These are recommendations. If the connector offers write tools, do not call them unless the user asks for that action in this conversation.
- Step size for a scale-up and the age a creative needs before it is judged come from the user's own history, not from this skill.
- Promo ads: a strong payback can be existing demand being harvested. Check new-customer share and the sale end date.
