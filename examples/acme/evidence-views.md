# Acme account evidence for the make skills

Generated, not hand-written, on the fictional Acme Outdoor Co. fixture (synthetic data, not a real account). One evidence script feeds persona-builder, hook-writer and creative-ideation; each view below is what that skill reads before it writes anything.

## Persona view (extended export, which carries the audience ad set and new-customer purchases)

`python3 -I skills/persona-builder/scripts/evidence.py examples/acme/ads_daily_extended.csv --for persona`

```text
Persona evidence
Basis: this account's own ads, 2026-03-01 to 2026-03-30, each graded against ads of the same format. Never a benchmark.
Settings (arbitrary defaults, set them from your own account): window=6 days, min-change=8%, min-impressions=1000. Ad types used to seed gaps: bau.

Results by adset_name (pooled over each group's ads; vs account = the group's rate as a percent of the account's own pooled rate, 100 = the same; account roas 4.38, cpa 28.64):
  gear-upgraders: 5 ads, 24% of spend, roas 5.47 (125% of account), cpa 25.99, new-customer share 55%
    top-quartile ads: 120000000021, 120000000026; bottom-quartile ads: 120000000014, 120000000017; concepts: comparison, guarantee, social-proof, social-proof-reviews, staff-picks
  weekend-hikers: 5 ads, 23% of spend, roas 3.14 (72% of account), cpa 32.03, new-customer share 55%
    top-quartile ads: 120000000002; bottom-quartile ads: 120000000010, 120000000018, 120000000023; concepts: before-after, durability-test, problem-cold-feet, problem-first, weather-ready
  broad-prospecting: 10 ads, 22% of spend, roas 3.73 (85% of account), cpa 31.26, new-customer share 48%
    top-quartile ads: none; bottom-quartile ads: 120000000005, 120000000013, 120000000015, 120000000020, 120000000030; concepts: founder-note, gift-guide, gift-guide-two, new-drop, new-drop-four, new-drop-three, new-drop-two, partnership-camp, partnership-trail, unboxing
  family-campers: 6 ads, 22% of spend, roas 4.74 (108% of account), cpa 27.94, new-customer share 55%
    top-quartile ads: 120000000022; bottom-quartile ads: 120000000009; concepts: behind-the-seams, fix-it-yourself, founder-story, packing-list, partnership-haul, trail-diary
  past-visitors: 4 ads, 9% of spend, roas 5.38 (123% of account), cpa 25.08, new-customer share 28%
    top-quartile ads: 120000000024, 120000000019; bottom-quartile ads: 120000000012; concepts: sale-bundle, sale-countdown, sale-last-chance, sale-percent-off

Angles (concepts) by how their ads did: winning = a top-quartile ad and no weak one; losing = weak or never-worked ads and no top-quartile one; mixed = both; middle = graded, none top or weak; ungraded = too few comparable ads to grade; unjudged = too little delivery:
  staff-picks [winning]: ads 120000000021; 6% of spend; formats carousel
  social-proof-reviews [winning]: ads 120000000026; 3% of spend; formats static
  sale-bundle [winning]: ads 120000000024; 3% of spend; formats carousel
  trail-diary [winning]: ads 120000000022; 3% of spend; formats partnership
  problem-first [winning]: ads 120000000002; 2% of spend; formats ugc-video
  sale-last-chance [winning]: ads 120000000019; 2% of spend; formats ugc-video
  durability-test [middle]: ads 120000000001; 8% of spend; formats ugc-video; fatiguing: 120000000001
  behind-the-seams [middle]: ads 120000000011; 6% of spend; formats founder-video
  social-proof [middle]: ads 120000000003; 3% of spend; formats static
  new-drop [middle]: ads 120000000007; 3% of spend; formats carousel
  partnership-haul [middle]: ads 120000000008; 3% of spend; formats partnership
  gift-guide-two [middle]: ads 120000000029; 2% of spend; formats carousel
  sale-countdown [middle]: ads 120000000004; 2% of spend; formats static
  founder-story [middle]: ads 120000000006; 2% of spend; formats founder-video
  fix-it-yourself [middle]: ads 120000000028; 2% of spend; formats ugc-video
  partnership-trail [middle]: ads 120000000016; 2% of spend; formats partnership
  new-drop-three [middle]: ads 120000000025; 2% of spend; formats static
  partnership-camp [middle]: ads 120000000027; 1% of spend; formats partnership
  comparison [losing]: ads 120000000014; 8% of spend; formats static
  packing-list [losing]: ads 120000000009; 6% of spend; formats carousel
  weather-ready [losing]: ads 120000000010; 5% of spend; formats ugc-video
  problem-cold-feet [losing]: ads 120000000023; 5% of spend; formats ugc-video
  founder-note [losing]: ads 120000000020; 4% of spend; formats founder-video
  unboxing [losing]: ads 120000000015; 4% of spend; formats ugc-video
  before-after [losing]: ads 120000000018; 4% of spend; formats ugc-video
  new-drop-two [losing]: ads 120000000013; 3% of spend; formats carousel
  guarantee [losing]: ads 120000000017; 3% of spend; formats static
  sale-percent-off [losing]: ads 120000000012; 2% of spend; formats static
  gift-guide [losing]: ads 120000000005; 1% of spend; formats carousel
  new-drop-four [losing]: ads 120000000030; 1% of spend; formats ugc-video
```

## Hooks view

The hooks and ideation views read keep-or-kill's verdicts, and the ideation view also reads a competitor scan. Make those files first:

`python3 -I skills/keep-or-kill/scripts/verdicts.py examples/acme/ads_daily.csv --target roas=3 --json > verdicts.json`

`python3 -I skills/creative-ideation/scripts/evidence.py examples/acme/ads_daily.csv --for ideation --verdicts verdicts.json --json > evidence.json`

`python3 -I skills/competitor-scan/scripts/scan.py tests/fixtures/competitor_ads.csv --as-of 2026-03-30 --evidence evidence.json --json > scan.json`

`python3 -I skills/hook-writer/scripts/evidence.py examples/acme/ads_daily.csv --for hooks --verdicts verdicts.json`

```text
Hook evidence
Basis: this account's own ads, 2026-03-01 to 2026-03-30, each graded against ads of the same format. Never a benchmark.
Settings (arbitrary defaults, set them from your own account): window=6 days, min-change=8%, min-impressions=1000. Ad types used to seed gaps: bau.
Hook rate = 3-second plays / impressions; hold rate = ThruPlays / 3-second plays. Bands are quartiles within the ad's format. Verdicts: keep-or-kill.

Openings that stop people (top quartile, not faded): learn from these:
  120000000023 problem-cold-feet (ugc-video): hook 28.31 [top quartile], hold 33.33 [middle], 29 days old, verdict Check before cutting; opening: n/a (missing primary text: the export has no ad text column)
  120000000016 partnership-trail (partnership): hook 28.13 [top quartile], hold 28.95 [bottom quartile], 21 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)
  120000000027 partnership-camp (partnership): hook 27.33 [top quartile], hold 37.30 [top quartile], 11 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)
  120000000018 before-after (ugc-video): hook 26.80 [top quartile], hold 34.61 [top quartile], 29 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)
  120000000019 sale-last-chance (ugc-video): hook 26.79 [top quartile], hold 28.01 [bottom quartile], 14 days old, verdict Scale; opening: n/a (missing primary text: the export has no ad text column)

Openings that do not stop people (bottom quartile): do not reuse as they are:
  120000000006 founder-story (founder-video): hook 19.71 [bottom quartile], hold 36.10 [top quartile], 29 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)
  120000000028 fix-it-yourself (ugc-video): hook 25.14 [bottom quartile], hold 33.42 [middle], 29 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)
  120000000011 behind-the-seams (founder-video): hook 22.82 [bottom quartile], hold n/a [not graded (missing video_thruplay)], 29 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)
  120000000020 founder-note (founder-video): hook 24.37 [bottom quartile], hold 37.12 [top quartile], 14 days old, verdict Pause; opening: n/a (missing primary text: the export has no ad text column)
  120000000001 durability-test (ugc-video): hook 25.52 [bottom quartile], hold 28.43 [bottom quartile], 29 days old, verdict Iterate; opening: n/a (missing primary text: the export has no ad text column)
  120000000008 partnership-haul (partnership): hook 24.58 [bottom quartile], hold 31.41 [middle], 29 days old, verdict Keep; opening: n/a (missing primary text: the export has no ad text column)

Faded hooks (hook rate down by at least the min-change since the ad's first days): skip these as models, or vary them one change at a time:
  120000000022 trail-diary (partnership): hook 25.25 [middle], hold 32.78 [middle], 29 days old, verdict Scale; opening: n/a (missing primary text: the export has no ad text column)
  120000000001 durability-test (ugc-video): hook 25.52 [bottom quartile], hold 28.43 [bottom quartile], 29 days old, verdict Iterate; opening: n/a (missing primary text: the export has no ad text column)
```

## Ideation view, with the competitor scan

`python3 -I skills/creative-ideation/scripts/evidence.py examples/acme/ads_daily.csv --for ideation --verdicts verdicts.json --competitor scan.json`

```text
Ideation evidence
Basis: this account's own ads, 2026-03-01 to 2026-03-30, each graded against ads of the same format. Never a benchmark.
Settings (arbitrary defaults, set them from your own account): window=6 days, min-change=8%, min-impressions=1000. Ad types used to seed gaps: bau.
Verdicts: keep-or-kill.

Angles (concepts) by how their ads did: winning = a top-quartile ad and no weak one; losing = weak or never-worked ads and no top-quartile one; mixed = both; middle = graded, none top or weak; ungraded = too few comparable ads to grade; unjudged = too little delivery:
  staff-picks [winning]: ads 120000000021; 6% of spend; formats carousel
  social-proof-reviews [winning]: ads 120000000026; 3% of spend; formats static
  sale-bundle [winning]: ads 120000000024; 3% of spend; formats carousel
  trail-diary [winning]: ads 120000000022; 3% of spend; formats partnership
  problem-first [winning]: ads 120000000002; 2% of spend; formats ugc-video
  sale-last-chance [winning]: ads 120000000019; 2% of spend; formats ugc-video
  durability-test [middle]: ads 120000000001; 8% of spend; formats ugc-video; fatiguing: 120000000001
  behind-the-seams [middle]: ads 120000000011; 6% of spend; formats founder-video
  social-proof [middle]: ads 120000000003; 3% of spend; formats static
  new-drop [middle]: ads 120000000007; 3% of spend; formats carousel
  partnership-haul [middle]: ads 120000000008; 3% of spend; formats partnership
  gift-guide-two [middle]: ads 120000000029; 2% of spend; formats carousel
  sale-countdown [middle]: ads 120000000004; 2% of spend; formats static
  founder-story [middle]: ads 120000000006; 2% of spend; formats founder-video
  fix-it-yourself [middle]: ads 120000000028; 2% of spend; formats ugc-video
  partnership-trail [middle]: ads 120000000016; 2% of spend; formats partnership
  new-drop-three [middle]: ads 120000000025; 2% of spend; formats static
  partnership-camp [middle]: ads 120000000027; 1% of spend; formats partnership
  comparison [losing]: ads 120000000014; 8% of spend; formats static
  packing-list [losing]: ads 120000000009; 6% of spend; formats carousel
  weather-ready [losing]: ads 120000000010; 5% of spend; formats ugc-video
  problem-cold-feet [losing]: ads 120000000023; 5% of spend; formats ugc-video
  founder-note [losing]: ads 120000000020; 4% of spend; formats founder-video
  unboxing [losing]: ads 120000000015; 4% of spend; formats ugc-video
  before-after [losing]: ads 120000000018; 4% of spend; formats ugc-video
  new-drop-two [losing]: ads 120000000013; 3% of spend; formats carousel
  guarantee [losing]: ads 120000000017; 3% of spend; formats static
  sale-percent-off [losing]: ads 120000000012; 2% of spend; formats static
  gift-guide [losing]: ads 120000000005; 1% of spend; formats carousel
  new-drop-four [losing]: ads 120000000030; 1% of spend; formats ugc-video

Concept x format coverage (spend share, best band of any ad in the cell, youngest ad's age):
  before-after in ugc-video: ads 120000000018; 4% of spend; best middle; youngest 29 days
  behind-the-seams in founder-video: ads 120000000011; 6% of spend; best middle; youngest 29 days
  comparison in static: ads 120000000014; 8% of spend; best middle; youngest 29 days
  durability-test in ugc-video: ads 120000000001; 8% of spend; best top quartile; youngest 29 days
  fix-it-yourself in ugc-video: ads 120000000028; 2% of spend; best top quartile; youngest 29 days
  founder-note in founder-video: ads 120000000020; 4% of spend; best bottom quartile; youngest 14 days
  founder-story in founder-video: ads 120000000006; 2% of spend; best middle; youngest 29 days
  gift-guide in carousel: ads 120000000005; 1% of spend; best bottom quartile; youngest 21 days
  gift-guide-two in carousel: ads 120000000029; 2% of spend; best middle; youngest 19 days
  guarantee in static: ads 120000000017; 3% of spend; best bottom quartile; youngest 29 days
  new-drop in carousel: ads 120000000007; 3% of spend; best middle; youngest 24 days
  new-drop-four in ugc-video: ads 120000000030; 1% of spend; best bottom quartile; youngest 3 days
  new-drop-three in static: ads 120000000025; 2% of spend; best top quartile; youngest 11 days
  new-drop-two in carousel: ads 120000000013; 3% of spend; best middle; youngest 17 days
  packing-list in carousel: ads 120000000009; 6% of spend; best middle; youngest 29 days
  partnership-camp in partnership: ads 120000000027; 1% of spend; best top quartile; youngest 11 days
  partnership-haul in partnership: ads 120000000008; 3% of spend; best top quartile; youngest 29 days
  partnership-trail in partnership: ads 120000000016; 2% of spend; best middle; youngest 21 days
  problem-cold-feet in ugc-video: ads 120000000023; 5% of spend; best middle; youngest 29 days
  problem-first in ugc-video: ads 120000000002; 2% of spend; best top quartile; youngest 29 days
  sale-bundle in carousel: ads 120000000024; 3% of spend; best top quartile; youngest 21 days
  sale-countdown in static: ads 120000000004; 2% of spend; best middle; youngest 21 days
  sale-last-chance in ugc-video: ads 120000000019; 2% of spend; best top quartile; youngest 14 days
  sale-percent-off in static: ads 120000000012; 2% of spend; best bottom quartile; youngest 21 days
  social-proof in static: ads 120000000003; 3% of spend; best top quartile; youngest 29 days
  social-proof-reviews in static: ads 120000000026; 3% of spend; best top quartile; youngest 29 days
  staff-picks in carousel: ads 120000000021; 6% of spend; best top quartile; youngest 29 days
  trail-diary in partnership: ads 120000000022; 3% of spend; best top quartile; youngest 29 days
  unboxing in ugc-video: ads 120000000015; 4% of spend; best middle; youngest 17 days
  weather-ready in ugc-video: ads 120000000010; 5% of spend; best middle; youngest 29 days

Untried cells beside a winner (a hypothesis to test, not a result):
  problem-first in carousel
  problem-first in partnership
  problem-first in static
  social-proof-reviews in carousel
  social-proof-reviews in partnership
  social-proof-reviews in ugc-video
  staff-picks in partnership
  staff-picks in static

Competitor scan (Meta Ad Library (public)): 18 ads from 6 advertisers.
  Open ground: education; problem; proof; story; identity
  Worth testing: feature; problem; proof
  Not to chase: comparison; story; education
```
