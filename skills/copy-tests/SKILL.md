---
name: copy-tests
description: Write Meta ad copy variants - primary text, headline and description - tied to a persona and a hook, one change per variant, within Meta's published text guidance, and design the test behind them - hypothesis, the one change, the smallest change worth detecting, sample size, budget and duration from the account's own baseline rate, and a stopping rule. Says plainly when the account cannot power a test. Use when the user wants copy variants, an A/B test plan, "how long should this test run" or "is this test big enough".
license: MIT
metadata:
  version: "0.2.0"
  role: make
---

# Copy tests

`hook-writer` owns the opening line. This skill owns the rest of the words (primary text after the opening, headline, description) and the structure of the test that compares them: what is changed, what would count as a win, how much volume that needs, and when to stop.

## Before you start

1. Read `creative-profile.md` if it exists (brand, tone, claims that need approval, offers). If not, ask for the five essentials in one round: brand, product, audience, offer or calendar, tone. Mark what you assumed.
2. Ask which persona and hook the copy serves (from `persona-builder` and `hook-writer` if they ran). Every variant names both.
3. Ask what the test should teach: one question per test ("does naming the guarantee beat naming the price?").
4. Say which data mode you are in. With no data, the copy still works; the test sizing needs a baseline from the account, so it says so and asks for an export.

## Write the variants

Follow `references/copy-guidance.md`:

- A control and variants that each change **one thing**: the angle of the primary text, the proof, the offer framing, the headline, or the call to action. Name the change in a `changed` column.
- Within Meta's published text recommendations for the placement (cited in the reference). Over the guidance is flagged, not banned: Meta truncates; it does not reject.
- Claims the brand can substantiate only; mark anything that needs approval "needs sign-off".

Put the variants in a CSV (`test, variant, persona, hook, field, text, changed`) and check them:

```
python3 -I scripts/copy_check.py variants.csv
python3 -I scripts/copy_check.py variants.csv --limits primary_text=150,headline=27,description=27
```

It fails a variant that changes more than one thing, one that changes nothing, a `changed` column that names the wrong field, a missing persona or hook, and text over the limits. The description limit is checked only when you pass one: Meta's feed spec gives none.

## Size the test

```
python3 -I scripts/power.py ads.csv --metric ctr --mde 18 --daily-budget 300 --max-days 21
python3 -I scripts/power.py ads.csv --metric cvr --mde 18 --daily-budget 300 --max-days 21 --where format=static
```

- `--metric` is the rate the variants should move: click-through for copy that earns the click, purchase rate for copy that sets up the sale.
- `--mde` is the smallest relative change worth knowing about, in percent of the baseline. It is the user's call, never a default.
- The baseline rate and the volume per unit of spend come from the account's own rows (`--where` narrows them to the format or market the test runs in).
- `--alpha` (0.05) and `--power` (0.8) are statistical conventions, not benchmarks. More than two arms split alpha (Bonferroni), and the output says so.

It answers in one line whether the account can power the test inside `--max-days`, and if not, the smallest change it could detect in that time, the daily budget that would fit, and the option of a higher-funnel metric. `references/test-design.md` explains the plan and the stopping rule.

## Present the result

1. The test plan: hypothesis, the one change, the metric, the smallest change worth detecting, sample per arm, budget, duration, stopping rule.
2. The variants table, with the check results.
3. When the account cannot power the test, say so plainly and give the options it printed. Never shrink the test to make it look powered.
4. **Next step:** `creative-brief` to brief the ads, `ad-namer` to name each variant with its version.

## Guardrails

- No significance shortcuts: no peeking, no stopping early on a lead, no extending a test that missed.
- No benchmarks and no promised lift. The smallest change worth detecting comes from the user.
- Never invent testimonials, reviews, prices or deadlines. Offers and dates come from the user.
- Regulated categories (health, finance, alcohol, weight loss and similar): flag them and tell the user to check the platform's ad policies and local advertising law.
- Read only: never create, edit or launch anything in the ad account.

## How to use

Have ready: the persona and hook, the offer, a daily budget for the test, and an export for the baseline.

Try:

- "Write three headline variants for the weekend-hiker persona and plan the test."
- "Can my account power a test of an 18% better purchase rate?"
- "Check these copy variants before we launch."

## Common questions

- **Why only one change per variant?** Two changes at once cannot tell you which one worked.
- **Why can't my account power the test?** Too little volume for the change you want to see. The output gives the change it can detect, the budget that would fit, or a higher-funnel metric.
- **Are Meta's length numbers rules?** Guidance for how much shows before truncation. Check the current spec page.
- **Can I stop when one arm is clearly ahead?** No: decide once, at the planned sample.
- More: creative-context/references/faq.md
