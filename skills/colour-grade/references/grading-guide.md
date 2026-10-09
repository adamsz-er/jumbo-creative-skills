# Grading guide

How to read the numbers `scripts/palette.py` prints, and what to do about them. Nothing here is a target: judge an image against the brand, the feed around it, and the other ads in the same set.

## Reading the numbers

| Output | What it tells you | How to use it |
|---|---|---|
| Top colours and shares | What the image is mostly made of | A big share of one neutral means the image is a background with a small subject. Check the subject is not the smallest thing on screen. |
| Brightness | How light the image is overall | Compare with the feed it runs in and with the other ads in the set, not with a number. |
| Saturation | How vivid | Vivid can stop a thumb in a muted feed and look loud in a bright one. |
| Warm and cool share | Where the colour leans, among coloured pixels (greys are left out) | Warm reads human and close, cool reads calm and precise. A product shot usually wants its own colour to stay true. |
| Contrast spread | Gap between the lightest and darkest areas | Low spread reads flat and soft; high spread reads graphic. A low spread is a risk for text. |
| Text contrast ratio | WCAG ratio of the two most common colours | A quick check for text over that background. The most common colours are not always the text and its ground, so confirm on the real layout. |

## Stopping a thumb

A thumb-stopper contrasts with what surrounds it. Open the live feed the ad will run in and look at what is on screen: if the ad would blend in, change something the eye reads first (a different background family, a strong subject against a calm ground, a clear light and dark split). Contrast against the feed matters more than prettiness.

## Variety across a set

When most ads in a set share one dominant colour family, such as every ad on the same beige or cream, they read as one ad and fatigue together. Keep the brand colours as accents and vary the ground: change background family, light against dark, and the position of the subject. The set check in `palette.py` flags a shared family so you can see it, but whether that sameness is a problem is a judgement about the brand: a strong, consistent look is a choice.

## Brand colours

Use them as accents: a button, a line, a product, a headline. A brand colour as wallpaper on every ad is the quickest way to make a set uniform. Keep the exact hex values from the brand profile and check them on the real image rather than guessing from a photo of a screen.

## Looks, and what each signals

| Look | Feels like | Use when |
|---|---|---|
| Warm | Friendly, human, close | Lifestyle, food, gifting, community |
| Natural | Honest, unprocessed, documentary | UGC, testimonial, product demo, trust-led offers |
| Punchy | Energetic, urgent, bold | Launches, sales, short-attention formats |
| Muted | Quiet, premium, considered | Considered purchases, craft, editorial |
| High-key | Clean, light, simple | Skincare, home, anything that needs to feel pure; test against a white feed |

These are hypotheses about how a look is read. Test them on the account and read results against its own baseline.

## Text and safe zones

- Keep key text and the product away from the edges and from the areas that placement interfaces cover (the top and bottom of vertical formats are the usual ones). Check the current safe-zone guides for each placement in Ads Manager's preview, because they change.
- Text over a photo needs a solid or darkened area behind it; measure it with the contrast ratio, then check it by eye.
- Never rely on colour alone to carry meaning: pair it with a word or a shape.
- Check every candidate on a phone at arm's length, in bright light if you can. A layout that reads on a desktop monitor can fail on a phone.

## Video frames

Export the first frame, a middle frame and the end card. The first frame is what the scroll decides on, so measure that one first. If frames share nothing in common, the ad may feel disjointed; if the end card clashes with the opening, the brand may not read as one.
