# CommandCenter trawler

Reads news, finds claims that countries **joined / left / applied to / were suspended from** a grouping (or **signed** a new pact), and checks each claim separately before it changes your map.

Python 3.9+. There's nothing to install.

## Quick start

```
python trawler.py run
```

This reads the RSS feeds in `feeds.json`, fetches each article, and extracts claims. It checks them, prints a review list, and writes `groupings.json`. The map loads the result automatically from `..\data\groupings.js`. **Groupings → Load groupings.json…** still works for loading other files by hand.

Other inputs:

```
python trawler.py run --input saved_articles/        # .txt / .html / .json files
python trawler.py run --input urls.txt               # one URL per line
python trawler.py run --input saved_articles/ --feeds-too
python trawler.py report                             # reprint the review list
```

A `.txt` article can begin with `Title:`, `Source:`, `URL:` and `Date:` lines.

## How verification works

An article can only *propose* a claim. Whether the claim is believed is decided by data from somewhere else:

| Status | Meaning | Changes the member list? |
|---|---|---|
| **confirmed** | Wikidata's membership records agree (e.g. it records an end date when the article says a country left) | yes |
| **corroborated** | 2+ *independent* outlets report it, but Wikidata hasn't caught up | only with `--accept corroborated` |
| **single-source** | one outlet only | no, shown dashed on the map |
| **speculative** | only "could / may / plans to / reportedly" language | no |
| **conflict** | Wikidata contradicts it (e.g. "X left NATO" while Wikidata lists X as a current member) | no, flagged for review |

- **Independence:** outlets are counted by website, and copies of the same wire story count once.
- **Applications** ("applied to join", "invited") are tracked as applicants and never treated as members.
- **Baseline check:** the trawler also compares your `blocs.json` against Wikidata's current membership and prints any differences.
- **Memory:** claims build up in `trawler_cache/claims.json` across runs. A story that only one outlet reported today can become corroborated tomorrow.

## Optional: Claude for extraction

```
set ANTHROPIC_API_KEY=sk-ant-...      (Windows)    export ANTHROPIC_API_KEY=...   (mac/linux)
python trawler.py run --llm
```

This catches phrasing the built-in rules miss. Claude only *extracts* claims. Checking them still uses Wikidata and the outlet count, so the model never decides on its own claims. Each article costs an API call.

## Files you edit

- `feeds.json`: your trusted sources (name and RSS URL). Add or remove freely.
- `blocs.json`: tracked groupings, starting members, colours and aliases. `qid` pins a group's Wikidata entry; otherwise `wikidata_search` is used to find it.
- `countries.json`: country names and their 3-letter codes. Add aliases here if a name is missed.

## Headline panel (`news.py`, free, no AI)

`news.py` runs right after the trawler in the daily task. It:
1. Picks the **focus countries**: the 20 largest by population plus the 20 largest by GDP (World Bank, about 30 countries).
2. Reads the outlets in **`news_sources.json`**. Each outlet has a *camp*: Western, Ukrainian, Russian state, Chinese state, Israeli, Arab/Gulf, Iranian state, Turkish state, Indian, Pakistani, African, Latin American, or UN/multilateral.
3. Groups headlines about the same event and keeps the top 4 stories per focus country, plus about 12 "Elsewhere" stories covered by 2+ outlets.
4. For each story, shows **up to 3 outlets from different camps**. These are the sides involved (e.g. Ukrainian plus Russian state for a Kharkiv strike), then UN News, then others. Each one is that outlet's own headline, linking to the article.
   - If a side involved didn't cover the story, it shows "No [side] coverage" with search links instead.
5. Writes `..\data\stories.js`. The map's right-hand **Headlines** panel loads it automatically and filters to the part of the map you're looking at ("In view"), or shows everything ("All").

**Editing outlets:** add or remove them in `news_sources.json`. A camp's `home` countries decide which side an outlet speaks for. Feeds that fail are listed in the log and in the panel's header ("23/28 feeds").

Nothing is summarised or rewritten, and no API or key is used, so it costs nothing.

## Run it daily (automatic)

1. Double-click **`setup_daily_task.bat`** once. It registers a Windows scheduled task, "CommandCenter Trawler", that runs every day at 6:45 am, and starts a first run straight away.
   - If the PC is off or asleep at 6:45, the task runs as soon as it's back on.
   - To use a different time, run `setup_daily_task.bat 8:30am` from a terminal.
2. Each run writes `groupings.json` here and **`..\data\groupings.js`**. The map loads `groupings.js` automatically every time it opens, so there is nothing to click. The Groupings panel shows when the trawler last ran, and warns if that was more than a day and a half ago.
3. Logs go to `logs\last_run.log`, with one file per day kept for 30 days.
4. To stop the daily run, double-click **`remove_daily_task.bat`**. To run it by hand, double-click **`run_trawler.bat`**.

If the log says Python wasn't found, install it from python.org and tick "Add python.exe to PATH". The Microsoft Store placeholder `python` doesn't count.

## Limits

- **Built-in rules:** they read one sentence at a time and rely on keywords. They can attribute a claim to the wrong country in long sentences listing several countries. The verification step exists to catch that.
- **Wikidata lag:** Wikidata sometimes trails real events by days. A missing entry is treated as "unknown", never as a contradiction.
- **Paywalls:** paywalled sites fall back to the RSS summary.

## Market charts (`markets.py`, free)

The top third of the Headlines panel is a chart you switch with the drop-down (Dow Jones, S&P 500, Hang Seng, BSE Sensex, Gold, Brent crude) and the 1M / 3M / 1Y buttons. `markets.py` runs last in the daily task and writes `..\data\markets.js`.

| Series | Source | Needs |
|---|---|---|
| Dow Jones, S&P 500, Brent crude | [FRED](https://fred.stlouisfed.org/) (St. Louis Fed), daily closes | nothing |
| Hang Seng, BSE Sensex, Gold | [EODHD](https://eodhd.com/) free plan (20 calls a day; this uses 3) | a free key |

To turn on the last three, register at eodhd.com, then create `trawler\keys.json` containing `{"eodhd": "YOUR_KEY"}`. The key stays on your PC and is never written into the page or the data files (keep `keys.json` out of any public repo). If a download fails, the chart keeps the previous day's data and says so.

## Global diplomacy section

Stories whose headlines are mostly about multilateral bodies or summits (EU, NATO, BRICS, G7, G20, UN General Assembly / Security Council, ASEAN, SCO, African Union, OPEC, COP, APEC, GCC, WTO, IMF, or any "summit") are listed first under **Global diplomacy**, with a tag for each body, and shown whatever part of the map is in view. The story's lead headline comes from a UN source if one covered it, then a Western outlet, then any outlet not from a country involved.
