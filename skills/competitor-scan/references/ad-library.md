# Collecting ads from the Meta Ad Library

The Meta Ad Library (https://www.facebook.com/ads/library) shows the ads currently running across Meta's platforms, to anyone, without logging in. Use only what it shows a visitor.

## Steps

1. Open the library, choose the country, and set the ad category to all ads.
2. Search a rival by its page name. Open the page's ads and filter to **active** ads.
3. For each ad, record one row (a spreadsheet or a pasted table is fine). For a long list, the most recent and the longest-running ads tell you the most.
4. Repeat for each rival. Note the date you collected them.

## Columns

| Column | What to put | Required |
|---|---|---|
| `advertiser` | the page name as the library shows it | yes |
| `ad_text` | the primary text | yes (or `headline`) |
| `headline` | the headline under the media, if shown | no |
| `format` | image, video or carousel | no |
| `started` | the date the library says the ad started running (YYYY-MM-DD) | no, but longevity needs it |
| `cta` | the button text | no |
| `platforms` | where it runs, if shown | no |

Leave out image and video links. The script skips any value that is a web address anyway, and keeps no media.

## What the library can and cannot tell you

- It shows that an ad is live and when it started. A long run hints that the rival keeps funding it.
- It does not show results, spend, reach or targeting for most commercial ads. Never infer them.
- Several near-identical ads usually mean one idea being tested in versions: count the idea once when you read the clusters.

## Care

- Collect by hand or with the agent's browsing at a human pace. No logins, no bulk collection, nothing behind the visitor view.
- Keep the scan for the team's own planning. Do not publish rivals' ads or copy their wording.
