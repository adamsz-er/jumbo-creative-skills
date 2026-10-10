# Reading the spend analysis

## Concentration

- **Pareto line.** The fewest ads that hold a chosen share of spend (80% by convention, not a rule). Compare it with the same line for purchase value. When fewer ads hold the value than hold the spend, the account's winners are underfunded relative to what they return. When more ads hold the value, spend is concentrated on ads that return less than their share.
- **Top-N share.** The share of spend in the few biggest ads. A high share means one fatigue event moves the whole account. Judge it against your own history, not a target.

## Spend by dimension

The "vs account" column is the group's pooled return as a percent of the account's pooled return. 100 is the same as the account; 150 returns half as much again per unit of spend; 60 returns a little over half. Pooled means summed spend and summed value across the group's ads, so one big ad weighs more than one small one.

Read it together with the share of spend. A concept with a high "vs account" and a small share is the first place to look for more budget. A concept with a low "vs account" and a large share is where money is leaking, unless it is doing another job (a launch building awareness, a retargeting ad finishing sales started elsewhere).

Age bands use each ad's age. With no creation date in the data, age starts at the ad's first delivery in the window, so an ad that started before the window looks younger than it is: the output says so.

## Spend on pause and never-worked ads

This is the money keep-or-kill would stop. It is only as strong as the verdicts: a pause needs the ad to miss the user's own target, so with no target set there is nothing here. Before stopping anything, rule out tracking, the landing page and the audience (`funnel-diagnosis` reads the page).

## Room to scale

A scale call means strong payback and no sign of wearing out. Frequency then says how much room is left: at or below the median of its format, the ad is still reaching new people; above most ads of its format, more budget will mostly buy repeat views. With daily rows, frequency is an average of daily values, not lifetime frequency.

## Budget moves

- **From pause to scale.** The daily spend of each pause ad, split across the scale ads in proportion to their current spend. The confidence is the weaker of the source and the destination verdicts.
- **No move from check-before-cutting.** The weakness is not proven: find out first.
- **No budget change for iterate.** The concept still pays; the creative needs a refresh (`hook-writer`, `fatigue-planner`).
- **No step size.** How much and how fast to raise a budget depends on how the account has absorbed increases before. Raise in steps you have seen work, and read the result before the next step.

What the moves do not tell you: whether the business made money (that needs margin and store revenue), whether the platform's attribution over-credits retargeting, or what a new audience would do. Treat each move as a test with a date to read it back.
