#!/usr/bin/env python3
"""
CommandCenter market charts: free daily closes for the Headlines panel.

  Dow Jones, S&P 500, Brent crude  ->  FRED (St. Louis Fed), no key needed
  Hang Seng, BSE Sensex, Gold      ->  EODHD free plan (20 calls/day), only if you add a key

To turn on the three optional series, get a free key at https://eodhd.com/register and save
it in trawler/keys.json as  {"eodhd": "YOUR_KEY"}  (or, on GitHub, as a repository secret named
EODHD_KEY).  The key stays on your PC: it is never
written into the page or data/markets.js. Without a key those series show "no free source
configured" plus a link to the official index page.

  python markets.py            # normal daily run (6 requests at most)
"""
from __future__ import annotations

import argparse, csv, datetime as dt, io, json, os, sys
from pathlib import Path

import trawler as T

HERE = Path(__file__).resolve().parent
TODAY = dt.date.today()

SERIES = [
    # key, label, kind, unit, provider, provider id, official page
    ("DJIA",  "Dow Jones",   "index",     "pts",     "fred",  "DJIA",         "https://fred.stlouisfed.org/series/DJIA"),
    ("SPX",   "S&P 500",     "index",     "pts",     "fred",  "SP500",        "https://fred.stlouisfed.org/series/SP500"),
    ("HSI",   "Hang Seng",   "index",     "pts",     "eodhd", "HSI.INDX",     "https://www.hsi.com.hk/eng"),
    ("SENSEX","BSE Sensex",  "index",     "pts",     "eodhd", "BSESN.INDX",   "https://www.bseindia.com/sensex/code/16/"),
    ("GOLD",  "Gold",        "commodity", "USD/oz",  "eodhd", "XAUUSD.FOREX", "https://www.lbma.org.uk/prices-and-data/precious-metal-prices"),
    ("BRENT", "Brent crude", "commodity", "USD/bbl", "fred",  "DCOILBRENTEU", "https://fred.stlouisfed.org/series/DCOILBRENTEU"),
]

def fred(sid: str, since: dt.date) -> list[list]:
    text = T.http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since.isoformat()}", timeout=30).decode("utf-8", "replace")
    if text.lstrip().startswith("<"): raise RuntimeError("FRED returned a web page, not data (series may be discontinued)")
    rows = list(csv.reader(io.StringIO(text)))[1:]
    return [[d, round(float(v), 2)] for d, v in rows if v not in ("", ".") and d >= since.isoformat()]

def eodhd(sym: str, since: dt.date, key: str) -> list[list]:
    text = T.http_get(f"https://eodhd.com/api/eod/{sym}?api_token={key}&fmt=json&from={since.isoformat()}", timeout=30).decode("utf-8", "replace")
    data = json.loads(text)
    if not isinstance(data, list): raise RuntimeError(str(data)[:120])
    return [[r["date"], round(float(r.get("close") or r.get("adjusted_close")), 2)] for r in data if r.get("close") is not None]

def run(args):
    since = TODAY - dt.timedelta(days=int(args.days))
    keys = T.read_json(HERE / "keys.json", {}) or {}
    if os.environ.get("EODHD_KEY"): keys["eodhd"] = os.environ["EODHD_KEY"]   # GitHub Actions secret
    old = {}
    prev = HERE / "markets.json"
    if prev.exists(): old = (T.read_json(prev, {}) or {}).get("series", {})
    out = {}
    for key, label, kind, unit, prov, pid, page in SERIES:
        s = {"label": label, "kind": kind, "unit": unit, "page": page, "points": [], "source": "", "note": ""}
        try:
            if prov == "fred":
                s["source"] = "FRED, Federal Reserve Bank of St. Louis"; s["source_url"] = f"https://fred.stlouisfed.org/series/{pid}"
                s["points"] = fred(pid, since)
            elif keys.get("eodhd"):
                s["source"] = "EODHD (free plan)"; s["source_url"] = "https://eodhd.com/"
                s["points"] = eodhd(pid, since, keys["eodhd"])
            else:
                s["note"] = "No free source configured: add an EODHD key to trawler/keys.json (see markets.py)."
        except Exception as e:
            msg = str(e).replace(keys.get("eodhd") or "\0", "***")   # never log the key
            s["note"] = f"Today's download failed ({msg[:90]})."
            if old.get(key, {}).get("points"):            # keep yesterday's chart rather than a blank
                s["points"] = old[key]["points"]; s["source"] = old[key].get("source", ""); s["source_url"] = old[key].get("source_url", "")
                s["note"] += " Showing the last good data."
            print(f"  ! {label}: {msg}", file=sys.stderr)
        out[key] = s
        print(f"  {label:12s} {len(s['points']):4d} days" + (f"  ({s['note']})" if s["note"] else ""))
    doc = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "series": out}
    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    T.write_text_atomic(prev, payload)
    T.write_text_atomic(Path(args.js_out), "// written by markets.py, loaded automatically by commandcenter-map.html\nwindow.CC_MARKETS = " + payload + ";\n")
    print(f"wrote {args.js_out}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--js-out", default=str(HERE.parent / "data" / "markets.js"))
    ap.add_argument("--days", default=400, help="history to keep (days)")
    run(ap.parse_args())

if __name__ == "__main__":
    main()
