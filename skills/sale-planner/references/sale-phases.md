# The phases of a sale

Each phase has a single purpose, and each needs its own creative: what opens a sale is not what should run on its final day.

| Phase | Timing | Spend | Who sees it | Purpose | What the ad shows | What the words say |
|---|---|---|---|---|---|---|
| Teaser | About a week before | Light; it pays for signups, not orders | People who engaged, visited or bought before | Build interest and a list | The product and the brand, no price; a hint that something is on its way | An invitation to sign up or get in early |
| Early access | A day or two before the public sale | Small and focused; email and SMS do most of the work, ads find the list again | Subscribers, past buyers, loyalty members | Let the keenest buyers in first | Being first, made to feel exclusive | How to get in (code or link) and when the window closes |
| Launch | Day one | The biggest increase of the whole sale | New prospects and warm audiences together | Turn the built-up interest into orders | The deal itself: what it is, how it works, when it stops | The offer in the opening line and a true end time |
| Peak | The middle days | Hold or trim; more budget will not fix a falling return | Mostly warm audiences, as new prospects get dearer | Keep cost per sale steady as demand flattens | New angles in turn: best sellers, proof, one category | Products and proof, not only the percentage |
| Extension | Only if planned or truly needed | A modest increase; watch what each sale costs | Warm audiences | Pick up buyers who missed the main run, without a second launch | Fresh creative on a neighbouring angle, never the launch ad again | The reason for the extra days and the new end |
| Last chance | The final day or two | A short push, then switch off at the close | Only people close to buying | Convert those who wait for a deadline | A countdown to the real end; low stock only where it is true | The exact closing time |
| Post-sale | The weeks after | Size targets from your own last sale (below) | New prospects, and follow-up for first-time buyers | Get back to full-price trade | The brand and the range, new arrivals first | Nothing about discounts |

## Rules for any sale

- **Keep sale campaigns apart from always-on campaigns,** so the sale does not take credit for full-price demand and can be switched off cleanly.
- **Brief and approve every phase's creative before the sale opens.** There is no time to brief during peak trading.
- **Plan each day against its phase,** not against the whole event's average. Launch day and last chance behave differently from the middle.
- **Have the post-sale creative ready before the sale ends.** Around gifting seasons, add delivery cut-off dates to the copy, then gift cards and fast shipping for the last-minute buyer.
- **Match the offer to the buyer.** Price-sensitive and newer buyers often answer bigger percentages; loyal buyers often answer perks such as free shipping or early access. Some markets barely answer sale messages at all: test before assuming one offer fits every market.
- **Raise budgets in steps** your account has absorbed before, a few days apart, rather than one large jump.

## Sizing the post-sale weeks

Do not assume a dip, and do not guess its size. Run `scripts/sale_lift.py` on the account's last comparable sale and read its pull-forward line: the post-sale days against the baseline. If those days ran below the baseline, lower the post-sale targets by about that gap for about that many days; if they did not, keep normal targets. With no past sale to read, say the post-sale target is unbacked and check it daily.

## Judging each phase

Read each phase on its own job: the teaser on list growth, early access on the share of revenue from owned channels and returning buyers, launch against its daily plan, peak on cost per sale as the sale ages, last chance on its final-day cost per sale, and post-sale on its days against the baseline (the pull-forward read). `scripts/sale_lift.py` reads the whole sale against a matched baseline.
