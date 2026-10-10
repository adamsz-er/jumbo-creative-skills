---
name: fatigue-planner
description: Plan creative refreshes for a Meta ad account - each ad's rates by day of delivery against the account's own band, the ads already fading and the ones on course to, an estimate of days left from each ad's own trajectory with its range stated, and a dated refresh calendar sized to how many ads the team can make per week. Use when the user asks which ads are wearing out, when to refresh, how much creative to produce, or for a refresh calendar. Ads with too little history say so.
license: MIT
metadata:
  version: "0.2.0"
  role: analyse
---

# Fatigue planner

Turns fatigue from a surprise into a schedule. It reads each ad's own trajectory, compares young ads with the account's band for the same day of delivery (the same age curve the report draws), estimates how long each has left, and lays the refreshes into the weeks the team can actually produce them.

## Before you start

1. Get daily rows (a daily Ads Manager export or a connector pull run through `from_mcp.py`): fatigue cannot be read from totals. Say which mode you are in.
2. Ask how many new or refreshed ads the team can make a week (`--capacity`), and how many days a refresh takes from brief to live (`--lead-days`). Without a capacity the skill gives the read but no calendar.
3. With no data, say so and stop: a refresh calendar from no data is a guess.

## Run it

```
python3 -I scripts/fatigue_plan.py ads.csv --capacity 2
python3 -I scripts/fatigue_plan.py ads.csv --capacity 2 --start 2026-03-31 --lead-days 7 --weeks 6
python3 -I scripts/fatigue_plan.py ads.csv --metric hook_rate --capacity 3 --where format=ugc-video
python3 -I scripts/fatigue_plan.py ads.csv --capacity 2 --json
```

`--window` (6), `--min-change` (8), `--fit-days` (9), `--min-days` (9), `--weeks` (6), `--lead-days` (7), `--min-impressions` (1000) and `--curve-min-ads` (3) are arbitrary defaults: set them from how fast your own ads tire and how your team works. The output prints the values it used.

## How it reads each ad

- **Fading:** the same rule keep-or-kill uses. The chosen rate (click-through by default) is down by at least `--min-change` percent from the ad's first days to its last, and frequency is up or hook rate is down by as much.
- **Against the band:** an ad launched inside the window is compared, day by day, with the account's own band for that day of delivery (median and quartiles across the ads launched in the window). An ad that was already running when the window opened is compared with its own start instead, and the output says so.
- **Days left:** a straight line through the ad's last `--fit-days` delivery days, run forward to the floor: the lower quartile of the same rate among ads of its format. The range uses the slope plus and minus one standard error. The line has to be clearly falling (still falling at the slow end of its range) before an ad is "on course to fade"; noise around a flat line is "steady".
- **Too little history:** under `--min-days` delivery days, no estimate at all.

`references/refresh-planning.md` covers what to refresh first, what a refresh changes, and how to read the estimate.

## Present the result

1. Lead with the two lines it prints: how many ads are fading and on course, and when the queue clears at this capacity, with how many refreshes land late.
2. Give the calendar week by week. Name late items and anything beyond the horizon, and offer the two levers: more capacity or a longer horizon.
3. Quote every days-left figure with its range and the straight-line caveat. Never round a range into a promise.
4. **Next step:** `hook-writer` for one-change variants of a fading ad whose concept still pays, `creative-brief` for each refresh in the calendar.

## Guardrails

- The estimate is a projection from the ad's own recent days, not a forecast of the future. Say so every time.
- Relative only: the floor and the band come from this account, never a benchmark.
- A missing rate is `n/a (missing <field>)`, never 0; an ad without it is "unreadable", never steady.
- Never pause or edit anything. A refresh calendar is a plan for the team.

## How to use

Have ready: daily rows for several weeks, and how many ads your team makes a week.

Try:

- "Which ads are wearing out, and when do I need replacements?"
- "Plan my refreshes for the next six weeks at two new ads a week."
- "How long has my best video got left?"

## Common questions

- **Why does an old ad have no band comparison?** It started before the data's window, so its day of delivery is unknown. It is compared with its own start.
- **How sure is the days-left number?** It is a straight line through recent days; the range shows how wide the uncertainty is.
- **Why is my ad steady when it dipped?** The dip is within noise: the line's range includes no fall.
- **What counts as a refresh?** A new opening, creator or format on a concept that still pays; see the reference.
- More: creative-context/references/faq.md
