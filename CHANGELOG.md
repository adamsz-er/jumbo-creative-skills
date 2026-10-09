# Changelog

## 0.1.0 (unreleased)

- Eleven skills: `creative-context`, `creative-grader`, `keep-or-kill`, `creative-mix`, `creative-ideation`, `hook-writer`, `persona-builder`, `creative-brief`, `ad-transcript`, `colour-grade` and `creative-report`.
- One shared metrics module (`shared/creative_metrics.py`) synced into every skill, so each works on its own after install.
- Worked examples for the fictional Acme Outdoor Co. in `examples/acme/`, generated from a synthetic fixture, including a shareable HTML report.
- Per-skill and all-skills zips for Claude desktop and claude.ai (`tools/build_zips.py`), and a release workflow that attaches them when a version tag is pushed.
- Fatigue compares each ad's first and last 6 delivery days by default (an arbitrary default: set it from your own account); a trend needs at least two full windows of delivery days (twice the window).
- The creative report gains an interaction layer: a Jumbo and Elephant Room lockup, a filter bar (search, smart views, facet chips, a filtered summary), an All ads gallery with grouping, sorting and a previews-only grid, an "Open this ad" view with plain-word bands and how to improve it, a next-version prompt for weak ads, and a Ways to improve panel. Every state reopens from a copied link, and the page still shows everything with scripts off.
- Connector pulls work as the connector sends them. `from_mcp.py` reads the `ad_entities` wrapper, prints the connector's own notes (such as refused fields), names expected fields that no row carries, fills `market` from the ad names and carries leads. `data-inputs.md` adds steps for archived ads, batch sizing, lead fields, scoped reach, previews, attribution and the cost of a prior-period pull.
- A cost per 3-second view rounded too coarsely to trust (judged from its decimals; `DERIVE_MAX_ERROR`, an arbitrary default of 2%) is no longer turned into 3-second plays. An ad with any refused day has none, so hook and hold rate read n/a with the reason instead of a wrong number. The connector's `cost_per_video_view` name is read too.
- `--where market=US` (any column or name field) restricts grade, verdicts, mix and the report to one scope and says what it kept. Market codes are found per separator and from the end of a name, so short or older-style names keep their market.
- Naming: `--key-map` names unkeyed segments by position (`6=tone,7=creator`), `--type-map core=bau` reads an account's own ad-type words, and a `Script settings` block in the profile (read with `--profile`) carries key map, type map, targets and currency to every script.
- keep-or-kill pauses a never-worked ad only when it misses the user's own `--target`; without a target it is "Check before cutting" and asks for one.
- The report takes `--key-map`, `--type-map`, `--where` and `--scope`; `--title` now wins over the profile's brand; every judged card shows its comparison-group size; a "Not in this pull" notice explains metrics that are n/a for every ad; `report.py --check` validates a built page without a browser.
- Documented commands run under `python3 -I`.
- README restyled for GitHub: copyable install steps, dashboard screenshot.
- Docs: the README is rewritten as the front door (install, quick start, a diagram of how the skills fit, a which-skill table, known limits). New `docs/how-it-works.md` (with every command-line flag, kept in step with the scripts by a test), `docs/faq.md` and `docs/troubleshooting.md`; every skill gains "How to use" and "Common questions" sections, and `creative-context` carries an agent-facing FAQ so a single installed skill can still answer how-do-I questions.
- Dashboard spacing and layout polish.
- creative-report can publish the dashboard as a native Claude dashboard.
