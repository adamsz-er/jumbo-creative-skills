# Acme sale-planner: reading a past sale

Generated, not hand-written, on the fictional Acme Outdoor Co. fixture (synthetic data, not a real account). The sale dates and margins are illustrative inputs; the value is platform-attributed purchase value, not store revenue.

`python3 -I skills/sale-planner/scripts/sale_lift.py examples/acme/ads_daily_extended.csv --sale-from 2026-03-16 --sale-to 2026-03-22 --baseline-days 13 --post-days 8 --min-baseline-days 6 --margin 38 --baseline-margin 52`

```text
Sale read: 2026-03-16 to 2026-03-22 (7 days)
Net lift, sale plus the days after: purchase value (platform-attributed) +86786.47 (+39.2%) and +694.0 purchases (+39.5%) (baseline: weekday-matched mean of 13 days, 2026-03-03 to 2026-03-15).
Incremental roas 3.79 fell short of the account's own baseline roas of 4.55.
Biggest caveat: this is platform-attributed purchase value, not store revenue: it can over- or under-count the sale.

Basis: the account's own daily data 2026-03-01 to 2026-03-30, amounts in USD. Baseline: 13 dated days 2026-03-03 to 2026-03-15 (--baseline-days 13 (yours); --gap-days 0 (default); --post-days 8 (yours); --min-baseline-days 6 (yours)).
The baseline may include other promotions: pass --exclude FROM:TO (YYYY-MM-DD, inclusive, repeatable) for each one.
Value: platform-attributed purchase value, not store revenue: it can over- or under-count the sale.

Sale window: actual vs what the baseline predicts for the same weekdays
  spend: actual 33019.54, expected 22805.24, lift +10214.30 (+44.8%)
  purchases: actual 1135.00, expected 823.00, lift +312.00 (+37.9%)
  purchase value (platform-attributed): actual 142146.25, expected 103414.49, lift +38731.76 (+37.5%)
  new-customer purchases: actual 560.00, expected 422.50, lift +137.50 (+32.5%)
  sale roas 4.30, cpa 29.09
  baseline roas 4.55, cpa 27.51
  incremental roas: 3.79

New vs returning customers (new-customer purchase share):
  sale: 49.3%
  baseline: 51.8%

After the sale (pull-forward):
  purchases: actual 1315.00, expected 933.00, lift +382.00
  purchase value (platform-attributed): actual 165861.73, expected 117807.01, lift +48054.72
  no dip after the sale in the days read.

Contribution:
  sale window: -9974.26
  sale + post window: +2255.82
  formula: sale value x margin 38% - expected value x baseline margin 52% - extra spend.
```
