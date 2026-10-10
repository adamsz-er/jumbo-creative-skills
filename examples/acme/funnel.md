# Acme funnel-diagnosis output

Generated, not hand-written, on the fictional Acme Outdoor Co. fixture (synthetic data, not a real account). It runs on the extended export, which carries landing page views and checkouts; ad 120000000002's landing page was made to break partway through the window.

`python3 -I skills/funnel-diagnosis/scripts/funnel.py examples/acme/ads_daily_extended.csv`

```text
Funnel diagnosis: 30 ads judged: 1 site, 1 both, 15 creative, 13 neither, 0 unjudged, 0 unreadable.
problem-first | ugc-video | creator-02 | bau | rain-shell | lofi | 2026-03-01: the ad still earns clicks (ctr holds) while landing page view rate fell 46% since its first 6 delivery days and cart to checkout rate is in the bottom quartile of its group: check the page before touching the creative.

account-wide: a sitewide problem (checkout, payment, shipping, stock) shows here first: creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  hook rate: down 16% from the account's first 6 days to its last
  ctr: down 10% from the account's first 6 days to its last

Per ad (site, both, creative, neither, unjudged, unreadable; within a call, ads with a step that fell first, then by spend):
problem-first | ugc-video | creator-02 | bau | rain-shell | lofi | 2026-03-01 (120000000002): site
  the ad still earns attention and clicks while a step on the site is weak or falling: check the page first
  weak: landing page view rate, bottom quartile of its group, down 46% since its first 6 delivery days
  weak: cart to checkout rate, bottom quartile of its group
guarantee | static | house | bau | water-bottle | polished | 2026-03-01 (120000000017): both
  steps on both sides are weak or falling: check the page before judging the creative
  weak: ctr, bottom quartile of its group
  weak: cart to checkout rate, bottom quartile of its group
  weak: cvr, bottom quartile of its group
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
durability-test | ugc-video | creator-01 | bau | trail-boot | lofi | 2026-03-01 (120000000001): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group, down 31% since its first 6 delivery days
  weak: hold rate, bottom quartile of its group
  weak: ctr, down 52% since its first 6 delivery days
behind-the-seams | founder-video | founder | bau | tent-2p | lofi | 2026-03-01 (120000000011): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group
  weak: ctr, down 9% since its first 6 delivery days
  hold rate: n/a (missing video_thruplay)
trail-diary | partnership | creator-09 | bau | tent-2p | lofi | 2026-03-01 (120000000022): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, down 8% since its first 6 delivery days
weather-ready | ugc-video | creator-04 | bau | rain-shell | lofi | 2026-03-01 (120000000010): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group
  weak: hold rate, bottom quartile of its group
founder-note | founder-video | founder | launch | headlamp | lofi | 2026-03-16 (120000000020): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group
  weak: ctr, bottom quartile of its group
before-after | ugc-video | creator-07 | bau | day-pack | lofi | 2026-03-01 (120000000018): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: ctr, bottom quartile of its group
  weak: cvr, bottom quartile of its group
sale-bundle | carousel | house | promo | camp-stove | polished | 2026-03-09 (120000000024): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: ctr, bottom quartile of its group
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
new-drop | carousel | house | launch | sleeping-bag | polished | 2026-03-06 (120000000007): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: ctr, bottom quartile of its group
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
partnership-haul | partnership | creator-03 | bau | day-pack | lofi | 2026-03-01 (120000000008): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group
  weak: ctr, bottom quartile of its group
sale-percent-off | static | house | promo | sleeping-bag | polished | 2026-03-09 (120000000012): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: ctr, bottom quartile of its group
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
founder-story | founder-video | founder | bau | trail-boot | lofi | 2026-03-01 (120000000006): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group
fix-it-yourself | ugc-video | creator-12 | bau | camp-stove | lofi | 2026-03-01 (120000000028): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hook rate, bottom quartile of its group
  weak: cvr, bottom quartile of its group
partnership-trail | partnership | creator-06 | promo | trail-boot | lofi | 2026-03-09 (120000000016): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hold rate, bottom quartile of its group
sale-last-chance | ugc-video | creator-08 | promo | rain-shell | lofi | 2026-03-16 (120000000019): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: hold rate, bottom quartile of its group
  weak: ctr, bottom quartile of its group
new-drop-four | ugc-video | creator-13 | launch | headlamp | lofi | 2026-03-27 (120000000030): creative
  a step the ad controls is weak or falling while the site steps hold: the creative is the place to work
  weak: ctr, bottom quartile of its group
  n/a (fewer than twice the window (2 x 6 delivery days): the ad's start and end cannot be compared)
comparison | static | house | bau | headlamp | polished | 2026-03-01 (120000000014): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
packing-list | carousel | house | bau | camp-stove | polished | 2026-03-01 (120000000009): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
staff-picks | carousel | house | bau | trail-boot | polished | 2026-03-01 (120000000021): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
problem-cold-feet | ugc-video | creator-10 | bau | sleeping-bag | lofi | 2026-03-01 (120000000023): neither
  no funnel step is weak or falling against the ad's own group or its own start
unboxing | ugc-video | creator-05 | launch | camp-stove | lofi | 2026-03-13 (120000000015): neither
  no funnel step is weak or falling against the ad's own group or its own start
social-proof | static | house | bau | day-pack | polished | 2026-03-01 (120000000003): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
new-drop-two | carousel | house | launch | water-bottle | polished | 2026-03-13 (120000000013): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
social-proof-reviews | static | house | bau | rain-shell | polished | 2026-03-01 (120000000026): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
gift-guide-two | carousel | house | promo | day-pack | polished | 2026-03-11 (120000000029): neither
  no funnel step is weak or falling against the ad's own group or its own start
  weak: cvr, bottom quartile of its group
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
sale-countdown | static | house | promo | tent-2p | polished | 2026-03-09 (120000000004): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
new-drop-three | static | house | launch | day-pack | polished | 2026-03-19 (120000000025): neither
  no funnel step is weak or falling against the ad's own group or its own start
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
gift-guide | carousel | house | promo | headlamp | polished | 2026-03-09 (120000000005): neither
  no funnel step is weak or falling against the ad's own group or its own start
  weak: cvr, bottom quartile of its group
  hook rate: n/a (missing video_views_3s)
  hold rate: n/a (missing video_thruplay)
partnership-camp | partnership | creator-11 | launch | water-bottle | lofi | 2026-03-19 (120000000027): neither
  no funnel step is weak or falling against the ad's own group or its own start

For a site call, work through references/page-checklist.md before changing the ad.
```
