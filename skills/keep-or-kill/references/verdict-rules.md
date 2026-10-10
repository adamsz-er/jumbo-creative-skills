# Verdict rules

First matching rule wins. Every verdict lists its reasons, a plain-English sentence, a confidence level and the spend at stake. All grading is relative to the account's own ads: top quartile at or above p75, bottom quartile at or below p25, costs inverted. No benchmark is used.

## Inputs

- **Learning flag.** Age is days from first delivery (or `created_time` when the data has it) to the latest date in the data. An ad is learning when age is under `--young-days` or its impressions are under `--min-impressions`.
- **Objective.** Read from the `objective` column. Sales (OUTCOME_SALES, CONVERSIONS, PRODUCT_CATALOG_SALES), traffic (OUTCOME_TRAFFIC, LINK_CLICKS), awareness (OUTCOME_AWARENESS, REACH, BRAND_AWARENESS, VIDEO_VIEWS), leads (OUTCOME_LEADS, LEAD_GENERATION), engagement (OUTCOME_ENGAGEMENT, POST_ENGAGEMENT). Unknown or absent is judged as sales and the output says so. An ad is only ever compared with ads of the same objective, so a traffic ad is never judged on purchases.
- **Payback measures, by objective.** Sales: `cpa` and `roas`. Traffic: `cpc` and `ctr`. Awareness: `cpm` and `hook_rate`. Leads: `cost_per_lead`. Engagement: `engagement_rate` and `cpm`. Formulas are in `creative-context/references/metrics.md`. A measure that cannot be computed is named and never read as 0.
- **Comparison group.** Default `--group-by format,ad_type`, within the objective. An ad is graded in the narrowest group with at least 5 comparable ads: format and ad type, then format, then the whole objective. Each reason names the group used and why a narrower one was skipped. 5 is an arbitrary default.
- **Thin group.** A group with 5 up to 9 comparable ads (under twice the minimum) is thin. The output lists thin groups in a warning, and every verdict that rests on one reads "Early read".
- **Attention.** `hook_rate` or `ctr` in the top quartile.
- **Fatiguing.** Comparing an ad's first and last `--window` delivery days: CTR falls by at least `--min-change` percent AND (average frequency rises by at least that, OR hook rate falls by at least that). With fewer than 2 x window delivery days the trend is "insufficient data": the ad is neither called fatiguing nor cleared.
- **Biggest sellers.** The account's top `--protect-top` ads by purchases, and by purchase value (default 3, arbitrary: set it from how many ads you run).

## Rules

| # | Condition | Verdict (`verdict_id`) |
|---|---|---|
| 1 | Learning | Too early (`too_early`) |
| 2 | No payback measure can be graded (missing data, or too few comparable ads) | Can't judge: missing ... (`cant_judge`). Never iterate, keep or scale. Fatigue is context only. |
| 3 | Fatiguing and payback is not bottom on every measure | Iterate (`iterate`) |
| 4 | Payback measures disagree (one top, one bottom) | Check before cutting (`check_mixed`) |
| 4a | Pause case, a small comparison group and under two `--window`s of delivery days | Check before cutting (`check_immature`) |
| 5 | Pause case (below) but not bottom account-wide within its objective | Keep (watch it) |
| 6 | Pause case but one of the biggest sellers | Check before cutting (`check_top_seller`) |
| 7 | Bottom on every payback measure, in its group and account-wide within its objective, and fatiguing | Pause: fatigued (`pause_fatigued`) |
| 8 | Bottom on every payback measure, in its group and account-wide within its objective, bottom in its first `--window` delivery days too, and missing every target the user set for its payback measures | Pause: never worked (`pause_never_worked`) |
| 8c | A Pause from 8 whose funnel points at the site: a landing-page view, add-to-cart or cart-to-checkout rate is weak (bottom quartile and clearly below similar ads, or clearly falling since its first days) while no step the ad controls (hook rate, hold rate, click-through) is | Check before cutting (`check_site`): the sentence names the weak site steps and says to check the landing page and checkout first. A fatigued pause (7) stands, since its click-through is falling by definition, and so does a pause whose own steps could not be judged; either way a weak site step is added to its reasons |
| 8a | As 8, but the user set no target for its payback measures | Check before cutting (`check_no_target`): weak only next to the account's other ads; the sentence asks for a target |
| 8b | As 8, but it meets a target the user set | Check before cutting (`check_meets_target`) |
| 9 | Payback top on every measure, fatigue readable and not fatiguing | Scale (`scale`) |
| 10 | Attention strong but payback bottom | Check before cutting (`check_feeds`) |
| 11 | Anything else | Keep (`keep`) |

Every Pause carries this line: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions.

Rule 8c is the funnel read from `funnel-diagnosis` (the shared `funnel_read`), applied to every would-be Pause. It needs landing page views, adds to cart or checkouts initiated in the data; without them the site side is unreadable, the Pause stands, and the JSON's `funnel` block says which steps were missing. Purchase rate is shown but never decides it: a weak one can be the offer or the audience as much as the page. The JSON carries the read as `funnel` (`call`, `reason`, `weak_steps`, `missing_site_steps`) on every ad that reached a Pause.

Targets come from the user only: `--target cpa=40,roas=3` (any metric id; cost metrics are met at or below the target, rates and ROAS at or above), or `target:` in the profile's `Script settings`. A target set for another objective's measure does not count. An ad whose measure is n/a (no purchases, so no CPA) misses its target. Never suggest a target value.

A thin group may produce a Pause, never a Confident one: the confidence is capped at Early read, and the sentence says so.

## Confidence

- **Confident**: group not thin, at least 2 x window delivery days, at least two payback measures that agree.
- **Early read**: thin group, or fewer delivery days than 2 x window, or one payback measure only, or the measures disagree.
- **Can't judge yet**: Can't judge or Too early.

## Spend at stake

`spend_at_stake` is the ad's spend in the window. Within each verdict the list is sorted by it, largest first. The do-these-first list is the top 5 by spend at stake across Pause, Check, Iterate and Scale; an ad that cannot be judged never leads it.

## Judgement calls to know about

- Payback top with fatigue unreadable (under two windows of delivery days) is held at Keep, never scaled.
- Fatiguing with a payback that is bottom on one measure only is Iterate: there is no agreement that it is weak.
- Never-worked uses the same payback measures over the ad's first `--window` delivery days, graded against every ad's own first window.
- Several ads of one concept share one fatigue clock; read their verdicts together.
- `--min-change` (default 8) is a materiality size to separate a real move from week-to-week noise. It is not a benchmark for fatigue: set it from how much your own metrics wobble when nothing is wrong.
- Every default here (`--young-days`, `--window`, `--min-impressions`, `--min-change`, `--top-n`, `--protect-top`, the group minimum of 5) is arbitrary. Set them from your own account.

## Summary block

Counts per verdict group, the ads too young to judge, the thin groups, the do-these-first list and spend concentration: "top N ads (N=3, an arbitrary default: set your own with `--top-n`) hold P% of spend". Heavy concentration means one fatigue event hurts the account. Judge how heavy against the account's own history.
