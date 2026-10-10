---
name: competitor-scan
description: Scan rivals' live Meta ads from the public Meta Ad Library - fetched where the agent can open the library, otherwise pasted or exported by the user - cluster them by angle, hook type, format and offer, and mark open ground, angles worth testing and ones not to chase against the brand's own winners. Use when the user asks what competitors are running, what angles a category is crowded with, or where there is room to stand out. Public data only; never stores rivals' images or videos.
license: MIT
metadata:
  version: "0.2.0"
  role: make
---

# Competitor scan

Reads what rivals are running so new concepts aim at open ground, not at the most crowded angle in the category. It never judges a rival's ad as good or bad: it can only see that an ad exists and how long it has run. A long run suggests an ad is working for them; it is not proof.

## Before you start

1. Ask which rivals to scan (three to eight names the user chooses) and which country to view the library in.
2. Get the ads, in this order:
   - **The agent can browse:** open https://www.facebook.com/ads/library as any visitor, search each rival, filter to active ads, and copy each ad's text, format, start date and call to action into a CSV (columns in `references/ad-library.md`). Only what the library shows a logged-out visitor. Never log in, never use anyone's session, never go past what the page shows.
   - **The agent cannot browse:** ask the user to do the same and paste the rows, or save a CSV.
   - **Nothing:** say so and offer the column list.
3. For the comparison with the brand's own winners, run the evidence script from `creative-ideation` (or `creative-brief`) with `--json` on the account's export.

## Run it

```
python3 -I scripts/scan.py rivals.csv --as-of 2026-03-30
python3 -I scripts/scan.py rivals.csv --evidence evidence.json --json > scan.json
python3 -I ../creative-ideation/scripts/evidence.py ads.csv --for ideation --competitor scan.json
```

`--long-days` (36) and `--crowded-share` (60) are arbitrary defaults: set them from how long ads usually run in the category and how many rivals you scan. Classification is a keyword first pass: read the clusters and correct anything misfiled before acting on it.

## What it shows

- **Clusters** by angle (problem, proof, offer, comparison, story, education, identity, feature, urgency), hook type (question, number, negative, how-to, testimonial, point-of-view, claim), offer type and format, with how many advertisers use each and how many of those ads have run long.
- **Crowded:** angles most rivals use. Standing out there takes a better execution, not just the angle.
- **Open ground:** angles one rival or none uses.
- **Worth testing:** angles rivals keep running that the brand has not tried, and the brand's own winning angles where rivals are thin.
- **Not to chase:** angles the brand's own ads say have not worked for it, however popular they are with rivals.

## Present the result

1. Lead with the three lines it prints: most crowded, best open ground, top worth-testing.
2. Show the clusters as a short table, and say how many ads and advertisers it is based on, and the date.
3. Give each worth-testing angle a one-line concept direction, and hand the scan to `creative-ideation` with `--competitor`.
4. **Next step:** `creative-ideation` for concepts on the open ground, `hook-writer` for openings that differ from the crowd's hook types.

## Guardrails

- Public data only: what the Ad Library shows any visitor. No logins, no scraping past the page, no automated bulk collection.
- Text only. Never download, save, commit or embed rivals' images or videos; the script strips every URL it sees and keeps no ad text unless asked (`--keep-text`). Do not copy a rival's wording into the brand's ads.
- Never claim to know a rival's results, spend or audience. The library does not show them for most ads.
- Do not name rivals in anything shared outside the user's team without their say.
- Read only: never call a tool that changes the brand's ad account.

## How to use

Have ready: the rivals' names and the country, or a pasted list of their ads.

Try:

- "What are my three main competitors running on Meta right now?"
- "Which angles is my category crowded with?"
- "Where is the open ground compared with what works for us?"

## Common questions

- **Can it see rivals' results?** No. Only that an ad exists and how long it has run.
- **Does it save their ads?** No: text only, URLs stripped, no media kept.
- **Is a long-running ad a winner?** A hint, not proof. Some ads run long because nobody switched them off.
- **Why is an angle in "not to chase"?** Your own ads on that angle have not worked, whatever rivals do.
- More: creative-context/references/faq.md
