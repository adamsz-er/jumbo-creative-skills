---
name: ad-transcript
description: Break a video ad's transcript into beats (hook, problem, agitation, solution, proof, offer, call to action), score its structure, flag claims that need substantiation, and rewrite it with a tighter hook and earlier proof. Use when the user pastes a script or captions (.txt, .srt, .vtt), asks why a video ad does not hold attention, or wants a script reviewed or rewritten. Works with no performance data.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Ad transcript

Reads the words of a video ad as a sequence of jobs, shows which jobs are missing or late, and rewrites the script without changing the idea. It judges one script on its own terms. It never says what a "good" length, pace or hook is for the platform.

## Get the transcript

1. A pasted script, a `.txt`, or captions in `.srt` or `.vtt` (timestamps unlock the timing checks).
2. Only a video file? Ask the user to export captions from Ads Manager or their editor, or use their agent's own transcription if it has one. Never send the video to an outside service for them.
3. Ask for the brand and product name, so the script can find the first product mention. If `creative-profile.md` exists, read it and use its tone and offer.

## Run it

```
python3 -I scripts/beats.py transcript.txt --product "rain shell,Acme"
python3 -I scripts/beats.py captions.srt --product "rain shell,Acme" --json
```

It prints one row per sentence with a beat label, then time to the first product mention and first call to action, words per second (only when timed), beats not found, and flags: no product in the first 3 seconds (timed only), CTA missing, more than one CTA, and claim words that need substantiation ("best", "guaranteed", "cure", "clinically", "#1" and similar).

The labels come from keywords and position. Treat them as a first pass: read each line, correct the ones the heuristic got wrong, and say which you changed. `references/beat-structure.md` describes each beat and what to look for.

## Score the structure

Five checks, each pass or fail with the line that proves it. Score out of 5.

1. **Hook lands in the first 3 seconds.** The opening line or image gives a reason to stay: a situation, a claim, a question or a surprise. Not a greeting or a logo.
2. **Problem named.** The viewer's situation is stated in words they would use.
3. **Proof present.** Something checkable: a number, a test, a demonstration, a real customer line with permission. Never invented.
4. **Product shown early.** It appears soon enough that a viewer who leaves at the midpoint still knows what is being sold. With no timestamps, judge by position and say so.
5. **One clear CTA.** Exactly one action, said once, at the end or after the offer.

State the score and the one fix that would move it most.

## Rewrite it

Write 2 rewrites that keep the concept, the persona and every true claim:

- **Tighter hook:** the same idea, the first line cut to one situation or one claim.
- **Proof earlier:** the proof moved ahead of the explanation, the explanation shortened.

For each rewrite give the spoken script, the on-screen text for every beat (readable with the sound off), and what changed. Mark every claim that needs sign-off with "needs sign-off". Any example customer quote is labelled illustrative. For more opening lines, hand off to `hook-writer`.

## Present the result

1. Lead with the score and the biggest problem.
2. The beat table, corrected where you disagreed with the script.
3. The two rewrites with on-screen text.
4. Flags the brand must clear before running (claims, offers, regulated categories).

## Guardrails

- No benchmarks: not for length, words per second, hook timing or how many beats an ad needs. The checks above are craft checks on this script, not targets from outside it.
- Never invent testimonials, reviews, statistics or results. A rewrite may only use proof the user supplied.
- Regulated categories (health, finance, alcohol, weight loss and similar): flag the claims and tell the user to check platform ad policies and local advertising law.
- Read only. Do not touch the ad account.

## How to use

Have ready: the script as .txt, .srt or .vtt, and the product name.

Try:

- "Break this script into beats and tighten it."
- "Is my proof early enough in this ad?"
- "Which claims in this script need sign-off?"

## Common questions

- **How does it find beats?** A keyword heuristic: a first pass, not a verdict.
- **Is there an ideal length?** No; the checks are craft checks on your script.
- **Will the rewrite add proof?** Only proof you supplied.
- **Can it read a video?** No; paste or export the transcript.
- More: creative-context/references/faq.md
