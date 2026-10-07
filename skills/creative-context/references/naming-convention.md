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

## Other styles

Accounts often use their own order. `parse_name` reads any of these without being told:

- **Separators:** ` | `, `|`, ` _ `, `_` or ` - `. It uses the one that splits the names consistently.
- **KEY:value segments** (also `KEY=value`; KEY is 2-10 letters), in any order: `FMT:carousel | CONCEPT:dusk | MKT:US | TYPE:offer` or `THEME:campfire | FMT:reel | TYPE:launch`. A name counts as keyed only when at least half its parts are `KEY:value` or one key is in the map below; otherwise a colon inside a value (`promo: 2 for 1`) is just text and the name is read by position.
- **Unkeyed segments**, read by shape: a date is `launch_date` only if it is a real date (`2026-07-21`, `2026/07/21`, or day-first `21/07/2026`; a date such as `05/06/2026` whose day and month could swap is left unlabelled and listed unless another name settles the order, so ask the user); a country or region code (`US`, `UK`, `CA`, `DE`, `EU`, `INT`, `ROW`, ...) is `market` only in the position most names carry a market; a format word (image, static, video, carousel, collection, catalogue, ugc, reel, story, dpa) is `format`. Anything else is kept as `segment_<position>`, never dropped.
- **The original fixed order** above still applies to a name of exactly seven unkeyed parts, and to `--pattern` (an ordered field list that needs an exact part count).

### Key map

| Key (any case) | Field |
|---|---|
| TYPE, ADTYPE | `ad_type` |
| ANGLE, CONCEPT, THEME | `concept` |
| FMT, FORMAT | `format` |
| SKU, PROD, PRODUCT | `product` |
| COLL, COLLECTION | `collection` |
| RNG, RANGE | `range` |
| CR, CREATOR, TALENT | `creator` |
| MKT, MARKET, GEO, REGION | `market` |
| STG, STAGE, FUNNEL | `funnel_stage` |
| TONE | `tone` |
| LD, DATE, LAUNCH | `launch_date` |

A key that is not in this table needs no map: it is read from the values it takes across all names. If most are format words it is `format`; ad-type words or synonyms, `ad_type`; market codes, `market`; dates, `launch_date`. Otherwise it keeps its own lowercase name as a field, with one exception: when nothing else is the concept and exactly one unmapped key holds free text (more than one distinct value), that key is read as the concept and detection says so. With two or more such keys none is, detection names them, and you ask the user ONE question about which is the concept. A key counts only when more than half of all names carry it, and a key whose values are mostly numbers is never read as the concept. Detection reports each inference with its computed share and the key's coverage ("key X read as format because 92% of its values are format words; the key is in 97% of names"). Override or add keys with `--key-map "PX=concept"` on `detect_naming.py`, `grade.py`, `verdicts.py` and `mix.py`; the map always wins.

## Detect before you describe

Never tell the user how their names are structured from a handful of examples. Run detection on every ad name in the pull:

```
python3 scripts/detect_naming.py ads.csv
```

(`creative_metrics.detect_convention(names)` does the same in code.) It reports the separator, each field and the share of all names carrying it, the KEY:value keys, the conventions in use with counts, the overall match rate (the share of names where a format, concept or ad type was read) and the names that did not parse.

- **Report the match rate** with whatever you say about the convention.
- **Ask the user to confirm only when** the match rate is under 85% of names, or a second convention covers at least 5% of names (report both, with counts). Both numbers are arbitrary defaults: `--min-match-rate` sets the first, and you should set both from how tidy this account's names are.
- **Below those lines, do not ask.** A few stray names are listed as "unparsed / odd names" and you carry on. The user should not have to answer a question the data has already answered.
- Ad types outside the six in `ad-types.md` are asked about in one question that lists them. Never drop them.

## Grouping by anything the data carries

Columns in the export that are not metrics (market, objective, campaign name, ad set name, placement, country) are carried through per ad, taking the most common value. They work anywhere a grouping is accepted: `--group-by market` or `--group-by format,ad_type,market` in `grade.py`, `verdicts.py` and `mix.py`. A column the data does not have stops the run with `column <x> not in the data; available: ...`. Accounts that mix markets with very different reach costs should group by market, because a CPM that is cheap in one market is not comparable with another.

## How to use it

- Split names with `parse_name` in `scripts/creative_metrics.py`. A name that does not match returns nothing, and you report that instead of guessing.
- Group by concept when you read results. Several near-identical versions of one concept are one data point and one fatigue clock.
- Test one variable at a time. Same script with a different creator is a creator test, not a new concept.
- If the account has its own convention, map its fields to these names and keep its separator. Ask the user to confirm the mapping before tagging.
- Add a field when you add a new dimension (region, persona, funnel stage). Keep the order stable.
