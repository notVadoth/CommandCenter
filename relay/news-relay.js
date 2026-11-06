// CommandCenter news relay (v1.2): a free Cloudflare Worker that searches Google News and Bing News at
// the same time for a place, merges the results and returns the top headlines from the last 24 hours
// as JSON the map page can read.
// Browsers can't read Google News directly (no CORS), so this small relay sits in between.
//
// Setup (about 5 minutes, free, no card):
//   1. Sign in at https://dash.cloudflare.com  ->  Workers & Pages  ->  Create  ->  Create Worker
//   2. Name it e.g. "cc-news", click Deploy, then "Edit code"
//   3. Replace everything with this file, click Deploy
//   4. Copy the address it shows (https://cc-news.<you>.workers.dev) into data/config.js
//
// Request:  GET https://cc-news.<you>.workers.dev/?q=%22Michigan%22||Michigan%20news&ceid=US:en   (up to 3 phrasings, ||-separated)
// Response: {"query":[…],"provider":"Google News + Bing News","fetched":"…","items":[{"title","source","url","published"}]}
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
const MAX_ITEMS = 15;
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
    // up to 3 search phrasings separated by "||" (e.g. "Michigan"||Michigan news); all are run at once and merged
    const queries = (url.searchParams.get("q") || "").split("||").map(x => x.trim().slice(0, 120)).filter(Boolean).slice(0, 3);
    const ceid = /^[A-Z]{2}:[a-z]{2}$/.test(url.searchParams.get("ceid") || "") ? url.searchParams.get("ceid") : "US:en";
    if (!queries.length) return json({ error: "missing q" }, 400, cors);

    const [gl, hl] = ceid.split(":");
    const cache = caches.default;
    const cacheKey = new Request(`https://relay.cache/v2?q=${encodeURIComponent(queries.join("||"))}&ceid=${ceid}`);
    let res = await cache.match(cacheKey);
    if (!res) {
      // Google refuses Cloudflare's servers some of the time (HTTP 503); after a refusal it is skipped for 30 minutes
      const googleDown = !!(await cache.match(GOOGLE_DOWN));
      const jobs = [];
      if (!googleDown) jobs.push(["Google News", 0, googleNews(queries[0], gl, hl)]);
      queries.forEach((q, i) => jobs.push(["Bing News", i, bingNews(q, gl, hl)]));
      const settled = await Promise.allSettled(jobs.map(j => withTimeout(j[2], 6000)));
      const lists = [], providers = new Set(), errors = [];
      settled.forEach((r, i) => {
        const [name] = jobs[i];
        if (r.status === "fulfilled") { lists.push(r.value); if (r.value.length) providers.add(name); }
        else {
          errors.push(`${name}: ${r.reason?.message || r.reason}`);
          if (name === "Google News") ctx.waitUntil(cache.put(GOOGLE_DOWN, new Response("1", { headers: { "Cache-Control": "max-age=1800" } })));
        }
      });
      if (!lists.length) return json({ error: errors.join("; ") }, 502, cors);
      const items = mergeRanked(lists).slice(0, MAX_ITEMS);
      res = json({ query: queries, ceid, provider: [...providers].join(" + ") || "none", fetched: new Date().toISOString(), items },
                 200, { "Cache-Control": `public, max-age=${CACHE_SECONDS}` });
      ctx.waitUntil(cache.put(cacheKey, res.clone()));
    }
    const out = new Response(res.body, res);
    for (const [k, v] of Object.entries(cors)) out.headers.set(k, v);
    return out;
  },
};

const GOOGLE_DOWN = new Request("https://relay.cache/google-down");

function withTimeout(p, ms) {
  return Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error(`timed out after ${ms / 1000}s`)), ms))]);
}

// Merge several ranked result lists: a story ranks by its best position in any list; near-identical titles are merged
function mergeRanked(lists) {
  const best = new Map();
  lists.forEach(list => list.forEach((it, pos) => {
    const k = it.title.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().slice(0, 70);
    const cur = best.get(k);
    if (!cur || pos < cur.pos) best.set(k, { ...it, pos });
  }));
  return [...best.values()].sort((a, b) => a.pos - b.pos || Date.parse(b.published) - Date.parse(a.published)).map(({ pos, ...it }) => it);
}

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
