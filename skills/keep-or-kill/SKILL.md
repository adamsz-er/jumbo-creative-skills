---
name: keep-or-kill
description: Give every Meta ad a pause, check, iterate, scale or keep verdict judged against its own campaign goal, with a confidence level, a plain-English sentence and the reasons shown. Use when the user asks which ads to pause, scale or refresh, runs a weekly creative review, asks "is this ad fatiguing", or wants a keep-or-kill call from an Ads Manager export or a Meta ads connector.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Keep or kill

One verdict per ad, with the evidence behind it. Grades are relative to the same account's own ads of the same campaign objective, in the same format and ad type. No benchmarks. An unknown is never a decision: an ad whose payback cannot be graded reads "Can't judge", not keep or iterate.

If there is no `creative-profile.md` yet, suggest running `creative-context` first, but do not require it.

## Pick the data mode and say it out loud

Follow `creative-context/references/data-inputs.md`.

1. **Meta ads connector.** Call read-only tools only: never one that activates, updates or changes anything. Pull an ad-level report with a **daily** breakdown (one row per ad per day) for several weeks, so fatigue can be read, and include paused ads that delivered in the window. Follow the numbered steps in `creative-context/references/data-inputs.md`: field catalogue first, every response saved to a JSON file, then `python3 scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total>` and use `ads.csv` wherever a CSV is named below. A `WARNING` line or exit 3 means the pull does not reconcile: re-fetch or drop duplicates the missing ads and run it again before you analyse. 3-second plays are derived per ad and shown as "(derived)"; say so when you quote a hook rate.
2. **CSV or screenshots.** Ask for a daily-breakdown Ads Manager export (`creative-context/references/export-recipe.md`). Screenshots cannot show a trend: say fatigue is unreadable and give weaker, clearly labelled calls.
3. **No data.** Say what is needed and offer the export recipe. Give no verdicts: label anything you say "no performance data".

## Run it

```
python3 scripts/verdicts.py ads.csv                    # ads.csv from the connector: see step 1
python3 scripts/verdicts.py ads.csv --young-days 5 --window 6 --min-change 8 --top-n 3 --protect-top 3
python3 scripts/verdicts.py ads.csv --group-by format,ad_type,market   # widest fallback last
python3 scripts/verdicts.py ads.csv --json
```

`--young-days` (5), `--window` (6), `--min-impressions` (1000) and `--min-change` (8) are arbitrary defaults, as is `--top-n` (3, how many top-spend ads the concentration line counts), `--protect-top` (3, the biggest sellers are never paused unchecked), and so is the minimum of 5 comparable ads needed to grade within a group. Set them from the account: how long its ads take to settle, how many days make a fair comparison, and how much ctr, frequency and hook rate move from one week to the next when nothing is wrong. `--min-change` is a materiality size, not a fatigue benchmark. The output states the values used. The rules are in `references/verdict-rules.md`.

## Present the result

1. Lead with the do-these-first list the script prints (largest spend at stake first), then the verdict counts.
2. For each ad, give the verdict, its sentence and its confidence as printed, then the reasons. Do not rephrase a sentence into stronger words.
3. An "Early read" is a lead, not a ruling: say it rests on a small comparison group, few delivery days or one payback measure.
4. Before any Pause, state the check line the script prints: rule out tracking, site or audience problems first. Only fatigue and never-worked are creative decisions.
5. "Can't judge" means the data cannot support a decision: say which field is missing and how to get it. Never turn it into iterate or keep.
6. Name the ads that are too young to judge, the thin-group warning, and the spend concentration line.
7. Say when fatigue could not be read (fewer than two windows of delivery days) and that such an ad is held, not scaled.

## Guardrails

- Relative grading only. Never invent or quote a benchmark.
- Say `n/a` when data is missing. Never treat a missing value as 0 or as "fine".
- Never pause, edit or scale anything in the account. These are recommendations. If the connector offers write tools, do not call them unless the user asks for that action in this conversation.
- Step size for a scale-up and the age a creative needs before it is judged come from the user's own history, not from this skill.
- Promo ads: a strong payback can be existing demand being harvested. Check new-customer share and the sale end date.
