# Naming convention

Ad names are what make theme-level and format-level reporting possible. Record the idea and its execution as separate fields, so a concept can be compared across formats and a format across concepts.

## Fields, in order

| Field | Meaning | Example |
|---|---|---|
| `concept` | The idea: the problem, proof, offer or emotion | `durability-test` |
| `format` | How it is made: static, carousel, ugc-video, founder-video, partnership | `ugc-video` |
| `creator` | Who fronts it, or `house` | `creator-01` |
| `ad_type` | One of the types in ad-types.md | `bau` |
| `product` | Product or collection, so a SKU can be paused fast | `trail-boot` |
| `tone` | Polished or lo-fi | `lofi` |
| `launch_date` | ISO date the ad went live | `2026-03-01` |

Example, pipe-separated: `durability-test | ugc-video | creator-01 | bau | trail-boot | lofi | 2026-03-01`

An underscore-separated version of the same fields also parses. Fields cannot contain the separator.

## How to use it

- Split names with `parse_name` in `scripts/creative_metrics.py`. A name that does not match returns nothing, and you report that instead of guessing.
- Group by concept when you read results. Several near-identical versions of one concept are one data point and one fatigue clock.
- Test one variable at a time. Same script with a different creator is a creator test, not a new concept.
- If the account has its own convention, map its fields to these names and keep its separator. Ask the user to confirm the mapping before tagging.
- Add a field when you add a pillar (region, persona, funnel stage). Keep the order stable.
