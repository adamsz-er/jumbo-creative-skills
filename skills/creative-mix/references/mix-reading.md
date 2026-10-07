# Reading the mix

## Tables

- **By format, by concept family, by ad type.** Ad count, spend, share of classified spend, and pooled ROAS and CPA (summed spend, conversions and value; never an average of ratios).
- **Concept x format grid.** Ad count and spend per cell. An empty cell is marked `gap`; a one-ad cell is thin evidence.
- **Funnel stage.** Only when names carry a `funnel_stage` field (pass `--pattern`). Otherwise the output says so rather than guessing.
- **Unclassified.** Ads whose names did not parse, with their spend. Counted and listed.

## Concept families

Several versions of one idea are one data point and one fatigue clock. A concept named like another with a "-suffix" joins that concept's family: `gift-guide` and `gift-guide-two` become `gift-guide`. The script lists which ads and names were grouped. It is a naming heuristic: if two names merely share a prefix by accident, run with `--no-family` or rename.

## Read-outs

- **Gaps worth testing.** An empty or one-ad cell next to a top-quartile concept (that concept is not yet in this format) or a top-quartile format (this concept is not yet in it). Top quartile is ranked on pooled ROAS across the account's BAU ads only, so promos do not inflate it, and only when there are at least 5 concepts or formats to rank. Treat each as a hypothesis for the next brief.
- **Over-reliance.** One concept family or format holding more than half of spend (arbitrary default; set it from your own account). One fatigue event then hurts the whole account.
- **Promo versus BAU.** Shown as separate rows, never blended. Promo performance depends on the offer and dates; launch performance on drops; retention flatters blended numbers and acquires no one.
- **Near-duplicates.** Families with more than one concept name, counted once.

## What it cannot tell you

- Whether a concept works: that needs `creative-grader` and `keep-or-kill`.
- Anything about ads that were not in the export. Widen the date range, or include paused ads.
- Funnel fit without a funnel stage in the names or in the profile.
