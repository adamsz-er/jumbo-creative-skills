# FAQ

Short answers. For the reasoning, see [how it works](how-it-works.md); for fixes, see [troubleshooting](troubleshooting.md).

## Getting started

### What does this package do?

It teaches your AI agent to review your Meta ad creative against your own account, say which ads to keep, fix or pause, and help you make new concepts, hooks and briefs. It reads and advises. These skills never call a tool that changes your ad account. Your agent could, if you asked it to directly, through the Meta connector's own tools.

### What do I say first?

Say "review my Meta ads". The creative-review skill does the rest: it gets the data, checks the totals, grades every ad, builds a dashboard and replies with three bullets and the path to the report. Without data, say "show me a sample review".

### Do I need to install all the skills?

No. Each skill works on its own, with its own copy of the shared code. Installing them all is easiest because creative-review calls its siblings; if one is missing it stops with a message naming the skill and the install command.

### Where do my results go?

Each review is saved in a `creative-review-runs` folder in your working directory, one subfolder per run, holding the data, the JSON results, `summary.md` and `report.html`. The next review of the same account compares itself with the latest one.

### Can I try it without my own data?

Yes. `python3 -I skills/creative-review/scripts/review.py run --demo` reviews a made-up account (Acme Outdoor Co.) and labels every output "sample data".

## Data and connections

### Do I need the Meta MCP?

No. It is the most convenient source, but an Ads Manager CSV export works for every metric (the export recipe lists the columns), and without any data the make skills still work. The MCP may not be enabled on every ad account yet.

### Why is hook rate missing or marked derived?

Meta's connector returns 3-second video plays only at ad set level and above, not per ad. The skills derive them per ad from the cost per 3-second view and mark the result "(derived)". Meta rounds that cost to cents, so when the rounding could throw the answer out by more than a small margin (an arbitrary default you can read in `creative_metrics.py`), the skills refuse to derive it and hook and hold rate show n/a with the reason. An Ads Manager export that includes the 3-second video plays column gives you both.

### Why was my pull reconciled / what does a shortfall warning mean?

A long connector pull can stop partway with no cursor and no warning, and a batch can be silently capped. So the review adds up the spend and impressions it pulled and compares them with account totals for the same window. "Reconciled" means they match within a small tolerance. A shortfall warning (E-RECONCILE) means ads are missing: usually archived ads that delivered in the window, or a batch that was too big. Re-pull the missing ads in smaller batches and run it again.

### Which attribution window do the numbers use?

Whatever you asked for. The connector does not say which setting it used, so the report header shows only what you pass (`--attribution`) and otherwise reads "not stated". An Ads Manager export uses the setting you chose when exporting; mention it when you share the file.

### Why do reach and frequency show n/a?

Reach counts people, so it does not add up across ads or days. The skills only show reach and frequency when you give an account-level figure for the same window and scope (`--account`). A whole-account figure on a one-market page would be the wrong number, so it is left n/a.

### Why are there no ad images in the report?

The connector returns preview links, not image files. Save screenshots of the ads you care about as `<ad_id>.png` in a folder and pass it with `--previews`; otherwise cards show a labelled placeholder.

## Metrics and grading

### Why don't you tell me what a good hook rate is?

Because it depends on your format, your audience, your offer and your account. A number that is good for one account is ordinary for another, and quoting one would mislead you. These skills compare each ad with the other ads in your own account (the median and quartiles of the same format and ad type over the same window). Where an industry figure is shown, it comes from a cited public source, appears only as context, and never changes a grade or a verdict.

### Why does an ad say too early to judge?

An ad is still learning when it is younger than a minimum age or has fewer than a minimum number of impressions. Judging it would mean reading noise. Both minimums are arbitrary defaults (`--young-days`, `--min-impressions`): set them from your own account. Ads that cannot be judged are never told to pause, iterate or scale.

### Why is an ad "not graded (low volume)"?

It has fewer impressions than `--min-impressions`, so its numbers are shown but not placed in a quartile. Lower the minimum only if your own spend per ad is small; a low volume grade is a guess.

### What does "early read" mean?

The ad was compared with a small group (fewer than twice the minimum of five comparable ads), or has few delivery days, or only one payback measure. The grade or verdict is a lead to check, not a conclusion, and the output says which group was used.

### What if my ad names don't follow a convention?

Detection reads positional names (split on ` | `, `|`, ` _ `, `_` or ` - `) and `KEY:value` names, and says what share of all your names it read. Names it cannot read go to "unclassified" and are listed, never dropped. Tell the agent which key is the concept and what any unlabelled segment means (`--key-map 6=tone`), or what your own ad-type words mean (`--type-map core=bau`). The answers live in the `Script settings` of your profile so you are not asked twice. Grading by format and ad type still works from the data columns.

### Why is a metric n/a instead of 0?

n/a (missing <field>) means the data does not have what the formula needs. Showing 0 would say something happened that did not. Add the column to your export, or pull the field, and it fills in.

### Can I change the thresholds?

Yes, and you should. Every default (minimum impressions, fatigue window, minimum change, minimum group size, how many top ads are protected, the Pareto share) is arbitrary and settable with a flag or in your profile's Script settings. [How it works](how-it-works.md#defaults-and-the-flags-that-change-them) lists every flag. Pick values from your own account, such as your own week-to-week noise, and the scripts print the settings they used.

## Decisions

### How does keep-or-kill decide to pause an ad?

It pauses only when an ad is in the bottom quartile of its group and of the whole objective on every payback measure and either is fatiguing or never worked. A never-worked ad is paused only when it misses a target you set; without a target it reads "Check before cutting" and asks for one. Your biggest sellers are never paused without a check.

### Why did an ad say "check before cutting" instead of pause?

Something weakens the case: its payback measures disagree, the comparison group is small, it is one of your biggest sellers, or you have not set a target. The sentence names the reason. Rule out tracking, site and audience problems before you pause anything.

### Does it judge every campaign the same way?

No. Each ad is judged on its own campaign objective: sales on cost per sale and return on ad spend, traffic on cost per click and CTR, awareness on CPM and hook rate, leads on cost per lead, engagement on engagement rate. If the data has no objective column, every ad is treated as a sales ad and the output says so; add the column to judge each ad on its goal.

### Will it change my ads for me?

No. It recommends. These skills never call a tool that changes your ad account. Your agent could, if you asked it to directly, through the Meta connector's own tools.

## Making creative

### Do the make skills need data?

No. Ideas, hooks, personas and briefs work with just a brand profile, and they get sharper with the analysis outputs (gaps in your mix, what faded, what won). Without data, nothing is labelled as proven.

### Where do the claims and results in a brief come from?

Only from you and your data. The skills do not invent testimonials, statistics or promised results, and they mark claims that need sign-off. Any example quote in the repository is illustrative.

### How do I make a one-change variant of a winning ad?

Ask hook-writer for variants of the ad, or ask creative-brief for a one-change brief on an ad the review marked Iterate. Changing one thing at a time (the opening, the creator) lets you see what moved the result.

## The report

### How do I share the report?

Send the single `report.html` file; it embeds its own images and works in any browser. To print it or save it as PDF, use your browser's print dialog. You can also copy the page address after setting filters, and it reopens the same view.

### Why do the report fonts look different offline?

The page asks Google Fonts for its typeface. Offline, or with that blocked, the browser falls back to a system font. Nothing else changes.

### What does "What changed since last time" compare?

The latest earlier review of the same account: which ads changed verdict, which are new or gone, and how spend, return on ad spend and cost per purchase moved. A different account is never compared, and a first run shows an empty state.

## Privacy and safety

### Does my data leave my machine?

The scripts run on your machine and make no network calls. But your AI agent sends what it reads, including your ad data and the results, to its AI provider, the same as anything else you share in a chat. The Meta connector is Meta's own service. The report is one local file whose only outside requests are to Google Fonts.

### Can it make changes in my ad account?

No. Everything here is advice. These skills never call a tool that changes your ad account. Your agent could, if you asked it to directly, through the Meta connector's own tools.

### Is it safe to share a report?

A report contains your ad names, spend and results. Share it as you would any account data, and never publish one built from a real account.

## Installing and updating

### How do I update?

Claude Code: run `claude plugin marketplace update jumbo-creative-skills`. Other agents: re-run the install command you used. Claude desktop or claude.ai: download the new zips from the latest Release and upload them again.

### Can I use this for TikTok or Google?

The skills are built Meta-first. Several metrics (hook rate, hold rate, ThruPlay) are defined from Meta's video measures, and hold rate is Meta-specific. A CSV from another platform may work for the metrics whose columns it can supply under the same names (spend, impressions, clicks, purchases), but the naming, objectives and video rules assume Meta, so treat anything else as untested.

### Can I use it in ChatGPT?

The skills follow the Agent Skills format, so they work in any agent that supports it and can run Python (see the install table). We have not tested them in ChatGPT. Without code execution the scripts cannot run, and the agent would have to compute from the formulas in `metrics.md` by hand.

### Why does the plugin not show up after installing?

Start a new Claude Code session. If it still does not show, run the install commands in the README again.

### Can I contribute?

Yes. Run the tests, the skill validator and the sync check (see Contributing in the README). Examples use the fictional Acme Outdoor Co., never real brands or accounts.
