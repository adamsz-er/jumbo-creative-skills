# Seeding the brand profile from public research

Given a brand name and its website (or an existing `creative-profile.md`), research the brand on the public web and draft what customers and the brand itself say, so the profile starts from evidence rather than a blank form. The user confirms every line before it is saved.

## What to look for, and where

| Topic | Look at | What to note |
|---|---|---|
| Claims | The brand's home, product and about pages | What the brand says its products do, in its own terms |
| Proof points | Product pages, guarantee and shipping pages, press pages | Tests, materials, guarantees, awards: things the brand can show |
| Objections | Public reviews, Q&A sections, public forum threads | What stops people buying, or what disappointed them |
| Tone | The brand's own copy, its posts | How it speaks: three to five words, plus words it avoids |
| Category words | Reviews, competitors' pages, search suggestions | The words customers use for the problem and the product |
| Products | The site's navigation and collection pages | Hero products and ranges |

Use only pages any visitor can open. No logins, no paywalls, no scraping beyond reading pages as a person would.

## How to write each line

Every seeded line is a bullet under its topic, with a label and its source:

```
## Seeded from public research

### Claims
- Keeps feet dry on wet trails [from the brand's site] (https://acme-outdoor.example/boots)

### Objections
- Some buyers found the boots stiff for the first few walks [from public reviews] (https://reviews.example/acme-trail-boot)

### Tone
- Plain, practical, outdoorsy; avoids hype [inferred] (based on: the product and about pages)
```

- **[from the brand's site]** with the page URL: what the brand says about itself.
- **[from public reviews]** with the page URL: a paraphrase of what reviewers say, never a quote. Reviews are opinions; do not turn a few into a statistic, and leave star ratings and percentages out (they change and need a date).
- **[inferred]** with `(based on: ...)` naming what it was inferred from: your reading, labelled as such. An inference never contains a number.
- **Nothing found** for a topic: write `- nothing found [inferred] (based on: search returned nothing)` rather than filling the gap.

Never invent a claim, a proof point or a customer opinion. If you cannot find it, it stays unknown.

## Check, confirm, save

1. Write the draft to a file (not over the existing profile) and run the checker:

   ```
   python3 -I scripts/research_check.py profile-draft.md
   ```

   It flags unlabelled lines, missing sources, quoted reviews, figures in reviews or inferences, review links on the brand's own domain, and empty topics. Fix every problem it lists.
2. Show the user the draft in one message: "Here is what I found in public. Correct anything, delete what is wrong, or say OK."
3. Only after the user says OK, move the confirmed lines into `creative-profile.md` under the matching fields, keeping each label and source.

## When there is no web access

Say so plainly: "I can't browse from here, so I can't research the brand." Then fall back to asking the user the profile questions in `brand-profile-template.md`, and offer to check a draft they paste with `research_check.py`.
