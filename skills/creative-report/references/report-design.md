# Report design

`scripts/report.py` assembles the page and fills `assets/report-template.html`. The template holds all styling, the header frame and the small tab script; `scripts/panels.py` holds one function per panel, `scripts/charts.py` the SVG charts and `scripts/previews.py` the image embedding. Extend any of them without touching the others where you can.

## Rules

- One self-contained HTML file. Inline CSS and inline SVG; images are data URIs, never URLs. A small inline script turns the stacked sections into tabs and keeps the hash in sync, and the page reads correctly without it (every section visible, nothing hidden by inline style). The only external request is the Google Fonts stylesheet (Plus Jakarta Sans and Inter), with system fonts as the fallback.
- Branding: the Elephant Room logo (`assets/er-logo.svg` is the white and amber variant for dark mode, `assets/er-logo-dark.svg` the ink and amber one for light) in the header and the footer, and no other brand mark. The account label is the subject, never the branding.
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

1. Overview analysis: key numbers (`kpi_strip`), performance over time (`over_time`), do these first (`do_first`), funnel (`funnel`)
2. Pareto: where the value comes from (`pareto`), the head and the long tail (`head_tail`)
3. Keep / kill: verdict board (`verdict_board`), fatigue (`fatigue`)
4. Format, 5. White space, 6. Briefing: placeholders built by `not_built`, labelled "Not built in this version"

Footer: data and method (the matched funnel columns, every flag and default used, reconciliation, the missing-data notes), image counts, "by Elephant Room", the generated date and the privacy line.

## Panels and states

Every panel function takes the `Ctx` and returns `(html, state)`: `"data"` when filled and `"empty"` when it shows a labelled empty state with **why** and **how to get it** (`empty_state`). A panel is never dropped. Unknown is never zero: a missing operand reads `n/a (missing <field>)`, reach and frequency read `n/a (needs account-level reach)` without `--account`, and a single day has no sparkline and says so.

The ad card (`ad_card`) is the one component used wherever an ad appears: preview image, readable label (concept · creator · format · ad type, never the raw first name segment), ad id, spend with currency, what placed it, verdict chip, confidence and the plain-English sentence. Lists show the top `--top-n` as cards and collapse the rest into a closed `<details>` capped at `LIST_CAP` rows, so a 500-ad account stays readable.

## Adding a panel

Write `def my_panel(ctx) -> (html, state)` in `panels.py`, add it to `TABS` in the position the spec gives it, and send any new missing-data phrase through `collect_notes` in `report.py` so it reaches the footer. Use the chart helpers in `charts.py`: every bar and dot needs a label, a unit and a title. Add a test with the data state and the empty state in `tests/test_dashboard_panels.py`.

## Placeholders in the template

`{{title}}`, `{{heading}}`, `{{logo_light}}`, `{{logo_dark}}`, `{{meta}}`, `{{badge}}`, `{{nav}}`, `{{body}}`, `{{footer}}`. Add a new one in the template and in the `fills` dict together; a value is inserted once and never re-scanned, so text from the data cannot become a placeholder.
