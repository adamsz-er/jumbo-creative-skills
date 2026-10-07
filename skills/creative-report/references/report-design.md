# Report design

`scripts/report.py` assembles the page and fills `assets/report-template.html`. The template holds all styling, the header frame and the small tab script; `scripts/panels.py` holds one function per panel, `scripts/charts.py` the SVG charts and `scripts/previews.py` the image embedding and `scripts/interact.py` the per-ad records, facets, smart views, group subtotals and how-to-improve wording (no HTML). Extend any of them without touching the others where you can.

## Rules

- One self-contained HTML file. Inline CSS and inline SVG; images are data URIs, never URLs. A small inline script turns the stacked sections into tabs and keeps the hash in sync, and the page reads correctly without it (every section visible, nothing hidden by inline style). The only external request is the Google Fonts stylesheet (Plus Jakarta Sans and Inter), with system fonts as the fallback.
- Branding: a lockup of the Jumbo wordmark (`assets/jumbo-logo.svg` for light, `assets/jumbo-logo-dark.svg` for dark: same drawing, lighter gradient stops), a thin divider, "by" and the Elephant Room logo (`assets/er-logo.svg` is the white and amber variant for dark mode, `assets/er-logo-dark.svg` the ink and amber one for light), in the header (28 px) and the footer (20 px), and no other brand mark. Every gradient and clip id gets a per-instance suffix. The account label is the subject, never the branding.
- Responsive to a 390 px phone width, light and dark (`prefers-color-scheme`), and print-friendly (`@media print`).
- Lead with the answer. Every section opens with its point; detail sits underneath.
- Every number comes from the inputs. Nothing in the page is typed by hand, and a missing value reads `n/a (missing <field>)`, never 0.
- Escape every string that came from the data.

## Tokens

Defined once as CSS custom properties at the top of the template.

| Token | Value | Use |
|---|---|---|
| violet accent | `#7c3aed` | eyebrows, accents, keep bars |
| violet button | `#6d28d9` | buttons if you add any |
| violet 50 / 100 / 200 | `#f5f3ff` / `#ede9fe` / `#ddd6fe` | soft surfaces, chips, dark-mode text |
| violet 600 / 900 | `#7c3aed` / `#4c1d95` | accent text on light |
| ink 50 | `#f8f8fb` | page base (never flat white), with a soft radial violet glow |
| ink 200 | `#e2e1ea` | dividers |
| ink 500 | `#6b6889` | body text |
| ink 900 | `#0a0227` | headings; dark-mode base |
| dark elevated | `#1a103d` | dark-mode cards |
| success | `#059669` | scale |
| error | `#dc2626` | kill |
| warning | `#e8ad00` | iterate |
| info | `#343CED` | check before cutting, gradient start |

Type: Plus Jakarta Sans for headings (tight negative letter-spacing, sentence case), Inter for body. One uppercase eyebrow per section. Radii 12 to 24 px, light shadows. One blue-to-violet gradient-text keyword in the title (the last word of `--title`).

## Layout (the order is part of the spec)

Header (sticky): logo, "<account label> creative review", date window, data source, currency, attribution, completeness badge, tab bar. Then six tabs, each a stacked `<section id="tab-...">`:

1. Overview analysis: key numbers (`kpi_strip`), performance over time (`over_time`), do these first (`do_first`), ways to improve (`ways_to_improve`), funnel (`funnel`)
2. Pareto: where the value comes from (`pareto`), the head and the long tail (`head_tail`)
3. Keep / kill: verdict board (`verdict_board`), fatigue (`fatigue`), all ads (`all_ads`)
4. Format, 5. White space, 6. Briefing: placeholders built by `not_built`, labelled "Not built in this version"

Footer: data and method (the matched funnel columns, every flag and default used, reconciliation, the missing-data notes), image counts, "by Elephant Room", the generated date and the privacy line.

## Panels and states

Every panel function takes the `Ctx` and returns `(html, state)`: `"data"` when filled and `"empty"` when it shows a labelled empty state with **why** and **how to get it** (`empty_state`). A panel is never dropped. Unknown is never zero: a missing operand reads `n/a (missing <field>)`, reach and frequency read `n/a (needs account-level reach)` without `--account`, and a single day has no sparkline and says so.

The ad card (`ad_card`) is the one component used wherever an ad appears: preview image, readable label (concept · creator · format · ad type, never the raw first name segment), ad id, spend with currency, what placed it, verdict chip, confidence and the plain-English sentence. Lists show the top `--top-n` as cards and collapse the rest into a closed `<details>` capped at `LIST_CAP` rows, so a 500-ad account stays readable.

## Adding a panel

Write `def my_panel(ctx) -> (html, state)` in `panels.py`, add it to `TABS` in the position the spec gives it, and send any new missing-data phrase through `collect_notes` in `report.py` so it reaches the footer. Use the chart helpers in `charts.py`: every bar and dot needs a label, a unit and a title. Add a test with the data state and the empty state in `tests/test_dashboard_panels.py`.

## Placeholders in the template

`{{title}}`, `{{heading}}`, `{{sprite}}`, `{{brand}}`, `{{meta}}`, `{{badge}}`, `{{nav}}`, `{{filterbar}}`, `{{body}}`, `{{footer}}`, `{{dialog}}`, `{{pool}}`, `{{data}}`. Add a new one in the template and in the `fills` dict together; a value is inserted once and never re-scanned, so text from the data cannot become a placeholder.

## Interaction layer

Everything below needs the page script; with scripts off every panel and card shows, grouped by verdict.

- **One JSON block.** `interact.payload_json` writes every ad (not only the top N) into `<script type="application/json" id="ad-data">`, with `<`, `>` and `&` turned into unicode escapes so no ad name can close the tag. The script reads that block only and builds the page with DOM calls, never by writing data into markup or code. A missing value is `null`, never 0. Verdict values in the block, the chips and the link are the board's own words: scale, keep, iterate, check, pause, too-early, cant-judge.
- **Facets** come from the block: a facet shows when it has at least `FACET_MIN_VALUES` values and is known for `FACET_KNOWN` of the ads (both arbitrary). Within a facet chips are OR, across facets AND; counts follow the other active facets. The smart views are the `PRESETS` tuple; "Biggest spenders" keeps `BIGGEST_N` ads (an arbitrary default).
- **Link state.** `#tab-keep-kill?verdict=pause%2Ccheck&q=boot&group=format&sort=roas` reopens the same view. Search, facets, `tiring`, `top`, `weak`, `group`, `sort` and `previews` are read back and validated.
- **Same numbers in Python and the browser.** Group and filtered-summary subtotals are ratios of sums (ROAS = purchase value / spend, CPA = spend / purchases). `interact.group_subtotals` renders the scripts-off view and the script recomputes it from the block; a test runs both on one fixture and compares.
- **The pool.** `{{pool}}` is an inert `<template>` holding every ad's full card, so a regrouped gallery can show any ad as a card; ads past the top N of a group are rebuilt as rows from the block. It adds roughly 5 KB per ad to the file. The "Open this ad" dialog clones the card's `<details>` body, so the two cannot drift.
- **How to improve** is `interact.improvement`: the verdict's next step, then the fix for the first weak funnel step from the grade output, then the other weak metrics. An ad with no grade data says "Not enough data to suggest a fix." and nothing else.
- **Words, not ids.** `interact.plain_ids` turns field ids in generated wording into the words a reader knows (3-second plays, purchase value) and `interact.humanise` reads a slug as words (UGC video, BAU); the raw value stays in the data attributes and the page JSON. Hook and hold rate, and the funnel's video steps, are read over video ads only and say how many ads that is.
- **Ratios over partial data.** ROAS and CPA are ratios of sums over the ads that have both operands; when that is fewer than the ads shown the text says "(X of Y ads)".
