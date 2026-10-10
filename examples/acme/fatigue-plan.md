# Acme fatigue-planner output

Generated, not hand-written, on the fictional Acme Outdoor Co. fixture (synthetic data, not a real account). Capacity (two refreshes a week) and the start date are illustrative inputs.

`python3 -I skills/fatigue-planner/scripts/fatigue_plan.py examples/acme/ads_daily.csv --capacity 2 --start 2026-03-31`

```text
1 ad is fading, 8 are on course to fade within 6 weeks;
at 2 refreshes a week the queue clears by 2026-05-04 (8 late).
Fading (1):
  durability-test (ugc-video): running before the window began: compared with its own start, not the account's delivery-day band; already at or below the floor
On course to fade (8):
  packing-list (carousel): running before the window began: compared with its own start, not the account's delivery-day band; about 1 day (range 1 to 1, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  behind-the-seams (founder-video): running before the window began: compared with its own start, not the account's delivery-day band; about 2 days (range 2 to 3, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  sale-countdown (static): about 23 days (range 15 to 59, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  gift-guide (carousel): about 7 days (range 5 to 20, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  partnership-trail (partnership): about 9 days (range 5 to 81, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  sale-bundle (carousel): already at or below the floor
  sale-last-chance (ugc-video): below the account's band for its age for most of its last days (5 of 6); already at or below the floor
  partnership-camp (partnership): about 9 days (range 6 to 16, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
Steady (20):
  problem-first (ugc-video): running before the window began: compared with its own start, not the account's delivery-day band; not falling
  social-proof (static): running before the window began: compared with its own start, not the account's delivery-day band; not clearly falling: the line's range includes no fall; about 10 days (range 4 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  founder-story (founder-video): running before the window began: compared with its own start, not the account's delivery-day band; not falling
  partnership-haul (partnership): running before the window began: compared with its own start, not the account's delivery-day band; already at or below the floor
  weather-ready (ugc-video): running before the window began: compared with its own start, not the account's delivery-day band; not clearly falling: the line's range includes no fall; about 162 days (range 48 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  comparison (static): running before the window began: compared with its own start, not the account's delivery-day band; not clearly falling: the line's range includes no fall; about 20 days (range 10 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  guarantee (static): running before the window began: compared with its own start, not the account's delivery-day band; already at or below the floor
  before-after (ugc-video): running before the window began: compared with its own start, not the account's delivery-day band; not falling
  staff-picks (carousel): running before the window began: compared with its own start, not the account's delivery-day band; not falling
  trail-diary (partnership): running before the window began: compared with its own start, not the account's delivery-day band; not clearly falling: the line's range includes no fall; about 213 days (range 23 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  problem-cold-feet (ugc-video): running before the window began: compared with its own start, not the account's delivery-day band; not clearly falling: the line's range includes no fall; about 62 days (range 17 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  social-proof-reviews (static): running before the window began: compared with its own start, not the account's delivery-day band; not clearly falling: the line's range includes no fall; about 24 days (range 10 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  fix-it-yourself (ugc-video): running before the window began: compared with its own start, not the account's delivery-day band; not falling
  new-drop (carousel): not clearly falling: the line's range includes no fall; already at or below the floor
  sale-percent-off (static): below the account's band for its age for most of its last days (6 of 6); already at or below the floor
  gift-guide-two (carousel): not falling
  new-drop-two (carousel): not falling
  unboxing (ugc-video): not clearly falling: the line's range includes no fall; about 25 days (range 12 to no end in sight, from a straight line through its last 9 delivery days; a real ad may not fade in a straight line)
  founder-note (founder-video): below the account's band for its age for most of its last days (6 of 6); not clearly falling: the line's range includes no fall; already at or below the floor
  new-drop-three (static): not falling
Too little history (1):
  new-drop-four (ugc-video): 4 delivery days, needs 9

Refresh calendar:
Week of 2026-03-31: refresh durability-test (ugc-video, fading, due now); refresh sale-bundle (carousel, on course, due now, late)
Week of 2026-04-07: refresh sale-last-chance (ugc-video, on course, due now, late); refresh packing-list (carousel, on course, due now, late)
Week of 2026-04-14: refresh behind-the-seams (founder-video, on course, due now, late); refresh gift-guide (carousel, on course, due now, late)
Week of 2026-04-21: refresh partnership-trail (partnership, on course, due 2026-04-01, late); refresh partnership-camp (partnership, on course, due 2026-04-01, late)
Week of 2026-04-28: refresh sale-countdown (static, on course, due 2026-04-15, late)
Week of 2026-05-05: nothing queued
```
