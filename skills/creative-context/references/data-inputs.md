# Data inputs

Three modes. Detect which you are in, say so, and never claim more than the mode supports.

## 1. Meta ads connector

Meta provides an official ads connector (MCP server) at `https://mcp.facebook.com/ads`, connected with an OAuth sign-in from the agent. Availability varies by account and may still be rolling out. If it reports that ads MCP is not enabled for the account, use mode 2.

What follows about the connector is not in Meta's documentation as of this writing and may change: check each point in your own session before relying on it.

Follow these steps in order:

1. **Read-only calls only.** The connector exposes tools that change things (for example activating or updating an ad). Never call one. These skills read and advise.
2. **Call the field-catalogue tool with no arguments first** and use the field names it returns, not names you remember. It lists every insights field the account can request.
3. **Pull ad-level daily rows** (time increment of 1 day) for the window, asking for: spend, impressions, reach, frequency, `link_click`, clicks, `omni_purchase`, `omni_purchase_values`, `omni_add_to_cart`, `cost_per_action_type:video_view`, `video_thruplay_watched_actions`, the video percentile fields, and the ad id, ad name, `created_time`, objective and campaign name.
4. **Save every response to a JSON file as it comes back.** Never transcribe rows by hand, and never retype numbers into a file.
5. **Pull the account-level totals for the same window** (spend and impressions), also saved.
6. **Run the adapter** and give it those totals:

   ```
   python3 scripts/from_mcp.py page1.json page2.json -o ads.csv --expect-spend <total> --expect-impressions <total>
   ```

   It merges the files, keeps one row per ad and day, maps the connector's field names, and prints the rows, ads, date range and totals. A short pull prints a `WARNING` line first and exits 3. The connector can stop a long pull partway with no cursor and no warning, and can cap a batch of ids at its default row limit without saying so. On a shortfall, re-fetch the missing ads in small batches by id (pass `--expect-ads ids.txt`, one id per line, to name the ads with no rows), save those responses, and run the adapter again until the totals reconcile or you can explain the residual. `--tolerance` is the percent of the expected total a pull may fall short (an arbitrary default of 0.5: set it from how closely your own totals should reconcile).
7. **Pass `ads.csv` to the analysis scripts.**

Field names the adapter maps: `link_click` is link clicks, `omni_purchase` is purchases, `omni_purchase_values` is purchase value, `omni_add_to_cart` is adds to cart, `date_start` is the day, `id` and `name` are the ad id and name (only on ad-level rows), and amounts may arrive as `{"value": ..., "unit": ...}`.

**3-second plays are not returned per ad by this connector** (not in Meta's documentation as of this writing and may change: check in your own session). They are only available from the ad set level up. The adapter derives them as spend divided by `cost_per_action_type:video_view` and labels them: `video_views_3s_source` reads "derived: spend / cost per 3-second view", and every script that prints hook rate shows "(derived)". Say so whenever you quote a hook rate from this mode. Hold rate uses ThruPlays, which are returned per ad.

Ad age uses `created_time` when the rows carry it, and the scripts say so ("age basis"). Without it, age is the first delivery day inside the window and older ads are understated.

Pass the attribution window explicitly. Meta removed the 7-day and 28-day view windows in January 2026, so do not request them.

## 2. CSV export or screenshots

Ask the user for an Ads Manager export. `export-recipe.md` gives the exact steps and columns. Column names are matched case-insensitively and loosely, because Meta's labels change. The loader maps, for example:

| Canonical field | Typical export header |
|---|---|
| spend | Amount spent (currency) |
| impressions, reach, frequency | Impressions, Reach, Frequency |
| video_views_3s | 3-second video plays |
| video_thruplay | ThruPlays |
| link_clicks / clicks | Link clicks / Clicks (all) |
| conversions | Purchases (preferred), else Results |
| conversion_value | Purchases conversion value |
| add_to_carts | Adds to cart |
| ad_name, ad_id, date | Ad name, Ad ID, Day |

Unrecognised columns are kept and ignored. Columns Meta computes itself (CTR, CPM, frequency) are never trusted: every metric is recomputed from the counts so the definitions in `metrics.md` hold.

If the user can only send screenshots, ask for the same columns, read the numbers off the table, and compute by hand. Say that the numbers were read from an image and may contain transcription errors.

## 3. No data

Work in ideation-only mode. Label every grade, ranking and recommendation "no performance data". Do not infer which ad is working from how it looks.

## What changes by mode

| Task | Connector | CSV | None |
|---|---|---|---|
| Grade ads against the account's baseline | if fields present (hook rate derived) | yes | no |
| Fatigue trend | needs daily rows | needs daily rows | no |
| Ad age | `created_time`, or first delivery day | first delivery day in the export | no |
| Brief and ideate | yes, from evidence | yes, from evidence | yes, labelled |
