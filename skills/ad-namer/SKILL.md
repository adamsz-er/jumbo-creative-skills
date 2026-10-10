---
name: ad-namer
description: Name Meta ads to a schema the user picks (concept, format, persona, hook, funnel stage, offer, version, launch date, in any order), audit how an account's existing ads are named, and write an old-to-new rename map as a CSV the user applies themselves. Use when the user asks for ad names, a naming convention, "my ad names are a mess", "rename my ads", or when a review could not read concepts from the names. Never renames anything in the account.
license: MIT
metadata:
  version: "0.2.0"
  role: make
---

# Ad namer

Names are how every other skill in this package reads an ad: the concept, the format, the persona and the funnel stage all come from them. This skill makes new names to a schema, checks the names an account already has, and writes a plan for renaming the old ones. It only writes files. It never renames, edits or publishes anything in the ad account, even when a connector offers tools that could.

It reuses the naming rules in `creative-context/references/naming-convention.md` (separators, `KEY:value` segments, the key map) and the same name reader the analyses use, so a name made here is a name the analyses can read back.

## Before you start

1. Look for `creative-profile.md` (from `creative-context`). Its `Script settings` block (key map, type map) applies to `audit` and `map` with `--profile creative-profile.md`.
2. Ask which fields the user wants and in what order, in one question. Offer the package's own order as a starting point (`concept | format | creator | ad_type | product | tone | launch_date`) and the fields that make later analysis sharper: `persona`, `hook`, `funnel_stage`, `offer`, `version`. `references/naming-schema.md` explains what each field buys.
3. Ask whether they want plain positions (`a | b | c`) or keyed segments (`CONCEPT:a | FMT:b`). Keyed names survive a field being added later; positional names are shorter.

## Run it

```
python3 -I scripts/namer.py make specs.csv --fields concept,format,persona,hook,funnel_stage,offer,version,launch_date
python3 -I scripts/namer.py make specs.csv --fields concept,format,persona,version --keyed --dedupe
python3 -I scripts/namer.py audit ads.csv --fields concept,format,persona,funnel_stage
python3 -I scripts/namer.py map ads.csv --fields concept,format,funnel_stage,version,launch_date --fill funnel_stage=prospecting,version=1 -o rename-map.csv
```

- `make` reads one row per new ad (columns named after the fields) and prints a name per row. Every name is parsed back with the package's own reader; a name that would not read back the same (a value holding the separator, say) is flagged. A missing value stops the run unless `--allow-missing`, which writes `unknown` and says so. Ad types go through the same synonyms as the analyses (`sale` is `promo`), and launch dates are written as ISO dates.
- `audit` reads every ad name in the export and reports the match rate, the fields it found and their coverage, which target fields most names lack, names used by more than one ad, and names that differ only by case or spacing.
- `map` writes `rename-map.csv` with `ad_id, old_name, new_name, missing_fields, changed`. Fields no name carries can be filled for every ad with `--fill`; otherwise they read `unknown` and are listed. It refuses to overwrite an existing file unless `--force`.

## Present the result

1. Lead with the audit sentence or the count of names made or changed.
2. For a map: say how many names change, which fields were filled or are unknown, and any collisions. Then say plainly: "This file is a plan. Nothing in your ad account has been renamed. Check it, then apply it yourself in Ads Manager (bulk edit or an import)."
3. Point out names flagged as not parsing back, and fix them before the user applies anything.
4. **Next step:** with readable names, `creative-review` and `creative-mix` can compare concepts and formats; `persona-builder` reads the `persona` field.

## Guardrails

- Read and write files only. Never call a connector tool that renames, edits, pauses or publishes. If the user asks you to apply the map, tell them this skill does not, and that their agent could only do it through the connector's own write tools if they ask for that directly.
- Never invent a field value from the creative: a persona or hook comes from the user or the existing name. Unknown stays `unknown`.
- Keep one schema per account. Changing field order mid-flight splits every report in two.
- No client data in examples: the examples use the fictional Acme Outdoor Co.

## How to use

Have ready: the fields you want, and an Ads Manager export or a list of names.

Try:

- "Name these nine new ads to our convention."
- "How messy are my ad names?"
- "Give me a rename plan so every ad carries its funnel stage."

## Common questions

- **Will it rename my ads?** No. It writes a CSV plan; you apply it.
- **Which order is best?** Whatever the team will keep. Idea before execution (concept before format) makes reports easier to read.
- **What if a field is unknown?** It writes `unknown` and lists it, never a guess.
- **Can it read my existing convention?** Yes: `audit` runs the same detection as `creative-context`.
- More: creative-context/references/faq.md
