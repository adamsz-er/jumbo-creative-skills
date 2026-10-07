#!/usr/bin/env python3
"""Generate the synthetic Ads Manager export for the fictional brand Acme Outdoor Co.

Deterministic: the same --seed always writes the same file. The data is invented;
it exists so the skills and tests have an export to run against.
Usage: python3 tools/make_fixture.py --seed 7 --out examples/acme/ads_daily.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import random
import sys
from pathlib import Path

START = dt.date(2026, 3, 1)
DAYS = 30
HEADERS = [
    "Day", "Ad name", "Ad ID", "Delivery", "Amount spent (USD)", "Impressions", "Reach",
    "Frequency", "CPM (cost per 1,000 impressions)", "Link clicks", "Clicks (all)",
    "CTR (link click-through rate)", "CTR (all)", "3-second video plays", "ThruPlays",
    "Video plays at 25%", "Video plays at 50%", "Video plays at 75%", "Video plays at 95%",
    "Video plays at 100%", "Video average play time", "Adds to cart", "Purchases",
    "Purchases conversion value",
]
VIDEO_FORMATS = {"ugc-video": 0.27, "founder-video": 0.21, "partnership": 0.26}

# concept, format, creator, ad type, product, tone, first delivery day (0 = start of window)
ADS = [
    ("durability-test", "ugc-video", "creator-01", "bau", "trail-boot", "lofi", 0),
    ("problem-first", "ugc-video", "creator-02", "bau", "rain-shell", "lofi", 0),
    ("social-proof", "static", "house", "bau", "day-pack", "polished", 0),
    ("sale-countdown", "static", "house", "promo", "tent-2p", "polished", 8),
    ("gift-guide", "carousel", "house", "promo", "headlamp", "polished", 8),
    ("founder-story", "founder-video", "founder", "bau", "trail-boot", "lofi", 0),
    ("new-drop", "carousel", "house", "launch", "sleeping-bag", "polished", 5),
    ("partnership-haul", "partnership", "creator-03", "bau", "day-pack", "lofi", 0),
    ("packing-list", "carousel", "house", "bau", "camp-stove", "polished", 0),
    ("weather-ready", "ugc-video", "creator-04", "bau", "rain-shell", "lofi", 0),
    ("behind-the-seams", "founder-video", "founder", "bau", "tent-2p", "lofi", 0),
    ("sale-percent-off", "static", "house", "promo", "sleeping-bag", "polished", 8),
    ("new-drop-two", "carousel", "house", "launch", "water-bottle", "polished", 12),
    ("comparison", "static", "house", "bau", "headlamp", "polished", 0),
    ("unboxing", "ugc-video", "creator-05", "launch", "camp-stove", "lofi", 12),
    ("partnership-trail", "partnership", "creator-06", "promo", "trail-boot", "lofi", 8),
    ("guarantee", "static", "house", "bau", "water-bottle", "polished", 0),
    ("before-after", "ugc-video", "creator-07", "bau", "day-pack", "lofi", 0),
    ("sale-last-chance", "ugc-video", "creator-08", "promo", "rain-shell", "lofi", 15),
    ("founder-note", "founder-video", "founder", "launch", "headlamp", "lofi", 15),
    ("staff-picks", "carousel", "house", "bau", "trail-boot", "polished", 0),
    ("trail-diary", "partnership", "creator-09", "bau", "tent-2p", "lofi", 0),
    ("problem-cold-feet", "ugc-video", "creator-10", "bau", "sleeping-bag", "lofi", 0),
    ("sale-bundle", "carousel", "house", "promo", "camp-stove", "polished", 8),
    ("new-drop-three", "static", "house", "launch", "day-pack", "polished", 18),
    ("social-proof-reviews", "static", "house", "bau", "rain-shell", "polished", 0),
    ("partnership-camp", "partnership", "creator-11", "launch", "water-bottle", "lofi", 18),
    ("fix-it-yourself", "ugc-video", "creator-12", "bau", "camp-stove", "lofi", 0),
    ("gift-guide-two", "carousel", "house", "promo", "day-pack", "polished", 10),
    ("new-drop-four", "ugc-video", "creator-13", "launch", "headlamp", "lofi", 26),
]


def ad_id(index):
    return "1200000%05d" % (index + 1)


# The four ads the tests and the CLI demo rely on (index into ADS).
SPECIAL = {
    "fatiguing": ad_id(0),
    "no_thruplay": ad_id(10),
    "never_worked": ad_id(16),
    "young": ad_id(29),
}


def ad_name(spec, index):
    concept, fmt, creator, kind, product, tone, start = spec
    launch = START + dt.timedelta(days=start)
    return " | ".join([concept, fmt, creator, kind, product, tone, launch.isoformat()])


def rows_for(index, spec, rng):
    concept, fmt, creator, kind, product, tone, start = spec
    is_video = fmt in VIDEO_FORMATS
    base_impressions = rng.uniform(4000, 22000)
    base_cpm = rng.uniform(9, 17)
    base_ctr = rng.uniform(0.9, 1.9) / 100
    base_hold = rng.uniform(0.27, 0.40)
    base_cvr = rng.uniform(0.018, 0.04)
    aov = rng.uniform(70, 160)
    link_share = rng.uniform(0.68, 0.76)
    base_frequency = rng.uniform(1.15, 1.35)
    hook = VIDEO_FORMATS.get(fmt, 0) * rng.uniform(0.85, 1.15)
    fatiguing = ad_id(index) == SPECIAL["fatiguing"]
    never_worked = ad_id(index) == SPECIAL["never_worked"]
    no_thruplay = ad_id(index) == SPECIAL["no_thruplay"]
    if fatiguing:
        base_impressions, base_ctr, hook = 24000, 0.020, 0.31
    if never_worked:
        base_ctr, base_cvr, base_impressions = 0.0025, 0.004, 9000

    out = []
    for day in range(start, DAYS):
        progress = (day - start) / max(1, DAYS - 1 - start)
        noise = lambda sd: max(0.2, rng.gauss(1.0, sd))
        ctr_mult = 1 - 0.55 * progress if fatiguing else 1.0
        hook_mult = 1 - 0.35 * progress if fatiguing else 1.0
        cpm_mult = 1 + 0.45 * progress if fatiguing else 1.0
        frequency = base_frequency + (2.1 * progress if fatiguing else 0.004 * (day - start)) + rng.uniform(-0.03, 0.03)
        impressions = int(base_impressions * noise(0.12))
        spend = impressions * base_cpm * cpm_mult * noise(0.05) / 1000
        reach = max(1, int(impressions / frequency))
        link_clicks = int(impressions * base_ctr * ctr_mult * noise(0.10))
        clicks = int(link_clicks / link_share * noise(0.03))
        carts = int(link_clicks * rng.uniform(0.08, 0.12))
        purchases = int(round(link_clicks * base_cvr * noise(0.25)))
        value = purchases * aov * noise(0.12)
        video = [""] * 8
        if is_video:
            views3 = int(impressions * hook * hook_mult * noise(0.06))
            thru = "" if no_thruplay else int(views3 * base_hold * noise(0.06))
            video = [views3, thru, int(views3 * 0.70), int(views3 * 0.50), int(views3 * 0.36),
                     int(views3 * 0.22), int(views3 * 0.20), round(rng.uniform(4.0, 9.0), 1)]
        out.append([
            (START + dt.timedelta(days=day)).isoformat(), ad_name(spec, index), ad_id(index), "active",
            "%.2f" % spend, impressions, reach, "%.2f" % (impressions / reach),
            "%.2f" % (spend / impressions * 1000), link_clicks, clicks,
            "%.2f" % (link_clicks / impressions * 100), "%.2f" % (clicks / impressions * 100),
            *video, carts, purchases, "%.2f" % value,
        ])
    return out


def build(seed):
    rng = random.Random(seed)
    rows = []
    for index, spec in enumerate(ADS):
        rows.extend(rows_for(index, spec, rng))
    rows.sort(key=lambda r: (r[0], r[2]))
    return rows


def write(path, seed):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADERS)
        writer.writerows(build(seed))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="examples/acme/ads_daily.csv")
    args = parser.parse_args(argv)
    write(args.out, args.seed)
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
