# Designing a test the account can power

## The plan, in six lines

1. **Hypothesis:** "For the weekend-hiker persona, naming the guarantee in the headline raises click-through against naming the price." One persona, one change, one metric.
2. **The one change:** what differs between control and variant. Everything else is held still.
3. **Metric:** the rate the change should move. Copy that earns the click is judged on click-through; copy that sets up the sale on purchase rate. Purchase rate needs far more spend to read, because clicks are far fewer than impressions.
4. **Smallest change worth detecting:** the smallest relative improvement that would change what the team does. It is a business decision, not a statistical one, and it decides everything else.
5. **Sample, budget and duration:** from `power.py`, using the account's own baseline rate for that metric and its own volume per unit of spend.
6. **Stopping rule:** decide once, at the planned sample.

## How the sample is worked out

`power.py` uses the standard two-proportion sample-size formula for a two-sided test, with the account's pooled baseline rate as the control and the baseline times (1 + smallest change) as the variant. The two inputs from statistics are conventions, not benchmarks: a false-win rate (alpha, 0.05) and the chance of catching a real change of the chosen size (power, 0.8). With more than two arms, alpha is split across the comparisons (Bonferroni), which raises the sample per arm.

The sample per arm is in the metric's own denominator: impressions for click-through and hook rate, clicks for purchase rate. The account's volume per unit of spend turns that into days at the daily budget.

## When the account cannot power it

Say so plainly. The output gives the options:

- **Test a bigger change.** The smallest change the account can detect inside the time limit. If that change is bigger than anything a copy tweak could plausibly do, the test is not worth running.
- **Spend more.** The daily budget that would fit the time limit.
- **Move up the funnel.** Click-through has far more volume than purchase rate. A copy change that cannot be read on purchases can often be read on clicks; say that this measures the click, not the sale.
- **Fewer arms.** Every extra variant splits the budget and the alpha.

## Rules that keep the result honest

- **No peeking.** Checking every day and stopping when one arm leads inflates false wins far above alpha.
- **No extending a test that missed.** Adding days until it "works" has the same effect.
- **Even split, same settings.** Same audience, placements, schedule and optimisation for every arm.
- **One test per audience at a time.** Overlapping tests contaminate each other.
- **Read the guardrail metrics.** A winning click-through with a falling purchase rate is not a win: check the funnel (`funnel-diagnosis`).
- **Record it.** Hypothesis, dates, result and decision, so the next test starts from what is known.

Meta's own A/B test tool (in Ads Manager, under Experiments) splits audiences so arms do not overlap; it is the cleanest way to run these.
