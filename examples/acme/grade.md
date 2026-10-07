# Acme grade output

Generated, not hand-written: `python3 skills/creative-grader/scripts/grade.py examples/acme/ads_daily.csv` on the fictional Acme Outdoor Co. fixture.

```text
Basis: graded against this account's own ads, never a benchmark.
Window: 2026-03-01 to 2026-03-30
Grouped by: format. Ads graded per group: carousel=7, founder-video=3, partnership=4, static=7, ugc-video=9
Bands: top quartile is at or above p75, bottom at or below p25 (costs inverted: a cheap CPM is top).
Ads under 1000 impressions are not graded (arbitrary default: set it from your own spend per ad).
CTR uses: link_clicks. Conversions column: Purchases.
Groups with fewer than 5 ads fall back to account-wide numbers: founder-video, partnership.

ad            group          hook%     hold%     ctr%      cpm        cpa        roas      diagnosis                                    
120000000001  ugc-video      25.5 LOW  28.4 LOW  1.42 mid  12.44 mid  30.72 top  3.39 mid  hook (hook_rate bottom quartile)
120000000002  ugc-video      26.5 mid  34.4 top  1.83 top  10.32 top  16.00 top  4.85 top  no broken step
120000000003  static         n/a       n/a       1.18 mid  9.02 top   20.11 top  6.46 mid  no broken step
120000000006  founder-video  19.7 LOW  36.1 top  1.19 mid  10.60 mid  25.00 mid  3.32 mid  hook (hook_rate bottom quartile)
120000000008  partnership    24.6 LOW  31.4 mid  1.09 LOW  11.15 mid  26.25 mid  6.19 top  hook (hook_rate bottom quartile)
120000000009  carousel       n/a       n/a       1.58 mid  13.82 LOW  27.49 LOW  4.40 mid  reach cost (cpm bottom quartile)
120000000010  ugc-video      25.7 LOW  28.4 LOW  1.75 top  15.06 mid  38.03 mid  2.70 LOW  hook (hook_rate bottom quartile)
120000000011  founder-video  22.8 LOW  n/a       1.57 mid  15.99 LOW  32.02 mid  4.93 mid  reach cost (cpm bottom quartile)
120000000014  static         n/a       n/a       1.62 mid  16.32 LOW  27.78 LOW  4.46 mid  reach cost (cpm bottom quartile)
120000000017  static         n/a       n/a       0.24 LOW  12.58 mid  n/a        0.00 LOW  click (ctr bottom quartile)
120000000018  ugc-video      26.8 top  34.6 top  1.06 LOW  9.95 top   44.91 LOW  2.72 mid  click (ctr bottom quartile)
120000000021  carousel       n/a       n/a       1.61 mid  12.08 mid  20.39 top  8.02 top  post-click (add_to_cart_rate bottom quartile)
120000000022  partnership    25.3 mid  32.8 mid  1.77 top  10.05 top  21.51 top  5.87 top  no broken step
120000000023  ugc-video      28.3 top  33.3 mid  1.70 top  15.52 LOW  39.43 mid  2.65 LOW  reach cost (cpm bottom quartile)
120000000026  static         n/a       n/a       1.76 top  10.99 top  21.51 top  6.95 top  no broken step
120000000028  ugc-video      25.1 LOW  33.4 mid  1.57 mid  11.53 mid  38.19 mid  3.48 top  hook (hook_rate bottom quartile)
120000000007  carousel       n/a       n/a       1.28 LOW  9.48 top   26.02 mid  5.19 mid  click (ctr bottom quartile)
120000000004  static         n/a       n/a       1.85 top  13.47 LOW  26.30 mid  5.58 mid  reach cost (cpm bottom quartile)
120000000005  carousel       n/a       n/a       1.84 top  13.44 LOW  32.24 LOW  3.87 LOW  reach cost (cpm bottom quartile)
120000000012  static         n/a       n/a       0.91 LOW  12.15 mid  43.95 LOW  1.63 LOW  click (ctr bottom quartile)
120000000016  partnership    28.1 top  28.9 LOW  1.58 mid  16.92 LOW  28.63 mid  3.13 mid  reach cost (cpm bottom quartile)
120000000024  carousel       n/a       n/a       1.42 LOW  9.85 top   17.55 top  8.13 top  click (ctr bottom quartile)
120000000029  carousel       n/a       n/a       1.80 top  10.07 mid  25.88 mid  4.21 mid  post-click (cvr bottom quartile)
120000000013  carousel       n/a       n/a       1.58 mid  12.73 mid  22.33 mid  3.59 LOW  pays back (roas bottom quartile)
120000000015  ugc-video      25.7 mid  39.0 top  1.51 mid  15.29 LOW  46.03 LOW  2.94 mid  reach cost (cpm bottom quartile)
120000000019  ugc-video      26.8 top  28.0 LOW  1.11 LOW  10.09 top  26.79 top  5.57 top  hold (hold_rate bottom quartile)
120000000020  founder-video  24.4 LOW  37.1 top  1.00 LOW  15.14 LOW  59.56 LOW  2.55 LOW  reach cost (cpm bottom quartile)
120000000025  static         n/a       n/a       1.36 mid  11.20 mid  21.81 mid  7.05 top  no broken step
120000000027  partnership    27.3 top  37.3 top  1.73 top  11.78 mid  19.58 top  4.07 mid  no broken step
120000000030  ugc-video      25.9 mid  30.5 mid  0.92 LOW  17.03 LOW  83.80 LOW  1.97 LOW  reach cost (cpm bottom quartile)

Diagnoses: reach cost=10, none=6, hook=5, click=5, post-click=2, pays back=1, hold=1

What to do, by first broken step (fix that step first, then re-read; 'also weak' lists later bottom-quartile metrics):
  reach cost: Reach is expensive: likely auction or audience saturation, not necessarily the creative. Rule that out before changing the ad.
    120000000009 (also weak: add_to_cart_rate, cpa)
    120000000011 (also weak: hook_rate)
    120000000014 (also weak: cpa)
    120000000023 (also weak: roas)
    120000000004 (also weak: cvr)
    120000000005 (also weak: cvr, cpa, roas)
    120000000016 (also weak: hold_rate)
    120000000015 (also weak: cpa)
    120000000020 (also weak: hook_rate, ctr, cpa, roas)
    120000000030 (also weak: ctr, add_to_cart_rate, cpa, roas)
  hook: Change the first 3 seconds: the opening is not stopping the scroll.
    120000000001 (also weak: hold_rate, add_to_cart_rate)
    120000000006 (also weak: add_to_cart_rate)
    120000000008 (also weak: ctr)
    120000000010 (also weak: hold_rate, cvr, add_to_cart_rate, roas)
    120000000028 (also weak: cvr)
  hold: The hook works but the promise is not sustained: tighten the body of the ad.
    120000000019 (also weak: ctr)
  click: People watch but few click: the call to action or the offer is weak.
    120000000017 (also weak: cvr, add_to_cart_rate, roas)
    120000000018 (also weak: cvr, cpa)
    120000000007
    120000000012 (also weak: add_to_cart_rate, cpa, roas)
    120000000024
  post-click: Clicks arrive but do not convert: likely the landing page or the offer, not the creative. Check the site and whether the page matches the message; also rule out an audience mismatch.
    120000000021
    120000000029
  pays back: The funnel reads normally but payback is weak: check price, margin, offer and attribution before blaming the creative.
    120000000013

Steps skipped, never read as healthy:
  hook_rate not graded (missing video_views_3s); hold_rate not graded (missing video_thruplay): 13 ads (120000000003, 120000000009, 120000000014, 120000000021, 120000000026, 120000000007, 120000000004, 120000000005, 120000000012, 120000000024, 120000000029, 120000000013, 120000000025)
  hold_rate not graded (missing video_thruplay): 1 ads (120000000011)
  hook_rate not graded (missing video_views_3s); hold_rate not graded (missing video_thruplay); cpa not graded (zero conversions): 1 ads (120000000017)

LOW = bottom quartile, top = top quartile, mid = middle; n/a = missing or zero operand, never 0.
```
