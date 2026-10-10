# Acme ad-namer output

Generated, not hand-written, on the fictional Acme Outdoor Co. fixture (synthetic data, not a real account). The rename map is a plan: nothing in any ad account is renamed.

## Audit the existing names

`python3 -I skills/ad-namer/scripts/namer.py audit examples/acme/ads_daily.csv --fields concept,format,persona,funnel_stage,version`

```text
100% of 30 names follow one convention; 3 target fields are missing from most names.

Separator: ' | ' (positional). Names read: 100% of 30.

Fields read from the names:
  concept: 30 of 30 names (100%)
  format: 30 of 30 names (100%)
  creator: 30 of 30 names (100%)
  ad_type: 30 of 30 names (100%)
  product: 30 of 30 names (100%)
  tone: 30 of 30 names (100%)
  launch_date: 30 of 30 names (100%)

Target fields:
  concept: on 30 of 30 names (100%)
  format: on 30 of 30 names (100%)
  persona: on 0 of 30 names (0%)
      lacks it: durability-test | ugc-video | creator-01 | bau | trail-boot | lofi | 2026-03-01
      lacks it: problem-first | ugc-video | creator-02 | bau | rain-shell | lofi | 2026-03-01
      lacks it: social-proof | static | house | bau | day-pack | polished | 2026-03-01
      lacks it: founder-story | founder-video | founder | bau | trail-boot | lofi | 2026-03-01
      lacks it: partnership-haul | partnership | creator-03 | bau | day-pack | lofi | 2026-03-01
      lacks it: packing-list | carousel | house | bau | camp-stove | polished | 2026-03-01
      lacks it: weather-ready | ugc-video | creator-04 | bau | rain-shell | lofi | 2026-03-01
      lacks it: behind-the-seams | founder-video | founder | bau | tent-2p | lofi | 2026-03-01
      ... 22 more
  funnel_stage: on 0 of 30 names (0%)
      lacks it: durability-test | ugc-video | creator-01 | bau | trail-boot | lofi | 2026-03-01
      lacks it: problem-first | ugc-video | creator-02 | bau | rain-shell | lofi | 2026-03-01
      lacks it: social-proof | static | house | bau | day-pack | polished | 2026-03-01
      lacks it: founder-story | founder-video | founder | bau | trail-boot | lofi | 2026-03-01
      lacks it: partnership-haul | partnership | creator-03 | bau | day-pack | lofi | 2026-03-01
      lacks it: packing-list | carousel | house | bau | camp-stove | polished | 2026-03-01
      lacks it: weather-ready | ugc-video | creator-04 | bau | rain-shell | lofi | 2026-03-01
      lacks it: behind-the-seams | founder-video | founder | bau | tent-2p | lofi | 2026-03-01
      ... 22 more
  version: on 0 of 30 names (0%)
      lacks it: durability-test | ugc-video | creator-01 | bau | trail-boot | lofi | 2026-03-01
      lacks it: problem-first | ugc-video | creator-02 | bau | rain-shell | lofi | 2026-03-01
      lacks it: social-proof | static | house | bau | day-pack | polished | 2026-03-01
      lacks it: founder-story | founder-video | founder | bau | trail-boot | lofi | 2026-03-01
      lacks it: partnership-haul | partnership | creator-03 | bau | day-pack | lofi | 2026-03-01
      lacks it: packing-list | carousel | house | bau | camp-stove | polished | 2026-03-01
      lacks it: weather-ready | ugc-video | creator-04 | bau | rain-shell | lofi | 2026-03-01
      lacks it: behind-the-seams | founder-video | founder | bau | tent-2p | lofi | 2026-03-01
      ... 22 more
```

## Write a rename map

`python3 -I skills/ad-namer/scripts/namer.py map examples/acme/ads_daily.csv --fields concept,format,funnel_stage,version,launch_date --fill funnel_stage=prospecting,version=1 -o rename-map.csv`

```text
30 ads read; 30 of their names change.
Every field has a value for every ad.
New names that collide: 0 (0 ads share a name).
Wrote rename-map.csv.
This file is a plan: nothing in your ad account has been renamed. Apply it yourself in Ads Manager (or bulk edit), after checking it.
```
