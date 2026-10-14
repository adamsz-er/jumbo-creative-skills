# Choosing a naming schema

The convention itself (separators, `KEY:value` segments, the key map, how names are read) lives in `creative-context/references/naming-convention.md`. This page is about which fields to put in a name and why.

## What each field buys

| Field | What it lets you answer later | Write it as |
|---|---|---|
| `concept` | Which ideas work, across every format they were made in | a short slug for the idea: `durability-test` |
| `format` | Which executions work, across every idea | `static`, `carousel`, `ugc-video`, `founder-video`, `partnership` |
| `creator` | Whether a face carries the result or the idea does | `creator-01`, `founder`, `house` |
| `ad_type` | Keeps launches and sales from being compared with evergreen ads | one of `bau`, `promo`, `launch`, `hype`, `partnership`, `retention` |
| `product` | Which product an ad sells, so a stock problem can be paused fast | `trail-boot` |
| `tone` | Polished against lo-fi | `polished`, `lofi` |
| `persona` | Who the ad was written for, so `persona-builder` can read results by persona | a slug from the brand profile: `weekend-hiker` |
| `hook` | Which opening pattern it uses, so `hook-writer` can compare patterns | an archetype from `hook-writer/references/hook-archetypes.md`: `question` |
| `funnel_stage` | Prospecting against retargeting, judged apart | `prospecting`, `retargeting` |
| `offer` | Which offer mechanic ran, so `sale-planner` can compare them | `gwp`, `bogo`, `percent-off`, `free-shipping`, `none` |
| `market` | Markets judged apart | an upper-case code: `US` |
| `version` | Which one-change variant this is | `v1`, `v2` |
| `launch_date` | Age and fatigue, even when the export has no creation date | `2026-03-01` |

## Rules of thumb

- **Idea before execution.** Put `concept` before `format`, so a sorted list groups by idea.
- **One variable per version.** A `v2` should differ from `v1` in one thing, named in the brief. Otherwise the result cannot say what mattered.
- **Fewer fields, always filled.** A field that is blank on most ads is noise. Pick the fields the team will fill every time.
- **Slugs, not sentences.** Lowercase, hyphens, no separator characters inside a value. The script enforces this.
- **Dates in ISO.** `2026-03-01` sorts and never swaps day and month.
- **Keep the order.** Add new fields at the end, or use keyed segments so position does not matter.

## Applying a rename map

A rename keeps the ad id, so the ad's history stays with it. Check the map first (the `changed` and `missing_fields` columns), then apply it with Ads Manager's bulk edit or an import. Keep the CSV: it is the record of what each old name became.
