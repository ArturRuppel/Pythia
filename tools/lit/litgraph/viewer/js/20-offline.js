// ── the offline copy ─────────────────────────────────────────────────────────────────────────
// The installed app keeps a read-only copy of itself — the page with its graph, the boot JSON,
// the views and every PDF — in Cache Storage, so tapping the icon with the server down still
// opens the library and every paper in it. viewer/sw.js answers from the copy; this module
// keeps it current. It runs on every open: GET offline.json (what the server has, each with a
// cheap size+mtime version), copy what is missing or changed, drop what the server no longer
// has. Each copy is stamped with its version as it lands, so an interrupted first sync of the
// whole library picks up at the next open where it stopped instead of starting over.
//
// It needs a secure context (the HTTPS of Tailscale Serve, or localhost) and a browser that
// keeps a worker; without one — plain http over the tailnet, a private window, a file:// build —
// it does nothing at all and the viewer behaves exactly as it always has. A static `lit build`
// on HTTPS hosting registers nothing either: it has no sw.js or offline.json to answer, and it
// is one self-contained file the browser's own cache already handles.
if (LIVE && !DETACHED) (function(){
  const supported = window.isSecureContext && "serviceWorker" in navigator && "caches" in window;
  if (!supported) return;
  const CACHE = "pythia-offline-v1", STATE = "pythia.offline", PARALLEL = 3;
  const base = new URL("./", location.href);
  const store = {
    get(){ try { return JSON.parse(localStorage.getItem(STATE)) || {}; } catch { return {}; } },
    set(v){ try { localStorage.setItem(STATE, JSON.stringify(v)); } catch {} },   // the copy still works
  };
  const size = b => b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB`
                 : b >= 1e6 ? `${Math.round(b / 1e6)} MB` : `${Math.max(1, Math.round(b / 1e3))} kB`;
  const when = t => new Date(t).toLocaleString([], {dateStyle: "medium", timeStyle: "short"});
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

  // ── the status chip ──
  // One line, bottom-left, above the app's tab bar. Progress while copying; once the copy is
  // current it says so for a few seconds and then folds to a small mark, since a working copy
  // is nothing to look at. Offline it stays open: it is the reason the write controls are gone.
  const el = document.createElement("button");
  el.id = "offline"; el.type = "button"; el.hidden = true;
  el.setAttribute("aria-live", "polite");
  document.body.appendChild(el);
  let foldTimer = null, action = null;
  function show(text, kind, then){
    clearTimeout(foldTimer);
    el.hidden = false; el.className = kind; el.textContent = text; el.title = text;
    action = then || null;
    if (kind === "ok") foldTimer = setTimeout(() => el.classList.add("folded"), 6000);
  }
  el.addEventListener("click", () => {
    if (el.classList.contains("folded")) { el.classList.remove("folded"); return; }
    if (action) action();
  });

  // Offline, a PDF the copy does not hold yet (a first sync that never finished) is as absent
  // as one the library lacks: trim the set the viewer offers so the gap is a plain "no PDF".
  async function trimPdfs(){
    if (!OFFLINE.on || !PDFS) return;
    try {
      const cache = await caches.open(CACHE), held = new Set();
      for (const r of await cache.keys()) {
        const m = /\/pdf\/([A-Za-z0-9]+)\.pdf$/.exec(new URL(r.url).pathname);
        if (m) held.add(m[1]);
      }
      PDFS = new Set([...PDFS].filter(k => held.has(k)));
    } catch {}
  }
  addEventListener("pdfsready", trimPdfs);

  function unreachable(){
    goOffline();
    trimPdfs();
    const st = store.get(), from = st.synced || OFFLINE.since;
    if (!from) return show("Server not reachable · no offline copy on this device yet", "off");
    show(`Server not reachable · offline copy from ${when(from)} · read-only`, "off",
         () => location.reload());
  }

  async function sync(){
    let r, manifest;
    try { r = await fetch("offline.json", {cache: "no-store"}); } catch { return unreachable(); }
    // 502-504 is a proxy (Tailscale Serve) in front of a server that is down; any other refusal
    // or a body that isn't the list is a host without the route — the labbook's mount, a static
    // build — which has nothing to keep and is not offline either
    if ([502, 503, 504].includes(r.status)) return unreachable();
    try { manifest = r.ok ? await r.json() : null; } catch { manifest = null; }
    if (!manifest || !Array.isArray(manifest.shell) || !Array.isArray(manifest.pdfs)) return;
    if (OFFLINE.on) {
      // this page came out of the copy (the server was slow or down at launch) and the server
      // has answered since: the live page is one reload away, so offer it, then keep copying
      show("Server is back · tap to reload the live library", "back", () => location.reload());
    }
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
    const run = () => copy(manifest);
    // one copier per device: a second window waits for the first instead of
    // fetching the same gigabyte alongside it
    if (navigator.locks) return navigator.locks.request("pythia-offline-sync", run);
    return run();
  }

  async function copy(manifest){
    const cache = await caches.open(CACHE);
    const items = [...manifest.shell, ...manifest.pdfs]
      .map(it => ({...it, href: new URL(it.url, base).href}));
    const pdfBytes = manifest.pdfs.reduce((s, it) => s + (it.size || 0), 0);
    // what is already here, at which version — read off the stamps the copies carry
    const held = new Set((await cache.keys()).map(r => r.url));
    const todo = [];
    for (const it of items) {
      const hit = held.has(it.href) ? await cache.match(it.href) : null;
      if (!hit || hit.headers.get("X-Pythia-Version") !== it.version) todo.push(it);
    }
    const total = todo.length, bytes = todo.reduce((s, it) => s + (it.size || 0), 0);
    let done = 0, got = 0, failed = 0, full = false;
    const started = Date.now();
    const progress = () => {
      if (OFFLINE.on || !total) return;          // "server is back" keeps the chip until reloaded
      show(`Syncing offline copy · ${done} of ${total}` + (bytes ? ` · ${size(got)} of ${size(bytes)}` : ""), "sync");
      el.style.setProperty("--done", (bytes ? got / bytes : done / total).toFixed(3));
    };
    progress();
    const queue = [...todo];
    const worker = async () => {
      for (let it = queue.shift(); it && !full; it = queue.shift()) {
        try {
          const r = await fetch(it.href, {cache: "no-store"});
          if (!r.ok) throw new Error(String(r.status));
          // Fresh headers rather than the server's: the body arrives decoded, so a stored
          // Content-Encoding or compressed Content-Length would describe bytes that aren't there.
          const headers = new Headers({"Content-Type": r.headers.get("Content-Type") || "application/octet-stream",
                                       "X-Pythia-Version": it.version, "X-Pythia-Synced": String(started)});
          if (it.size != null && !r.headers.get("Content-Encoding")) headers.set("Content-Length", String(it.size));
          await cache.put(it.href, new Response(r.body, {status: 200, headers}));
          got += it.size || 0;
        } catch (e) {
          failed += 1;
          if (e && e.name === "QuotaExceededError") full = true;   // more of the same won't fit either
        }
        done += 1;
        progress();
      }
    };
    await Promise.all(Array.from({length: PARALLEL}, worker));
    // drop what the server no longer has: a removed PDF, a view that went away
    const keep = new Set(items.map(it => it.href));
    for (const r of await cache.keys()) if (!keep.has(r.url)) await cache.delete(r);
    const missing = full ? queue.length + failed : failed;
    const st = {synced: Date.now(), pdfs: manifest.pdfs.length, bytes: pdfBytes, missing};
    store.set(st);
    if (OFFLINE.on) return;
    if (full) show(`Offline copy incomplete: storage is full · ${plural(missing, "file")} not copied`, "warn", () => sync());
    else if (failed) show(`Offline copy incomplete · ${plural(failed, "file")} could not be copied · tap to retry`, "warn", () => sync());
    else show(`Offline copy up to date · ${plural(st.pdfs, "PDF")} · ${size(st.bytes)}`, "ok", () => sync());
  }

  navigator.serviceWorker.register("sw.js").catch(() => {});   // a host without sw.js: nothing
  if (OFFLINE.on) unreachable();               // say so at once; the sync below may still find it
  sync().catch(() => {});
})();
