# FAQ for the agent

Answer the user's "how do I..." question from here, in plain words. Longer answers: `docs/faq.md` in the repository, which is not installed with a single skill.

## Getting started

### What does this package do?

Reads your ads, grades them against your own account, and helps you make the next batch. Read only.

### What do I say first?

"Review my Meta ads" runs the whole flow. No data: offer the sample account (`review.py run --demo`).

### Do I need to install all the skills?

No; each works alone. creative-review needs its siblings and says which one is missing (E-SKILL).

### Where do my results go?

`./creative-review-runs/<account>/<window end>_<time>/`; the next run of the same account compares with the latest folder.

### Can I try it without my own data?

Yes: `review.py run --demo`, labelled sample data.

## Data and connections

### Do I need the Meta MCP?

No. A daily Ads Manager CSV works; with no data, ideation-only mode, labelled "no performance data".

### Why is hook rate missing or marked derived?

The connector returns 3-second plays only above ad level; they are derived from cost per 3-second view and labelled "(derived)", or refused when the cost is rounded too coarsely. Use an export with the column.

### Why was my pull reconciled / what does a shortfall warning mean?

Pulled spend and impressions are compared with account totals. A shortfall (E-RECONCILE) means missing ads: check archived ads first, then re-fetch in smaller batches.

### Which attribution window do the numbers use?

Not stated unless you pass `--attribution`; the connector does not return the setting it used.

### Why do reach and frequency show n/a?

Reach does not add across ads or days; supply an account-level figure for the same scope with `--account`, else n/a.

### Why are there no ad images in the report?

The connector gives links, not images. Save `<ad_id>.png` files and pass `--previews`.

## Metrics and grading

### Why don't you tell me what a good hook rate is?

No universal "good" value exists. Grades are relative to the account's own quartiles; any industry band is cited context and never changes a verdict.

### Why does an ad say too early to judge?

The ad is younger than `--young-days` or under `--min-impressions`. Both are arbitrary and user-settable. Too early is never a pause.

### Why is an ad "not graded (low volume)"?

Under `--min-impressions`. Shown, not graded.

### What does "early read" mean?

Small comparison group, few delivery days or one payback measure: treat as a lead.

### What if my ad names don't follow a convention?

Run `detect_naming.py` on ALL names; below the match rate it asks once. Fix with `--key-map` and `--type-map`, saved in the profile's Script settings. Unread names are listed as unclassified.

### Why is a metric n/a instead of 0?

A missing operand or zero denominator is n/a (missing <field>), never 0.

### Can I change the thresholds?

Yes. All defaults are arbitrary; see the flags table in docs/how-it-works.md and set them from your own account via flags or Script settings.

## Decisions

### How does keep-or-kill decide to pause an ad?

Bottom on every payback measure plus fatigue, or never worked and missing the user's own target. No target gives Check before cutting. Top sellers are protected.

### Why did an ad say "check before cutting" instead of pause?

Mixed payback, small group, top seller or no target. The sentence gives the reason.

### Does it judge every campaign the same way?

Per objective (sales, traffic, awareness, leads, engagement). Without an objective column, all ads are judged as sales, and the output says so.

### Will it change my ads for me?

Never. Recommendations only; write tools are not called unless the user asks in that conversation.

## Making creative

### Do the make skills need data?

No; with data they are aimed at the gaps and winners.

### Where do the claims and results in a brief come from?

Only from the user and the data; claims needing approval are marked "needs sign-off".

### How do I make a one-change variant of a winning ad?

Ask hook-writer for variants, or creative-brief for a one-change brief on an Iterate ad.

## The report

### How do I share the report?

Share `report.html`; print to PDF from a browser. The address reopens the filtered view.

### Why do the report fonts look different offline?

Fonts load from Google Fonts; offline it falls back to a system font.

### What does "What changed since last time" compare?

The latest earlier run folder of the same account.

## Privacy and safety

### Does my data leave my machine?

Scripts are local and make no network calls. Only your agent and the connector move data. The report requests only Google Fonts.

### Can it make changes in my ad account?

No. Read only.

### Is it safe to share a report?

It holds real account numbers. Share like account data; never publish one.

## Installing and updating

### How do I update?

Claude Code: `/plugin marketplace update`. Others: re-run `npx skills add`. claude.ai: re-download the zips.

### Can I use this for TikTok or Google?

Meta-first. Another platform's CSV may work for spend, impressions, clicks and purchases; hold rate is Meta-specific. Untested.

### Can I use it in ChatGPT?

Works in any Agent Skills agent that can run Python. ChatGPT is untested; without code execution, compute by hand from metrics.md.

### Why does the plugin not show up after installing?

`/reload-plugins` or a new session.

### Can I contribute?

Yes: tests, validator, sync check; fictional examples only.
