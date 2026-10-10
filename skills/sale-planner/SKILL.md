---
name: sale-planner
description: Plan a sale on Meta phase by phase - teaser, early access, launch, peak, extension, last chance, post-sale - with the creative, copy, audience and budget shape for each; choose the offer mechanic (gift with purchase, buy-more-save-more and tiers, BOGO, red-line markdowns, "take a further X% off", sale extended, early access, free-shipping threshold, bundles, mystery offers, sitewide or category); and judge a past sale from the account's own data - lift against a weekday-matched baseline (with earlier promotions left out when the user names them), new against returning buyers, pull-forward after the sale and contribution when margins are given. Consumer-law guardrails are hard rules. Use for Black Friday and Cyber Monday, the Australian end of financial year, Boxing Day, or any other sale or offer question.
license: MIT
metadata:
  version: "0.2.0"
  role: make
---

# Sale planner

A sale is several jobs in a row, and each needs its own creative. This skill plans the phases, helps pick the offer mechanic for the reason the sale exists, and reads a past sale honestly: against what the same days would have done without it, net of any dip that follows.

## Before you start

1. Read `creative-profile.md` (offers, calendar, margin, claims that need approval). If missing, ask in one round: brand, product, audience, the sale's dates and offer, tone.
2. Ask **why** this sale: clear stock, acquire new customers, reward existing ones, hit a cash target, match a market moment. The reason picks the mechanic.
3. Ask the market. Australia: the rules from the Australian Competition and Consumer Commission and the calendar in the references apply. Elsewhere: tell the user to check their own regulator's rules on sale pricing and urgency before anything runs.
4. Never invent the offer, the discount, the dates or a "was" price. They come from the user.

## Plan the sale

- **Phases:** `references/sale-phases.md` gives each phase's job, creative, copy, audience and budget shape. Build the creative for every phase before the sale opens; a sale that is briefed mid-flight runs launch ads at last chance.
- **Mechanic:** `references/offer-tactics.md` covers when to use each, when not to, its creative pattern, its risks and what to judge it on.
- **Calendar:** `references/sale-calendar.md` lists the Australian moments by rule and asks for the user's own market.
- **Rules:** `references/consumer-law.md` is a hard gate. Check every phase's copy against it before it is briefed.

Give the plan as one table, one row per phase: dates, job, creative, copy (the actual lines, checked against the rules), audience, budget shape, and what to watch.

## Judge a past sale

```
python3 -I scripts/sale_lift.py ads.csv --sale-from 2026-03-16 --sale-to 2026-03-22
python3 -I scripts/sale_lift.py ads.csv --sale-from 2026-03-16 --sale-to 2026-03-22 --margin 38 --baseline-margin 52
python3 -I scripts/sale_lift.py ads.csv --sale-from 2026-03-16 --sale-to 2026-03-22 --gap-days 3 --post-days 8 --json
```

- **Lift** is the sale's actual against what the same weekdays did in the baseline before it (`--baseline-days`, 21 by default; `--gap-days` skips a teaser; `--exclude FROM:TO`, repeatable, drops an earlier promotion from the baseline, otherwise the output warns the baseline may include other promotions). Never against the sale's own first days.
- **New against returning:** the new-customer purchase share in the sale and the baseline, where the data has a new-customer count. A sale that mostly served returning buyers is a retention tool.
- **Pull-forward:** the days after the sale (`--post-days`, 9 by default) against the same baseline. A dip there was partly bought early; the net lift subtracts it.
- **Contribution** only when the user gives margins: sale revenue times the sale margin, less expected revenue times the full-price margin, less the extra ad spend. Without margins it says it cannot judge profit.
- With a revenue column (the store's own), it leads with that. Otherwise it says the value is platform-attributed purchase value, which can over- or under-count a sale.

The window lengths and `--min-baseline-days` (7) are arbitrary defaults: set them from your own trading pattern. `--where ad_type=promo` reads only the sale ads, and the output then says it cannot see the sale's effect on the rest of the account.

## Present the result

1. For a plan: the phase table, the mechanic with its reason, and the rules each phase's copy was checked against.
2. For a past sale: the three lines it leads with (net lift with its basis, incremental return against the account's own baseline return, the biggest caveat), then the detail.
3. **Next step:** `copy-tests` for copy variants per phase, `creative-brief` for each phase's ads, `ad-namer` with the `offer` field so the next sale can be compared.

## Guardrails

- Consumer law is a hard rule, not advice: no false urgency, no "final" or "ends today" when an extension is planned, no countdown that resets, only genuine "was" prices, "sitewide" means every product. See `references/consumer-law.md`.
- No benchmarks: no "a good sale lifts X%". Judge against the account's own baseline.
- No invented offers, prices, deadlines, stock levels or testimonials.
- Mystery and chance-based offers: disclose the odds and a guaranteed minimum, and check local law on promotions of chance before running one.
- Read only: never create, edit or launch anything in the ad account.

## How to use

Have ready: the sale's reason, dates and offer; your market; for a past sale, daily rows covering the weeks before and after it.

Try:

- "Plan our Black Friday sale on Meta, phase by phase."
- "Gift with purchase or a percentage off for our end-of-financial-year sale?"
- "Did last month's sale actually make us money?"

## Common questions

- **Why compare with weeks before, not last year?** The script uses the weeks before because the data is there; compare with last year's same event too if you have it.
- **What is pull-forward?** Sales that would have happened anyway, just earlier. The days after a sale show it as a dip.
- **Can I extend the sale?** Only if you did not say it was ending. Plan the extension, or do not promise an end you will not keep.
- **My market is not Australia.** The phases and tactics travel; the rules do not. Check your regulator's guidance.
- More: creative-context/references/faq.md
