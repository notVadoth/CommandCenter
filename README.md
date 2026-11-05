# Command Centre

A web app to interactively analyse geopolitics with Current affairs, Blocs and macroeconomic figures available at the user's discretion.

Open `commandcenter-map.html` (or `index.html`) in a browser. No build step and no server are needed.

## What's in it

- **World map** (Leaflet). Toggle national, province/state and county/district boundaries, plus bloc overlays (EU, NATO, BRICS and more).
- **Country hover card and click drawer:**
  - GDP, GDP per capita and Gini (World Bank).
  - Paramount leader and cabinet (Wikidata/Wikipedia).
  - GDP and population growth charts.
  - Legislature composition, with the governing coalition highlighted.
- **Contested control layers:** areas held by non-state actors, occupied territory, DMZs and ceasefire lines, and disputed territories. Sources are listed in [`CONTROL_SOURCES.md`](CONTROL_SOURCES.md).
- **Headlines panel:**
  - Market charts (Dow, S&P 500, Hang Seng, BSE Sensex, Gold, Brent): live from TradingView, with a "Daily close" view from the daily job that also works offline.
  - A "Global diplomacy" section.
  - Daily headlines for the 20 largest countries by population and by GDP, plus other major stories. Each story links up to 3 outlets from different sides.

## Hosting (GitHub Pages)

1. **Settings → General → Danger Zone → Change visibility → Public.** Pages is free only for public repos.
2. **Settings → Pages → Build and deployment → Source: Deploy from a branch → `main` / `(root)` → Save.**
3. After a minute or so the site is live at `https://notvadoth.github.io/CommandCenter/`.

## Daily data update on GitHub (no PC needed)

`.github/workflows/daily.yml` runs every morning at 6:41 am Toronto time (7:41 am in summer). It runs the three scripts below and commits the new `data/` files; Pages then republishes on its own.
- To run it now: **Actions → Daily data update → Run workflow**.
- If a run can't push, set **Settings → Actions → General → Workflow permissions** to **Read and write**.
- Optional: add a repository secret `EODHD_KEY` (**Settings → Secrets and variables → Actions**) to fill the Daily close charts for the Hang Seng, Sensex and Gold. The live charts don't need it.

## Daily data update on your PC

`trawler/` holds the free daily job (Python standard library only, no API keys required). It runs three scripts:
- `trawler.py` writes bloc memberships.
- `news.py` writes headlines.
- `markets.py` writes market closes.

All three write into `data/`. Locally on Windows, run `trawler\setup_daily_task.bat` once to schedule it every morning, or run `trawler\run_trawler.bat` by hand. See [`trawler/README.md`](trawler/README.md).

If GitHub runs the job, you can switch the PC task off with `trawler\remove_daily_task.bat`; `git pull` brings the latest data down. A local EODHD key goes in `trawler/keys.json`, which is git-ignored; never commit it.

## Live headlines when you click a place (free relay)

Clicking a country or province shows its top Google News headlines from the last 24 hours at the top of the Headlines panel; × goes back to the daily headlines. Browsers can't read Google News directly, so a tiny free relay sits in between:

1. Sign in (or sign up, free) at [dash.cloudflare.com](https://dash.cloudflare.com) → **Workers & Pages → Create → Create Worker**.
2. Name it `cc-news` → **Deploy** → **Edit code**.
3. Replace everything with the contents of [`relay/news-relay.js`](relay/news-relay.js) → **Deploy**.
4. Copy the worker's address (`https://cc-news.<your-name>.workers.dev`) into `data/config.js` as `newsRelay`, and commit it.

The relay only answers pages served from `notvadoth.github.io` or opened from your PC (edit `ALLOWED_ORIGINS` if you rename the repo or use another host). It caches each place for 15 minutes; Cloudflare's free plan allows 100,000 requests a day. If the relay isn't set up, the panel says so and nothing else changes.

## Charts for the place you click, and chart search

Clicking a place adds its own charts to the market panel (the six defaults stay in the drop-down). For example, Wayanad shows coffee, Kerala tea planters, the Sensex and the rupee; Texas shows oil, gas, cattle and cotton. The choices come from [`data/market_catalog.js`](data/market_catalog.js): add a region there with a name pattern and its chart keys.

TradingView's free embedded charts don't show every market. Exchange feeds like the Nikkei, FTSE, ICE coffee futures, palm oil, rubber and iron ore futures only display on tradingview.com, so the catalog uses index CFDs, US-listed country ETFs and producer stocks (e.g. Vale for Brazilian iron ore) instead. There is no embeddable tea price, so tea regions use tea-grower stocks, labelled as such.

The search box next to Live / Daily close takes any TradingView symbol (`AAPL`, `NSE:TCS`, `FX_IDC:USDJPY`) or a catalog name (`coffee`, `copper`). The last 8 searches are kept under "My charts".

## Data and licences

- Boundaries: Natural Earth (public domain) and geoBoundaries (CC BY 4.0).
- Live figures: World Bank, Wikidata and Wikipedia.
- Markets: live charts embedded from TradingView (free widget, attribution kept); daily closes from FRED.
- Headlines link to the original outlets; only titles are stored. Live place headlines come from Google News search via your own relay.
- ISW/CTP maps are not included (their licence requires written consent).
