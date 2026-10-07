# Acme creative-mix output

Generated, not hand-written: `python3 skills/creative-mix/scripts/mix.py examples/acme/ads_daily.csv` on the fictional Acme Outdoor Co. fixture.

```text
Basis: this account's own ads. Window 2026-03-01 to 2026-03-30. Shares are of classified spend (119506); roas and cpa are pooled from summed spend, conversions and value.
Classified: 30 ads. unclassified: 0 ads, spend 0 (names that do not match the naming convention are listed, never dropped).
Concept grouping: '-suffix' variants share a family (--no-family turns it off). Top quartile = at or above p75 of pooled ROAS across this account's BAU concepts or formats.

By format
format         ads  spend  share%  roas  cpa  
ugc-video      9    37318  31.2    3.26  33.71
carousel       7    29684  24.8    5.68  23.15
static         7    28216  23.6    4.53  28.91
founder-video  3    14901  12.5    3.86  35.73
partnership    4    9387   7.9     5.16  24.01

By concept family (several ads of one family count as ONE concept and one fatigue clock)
concept family     ads  spend  share%  roas  cpa    grouped from                                         
comparison         1    9973   8.3     4.46  27.78  -
new-drop           4    9491   7.9     4.68  24.65  new-drop, new-drop-four, new-drop-three, new-drop-two
durability-test    1    9062   7.6     3.39  30.72  -
packing-list       1    7698   6.4     4.40  27.49  -
social-proof       2    7603   6.4     6.68  20.72  social-proof, social-proof-reviews
staff-picks        1    7543   6.3     8.02  20.39  -
behind-the-seams   1    7333   6.1     4.93  32.02  -
weather-ready      1    5628   4.7     2.70  38.03  -
problem-cold-feet  1    5481   4.6     2.65  39.43  -
founder-note       1    4943   4.1     2.55  59.56  -
unboxing           1    4833   4.0     2.94  46.03  -
before-after       1    4267   3.6     2.72  44.91  -
gift-guide         2    4156   3.5     4.11  27.52  gift-guide, gift-guide-two
guarantee          1    3366   2.8     0.00  n/a    -
sale-bundle        1    3300   2.8     8.13  17.55  -
trail-diary        1    3248   2.7     5.87  21.51  -
partnership-haul   1    2993   2.5     6.19  26.25  -
sale-countdown     1    2761   2.3     5.58  26.30  -
problem-first      1    2752   2.3     4.85  16.00  -
sale-percent-off   1    2681   2.2     1.63  43.95  -
founder-story      1    2625   2.2     3.32  25.00  -
fix-it-yourself    1    2482   2.1     3.48  38.19  -
partnership-trail  1    2148   1.8     3.13  28.63  -
sale-last-chance   1    2143   1.8     5.57  26.79  -
partnership-camp   1    999    0.8     4.07  19.58  -

By ad type (shown separately, never blended: promo and BAU do different jobs)
ad type  ads  spend  share%  roas  cpa  
bau      16   82052  68.7    4.46  28.40
launch   7    20266  17.0    3.71  32.48
promo    7    17188  14.4    4.79  26.04

Concept x format grid (ads / spend; gap = no ad)
concept            ugc-video  carousel  static    founder-video  partnership
comparison         gap        gap       1 / 9973  gap            gap
new-drop           1 / 670    2 / 6989  1 / 1832  gap            gap
durability-test    1 / 9062   gap       gap       gap            gap
packing-list       gap        1 / 7698  gap       gap            gap
social-proof       gap        gap       2 / 7603  gap            gap
staff-picks        gap        1 / 7543  gap       gap            gap
behind-the-seams   gap        gap       gap       1 / 7333       gap
weather-ready      1 / 5628   gap       gap       gap            gap
problem-cold-feet  1 / 5481   gap       gap       gap            gap
founder-note       gap        gap       gap       1 / 4943       gap
unboxing           1 / 4833   gap       gap       gap            gap
before-after       1 / 4267   gap       gap       gap            gap
gift-guide         gap        2 / 4156  gap       gap            gap
guarantee          gap        gap       1 / 3366  gap            gap
sale-bundle        gap        1 / 3300  gap       gap            gap
trail-diary        gap        gap       gap       gap            1 / 3248
partnership-haul   gap        gap       gap       gap            1 / 2993
sale-countdown     gap        gap       1 / 2761  gap            gap
problem-first      1 / 2752   gap       gap       gap            gap
sale-percent-off   gap        gap       1 / 2681  gap            gap
founder-story      gap        gap       gap       1 / 2625       gap
fix-it-yourself    1 / 2482   gap       gap       gap            gap
partnership-trail  gap        gap       gap       gap            1 / 2148
sale-last-chance   1 / 2143   gap       gap       gap            gap
partnership-camp   gap        gap       gap       gap            1 / 999

Funnel stage
  Names carry no funnel stage field, so there is no funnel stage view. Add the field to your naming convention and pass --pattern to read it.

Read-outs
  Top quartile on pooled ROAS among BAU ads: concepts partnership-haul, social-proof, staff-picks, trail-diary; formats carousel, partnership.
  Gaps worth testing: empty or single-ad cells beside a top-quartile concept or format, strongest first. A hypothesis to test, not a result:
    partnership-haul in carousel: gap (top concept and top format)
    social-proof in carousel: gap (top concept and top format)
    social-proof in partnership: gap (top concept and top format)
    staff-picks in partnership: gap (top concept and top format)
    trail-diary in carousel: gap (top concept and top format)
    partnership-haul in partnership: 1 ad (top concept and top format)
    staff-picks in carousel: 1 ad (top concept and top format)
    trail-diary in partnership: 1 ad (top concept and top format)
    ... 51 more (see --json)
  Over-reliance: no concept family or format holds more than 50% of spend.
  Near-duplicates counted as one concept (override with --no-family):
    new-drop: new-drop, new-drop-four, new-drop-three, new-drop-two (ads 120000000007, 120000000013, 120000000025, 120000000030)
    social-proof: social-proof, social-proof-reviews (ads 120000000003, 120000000026)
    gift-guide: gift-guide, gift-guide-two (ads 120000000005, 120000000029)
```
