# AGENTS.md

This repo is a public package of Agent Skills for analysing and making Meta ad creative. Skills live in `skills/<name>/SKILL.md`, with `references/` and `scripts/` beside each. `shared/creative_metrics.py` is the one canonical metrics module. Each skill carries a synced copy in its own `scripts/` so it works after install on its own.

## Contributor rules

1. **No client data, ever.** No client, brand or person names, no figures from real ad accounts, no internal URLs, hostnames, keys, or quoted messages. Examples use the fictional "Acme Outdoor Co." with synthetic data.
2. **No private tooling.** Users do not have our internal systems. Data comes from a Meta ads MCP, an Ads Manager CSV export or screenshots, or nothing. Do not name internal tools or services anywhere in the repo.
3. **No benchmarks.** Never write "a good hook rate is X%". Judge an ad against the account's own median and quartiles over a trailing window, within the same format and funnel stage.
4. **Metric ids and formulas** are defined once, in `skills/creative-context/references/metrics.md` and implemented in `shared/creative_metrics.py`. A missing operand or a zero denominator is `n/a (missing <field>)`, never 0.

Frontmatter in `SKILL.md` uses spec keys only: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Keep the body under 500 lines.

## Tests

Standard library only:

```
python3 -m unittest discover -s tests -v
python3 tools/validate_skills.py
python3 tools/sync_shared.py --check     # run without --check to copy shared/ into the skills
```

After editing `shared/creative_metrics.py`, run `python3 tools/sync_shared.py`. The fixture is regenerated with `python3 tools/make_fixture.py --seed 7 --out examples/acme/ads_daily.csv`.
