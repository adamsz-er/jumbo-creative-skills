# Diagnosis patterns

Read the funnel in order and name the **first** step in the bottom quartile of the account's own distribution (same format group). Fix that step first, then read again: later weak steps often move once the earlier one is fixed.

| First broken step | Metric | What it usually means | Action |
|---|---|---|---|
| Reach cost | `cpm` bottom quartile (costs inverted: a high CPM is bottom) | The auction or the audience is expensive for this ad. Rising CPM with a stable CTR points at auction pressure or audience saturation, not necessarily the creative. | Check audience size and overlap, placement mix and the sale calendar before touching the ad. |
| Hook | `hook_rate` bottom quartile, the rest normal | The opening does not stop the scroll. | Change the first 3 seconds: a new opening shot, a stronger first line, a different face or sound. Keep the body. |
| Hold | `hold_rate` bottom quartile, hook not bottom | People stop, then leave: the promise is not sustained. | Tighten the body: cut dead time, deliver the promise sooner, put proof earlier. |
| Click | `ctr` bottom quartile, hook and hold not bottom | People watch but do not act: weak call to action or offer. | Make the offer and the next step explicit; test a clearer end card or caption. |
| Post-click | `cvr` or `add_to_cart_rate` bottom quartile while CTR is not bottom | Clicks arrive and then stall: likely the landing page, the offer or the audience, not the creative. | Check the site and whether the page matches the ad's message. Rule out an audience mismatch. |
| Pays back | `cpa` or `roas` bottom quartile while the steps above read normally | The funnel works but the economics do not. | Check price, margin, attribution setting and tracking before blaming the creative. |

## Reading notes

- Hook rate and thumb-stop rate are one number (see creative-context `metrics.md`).
- Hold rate is ThruPlay-based. Without ThruPlays the hold step is skipped and said so.
- Static ads have no video metrics. Their funnel starts at CPM and goes straight to CTR.
- Compare within a format. A carousel is never graded against a video.
- Several ads can be bottom quartile on the same step: that is a pattern in the account, worth saying once.
- A diagnosis is a hypothesis from the numbers. Mark anything you could not check as "check in your Ads Manager".
