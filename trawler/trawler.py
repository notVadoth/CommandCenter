#!/usr/bin/env python3
"""
CommandCenter data trawler
==========================

Reads news articles (RSS feeds, URLs, or local files), extracts claims about
countries joining / leaving / applying to groupings (EU, NATO, BRICS ... or new
pacts and coalitions named in the news), then verifies every claim
INDEPENDENTLY of the article that made it:

  1. Wikidata  - structured membership data (P463 "member of", P1891 "signatory")
  2. Corroboration - how many *independent* outlets report the same claim
                     (syndicated copies of the same text count once)
  3. Baseline  - your curated blocs.json

The article text is only ever used to *propose* a claim; it never verifies itself.
Output is groupings.json, which the CommandCenter map can load.

Python 3.9+, standard library only.

Usage
-----
  python trawler.py run                         # feeds.json -> groupings.json
  python trawler.py run --input articles/ urls.txt
  python trawler.py run --llm                   # use Claude for extraction (needs ANTHROPIC_API_KEY)
  python trawler.py run --no-wikidata           # corroboration-only verification
  python trawler.py run --accept corroborated   # also apply multi-source claims to members
  python trawler.py report                      # print the review queue from the last run
"""
from __future__ import annotations

import argparse, datetime as dt, email.utils, hashlib, html, json, os, re, sys, time
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Windows consoles default to a legacy code page; never crash on a non-English headline
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


def read_json(path: Path, default):
    """Read JSON (UTF-8). A missing, empty or half-written file gives `default` instead of a crash."""
    try:
        txt = Path(path).read_text(encoding="utf-8")
        return json.loads(txt) if txt.strip() else default
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, UnicodeDecodeError):
        bad = Path(str(path) + ".corrupt"); Path(path).replace(bad)
        print(f"  ! {Path(path).name} was unreadable; moved to {bad.name} and starting fresh", file=sys.stderr)
        return default


def write_text_atomic(path: Path, text: str):
    """Write UTF-8 via a temp file + rename, so an interrupted run never leaves a half-written file."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
UA = "CommandCenterTrawler/0.1 (personal research tool)"
NOW = dt.datetime.now(dt.timezone.utc)

# --------------------------------------------------------------------------
# Gazetteers
# --------------------------------------------------------------------------
COUNTRIES: dict[str, str] = json.loads((HERE / "countries.json").read_text(encoding="utf-8"))

# action vocabulary: regex -> action. Order matters (first match wins).
ACTIONS = [
    ("suspended", r"\b(?:was|were|been|is|are|got)?\s*suspended\b|\bsuspen(?:ds|sion of)\b"),
    ("reinstated", r"\breinstat(?:ed|es|ement)\b|\breadmit(?:ted|s)?\b|\blift(?:ed|s)? (?:its|the) suspension\b"),
    ("left", r"\b(?:withdr[ae]w|withdrawn|withdrawing|withdrawal)\b|\b(?:left|leaves|leaving|quit|quits|exited|exits|exit from|pulled out of|pulls out of)\b"),
    ("applied", r"\b(?:applied|applies|application|bid|bids|seeks?|seeking|sought|wants? to join|candidate|candidacy|invited|invitation|aspir\w+|hopes? to join|will join|set to join|is to join|plans? to join|intends? to join)\b"),
    ("partner", r"\bpartner (?:country|state|nation|status)\b|\bbec(?:a|o)me an? partner\b|\bdialogue partner\b"),
    ("joined", r"\b(?:joined|joins|joining|became (?:a|the \w+) (?:full )?member|becomes (?:a|the \w+) (?:full )?member|admitted|accession|acceded|accedes|welcomed .{0,30} as (?:a|its) (?:new |newest )?member|newest member|ratified (?:its|the) membership)\b"),
    ("signed", r"\b(?:signed|signs|signing|inked|ratified|concluded|launched|formed|founded|established|created)\b"),
]
ACTIONS = [(a, re.compile(p, re.I)) for a, p in ACTIONS]
HEDGE = re.compile(r"\b(?:could|might|may|would|considering|consider|mulls?|weighs?|rumou?red|reportedly|if|unless|whether|denied|denies|rejected|rejects|not (?:yet )?(?:join|joined|a member)|never)\b", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'“])")

# new-grouping detector: "... the Abc Def Accord/Pact/..." (proper-noun phrase)
NEW_GROUP = re.compile(
    r"\b(?:the\s+)?((?:[A-Z][\w'’\-]+|of|for|on|and|the|de)(?:\s+(?:[A-Z][\w'’\-]+|of|for|on|and|the|de)){0,6}\s+"
    r"(?:Agreement|Accord|Accords|Pact|Treaty|Alliance|Coalition|Initiative|Partnership|Declaration|Compact|Bloc|Union|Forum|Framework|Charter))\b")


def build_country_regex():
    names = sorted(COUNTRIES, key=len, reverse=True)
    alts = "|".join(re.escape(n) for n in names)
    # case-sensitive: avoids "us"/"chad" false hits in lowercase prose
    return re.compile(r"(?<![\w.])(?:the\s+)?(" + alts + r")(?![\w])")


COUNTRY_RE = build_country_regex()


def load_blocs(path: Path) -> dict:
    blocs = json.loads(path.read_text(encoding="utf-8"))
    for k, b in blocs.items():
        b["key"] = k
        b["members"] = b["members"].split() if isinstance(b["members"], str) else list(b["members"])
        als = set(b.get("aliases", [])) | {b["name"], k}
        b["_re"] = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(a) for a in sorted(als, key=len, reverse=True)) + r")(?![\w+])")
    return blocs


# --------------------------------------------------------------------------
# HTTP + parsing helpers
# --------------------------------------------------------------------------
def http_get(url: str, timeout=20, accept="*/*") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0; self.in_p = 0; self.title = ""; self._t = False
    def handle_starttag(self, t, a):
        if t in ("script", "style", "nav", "footer", "header", "aside", "form"): self.skip += 1
        if t == "p": self.in_p += 1
        if t == "title": self._t = True
    def handle_endtag(self, t):
        if t in ("script", "style", "nav", "footer", "header", "aside", "form") and self.skip: self.skip -= 1
        if t == "p" and self.in_p: self.in_p -= 1; self.parts.append("\n")
        if t == "title": self._t = False
    def handle_data(self, d):
        if self._t: self.title += d
        if self.in_p and not self.skip: self.parts.append(d)


def html_to_text(raw: str) -> tuple[str, str]:
    p = _Text(); p.feed(raw)
    text = re.sub(r"[ \t]+", " ", "".join(p.parts)).strip()
    return p.title.strip(), text


def domain_of(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    host = re.sub(r"^(www|m|amp|edition|rss|feeds)\.", "", host)
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "ac"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def parse_date(s: str | None) -> str | None:
    if not s: return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc).isoformat()
    except Exception:
        pass
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
    except Exception:
        return None


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------
def read_feed(url: str, max_items: int) -> list[dict]:
    return read_feed_xml(http_get(url, accept="application/rss+xml, application/atom+xml, */*"), max_items)


def read_feed_xml(data: bytes, max_items: int) -> list[dict]:
    root = ET.fromstring(data)
    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"): continue
        kids = {}
        for c in it:   # first child of each name (Element truthiness is unreliable, so test "is None" explicitly)
            kids.setdefault(c.tag.split("}")[-1], c)
        def txt(*names):
            for n in names:
                e = kids.get(n)
                if e is not None and (e.text or "").strip(): return e.text.strip()
            return ""
        link = kids.get("link")
        href = ((link.get("href") or link.text or "") if link is not None else "").strip()
        raw_desc = txt("description", "summary", "encoded")
        summary = html_to_text(raw_desc)[1] or re.sub(r"<[^>]+>", " ", html.unescape(raw_desc))
        items.append({
            "url": href,
            "title": html.unescape(re.sub(r"<[^>]+>", "", txt("title"))),
            "summary": re.sub(r"\s+", " ", summary).strip(),
            "date": parse_date(txt("pubDate", "published", "updated", "date")),
        })
        if len(items) >= max_items: break
    return items


def load_inputs(paths: list[str]) -> list[dict]:
    """Local .txt/.md/.html/.json files, directories of them, or a .txt list of URLs."""
    out = []
    for p in paths:
        P = Path(p)
        if p.startswith("http"):
            out.append({"url": p}); continue
        files = sorted(P.rglob("*")) if P.is_dir() else [P]
        for f in files:
            if not f.is_file(): continue
            raw = f.read_text(encoding="utf-8", errors="replace")
            if f.suffix == ".json":
                data = json.loads(raw)
                out.extend(data if isinstance(data, list) else [data])
            elif f.suffix in (".html", ".htm"):
                title, text = html_to_text(raw)
                out.append({"url": f.resolve().as_uri(), "title": title, "text": text, "source": f.stem})
            elif f.suffix == ".txt" and all(l.strip().startswith("http") for l in raw.splitlines() if l.strip()):
                out.extend({"url": l.strip()} for l in raw.splitlines() if l.strip())
            else:
                # plain text; optional header lines "Title:", "Source:", "URL:", "Date:"
                meta, body = {}, []
                for line in raw.splitlines():
                    m = re.match(r"^(Title|Source|URL|Date):\s*(.*)$", line) if not body else None
                    if m: meta[m.group(1).lower()] = m.group(2).strip()
                    else: body.append(line)
                out.append({"url": meta.get("url") or f.resolve().as_uri(), "title": meta.get("title", f.stem),
                            "source": meta.get("source"), "date": parse_date(meta.get("date")) or meta.get("date"),
                            "text": "\n".join(body).strip()})
    return out


def fetch_full_text(a: dict) -> None:
    if a.get("text") or not a.get("url", "").startswith("http"): return
    try:
        title, text = html_to_text(http_get(a["url"]).decode("utf-8", "replace"))
        a["text"] = text if len(text) > 200 else (a.get("summary") or "")
        a.setdefault("title", title)
    except Exception as e:
        a["text"] = a.get("summary") or ""
        a["fetch_error"] = str(e)[:120]


# --------------------------------------------------------------------------
# Extraction (rule-based, or Claude if --llm)
# --------------------------------------------------------------------------
def extract_rules(a: dict, blocs: dict) -> list[dict]:
    text = f"{a.get('title','')}. {a.get('text') or a.get('summary') or ''}"
    claims = []
    for sent in SENT_SPLIT.split(text):
        if len(sent) > 600: continue
        hits = [(m.start(1), m.end(1), COUNTRIES[m.group(1)]) for m in COUNTRY_RE.finditer(sent)]
        if not hits: continue
        hedged = bool(HEDGE.search(sent))
        targets = [("bloc", b, m) for b in blocs.values() for m in b["_re"].finditer(sent)]
        for m in NEW_GROUP.finditer(sent):
            name = re.sub(r"^(?:the|and|of|for|on)\s+", "", m.group(1), flags=re.I).strip()
            if any(b["_re"].fullmatch(name) for b in blocs.values()): continue
            if name.split()[0] in COUNTRIES and len(name.split()) == 2: continue
            targets.append(("new", name, m))
        for kind, tgt, m in targets:
            action, vpos = None, None
            for act, rx in ACTIONS:
                if act == "signed" and kind == "bloc": continue
                if act in ("joined", "left", "suspended", "reinstated", "partner") and kind == "new" and act != "joined": continue
                vm = rx.search(sent)
                if vm: action, vpos = act, vm.start(); break
            if not action: continue
            # subject countries: those before the verb (fallback: all in sentence, minus inside the target name)
            span = (m.start(), m.end())
            cs = [c for s, e, c in hits if not (s >= span[0] and e <= span[1])]
            before = [c for s, e, c in hits if s < vpos and not (s >= span[0] and e <= span[1])]
            subj = before or cs
            if kind == "bloc":
                subj = [c for c in subj if not (tgt["key"] == "EU" and c in ("EUR",))]
            for c in dict.fromkeys(subj):
                claims.append({
                    "kind": kind, "group": tgt["key"] if kind == "bloc" else tgt, "country": c,
                    "action": "joined" if (kind == "new" and action == "signed") else action,
                    "hedged": hedged, "sentence": sent.strip()[:400]})
    return claims


LLM_PROMPT = """You extract factual claims about countries' membership in international groupings from a news article.
Return ONLY a JSON array. Each item: {"group": "<grouping name as written>", "country": "<country name>",
"action": "joined|left|applied|suspended|reinstated|partner", "hedged": true|false, "sentence": "<supporting sentence, verbatim, max 300 chars>"}.
"hedged" is true if the article presents it as speculation, intention, or reported-but-unconfirmed.
Only include claims the article actually states. No commentary.

ARTICLE TITLE: {title}
ARTICLE TEXT:
{text}"""


def extract_llm(a: dict, blocs: dict) -> list[dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: raise SystemExit("--llm needs ANTHROPIC_API_KEY set in your environment")
    body = json.dumps({"model": os.environ.get("TRAWLER_MODEL", "claude-sonnet-5-5"), "max_tokens": 2000,
                       "messages": [{"role": "user", "content": LLM_PROMPT.replace("{title}", a.get("title", ""))
                                     .replace("{text}", (a.get("text") or a.get("summary") or "")[:20000])}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        out = json.loads(r.read())["content"][0]["text"]
    items = json.loads(out[out.find("["): out.rfind("]") + 1] or "[]")
    claims = []
    for it in items:
        c = COUNTRIES.get(it.get("country", "").strip()) or COUNTRIES.get(it.get("country", "").strip().title())
        if not c: continue
        gname = it.get("group", "").strip()
        bloc = next((b for b in blocs.values() if b["_re"].fullmatch(gname)), None)
        claims.append({"kind": "bloc" if bloc else "new", "group": bloc["key"] if bloc else gname, "country": c,
                       "action": it.get("action", "joined"), "hedged": bool(it.get("hedged")),
                       "sentence": it.get("sentence", "")[:400]})
    return claims


# --------------------------------------------------------------------------
# Verification against independent data
# --------------------------------------------------------------------------
class Wikidata:
    SPARQL = "https://query.wikidata.org/sparql"
    API = "https://www.wikidata.org/w/api.php"

    def __init__(self, cache_dir: Path, enabled=True, fixture: Path | None = None):
        self.enabled = enabled
        self.cache_path = cache_dir / "wikidata_cache.json"
        self.cache = read_json(self.cache_path, {})
        self.fixture = read_json(fixture, None) if fixture else None

    def save(self):
        write_text_atomic(self.cache_path, json.dumps(self.cache, indent=1, ensure_ascii=False))

    def _cached(self, key, fn, max_age_h=24):
        hit = self.cache.get(key)
        if hit and time.time() - hit["t"] < max_age_h * 3600: return hit["v"]
        v = fn(); self.cache[key] = {"t": time.time(), "v": v}; return v

    def sparql(self, q):
        url = self.SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
        return json.loads(http_get(url, timeout=60, accept="application/sparql-results+json"))["results"]["bindings"]

    def resolve(self, name: str) -> dict | None:
        if self.fixture is not None: return self.fixture.get("resolve", {}).get(name)
        if not self.enabled: return None
        def go():
            url = self.API + "?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": name, "language": "en",
                                                         "type": "item", "limit": 5, "format": "json"})
            res = json.loads(http_get(url))["search"]
            good = [r for r in res if re.search(r"organi[sz]ation|alliance|union|group|bloc|treaty|agreement|accord|pact|forum|partnership|coalition|council|initiative|declaration|community", r.get("description", ""), re.I)]
            r = (good or res or [None])[0]
            return {"qid": r["id"], "label": r.get("label"), "description": r.get("description")} if r else None
        try: return self._cached("resolve:" + name, go, 24 * 30)
        except Exception as e: print(f"  ! wikidata resolve failed for {name}: {e}", file=sys.stderr); return None

    def members(self, qid: str) -> dict | None:
        """{ISO3: {"start":..., "end":...}} from P463 (member of) and P1891 (signatory)."""
        if self.fixture is not None: return self.fixture.get("members", {}).get(qid)
        if not self.enabled: return None
        q = f"""SELECT ?iso ?start ?end WHERE {{
          {{ ?c p:P463 ?st . ?st ps:P463 wd:{qid} . ?st wikibase:rank ?rk . FILTER(?rk != wikibase:DeprecatedRank)
             OPTIONAL {{ ?st pq:P580 ?start }} OPTIONAL {{ ?st pq:P582 ?end }} }}
          UNION {{ wd:{qid} wdt:P1891 ?c }}
          ?c wdt:P298 ?iso . }}"""
        def go():
            out = {}
            for r in self.sparql(q):
                iso = r["iso"]["value"]
                rec = out.setdefault(iso, {"start": None, "end": None})
                if "start" in r: rec["start"] = max(filter(None, [rec["start"], r["start"]["value"][:10]]))
                if "end" in r: rec["end"] = max(filter(None, [rec["end"], r["end"]["value"][:10]]))
                elif rec["end"] and not rec["start"]: pass
            return out
        try: return self._cached("members:" + qid, go)
        except Exception as e: print(f"  ! wikidata members failed for {qid}: {e}", file=sys.stderr); return None


def wd_iso(iso3: str) -> str:
    return {"KOS": "XKX"}.get(iso3, iso3)


def wikidata_says(action: str, rec: dict | None, have_data: bool) -> str:
    """'agrees' | 'disagrees' | 'unknown'"""
    if not have_data: return "unknown"
    current = bool(rec) and not rec.get("end")
    if action == "joined": return "agrees" if current else "unknown"   # Wikidata often lags; absence ≠ contradiction
    if action == "left":
        if rec and rec.get("end"): return "agrees"
        return "disagrees" if current else "unknown"
    if action == "applied": return "disagrees" if current else "unknown"  # already a member → stale/odd claim
    return "unknown"


def status_for(wd: str, n_outlets: int, hedged_only: bool) -> str:
    if wd == "disagrees": return "conflict"
    if hedged_only: return "speculative"
    if wd == "agrees": return "confirmed"
    if n_outlets >= 2: return "corroborated"
    return "single-source"


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def run(args):
    blocs = load_blocs(Path(args.blocs))
    cache_dir = Path(args.cache); cache_dir.mkdir(exist_ok=True)
    db_path = cache_dir / "claims.json"
    db = read_json(db_path, {"articles": {}, "claims": []})

    # 1. gather articles
    articles = []
    if not args.input or args.feeds_too:
        feeds = read_json(Path(args.feeds), [])
        for f in feeds:
            try:
                items = read_feed(f["url"], args.max_items)
                for it in items: it["source"] = f.get("name"); it["trust"] = f.get("trust", 1)
                articles += items
                print(f"  feed {f.get('name')}: {len(items)} items")
            except Exception as e:
                print(f"  ! feed {f.get('name')} failed: {e}", file=sys.stderr)
    if args.input:
        articles += load_inputs(args.input)

    cutoff = NOW - dt.timedelta(days=args.days)
    new = 0
    for a in articles:
        url = a.get("url") or ("text:" + hashlib.sha1((a.get("text") or "").encode()).hexdigest())
        a["url"] = url
        if url in db["articles"] and not args.reprocess: continue
        if a.get("date"):
            try:
                if dt.datetime.fromisoformat(a["date"]) < cutoff: continue
            except Exception: pass
        if not args.no_fetch: fetch_full_text(a)
        try:
            claims = extract_llm(a, blocs) if args.llm else extract_rules(a, blocs)
        except Exception as e:
            print(f"  ! extraction failed for {url}: {e}", file=sys.stderr); continue
        dom = domain_of(url) if url.startswith("http") else (a.get("source") or "local").lower()
        db["articles"][url] = {"title": a.get("title"), "source": a.get("source") or dom, "domain": dom, "date": a.get("date"),
                               "seen": NOW.isoformat(), "n_claims": len(claims)}
        db["claims"] = [c for c in db["claims"] if c["url"] != url]
        for c in claims:
            c.update(url=url, domain=dom, source=a.get("source") or dom, title=a.get("title"), date=a.get("date"))
            db["claims"].append(c)
        new += 1
    write_text_atomic(db_path, json.dumps(db, indent=1, ensure_ascii=False))
    print(f"processed {new} new article(s); {len(db['claims'])} claim(s) in store")

    # 2. group claims and verify
    wd = Wikidata(cache_dir, enabled=not args.no_wikidata, fixture=Path(args.wikidata_fixture) if args.wikidata_fixture else None)
    groups: dict[tuple, list] = {}
    for c in db["claims"]:
        groups.setdefault((c["kind"], c["group"], c["country"], c["action"]), []).append(c)

    out_blocs, review, new_groups = {}, [], {}
    bloc_wd = {}
    for k, b in blocs.items():
        ref = {"qid": b["qid"], "label": b.get("qid_label")} if b.get("qid") else wd.resolve(b.get("wikidata_search") or b["name"])
        bloc_wd[k] = {"ref": ref, "members": wd.members(ref["qid"]) if ref else None}

    def evidence(cs):
        seen_text, ev = set(), []
        for c in sorted(cs, key=lambda c: c.get("date") or ""):
            h = re.sub(r"\W+", "", c["sentence"].lower())[:160]
            ev.append({"source": c["source"], "domain": c["domain"], "title": c["title"], "url": c["url"], "date": c["date"],
                       "sentence": c["sentence"], "hedged": c["hedged"], "syndicated_copy": h in seen_text})
            seen_text.add(h)
        outlets = {e["domain"] for e in ev if not e["syndicated_copy"] and not e["hedged"]}
        return ev, len(outlets), all(e["hedged"] for e in ev)

    for k, b in blocs.items():
        members = list(b["members"]); applicants, partners, changes = [], list(b.get("partners", [])), []
        wdm = bloc_wd[k]["members"]
        for (kind, g, iso, act), cs in groups.items():
            if kind != "bloc" or g != k: continue
            ev, n, hedged_only = evidence(cs)
            in_baseline = iso in members
            # drop no-op claims (e.g. "NATO member Poland joined talks") that only restate baseline
            if act == "joined" and in_baseline and not hedged_only:
                continue
            # "applied" for a country that is already a member is a misread (e.g. a mention of Croatia's 2011 talks)
            if act == "applied" and in_baseline:
                continue
            w = wikidata_says(act, (wdm or {}).get(wd_iso(iso)), wdm is not None)
            st = status_for(w, n, hedged_only)
            changes.append({"country": iso, "action": act, "status": st, "wikidata": w, "independent_outlets": n, "evidence": ev})
            accepted = st == "confirmed" or (args.accept == "corroborated" and st == "corroborated")
            if accepted:
                if act == "joined" and iso not in members: members.append(iso)
                if act == "left" and iso in members: members.remove(iso)
                if act == "partner" and iso not in partners: partners.append(iso)
            # only well-supported applications go on the map; one-outlet or hedged claims stay in the review list
            if act == "applied" and st in ("confirmed", "corroborated"): applicants.append(iso)
            if st in ("corroborated", "single-source", "conflict"): review.append({"group": b["name"], **changes[-1]})
        # baseline vs Wikidata audit (separate data disagreeing with your list)
        audit = None
        if wdm is not None:
            cur = {iso for iso, r in wdm.items() if not r.get("end")}
            base = {wd_iso(m) for m in members}
            audit = {"in_wikidata_not_baseline": sorted(cur - base), "in_baseline_not_wikidata": sorted(base - cur)}
        out_blocs[k] = {"name": b["name"], "color": b.get("color", "#888"), "members": members, "partners": partners,
                        "applicants": sorted(set(applicants)), "note": b.get("note"), "wikidata": bloc_wd[k]["ref"],
                        "baseline_audit": audit, "changes": sorted(changes, key=lambda c: c["status"])}

    # new groupings discovered in the news
    for (kind, g, iso, act), cs in groups.items():
        if kind != "new": continue
        ng = new_groups.setdefault(g, {"name": g, "members": {}})
        ev, n, hedged_only = evidence(cs)
        ng["members"][iso] = {"action": act, "independent_outlets": n, "hedged_only": hedged_only, "evidence": ev}
    final_new = []
    for name, ng in new_groups.items():
        if len(ng["members"]) < args.min_new_members: continue
        ref = wd.resolve(name)
        wdm = wd.members(ref["qid"]) if ref else None
        mem = []
        for iso, m in ng["members"].items():
            w = "agrees" if (wdm and wd_iso(iso) in wdm) else ("unknown" if wdm is None or not wdm else "absent")
            st = "speculative" if m["hedged_only"] else "confirmed" if w == "agrees" else "corroborated" if m["independent_outlets"] >= 2 else "single-source"
            mem.append({"country": iso, "status": st, "wikidata": w, **m})
        overall = "confirmed" if any(x["status"] == "confirmed" for x in mem) else \
                  "corroborated" if any(x["status"] == "corroborated" for x in mem) else "single-source"
        final_new.append({"name": name, "status": overall, "wikidata": ref, "color": "#" + hashlib.md5(name.encode()).hexdigest()[:6],
                          "members": sorted(mem, key=lambda x: x["country"])})
        if overall != "confirmed": review.append({"group": name, "country": ",".join(m["country"] for m in mem), "action": "new grouping",
                                                  "status": overall, "evidence": [e for m in mem for e in m["evidence"]][:3]})
    final_new.sort(key=lambda g: (-len(g["members"]), g["name"]))
    wd.save()

    out = {"generated": NOW.isoformat(), "extractor": "claude" if args.llm else "rules",
           "verification": {"wikidata": not args.no_wikidata, "accept": args.accept,
                            "statuses": {"confirmed": "Wikidata agrees with the article claim",
                                         "corroborated": "2+ independent outlets, not yet in Wikidata",
                                         "single-source": "one outlet only", "speculative": "only hedged/intent language",
                                         "conflict": "Wikidata contradicts the claim — review"}},
           "articles_in_store": len(db["articles"]), "blocs": out_blocs, "new_groupings": final_new, "review": review}
    payload = json.dumps(out, indent=1, ensure_ascii=False)
    write_text_atomic(Path(args.out), payload)
    if args.js_out:   # the map loads this automatically (a <script> works from a local file; fetch() would not)
        write_text_atomic(Path(args.js_out), "// written by trawler.py — loaded automatically by commandcenter-map.html\nwindow.TRAWLER_GROUPINGS = " + payload + ";\n")
    print_report(out)
    print(f"\nwrote {args.out}" + (f" and {args.js_out}" if args.js_out else ""))


def print_report(out):
    print(f"\n=== Review queue ({len(out['review'])}) ===")
    for r in out["review"][:40]:
        e = (r.get("evidence") or [{}])[0]
        print(f"[{r['status']:>13}] {r['group']}: {r['country']} {r['action']}  — {e.get('source','?')}: \"{(e.get('sentence') or '')[:110]}\"")
    for k, b in out["blocs"].items():
        a = b.get("baseline_audit")
        if a and (a["in_wikidata_not_baseline"] or a["in_baseline_not_wikidata"]):
            print(f"[   audit     ] {b['name']}: Wikidata-only {a['in_wikidata_not_baseline']}  baseline-only {a['in_baseline_not_wikidata']}")
    if out["new_groupings"]:
        print("\n=== New groupings spotted ===")
        for g in out["new_groupings"][:15]:
            print(f"  {g['name']} [{g['status']}]: {', '.join(m['country'] for m in g['members'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="trawl, extract, verify, write groupings.json")
    r.add_argument("--feeds", default=str(HERE / "feeds.json"))
    r.add_argument("--blocs", default=str(HERE / "blocs.json"))
    r.add_argument("--input", nargs="*", help="files, folders, URL-list .txt files, or URLs (skips feeds unless --feeds-too)")
    r.add_argument("--feeds-too", action="store_true")
    r.add_argument("--out", default=str(HERE / "groupings.json"))
    r.add_argument("--js-out", default=str(HERE.parent / "data" / "groupings.js"),
                   help="also write a JS copy the map auto-loads ('' to skip)")
    r.add_argument("--cache", default=str(HERE / "trawler_cache"))
    r.add_argument("--days", type=int, default=30, help="ignore articles older than this")
    r.add_argument("--max-items", type=int, default=60, help="per feed")
    r.add_argument("--llm", action="store_true", help="use Claude for extraction (verification stays independent)")
    r.add_argument("--no-wikidata", action="store_true")
    r.add_argument("--no-fetch", action="store_true", help="use feed summaries only, don't fetch full articles")
    r.add_argument("--reprocess", action="store_true", help="re-extract articles already in the store")
    r.add_argument("--accept", choices=["confirmed", "corroborated"], default="confirmed",
                   help="lowest status that changes a bloc's member list")
    r.add_argument("--min-new-members", type=int, default=2, help="countries needed before a new grouping is reported")
    r.add_argument("--wikidata-fixture", help=argparse.SUPPRESS)
    p = sub.add_parser("report", help="print the review queue from the last groupings.json")
    p.add_argument("--out", default=str(HERE / "groupings.json"))
    a = ap.parse_args()
    if a.cmd == "run": run(a)
    else: print_report(read_json(Path(a.out), {"review": [], "blocs": {}, "new_groupings": []}))


if __name__ == "__main__":
    main()
