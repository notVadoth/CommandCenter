// CommandCenter news relay: a free Cloudflare Worker that fetches Google News search results for a
// place (falling back to Bing News if Google refuses) and returns the top headlines from the last
// 24 hours as JSON the map page can read.
// Browsers can't read Google News directly (no CORS), so this small relay sits in between.
//
// Setup (about 5 minutes, free, no card):
//   1. Sign in at https://dash.cloudflare.com  ->  Workers & Pages  ->  Create  ->  Create Worker
//   2. Name it e.g. "cc-news", click Deploy, then "Edit code"
//   3. Replace everything with this file, click Deploy
//   4. Copy the address it shows (https://cc-news.<you>.workers.dev) into data/config.js
//
// Request:  GET https://cc-news.<you>.workers.dev/?q=Ontario%20Canada&ceid=CA:en
// Response: {"query":"…","provider":"Google News|Bing News","fetched":"…","items":[{"title","source","url","published"}]}
//
// The free plan allows 100,000 requests a day; results are cached for 15 minutes per place.

// Only these pages may use the relay (stops other sites from borrowing it).
// "null" is what browsers send for a page opened straight from disk (file://).
const ALLOWED_ORIGINS = [
  "https://notvadoth.github.io",
  "null",
  "http://localhost",
  "http://127.0.0.1",
];
const MAX_ITEMS = 12;
const CACHE_SECONDS = 900;

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";
    const allowed = ALLOWED_ORIGINS.some(o => origin === o || (o.startsWith("http://") && origin.startsWith(o + ":")));
    const cors = {
      "Access-Control-Allow-Origin": allowed ? origin : ALLOWED_ORIGINS[0],
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (!allowed) return json({ error: "origin not allowed" }, 403, cors);

    const url = new URL(request.url);
    const q = (url.searchParams.get("q") || "").trim().slice(0, 120);
    const ceid = /^[A-Z]{2}:[a-z]{2}$/.test(url.searchParams.get("ceid") || "") ? url.searchParams.get("ceid") : "US:en";
    if (!q) return json({ error: "missing q" }, 400, cors);

    const [gl, hl] = ceid.split(":");
    const cacheKey = new Request(`https://relay.cache/?q=${encodeURIComponent(q)}&ceid=${ceid}`);
    const cache = caches.default;
    let res = await cache.match(cacheKey);
    if (!res) {
      // Google News first; it sometimes refuses cloud servers (HTTP 503), so fall back to Bing News
      let items = [], provider = "", errors = [];
      for (const [name, getter] of [["Google News", googleNews], ["Bing News", bingNews]]) {
        try { items = await getter(q, gl, hl); provider = name; if (items.length) break; }
        catch (e) { errors.push(`${name}: ${e.message}`); }
      }
      if (!provider) return json({ error: errors.join("; ") }, 502, cors);
      res = json({ query: q, ceid, provider, fetched: new Date().toISOString(), items }, 200, { "Cache-Control": `public, max-age=${CACHE_SECONDS}` });
      ctx.waitUntil(cache.put(cacheKey, res.clone()));
    }
    const out = new Response(res.body, res);
    for (const [k, v] of Object.entries(cors)) out.headers.set(k, v);
    return out;
  },
};

const UA = "Mozilla/5.0 (compatible; CommandCenter-news-relay/1.1)";
const DAY = 24 * 3600 * 1000;

async function googleNews(q, gl, hl) {
  const feed = `https://news.google.com/rss/search?q=${encodeURIComponent(q + " when:1d")}&hl=${hl}-${gl}&gl=${gl}&ceid=${gl}:${hl}`;
  const r = await fetch(feed, { headers: { "Accept": "application/rss+xml, application/xml", "User-Agent": UA } });
  if (!r.ok) throw new Error(`returned ${r.status}`);
  return parseItems(await r.text(), it => {
    const source = text(it, "source");
    let title = text(it, "title");
    if (source && title.endsWith(" - " + source)) title = title.slice(0, -(source.length + 3));
    return { title, source, url: text(it, "link"), published: text(it, "pubDate") };
  });
}

async function bingNews(q, gl, hl) {
  // qft interval "7" = past 24 hours
  const feed = `https://www.bing.com/news/search?q=${encodeURIComponent(q)}&format=rss&qft=${encodeURIComponent('interval="7"')}&setlang=${hl}-${gl}&cc=${gl}`;
  const r = await fetch(feed, { headers: { "Accept": "application/rss+xml, application/xml", "User-Agent": UA } });
  if (!r.ok) throw new Error(`returned ${r.status}`);
  return parseItems(await r.text(), it => {
    let url = text(it, "link");
    try { const real = new URL(url).searchParams.get("url"); if (real) url = real; } catch (e) {}   // skip Bing's click-tracking redirect
    return { title: text(it, "title"), source: text(it, "News:Source"), url, published: text(it, "pubDate") };
  });
}

function parseItems(xml, pick) {
  const cutoff = Date.now() - DAY;
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map(m => pick(m[1]))
    .map(x => ({ ...x, published: new Date(x.published).toISOString() }))
    .filter(x => x.title && x.url && Date.parse(x.published) >= cutoff)
    .slice(0, MAX_ITEMS);
}

function text(xml, tag) {
  const m = xml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`));
  if (!m) return "";
  return m[1].replace(/^<!\[CDATA\[|\]\]>$/g, "")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&amp;/g, "&").trim();
}

function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...headers } });
}
