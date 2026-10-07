---
name: hook-writer
description: Write hooks for Meta (Facebook and Instagram) ads - the first 3 seconds of a video (spoken line, on-screen text, visual action) and the opening line of primary text - and produce one-change variants of a winning hook. Use when the user needs hooks, openers, a scroll-stopping first line, or fresh variants of an ad whose hook is fatiguing or working. Works with no data and gets sharper with a brand profile, personas or keep-or-kill verdicts.
license: MIT
metadata:
  version: "0.1.0"
  role: make
---

# Hook writer

A hook is the part of the ad that earns the next second. This skill writes hooks for video and for text, checks each against a short checklist, and, in iteration mode, makes variants of a hook that already works.

## Before you start

1. Look for `creative-profile.md` in the working directory (from `creative-context`). If it exists, read it and confirm it is current in one line.
2. If not, ask for the five essentials in one short round: **brand, product, audience, offer or calendar, tone**. Never block on this. Say what you assumed and mark it "assumed".
3. Ask which persona and funnel stage the hooks are for. If `persona-builder` output exists, use its starting states and language. If not, ask for the viewer's situation in one sentence.
4. With no performance data, say so: the hooks come from craft, not results.

## Inputs it can use if present

- `verdicts.md` from `keep-or-kill`: an ad marked "iterate" is the best source for iteration mode.
- `grade.md` from `creative-grader`: a diagnosis of "hook" means the opening is not stopping the scroll; a diagnosis of "hold" means the opening works but the body does not sustain it, so the hook is not the thing to change.
- An Ads Manager CSV or Meta ads connector. An ad export carries no hook wording, so ask the user for the opening line, or read it from the ad itself.

## Modes

### 1. New video hooks
Pick archetypes from `references/hook-archetypes.md`. Default **6** hooks (an arbitrary default). For each:

| Field | What to write |
|---|---|
| Archetype | which pattern it uses |
| Spoken line | the exact words, written for speech |
| On-screen text | the exact words, short enough to read at a glance |
| Seconds 0-3 | what happens visually, beat by beat |
| Persona and stage | who it is for and where they are in the funnel |
| Pays off with | what the next few seconds deliver |

Every hook must work with the sound off: the on-screen text and the visual carry it alone.

### 2. New text hooks
Write the opening line of the primary text so it makes sense **on its own in the first visible line**. Truncation length varies by placement and device: tell the user to check the current cut-off in their placement preview in Ads Manager, and write the first sentence to stand alone whatever the cut-off is. Offer a few openers per archetype and mark which ones need a second line to land (those are riskier).

### 3. Iteration mode
Input: a hook that is working or fatiguing (a "scale" or "iterate" verdict, or the user's pick). Keep the concept and **change exactly one thing per variant**: the opening line, the visual, the creator, the setting or the length. Label each variant with the one thing that changed, so the result can be read. If the ad was fatiguing, make variants that change the first moments and keep the idea that still earns. Do not change two things at once: that tests nothing.

## Check every hook

Run each hook through `references/hook-checklist.md` and show pass or fail. Fix or drop a hook that fails; do not ship it with a caveat.

## Output

1. Hooks in the table above, grouped by persona and stage.
2. The checklist result for each.
3. For iteration mode, a table of variants: what stayed, what changed, what it tests.
4. **Next step:** `creative-brief` to turn a chosen hook into a production brief, or `creative-ideation` for concepts behind the hooks.

## Guardrails

- No invented performance claims, no benchmarks, no promises of results.
- Never invent testimonials, reviews or customer quotes: use only real ones, with the customer's permission.
- Hooks must be something the ad can pay off. No clickbait the body cannot deliver.
- Claims in a hook must be ones the brand can substantiate. Mark anything that needs approval "needs sign-off".
- Regulated categories (health, finance, alcohol, weight loss and similar): flag them and tell the user to check the platform's ad policies and local advertising law. Avoid hooks that imply the viewer has a personal condition or characteristic.
- Do not cast by stereotype; describe the energy of the person, not their demographic.
- Read only: only read data, and never call a tool that changes ads, budgets or status. Do not touch the ad account.
