# Acme spend-analysis output

Generated, not hand-written, on the fictional Acme Outdoor Co. fixture (synthetic data, not a real account). The verdicts come from keep-or-kill with an illustrative target (`--target roas=3`): a user's own target is needed before any ad is judged pause.

First, the verdicts file it reads:

`python3 -I skills/keep-or-kill/scripts/verdicts.py examples/acme/ads_daily.csv --target roas=3 --json > verdicts.json`

Then:

`python3 -I skills/spend-analysis/scripts/spend.py examples/acme/ads_daily.csv --verdicts verdicts.json`

```text
Where the money goes: 19 of 30 ads hold 80% of spend; the biggest concept is comparison (8% of spend).
Spend on ads judged pause: USD 10990.00 (9% of spend, 3 ads).
Top move: shift USD 329.54 a day from 120000000020 to the scale ads (Early read). raise in steps you have seen your account absorb before.

Totals (USD; 2026-03-01 to 2026-03-30, 30 days)
  spend USD 119506.34; purchases 4173; purchase value 523807.70; roas 4.38; cpa 28.64

Concentration (80% is a common convention, not a rule; set your own)
  spend: 19 of 30 ads (63%) hold 81% of spend
  purchase value: 17 of 30 ads (57%) hold 81% of purchase value
  top 3 ads hold 22% of spend

Spend by dimension (roas vs account: 100 = the same as the account)
  Note: age is from first delivery in the window, so older ads may be understated.
  Concept:
    comparison: 1 ad; spend USD 9973.18 (8%); purchases 359; value 44462.71; roas 4.46; cpa 27.78; vs account 102
    durability-test: 1 ad; spend USD 9061.59 (8%); purchases 295; value 30759.34; roas 3.39; cpa 30.72; vs account 77
    packing-list: 1 ad; spend USD 7697.58 (6%); purchases 280; value 33900.59; roas 4.40; cpa 27.49; vs account 100
    staff-picks: 1 ad; spend USD 7542.52 (6%); purchases 370; value 60528.60; roas 8.02; cpa 20.39; vs account 183
    behind-the-seams: 1 ad; spend USD 7333.17 (6%); purchases 229; value 36150.56; roas 4.93; cpa 32.02; vs account 112
    weather-ready: 1 ad; spend USD 5628.39 (5%); purchases 148; value 15223.84; roas 2.70; cpa 38.03; vs account 62
    problem-cold-feet: 1 ad; spend USD 5480.99 (5%); purchases 139; value 14505.03; roas 2.65; cpa 39.43; vs account 60
    founder-note: 1 ad; spend USD 4943.16 (4%); purchases 83; value 12617.16; roas 2.55; cpa 59.56; vs account 58
    unboxing: 1 ad; spend USD 4832.85 (4%); purchases 105; value 14190.48; roas 2.94; cpa 46.03; vs account 67
    before-after: 1 ad; spend USD 4266.75 (4%); purchases 95; value 11595.14; roas 2.72; cpa 44.91; vs account 62
    social-proof: 1 ad; spend USD 4181.93 (3%); purchases 208; value 27019.96; roas 6.46; cpa 20.11; vs account 147
    new-drop-two: 1 ad; spend USD 3840.89 (3%); purchases 172; value 13795.34; roas 3.59; cpa 22.33; vs account 82
    social-proof-reviews: 1 ad; spend USD 3420.65 (3%); purchases 159; value 23756.85; roas 6.95; cpa 21.51; vs account 158
    guarantee: 1 ad; spend USD 3365.80 (3%); purchases 0; value 0.00; roas 0.00; cpa n/a (zero conversions); vs account 0
    sale-bundle: 1 ad; spend USD 3299.57 (3%); purchases 188; value 26816.81; roas 8.13; cpa 17.55; vs account 185
    trail-diary: 1 ad; spend USD 3247.68 (3%); purchases 151; value 19071.01; roas 5.87; cpa 21.51; vs account 134
    new-drop: 1 ad; spend USD 3147.94 (3%); purchases 121; value 16353.15; roas 5.19; cpa 26.02; vs account 119
    partnership-haul: 1 ad; spend USD 2992.62 (3%); purchases 114; value 18535.92; roas 6.19; cpa 26.25; vs account 141
    gift-guide-two: 1 ad; spend USD 2898.63 (2%); purchases 112; value 12209.55; roas 4.21; cpa 25.88; vs account 96
    sale-countdown: 1 ad; spend USD 2761.08 (2%); purchases 105; value 15401.73; roas 5.58; cpa 26.30; vs account 127
    problem-first: 1 ad; spend USD 2752.19 (2%); purchases 172; value 13346.00; roas 4.85; cpa 16.00; vs account 111
    sale-percent-off: 1 ad; spend USD 2681.04 (2%); purchases 61; value 4374.82; roas 1.63; cpa 43.95; vs account 37
    founder-story: 1 ad; spend USD 2624.79 (2%); purchases 105; value 8723.04; roas 3.32; cpa 25.00; vs account 76
    fix-it-yourself: 1 ad; spend USD 2482.13 (2%); purchases 65; value 8643.43; roas 3.48; cpa 38.19; vs account 79
    partnership-trail: 1 ad; spend USD 2147.59 (2%); purchases 75; value 6725.06; roas 3.13; cpa 28.63; vs account 71
    sale-last-chance: 1 ad; spend USD 2142.91 (2%); purchases 80; value 11930.88; roas 5.57; cpa 26.79; vs account 127
    new-drop-three: 1 ad; spend USD 1832.25 (2%); purchases 84; value 12921.88; roas 7.05; cpa 21.81; vs account 161
    gift-guide: 1 ad; spend USD 1257.32 (1%); purchases 39; value 4867.47; roas 3.87; cpa 32.24; vs account 88
    partnership-camp: 1 ad; spend USD 998.76 (1%); purchases 51; value 4060.08; roas 4.07; cpa 19.58; vs account 93
    new-drop-four: 1 ad; spend USD 670.39 (1%); purchases 8; value 1321.27; roas 1.97; cpa 83.80; vs account 45
  Format:
    ugc-video: 9 ads; spend USD 37318.19 (31%); purchases 1107; value 121515.41; roas 3.26; cpa 33.71; vs account 74
    carousel: 7 ads; spend USD 29684.45 (25%); purchases 1282; value 168471.51; roas 5.68; cpa 23.15; vs account 129
    static: 7 ads; spend USD 28215.93 (24%); purchases 976; value 127937.95; roas 4.53; cpa 28.91; vs account 103
    founder-video: 3 ads; spend USD 14901.12 (12%); purchases 417; value 57490.76; roas 3.86; cpa 35.73; vs account 88
    partnership: 4 ads; spend USD 9386.65 (8%); purchases 391; value 48392.07; roas 5.16; cpa 24.01; vs account 118
  Ad type:
    bau: 16 ads; spend USD 82051.96 (69%); purchases 2889; value 366222.02; roas 4.46; cpa 28.40; vs account 102
    launch: 7 ads; spend USD 20266.24 (17%); purchases 624; value 75259.36; roas 3.71; cpa 32.48; vs account 85
    promo: 7 ads; spend USD 17188.14 (14%); purchases 660; value 82326.32; roas 4.79; cpa 26.04; vs account 109
  Age:
    18-35 days: 23 ads; spend USD 100245.13 (84%); purchases 3590; value 452970.61; roas 4.52; cpa 27.92; vs account 103
    9-17 days: 6 ads; spend USD 18590.82 (16%); purchases 575; value 69515.82; roas 3.74; cpa 32.33; vs account 85
    under 9 days: 1 ad; spend USD 670.39 (1%); purchases 8; value 1321.27; roas 1.97; cpa 83.80; vs account 45
  Verdict:
    keep: 17 ads; spend USD 69640.53 (58%); purchases 2428; value 299912.46; roas 4.31; cpa 28.68; vs account 98
    scale: 6 ads; spend USD 22405.52 (19%); purchases 1120; value 155450.15; roas 6.94; cpa 20.00; vs account 158
    pause: 3 ads; spend USD 10990.00 (9%); purchases 144; value 16991.98; roas 1.55; cpa 76.32; vs account 35
    iterate: 1 ad; spend USD 9061.59 (8%); purchases 295; value 30759.34; roas 3.39; cpa 30.72; vs account 77
    check: 2 ads; spend USD 6738.31 (6%); purchases 178; value 19372.50; roas 2.87; cpa 37.86; vs account 66
    not judged yet: 1 ad; spend USD 670.39 (1%); purchases 8; value 1321.27; roas 1.97; cpa 83.80; vs account 45

Spend on ads judged pause: USD 10990.00 (9% of spend); never worked: USD 10990.00 (9%); USD 366.33 a day across the window
  120000000020 [never worked] (USD 4943.16, 4%): Pause it: after 15 days it costs USD 59.56 per sale, more than most of your sales ads, and it was weak from the start.
  120000000017 [never worked] (USD 3365.80, 3%): Pause it: after 30 days it has not brought back any sales, and it was weak from the start. Early read: small comparison group (7 similar ads).
  120000000012 [never worked] (USD 2681.04, 2%): Pause it: after 22 days it costs USD 43.95 per sale, more than most of your similar ads, and it was weak from the start. Early read: small comparison group (6 similar ads).

Room to scale
  scale:
    120000000021: 6% of spend; roas vs account 183; frequency 1.35; room: frequency at or below the format median
    120000000026: 3% of spend; roas vs account 158; frequency 1.35; watch: frequency above most ads of its format
    120000000024: 3% of spend; roas vs account 185; frequency 1.38; watch: frequency above most ads of its format
    120000000022: 3% of spend; roas vs account 134; frequency 1.21; room: frequency at or below the format median
    120000000002: 2% of spend; roas vs account 111; frequency 1.34; watch: frequency above most ads of its format
    120000000019: 2% of spend; roas vs account 127; frequency 1.25; room: frequency at or below the format median
  keep:
    120000000014: 8% of spend; roas vs account 102; frequency 1.37; watch: frequency above most ads of its format
    120000000009: 6% of spend; roas vs account 100; frequency 1.33; room: frequency at or below the format median
    120000000011: 6% of spend; roas vs account 112; frequency 1.22; room: frequency at or below the format median
    120000000010: 5% of spend; roas vs account 62; frequency 1.22; room: frequency at or below the format median
    120000000015: 4% of spend; roas vs account 67; frequency 1.31; frequency between the format median and the top quarter of its format
    120000000018: 4% of spend; roas vs account 62; frequency 1.26; room: frequency at or below the format median
    120000000003: 3% of spend; roas vs account 147; frequency 1.30; room: frequency at or below the format median
    120000000013: 3% of spend; roas vs account 82; frequency 1.38; watch: frequency above most ads of its format
    120000000007: 3% of spend; roas vs account 119; frequency 1.36; frequency between the format median and the top quarter of its format
    120000000008: 3% of spend; roas vs account 141; frequency 1.23; room: frequency at or below the format median
    120000000029: 2% of spend; roas vs account 96; frequency 1.27; room: frequency at or below the format median
    120000000004: 2% of spend; roas vs account 127; frequency 1.23; room: frequency at or below the format median
    120000000006: 2% of spend; roas vs account 76; frequency 1.26; room: frequency at or below the format median
    120000000028: 2% of spend; roas vs account 79; frequency 1.22; room: frequency at or below the format median
    120000000016: 2% of spend; roas vs account 71; frequency 1.21; room: frequency at or below the format median
    120000000025: 2% of spend; roas vs account 161; frequency 1.27; room: frequency at or below the format median
    120000000027: 1% of spend; roas vs account 93; frequency 1.18; room: frequency at or below the format median

Budget moves (raise in steps you have seen your account absorb before)
  Move USD 329.54 a day from 120000000020 [Early read]
    to 120000000002: USD 40.48 a day (12% of the scale spend)
    to 120000000021: USD 110.94 a day (34% of the scale spend)
    to 120000000022: USD 47.77 a day (14% of the scale spend)
    to 120000000026: USD 50.31 a day (15% of the scale spend)
    to 120000000024: USD 48.53 a day (15% of the scale spend)
    to 120000000019: USD 31.52 a day (10% of the scale spend)
    evidence: Pause it: after 15 days it costs USD 59.56 per sale, more than most of your sales ads, and it was weak from the start.
    evidence: 120000000002: roas 111% against the account's pooled roas
    evidence: 120000000021: roas 183% against the account's pooled roas
    evidence: 120000000022: roas 134% against the account's pooled roas
    evidence: 120000000026: roas 158% against the account's pooled roas
    evidence: 120000000024: roas 185% against the account's pooled roas
    evidence: 120000000019: roas 127% against the account's pooled roas
  Move USD 112.19 a day from 120000000017 [Early read]
    to 120000000002: USD 13.78 a day (12% of the scale spend)
    to 120000000021: USD 37.77 a day (34% of the scale spend)
    to 120000000022: USD 16.26 a day (14% of the scale spend)
    to 120000000026: USD 17.13 a day (15% of the scale spend)
    to 120000000024: USD 16.52 a day (15% of the scale spend)
    to 120000000019: USD 10.73 a day (10% of the scale spend)
    evidence: Pause it: after 30 days it has not brought back any sales, and it was weak from the start. Early read: small comparison group (7 similar ads).
    evidence: 120000000002: roas 111% against the account's pooled roas
    evidence: 120000000021: roas 183% against the account's pooled roas
    evidence: 120000000022: roas 134% against the account's pooled roas
    evidence: 120000000026: roas 158% against the account's pooled roas
    evidence: 120000000024: roas 185% against the account's pooled roas
    evidence: 120000000019: roas 127% against the account's pooled roas
  Move USD 121.87 a day from 120000000012 [Early read]
    to 120000000002: USD 14.97 a day (12% of the scale spend)
    to 120000000021: USD 41.02 a day (34% of the scale spend)
    to 120000000022: USD 17.66 a day (14% of the scale spend)
    to 120000000026: USD 18.61 a day (15% of the scale spend)
    to 120000000024: USD 17.95 a day (15% of the scale spend)
    to 120000000019: USD 11.66 a day (10% of the scale spend)
    evidence: Pause it: after 22 days it costs USD 43.95 per sale, more than most of your similar ads, and it was weak from the start. Early read: small comparison group (6 similar ads).
    evidence: 120000000002: roas 111% against the account's pooled roas
    evidence: 120000000021: roas 183% against the account's pooled roas
    evidence: 120000000022: roas 134% against the account's pooled roas
    evidence: 120000000026: roas 158% against the account's pooled roas
    evidence: 120000000024: roas 185% against the account's pooled roas
    evidence: 120000000019: roas 127% against the account's pooled roas
  check before moving money: 120000000023 - Check before cutting: it catches attention (hook_rate) but pays back weakly. See whether it feeds your other ads first. Early read: small comparison group (6 similar ads).
  check before moving money: 120000000005 - Check before cutting: it catches attention (ctr) but pays back weakly. See whether it feeds your other ads first. Early read: small comparison group (7 similar ads).
  refresh the creative before changing its budget: 120000000001 - Refresh it, keep the idea: people are tiring of it (more repeat views, fewer clicks), but its payback is not weak. Change the opening or the creator. Early read: small comparison group (6 similar ads).
```
