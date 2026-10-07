# Changelog

## 0.1.0 (unreleased)

- Eleven skills: `creative-context`, `creative-grader`, `keep-or-kill`, `creative-mix`, `creative-ideation`, `hook-writer`, `persona-builder`, `creative-brief`, `ad-transcript`, `colour-grade` and `creative-report`.
- One shared metrics module (`shared/creative_metrics.py`) synced into every skill, so each works on its own after install.
- Worked examples for the fictional Acme Outdoor Co. in `examples/acme/`, generated from a synthetic fixture, including a shareable HTML report.
- Per-skill and all-skills zips for Claude desktop and claude.ai (`tools/build_zips.py`), and a release workflow that attaches them when a version tag is pushed.
- Fatigue compares each ad's first and last 6 delivery days by default (an arbitrary default: set it from your own account); a trend needs at least two full windows of delivery days (twice the window).
- The creative report gains an interaction layer: a Jumbo and Elephant Room lockup, a filter bar (search, smart views, facet chips, a filtered summary), an All ads gallery with grouping, sorting and a previews-only grid, an "Open this ad" view with plain-word bands and how to improve it, a next-version prompt for weak ads, and a Ways to improve panel. Every state reopens from a copied link, and the page still shows everything with scripts off.
