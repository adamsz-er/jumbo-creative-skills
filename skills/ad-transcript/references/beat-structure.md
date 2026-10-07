# Beat structure

A video ad is a run of jobs. `scripts/beats.py` labels each sentence with the job it seems to do. Not every ad needs every beat, and the order is a convention, not a rule: a testimonial may open on proof, a demo may skip the problem. What matters is that each beat the ad does use is doing its job, and that the ones it skips were skipped on purpose.

| Beat | Its job | What to look for | Common failure |
|---|---|---|---|
| Hook | Earns the next second | A situation the viewer recognises, a specific claim, a question, a surprise. Works with the sound off. | A greeting, a logo, a slow build, a claim with no tension |
| Problem | Names the viewer's situation | Their own words; one problem, not three | Stated in category language the viewer would never use |
| Agitation | Makes the cost of the problem felt | A concrete consequence | Piling on until it feels manipulative; repeating the problem |
| Solution / product | Shows what fixes it | Product on screen and named, with the one reason it works | Arrives late; described by features, not by the change for the viewer |
| Proof | Makes the claim believable | A number, a test, a demonstration, a real customer line (with permission) | Adjectives in place of evidence; invented quotes |
| Offer | Gives a reason to act now | Price, saving, shipping, code, date, stated plainly | Unclear terms; an offer with no end date when one exists |
| CTA | Says the one next step | One imperative, said once | Two or three competing actions; none |

## How the script labels

- First sentence, and any sentence starting in the first 3 seconds when timed, is the hook (unless it is a call to action).
- Imperative verbs ("shop", "get", "try", "tap", "click", "order") mark a CTA.
- Prices, percentages, "free", "code", "off" mark an offer.
- Numbers with a unit of time or count, "reviews", "tested", "I've used" mark proof.
- The product or brand words you pass with `--product`, and phrases like "introducing" or "that's why", mark the solution.
- "Never", "can't", "tired of", "used to" mark the problem; "worse", "every time", "keeps" mark agitation.

Keywords are blunt. Read every label and fix the wrong ones before you score anything.

## Timing

With timestamps the script reports time to the first product mention, time to the first CTA, and words per second. These describe this script, so compare a script with its own rewrite or with the user's other ads, never with a number from outside. A wall of words per second is a signal to cut, and a long silence is a signal to check that the visuals carry the story.

## Claims

Words like "best", "guaranteed", "cure", "clinically", "proven" and "#1" make a claim the brand must be able to prove. The script flags them; it cannot judge whether they are true. Mark each one "needs sign-off" and keep it out of a rewrite unless the user confirms the proof exists.
