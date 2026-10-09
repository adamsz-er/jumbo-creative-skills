---
name: colour-grade
description: Extract the colour palette of ad images or video frames and give colour and grading direction - dominant colours, brightness, saturation, warm or cool balance, contrast, text legibility, and whether a set of ads all share one look. Use when the user shares ad images or a folder, asks why creative blends into the feed, wants colour direction for a brief, or needs a grading look (warm, natural, punchy, muted, high-key). Works with no images too, from the brand profile.
license: MIT
metadata:
  version: "0.1.0"
  role: analyse
---

# Colour grade

Measures the colour of ad images and turns the numbers into direction: what the palette signals, whether it will stand out against the rest of a feed, whether the text on it can be read, and whether a set of ads looks too alike. The numbers describe the images. There are no target values.

## Pick the input and say it out loud

1. **One image.** A PNG or, with Pillow installed, JPEG, WebP and others.
2. **A folder.** A set of ads, to compare them. The tool flags when most images share a dominant colour family.
3. **Video frames.** Ask the user to export a few frames (the first frame, the middle, the end card) as images. Never run video through an outside service.
4. **No images.** Say so. Give colour direction for a brief from `creative-profile.md` (brand colours, tone) and label it "no images measured".

## Run it

```
python3 -I scripts/palette.py ad.png
python3 -I scripts/palette.py ads-folder/ --k 6
python3 -I scripts/palette.py ads-folder/ --json
```

`--k` is how many colours to report (default 6, an arbitrary default). With Pillow installed it uses median cut. Without it, PNG files still work through a standard-library decoder; any other format exits 2 with a message. In that case ask the user to install Pillow (`pip install pillow`), to export PNGs, or describe the colours yourself from the image and say they were not measured.

Per image it prints the top colours with their share, average brightness, saturation, the warm and cool share of the coloured pixels, a contrast spread (how far apart the darkest and lightest areas are), and the WCAG contrast ratio of the two most common colours, which is a quick read on text over background. `references/grading-guide.md` explains how to read each number for ads.

## Give the direction

1. Lead with the one thing most worth changing: a set that shares one look, text that cannot be read, or a palette that matches the feed around it.
2. Describe the current look in plain words (warm and muted, high-key and clean) and what it signals.
3. Name the brand colours and where they should sit (accent, not wallpaper).
4. Suggest a grading look and a safe layout for text, from `references/grading-guide.md`.
5. For a set, say which images differ and which repeat.
6. Ask the user to check legibility on a phone before approving.

## Guardrails

- No benchmarks and no target percentages. A palette is judged against the brand, the feed it runs in, and the other ads in the same set.
- The numbers come from a compressed, shrunk image: treat close values as equal and say when you are guessing.
- Colour meaning varies by market and category. Offer it as a hypothesis to test, not a rule.
- Read only. Do not touch the ad account.

## How to use

Have ready: one image, a folder of ads, or exported video frames. PNG works as is; other formats need Pillow.

Try:

- "What does the palette of these ads say, and do they all look alike?"
- "Check legibility of the text colour on this ad."
- "Give colour direction for my next brief."

## Common questions

- **JPEG fails?** Install Pillow (`pip install pillow`) or export PNG.
- **Is the colour reading exact?** No; it comes from a shrunk image, so treat close values as equal.
- **Does colour meaning carry across markets?** No; treat it as a hypothesis to test.
- **Video?** Export a few frames as images; nothing leaves your machine.
- More: creative-context/references/faq.md
