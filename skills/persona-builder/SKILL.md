---
name: persona-builder
description: Build ad personas for any brand defined by emotional starting state and awareness stage rather than demographics - the job they hire the product for, their objections, trigger moments, the proof they need and the language they use - then map each persona to concepts and hooks to test. Use when the user asks who an ad is for, wants audience personas, or needs copy that matches where a buyer is in their decision. Works with no data.
license: MIT
metadata:
  version: "0.1.0"
  role: make
---

# Persona builder

A persona here is a **state of mind**, not a demographic. Two people of the same age and income can start from opposite feelings about the same product. This skill defines each persona by where they start emotionally and how much they already know, because that decides what an ad has to say.

## Before you start

1. Look for `creative-profile.md` in the working directory (from `creative-context`). If it exists, read it, including any personas already listed, and confirm it is current in one line.
2. If not, ask for the five essentials in one short round: **brand, product, audience, offer or calendar, tone**. Never block on this. Say what you assumed and mark it "assumed".
3. Ask what the user knows about why people buy: reviews, support questions, return reasons, sales conversations, comments on ads. Real customer words beat invention. Quote only what the user gives you.
4. With no performance data, say so: personas come from the user's knowledge and craft, and are hypotheses to test.

## Inputs it can use if present

- Customer language from the user: reviews, survey answers, help-desk messages.
- Performance by audience or region from a CSV or the Meta ads connector. Use it only as **relative evidence** (this audience's ads sit higher or lower than the account's own median), never as proof of who a person is.
- `mix.md`, `grade.md` or `verdicts.md`: which concepts have worked for which audience, if the names carry it.

## Define each persona

Use `references/persona-template.md`. Each persona needs:

- **Emotional starting state** and the state they want to reach (for example, anxious to reassured).
- **Awareness stage:** unaware, problem-aware, solution-aware, product-aware, or ready to buy.
- **The job** they are hiring the product to do.
- **Objections:** what stops them from buying.
- **Trigger moments:** what happens that sends them looking.
- **Proof they need** before they believe it.
- **Language:** words and phrases they use, in their voice.
- Demographics: a light note at most, and only if the user supplied it.

Default **3** personas (an arbitrary default: fewer if the product has one clear buyer, more only if the user can make creative for them all).

## Map personas to tests

After the personas, give a table: persona, stage, concept angles to test (from `creative-ideation/references/concept-frameworks.md`), hook archetypes to try (from `hook-writer/references/hook-archetypes.md`), and the proof to show. This is the bridge to making ads.

## Output

1. The personas, each filled in with the template.
2. The persona to concept and hook map.
3. A list of what is assumed versus what the user told you, so the user knows what to check.
4. **Next step:** `creative-ideation` for concepts per persona, `hook-writer` for openings, or `creative-brief` for a chosen persona and concept.

## Guardrails

- Never stereotype. Do not infer a persona's feelings, needs or buying power from ethnicity, body type, gender, age or religion, and never suggest casting by those traits. Describe the person's situation and state of mind.
- No invented statistics about audience size, share of buyers or behaviour. No benchmarks.
- No promise that a persona will convert.
- Regulated categories (health, finance, alcohol, weight loss and similar): do not build personas around a sensitive personal condition, and flag the category. Tell the user to check the platform's ad policies and local advertising law, including limits on targeting by sensitive traits.
- Read only: only read data, and never call a tool that changes ads, budgets or status. Do not touch the ad account.
