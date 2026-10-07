---
name: creative-brief
description: Write a production-ready Meta (Facebook and Instagram) ad creative brief for any brand, built from evidence - what won, what faded, where the coverage gaps are - with hook, script, visual direction, copy, specs, naming and how it will be judged; also writes a creator brief with usage rights and disclosure. Use when the user wants a brief for a designer, editor, studio or creator, or needs to turn a concept into something that can be made. Works with no data.
license: MIT
metadata:
  version: "0.1.0"
  role: make
---

# Creative brief

Turns one chosen concept into a brief a producer can make without asking questions, and backs it with evidence from the account where there is any.

## Before you start

1. Look for `creative-profile.md` in the working directory (from `creative-context`). If it exists, read it and confirm it is current in one line.
2. If not, ask for the five essentials in one short round: **brand, product, audience, offer or calendar, tone**. Never block on this. Say what you assumed and mark it "assumed".
3. Ask which concept the brief is for. If there is none, offer `creative-ideation` first, or draft the brief from the user's description.
4. Ask who will make it: an in-house team, a studio, or a creator. A creator needs the creator brief as well.

## Inputs it can use if present

- Output of `creative-ideation`, `hook-writer` and `persona-builder`: the concept, the hook and the persona.
- `grade.md`, `verdicts.md`, `mix.md` from the analyse skills.
- An Ads Manager CSV (daily rows) or a Meta ads connector. For the connector, call read-only tools only (never one that activates, updates or changes anything), save every response to a JSON file, and convert them with `python3 -I scripts/from_mcp.py responses.json -o ads.csv --expect-spend <account total> --expect-impressions <account total> --expect-ads ids.txt` (list archived ads that delivered in the window too, step 3 there) as `creative-context/references/data-inputs.md` describes. A `WARNING` line or exit 3 means the pull does not reconcile: re-fetch or drop duplicates and run it again.

## Build the evidence

With data, run:

```
python3 -I scripts/evidence.py ads.csv          # ads.csv from the connector: see above
python3 -I scripts/evidence.py ads.csv --json
python3 -I scripts/evidence.py ads.csv --include-types bau,promo   # briefing a sale: promo winners seed gaps too
python3 -I scripts/evidence.py ads.csv --profile creative-profile.md --where market=US   # naming settings and one market
```

Pass the same `--profile` (or `--key-map` and `--type-map`) as the analyses, or keyed ad names will not yield concepts and the evidence comes back empty. `--where` keeps one scope, read from a column or the names.

It prints an **Evidence** block: top-quartile ads (every available payback metric top quartile for the ad's format) with the fields parsed from their names, ads that are fatiguing or never worked, and coverage gaps (evergreen concepts behind a winner that have no ad in a winning format). Everything is relative to the account's own ads in the same format, never a benchmark. `--include-types` (default `bau`) picks which ad types seed the gaps, and the header names the ones used. `--window`, `--min-change` and `--max-gaps` are arbitrary defaults: set them from the account. Paste the block into the brief. Hook wording is not in an export, so take the winning hook from the ad itself.

**With no data, write "Evidence: none available".** Never invent evidence, and never present a hunch as a result.

## Write the brief

Use `references/brief-template.md`. It covers: objective, persona and stage, single message, proof, offer and dates, ad type, format and placements, the hook (with alternates), script or shot list, on-screen text, visual direction, casting direction, tone, hero line, supporting line and CTA, mandatories and must-avoids, naming per deliverable, how it will be judged, and the evidence.

Rules for the content:

- **One objective:** one behaviour or feeling to unlock, stated so the result can be read.
- **One message:** if the brief needs "and", it is two ads.
- **Promo:** offer and dates come from the user. Sale creative states both.
- **Judging:** name the metrics and say they are read against the account's own median and quartiles in the same format and funnel stage, over a window the user sets. Never a target taken from outside the account.
- **Naming:** give every deliverable a name in the convention from `creative-context/references/naming-convention.md`.
- **Casting:** describe energy and situation. Never cast by ethnicity, body type or gender assumptions.

For a creator, also fill `references/creator-brief-template.md`.

## Output

1. The brief, in the template order, with every field filled or marked "to confirm".
2. The Evidence block.
3. A short list of assumptions and open questions for the user.
4. **Next step:** after the work comes back, run `creative-grader` and `keep-or-kill` on the new ads to read the result.

## Guardrails

- No invented performance claims, no benchmarks, no promises of results.
- Claims in the brief must be ones the brand can substantiate. Mark claims that need approval "needs sign-off" and name who approves, if the profile says.
- Regulated categories (health, finance, alcohol, weight loss and similar): flag them and tell the user to check the platform's ad policies and local advertising law before production.
- Creator work: usage rights, paid-use permission and the disclosure label must be written down before the ad runs; the platform's rules decide the label.
- Read only. Do not touch the ad account.
