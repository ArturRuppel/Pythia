/* Pythia's offline copy: the installed app still opens, with the last synced graph and every
   PDF readable, when `lit serve` cannot be reached. Read-only — anything that writes needs the
   server.

   js/20-offline.js (inlined into the page) fills the cache from /offline.json on every open and
   stamps each copy with the version it was fetched at. This worker never writes the cache — the
   sync owns it, so a stamp always describes the body it sits on — it only decides where an
   answer comes from:
     - PDFs: the cached copy first (the sync replaces it when its version changes), cut to the
       requested byte range, because Safari and PDF viewers read a PDF in ranges.
     - the page (graph inlined), graph.json, the boot JSON, the PWA files and the alternative
       views: the server first, the cached copy when the server does not answer within
       TIMEOUT_MS or answers through a proxy whose backend is down (502/503/504). A 500 is the
       server talking — a mid-edit BuildError the curator needs to see — so it is passed on.
     - everything else (page rasters, word geometry, search, previews, abstracts): the server
       only, exactly as without a worker. Non-GETs and the sync's own `cache: "no-store"`
       fetches never reach this worker's logic at all. */
const CACHE = "pythia-offline-v1";
const TIMEOUT_MS = 4000;
const DOWN = new Set([502, 503, 504]);
const SCOPE = new URL(self.registration.scope);

// The shell, as paths relative to the scope. Each view's graph.json is the live payload, so it
// is answered from the one cached graph.json rather than kept once per view.
const SHELL = new Set(["graph.json", "aims.json", "pdfs.json", "manifest.webmanifest",
                       "icon-192.png", "icon-512.png", "apple-touch-icon.png"]);
function shellKey(path) {
  if (path === "" || path === "index.html") return "";
  if (SHELL.has(path)) return path;
  if (/^views\/[^/]+\/graph\.json$/.test(path)) return "graph.json";
  if (/^views\/[^/]+\/index\.html$/.test(path)) return path.slice(0, -"index.html".length);
  if (path.startsWith("views/")) return path;
  return null;
}
const isPdf = (path) => /^pdf\/[A-Za-z0-9]+\.pdf$/.test(path);

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  for (const name of await caches.keys())
    if (name.startsWith("pythia-offline-") && name !== CACHE) await caches.delete(name);
  await self.clients.claim();
})()));

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (request.cache === "no-store") return;          // 20-offline.js fetching fresh copies
  const url = new URL(request.url);
  if (url.origin !== SCOPE.origin || !url.pathname.startsWith(SCOPE.pathname)) return;
  const path = url.pathname.slice(SCOPE.pathname.length);
  if (isPdf(path)) return event.respondWith(cacheFirst(request, path));
  const key = shellKey(path);
  if (key !== null) return event.respondWith(serverFirst(request, key));
  if (request.mode === "navigate") event.respondWith(fetch(request).catch(() => needsServer()));
});

async function cached(key) {
  const cache = await caches.open(CACHE);
  return cache.match(new URL(key, SCOPE).href);
}

async function cacheFirst(request, path) {
  const hit = await cached(path);
  if (!hit) return fetch(request);                   // not synced yet: the server, as before
  const range = request.headers.get("Range");
  if (!range) {
    const headers = new Headers(hit.headers);
    headers.set("Accept-Ranges", "bytes");
    return new Response(hit.body, { status: 200, headers });
  }
  return slice(hit, range);
}

/** A 206 cut out of a cached full response, or 416 when the range lies outside it. A
 *  multi-range or malformed header gets the whole body, which RFC 9110 allows. */
async function slice(response, range) {
  const blob = await response.blob();
  const size = blob.size;
  const headers = new Headers(response.headers);
  headers.set("Accept-Ranges", "bytes");
  const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
  if (!m || (!m[1] && !m[2])) {
    headers.set("Content-Length", String(size));
    return new Response(blob, { status: 200, headers });
  }
  let start, end;
  if (!m[1]) { start = Math.max(0, size - Number(m[2])); end = size - 1; }  // suffix: the last N
  else { start = Number(m[1]); end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1; }
  if (start >= size || start > end || (!m[1] && Number(m[2]) === 0)) {
    return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}`,
                                                        "Accept-Ranges": "bytes" } });
  }
  headers.set("Content-Range", `bytes ${start}-${end}/${size}`);
  headers.set("Content-Length", String(end - start + 1));
  return new Response(blob.slice(start, end + 1, blob.type), { status: 206, headers });
}

async function serverFirst(request, key) {
  const network = fetch(request);
  const hit = await cached(key);
  if (!hit) return network.catch(() => (request.mode === "navigate" ? needsServer() : Response.error()));
  network.catch(() => {});
  let timer;
  const timeout = new Promise((resolve) => { timer = setTimeout(() => resolve(null), TIMEOUT_MS); });
  const response = await Promise.race([network.catch(() => null), timeout]);
  clearTimeout(timer);
  if (response && !DOWN.has(response.status)) return response;
  return key === "" ? markedPage(hit) : hit;
}

/** The cached page, marked as the offline copy: the viewer reads `data-offline` on <html> at
 *  boot (09-live.js), hides what needs the server and says so. The value is when this copy of
 *  the page was fetched. */
async function markedPage(hit) {
  const synced = hit.headers.get("X-Pythia-Synced") || "0";
  const html = (await hit.text()).replace(/<html\b/i, `<html data-offline="${Number(synced) || 0}"`);
  const headers = new Headers(hit.headers);
  headers.delete("Content-Length");
  return new Response(html, { status: 200, headers });
}

function needsServer() {
  const home = SCOPE.pathname;
  return new Response(`<!DOCTYPE html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Pythia</title>
<body style="margin:0;background:#f3f3f4;color:#1c1b22;font:15px/1.5 Archivo,system-ui,-apple-system,sans-serif">
<div style="max-width:32rem;margin:15vh auto;padding:0 24px">
<h1 style="font:800 22px/1.2 inherit;margin:0 0 12px;padding-bottom:12px;border-bottom:2px solid #1c1b22">This page needs the Pythia server</h1>
<p>The server cannot be reached. The library, the graph and every synced PDF are still readable
from the offline copy; this page is built live and was not copied.</p>
<p><a href="${home}" style="color:#1f3f7a">Back to the library</a></p></div></body></html>`,
    { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
}
