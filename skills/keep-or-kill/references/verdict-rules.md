# Verdict rules

First matching rule wins. Every verdict lists its reasons. All grading is relative to the account's own ads in the same group (usually format): top quartile at or above p75, bottom quartile at or below p25, costs inverted.

## Inputs

- **Learning flag.** Age is days from first delivery to the latest date in the data, so an ad older than the export window looks as young as the window start; widen the export if that matters. An ad is learning when age is under `--young-days` or its impressions are under `--min-impressions`.
- **Payback band.** Combines `cpa` and `roas`. Bottom if either is bottom quartile; top only if every graded one is top. A metric that cannot be computed (for example CPA with zero purchases) is not graded and is named, never read as 0. "From the start" means the ad's first `--window` delivery days graded against every ad's own first window.
- **Attention.** `hook_rate` or `ctr` in the top quartile.
- **Fatiguing.** Comparing an ad's first and last `--window` delivery days: CTR falls by at least `--min-change` percent AND (average frequency rises by at least that, OR hook rate falls by at least that). With fewer than 2 x window delivery days the trend is "insufficient data": the ad is neither called fatiguing nor cleared.

## Rules

| # | Condition | Verdict |
|---|---|---|
| 1 | Learning | too early (learning). Nothing else is said. |
| 2 | Payback bottom overall AND bottom from the start, not fatiguing | kill: never worked |
| 3 | Fatiguing and payback not bottom (middle, top, or not gradable) | iterate: refresh the hook or creator, keep the concept |
| 4 | Fatiguing and payback bottom | kill: fatigued |
| 5 | Payback top, fatigue readable and not fatiguing | scale: raise budget in steps |
| 6 | Attention strong but payback bottom | keep: check whether it feeds other ads before cutting |
| 7 | Anything else | keep |

Every kill verdict carries this line: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions.

## Judgement calls to know about

- Payback top with fatigue unreadable (under two windows of delivery days) is held at "keep", never scaled. Scaling an ad whose trend cannot be read is a bet the data cannot support.
- Fatiguing with a payback that cannot be graded is "iterate", because there is no evidence it is weak.
- Rule 2 uses the combined payback band: an ad weak on either cost or return from day one counts as never worked.
- Several ads of one concept share one fatigue clock; read their verdicts together.
- Grading within a group needs at least 5 comparable ads; with fewer it falls back to the whole account. 5 is an arbitrary default, not a statistical rule.
- `--min-change` (default 8) is a materiality size to separate a real move from week-to-week noise. It is not a benchmark for fatigue: set it from how much your own metrics wobble when nothing is wrong.

## Summary block

Counts per verdict, the ads too young to judge, and spend concentration: "top N ads (N=3, an arbitrary default: set your own with `--top-n`) hold P% of spend". Heavy concentration means one fatigue event hurts the account. Judge how heavy against the account's own history.
