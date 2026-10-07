# Data inputs

Three modes. Detect which you are in, say so, and never claim more than the mode supports.

## 1. Meta ads connector

Meta provides an official ads connector (MCP server) at `https://mcp.facebook.com/ads`, connected with an OAuth sign-in from the agent. Availability varies by account and may still be rolling out. If it reports that ads MCP is not enabled for the account, use mode 2.

Before relying on it:

1. List the connector's tools. Note which ones read reports, creatives and videos. Do not call tools that create or change ads unless the user asks for that specific action.
2. Use its field-discovery tool if it has one, or run one small ad-level report for a single day, and look at which fields come back.
3. Check each field the task needs: impressions, spend, reach, frequency, 3-second plays, ThruPlays, link clicks, purchases and purchase value, adds to cart, ad creation date, and daily rows. The connector's documentation does not say whether every video field is exposed. Check in your session and fall back to a CSV for whatever is absent.

In API rows, 3-second plays sit in the `actions` list as the `video_view` entry, ThruPlays in `video_thruplay_watched_actions`, purchases in `actions` as `purchase` with its value in `action_values`. Request daily rows (one row per ad per day) for fatigue work. Pass the attribution window explicitly. Meta removed the 7-day and 28-day view windows in January 2026, so do not request them.

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
| Grade ads against the account's baseline | if fields present | yes | no |
| Fatigue trend | needs daily rows | needs daily rows | no |
| Ad age | creation date, or first delivery day | first delivery day in the export | no |
| Brief and ideate | yes, from evidence | yes, from evidence | yes, labelled |
