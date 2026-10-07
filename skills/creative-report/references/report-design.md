# Report design

`scripts/report.py` fills `assets/report-template.html`. The template holds all styling; the script holds all content. Extend either without touching the other where you can.

## Rules

- One self-contained HTML file. Inline CSS and inline SVG, no JavaScript required. The only external request is the Google Fonts stylesheet (Plus Jakarta Sans and Inter), with system fonts as the fallback.
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

## Section order

1. What to do first (`headline`)
2. Basis (`basis_section`)
3. Pause, check, iterate, scale, keep (`verdict_section`)
4. Funnel diagnosis (`funnel_section`)
5. Creative mix (`mix_section`)
6. Notes and missing data (`notes_section`)

Footer: "Made with jumbo-creative-skills", the generated date, and "Numbers come from your own export; nothing left your machine."

## Adding a section

Write a function that returns `section(eyebrow, heading, inner)` and add it to the list in `build_html`. Put any new missing-data phrase through `collect_notes` so it reaches section 6. Use `bar_chart` and `scatter` for charts: every bar and dot needs a label, a unit and a title. Add a test in `tests/test_report.py` that the heading is present and the HTML stays balanced.

## Placeholders in the template

`{{title}}`, `{{eyebrow}}`, `{{heading}}`, `{{subtitle}}`, `{{body}}`, `{{generated}}`. Add a new one in the template and in the `fills` dict together.
