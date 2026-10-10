# Acme competitor-scan output

Generated, not hand-written. The rivals ("Rival A" to "Rival F") and their ad copy are invented for this example; the brand side is the fictional Acme Outdoor Co. fixture.

First, the two files it reads, keep-or-kill's verdicts and the brand's own evidence:

`python3 -I skills/keep-or-kill/scripts/verdicts.py examples/acme/ads_daily.csv --target roas=3 --json > verdicts.json`

`python3 -I skills/creative-ideation/scripts/evidence.py examples/acme/ads_daily.csv --for ideation --verdicts verdicts.json --json > evidence.json`

Then:

`python3 -I skills/competitor-scan/scripts/scan.py tests/fixtures/competitor_ads.csv --as-of 2026-03-30 --evidence evidence.json`

```text
Most crowded angle: offer, used by 6 of 6 advertisers.
Best open ground: education: used by 1 of 6 advertisers.
Top worth testing: feature: rivals run it long (long-running ads: 1, advertisers using it: 2); you have not tried it.

18 ads from 6 advertisers, as of 2026-03-30 (source: Meta Ad Library (public)).
Removed 18 URLs from the text; images and videos are not downloaded or kept.
Long-running (36 or more days; a long run suggests the ad is working for them, it is not proof): 7 ads.

Crowded:
  offer: used by 6 of 6 advertisers (100%) | your side: sale-bundle: winning; sale-last-chance: winning; gift-guide-two: middle; sale-countdown: middle; sale-percent-off: losing; gift-guide: losing

Open ground:
  education: used by 1 of 6 advertisers | your side: gift-guide-two: middle; gift-guide: losing
  problem: used by 1 of 6 advertisers | your side: problem-first: winning; problem-cold-feet: losing
  proof: used by 1 of 6 advertisers | your side: social-proof-reviews: winning; social-proof: middle
  story: used by 1 of 6 advertisers | your side: behind-the-seams: middle; founder-story: middle; founder-note: losing
  identity: used by 1 of 6 advertisers | your side: not tried

Worth testing:
  feature: rivals run it long (long-running ads: 1, advertisers using it: 2); you have not tried it | your side: not tried
  problem: your own ads win with it and rivals are thin there (advertisers using it: 1) | your side: problem-first: winning; problem-cold-feet: losing
  proof: your own ads win with it and rivals are thin there (advertisers using it: 1) | your side: social-proof-reviews: winning; social-proof: middle

Not to chase:
  comparison: your own ads say this has not worked for you | your side: comparison: losing
  story: your own ads say this has not worked for you | your side: behind-the-seams: middle; founder-story: middle; founder-note: losing
  education: your own ads say this has not worked for you | your side: gift-guide-two: middle; gift-guide: losing

By angle (ads, advertisers, long-running):
  offer: 7, 6, 1
  unclassified: 3, 3, 1
  comparison: 2, 2, 1
  feature: 2, 2, 1
  urgency: 2, 2, 0
  education: 1, 1, 1
  identity: 1, 1, 0
  problem: 1, 1, 1
  proof: 1, 1, 1
  story: 1, 1, 1

By hook type (ads, advertisers, long-running):
  claim: 11, 5, 4
  number: 2, 2, 0
  how-to: 1, 1, 1
  negative: 1, 1, 1
  pov: 1, 1, 0
  question: 1, 1, 1
  testimonial: 1, 1, 0

By offer (ads, advertisers, long-running):
  none: 12, 6, 6
  bundle: 1, 1, 0
  free shipping: 1, 1, 0
  gift with purchase: 1, 1, 0
  money off: 1, 1, 0
  percent off: 1, 1, 0
  tiered: 1, 1, 1

By format (ads, advertisers, long-running):
  image: 9, 6, 2
  video: 6, 6, 4
  carousel: 3, 3, 1

The sorting is a keyword first pass, not a verdict: read the ads and correct it.
```
