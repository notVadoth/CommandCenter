# Command Centre

A web app to interactively analyse geopolitics with Current affairs, Blocs and macroeconomic figures available at the user's discretion.

**Live site:** https://notvadoth.github.io/CommandCenter/

Command Centre is a single-page world map that brings together political geography, economic indicators, contested territory, multilateral blocs, market data and daily news. It runs entirely in the browser; a scheduled job refreshes its data files once a day.

## Features

**Map**
- Physical, topographic, satellite and bathymetric base maps.
- National, province/state and county/district boundaries, loaded per country as you zoom.
- Bloc overlays: EU, NATO, BRICS and partners, G7, G20, ASEAN, SCO, CSTO, African Union, GCC, OPEC, USMCA, Mercosur, Five Eyes, Quad and the Mecca Joint Defence Agreement.
- Contested-control layers: areas held by non-state actors, occupied territory, DMZs and ceasefire lines, and disputed territory. Each area shows its source and date.

**Country and province details**
- Hover card with GDP, GDP per capita, Gini, leader and cabinet for countries; leader and government for provinces and states.
- Click panel with GDP-growth and population-growth charts, and the legislature's composition with the governing coalition highlighted.

**Headlines panel**
- Market chart: Dow Jones, S&P 500, Hang Seng, BSE Sensex, gold and Brent by default.
  - Clicking a place adds recommended charts for it, e.g. coffee and tea growers for Wayanad, oil and cattle for Texas.
  - A search box opens any TradingView symbol.
- Top headlines from the last 24 hours for the place you click.
- Daily headlines:
  - A "Global diplomacy" section for summits and multilateral bodies.
  - Stories for the 20 largest countries by population and by GDP.
  - Each story is linked to up to three outlets from different sides of the issue.

**Layout**
- The layers, country and headlines panels each collapse to a side strip.
- On phones the panels open over the map, one at a time.

## How it works

```
GitHub Actions (daily)                        Browser
──────────────────────                        ───────
trawler/trawler.py ─► data/groupings.js  ─┐
trawler/news.py    ─► data/stories.js    ─┼─► commandcenter-map.html ◄─ World Bank, Wikidata, Wikipedia (live)
trawler/markets.py ─► data/markets.js    ─┘          │                ◄─ TradingView widgets (live)
                                                     └─► relay/news-relay.js (Cloudflare Worker) ─► Bing News
```

- **`trawler.py`** reads news feeds for claims that a country joined, left or applied to a bloc. Each claim is checked against Wikidata and against independent outlets. A change appears on the map only when two or more independent outlets report it.
- **`news.py`** groups the day's headlines from about 30 outlets into stories. For each story it picks sources from different perspectives and assigns it to a country or to the diplomacy section.
- **`markets.py`** stores daily Brent closes for the offline "Daily close" view.
- **`relay/news-relay.js`** is a small Cloudflare Worker. It fetches Bing News search results for a clicked place, because browsers cannot read the feed directly.

The scripts use only the Python standard library. No API keys are required.

## Project structure

```
commandcenter-map.html     the app (HTML, CSS and JavaScript in one file)
index.html                 redirects to the app
data/                      data files loaded by the app
  config.js                news relay address
  market_catalog.js        TradingView symbols and place-to-chart rules
  *.geojson                contested-control, disputed-area and DMZ layers
  groupings.js, stories.js, markets.js   written by the daily job
trawler/                   daily job: trawler.py, news.py, markets.py, and their settings
relay/news-relay.js        Cloudflare Worker for place headlines
.github/workflows/daily.yml   schedule for the daily job
CONTROL_SOURCES.md         sources for each contested-control layer
```

## Running locally

Open `commandcenter-map.html` in a browser. There is no build step and no server is needed.

To refresh the data by hand:

```
cd trawler
python trawler.py run
python news.py
python markets.py
```

On Windows:
- `trawler\run_trawler.bat` runs all three scripts and keeps a log.
- `trawler\setup_daily_task.bat` schedules it every morning.
- `trawler\remove_daily_task.bat` removes the schedule.

See [`trawler/README.md`](trawler/README.md) for options.

## Deployment

**GitHub Pages:** in **Settings → Pages**, deploy from the `main` branch, root folder.

**Daily data update:** `.github/workflows/daily.yml` runs at 11:41 UTC and commits the refreshed files in `data/`. Pages then redeploys automatically.
- To run it by hand, use **Actions → Daily data update → Run workflow**.
- The workflow needs **Settings → Actions → General → Workflow permissions → Read and write**.

**News relay:**
1. Create a Cloudflare Worker.
2. Paste in [`relay/news-relay.js`](relay/news-relay.js) and deploy.
3. Put the Worker's address in `data/config.js`.

The relay only answers requests from the origins listed in `ALLOWED_ORIGINS`, and caches each search for 15 minutes.

## Configuration

| File | What it controls |
|---|---|
| `commandcenter-map.html` → `GROUPINGS` | Built-in bloc members and colours |
| `trawler/blocs.json` | Blocs the trawler tracks, with aliases and Wikidata lookup |
| `trawler/feeds.json` | Feeds the bloc trawler reads |
| `trawler/news_sources.json` | Outlets and the perspective ("camp") each represents |
| `data/market_catalog.js` | Chart symbols and which places they are recommended for |
| `data/config.js` | News relay address |

Secrets never go in the repository:
- Optional keys, such as `EODHD_KEY` for extra daily market series, belong in GitHub Actions secrets.
- On a local machine they go in `trawler/keys.json`, which is git-ignored.

## Data sources and licences

The app's left panel lists every source with its licence. In summary:

| Data | Source | Licence |
|---|---|---|
| National borders | Natural Earth | Public domain |
| Province and district borders | geoBoundaries (Runfola et al., 2020, *PLoS ONE* 15(4): e0231866) | CC BY 4.0 |
| Base maps | Esri; OpenTopoMap, © OpenStreetMap contributors | Esri terms; CC BY-SA, ODbL |
| GDP, Gini, growth charts | World Bank, World Development Indicators | CC BY 4.0 |
| Leaders and cabinets | Wikidata | CC0 |
| Legislature seats | Wikipedia infoboxes | CC BY-SA 4.0 |
| Contested-control layers | Per layer; see [`CONTROL_SOURCES.md`](CONTROL_SOURCES.md) | Per source |
| Headlines | Outlets' RSS feeds; Bing News search | Titles and links only |
| Live market charts | TradingView widgets | TradingView terms |
| Brent daily closes | U.S. Energy Information Administration via FRED | Public domain |

**Not included:**
- Daily data for the S&P 500 and Dow Jones. On FRED these series are copyrighted by S&P Dow Jones Indices and may not be republished, so they appear only as live charts.
- ISW/CTP conflict maps, which require written consent.

## Limitations

- Contested-control outlines are approximate and can lag events. The current Ukraine front line is not included because no openly licensed source was found.
- Economic figures are national only; provinces and states show their leader and government.
- TradingView's embedded charts do not display some exchange feeds (Nikkei, FTSE, several futures). The catalogue uses CFDs, country ETFs or producer stocks instead, and labels them as such.
- Place headlines rely on Bing News search coverage.

## Versions

Saved snapshots are kept as branches:
- **`V2`**: headlines panel, market charts and GitHub hosting.
- **`V3`**: place headlines, recommended charts and chart search.

`main` is the current version.
