# Acme palette output

Generated, not hand-written: `python3 skills/colour-grade/scripts/palette.py examples/acme/swatch.png`. The image is a made-up swatch of flat colour blocks (`python3 tools/make_swatch.py`), not a real ad, so the shares are exact by construction. Example output for a fictional brand.

```text
Basis: colours counted from each image's own pixels (standard-library PNG decoder, 4-bit buckets). Shares are of counted pixels; brightness, saturation and contrast spread are 0-100 scales on that image; warm and cool are shares of its coloured pixels (greys excluded).

examples/acme/swatch.png
  colours: #2F4A3A 36%, #E6DCC8 24%, #B5532A 18%, #3B4A5A 13%, #D9A441 9%
  brightness 47, saturation 41, warm 51% / cool 49%, contrast spread 66
  text legibility: the two most common colours have a WCAG contrast ratio of 7.1:1
```

## Direction (written by following the skill)

- **What to change first:** nothing is wrong with legibility, but the two biggest areas are the forest green and the sand, both quiet. In a feed of bright creative this palette would need a stronger subject to stop a thumb.
- **Current look:** natural and slightly muted, balanced warm and cool. It signals honest, practical gear, which matches the brand profile.
- **Brand colours:** keep forest green `#2F4A3A` and sand `#E6DCC8` as the ground and the text; give the burnt orange `#B5532A` and ochre `#D9A441` to the one thing the eye should land on (the product or the offer), as accents, not wallpaper.
- **Text:** green on sand reads clearly. Confirm on the real layout and check it on a phone.
- **Set check:** run it on the whole folder of ads: if most share this green or sand ground, vary the background family across the set.
