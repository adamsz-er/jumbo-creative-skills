# Data inputs

Three modes. Detect which you are in, say so, and never claim more than the mode supports.

## 1. Meta ads connector

Meta provides an official ads connector (MCP server) at `https://mcp.facebook.com/ads`, connected with an OAuth sign-in from the agent. Availability varies by account and may still be rolling out. If it reports that ads MCP is not enabled for the account, use mode 2.

What follows about the connector is not in Meta's documentation as of this writing and may change: check each point in your own session before relying on it.

Follow these steps in order:

1. **Read-only calls only.** The connector exposes tools that change things (for example activating or updating an ad). Never call one. These skills read and advise.
2. **Call the field-catalogue tool with no arguments first** and use the field names it returns, not names you remember or the ones below. Field names on this connector have changed before. When it rejects a field, it still returns every row, drops that field and says so only in the response's `additional_info` ("Unsupported fields: ... Supported fields at this level are: ..."). The adapter prints that note; read it.
3. **List every ad that delivered in the window, archived ones included.** The default ad listing leaves out ads that are archived now but spent inside the window, and without them the pull will not reconcile. List ads with impressions in the window, then list again filtered on `effective_status` ARCHIVED and DELETED (that listing is long and paginated, so keep only rows with delivery). Save both listings and write every ad id to `ids.txt`.
4. **Pull ad-level daily rows** (time increment of 1 day) for the window, by id in batches, asking for (names as the catalogue spells them):
   - always: spend (`amount_spent`), `impressions`, `reach`, `link_click`, `clicks`, the ad `id`, `name`, `created_time`, `objective` and `campaign_name`
   - sales: `omni_purchase`, `omni_purchase_values`, `omni_add_to_cart`
   - leads: `lead` or `onsite_conversion_lead_grouped` (without one, every lead ad is "can't judge")
   - video: `video_thruplay_watched_actions`, and the cost per 3-second view (`cost_per_video_view` on the current connector; it was `cost_per_action_type:video_view`)
   The scripts do not use frequency or the video percentile fields, so leave them out.
   **Batch size:** set `limit` explicitly (the default caps a batch silently), and keep ads per batch at or under `limit` ÷ days in the window. A batch of about 25 to 30 ads over 30 days stays under a 1,000-row limit and comes back large enough to be saved to a file.
5. **Save every response to a JSON file as it comes back.** Never transcribe rows by hand, and never retype numbers into a file. Save the response exactly as returned: the adapter reads the connector's own wrapper (rows as a JSON string under `ad_entities`). If your client shows a small response inline instead of saving it, re-request it in a form that is saved (a larger batch, or more fields) rather than copying it out; never retype it.
6. **Pull the account-level totals for the same window** (spend and impressions), also saved.
7. **Run the adapter** and give it those totals and the ids:

   ```
   python3 -I scripts/from_mcp.py page1.json page2.json -o ads.csv --expect-spend <total> --expect-impressions <total> --expect-ads ids.txt
   ```

   It merges the files, keeps one row per ad and day, maps the connector's field names, fills `market` from the ad names, and prints the rows, ads, date range and totals. It also prints any note the connector sent and every expected field that no row carries. A short pull prints a `WARNING` line first and exits 3. The connector can stop a long pull partway with no cursor and no warning, and can cap a batch of ids at its row limit without saying so. On a shortfall, check step 3 (archived ads) first, then re-fetch the missing ads in small batches by id, save those responses, and run the adapter again until the totals reconcile or you can explain the residual. `--tolerance` is the percent of the expected total a pull may fall short (an arbitrary default of 0.5: set it from how closely your own totals should reconcile).
8. **Pass `ads.csv` to the analysis scripts**, with the same `--where` (for example `--where market=US`) to each when the review covers one market.

A large batch may answer "result (N characters) exceeds maximum allowed tokens. Output has been saved to …": that is expected, and the saved file is the data. Pass it to the adapter as it is.

Field names the adapter maps: `link_click` is link clicks, `omni_purchase` is purchases, `omni_purchase_values` is purchase value, `omni_add_to_cart` is adds to cart, `lead` and `onsite_conversion_lead_grouped` are leads, `date_start` is the day, `id` and `name` are the ad id and name (only on ad-level rows), and amounts may arrive as `{"value": ..., "unit": ...}`; when every spend amount states the same unit, the CSV's spend header becomes `Amount spent (<CODE>)` and the review needs no `--currency`.

**3-second plays are not returned per ad by this connector** (not in Meta's documentation as of this writing and may change: check in your own session). `3_second_video_plays` exists only at ad set level and above. The adapter derives per-ad plays as spend divided by the cost per 3-second view and labels them: `video_views_3s_source` reads "derived: spend / cost per 3-second view", and every script that prints hook rate shows "(derived)". Say so whenever you quote a hook rate from this mode.

The connector rounds that cost to cents, and a view that costs a few cents can then be tens of percent out. So the adapter judges the error from the decimals shown and refuses to derive when it could exceed 2% (an arbitrary default: `DERIVE_MAX_ERROR` in `creative_metrics.py`). A refused row reads "not derived: cost per 3-second view is rounded too coarsely (up to X% out)", and an ad with any refused day has no plays at all rather than a sum of some days. Hook rate and hold rate are then n/a, and the report says why. To get them, use an Ads Manager export with the 3-second video plays column (mode 2) for those metrics. You can check the rounding yourself at ad set level, where both `3_second_video_plays` and the cost are returned.

Hold rate uses ThruPlays, which are returned per ad, but it needs 3-second plays as its denominator, so it is n/a whenever they are.

Ad age uses `created_time` when the rows carry it, and the scripts say so ("age basis"). Without it, age is the first delivery day inside the window and older ads are understated.

Pass the attribution window explicitly. Meta removed the 7-day and 28-day view windows in January 2026, so do not request them. The connector does not return the attribution setting it used, so the report header reads it only from what you pass with `--attribution`; if you did not set one, say "account default (not stated by the connector)".

**Reach and frequency for one scope.** Reach does not add up across ads or days. The report's reach and frequency tiles need an account-level figure for the same scope as the rest of the page. For the whole account, pull them at account level. For one market, pull them at campaign level only when each campaign serves exactly one market, and only if the connector returns campaign reach for the window. Otherwise leave the tiles n/a: a whole-account figure on a one-market page is the wrong number. The `--account` file holds `reach` and either `frequency` or `impressions` (frequency is then impressions / reach, shown as computed); add `"scope"` with the same words as the report's scope when the figures are filtered to it, otherwise a scoped report captions the tiles as account-wide.

**Ad previews.** The connector's preview tool returns preview links and one-time screenshot tokens for Meta's own app, not an image file, and the screenshot tool is not for model use. Creative thumbnails are 64×64 crops. So in connector mode the report's ad cards usually show labelled placeholders. To get images, ask the user to save screenshots of the ads they care about as `<ad_id>.png` in a folder and pass it with `--previews`.

**The prior period.** Change against the previous period on every tile needs a second pull of the same size (the same batching and reconcile work), so it roughly doubles the connector work. Say so before you start, and skip it unless the user wants the comparison. A cheaper prior is enough for the tiles: one ad-level request for the previous window with no time increment (one totals row per ad), saved and run through the adapter like any pull. The tiles then show the change; the sparklines still come from the current window.

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
| Hook and hold rate | only when the cost per 3-second view is precise enough | yes | no |
| Ad age | `created_time`, or first delivery day | first delivery day in the export | no |
| Brief and ideate | yes, from evidence | yes, from evidence | yes, labelled |
