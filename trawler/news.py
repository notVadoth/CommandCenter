#!/usr/bin/env python3
"""
CommandCenter headline builder: free, with no AI or API keys.

Once a day:
  1. Focus countries = 20 largest by population, plus 20 largest by GDP (World Bank).
  2. Pull RSS headlines from news_sources.json (each outlet tagged with a "camp").
  3. Tag each headline with the countries it mentions.
  4. Group headlines about the same event (TF-IDF text similarity, plus a shared country).
  5. Stories about multilateral bodies / summits (EU, NATO, BRICS, G7, G20, UN, ...) go to
     a "Global diplomacy" section instead of a country.
  6. For each story, pick up to 3 outlets from DIFFERENT camps, preferring the camps of
     the countries involved plus a UN/multilateral source. For sides with no coverage,
     add a "search this outlet" link instead of making something up.
  7. Write ../data/stories.js, which the map's headline panel loads automatically.

The map shows only headlines and links, so nothing is summarised or rewritten.

  python news.py                 # normal daily run
  python news.py --input feeds/  # use saved RSS/XML files instead (testing)
"""
from __future__ import annotations

import argparse, collections, datetime as dt, json, math, re, sys, urllib.parse
from pathlib import Path

import trawler as T   # reuse feed reading, country names and safe file writing

HERE = Path(__file__).resolve().parent
NOW = dt.datetime.now(dt.timezone.utc)

# Extra names the country list lacks: demonyms, capitals, common places
EXTRA_PLACES = {
    "Russian": "RUS", "Kremlin": "RUS", "Moscow": "RUS", "Putin": "RUS",
    "Ukrainian": "UKR", "Kyiv": "UKR", "Kiev": "UKR", "Zelensky": "UKR", "Zelenskyy": "UKR", "Donbas": "UKR", "Kharkiv": "UKR", "Odesa": "UKR", "Crimea": "UKR",
    "Chinese": "CHN", "Beijing": "CHN", "Xi Jinping": "CHN", "Taiwanese": "TWN", "Taipei": "TWN",
    "American": "USA", "Washington": "USA", "White House": "USA", "Pentagon": "USA", "Trump": "USA",
    "British": "GBR", "London": "GBR", "French": "FRA", "Paris": "FRA", "German": "DEU", "Berlin": "DEU",
    "Israeli": "ISR", "Jerusalem": "ISR", "Netanyahu": "ISR", "IDF": "ISR",
    "Palestinian": "PSE", "Gaza": "PSE", "West Bank": "PSE", "Hamas": "PSE",
    "Iranian": "IRN", "Tehran": "IRN", "Lebanese": "LBN", "Hezbollah": "LBN", "Beirut": "LBN",
    "Syrian": "SYR", "Damascus": "SYR", "Yemeni": "YEM", "Houthi": "YEM", "Houthis": "YEM",
    "Saudi": "SAU", "Riyadh": "SAU", "Qatari": "QAT", "Doha": "QAT", "Emirati": "ARE", "Egyptian": "EGY", "Cairo": "EGY",
    "Turkish": "TUR", "Ankara": "TUR", "Erdogan": "TUR", "Iraqi": "IRQ", "Baghdad": "IRQ",
    "Indian": "IND", "New Delhi": "IND", "Delhi": "IND", "Modi": "IND", "Pakistani": "PAK", "Islamabad": "PAK",
    "Afghan": "AFG", "Taliban": "AFG", "Kabul": "AFG", "Bangladeshi": "BGD", "Dhaka": "BGD",
    "Japanese": "JPN", "Tokyo": "JPN", "South Korean": "KOR", "Seoul": "KOR", "North Korean": "PRK", "Pyongyang": "PRK",
    "Indonesian": "IDN", "Jakarta": "IDN", "Philippine": "PHL", "Filipino": "PHL", "Manila": "PHL", "Vietnamese": "VNM", "Hanoi": "VNM",
    "Thai": "THA", "Bangkok": "THA", "Burmese": "MMR", "Myanmar": "MMR",
    "Nigerian": "NGA", "Abuja": "NGA", "Lagos": "NGA", "Ethiopian": "ETH", "Addis Ababa": "ETH", "Kenyan": "KEN", "Nairobi": "KEN",
    "Sudanese": "SDN", "Khartoum": "SDN", "Darfur": "SDN", "RSF": "SDN", "Congolese": "COD", "Kinshasa": "COD", "Goma": "COD", "M23": "COD",
    "Somali": "SOM", "Mogadishu": "SOM", "South African": "ZAF", "Pretoria": "ZAF", "Johannesburg": "ZAF",
    "Malian": "MLI", "Bamako": "MLI", "Burkinabe": "BFA",
    "Brazilian": "BRA", "Brasilia": "BRA", "Lula": "BRA", "Mexican": "MEX", "Mexico City": "MEX", "Argentine": "ARG", "Buenos Aires": "ARG",
    "Venezuelan": "VEN", "Caracas": "VEN", "Colombian": "COL", "Bogota": "COL", "Cuban": "CUB", "Havana": "CUB", "Haitian": "HTI",
    "Canadian": "CAN", "Ottawa": "CAN", "Australian": "AUS", "Canberra": "AUS", "Italian": "ITA", "Rome": "ITA", "Spanish": "ESP", "Madrid": "ESP",
    "Polish": "POL", "Warsaw": "POL", "Belarusian": "BLR", "Minsk": "BLR", "Georgian": "GEO", "Tbilisi": "GEO",
    "Armenian": "ARM", "Yerevan": "ARM", "Azerbaijani": "AZE", "Baku": "AZE", "Serbian": "SRB", "Belgrade": "SRB",
    "Dutch": "NLD", "Swiss": "CHE", "Swedish": "SWE", "Norwegian": "NOR", "Finnish": "FIN", "Danish": "DNK", "Greek": "GRC", "Hungarian": "HUN", "Romanian": "ROU",
}
PLACES = {**T.COUNTRIES, **EXTRA_PLACES}
PLACE_RE = re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in sorted(PLACES, key=len, reverse=True)) + r")(?![\w])")

# Multilateral bodies and summits, used for the "Global diplomacy" section
BODIES = [
    ("EU", r"\bEU\b|European Union|European Commission|European Council|Brussels summit|von der Leyen"),
    ("NATO", r"\bNATO\b"), ("BRICS", r"\bBRICS\b"), ("G7", r"\bG7\b|\bG-7\b"), ("G20", r"\bG20\b|\bG-20\b"),
    ("UN", r"UN General Assembly|\bUNGA\b|Security Council|\bUN chief\b|Guterres|United Nations summit"),
    ("ASEAN", r"\bASEAN\b"), ("SCO", r"Shanghai Cooperation|\bSCO\b"), ("AU", r"African Union"),
    ("OPEC", r"\bOPEC\+?"), ("COP", r"\bCOP ?\d\d\b|climate summit"), ("APEC", r"\bAPEC\b"),
    ("Quad", r"\bQuad\b(?= (summit|leaders|foreign))"), ("Arab League", r"Arab League"), ("GCC", r"\bGCC\b|Gulf Cooperation Council"),
    ("WTO", r"\bWTO\b"), ("IMF", r"\bIMF\b"), ("Summit", r"\bsummit\b|foreign ministers'? (meeting|talks)|state visit"),
]
BODY_RE = [(lbl, re.compile(rx, re.I if lbl in ("Summit","UN","COP") else 0)) for lbl, rx in BODIES]
def bodies_in(text: str) -> list[str]:
    return [lbl for lbl, rx in BODY_RE if rx.search(text)]

FALLBACK_FOCUS = "CHN IND USA IDN PAK NGA BRA BGD RUS ETH MEX JPN EGY PHL COD VNM IRN TUR DEU THA GBR FRA ITA CAN KOR AUS ESP NLD SAU CHE".split()

STOP = set("""a an the and or but of to in on at for from by with as is are was were be been being has have had it its this that these those
over after before amid into about against says said say new latest live update updates report reports news video watch how why what who
will would could may might can more than up down out off not no yes his her their our your they he she we you us them him
first last year years day days week weeks month months today yesterday tomorrow two three four five one""".split())

PLACE_WORDS = {w.lower() for name in PLACES for w in name.split()}

def tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", text)
    title_case = sum(w[0].isupper() for w in words) > 0.6 * max(1, len(words))   # "Russia Attacks Kharkiv" style headlines
    out = []
    for i, w in enumerate(words):
        lw = w.lower().strip("'-")
        if lw in STOP: continue
        if lw.endswith("'s"): lw = lw[:-2]
        if len(lw) > 4 and lw.endswith("s") and not lw.endswith("ss"): lw = lw[:-1]
        proper = lw in PLACE_WORDS or (w[0].isupper() and i > 0 and not title_case)
        out.append(("^" + lw) if proper else lw)   # names and places weigh more
    return out

def countries_in(text: str) -> collections.Counter:
    return collections.Counter(PLACES[m.group(1)] for m in PLACE_RE.finditer(text))

# --------------------------------------------------------------------------
def focus_countries(cache: Path) -> list[str]:
    """Top 20 by population, plus top 20 by GDP, from World Bank data (cached for 30 days)."""
    c = T.read_json(cache, None)
    if c and (NOW - dt.datetime.fromisoformat(c["t"])).days < 30: return c["codes"]
    try:
        meta = json.loads(T.http_get("https://api.worldbank.org/v2/country?format=json&per_page=400"))[1]
        real = {m["id"] for m in meta if m.get("region", {}).get("value") != "Aggregates"}
        def top(ind):
            rows = json.loads(T.http_get(f"https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&mrnev=1&per_page=400"))[1]
            rows = [r for r in rows if r.get("value") and r.get("countryiso3code") in real]
            return [r["countryiso3code"] for r in sorted(rows, key=lambda r: -r["value"])[:20]]
        codes = list(dict.fromkeys(top("SP.POP.TOTL") + top("NY.GDP.MKTP.CD")))
        T.write_text_atomic(cache, json.dumps({"t": NOW.isoformat(), "codes": codes}))
        return codes
    except Exception as e:
        print(f"  ! World Bank lookup failed ({e}); using built-in focus list", file=sys.stderr)
        return (c or {}).get("codes") or FALLBACK_FOCUS

def gather(cfg: dict, args) -> tuple[list[dict], list[dict]]:
    arts, status = [], []
    for o in cfg["outlets"]:
        try:
            if args.input:
                f = Path(args.input) / (re.sub(r"\W+", "_", o["name"]).strip("_") + ".xml")
                if not f.exists(): continue
                items = T.read_feed_xml(f.read_bytes(), args.max_items)
            else:
                items = T.read_feed(o["url"], args.max_items)
            n = 0
            for it in items:
                if not it.get("url") or not it.get("title"): continue
                when = it.get("date")
                if when:
                    try:
                        if (NOW - dt.datetime.fromisoformat(when)).total_seconds() > args.hours * 3600: continue
                    except Exception: pass
                arts.append({"outlet": o["name"], "camp": o["camp"], "ownership": o.get("ownership", ""), "domain": o.get("domain", ""),
                             "title": re.sub(r"\s+", " ", it["title"]).strip(), "url": it["url"], "date": when,
                             "summary": (it.get("summary") or "")[:400]})
                n += 1
            status.append({"outlet": o["name"], "ok": True, "items": n})
        except Exception as e:
            status.append({"outlet": o["name"], "ok": False, "error": str(e)[:120]})
            print(f"  ! {o['name']}: {e}", file=sys.stderr)
    return arts, status

def cluster(arts: list[dict], threshold: float) -> list[list[dict]]:
    docs = []
    for a in arts:
        toks = tokens(a["title"]) * 2 + tokens(a["summary"][:240])
        a["_tf"] = collections.Counter(toks)
        a["_c"] = countries_in(a["title"]) + countries_in(a["summary"][:240])
        docs.append(a)
    df = collections.Counter(t for a in docs for t in a["_tf"])
    N = max(1, len(docs))
    for a in docs:
        v = {t: (1 + math.log(c)) * math.log(1 + N / df[t]) * (1.6 if t.startswith("^") else 1.0) for t, c in a["_tf"].items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        a["_v"] = {t: x / norm for t, x in v.items()}
    # single-link grouping: join the story containing the most similar headline
    clusters: list[dict] = []
    for a in sorted(docs, key=lambda a: a.get("date") or "", reverse=True):
        best, bs, bshare = None, 0.0, set()
        for c in clusters:
            if a["_c"] and c["countries"] and not (set(a["_c"]) & set(c["countries"])): continue
            for m in c["items"]:
                sim = sum(x * m["_v"].get(t, 0.0) for t, x in a["_v"].items())
                if sim > bs: best, bs, bshare = c, sim, set(a["_tf"]) & set(m["_tf"])
        names = {t for t in bshare if t.startswith("^")}
        if best and (bs >= threshold or (bs >= threshold * 0.55 and names and len(bshare) >= 3)):
            best["items"].append(a); best["outlets"].add(a["outlet"]); best["countries"].update(a["_c"])
        else:
            clusters.append({"items": [a], "outlets": {a["outlet"]}, "countries": collections.Counter(a["_c"])})
    return [c["items"] for c in clusters]

def pick_sources(items: list[dict], parties: list[str], camps: dict) -> tuple[list[dict], list[dict]]:
    """Up to 3 articles from different camps: the sides involved first, then UN/multilateral, then others."""
    by_camp: dict[str, list[dict]] = collections.defaultdict(list)
    for a in items: by_camp[a["camp"]].append(a)
    for v in by_camp.values(): v.sort(key=lambda a: a.get("date") or "", reverse=True)
    chosen: list[str] = []
    # 1) one camp per country involved (e.g. Ukrainian for UKR, Russian state for RUS)
    for p in parties:
        for camp, info in camps.items():
            if p in info["home"] and camp in by_camp and camp not in chosen:
                chosen.append(camp); break
        if len(chosen) >= 2: break
    # 2) a neutral / multilateral voice
    if "multilateral" in by_camp and "multilateral" not in chosen and len(chosen) < 3: chosen.append("multilateral")
    # 3) fill with the remaining camps, most outlets first
    for camp in sorted(by_camp, key=lambda c: -len(by_camp[c])):
        if len(chosen) >= 3: break
        if camp not in chosen: chosen.append(camp)
    picked = [by_camp[c][0] for c in chosen[:3]]
    # sides involved in the story with no coverage among today's headlines: offer a search instead
    missing = []
    for p in parties[:2]:
        for camp, info in camps.items():
            if p in info["home"] and camp not in by_camp and camp != "multilateral" and camp != "russia-independent":
                missing.append({"camp": camp, "label": info["label"]}); break
    return picked, missing

def run(args):
    cfg = json.loads((HERE / "news_sources.json").read_text(encoding="utf-8"))
    camps = cfg["camps"]
    cache = HERE / "trawler_cache"; cache.mkdir(exist_ok=True)
    focus = focus_countries(cache / "focus_countries.json")
    arts, status = gather(cfg, args)
    print(f"  {len(arts)} headlines from {sum(s['ok'] for s in status)}/{len(status)} outlets")
    groups = cluster(arts, args.threshold)
    stories = []
    for items in groups:
        cc = collections.Counter()
        for a in items: cc.update(a["_c"])
        parties = [c for c, _ in cc.most_common(3)]
        n_out = len({a["outlet"] for a in items}); n_camp = len({a["camp"] for a in items})
        newest = max((a.get("date") or "") for a in items)
        try: age_h = (NOW - dt.datetime.fromisoformat(newest)).total_seconds() / 3600
        except Exception: age_h = 24
        score = n_out * 2 + n_camp * 3 - age_h / 12
        picked, missing = pick_sources(items, parties, camps)
        key_terms = " ".join(t.lstrip("^") for t, _ in collections.Counter(t for a in items for t in tokens(a["title"])).most_common(5))
        side_camps = {c for c, info in camps.items() if set(info["home"]) & set(parties[:2])}
        lead = (next((a for a in picked if a["camp"] == "multilateral"), None)
                or next((a for a in picked if a["camp"] == "western"), None)
                or next((a for a in picked if a["camp"] not in side_camps), None)
                or (picked[0] if picked else items[0]))
        hits = [bodies_in(a["title"]) for a in items]
        share = sum(1 for h in hits if h) / max(1, len(items))
        blist = [b for b, _ in collections.Counter(b for h in hits for b in h if b != "Summit").most_common(3)]
        if not blist and any("Summit" in h for h in hits): blist = ["Summit"]
        is_diplo = bool(blist) and (share >= 0.5 or bool(bodies_in(lead["title"])))
        stories.append({
            "bodies": blist if is_diplo else [],
            "id": T.hashlib.sha1(lead["url"].encode()).hexdigest()[:10],
            "headline": lead["title"], "countries": parties, "score": round(score, 2),
            "outlets": n_out, "camps": n_camp, "updated": newest,
            "sources": [{"outlet": a["outlet"], "camp": a["camp"], "camp_label": camps[a["camp"]]["label"], "ownership": a["ownership"],
                         "title": a["title"], "url": a["url"], "date": a.get("date")} for a in picked],
            "missing": [{**m, "search": [{"outlet": o["name"], "url": "https://duckduckgo.com/?q=" + urllib.parse.quote(f"site:{o['domain']} {key_terms}")}
                                         for o in cfg["outlets"] if o["camp"] == m["camp"]][:2]} for m in missing],
        })
    # per focus country: its top stories; elsewhere: the most widely covered stories
    by_country: dict[str, list] = collections.defaultdict(list)
    other, diplomacy = [], []
    for s in sorted(stories, key=lambda s: -s["score"]):
        if s["bodies"] and (s["outlets"] >= 2 or any(x["camp"] == "multilateral" for x in s["sources"])):
            if len(diplomacy) < args.diplomacy: diplomacy.append(s["id"])
            continue
        fc = [c for c in s["countries"] if c in focus]
        if fc:
            for c in fc[:2]:
                if len(by_country[c]) < args.per_country: by_country[c].append(s["id"])
        elif s["outlets"] >= 2 and len(other) < args.other:
            other.append(s["id"])
    keep = {i for v in by_country.values() for i in v} | set(other) | set(diplomacy)
    out = {"generated": NOW.isoformat(), "focus": focus, "diplomacy": diplomacy, "by_country": by_country, "other": other,
           "stories": {s["id"]: s for s in stories if s["id"] in keep}, "feeds": status,
           "note": "Headlines and links only; each story lists up to 3 outlets from different camps."}
    payload = json.dumps(out, ensure_ascii=False, indent=1)
    T.write_text_atomic(HERE / "stories.json", payload)
    T.write_text_atomic(Path(args.js_out), "// written by news.py — loaded automatically by commandcenter-map.html\nwindow.CC_STORIES = " + payload + ";\n")
    multi = sum(1 for i in keep if out["stories"][i]["camps"] >= 3)
    print(f"  {len(keep)} stories kept ({multi} with 3+ perspectives) across {len(diplomacy)} diplomacy, {len(by_country)} focus countries + {len(other)} others")
    bad = [s["outlet"] for s in status if not s["ok"]]
    if bad: print("  feeds that failed: " + ", ".join(bad))
    print(f"wrote {args.js_out}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="folder of saved feeds named <Outlet_Name>.xml (testing)")
    ap.add_argument("--js-out", default=str(HERE.parent / "data" / "stories.js"))
    ap.add_argument("--hours", type=float, default=36, help="ignore headlines older than this")
    ap.add_argument("--max-items", type=int, default=80, help="per feed")
    ap.add_argument("--threshold", type=float, default=0.24, help="similarity needed to group headlines (0-1)")
    ap.add_argument("--per-country", type=int, default=4)
    ap.add_argument("--other", type=int, default=12)
    ap.add_argument("--diplomacy", type=int, default=8, help="stories in the Global diplomacy section")
    run(ap.parse_args())

if __name__ == "__main__":
    main()
