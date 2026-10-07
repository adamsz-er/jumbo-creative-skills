# Acme keep-or-kill output

Generated, not hand-written: `python3 -I skills/keep-or-kill/scripts/verdicts.py examples/acme/ads_daily.csv --profile examples/acme/brand-profile.md` on the fictional Acme Outdoor Co. fixture.

```text
from the profile: target: cpa=40; currency: USD
Basis: each ad graded against this account's own ads of the same campaign objective (same format, ad_type group, widening when a group has under 5 comparable ads), never a benchmark.
Window: 2026-03-01 to 2026-03-30. Fatigue compares each ad's first and last 6 delivery days.
Settings used (arbitrary defaults, set them from your own account): young-days=5, window=6, min-impressions=1000, top-n=3, protect-top=3, min-change=8% (a materiality size for ctr, frequency and hook movement, not a fatigue benchmark: set it from your own week-to-week noise).
Money is shown in USD.
Objective: not in the data (or not a known objective) for 30 ads, so they are judged as sales: add an objective column to judge each ad on its own goal.
WARNING small comparison groups (fewer than twice the 5-ad minimum; their verdicts are an early read at most): carousel, sales objective n=7, static, sales objective n=6, ugc-video / bau, sales objective n=6, ugc-video, sales objective n=9.
Age basis: first delivery in window (older ads may be understated).

Summary:
  Scale                    6
  Keep                     17
  Check before cutting     2
  Iterate                  1
  Pause                    3
  Too early                1
  too young to judge: 120000000030
  top 3 ads (N=3, an arbitrary default: set your own) hold 22% of spend. Heavy concentration means one fatigue event hurts the whole account; judge it against your own history.

Do these first (largest spend at stake; an ad that cannot be judged never leads):
  120000000001  Iterate: refresh the hook or creator, keep the concept  spend USD 9061.59  [Early read]
  120000000021  Scale: raise budget in steps  spend USD 7542.52  [Early read]
  120000000023  Check before cutting  spend USD 5480.99  [Early read]
  120000000020  Pause: never worked  spend USD 4943.16  [Confident]
  120000000026  Scale: raise budget in steps  spend USD 3420.65  [Early read]

Verdicts (largest spend at stake first within each):
120000000021  [carousel]  age 29 d, Scale: raise budget in steps  (spend USD 7542.52)
    Scale it gradually: it costs USD 20.39 per sale, less than most of your similar ads, and it is not showing signs of wearing out. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas top quartile
    - compared with format: carousel (7 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -2%, frequency +9%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000026  [static]  age 29 d, Scale: raise budget in steps  (spend USD 3420.65)
    Scale it gradually: it costs USD 21.51 per sale, less than most of your similar ads, and it is not showing signs of wearing out. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas top quartile
    - compared with format: static (6 comparable ads); format / ad_type has 3 comparable ads, under 5; format / ad_type has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -7%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000024  [carousel]  age 21 d, Scale: raise budget in steps  (spend USD 3299.57)
    Scale it gradually: it costs USD 17.55 per sale, less than most of your similar ads, and it is not showing signs of wearing out. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas top quartile
    - compared with format: carousel (7 comparable ads); format / ad_type has 3 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -4%, frequency +5%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
    - promo: strong payback can be existing demand being harvested; check new-customer share and the sale end date before raising budget
120000000022  [partnership]  age 29 d, Scale: raise budget in steps  (spend USD 3247.68)
    Scale it gradually: it costs USD 21.51 per sale, less than most of your sales ads, and it is not showing signs of wearing out.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas top quartile
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 2 comparable ads, under 5; format has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -5%, frequency +9%, hook rate -8% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000002  [ugc-video]  age 29 d, Scale: raise budget in steps  (spend USD 2752.19)
    Scale it gradually: it costs USD 16.00 per sale, less than most of your similar ads, and it is not showing signs of wearing out. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas top quartile
    - compared with format / ad_type: ugc-video / bau (6 comparable ads)
    - trend over first vs last 6 delivery days: ctr +1%, frequency +7%, hook rate +1% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
120000000019  [ugc-video]  age 14 d, Scale: raise budget in steps  (spend USD 2142.91)
    Scale it gradually: it costs USD 26.79 per sale, less than most of your similar ads, and it is not showing signs of wearing out. Early read: small comparison group (9 similar ads).
    confidence: Early read (small comparison group: only 9 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas top quartile
    - compared with format: ugc-video (9 comparable ads); format / ad_type has 1 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +6%, frequency +4%, hook rate -7% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is top quartile and the ad is not fatiguing; set the step size from your own account's history
    - promo: strong payback can be existing demand being harvested; check new-customer share and the sale end date before raising budget
120000000014  [static]  age 29 d, Keep  (spend USD 9973.18)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas middle
    - compared with format: static (6 comparable ads); format / ad_type has 3 comparable ads, under 5; format / ad_type has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -7%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000009  [carousel]  age 29 d, Keep  (spend USD 7697.58)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas middle
    - compared with format: carousel (7 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -1%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000011  [founder-video]  age 29 d, Keep  (spend USD 7333.17)
    Keep it running: nothing here says to change it yet.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas middle
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 2 comparable ads, under 5; format has 3 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -9%, frequency +7%, hook rate -0% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000010  [ugc-video]  age 29 d, Keep  (spend USD 5628.39)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas bottom quartile
    - compared with format / ad_type: ugc-video / bau (6 comparable ads)
    - trend over first vs last 6 delivery days: ctr -3%, frequency +8%, hook rate -3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000015  [ugc-video]  age 17 d, Keep  (spend USD 4832.85)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (9 similar ads).
    confidence: Early read (small comparison group: only 9 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas middle
    - compared with format: ugc-video (9 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -6%, frequency +2%, hook rate -3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000018  [ugc-video]  age 29 d, Keep  (spend USD 4266.75)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas middle
    - compared with format / ad_type: ugc-video / bau (6 comparable ads)
    - trend over first vs last 6 delivery days: ctr +6%, frequency +8%, hook rate -2% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000003  [static]  age 29 d, Keep  (spend USD 4181.93)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas middle
    - compared with format: static (6 comparable ads); format / ad_type has 3 comparable ads, under 5; format / ad_type has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -6%, frequency +9%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000013  [carousel]  age 17 d, Keep  (spend USD 3840.89)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas bottom quartile
    - compared with format: carousel (7 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +10%, frequency +4%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000007  [carousel]  age 24 d, Keep  (spend USD 3147.94)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas middle
    - compared with format: carousel (7 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +9%, frequency +5%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000008  [partnership]  age 29 d, Keep  (spend USD 2992.62)
    Keep it running: nothing here says to change it yet.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas top quartile
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 2 comparable ads, under 5; format has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -3%, frequency +9%, hook rate +3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000029  [carousel]  age 19 d, Keep  (spend USD 2898.63)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas middle
    - compared with format: carousel (7 comparable ads); format / ad_type has 3 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +11%, frequency +6%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000004  [static]  age 21 d, Keep  (spend USD 2761.08)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas middle
    - compared with format: static (6 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -8%, frequency +4%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000006  [founder-video]  age 29 d, Keep  (spend USD 2624.79)
    Keep it running: nothing here says to change it yet.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas middle
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 2 comparable ads, under 5; format has 3 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +6%, frequency +8%, hook rate -4% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000028  [ugc-video]  age 29 d, Keep  (spend USD 2482.13)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas top quartile
    - compared with format / ad_type: ugc-video / bau (6 comparable ads)
    - trend over first vs last 6 delivery days: ctr -7%, frequency +9%, hook rate +7% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000016  [partnership]  age 21 d, Keep  (spend USD 2147.59)
    Keep it running: nothing here says to change it yet.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas middle
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 1 comparable ads, under 5; format has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -9%, frequency +5%, hook rate -3% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000025  [static]  age 11 d, Keep  (spend USD 1832.25)
    Keep it running: nothing here says to change it yet. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa middle, roas top quartile
    - compared with format: static (6 comparable ads); format / ad_type has 1 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +1%, frequency +1%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000027  [partnership]  age 11 d, Keep  (spend USD 998.76)
    Keep it running: nothing here says to change it yet.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas middle
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 1 comparable ads, under 5; format has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +0%, frequency +2%, hook rate -2% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
120000000023  [ugc-video]  age 29 d, Check before cutting  (spend USD 5480.99)
    Check before cutting: it catches attention (hook_rate) but pays back weakly. See whether it feeds your other ads first. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas bottom quartile
    - compared with format / ad_type: ugc-video / bau (6 comparable ads)
    - trend over first vs last 6 delivery days: ctr +0%, frequency +6%, hook rate -1% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - hook_rate top quartile but payback is bottom quartile
120000000005  [carousel]  age 21 d, Check before cutting  (spend USD 1257.32)
    Check before cutting: it catches attention (ctr) but pays back weakly. See whether it feeds your other ads first. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas bottom quartile
    - compared with format: carousel (7 comparable ads); format / ad_type has 3 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +0%, frequency +6%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - ctr top quartile but payback is bottom quartile
120000000001  [ugc-video]  age 29 d, Iterate: refresh the hook or creator, keep the concept  (spend USD 9061.59)
    Refresh it, keep the idea: people are tiring of it (more repeat views, fewer clicks), but its payback is not weak. Change the opening or the creator. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa top quartile, roas middle
    - compared with format / ad_type: ugc-video / bau (6 comparable ads)
    - trend over first vs last 6 delivery days: ctr -52%, frequency +122%, hook rate -31% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - fatiguing, but payback is not weak on every measure: the concept still earns
120000000020  [founder-video]  age 14 d, Pause: never worked  (spend USD 4943.16)
    Pause it: after 15 days it costs USD 59.56 per sale, more than most of your sales ads, and it was weak from the start.
    confidence: Confident (enough comparable ads and delivery days, and the payback measures agree)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas bottom quartile
    - compared with all ads: account-wide (29 comparable ads); format / ad_type has 1 comparable ads, under 5; format has 3 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -1%, frequency +4%, hook rate -2% (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is bottom quartile on every measure, in its group and account-wide within its objective, and was bottom in the first 6 delivery days too
    - it misses your target: cpa: it costs USD 59.56 per sale, target USD 40.00
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000017  [static]  age 29 d, Pause: never worked  (spend USD 3365.80)
    Pause it: after 30 days it has not brought back any sales, and it was weak from the start. Early read: small comparison group (7 similar ads).
    confidence: Early read (small comparison group: only 7 similar ads; one payback measure only (roas))
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa not graded (zero conversions), roas bottom quartile
    - compared with format: static (7 comparable ads); format / ad_type has 4 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr +4%, frequency +8%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is bottom quartile on every measure, in its group and account-wide within its objective, and was bottom in the first 6 delivery days too
    - it misses your target: cpa: n/a for this ad (nothing to divide by), target USD 40.00
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000012  [static]  age 21 d, Pause: never worked  (spend USD 2681.04)
    Pause it: after 22 days it costs USD 43.95 per sale, more than most of your similar ads, and it was weak from the start. Early read: small comparison group (6 similar ads).
    confidence: Early read (small comparison group: only 6 similar ads)
    - objective not in the data: judged as sales
    - payback measured by cost per sale and return on ad spend
    - payback: cpa bottom quartile, roas bottom quartile
    - compared with format: static (6 comparable ads); format / ad_type has 2 comparable ads, under 5
    - trend over first vs last 6 delivery days: ctr -6%, frequency +4%, hook rate n/a (fatigue needs ctr down 8%+ and frequency up 8%+ or hook down 8%+)
    - payback is bottom quartile on every measure, in its group and account-wide within its objective, and was bottom in the first 6 delivery days too
    - it misses your target: cpa: it costs USD 43.95 per sale, target USD 40.00
    ! check first: rule out tracking, site or audience problems first; only fatigue and never-worked are creative decisions
120000000030  [ugc-video]  age 3 d, Too early (learning)  (spend USD 670.39)
    Too early to judge: it is 3 days old, under the 5-day learning window.
    confidence: Can't judge yet (still learning)
    - learning: 3 days old, under the 5-day learning window
    - no other verdict until it has delivered longer
```
