---
name: persona-builder
description: Build ad personas for any brand from who actually responded in the account - results by persona or audience, new-customer share, winning and losing angles - defined by emotional starting state and awareness stage rather than demographics, with the job, objections, trigger moments, proof needed and language, then map each persona to concepts and hooks to test. Every persona names the ads it came from. Use when the user asks who an ad is for, wants audience personas, or needs copy that matches where a buyer is. Works with no data and says the personas are unbacked.
license: MIT
metadata:
  version: "0.2.0"
  role: make
---

# Persona builder

A persona here is a **state of mind**, not a demographic. Two people of the same age and income can start from opposite feelings about the same product. This skill defines each persona by where they start emotionally and how much they already know, because that decides what an ad has to say.

## Before you start

1. Look for `creative-profile.md` in the working directory (from `creative-context`). If it exists, read it, including any personas already listed, and confirm it is current in one line.
2. If not, ask for the five essentials in one short round: **brand, product, audience, offer or calendar, tone**. Never block on this. Say what you assumed and mark it "assumed".
3. Ask what the user knows about why people buy: reviews, support questions, return reasons, sales conversations, comments on ads. Real customer words beat invention. Quote only what the user gives you.
4. With no performance data, say so: personas come from the user's knowledge and craft, and are hypotheses to test.

## Read the account first

When there is data (a daily export or a connector pull run through `from_mcp.py`), start from who responded:

```
python3 -I scripts/evidence.py ads.csv --for persona
python3 -I scripts/evidence.py ads.csv --for persona --segment adset_name --verdicts verdicts.json
python3 -I scripts/evidence.py ads.csv --for persona --json
```

It shows results by persona or audience (a `persona` field in the ad names, else an audience or ad set column; `--segment` picks any column or name field), each group's return and cost per sale as a percent of the account's own, its new-customer purchase share where the data has it, its top- and bottom-quartile ads and its concepts, then the angles (concepts) that won, lost, were mixed or sat in the middle. `--verdicts` adds keep-or-kill's call to each ad.

Build each persona from a group that responded, and name the ads behind it ("built from 120000000021 and 120000000026, the gear-upgraders ad set"). A group that responded poorly is a persona to deprioritise or to reach with a different angle, not one to drop silently. With no persona or audience tag in the data, the evidence says so: build personas from the profile and the user's knowledge and label each one "unbacked: no results by persona in the data". With no data at all, say every persona is unbacked.

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

1. The personas, each filled in with the template, each naming the ads and the group it came from, or "unbacked".
2. The persona to concept and hook map.
3. A list of what is assumed versus what the user told you, so the user knows what to check.
4. **Next step:** `creative-ideation` for concepts per persona, `hook-writer` for openings, or `creative-brief` for a chosen persona and concept.

## Guardrails

- Never stereotype. Do not infer a persona's feelings, needs or buying power from ethnicity, body type, gender, age or religion, and never suggest casting by those traits. Describe the person's situation and state of mind.
- No invented statistics about audience size, share of buyers or behaviour. No benchmarks. Numbers come only from the evidence script, relative to the account's own.
- No promise that a persona will convert.
- Regulated categories (health, finance, alcohol, weight loss and similar): do not build personas around a sensitive personal condition, and flag the category. Tell the user to check the platform's ad policies and local advertising law, including limits on targeting by sensitive traits.
- Read only: only read data, and never call a tool that changes ads, budgets or status. Do not touch the ad account.

## How to use

Have ready: the brand profile, and any customer words you have (reviews, support notes).

Try:

- "Who am I really talking to? Build me personas for this brand."
- "Map these personas to my concepts."
- "What objections does each persona have?"

## Common questions

- **Demographics?** Personas are built from starting state and awareness, not age or gender.
- **Statistics?** None invented; no audience-size claims.
- **Where do the personas come from?** From who responded in your account (results by persona or audience), or labelled unbacked when the data has no such tag.
- **Real customers?** Use real quotes only with permission; examples here are illustrative.
- **What next?** Hand the personas to creative-ideation and hook-writer.
- More: creative-context/references/faq.md
