# Ad types

Tag every ad with exactly one type. Compare ads within a type, because a promo ad and an always-on ad do different jobs.

| Type | What it is | How to read it |
|---|---|---|
| `bau` (BAU / evergreen) | Always-on creative with no end date and no dependence on an offer. | The long-run baseline. Fatigue is the main risk. |
| `promo` (promo / sale) | Carries an offer and dates. | Retire it when the sale ends. Strong ROAS can be existing demand being harvested, so check new-customer share before scaling. |
| `launch` (new product release / new arrivals) | Introduces a product or a drop. | Needs a drop cadence with fresh creative each time. Don't send traffic to products that are out of stock. Don't credit a launch spike to BAU ads running alongside. |
| `hype` (hype / teaser) | Builds anticipation before a launch or sale. | Judge on attention and registrations, not on revenue. |
| `partnership` (partnership / creator) | Creator-fronted or brand-handle ads. | Track usage-rights end dates. Run as a dedicated test. Quality varies with the source of the creator. |
| `retention` | Aimed at people who already bought. | Judge separately. It flatters blended results and does not acquire anyone. |

## Synonyms

Names use many words for the six types. `creative_metrics.SYNONYMS` maps them (case-insensitive), so `TYPE:sale` reads as `promo`:

| Type | Words read as that type |
|---|---|
| `promo` | sale, promo, offer, discount, bfcm |
| `bau` | bau, evergreen, always-on, aon |
| `launch` | launch, drop, newin |
| `hype` | hype, teaser, tease |
| `partnership` | collab, partnership, influencer, whitelist, spark |
| `retention` | retention, rtg, existing, loyalty |

A word that is not on this list is kept as written, counted, and shown in the mix and detection output. Ask the user which type it is, in one question that lists every unknown word, and never drop those ads or guess. Then pass the answer on as the type for those ads.

## Rules

- One type per ad. If an ad is both a launch and a creator ad, record the purpose (`launch`) and put the creator in the creator field.
- Overlay the offer and launch calendar on any results view, so a spike is credited to the right type.
- Sale creative must show its offer and dates. Evergreen creative should work without an offer.
- Prospecting and retargeting need different measures: attention and new-customer cost for prospecting, conversion and incremental lift for retargeting.
- Record the calendar in the brand profile so type can be checked against dates.
