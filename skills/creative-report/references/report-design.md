# Report design

`scripts/report.py` assembles the page and fills `assets/report-template.html`. The template holds all styling, the header frame and the small tab script; `scripts/panels.py` holds one function per panel, `scripts/charts.py` the SVG charts and `scripts/previews.py` the image embedding and `scripts/interact.py` the per-ad records, facets, smart views, group subtotals and how-to-improve wording (no HTML). Extend any of them without touching the others where you can.

## Rules

- One self-contained HTML file. Inline CSS and inline SVG; images are data URIs, never URLs. A small inline script turns the stacked sections into tabs and keeps the hash in sync, and the page reads correctly without it (every section visible, nothing hidden by inline style). The only external request is the Google Fonts stylesheet (DM Sans and Roboto Mono), with Inter and system fonts as the fallback.
- Branding: a lockup of the Jumbo wordmark (`assets/jumbo-logo.svg` for light, `assets/jumbo-logo-dark.svg` for dark: same drawing, lighter gradient stops), a thin divider, "by" and the Elephant Room logo (`assets/er-logo.svg` is the white and amber variant for dark mode, `assets/er-logo-dark.svg` the ink and amber one for light), in the top bar (28 px) and the footer (20 px), and no other brand mark. Every gradient and clip id gets a per-instance suffix. The account label is the subject, never the branding.
- Responsive to a 390 px phone width, light and dark (`prefers-color-scheme`, or `data-theme` once the toggle has set it), and print-friendly (`@media print`: light tokens, no nav, filter row or toggle, every tab in order).
- Lead with the answer. Every section opens with its point; detail sits underneath.
- Every number comes from the inputs. Nothing in the page is typed by hand, and a missing value reads `n/a`, with its reason on a muted line (`n/a (missing <field>)` in running text), never 0.
- Reader words: ads, never rows; never a command flag (they live in `SKILL.md`). A metric missing for every ad gets one banner at the top of Overview and a plain "n/a" in its tile; a metric present on only some ads says "recorded on N of M ads; the rest had none in this window".
- Escape every string that came from the data.

## Tokens

Defined once as CSS custom properties at the top of the template; the values are borrowed from a production analytics UI, so charts, tiles and tables read as one family.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` / `--surface` | `#ffffff` | `hsl(222 35% 5%)` / `hsl(222 28% 11%)` | page and cards (dark depth is lightness, never `#000`) |
| `--surface-raised` | `#ffffff` | `hsl(222 28% 14%)` | popovers, the active segmented chip |
| `--surface-muted` | `hsl(210 40% 96.1%)` | `hsl(222 25% 17%)` | track behind the segmented control, table heads |
| `--text` / `--text-muted` | `hsl(222 47% 11%)` / `hsl(215 16% 47%)` | `hsl(210 20% 96%)` / `hsl(217 18% 68%)` | copy and labels |
| `--border` | `hsl(220 13% 91%)` | `hsl(222 18% 29%)` | 1 px card and row borders |
| `--accent` / `--accent-soft` | `hsl(251 97% 60%)` / 10% | `hsl(251 91% 64%)` | the one violet accent: eyebrows, active nav, links |
| `--bar`, `--bar-border`, `--bar-text` | `hsl(222 47% 8%)`, `hsl(217 33% 18%)`, `hsl(210 20% 96%)` | same | the dark scope bar, in both themes |
| `--up-*`, `--down-*`, `--flat-*` | `#dcfce7`/`#15803d`, `#fee2e2`/`#b91c1c`, `hsl(220 13% 91%)`/`hsl(220 9% 46%)` | 10% washes of green and red | delta pills |
| `--series-1` to `-6`, `--series-neutral` | `#6366f1 #10b981 #f59e0b #8b5cf6 #06b6d4 #f43f5e`, `#64748b` | same | chart bars, lines and dots |
| `--danger`, success, warning, info | `hsl(0 84% 60%)`, `#059669`, `#e8ad00`, `#343CED` | | verdict badges and the Reconciled / Totals don't match badge; Totals not checked uses the neutral `--flat-*` pill |

Type: DM Sans (400 to 700) with Inter and system fallbacks, Roboto Mono for code; root 15 px; every number tabular. Radius 10 px cards, 6 px controls, 999 px pills; spacing on a 4 px grid. Cards have a 1 px border and `0 1px 2px rgb(0 0 0 / .05)`; hover tints the border and adds a soft violet shadow, with no movement. A tile's delta pill is green when the change is good (down for CPM and CPA) and neutral for spend, impressions, reach and frequency.

## Layout (the order is part of the spec)

App shell, 1536 px wide: a 56 px top bar (lockup, "<account> · <scope> creative review", completeness badge, theme toggle); the dark scope bar (window, currency, source, attribution); then a 208 px sticky left sub-nav (the completeness badge reads Reconciled only when a reconcile ran and passed, amber Totals don't match when one fell short, neutral grey Totals not checked when none ran) beside the content column, with the sticky filter row above the first card. Under 1024 px the sub-nav is a segmented control. Six tabs, each a `<section id="tab-...">` whose first card opens it (no separate tab heading):

1. Overview analysis: key numbers (`kpi_strip`), performance over time (`over_time`), where the money went by format (`spend_by_format`), do these first (`do_first`), ways to improve (`ways_to_improve`), funnel (`funnel`)
2. Pareto: where the value comes from (`pareto`), the head and the long tail (`head_tail`)
3. Keep / kill: verdict board (`verdict_board`), fatigue (`fatigue`), performance by ad age (`ad_age`), new ads launched per week (`launches`), all ads (`all_ads`)
4. Format: scorecard (`format_scorecard`), benchmarks (`format_benchmarks`), formats over time (`formats_over_time`), spend share against return (`spend_vs_return`), hook against hold (`video_hook_hold`), retention (`video_retention`), ad types (`ad_type_split`)
5. White space: concept heatmap (`concept_heatmap`), stage heatmap (`stage_heatmap`), types with no creative (`no_creative_types`), markets and segments (`segments`), gap list (`gap_list`)
6. Briefing: ready briefs (`ready_briefs`), copy and call to action (`copy_cta`), prompts (`prompts_panel`)

Footer: data and method (the matched funnel columns, every flag and default used, reconciliation, the missing-data notes), image counts, "by Elephant Room", the generated date and the privacy line.

## Panels and states

Every panel function takes the `Ctx` and returns `(html, state)`: `"data"` when filled and `"empty"` when it shows a labelled empty state with **why** and **how to get it** (`empty_state`). A panel is never dropped. Unknown is never zero: a missing operand reads `n/a (missing <field>)`, reach and frequency read `n/a` without an account-level figure (one banner on Overview says why), and a single day has no sparkline and says so.

The ad card (`ad_card`) is the one component used wherever an ad appears: preview image, readable label (concept · creator · format · ad type, never the raw first name segment), ad id, spend with currency, what placed it, verdict chip, confidence and the plain-English sentence. Lists show the top N (`--top-n`) as cards and collapse the rest into a closed `<details>` capped at `LIST_CAP` ads, so a 500-ad account stays readable.

## Charts

Shared plumbing lives in `charts.py`. One colour per format for the whole page (`format_colours`: formats by total spend take `--series-1` to `--series-6`, the rest the muted tone), used by every format chart. Every mark carries `data-tip` text that one small script shows on hover or focus; a chart with more than `POINT_FOCUS_MAX` points is hover only. Legend chips are `<button data-series>` and toggle `.is-off` on that series' group (the last one stays on; a stacked chart dims a layer instead of leaving a gap). A measure switcher (`switcher`) pre-renders one view per measure: with scripts off every view shows stacked under its heading, with scripts on one shows. Time axes write at most `TICKS_WIDE` day labels and the narrow subset (`TICKS_NARROW`) under 480 px, and a narrow plot writes fewer. A missing day is a gap in the line, never a zero; a rolling average is the ratio of the window's sums and needs `ROLLING_MIN_VALUES` days with data.

Industry bands come only from `references/benchmarks.json`, read by `scripts/benchmarks.py`. Each entry names its source, URL, publication date, sample, metric definition and caveat. `benchmarks.lookup` returns a band or the plain reason there is none: our format word has no source key (a bare "ugc", "story" or a partnership is never guessed), the source does not cover that format, the figure is money in another currency, or the definition differs (hold rate). Every band drawn is cited under its chart and the footer lists each source used with its URL and year. Benchmarks never feed verdicts, grades or "Do these first".

Arbitrary defaults to set from your own account: the rolling window and its minimum days, the weekly impressions floor (`MIN_WEEK_IMPRESSIONS`), and the ad-age bucket edges (`AGE_EDGES`). The footer names them.

Key numbers that no ad in the pull can show (every ad n/a) are named once at the top of the Overview's first panel, in a "Not in this pull" notice with the reason and how to get them (`missing_everywhere`). The cells keep their own `n/a (missing ...)` text: the notice adds the explanation, it never replaces the label.

`report.py --check page.html` validates a built page's structure (tabs and panels in order, panel states, badge, Scope line, outside requests, inline scripts, n/a never shown as 0, size). Run it after a change and in any environment where you cannot open a browser; it does not replace looking at the page.

## Adding a panel

Write `def my_panel(ctx) -> (html, state)` in `panels.py`, add it to `TABS` in the position the spec gives it, and send any new missing-data phrase through `collect_notes` in `report.py` so it reaches the footer. Use the chart helpers in `charts.py`: every bar and dot needs a label, a unit and a title. Add a test with the data state and the empty state in `tests/test_dashboard_panels.py`.

## Placeholders in the template

`{{title}}`, `{{heading}}`, `{{sprite}}`, `{{brand}}`, `{{meta}}` (the scope-bar segments), `{{badge}}`, `{{nav}}`, `{{filterbar}}`, `{{body}}`, `{{footer}}`, `{{dialog}}`, `{{pool}}`, `{{data}}`. Add a new one in the template and in the `fills` dict together; a value is inserted once and never re-scanned, so text from the data cannot become a placeholder.

## Interaction layer

Everything below needs the page script; with scripts off every panel and card shows, grouped by verdict.

- **One JSON block.** `interact.payload_json` writes every ad (not only the top N) into `<script type="application/json" id="ad-data">`, with `<`, `>` and `&` turned into unicode escapes so no ad name can close the tag. The script reads that block only and builds the page with DOM calls, never by writing data into markup or code. A missing value is `null`, never 0. Verdict values in the block, the chips and the link are the board's own words: scale, keep, iterate, check, pause, too-early, cant-judge.
- **The filter row** is one sticky row (search, "Filters (n)" popover, Clear, "N of M ads", group, sort, previews only) with the summary line under it, not sticky. Under 640 px the group, sort and previews controls move into the Filters popover (a second copy of the same controls) instead of disappearing. The popover holds the smart views and the facets; with scripts off the row is not shown and every ad stays visible. The theme toggle sets `data-theme` and keeps the choice in `localStorage` inside try/catch, so a blocked store only forgets it.
- **Facets** come from the block: a facet shows when it has at least `FACET_MIN_VALUES` values and is known for `FACET_KNOWN` of the ads (both arbitrary). Within a facet chips are OR, across facets AND; counts follow the other active facets. The smart views are the `PRESETS` tuple; "Biggest spenders" keeps `BIGGEST_N` ads (an arbitrary default).
- **Link state.** `#tab-keep-kill?verdict=pause%2Ccheck&q=boot&group=format&sort=roas` reopens the same view. Search, facets, `tiring`, `top`, `weak`, `group`, `sort` and `previews` are read back and validated.
- **Same numbers in Python and the browser.** Group and filtered-summary subtotals are ratios of sums over every ad in view (ROAS = purchase value / spend, CPA = spend / purchases; an ad with no recorded value or purchases adds none; n/a only when no ad has any), the same basis as the key-number tiles. `interact.group_subtotals` renders the scripts-off view and the script recomputes it from the block; a test runs both on one fixture and compares.
- **The pool.** `{{pool}}` is an inert `<template>` holding every ad's full card, so a regrouped gallery can show any ad as a card; ads past the top N of a group are rebuilt as rows from the block. It adds roughly 5 KB per ad to the file. The "Open this ad" dialog clones the card's `<details>` body, so the two cannot drift.
- **How to improve** is `interact.improvement`: the verdict's next step, then the fix for the first weak funnel step from the grade output, then the other weak metrics. An ad with no grade data says "Not enough data to suggest a fix." and nothing else.
- **Words, not ids.** `interact.plain_ids` turns field ids in generated wording into the words a reader knows (3-second plays, purchase value) and `interact.humanise` reads a slug as words (UGC video, BAU); the raw value stays in the data attributes and the page JSON. Hook and hold rate, and the funnel's video steps, are read over video ads only and say how many ads that is.
- **Ratios over partial data.** One basis everywhere: ROAS and CPA divide over all ads in view, so a partly missing operand shows in the value, not in a suffix. The filtered summary and group headers append "value recorded on k of n ads" (or purchases) whenever only some ads carry it, in Python and the script alike. Tiles say how many ads recorded the field ("recorded on N of M ads; the rest had none in this window").

## Tabs 4 to 6

- **Sources.** Format, ad types, heatmaps, gaps and prompts read the creative-mix output (`--mix`); the scorecard's CTR, CPM, hook and hold are ratios of summed counts from the rows. Segments read the market from ad names and, only from `--breakdowns`, age, gender, placement, platform, region or country; each segment adds its own spend, purchases and value before dividing. Briefs come from `--briefs` (`briefing.validate_briefs`), else from starters.
- **Grading across formats** is by rank (`_grade_across`): best, middle or weakest, lowest best for CPM and CPA, equal values share a band and say "(tied)", and fewer than `MIN_FORMATS` formats with a value reads "not graded". An arbitrary default.
- **Retention** matches columns by normalised header (Video plays at 25, 50, 75, 95 and 100 percent, Video average play time, and the API names); the footer names each column read or not found. All five quartile columns are needed, else the panel is an empty state naming the missing ones. Lines are raw counts, so the y axis is a count.
- **Heatmaps** show the top `HEATMAP_CONCEPTS` concepts by spend and say how many are hidden. Gap numbers are the gap list's order (creative-mix order), so a number on a cell and a number in the list are the same gap.
- **Filter attributes.** Every ad shown in a new panel is a `.pv-tile` (or a table row) carrying `data-ad`, so the filter bar hides it; clicking a tile opens the same detail dialog as a card. A format strip with every ad filtered out folds away.
- **Prompts.** A copy button sits in a `.prompt-scope` beside a `<details>` holding the prompt text, so with scripts off the prompt is still readable. Prompts hold names only and no digits from the data.
