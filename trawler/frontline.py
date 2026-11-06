#!/usr/bin/env python3
"""
CommandCenter front-line tracker: marks districts as contested in active wars, from news reports.

For each war in wars.json, once a day:
  1. Read the news feeds in news_sources.json plus a few Bing News searches per war (past 24 hours).
  2. Keep only sentences that report ground control changing hands: "<side> forces captured / took control
     of / liberated / entered <place>", "<place> fell to <side>". Strikes, shelling, failed or repelled
     assaults and attempts don't count.
  3. Find the place on Wikidata (its coordinates) and the district it lies in (geoBoundaries).
  4. Mark a district contested when, within the last 30 days, 3+ different outlets reported such a change
     there, and at least one of them isn't an outlet speaking for either side (state media, defence ministries).
Writes ../data/frontline.js (window.CC_FRONTLINE) with the districts' outlines and the reports behind them.
Reports are kept in frontline_state.json so evidence builds up over days.

Also lists "other fighting": countries outside the tracked wars where 3+ outlets this week reported a town or
district being captured, as candidates to add to wars.json. Nothing is mapped for those automatically.

  python frontline.py            # normal daily run
  python frontline.py --offline  # re-use cached feeds/geocodes only (testing)
"""
from __future__ import annotations

import argparse, collections, datetime as dt, json, math, re, sys, time, unicodedata, urllib.error, urllib.parse
from pathlib import Path

import trawler as T
import news as N

HERE = Path(__file__).resolve().parent
CACHE = HERE / "trawler_cache"
NOW = dt.datetime.now(dt.timezone.utc)
GEO_URL = "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/{iso}/{lvl}/geoBoundaries-{iso}-{lvl}_simplified.geojson"
WD_COUNTRY = {"UKR": "Q212", "RUS": "Q159", "YEM": "Q805", "SYR": "Q858", "SDN": "Q1049", "MMR": "Q836", "ISR": "Q801", "PSE": "Q219060", "LBN": "Q822"}

GAIN = r"(?:captured|seized|took(?: full)? control of|taken(?: full)? control of|gained control of|took|liberated|retook|recaptured|regained(?: control of)?|entered|overran|occupied|pushed into|advanced into|stormed|cleared)"
PLACE = r"(?:the\s+)?(?:(?:village|town|city|settlement|hamlet|district|port|port city|strategic town|key town|frontline town|front-line town)\s+of\s+)?(?P<place>[A-Z][\w'’\-]+(?:[ \-](?:al-|el-|ad-)?[A-Z][\w'’\-]+){0,2})"
NOT_GROUND = re.compile(r"\b(?:repell?ed|repulsed|failed|fail to|attempt(?:ed|s)? to|trying to|tried to|denied|deny|seeks? to|aims? to|plans? to|threaten(?:s|ed)? to|could|would|might|strike|struck|shell(?:ed|ing)|drone|missile|air ?strike)\b", re.I)
STOP = {"Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday","January","February","March","April","May","June","July","August",
        "September","October","November","December","The","A","An","Control","Positions","Territory","Ground","Part","Parts","Areas","Area"}


def load(p, default):
    return T.read_json(p, default) or default

def save(p, obj):
    T.write_text_atomic(p, json.dumps(obj, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- geography
def boundaries(iso, lvl):
    f = CACHE / f"geo_{iso}_{lvl}.geojson"
    if not f.exists():
        f.write_bytes(T.http_get(GEO_URL.format(iso=iso, lvl=lvl), timeout=60))
    return json.loads(f.read_text(encoding="utf-8"))["features"]

def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]; xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside

def contains(geom, x, y):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return any(_in_ring(x, y, p[0]) and not any(_in_ring(x, y, h) for h in p[1:]) for p in polys)

def district_at(iso, lvl, lon, lat):
    for f in boundaries(iso, lvl):
        if contains(f["geometry"], lon, lat):
            return f
    return None

# ---------------------------------------------------------------- geocoding (Wikidata, cached)
def wd_get(params):
    """Wikidata API call; waits and retries when rate-limited (HTTP 429)."""
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
    for wait in (5, 20, 60, None):
        try:
            return json.loads(T.http_get(url))
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait is None: raise
            time.sleep(int(e.headers.get("Retry-After") or wait))

def geocode(name, countries, cache, offline=False):
    """All settlements called `name` in `countries` (ISO3) on Wikidata: [{qid, iso, lat, lon}], cached."""
    key = name + "|" + ",".join(sorted(countries))
    if key in cache: return cache[key]
    if offline: return []
    want = {WD_COUNTRY[c]: c for c in countries if c in WD_COUNTRY}
    found = []
    try:
        ids = [h["id"] for h in wd_get({"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 12, "format": "json"})["search"]]
        if ids:
            ents = wd_get({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims", "format": "json"})["entities"]
            for i in ids:
                cl = ents.get(i, {}).get("claims", {})
                c17 = [c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in cl.get("P17", [])]
                iso = next((want[c] for c in c17 if c in want), None)
                coord = next((c["mainsnak"].get("datavalue", {}).get("value") for c in cl.get("P625", []) if c["mainsnak"].get("datavalue")), None)
                if iso and coord: found.append({"qid": i, "iso": iso, "lat": coord["latitude"], "lon": coord["longitude"]})
        time.sleep(1)     # be gentle with Wikidata
    except Exception as e:
        print(f"  ! geocode {name}: {e}", file=sys.stderr)
        return []         # don't cache failures
    cache[key] = found
    return found

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(oblast|governorate|district|raion|region|krai|republic of|city)\b", " ", s)
    s = re.sub(r"^(al|el|ad|ar|as|ash|at|an)[ \-]", "", s.strip())
    return re.sub(r"[^a-z]", "", s)

# common English spellings of first-level regions, to read hints like "in Donetsk region" or "in Marib"
REGION_ALIASES = {"zaporizhzhia": "zaporizhia", "zaporozhye": "zaporizhia", "hodeidah": "hudaydah", "hudaydah": "hudaydah", "taiz": "taizz",
                  "marib": "marib", "sanaa": "sana", "aden": "adan", "lahj": "lahij", "hadramout": "hadhramaut", "hadramawt": "hadhramaut",
                  "dnipropetrovsk": "dnipropetrovsk", "dnipro": "dnipropetrovsk", "kursk": "kursk", "belgorod": "belgorod", "bryansk": "bryansk"}

def region_hints(text, iso):
    names = {norm(f["properties"]["shapeName"]): f for f in boundaries(iso, "ADM1")}
    hints = set()
    for w in re.findall(r"[A-Z][\w'’\-]+", text):
        n = REGION_ALIASES.get(norm(w), norm(w))
        if n in names: hints.add(n)
    return hints, names

def resolve(place, text, war, gcache, offline):
    """The district (feature) where `place` is, or None when it can't be told apart from other places of that name."""
    # 1. the place is itself a district ("Harib district", "Kupiansk")
    for iso, lvl in war["countries"].items():
        for f in boundaries(iso, lvl):
            if norm(f["properties"]["shapeName"]) == norm(place): return iso, lvl, f
    # a whole region ("Crimea", "Donetsk region") is too broad to mark one district
    for iso, lvl in war["countries"].items():
        if lvl != "ADM1" and REGION_ALIASES.get(norm(place), norm(place)) in {norm(f["properties"]["shapeName"]) for f in boundaries(iso, "ADM1")}:
            return None
    # 2. a settlement: Wikidata coordinates -> district; region names in the text settle duplicates
    spots = []
    for g in geocode(place, list(war["countries"]), gcache, offline):
        lvl = war["countries"][g["iso"]]
        d = district_at(g["iso"], lvl, g["lon"], g["lat"])
        if d: spots.append((g, lvl, d))
    if not spots: return None
    isos = {g["iso"] for g, _, _ in spots}
    hinted = []
    for iso in isos:
        hints, names = region_hints(text, iso)
        for g, lvl, d in spots:
            if g["iso"] == iso and hints and any(contains(names[h]["geometry"], g["lon"], g["lat"]) for h in hints): hinted.append((g, lvl, d))
    pool = hinted or spots
    if len({d["properties"]["shapeID"] for _, _, d in pool}) > 1: return None   # ambiguous: several places of that name, no region named
    g, lvl, d = pool[0]
    return g["iso"], lvl, d

# ---------------------------------------------------------------- extraction
def side_pattern(words):
    return "(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + ")"

def claims_in(text, war):
    """[(side, place, sentence)] for ground-control changes in `text`."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\s+[-–—|]\s+", text):
        if len(sent) < 15 or NOT_GROUND.search(sent): continue
        for side, words in war["sides"].items():
            sp = side_pattern(words)
            for rx in (rf"\b{sp}\b[^.;]{{0,70}}?\b{GAIN}\s+{PLACE}",
                       rf"\b{sp}\b[^.;]{{0,40}}?\b(?:capture|seizure|liberation|takeover|recapture)\s+of\s+{PLACE}",
                       rf"{PLACE}\s+(?:has\s+|had\s+)?(?:fell|fallen|was captured|was taken|came under the control|is now under the control)\s+(?:to|by|of)\s+(?:the\s+)?{sp}"):
                for m in re.finditer(rx, sent):
                    pl = m.group("place").strip(" '’-")
                    if pl in STOP or any(pl == w or pl.startswith(w + " ") for ws in war["sides"].values() for w in ws): continue
                    if re.match(rf"{re.escape(pl)}\s+(?:region|oblast|governorate|province)\b", sent[m.start('place'):]): continue
                    out.append((side, pl, sent.strip()[:300]))
    return out

GENERIC = re.compile(rf"\b(?i:forces|troops|fighters|militants|rebels|army|militia|insurgents|jihadists)\b[^.;]{{0,50}}?\b{GAIN}\s+{PLACE}")

# ---------------------------------------------------------------- sources
def bing(query, max_items=40):
    url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "rss", "qft": 'interval="7"', "setlang": "en-US", "cc": "US"})
    xml = T.http_get(url, accept="application/rss+xml").decode("utf-8", "replace")
    def tag(it, t):
        m = re.search(rf"<{t}[^>]*>([\s\S]*?)</{t}>", it)
        v = m.group(1) if m else ""
        return re.sub(r"^<!\[CDATA\[|\]\]>$", "", v).replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">").strip()
    items = []
    for m in list(re.finditer(r"<item>([\s\S]*?)</item>", xml))[:max_items]:
        it = m.group(1); link = tag(it, "link")
        real = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [None])[0] or link
        try: date = dt.datetime.strptime(tag(it, "pubDate"), "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc).isoformat()
        except Exception: date = None
        items.append({"title": tag(it, "title"), "summary": tag(it, "description"), "url": real, "date": date,
                      "outlet": tag(it, "News:Source") or (urllib.parse.urlparse(real).hostname or "").replace("www.", "")})
    return items

def outlet_key(name, url):
    host = (urllib.parse.urlparse(url).hostname or "").replace("www.", "")
    return (name or host).strip().lower(), host

def is_partisan(war, outlet, host):
    p = [x.lower() for x in war.get("partisan", [])]
    return outlet.lower() in p or any(host.endswith(x) for x in p if "." in x)

# ---------------------------------------------------------------- main
def run(args):
    cfg = load(HERE / "wars.json", {"wars": []})
    state = load(HERE / "frontline_state.json", {"reports": []})
    gcache = load(CACHE / "places.json", {})
    sources = load(HERE / "news_sources.json", {"outlets": []})
    camp_of = {o["name"].lower(): o["camp"] for o in sources["outlets"]}

    # 1. articles: the regular feeds plus per-war searches
    arts = []
    if not args.offline:
        class A: input = None; max_items = 80; hours = 48
        feed_arts, _ = N.gather(sources, A)
        arts += [{"title": a["title"], "summary": a["summary"], "url": a["url"], "date": a["date"], "outlet": a["outlet"], "via": "feed"} for a in feed_arts]
        for war in cfg["wars"]:
            for q in war.get("queries", []):
                try: arts += [dict(x, via="bing", war=war["id"]) for x in bing(q)]
                except Exception as e: print(f"  ! bing '{q}': {e}", file=sys.stderr)
    print(f"  {len(arts)} articles to scan")

    seen = {r["url"] + "|" + r["place"] for r in state["reports"]}
    new = 0
    for a in arts:
        text = (a["title"] or "") + ". " + re.sub(r"<[^>]+>", " ", a["summary"] or "")
        for war in cfg["wars"]:
            for side, place, sent in claims_in(text, war):
                k = a["url"] + "|" + place
                if k in seen: continue
                try: hit = resolve(place, text, war, gcache, args.offline)
                except Exception as e: print(f"  ! resolve {place}: {e}", file=sys.stderr); continue
                if not hit: continue
                iso, lvl, d = hit
                outlet, host = outlet_key(a["outlet"], a["url"])
                state["reports"].append({"war": war["id"], "side": side, "place": place, "iso": iso, "lvl": lvl,
                    "district": d["properties"].get("shapeName"), "district_id": d["properties"].get("shapeID"),
                    "outlet": a["outlet"], "host": host, "camp": camp_of.get(outlet, ""), "partisan": is_partisan(war, a["outlet"], host),
                    "title": a["title"][:200], "sentence": sent, "url": a["url"], "date": a.get("date") or NOW.isoformat(), "seen": NOW.isoformat()})
                seen.add(k); new += 1
    # forget reports older than the window
    cutoff = NOW - dt.timedelta(days=cfg.get("window_days", 30))
    def when(r):
        try: return dt.datetime.fromisoformat(r["date"].replace("Z", "+00:00"))
        except Exception: return NOW
    state["reports"] = [r for r in state["reports"] if when(r) >= cutoff]
    print(f"  {new} new ground-control reports, {len(state['reports'])} in the last {cfg.get('window_days', 30)} days")

    # 2. districts with enough independent reports
    out_wars = []
    for war in cfg["wars"]:
        by = collections.defaultdict(list)
        for r in state["reports"]:
            if r["war"] == war["id"]: by[(r["iso"], r["lvl"], r["district_id"])].append(r)
        contested = []
        for (iso, lvl, did), rs in by.items():
            outlets = {r["outlet"].lower() for r in rs}
            neutral = {r["outlet"].lower() for r in rs if not r["partisan"]}
            if len(outlets) < cfg.get("min_outlets", 3) or not neutral: continue
            feat = next((f for f in boundaries(iso, lvl) if f["properties"].get("shapeID") == did), None)
            if not feat: continue
            sides = collections.Counter(r["side"] for r in rs)
            rs.sort(key=when, reverse=True)
            one = {}
            for r in rs: one.setdefault(r["outlet"].lower(), r)          # one report per outlet
            contested.append({"type": "Feature", "geometry": feat["geometry"], "properties": {
                "war": war["id"], "district": feat["properties"].get("shapeName"), "iso": iso, "level": lvl,
                "places": sorted({r["place"] for r in rs}), "advancing": [{"side": s, "reports": n} for s, n in sides.most_common()],
                "outlets": len(outlets), "first": min(when(r) for r in rs).date().isoformat(), "last": max(when(r) for r in rs).date().isoformat(),
                "reports": [{k: r[k] for k in ("outlet", "side", "place", "title", "url", "date", "partisan")} for r in list(one.values())[:8]]}})
        out_wars.append({k: war.get(k) for k in ("id", "name", "since", "reference", "countries")} | {"sides": list(war["sides"]), "districts": len(contested), "features": contested})
        print(f"  {war['name']}: {len(contested)} contested districts")

    # 3. other fighting in the news (candidates, not mapped)
    tracked = {iso for w in cfg["wars"] for iso in w["countries"]}
    week = NOW - dt.timedelta(days=7)
    cand = collections.defaultdict(lambda: {"outlets": set(), "examples": []})
    for a in arts:
        if a.get("via") != "feed": continue
        text = a["title"] + ". " + re.sub(r"<[^>]+>", " ", a["summary"] or "")
        if NOT_GROUND.search(a["title"]) or not GENERIC.search(text): continue
        for iso in set(N.countries_in(text)) - tracked:
            c = cand[iso]; c["outlets"].add(a["outlet"])
            if len(c["examples"]) < 3: c["examples"].append({"outlet": a["outlet"], "title": a["title"][:200], "url": a["url"]})
    prev = {c["iso"]: c for c in state.get("candidates", [])}
    candidates = []
    for iso, c in cand.items():
        p = prev.get(iso, {})
        outlets = sorted(set(c["outlets"]) | set(p.get("outlets", [])))
        candidates.append({"iso": iso, "outlets": outlets, "examples": (c["examples"] + p.get("examples", []))[:3], "last": NOW.date().isoformat()})
    for iso, p in prev.items():
        if iso not in cand and p.get("last", "") >= week.date().isoformat(): candidates.append(p)
    state["candidates"] = candidates
    shown = sorted([c for c in candidates if len(c["outlets"]) >= cfg.get("min_outlets", 3)], key=lambda c: -len(c["outlets"]))

    save(HERE / "frontline_state.json", state)
    save(CACHE / "places.json", gcache)
    doc = {"generated": NOW.isoformat(), "min_outlets": cfg.get("min_outlets", 3), "window_days": cfg.get("window_days", 30), "wars": out_wars, "other_fighting": shown}
    T.write_text_atomic(Path(args.js_out), "// written by frontline.py, loaded automatically by commandcenter-map.html\nwindow.CC_FRONTLINE = "
                        + json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"wrote {args.js_out}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--js-out", default=str(HERE.parent / "data" / "frontline.js"))
    ap.add_argument("--offline", action="store_true")
    run(ap.parse_args())

if __name__ == "__main__":
    main()
