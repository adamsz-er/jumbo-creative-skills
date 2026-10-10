---
name: creative-ideation
description: Generate Meta (Facebook and Instagram) ad concepts for any brand, spread across themes, formats, ad types, personas and funnel stages, aimed at the gaps in the account's own concept and format coverage and informed by verdicts, spend share, ad age and a competitor scan when present. Every idea names the ads or gap it came from. Use when the user wants ad ideas, a concept pipeline, "what should we make next", a test plan for new creative, or fresh angles after a creative review. Works with no data and says the ideas are unbacked.
license: MIT
metadata:
  version: "0.2.0"
  role: make
---

# Creative ideation

Turns a brand and what is known about its account into a set of concepts worth making, each with the reason it should work and what would prove it wrong. An idea is not an ad: this skill keeps the **idea** (theme) apart from its **execution** (format), so a concept can be tested across formats and a format across concepts.

## Before you start

1. Look for `creative-profile.md` in the working directory (written by `creative-context`). If it exists, read it and confirm it is current in one line.
2. If not, ask for the five essentials in one short round: **brand, product, audience, offer or calendar, tone**. Never block on this. If the user skips something, say what you assumed and mark it "assumed".
3. Say which data mode you are in: connector, CSV, or none (see `creative-context/references/data-inputs.md`). With none, label the output "no performance data": the ideas come from craft, not results.

## Read the account first

When there is data, start from what the account has tried:

```
python3 -I scripts/evidence.py ads.csv --for ideation
python3 -I scripts/evidence.py ads.csv --for ideation --verdicts verdicts.json --competitor scan.json
python3 -I scripts/evidence.py ads.csv --for ideation --json
```

It shows each concept as winning, mixed, middle or losing (or ungraded or unjudged when there is too little to grade) with its ads, formats and share of spend; concept by format coverage with spend share, the best band in each cell and the youngest ad's age; the untried cells beside a winner; and, with `--competitor` (from `competitor-scan`), the open ground, the angles worth testing and the ones not to chase.

- Iterate winners into untried formats; do not repeat losing angles as they were; give young cells time before judging them.
- Prefer open ground the account's own results support over angles rivals have crowded.
- Every concept names its source: the ads it iterates, the gap it fills, or the competitor finding. With no data, label each "unbacked: from craft and the profile, not results".

## Inputs it can use if present

- `mix.md` or the output of `creative-mix`: its gaps and top-quartile concepts steer the whole run.
- `verdicts.md` or `keep-or-kill` output: "iterate" and "scale" ads are the best seeds for variations; "never worked" ads are things not to repeat as they were.
- `grade.md` or `creative-grader` output: the first broken funnel step says what a new concept must fix (a weak hook calls for a stronger opening, a weak click calls for a clearer offer).
- An Ads Manager CSV or a Meta ads connector: run `creative-mix` for the grid if no mix output exists.

## Build each concept from five choices

Every concept is a combination, written out explicitly:

| Choice | Options |
|---|---|
| Theme or angle | problem, proof, offer, emotion, identity, comparison, behind-the-scenes, founder story, social proof, education. See `references/concept-frameworks.md` |
| Format | static, carousel, catalog or collection, UGC video, founder video, creator or partnership, lo-fi vs polished |
| Ad type | bau, promo, launch, hype, partnership, retention. See `references/ad-type-playbook.md` |
| Persona | from `persona-builder` or the profile; one per concept |
| Funnel stage | prospecting (cold) or retargeting (warm) |

Change one choice at a time when you want to learn something.

## Aim at the gaps

- If a mix output exists, start from its gaps (concept by format cells with no ad beside a top-quartile concept or format) and from top-quartile concepts worth iterating. For each idea, **say which gap it fills or which winner it iterates**.
- If there is no mix output, aim at what the brand profile lacks: a persona with no concept, an ad type with no creative, a funnel stage with nothing. Say so.
- Treat a gap as a hypothesis, never a promise.

## Output

1. **Concept table.** Default **9** concepts (an arbitrary default: ask the user how many they can produce). Columns: name, theme, format, ad type, persona, stage, the one-line idea, the hook, why it should work, what would prove it wrong, which gap, winner (by ad id) or competitor finding it addresses, or "unbacked".
2. **Test plan.**
   - Group concepts into **one-variable tests**: hold the format constant to compare concepts, hold the concept constant to compare formats.
   - Give each ad a name in the naming convention from `creative-context/references/naming-convention.md` (concept | format | creator | ad type | product | tone | launch date).
   - Split the set into three buckets: **iterate what works**, **adapt to an adjacent audience or product**, **genuinely new**. Leave the ratios to the user and ask what they want; do not suggest numbers.
3. **Next step.** Offer `hook-writer` for the openings, `persona-builder` if personas are thin, and `creative-brief` to turn a chosen concept into a production brief.

## Guardrails

- No invented performance claims, no benchmarks, no promises of results. "Why it should work" is reasoning, labelled as such.
- Product claims in an ad must be ones the brand can substantiate. Where the profile lists claims that need approval, mark those ideas "needs sign-off".
- Regulated categories (health, finance, alcohol, weight loss and similar): flag the idea and tell the user to check the platform's ad policies and local advertising law before making it.
- Promo concepts need the offer and dates from the user. Never invent a discount or a deadline.
- Read only: only read data, and never call a tool that changes ads, budgets or status. Do not touch the ad account.

## How to use

Have ready: a brand profile helps; the mix or verdicts aim ideas at the gaps. No data is fine.

Try:

- "Give me nine ad concepts that fill the gaps in my mix."
- "Concepts for a spring launch."
- "Ideas for people who have never heard of us."

## Common questions

- **Do I need data?** No; ideas without data are labelled unbacked: craft, not proof.
- **Can it use competitors' ads?** Yes: run `competitor-scan` and pass its output with `--competitor`.
- **Will it invent a discount?** No; offers and dates come from you.
- **Are the ideas guaranteed to win?** No; each carries reasoning, not a result.
- **Regulated category?** It flags the idea and asks you to check platform policy and local law.
- More: creative-context/references/faq.md
