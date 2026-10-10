# Writing copy variants

## The parts of a feed ad's text

- **Primary text:** the text above the media. Its opening line belongs to `hook-writer`; this skill writes what follows. Only the first lines show before "more", and the cut-off depends on placement and device, so the first sentence has to stand alone.
- **Headline:** the bold line under the media, beside the button. It names the product or the offer, not the brand's slogan.
- **Description:** the smaller line under the headline. Many placements hide it; never put anything essential there.
- **Call to action:** the button. Choose the one that matches the next step on the page ("Shop now" only if the page sells).

## Meta's published text recommendations

Meta's own ad specs give a recommended range for primary text and a headline length for Facebook Feed image and video ads (checked 2026-10-10):

- Image: https://www.facebook.com/business/ads-guide/update/image/facebook-feed
- Video: https://www.facebook.com/business/ads-guide/update/video/facebook-feed

`copy_check.py` uses the top of the primary-text range and the headline length as its default limits. These are Meta's recommendations for what displays well, not limits Meta enforces and not rules of this package. The feed spec gives no description length, so set one with `--limits` only if your placement preview shows a cut. Meta changes its specs: check the pages before relying on the numbers, and look at the placement preview in Ads Manager.

## Tie every variant to a persona and a hook

Each variant row names the persona (from `persona-builder`) and the hook (from `hook-writer`). Copy for a person who already knows the problem reads differently from copy for someone who has never thought about it. Write to the persona's starting state and the proof they need.

## One change per variant

| Change | Example (fictional Acme Outdoor Co., illustrative) |
|---|---|
| Angle of the primary text | proof-led ("Tested on a wet ridge walk") against problem-led ("Soaked socks end a hike early") |
| Proof | a test result the brand can stand behind against a guarantee |
| Offer framing | "free returns" against "free shipping" (only offers the brand runs) |
| Headline | product name against benefit |
| Call to action | "Shop now" against "Learn more" |

Hold everything else still: the media, the opening line, the audience, the budget split. Label the one thing that changed.

## Claims and care

- Every claim must be one the brand can substantiate. Mark the rest "needs sign-off".
- No invented reviews or quotes. Use real customer words only with permission, and label any example as illustrative.
- No false urgency: a deadline in the copy must be real (see `sale-planner/references/consumer-law.md`).
- Regulated categories need a check against the platform's ad policies and local advertising law before anything runs.
