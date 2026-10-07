# jumbo-creative-skills

A package of agent skills that teach any brand to analyse and make Meta (Facebook and Instagram) ad creative. The skills grade ads against your own account's baseline, never against generic benchmarks, and they work for any brand: the brand is something you tell the agent, not something baked in. Data comes from Meta's ads connector, an Ads Manager CSV export, or nothing at all.

## Works with

Claude Code, Claude desktop / claude.ai, Codex, Cursor, Gemini CLI, and any agent that supports Agent Skills through `npx skills`.

## Install

| Where | How |
|---|---|
| Claude Code | `/plugin marketplace add adamsz-er/jumbo-creative-skills` then `/plugin install jumbo-creative@jumbo-creative-skills` |
| Any agent | `npx skills add adamsz-er/jumbo-creative-skills` |
| Claude desktop / claude.ai | download a skill zip from Releases, then Customize > Skills > Upload (coming soon) |

## Connect your ad data

The skills read your own numbers. Pick whichever you have:

1. **Meta's official Ads MCP** (recommended). Add the connector at `https://mcp.facebook.com/ads` in your agent and sign in with Meta through OAuth. It may not be enabled on every ad account yet.
2. **A CSV export from Ads Manager** as the fallback. Follow [the export recipe](skills/creative-context/references/export-recipe.md) for the exact columns.
3. **Nothing.** The skills still work for ideation, and label every grade "no performance data".

Try it on made-up data first: `python3 skills/creative-context/scripts/creative_metrics.py examples/acme/ads_daily.csv` prints a per-ad table for the fictional "Acme Outdoor Co.".

## Skills

| Skill | What it does | Status |
|---|---|---|
| `creative-context` | Builds the brand profile, detects the data mode, fixes metric definitions, ad types and naming fields | available |
| `creative-ideation` | Generates concepts from your brand profile and what has worked | coming soon |
| `creative-grading` | Grades each ad against your own account's median and quartiles | coming soon |
| `keep-or-kill` | Weekly keep, kill or iterate call for every ad | coming soon |
| `ad-fatigue` | Reads ad age and week-over-week trends to catch fatigue early | coming soon |
| `creative-brief` | Writes a brief from evidence: what won, what faded, where the gaps are | coming soon |
| `hook-analysis` | Breaks down openings and hook archetypes for video | coming soon |
| `persona-hooks` | Maps personas to hooks and angles | coming soon |
| `transcript-analysis` | Reads video transcripts for the claims and structure that perform | coming soon |
| `creative-coverage` | Finds empty cells in your concept by format grid | coming soon |
| `creative-report` | Turns a review into a shareable report | coming soon |

## Privacy

The skills never send your data anywhere. They run inside your agent, and the bundled script uses only the Python standard library.

## License

MIT. See [LICENSE](LICENSE).
