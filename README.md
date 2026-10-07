# jumbo-creative-skills

A package of agent skills that teach any brand to analyse and make Meta (Facebook and Instagram) ad creative. The skills grade ads against your own account's baseline, never against generic benchmarks, and they work for any brand: the brand is something you tell the agent, not something baked in. Data comes from Meta's ads connector, an Ads Manager CSV export, or nothing at all.

## Quick start

1. **Install** the skills (table below).
2. **Connect your ad data**: add Meta's Ads MCP, or export a CSV from Ads Manager ([how](#connect-your-ad-data)).
3. **Ask** your agent: "grade my ads".

## Install

| Where | How |
|---|---|
| Claude Code | `/plugin marketplace add adamsz-er/jumbo-creative-skills` then `/plugin install jumbo-creative@jumbo-creative-skills`. From a shell: `claude plugin marketplace add adamsz-er/jumbo-creative-skills` then `claude plugin install jumbo-creative@jumbo-creative-skills` |
| Any agent that supports Agent Skills (Claude Code, Codex, Cursor, Gemini CLI, Copilot and others) | `npx skills add adamsz-er/jumbo-creative-skills`. Add `--skill <name>` to pick one skill, `-a <agent>` to target one agent |
| Claude desktop / claude.ai | Download `<skill>.zip` from the [latest Release](https://github.com/adamsz-er/jumbo-creative-skills/releases/latest), then Customize > Skills > Upload. Needs code execution enabled. Releases appear once the first version is tagged; until then build the zips yourself with `python3 tools/build_zips.py` (they land in `dist/`) |

`jumbo-creative-skills-all.zip` on the Release holds every skill in one file.

## Connect your ad data

The skills read your own numbers. Pick whichever you have:

1. **Meta's official Ads MCP** (recommended). Add the connector at `https://mcp.facebook.com/ads` in your agent and sign in with Meta through OAuth. In Claude Code: `claude mcp add --transport http meta-ads https://mcp.facebook.com/ads`, then authenticate from `/mcp`. It may not be enabled on every ad account yet.
2. **A CSV export from Ads Manager** as the fallback. Follow [the export recipe](skills/creative-context/references/export-recipe.md) for the exact columns.
3. **Nothing.** The skills still work for ideation, and label every grade "no performance data".

Try it on made-up data first: `python3 -I skills/creative-context/scripts/creative_metrics.py examples/acme/ads_daily.csv` prints a per-ad table for the fictional "Acme Outdoor Co.".

## What each skill does

| Skill | What it does |
|---|---|
| `creative-context` | Builds the brand profile, detects the data mode, fixes metric definitions, ad types and naming fields |
| `creative-ideation` | Generates concepts across themes, formats, ad types and personas, aimed at the gaps in your mix |
| `creative-grader` | Grades each ad against your own account's median and quartiles and names the first broken funnel step |
| `keep-or-kill` | Keep, kill, iterate or scale call for every ad, with age, learning flag and fatigue trend |
| `creative-brief` | Writes a production-ready brief from evidence: what won, what faded, where the gaps are |
| `persona-builder` | Builds personas by emotional starting state and awareness stage, mapped to concepts and hooks |
| `hook-writer` | Writes video and text hooks, and one-change variants of a winning hook |
| `creative-mix` | Maps your portfolio: concept by format grid, ad types, spend concentration, gaps worth testing |
| `ad-transcript` | Breaks a video script into beats, scores its structure, flags claims, and rewrites it |
| `colour-grade` | Extracts the palette of ad images and gives colour and grading direction |
| `creative-report` | Turns the analyse outputs into one shareable HTML report |

## Try the analyse skills

Each prints its basis first, then the result. On the made-up Acme data (outputs are saved in `examples/acme/`):

- `creative-grader`: "Grade my ads and tell me what to fix first." Runs `python3 -I skills/creative-grader/scripts/grade.py examples/acme/ads_daily.csv` ([output](examples/acme/grade.md)).
- `keep-or-kill`: "Which ads should I pause, refresh or scale this week?" Runs `python3 -I skills/keep-or-kill/scripts/verdicts.py examples/acme/ads_daily.csv` ([output](examples/acme/verdicts.md)).
- `creative-mix`: "What creative am I missing, and am I leaning too hard on one thing?" Runs `python3 -I skills/creative-mix/scripts/mix.py examples/acme/ads_daily.csv` ([output](examples/acme/mix.md)).
- `ad-transcript`: "Break this script into beats and tighten it." Runs `python3 -I skills/ad-transcript/scripts/beats.py examples/acme/transcript.txt` on an illustrative script ([output](examples/acme/transcript-analysis.md)).
- `colour-grade`: "What does the palette of these ads say, and do they all look alike?" Runs `python3 -I skills/colour-grade/scripts/palette.py examples/acme/swatch.png` ([output](examples/acme/palette.md)).
- `creative-report`: "Put this review in a report I can share." Builds one HTML file from the three analyses. See an example report: [examples/acme/report.html](examples/acme/report.html) (download it and open it in a browser).

With a Meta ads connector, the agent saves the rows it pulls to a JSON file and passes that file to the same scripts.

## Try the make skills

They work with no data and get sharper with a brand profile or the analyse outputs. On the made-up Acme data (worked examples in `examples/acme/`):

- `creative-ideation`: "Give me nine ad concepts that fill the gaps in my mix." ([output](examples/acme/ideas.md))
- `hook-writer`: "Write hooks for my rain shell, and variants of the ad that is fatiguing." ([output](examples/acme/hooks.md))
- `persona-builder`: "Who am I really talking to? Build me personas for this brand." ([output](examples/acme/personas.md))
- `creative-brief`: "Write a production brief for the boot test with a new opening." Runs `python3 -I skills/creative-brief/scripts/evidence.py examples/acme/ads_daily.csv` for the evidence block ([output](examples/acme/brief.md)).

## Example output

Everything below runs on the made-up Acme data: [grade](examples/acme/grade.md), [verdicts](examples/acme/verdicts.md), [mix](examples/acme/mix.md), [brief](examples/acme/brief.md) and the shareable [report](examples/acme/report.html) (download it and open it in a browser).

## Privacy

The skills run inside your agent. The bundled scripts use only the Python standard library and make no network calls, so your data leaves your machine only through what your agent and the Meta MCP already do. `colour-grade` reads other image formats too if you have Pillow installed, and the report is one local HTML file whose only outside requests are to Google Fonts (the stylesheet and font files).

## License

MIT. See [LICENSE](LICENSE).
