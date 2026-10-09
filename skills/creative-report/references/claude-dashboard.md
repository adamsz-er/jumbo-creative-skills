# Publish the report as a Claude dashboard

Where your Claude offers the **Dashboard** artifact type, the creative report can also be a native Claude dashboard: the same numbers, laid out in the dashboard's own style, where a reader can click any number to see which data it came from. The HTML file stays the version to share outside Claude, to print, or to open where dashboards are not offered (free plans, other agents). Ad previews, video and the open-ad view are only in the HTML version.

Every number is computed by `report.py`, by the same code that builds the HTML. The dashboard page only formats and draws it; it never works a figure out itself.

## Is the Dashboard type offered?

List the artifact types your artifact tool can start from. If one is called "Dashboard", go on. If not, build the HTML report as usual and tell the user why: this Claude does not offer dashboards, so the report is the HTML file.

## 1. Build the bundle and check it

Add `--claude-dashboard <folder>` to the `report.py` command you already run. It writes the HTML exactly as before and, beside it, the bundle:

```
python3 -I scripts/report.py ads.csv --verdicts verdicts.json --grade grade.json --mix mix.json \
    --profile creative-profile.md -o report.html --claude-dashboard dashboard/
python3 -I scripts/report.py --check-dashboard dashboard/
```

The check must print `OK`. Fix anything it names by fixing the inputs and building again; never edit a bundle file by hand.

The bundle holds:

- `manifest.json`: the dashboard title, each dataset's id, title, one-line description and file, the page files, and the store documents.
- `datasets/<id>.json`: one JSON array of rows per dataset (the table below).
- `files/`: the page (`index.html`, `dashboard.css`, `dashboard.js`).
- `store/`: the title and each page file as a ready store document (`{"title": ...}` or `{"text": ...}`), so you can write them by file path instead of retyping them.

## 2. Create one dashboard

With your artifact tool, create one artifact from the Dashboard type: pass the type's link, the manifest's `title` as the title, and ask it to open after the first write (`auto_open: "after_first_write"`). Note the new dashboard's link. Create it once; a second create makes a second dashboard.

## 3. Upload each dataset file

For each entry in the manifest's `datasets`, upload its file to the new dashboard as an asset (a publish to the dashboard's link with `file_path` set to the dataset file and `asset: true`; one file per call). Keep the `url` each upload returns, exactly as given (it reads like `/_blob/<id>`).

## 4. Write everything in one batch

One database batch write (the `ArtifactData` tool's `batch` action) on the dashboard's link, with these writes, all `set`:

1. `dash/meta`: `file_path` the manifest's store file for `dash/meta`.
2. For each dataset, `datasets/<id>` with `data`:
   `{"title": <manifest title>, "description": <manifest description>, "source": {"kind": "file", "url": <the upload's url>, "name": "<id>.json"}, "updated": {"at": <now, ISO time>, "by": "creative-report"}}`.
3. For each page file, `files/<name>`: `file_path` the manifest's store file for that document.

That is under 20 writes, within the batch limit of 50. A refused write means you cannot edit this dashboard: say so and stop.

## 5. Hand it over

Tell the user, in a line each:

- The dashboard is open, and each number shows its source when clicked.
- Anyone who can open the dashboard can read the attached data files.
- The HTML file is the version to share outside Claude, to print, and the one with ad previews and video.
- What the report does not cover (missing fields, unclassified names, ads too young, the scope), as with the HTML.

Do not open, screenshot or browse the dashboard to check it: the dashboard type asks that it is not rendered to verify it, and the bundle check in step 1 is the check.

## Refreshing it

Build the bundle again from the new data and check it. Upload each dataset file again, then update each `datasets/<id>` with the new `url`, `name` and `updated`. Write a page file again only when it changed.

## The datasets

`references/dashboard-schema.json` is the contract (JSON Schema, draft 2020-12); `--check-dashboard` validates every dataset against it and every mark on the page against its columns. It also refuses a manifest that lacks a schema dataset or a page file, any number in the page's text, script that reaches the network, storage, cookies or `eval`, styles outside the page's own `.cr` classes, and anything loaded from outside the bundle that is not a `data:` URL. Its `x-version` is repeated in the header dataset as the "Schema version" fact, so a dashboard built from an older bundle can be told apart.

- Metric columns use the metric ids in `creative-context/references/metrics.md` (`roas`, `cpa`, `ctr`, `cpm`, `hook_rate`, `hold_rate`, `spend`, `conversion_value`, ...).
- A value that could not be read is `null` and its `<column>_note` sibling says why, as `n/a (missing <field>)` or another plain reason. A value is null exactly when its note is set: a missing value is never 0 and never a dropped row.
- Units: `currency` is the report currency (the header's Currency fact); `percent` is already multiplied by 100; `ratio` is a multiple (ROAS 3.2 is 3.2x); `count`, `days`, `date` (ISO); `per-row` takes the unit the row names.
- An empty panel has its reason in `sections`: its `why` and `how` are the HTML's own empty state.

| Dataset | Key | Columns |
|---|---|---|
| `header` | `fact` | `fact` (string); `value` (string); `tone` (string, or null) |
| `sections` | `panel` | `tab` (string); `panel` (string); `heading` (string); `state` (string); `why` (string, or null); `how` (string, or null) |
| `kpis` | `metric` | `metric` (string); `name` (string); `unit` (string); `value` (number, per-row, null with `value_note`); `shown` (string); `detail` (string, or null); `change_pct` (number, percent, null with `change_pct_note`); `change_tone` (string, or null); `against` (string) |
| `daily` | `day,metric` | `day` (string, date); `metric` (string); `name` (string); `kind` (string); `unit` (string); `value` (number, per-row, null with `value_note`); `average` (number, per-row, null with `average_note`) |
| `pareto` | `ad_id` | `rank` (integer, count); `ad_id` (string); `label` (string); `format` (string); `spend` (number, currency); `conversion_value` (number, currency, null with `conversion_value_note`); `cum_spend_pct` (number, percent); `cum_basis_pct` (number, percent); `in_head` (boolean) |
| `pareto-cut` | one row | `ads` (integer, count); `cut` (integer, count); `ads_pct` (number, percent); `head_share_pct` (number, percent); `basis` (string); `setting_pct` (number, percent); `sentence` (string); `coverage` (string, or null); `top_n` (integer, count); `concentration_pct` (number, percent, null with `concentration_pct_note`); `tail_ads` (integer, count); `tail_spend` (number, currency); `tail_conversion_value` (number, currency, null with `tail_conversion_value_note`) |
| `verdict-board` | `verdict_class` | `verdict_class` (string); `verdict` (string); `ads` (integer, count); `spend_at_stake` (number, currency, null with `spend_at_stake_note`); `check` (string, or null) |
| `verdicts` | `ad_id` | `ad_id` (string); `label` (string); `ad_name` (string, or null); `format` (string); `verdict` (string, null with `verdict_note`); `verdict_class` (string, or null); `confidence` (string, null with `confidence_note`); `spend` (number, currency, null with `spend_note`); `spend_at_stake` (number, currency, null with `spend_at_stake_note`); `age_days` (number, days, null with `age_days_note`); `fatiguing` (boolean, null with `fatiguing_note`); `next_step` (string, or null); `check` (string, or null); `roas` (number, ratio, null with `roas_note`); `cpa` (number, currency, null with `cpa_note`); `ctr` (number, percent, null with `ctr_note`); `hook_rate` (number, percent, null with `hook_rate_note`); `thumb` (string, or null, optional) |
| `formats` | `format` | `format` (string); `name` (string); `ads` (integer, count); `spend_share` (number, percent, null with `spend_share_note`); `ctr` (number, percent, null with `ctr_note`); `ctr_grade` (string, or null); `cpm` (number, currency, null with `cpm_note`); `cpm_grade` (string, or null); `cpa` (number, currency, null with `cpa_note`); `cpa_grade` (string, or null); `roas` (number, ratio, null with `roas_note`); `roas_grade` (string, or null); `hook_rate` (number, percent, null with `hook_rate_note`); `hook_rate_grade` (string, or null); `hold_rate` (number, percent, null with `hold_rate_note`); `hold_rate_grade` (string, or null) |
| `white-space` | `concept,format` | `concept` (string); `format` (string); `ads` (integer, count); `spend` (number, currency); `gap` (integer, count, or null) |
| `gaps` | `number` | `number` (integer, count); `label` (string); `why` (string) |
| `briefing` | `number` | `number` (integer, count); `kind` (string); `title` (string); `details` (string); `references` (string); `judged` (string); `prompt` (string, null with `prompt_note`) |
| `notes` | `id` | `id` (integer, count); `section` (string); `text` (string) |
