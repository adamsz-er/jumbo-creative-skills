# Metric definitions

One id, one formula. Use these exactly. All rates are percentages unless stated. If an operand is missing or its denominator is zero, the metric is **n/a**, shown as `n/a (missing <field>)`, and never 0.

| Id | Formula | Notes |
|---|---|---|
| `hook_rate` | video_views_3s / impressions * 100 | Alias: `thumb_stop_rate`. Same formula, same number. Present it as an alias, never as a second metric. |
| `hold_rate` | video_thruplay / video_views_3s * 100 | ThruPlay-based. If ThruPlays are missing, hold rate is unavailable. Do not substitute 75% plays or any other measure. |
| `video_completion_rate` | video_thruplay / impressions * 100 | |
| `ctr` | clicks / impressions * 100 | State whether link clicks or all clicks were used. Prefer link clicks for creative work. |
| `cpm` | spend / impressions * 1000 | |
| `cpc` | spend / clicks | Same click type as CTR. |
| `cpa` | spend / conversions | |
| `roas` | conversion_value / spend | |
| `cvr` | conversions / clicks * 100 | |
| `add_to_cart_rate` | add_to_carts / clicks * 100 | |
| `cost_per_add_to_cart` | spend / add_to_carts | |
| `cost_per_lead` | spend / leads | Judges lead-generation campaigns. `leads` is the lead count Meta reports for the ad. |
| `engagement_rate` | (shares + saves + comments) / impressions * 100 | Needs all three counts; if any is missing the rate is n/a (missing ...). Judges engagement campaigns, beside `cpm`. |
| `frequency` | impressions / reach | Average times a person saw the ad. With daily rows, an average of daily values is not lifetime frequency. |
| `mer` | revenue / spend | Revenue is the store's own total revenue, which Ads Manager does not report. Ask for it. |
| `landing_page_view_rate` | landing_page_views / link_clicks * 100 | Package metric, not in the shared schema. Of the link clicks, how many loaded the page. A fall while CTR holds points at the page (speed, a broken link), not the ad. |
| `cart_to_checkout_rate` | checkouts / add_to_carts * 100 | Package metric. Of the adds to cart, how many started checkout. Not the same as a checkout rate measured against site sessions. |
| `new_customer_purchase_share` | new_customers / conversions * 100 | Package metric, count based: of the purchases, how many were from new customers. Only where the data carries a new-customer purchase count. |

## Base fields

`spend`, `impressions`, `reach`, `video_views_3s` (3-second video plays), `video_thruplay`, `link_clicks`, `clicks` (all clicks), `conversions`, `conversion_value`, `add_to_carts`, `revenue`, `leads`, `shares`, `saves`, `comments`, `landing_page_views`, `checkouts` (checkouts initiated), `new_customers` (purchases by new customers).

- Landing page views and checkouts initiated come from the Meta pixel or Conversions API: an Ads Manager export adds them as columns ("Landing page views", "Checkouts initiated"). A new-customer purchase count is not a standard ad-level column: add it as "New customer purchases" only if your store or a customer-list breakdown gives it per ad, and leave it out otherwise.

- 3-second plays: Meta counts a play at 3 seconds, or at 97% of the video for shorter videos, and excludes replays within one impression. In API terms this is the `video_view` entry in `actions`. The field that counts every video start is a different, larger number: using it inflates hook rate.
- ThruPlay is a play to 15 seconds, or to the end for shorter videos, or 6 seconds depending on how the ad was set up. Note which one the account used. Check in your Ads Manager.
- Meta stopped reporting the 10-second watch metrics in January 2026. Do not use them.

## Conversions column

Ads Manager exports may contain both "Purchases" and "Results". "Results" is whatever the campaign objective optimises for (a lead, a link click, a purchase), so it is not a purchase count. When both exist, use Purchases and record which column fed `conversions`. When only Results exists, say so in the answer, because CPA and CVR then describe the objective's result, not purchases.

## Reading the numbers

- Compare an ad with its own account: median and quartiles of the same metric over a trailing window (the window you analyse, for example several weeks), within the same format and funnel stage. Top quartile of the account's own distribution is that account's "good". There are no universal thresholds.
- Require volume before judging. Ads under a minimum number of impressions are shown but not graded. Pick the minimum from the account's own spend per ad and say what you chose.
- Read the funnel in order and diagnose the first broken step: CPM (cost of reach) then hook rate (stops the scroll) then hold rate (message sustained) then CTR (click offer) then landing-page view rate, add-to-cart rate, cart-to-checkout rate and conversion (site) then CPA and ROAS (payback).
- Platform ROAS is a creative-level signal. Whether the business is healthy is answered by MER and by new-customer cost, which need data from outside Ads Manager.
- Keep definitions fixed within one report. Mixing 3-second and ThruPlay bases silently changes hold rate.
