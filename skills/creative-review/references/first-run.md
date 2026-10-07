# First run

Show this in three lines the first time (no `creative-profile.md` and no earlier run folder), then carry on. Never stop to ask more than one question.

> **What this does:** reads your Meta ads for a window, grades every ad against your own account, says which to keep, fix or pause, and builds a six-tab dashboard you can open in any browser.
> **What it needs:** your ad data, from Meta's ads connector or a daily Ads Manager CSV. No data yet? Say so and it runs on a sample account first.
> **Safe:** it only reads. It never changes an ad, a budget or a setting.

## What the skill needs

| Need | Where it comes from | If it is missing |
|---|---|---|
| Daily ad rows: date, ad name, amount spent, impressions | Meta's ads connector, or an Ads Manager export (`creative-context/references/export-recipe.md`) | Offer the sample account: `review.py run --demo` |
| A currency code | The spend header of the export ("Amount spent (USD)"), `--currency`, or the profile | Ask once, or pass `--currency` |
| Purchases and purchase value | The same export (the recipe adds them) | Those measures read "n/a (missing ...)", never 0 |
| A brand profile | Drafted from the data by `profile_draft.py`; the user corrects it once | The draft leaves voice, offers and personas as "not stated" |

## The one question

If the connector finds two accounts that match the name the user gave, ask which one. That is the only question the skill should need.

## Repeat runs

Each run is filed under `creative-review-runs/<account>/<window end>_<time>/`. The next run of the same account compares itself with the latest earlier folder and reports, at the top of the Overview tab and in the summary, which ads changed verdict, which are new or gone, and how spend, return on ad spend and cost per purchase moved.
