#!/usr/bin/env python3
"""
CommandCenter war tracker: marks the provinces where an active war is being fought, and names the sides.

For each war in wars.json, once a day:
  1. Start from the war's front-line provinces listed in wars.json ("front", with the date and sources they were
     checked against). Provinces firmly held by one side ("held", e.g. Sanaa, Crimea) are never marked.
  2. Read the news feeds in news_sources.json plus a few Bing News searches per war, and keep sentences that name
     a side and report ground fighting (clashes, battles, assaults, advances, captures). Air, drone, missile and
     shelling reports don't count. Each place named is found on Wikidata and assigned to its province
     (geoBoundaries); ambiguous names are dropped.
  3. A province not on the front list is added when 3+ different outlets report ground fighting there within the
     window (default 14 days), at least one not run by a party to the war.
Writes ../data/frontline.js (window.CC_FRONTLINE): province outlines, the belligerents and the reports behind each.
Reports are kept in frontline_state.json so evidence builds up over days.

Also lists "other fighting": countries outside the tracked wars where 3+ outlets this week reported ground fighting,
as candidates to add to wars.json. Nothing is mapped for those automatically.

  python frontline.py            # normal daily run
  python frontline.py --offline  # re-use cached feeds/geocodes only (testing)
"""
from __future__ import annotations

import argparse, collections, datetime as dt, json, re, sys, time, unicodedata, urllib.error, urllib.parse
from pathlib import Path

import trawler as T
import news as N

HERE = Path(__file__).resolve().parent
CACHE = HERE / "trawler_cache"
NOW = dt.datetime.now(dt.timezone.utc)
GEO_URL = "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/{iso}/{lvl}/geoBoundaries-{iso}-{lvl}_simplified.geojson"
WD_COUNTRY = {"UKR": "Q212", "RUS": "Q159", "YEM": "Q805", "SYR": "Q858", "SDN": "Q1049", "MMR": "Q836", "ISR": "Q801", "PSE": "Q219060", "LBN": "Q822"}

GAIN = r"(?:captured|seized|took(?: full)? control of|taken(?: full)? control of|gained control of|took|liberated|retook|recaptured|regained(?: control of)?|entered|overran|occupied|pushed into|advanced into|stormed|cleared)"
FIGHT = re.compile(rf"\b(?:clash(?:es|ed)?|fighting|fought|battles?|combat|assaults?|offensive|advanc(?:e|es|ed|ing)|attack(?:s|ed)?|engagements?|repell?ed|repulsed|ambush(?:ed)?|ground (?:operation|attack)s?|front ?lines?|{GAIN})\b", re.I)
AIR = re.compile(r"\b(?:air ?strikes?|drones?|missiles?|shell(?:ed|ing)|bomb(?:ed|ing|s)?|rockets?|UAVs?|Shaheds?|artillery|struck|strikes?)\b", re.I)
HYPO = re.compile(r"\b(?:could|would|might|plans? to|threaten(?:s|ed)? to|aims? to|seeks? to)\b", re.I)
PLACE = r"(?P<place>[A-Z][\w'’\-]+(?:[ \-](?:al-|el-|ad-)?[A-Z][\w'’\-]+){0,2})"
WHERE = re.compile(rf"\b(?:in|near|on|around|outside|toward|towards|into|of|at|from)\s+(?:the\s+)?(?:(?:village|town|city|settlement|district|port|outskirts|area|province|governorate|region|oblast)s?\s+of\s+)?{PLACE}")
# ceasefires: front-wide only. Local, humanitarian, prisoner-exchange, holiday or sector-limited truces don't count.
TRUCE = re.compile(r"\b(?:cease-?fire|truce|armistice|peace (?:deal|agreement|accord)|cessation of hostilities)\b", re.I)
TRUCE_START = re.compile(r"\b(?:takes? effect|took effect|came into (?:force|effect)|comes? into (?:force|effect)|went into effect|goes into effect|"
                         r"entered into force|enters into force|(?:was |were |been )?signed|agreed (?:to )?(?:a|an|the)|declared (?:a|an)|announced (?:a|an)|"
                         r"began|begins|started|is now in (?:force|effect))\b", re.I)
TRUCE_LOCAL = re.compile(r"\b(?:local(?:i[sz]ed)?|humanitarian|pause|prisoners?|POWs?|exchange|swap|Christmas|Easter|Orthodox|Eid|Ramadan|Hanukkah|New Year|holiday|"
                         r"Olympic|energy|infrastructure|power plants?|air|aerial|maritime|naval|Black Sea|sea|partial|limited|\d+[- ]hours?|\d+[- ]day|one-day|"
                         r"evacuat\w*|aid|vaccination|polio|corridor|town|city|village|district|sector|nuclear plant)\b", re.I)
TRUCE_NOT = re.compile(r"\b(?:since|despite|violat\w*|breach\w*|call(?:s|ed)? for|urg\w+|propos\w*|push(?:es|ed)? for|seek\w*|talks?|negotiat\w*|"
                       r"reject\w*|refus\w*|would|could|might|may|hopes?|if|unless|ahead of|prospects?|plan|draft|framework|previous|last year|earlier)\b", re.I)
TRUCE_END = re.compile(r"\b(?:cease-?fire|truce)\b[^.;]{0,40}\b(?:collaps\w+|broke down|breaks? down|has ended|ended|is over|shattered|abandoned)\b|"
                       r"\b(?:resum\w+|renewed) (?:fighting|hostilities|offensive|assaults?|attacks)\b", re.I)

MONTHS = ["january","february","march","april","may","june","july","august","september","october","november","december"]
def old_date(sent):
    """True when the sentence dates the ceasefire to an earlier month or year (a look back, not news of a new one)."""
    recent = {MONTHS[NOW.month - 1]} | ({MONTHS[NOW.month - 2]} if NOW.day <= 7 else set())
    named = {m for m in MONTHS if re.search(rf"\b{m}\b", sent, re.I)} - {"may"} | ({"may"} if re.search(r"\bin May\b|\bMay \d", sent) else set())
    years = {int(y) for y in re.findall(r"\b(20\d\d)\b", sent)}
    return bool(named - recent) or any(y < NOW.year for y in years)

# withdrawals: only complete pull-outs from a whole province or country count, not "withdrew from three villages"
WITHDRAW = re.compile(r"\b(?:complet\w*|finish\w*|full|fully|total|entire|final)\b[^.;]{0,30}\b(?:withdraw\w*|pull-?out|pulled out|pullback)\b|"
                      r"\b(?:withdr(?:ew|awn)|pulled out)\b[^.;]{0,15}\b(?:all (?:its|their) (?:troops|forces)|(?:its|their) last (?:troops|forces|positions)|completely|fully)\b", re.I)
WITHDRAW_NOT = re.compile(r"\b(?:will|would|could|must|should|agree\w* to|plans?|planned|deadline|demand\w*|calls? for|urg\w+|expected|due to|refus\w*|delay\w*|"
                          r"reject\w*|denied|partial|some|several|positions? near|villages?|if|unless|before|after (?:a|the) (?:deal|agreement) is)\b", re.I)
WITHDRAW_FROM = re.compile(r"\bfrom\s+(?:the\s+)?(?:(?:southern|northern|eastern|western|south|north|east|west|occupied)\s+)?(?P<place>[A-Z][\w'’\-]+(?:[ \-][A-Z][\w'’\-]+){0,2})")
COUNTRY_NAMES = {"UKR": ["Ukraine"], "RUS": ["Russia"], "LBN": ["Lebanon"], "PSE": ["Gaza", "Gaza Strip"], "YEM": ["Yemen"], "SDN": ["Sudan"],
                 "MMR": ["Myanmar", "Burma"], "COD": ["Congo", "DR Congo", "DRC"], "SYR": ["Syria"]}

def withdrawals_in(text, war, gcache, offline):
    """[(iso, province or '*', sentence)]: complete withdrawals from a whole province ('*' = every held province in that country)."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\s+[-–—|]\s+", text):
        if len(sent) < 15 or not WITHDRAW.search(sent) or WITHDRAW_NOT.search(sent) or old_date(sent): continue
        for m in WITHDRAW_FROM.finditer(sent):
            pl = m.group("place").strip(" '’-")
            iso = next((i for i in war["countries"] if pl in COUNTRY_NAMES.get(i, [])), None)
            if iso and not provinces(iso).get(REGION_ALIASES.get(norm(pl), norm(pl))):
                out.append((iso, "*", sent.strip()[:300])); continue
            for i in war["countries"]:
                f = provinces(i).get(REGION_ALIASES.get(norm(pl), norm(pl)))
                if f: out.append((i, f["properties"]["shapeName"], sent.strip()[:300])); break
    return out

def withdrawal_status(war, state, cfg):
    """{(iso, province|'*'): {status, since, outlets, reports}} for complete withdrawals reported by 3+ outlets (1+ independent);
    'verified' once held `ceasefire_hold_days` with no renewed ground fighting there reported by 3+ outlets."""
    need = cfg.get("min_outlets", 3); hold = cfg.get("ceasefire_hold_days", 4)
    by = collections.defaultdict(list)
    for r in state.get("withdrawals", []):
        if r["war"] == war["id"]: by[(r["iso"], r["province"])].append(r)
    out = {}
    for key, rs in by.items():
        rs.sort(key=when)
        outs = {r["outlet"].lower() for r in rs}
        if len(outs) < need or all(r["partisan"] for r in rs): continue
        since = when(rs[0])
        fights = {r["outlet"].lower() for r in state["reports"] if r["war"] == war["id"] and r["iso"] == key[0]
                  and (key[1] == "*" or norm(r["province"]) == norm(key[1])) and when(r) > since + dt.timedelta(days=1)}
        if len(fights) >= need: continue
        one = {}
        for r in rs: one.setdefault(r["outlet"].lower(), r)
        out[key] = {"status": "verified" if NOW - since >= dt.timedelta(days=hold) else "reported", "since": since.date().isoformat(),
                    "outlets": len(outs), "reports": [{k: r[k] for k in ("outlet", "title", "url", "date")} for r in list(one.values())[:4]]}
    return out

def truce_in(text, war):
    """('start'|'end', sentence) for front-wide ceasefire news about this war."""
    names = re.compile("|".join(re.escape(w) for ws in war["sides"].values() for w in ws) + "|" + "|".join(re.escape(n) for n in war.get("names", [])))
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\s+[-–—|]\s+", text):
        if len(sent) < 15 or not names.search(sent): continue
        if TRUCE_END.search(sent): out.append(("end", sent.strip()[:300])); continue
        if TRUCE.search(sent) and TRUCE_START.search(sent) and not TRUCE_LOCAL.search(sent) and not TRUCE_NOT.search(sent) and not old_date(sent):
            out.append(("start", sent.strip()[:300]))
    return out

TAKEN = re.compile(rf"\b{GAIN}\s+(?:the\s+)?(?:(?:village|town|city|settlement|district|port)\s+of\s+)?{PLACE}")
STOP = {"Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday","January","February","March","April","May","June","July","August",
        "September","October","November","December","The","A","An","Control","Positions","Territory","Ground","Part","Parts","Areas","Area",
        "Defense Forces","Defence Forces","General Staff","Armed Forces","Red Sea","Gulf","Europe","West","East","North","South","UN","US","EU","NATO"}


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

def _dp(pts, tol):
    """Douglas-Peucker line simplification (degrees)."""
    if len(pts) < 3: return pts
    (x1, y1), (x2, y2) = pts[0][:2], pts[-1][:2]
    dx, dy = x2 - x1, y2 - y1; n = (dx * dx + dy * dy) ** .5 or 1e-12
    i, dmax = 0, 0
    for k in range(1, len(pts) - 1):
        d = abs(dy * pts[k][0] - dx * pts[k][1] + x2 * y1 - y2 * x1) / n
        if d > dmax: i, dmax = k, d
    if dmax <= tol: return [pts[0], pts[-1]]
    return _dp(pts[:i + 1], tol)[:-1] + _dp(pts[i:], tol)

def light(geom, tol=0.02):
    """A smaller copy of a polygon for the map: simplified rings, 3-decimal coordinates, tiny islands dropped."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    out = []
    for poly in polys:
        rings = []
        for r in poly:
            far = max(range(len(r)), key=lambda k: (r[k][0] - r[0][0]) ** 2 + (r[k][1] - r[0][1]) ** 2)   # closed ring: split in two
            simple = _dp(r[:far + 1], tol)[:-1] + _dp(r[far:], tol)
            rr = [[round(x, 3), round(y, 3)] for x, y in (pt[:2] for pt in simple)]
            if len(rr) >= 4: rings.append(rr)
        if rings: out.append(rings)
    if not out: return geom
    return {"type": "MultiPolygon", "coordinates": out}

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

# common English spellings of first-level regions ("Donetsk region", "Taiz", "Hodeidah")
REGION_ALIASES = {"nabatieh": "nabatiye", "nabatiyeh": "nabatiye", "nabatieh governorate": "nabatiye", "zaporizhzhia": "zaporizhia", "zaporozhye": "zaporizhia", "hodeidah": "hudaydah", "hudaydah": "hudaydah", "taiz": "taizz",
                  "marib": "marib", "maarib": "marib", "maareb": "marib", "sanaa": "sana", "aden": "adan", "lahj": "lahij", "hadramout": "hadhramaut",
                  "hadramawt": "hadhramaut", "dhale": "dali", "dhalea": "dali", "daleh": "dali", "bayda": "bayda", "baydha": "bayda", "jouf": "jawf",
                  "saada": "sadah", "amran": "amran", "kharkov": "kharkiv", "odesa": "odessa", "lugansk": "luhansk", "dnipro": "dnipropetrovsk"}

def provinces(iso):
    return {REGION_ALIASES.get(norm(f["properties"]["shapeName"]), norm(f["properties"]["shapeName"])): f for f in boundaries(iso, "ADM1")}

def province_at(iso, lon, lat):
    return next((f for f in boundaries(iso, "ADM1") if contains(f["geometry"], lon, lat)), None)

def resolve(place, text, war, gcache, offline):
    """The province (iso, feature) where `place` is, or None when it can't be told apart from other places of that name."""
    key = REGION_ALIASES.get(norm(place), norm(place))
    for iso in war["countries"]:                       # 1. the place is itself a province ("Taiz", "Donetsk region")
        f = provinces(iso).get(key)
        if f: return iso, f
    spots = []                                         # 2. a settlement: Wikidata coordinates -> province
    for g in geocode(place, list(war["countries"]), gcache, offline):
        f = province_at(g["iso"], g["lon"], g["lat"])
        if f: spots.append((g["iso"], f))
    if not spots: return None
    ids = {f["properties"]["shapeID"] for _, f in spots}
    if len(ids) > 1:                                   # several places of that name: use a province named in the text
        named = {REGION_ALIASES.get(norm(w), norm(w)) for w in re.findall(r"[A-Z][\w'’\-]+", text)}
        spots = [(i, f) for i, f in spots if REGION_ALIASES.get(norm(f["properties"]["shapeName"]), norm(f["properties"]["shapeName"])) in named]
        if len({f["properties"]["shapeID"] for _, f in spots}) != 1: return None
    return spots[0]

# ---------------------------------------------------------------- extraction
def side_pattern(words):
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b")

def fighting_in(text, war):
    """[(sides, place, sentence)]: places named in sentences that report ground fighting between this war's sides."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\s+[-–—|]\s+", text):
        if len(sent) < 15 or HYPO.search(sent): continue
        sides = [s for s, words in war["sides"].items() if side_pattern(words).search(sent)]
        if not sides or not FIGHT.search(sent): continue
        if AIR.search(sent) and not re.search(rf"\b(?:clash(?:es|ed)?|fighting|battles?|assaults?|ground|{GAIN})\b", sent, re.I): continue
        words = {w for ws in war["sides"].values() for w in ws}
        for m in [*WHERE.finditer(sent), *TAKEN.finditer(sent)]:
            pl = re.sub(r"(?:'s|’s)$", "", m.group("place").strip(" '’-"))
            if pl in STOP or pl in words or any(pl.startswith(w + " ") for w in words): continue
            out.append((sides, pl, sent.strip()[:300]))
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
def when(r):
    try: return dt.datetime.fromisoformat(r["date"].replace("Z", "+00:00"))
    except Exception: return NOW

def ceasefire_status(war, state, cfg):
    """None, or {status: 'reported'|'verified', since, verify_by, outlets, reports}.
    Reported: 3+ outlets (1+ not run by a party to the war) report a front-wide ceasefire taking effect, within 7 days of each other.
    Verified: it has then held for `ceasefire_hold_days` (default 4) with no collapse reported by 3+ outlets and no renewed
    ground fighting reported by 3+ outlets. A later collapse or renewed fighting puts the shading back."""
    need = cfg.get("min_outlets", 3); hold = cfg.get("ceasefire_hold_days", 4)
    rs = sorted((r for r in state.get("truce", []) if r["war"] == war["id"]), key=when)
    starts = [r for r in rs if r["kind"] == "start"]
    best = None
    for i, r in enumerate(starts):                       # earliest 7-day window with enough independent outlets
        win = [x for x in starts[i:] if when(x) - when(r) <= dt.timedelta(days=7)]
        outs = {x["outlet"].lower() for x in win}
        if len(outs) >= need and any(not x["partisan"] for x in win): best = (r, win, outs)
    if not best: return None
    first, win, outs = best
    since = when(first)
    ends = {r["outlet"].lower() for r in rs if r["kind"] == "end" and when(r) > since}
    fights = {r["outlet"].lower() for r in state["reports"] if r["war"] == war["id"] and when(r) > since + dt.timedelta(days=1)}
    if len(ends) >= need or len(fights) >= need: return None          # broke down: keep shading
    one = {}
    for r in win: one.setdefault(r["outlet"].lower(), r)
    return {"status": "verified" if NOW - since >= dt.timedelta(days=hold) else "reported",
            "since": since.date().isoformat(), "verify_by": (since + dt.timedelta(days=hold)).date().isoformat(), "outlets": len(outs),
            "reports": [{k: r[k] for k in ("outlet", "title", "url", "date", "partisan")} for r in list(one.values())[:6]]}

def run(args):
    cfg = load(HERE / "wars.json", {"wars": []})
    state = load(HERE / "frontline_state.json", {"reports": []})
    if state["reports"] and "province" not in state["reports"][0]: state["reports"] = []    # old district-level format
    gcache = load(CACHE / "places.json", {})
    sources = load(HERE / "news_sources.json", {"outlets": []})
    window = cfg.get("window_days", 14)

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

    seen = {r["url"] + "|" + r["province"] for r in state["reports"]} | {r["url"] + "|truce" for r in state.get("truce", [])} \
           | {r["url"] + "|wd|" + r["province"] for r in state.get("withdrawals", [])}
    new = 0
    for a in arts:
        text = (a["title"] or "") + ". " + re.sub(r"<[^>]+>", " ", a["summary"] or "")
        for war in cfg["wars"]:
            if war.get("ceasefire_check", True):
                for kind, sent in truce_in(text, war):
                    k = a["url"] + "|truce"
                    if k in seen: continue
                    outlet, host = outlet_key(a["outlet"], a["url"])
                    state.setdefault("truce", []).append({"war": war["id"], "kind": kind, "outlet": a["outlet"], "partisan": is_partisan(war, a["outlet"], host),
                        "title": a["title"][:200], "sentence": sent, "url": a["url"], "date": a.get("date") or NOW.isoformat()})
                    seen.add(k)
            if war.get("after_ceasefire"):
                for iso, prov, sent in withdrawals_in(text, war, gcache, args.offline):
                    k = a["url"] + "|wd|" + prov
                    if k in seen: continue
                    outlet, host = outlet_key(a["outlet"], a["url"])
                    state.setdefault("withdrawals", []).append({"war": war["id"], "iso": iso, "province": prov, "outlet": a["outlet"],
                        "partisan": is_partisan(war, a["outlet"], host), "title": a["title"][:200], "sentence": sent, "url": a["url"],
                        "date": a.get("date") or NOW.isoformat()})
                    seen.add(k)
            for sides, place, sent in fighting_in(text, war):
                try: hit = resolve(place, text, war, gcache, args.offline)
                except Exception as e: print(f"  ! resolve {place}: {e}", file=sys.stderr); continue
                if not hit: continue
                iso, f = hit
                prov = f["properties"]["shapeName"]
                k = a["url"] + "|" + prov
                if k in seen: continue
                outlet, host = outlet_key(a["outlet"], a["url"])
                state["reports"].append({"war": war["id"], "sides": sides, "place": place, "iso": iso, "province": prov,
                    "province_id": f["properties"].get("shapeID"), "outlet": a["outlet"], "host": host,
                    "partisan": is_partisan(war, a["outlet"], host), "title": a["title"][:200], "sentence": sent,
                    "url": a["url"], "date": a.get("date") or NOW.isoformat(), "seen": NOW.isoformat()})
                seen.add(k); new += 1
    cutoff = NOW - dt.timedelta(days=max(window, 30))
    state["reports"] = [r for r in state["reports"] if when(r) >= cutoff]
    state["truce"] = [r for r in state.get("truce", []) if when(r) >= NOW - dt.timedelta(days=60)]
    state["withdrawals"] = [r for r in state.get("withdrawals", []) if when(r) >= NOW - dt.timedelta(days=365)]
    print(f"  {new} new fighting reports, {len(state['reports'])} kept")

    # 2. provinces: the listed front, plus provinces with enough independent reports; never the firmly held ones
    recent = NOW - dt.timedelta(days=window)
    out_wars = []
    for war in cfg["wars"]:
        held = {(iso, norm(p)) for iso, ps in war.get("held", {}).items() for p in ps}
        front = {(iso, norm(p)) for iso, ps in war.get("front", {}).items() for p in ps}
        by = collections.defaultdict(list)
        for r in state["reports"]:
            if r["war"] == war["id"] and when(r) >= recent: by[(r["iso"], norm(r["province"]))].append(r)
        cf = ceasefire_status(war, state, cfg)
        wd = withdrawal_status(war, state, cfg)
        gone = {(iso, norm(p)) for (iso, p), v in wd.items() if v["status"] == "verified" and p != "*"}
        gone_all = {iso for (iso, p), v in wd.items() if v["status"] == "verified" and p == "*"}
        feats = []
        if cf and cf["status"] == "verified":           # under a verified ceasefire: keep only provinces still (partly) held by the other side
            after = war.get("after_ceasefire", {})
            for iso, ps in after.get("provinces", {}).items():
                keep = {norm(x) for x in ps}
                for f in boundaries(iso, "ADM1"):
                    if norm(f["properties"]["shapeName"]) in keep and iso not in gone_all and (iso, norm(f["properties"]["shapeName"])) not in gone:
                        feats.append({"type": "Feature", "geometry": light(f["geometry"]), "properties": {
                            "war": war["id"], "province": f["properties"]["shapeName"], "iso": iso, "basis": "ceasefire",
                            "label": after.get("label", ""), "outlets": 0, "places": [], "last": None, "reports": []}})
        for iso in (war["countries"] if not (cf and cf["status"] == "verified") else []):
            for f in boundaries(iso, "ADM1"):
                key = (iso, norm(f["properties"]["shapeName"]))
                if key in held: continue
                rs = sorted(by.get(key, []), key=when, reverse=True)
                outlets = {r["outlet"].lower() for r in rs}
                by_news = len(outlets) >= cfg.get("min_outlets", 3) and any(not r["partisan"] for r in rs)
                if key not in front and not by_news: continue
                one = {}
                for r in rs: one.setdefault(r["outlet"].lower(), r)
                feats.append({"type": "Feature", "geometry": light(f["geometry"]), "properties": {
                    "war": war["id"], "province": f["properties"]["shapeName"], "iso": iso,
                    "basis": "front" if key in front else "news", "outlets": len(outlets),
                    "places": sorted({r["place"] for r in rs})[:8], "last": rs[0]["date"][:10] if rs else None,
                    "reports": [{k: r[k] for k in ("outlet", "place", "title", "url", "date", "partisan")} for r in list(one.values())[:6]]}})
        out_wars.append({k: war.get(k) for k in ("id", "name", "since", "trackers", "note", "belligerents", "front_as_of", "front_sources")}
                        | {"held": war.get("held", {}), "provinces": len(feats), "features": feats, "ceasefire": cf,
                           "withdrawals": [dict(v, iso=iso, province=(p if p != "*" else None)) for (iso, p), v in wd.items()]})
        if cf: print(f"  {war['name']}: ceasefire {cf['status']} (since {cf['since']}, {cf['outlets']} outlets)")
        print(f"  {war['name']}: {len(feats)} provinces ({sum(f['properties']['basis'] == 'news' for f in feats)} from news)")

    # 3. other fighting in the news (candidates, not mapped)
    tracked = {iso for w in cfg["wars"] for iso in w["countries"]}
    week = NOW - dt.timedelta(days=7)
    cand = collections.defaultdict(lambda: {"outlets": set(), "examples": []})
    for a in arts:
        if a.get("via") != "feed": continue
        text = a["title"] + ". " + re.sub(r"<[^>]+>", " ", a["summary"] or "")
        if AIR.search(a["title"]) or HYPO.search(a["title"]) or not GENERIC.search(text): continue
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
    doc = {"generated": NOW.isoformat(), "min_outlets": cfg.get("min_outlets", 3), "window_days": window, "wars": out_wars, "other_fighting": shown}
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
