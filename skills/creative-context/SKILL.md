---
name: creative-context
description: Use first, before any other creative skill, when analysing or making Meta (Facebook and Instagram) ad creative. Builds or loads the brand profile, detects whether performance data comes from a Meta ads connector, a CSV export or nothing, and fixes the metric definitions, ad-type vocabulary and naming fields every later answer relies on. Also use when the user asks how to export creative data from Ads Manager.
license: MIT
metadata:
  version: "0.1.0"
  role: hub
---

# Creative context

This is the hub of the package. Run it once per brand and per session, before grading, briefing or ideating. Everything downstream reads what it sets up: the brand profile, the data mode, the metric definitions, the ad-type vocabulary and the naming fields.

The brand is always an input. Nothing here assumes a particular brand, category or ad account.

## Step 1: Brand profile

1. Look for `creative-profile.md` in the working directory. If it exists, read it, confirm it is still current in one line, and move on.
2. If not, interview the user using the fields in `references/brand-profile-template.md`: brand, category, products, offer and sale calendar, personas, funnel goals, brand tone, colours. Ask in two or three short rounds, not one long form. Accept "skip" for any field and record it as unknown rather than inventing a value.
3. If you can write files, save the answers as `creative-profile.md` in the working directory. If you cannot, print the profile in a code block and tell the user to keep it for next time.

Every field in the profile comes from the user. Never fill a gap from what you assume brands in that category usually do.

## Step 2: Detect the data mode

Work out which of three modes you are in, and say which one out loud.

1. **Connector.** If a Meta ads MCP server is connected, follow the numbered steps in `references/data-inputs.md`: read-only calls only, field catalogue first, ad-level daily rows saved to JSON files, then `scripts/from_mcp.py` with the account totals so a short pull is caught. Anything the connector does not return means that metric is unavailable from it, and you fall back to a CSV for it. 3-second plays are derived per ad and labelled "(derived)". Meta's connector is new and its field list can change, so check in your session.
2. **CSV or screenshots.** If there is no connector, or it lacks the fields you need, ask for an Ads Manager export using `references/export-recipe.md`. Load it with `scripts/creative_metrics.py` when you can run Python. If you cannot run code, ask for screenshots of the table with those columns and compute by hand from the formulas.
3. **No data.** If the user has neither, work in ideation-only mode. Label every grade, ranking and recommendation "no performance data" so nobody mistakes a judgement from craft for a result.

Record the mode in your reply and in `creative-profile.md` under "Data".

## Step 3: Use the metric definitions verbatim

`references/metrics.md` is the only source for metric ids and formulas. Rules that follow from it:

- Quote the formula the first time you use a metric in an answer.
- Hook rate and thumb-stop rate are the same number. Use hook rate, mention the alias once.
- Hold rate is ThruPlay-based. If ThruPlays are missing, say hold rate is unavailable. Do not swap in another watch-time measure and call it hold rate.
- State whether CTR used link clicks or all clicks.
- A missing field or a zero denominator is "n/a (missing <field>)", never 0.
- Judge every number against the account's own baseline: its median and quartiles over a trailing window, for the same format and funnel stage. There are no universal "good" values in this package, and you must not quote any.

When Python is available, `scripts/creative_metrics.py` does the arithmetic:

```
python3 scripts/creative_metrics.py ads.csv          # per-ad table
python3 scripts/creative_metrics.py ads.csv --json   # same, machine-readable
```

The CLI prints n/a for anything it cannot compute, flags young ads, and marks ads whose CTR is below the first quartile of their own format. Read its output, do not retype it.

## Step 4: Classify each ad

Tag every ad with one type from `references/ad-types.md`: BAU/evergreen, promo/sale, launch/new product release, hype/teaser, partnership/creator, or retention. Compare ads of the same type with each other. A launch spike is not credit for the always-on ads running beside it.

## Step 5: Read the names

Ad names carry the variables you need to slice results. Use `references/naming-convention.md` to split a name into concept, format, creator, ad type, product, tone and launch date. If the names do not follow a convention, say so, propose one, and ask the user to confirm before you tag ads from the name. Treat a parsed field as a guess until the user confirms it.

## Hand-off to other skills

Finish this skill by writing a short context block that later skills can read:

```
Brand: <name>            Mode: connector | csv | none
Window: <dates>          Currency: <code>
Baseline: median/p25/p75 per format from the last <n> days
Conversions column: <Purchases | Results | ...>
Naming convention: <detected | proposed | none>
```

## Guardrails

- Never send the user's data anywhere. Everything runs inside the agent session.
- Never state a benchmark or an industry average. If the user asks for one, explain that this package compares an ad with its own account, and offer to compute that.
- Never act on the account. These skills read and advise. If a connector offers write tools, do not call them unless the user explicitly asks for that action in this conversation.
- Mark anything you could not check as "check in your Ads Manager" rather than stating it as fact.
