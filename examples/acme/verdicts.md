# Acme keep-or-kill output

Generated, not hand-written: `python3 skills/keep-or-kill/scripts/verdicts.py examples/acme/ads_daily.csv` on the fictional Acme Outdoor Co. fixture.

```text
Basis: each ad graded against this account's own ads (same format group), never a benchmark.
Window: 2026-03-01 to 2026-03-30. Fatigue compares each ad's first and last 6 delivery days.
Settings used (arbitrary defaults, set them from your own account): young-days=5, window=6, min-impressions=1000, top-n=3, min-change=8% (a materiality size for ctr, frequency and hook movement, not a fatigue benchmark: set it from your own week-to-week noise).

Summary:
  scale: raise budget in steps                             6
  keep                                                     13
  keep: check whether it feeds other ads before cutting    1
  iterate: refresh the hook or creator, keep the concept   1
  kill: never worked                                       8
  too early (learning)                                     1
  too young to judge: 120000000030
  top 3 ads (N=3, an arbitrary default: set your own) hold 22% of spend. Heavy concentration means one fatigue event hurts the whole account; judge it against your own history.

Verdicts:
120000000002  [ugc-video]  age 29 d, scale: raise budget in steps
    - payback: cpa top quartile, roas top quartile
    - trend over first vs last 6 delivery days: ctr +1%, frequency +7%, hook rate +1% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000021  [carousel]  age 29 d, scale: raise budget in steps
    - payback: cpa top quartile, roas top quartile
    - trend over first vs last 6 delivery days: ctr -2%, frequency +9%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000022  [partnership]  age 29 d, scale: raise budget in steps
    - payback: cpa top quartile, roas top quartile
    - trend over first vs last 6 delivery days: ctr -5%, frequency +9%, hook rate -8% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000026  [static]  age 29 d, scale: raise budget in steps
    - payback: cpa top quartile, roas top quartile
    - trend over first vs last 6 delivery days: ctr -7%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000024  [carousel]  age 21 d, scale: raise budget in steps
    - payback: cpa top quartile, roas top quartile
    - trend over first vs last 6 delivery days: ctr -4%, frequency +5%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
    - promo: strong payback can be existing demand being harvested; check new-customer share and the sale end date before raising budget
120000000019  [ugc-video]  age 14 d, scale: raise budget in steps
    - payback: cpa top quartile, roas top quartile
    - trend over first vs last 6 delivery days: ctr +6%, frequency +4%, hook rate -7% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
    - promo: strong payback can be existing demand being harvested; check new-customer share and the sale end date before raising budget
120000000003  [static]  age 29 d, keep
    - payback: cpa top quartile, roas middle
    - trend over first vs last 6 delivery days: ctr -6%, frequency +9%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000006  [founder-video]  age 29 d, keep
    - payback: cpa middle, roas middle
    - trend over first vs last 6 delivery days: ctr +6%, frequency +8%, hook rate -4% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000008  [partnership]  age 29 d, keep
    - payback: cpa middle, roas top quartile
    - trend over first vs last 6 delivery days: ctr -3%, frequency +9%, hook rate +3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000009  [carousel]  age 29 d, keep
    - payback: cpa bottom quartile, roas middle
    - trend over first vs last 6 delivery days: ctr -1%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is bottom quartile but not from the start and not fatiguing: watch it
120000000011  [founder-video]  age 29 d, keep
    - payback: cpa middle, roas middle
    - trend over first vs last 6 delivery days: ctr -9%, frequency +7%, hook rate -0% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000028  [ugc-video]  age 29 d, keep
    - payback: cpa middle, roas top quartile
    - trend over first vs last 6 delivery days: ctr -7%, frequency +9%, hook rate +7% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000007  [carousel]  age 24 d, keep
    - payback: cpa middle, roas middle
    - trend over first vs last 6 delivery days: ctr +9%, frequency +5%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000004  [static]  age 21 d, keep
    - payback: cpa middle, roas middle
    - trend over first vs last 6 delivery days: ctr -8%, frequency +4%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000016  [partnership]  age 21 d, keep
    - payback: cpa middle, roas middle
    - trend over first vs last 6 delivery days: ctr -9%, frequency +5%, hook rate -3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000029  [carousel]  age 19 d, keep
    - payback: cpa middle, roas middle
    - trend over first vs last 6 delivery days: ctr +11%, frequency +6%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000013  [carousel]  age 17 d, keep
    - payback: cpa middle, roas bottom quartile
    - trend over first vs last 6 delivery days: ctr +10%, frequency +4%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is bottom quartile but not from the start and not fatiguing: watch it
120000000025  [static]  age 11 d, keep
    - payback: cpa middle, roas top quartile
    - trend over first vs last 6 delivery days: ctr +1%, frequency +1%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000027  [partnership]  age 11 d, keep
    - payback: cpa top quartile, roas middle
    - trend over first vs last 6 delivery days: ctr +0%, frequency +2%, hook rate -2% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000023  [ugc-video]  age 29 d, keep: check whether it feeds other ads before cutting
    - payback: cpa middle, roas bottom quartile
    - trend over first vs last 6 delivery days: ctr +0%, frequency +6%, hook rate -1% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - hook_rate and ctr top quartile but payback is bottom quartile
120000000001  [ugc-video]  age 29 d, iterate: refresh the hook or creator, keep the concept
    - payback: cpa top quartile, roas middle
    - trend over first vs last 6 delivery days: ctr -52%, frequency +122%, hook rate -31% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - fatiguing, but payback is not bottom quartile: the concept still earns
120000000010  [ugc-video]  age 29 d, kill: never worked
    - payback: cpa middle, roas bottom quartile
    - trend over first vs last 6 delivery days: ctr -3%, frequency +8%, hook rate -3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000014  [static]  age 29 d, kill: never worked
    - payback: cpa bottom quartile, roas middle
    - trend over first vs last 6 delivery days: ctr -7%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000017  [static]  age 29 d, kill: never worked
    - payback: cpa not graded (zero conversions), roas bottom quartile
    - trend over first vs last 6 delivery days: ctr +4%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000018  [ugc-video]  age 29 d, kill: never worked
    - payback: cpa bottom quartile, roas middle
    - trend over first vs last 6 delivery days: ctr +6%, frequency +8%, hook rate -2% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000005  [carousel]  age 21 d, kill: never worked
    - payback: cpa bottom quartile, roas bottom quartile
    - trend over first vs last 6 delivery days: ctr +0%, frequency +6%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000012  [static]  age 21 d, kill: never worked
    - payback: cpa bottom quartile, roas bottom quartile
    - trend over first vs last 6 delivery days: ctr -6%, frequency +4%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000015  [ugc-video]  age 17 d, kill: never worked
    - payback: cpa bottom quartile, roas middle
    - trend over first vs last 6 delivery days: ctr -6%, frequency +2%, hook rate -3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000020  [founder-video]  age 14 d, kill: never worked
    - payback: cpa bottom quartile, roas bottom quartile
    - trend over first vs last 6 delivery days: ctr -1%, frequency +4%, hook rate -2% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback was bottom quartile in the first 6 delivery days and still is
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000030  [ugc-video]  age 3 d, too early (learning)
    - learning: 3 days old, under the 5-day learning window
    - no other verdict until it has delivered longer
```
