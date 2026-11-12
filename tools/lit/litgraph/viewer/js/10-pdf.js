// ── page raster sizing ───────────────────────────────────────────────────────────────────
// The server used to hand every client the same 1600px-wide PNG — about 1.1 MB per page, which
// on a phone is ~7x the bytes needed to fill a 390px-wide pane and the difference between a
// viewer that scrolls and one that stalls. Now the client asks for the width it will actually
// paint and the server snaps up to a shared rung (keep RUNGS in step with pdfview.WIDTHS).
const RUNGS = [480, 640, 828, 1100, 1600];
// Cap the device pixel ratio at 2: a 3x phone gains nothing legible on a rasterized page and
// pays 2.25x the bytes for it. Desktop dock at 44% of a 1440px window lands on 1100.
const DPR = Math.min(window.devicePixelRatio || 1, 2);
function rung(cssW, zoom){                          // narrowest rung that covers this paint width
  const want = Math.ceil(cssW * DPR * (zoom || 1));
  return RUNGS.find(r => want <= r) || RUNGS[RUNGS.length - 1];
}
// JPEG at the server's quality 82 is ~2.5x smaller than PNG for a rendered page and visually
// indistinguishable at reading zoom — these are photographs of text, not line art needing exact
// pixels. Highlights and the text overlay are DOM on top, so nothing lossy touches them.
const pageSrc = (key, n, w) => `page/${key}/${n}.jpg?w=${w}`;

// A page raster is fetched and decoded OFF the document and only then put on screen. The server's
// JPEGs are progressive (MuPDF writes nothing else), and an <img> that is already in the page
// paints whatever has arrived: on the iPad a transfer or decode that stopped after the first
// coarse scan left a page blurred at the top and blank below, for good — nothing retried, and a
// reload was handed the same half-finished resource. So: wait for the whole image (onload) and
// its decode; give up on an attempt that takes longer than RASTER_WAIT and ask again under a
// different URL (`&r=`), so the retry cannot be joined to the stuck request; after RASTER_TRIES
// reject, and the caller says so on the page instead of leaving it white.
const RASTER_WAIT = 20000, RASTER_TRIES = 3;
function loadRaster(src, attempt = 0){
  return new Promise((resolve, reject) => {
    const im = new Image(); im.className = "pw-img";
    let settled = false;
    const fail = () => {
      if (settled) return; settled = true; clearTimeout(timer);
      im.onload = im.onerror = null; im.removeAttribute("src");   // drop the stalled request
      if (attempt + 1 < RASTER_TRIES) loadRaster(src, attempt + 1).then(resolve, reject);
      else reject(new Error("raster"));
    };
    const ok = () => { if (settled) return; settled = true; clearTimeout(timer); resolve(im); };
    const timer = setTimeout(fail, RASTER_WAIT);
    im.onerror = fail;
    // onload means every byte is here; a decode that still rejects (memory) is the browser's to
    // redo at paint, and the image is whole either way
    im.onload = () => { im.decode ? im.decode().then(ok, ok) : ok(); };
    im.src = attempt ? `${src}&r=${attempt}` : src;
  });
}

// ── pages drawn on the device, from its own copy of the PDF ──────────────────────────────
// The offline copy (20-offline.js) already holds every PDF, and a file on the device cannot
// stall half way the way a page picture from the server can. So when the copy holds this paper,
// its pages are drawn here by pdf.js (vendor/pdfjs/, loaded on first use) and the server is asked
// for nothing but the small JSON — page sizes, word boxes, find hits. A PDF the copy does not
// hold yet, a browser without Cache Storage, or a pdf.js that will not load all fall back to the
// server's rasters (loadRaster), which is the whole of the old behaviour.
// A step that neither finishes nor fails must not hold the pane: pdf.js waiting on a worker that
// never started, or a render that hangs, would otherwise leave every later page blank.
function within(promise, ms, what){
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(what + " timed out")), ms);
    promise.then(v => { clearTimeout(t); resolve(v); }, e => { clearTimeout(t); reject(e); });
  });
}
const PDFJS_DIR = new URL("vendor/pdfjs/", document.baseURI).href;
const PDF_CACHE = "pythia-offline-v1";             // keep in step with 20-offline.js and sw.js
let pdfjsLib = null;
function pdfjs(){
  if (!pdfjsLib) pdfjsLib = import(PDFJS_DIR + "pdf.min.mjs").then(lib => {
    lib.GlobalWorkerOptions.workerSrc = PDFJS_DIR + "pdf.worker.min.mjs";
    return lib;
  }).catch(e => { pdfjsLib = null; throw e; });
  return pdfjsLib;
}
// One document open at a time: a parsed PDF is tens of MB in the worker, and the pane shows one
// paper. Re-mounts of the same paper (a resize, a new quote) reuse it. Resolves to null when the
// paper cannot be drawn here.
let pdfOpen = null;                                // {key, task, doc: Promise<PDFDocumentProxy|null>}
function openPdf(key){
  if (pdfOpen && pdfOpen.key === key) return pdfOpen.doc;
  if (pdfOpen) { const old = pdfOpen; old.doc.then(() => { if (old.task) old.task.destroy(); }); }
  const o = pdfOpen = {key, task: null};
  o.doc = (async () => {
    if (!window.isSecureContext || !("caches" in window)) return null;
    const cache = await caches.open(PDF_CACHE);
    const hit = await cache.match(new URL(`pdf/${encodeURIComponent(key)}.pdf`, document.baseURI).href);
    if (!hit) return null;                         // not synced to this device yet
    // the bytes are handed over whole, straight out of the copy: no range requests, and no
    // dependence on the service worker being the one to answer them
    const [lib, data] = await Promise.all([within(pdfjs(), 15000, "pdf.js load"), hit.arrayBuffer()]);
    o.task = lib.getDocument({data, wasmUrl: PDFJS_DIR + "wasm/", iccUrl: PDFJS_DIR + "iccs/",
                              standardFontDataUrl: PDFJS_DIR + "standard_fonts/",
                              isEvalSupported: false});
    return await within(o.task.promise, 15000, "open");
  })().catch(() => { if (o.task) o.task.destroy(); if (pdfOpen === o) pdfOpen = null; return null; });
  return o.doc;
}
async function pdfSizes(doc){                      // [[w,h],…] — the /pages manifest, read locally
  const out = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const vp = (await doc.getPage(n)).getViewport({scale: 1});
    out.push([vp.width, vp.height]);
  }
  return out;
}
// Draw page `n` at `want` px wide onto a fresh canvas, which is put on screen only once it is
// finished. One page at a time: the worker is single-threaded anyway, and a queue lets a page the
// reader has already scrolled past (`live()` false) be skipped instead of drawn for nothing.
const PDF_MAX_PX = 4e6;                            // pdfview._MAX_PX: the oversized-mediabox guard
let pdfQueue = Promise.resolve();
function drawPage(doc, n, want, live){
  const job = pdfQueue.then(async () => {
    if (!live()) throw new Error("stale");
    const page = await within(doc.getPage(n + 1), 10000, "getPage");
    const base = page.getViewport({scale: 1});
    let scale = want / base.width;
    const px = base.width * scale * base.height * scale;
    if (px > PDF_MAX_PX) scale *= Math.sqrt(PDF_MAX_PX / px);
    const viewport = page.getViewport({scale});
    const cv = document.createElement("canvas"); cv.className = "pw-img";
    cv.width = Math.round(viewport.width); cv.height = Math.round(viewport.height);
    const task = page.render({canvas: cv, canvasContext: cv.getContext("2d", {alpha: false}), viewport});
    try { await within(task.promise, 20000, "render"); }
    catch (e) { try { task.cancel(); } catch {} freeRaster(cv); throw e; }
    page.cleanup();
    return cv;
  });
  pdfQueue = job.catch(() => {});
  return job;
}
// iOS counts canvas memory against a fixed budget and frees it lazily; zeroing the size gives it
// back at once.
function freeRaster(el){ if (el && el.tagName === "CANVAS") el.width = el.height = 0; }

// ── PDF quote location resolution ────────────────────────────────────────────────────────
// A slice's weld is no longer shown as text — the PDF *is* the link. The quote's location is
// resolved from its stored quote_loc (lit locate) or live server-side (/resolve → page +
// highlight rects) and cached per session; the page is rendered by /page/<key>/<n>.jpg.
// Live only — needs `lit serve`.
const locCache = new Map();                        // "key:sid" -> {page,rects} | null (a miss)
async function resolveLoc(key, sid){
  const qid = `${key}:${sid}`;
  if (locCache.has(qid)) return locCache.get(qid);
  const s = (PAPERS[key] && PAPERS[key].slices || []).find(x => x.id === sid);
  let loc = null;
  if (s && s.loc && s.loc.rects && s.loc.rects.length) {
    loc = s.loc;                                   // stored (lit locate) — exact + instant
  } else if (s && s.quote) {
    try { loc = await fetch("resolve", {method: "POST",   // not yet stored → resolve live
      headers: {"Content-Type": "application/json"},     // the server refuses any other type
      body: JSON.stringify({citekey: key, quote: s.quote})}).then(r => r.ok ? r.json() : null); }
    catch { loc = null; }
  }
  locCache.set(qid, loc); return loc;
}
const idKey = cardId => cardId.slice(cardId.indexOf(":") + 1);

// ── collapsible PDF viewer (browse view, live-only) ──────────────────────────────────────
// One docked pane on the right, toggled from the HUD. While OPEN, hovering a quote-slice aims
// it at that claim's citation (resolveLoc → mountDoc); while collapsed, hover is inert. No
// floating windows and no server-side round-trip to keep in sync — hover drives mountDoc
// directly, in this same window. The pane rests on the last-hovered claim when the pointer
// leaves; a non-quote row leaves it put.
let dockOpen = false, dockWin = null, dockShown = null, dockReq = null, dockTimer = null;
let dockDoc = null, dockRefitTimer = null;             // dockDoc = last mount {key,page,rects} (for refit)
// ── detachable PDF pane ──────────────────────────────────────────────────────────────────
// The dock can DETACH into its own OS window (window.open of index.html?detached=1) so the PDF
// can live on a second monitor. The child runs this same viewer in "detached" mode: no graph,
// just a full-bleed PDF pane. Parent and child stay in sync over a BroadcastChannel — the parent
// broadcasts {t:"aim",key,page,rects} on the SAME hover that would aim the in-page dock, and the
// child mounts it. `dockDoc` stays the single source of truth for what's shown; `renderCurrent`
// paints it wherever the PDF currently lives (in-page dock, or broadcast to the detached child).
let pdfDetached = false, pdfWin = null, pdfWatch = null;
const pdfChan = (LIVE && !DETACHED && "BroadcastChannel" in window) ? new BroadcastChannel("lit-pdf") : null;
const pdfActive = () => dockOpen || pdfDetached;       // hover aims the PDF while EITHER home is live
function broadcastAim(){ if (pdfChan && dockDoc) pdfChan.postMessage({t: "aim", ...dockDoc}); }
function renderCurrent(){ if (pdfDetached) broadcastAim(); else if (dockOpen) mountDockDoc(); }
function pdfDetachTeardown(){                           // the detached window is gone (closed / re-attached)
  pdfDetached = false; pdfWin = null;
  if (pdfWatch) { clearInterval(pdfWatch); pdfWatch = null; }
}
if (pdfChan) pdfChan.onmessage = e => {                 // messages FROM the detached child
  const m = e.data; if (!m) return;
  if (m.t === "ready") broadcastAim();                 // child booted → (re)send the current aim
  else if (m.t === "closed") pdfDetachTeardown();      // child window closed → drop detached state
};
// reopen THIS exact URL with ?detached=1 — robust to whatever path the viewer is mounted under
// (a hardcoded "index.html" resolves relative to the base and breaks under a prefix / no-slash mount).
function detachedUrl(){ const u = new URL(location.href); u.searchParams.set("detached", "1"); u.hash = ""; return u.href; }
function detachDock(){
  if (!pdfChan) { window.open(detachedUrl(), "litpdf"); return; }   // no channel: fire-and-forget
  const keep = dockDoc, keepShown = dockShown;         // collapse the in-page dock but KEEP what's shown
  dockOpen = false; document.body.classList.remove("dock-open");
  if (pdfToggle) pdfToggle.classList.remove("on");
  if (dockWin) { dockWin.remove(); dockWin = null; }
  pdfDetached = true; dockDoc = keep; dockShown = keepShown;
  if (pdfWin && !pdfWin.closed) { pdfWin.focus(); broadcastAim(); return; }
  pdfWin = window.open(detachedUrl(), "litpdf",
                       "popup,width=880,height=1040,left=120,top=60");
  pdfWatch = setInterval(() => { if (!pdfWin || pdfWin.closed) pdfDetachTeardown(); }, 1000);
  broadcastAim();                                       // child re-asks on ready; this covers a warm reuse
}
function reattachDock(){                                // bring the PDF back into the page (📄 while detached)
  const keep = dockDoc;
  if (pdfWin && !pdfWin.closed) pdfWin.close();
  pdfDetachTeardown();
  dockDoc = keep; openDock();
  if (keep) mountDockDoc();
}
// The PDF is opened EXPLICITLY — by the 📄 pill, never as a side effect of reading the graph.
// Opening a card used to force the dock open and load that paper, which meant every click while
// browsing threw a PDF across half the screen; with a library this size that is almost always in
// the way. So the pill is the only door, and it lands on whatever the last claim-click aimed at
// (recorded even while the dock was shut), falling back to the focused paper's page 1.
function focusedKey(){                                 // most recently focused card (Set = insertion order)
  let k = null;
  for (const id of open) { const kk = idKey(id); if (PAPERS[kk]) k = kk; }
  return k;
}
function openDock(){
  if (dockOpen) return;
  dockOpen = true; document.body.classList.add("dock-open");
  if (pdfToggle) pdfToggle.classList.add("on");
  if (dockDoc) mountDockDoc();                         // the remembered aim, highlight and all
  else { const k = focusedKey(); if (k) loadDock(k); } // nothing aimed yet → the open paper, page 1
}
function closeDock(){
  dockOpen = false; document.body.classList.remove("dock-open");
  if (pdfToggle) pdfToggle.classList.remove("on");
  clearTimeout(dockTimer);
  if (dockWin) { dockWin.remove(); dockWin = null; }
  dockShown = null; dockReq = null; dockDoc = null;
}
function toggleDock(){
  if (pdfDetached) return reattachDock();              // detached → the pill re-docks it here
  dockOpen ? closeDock() : openDock();
}
// (re)mount the dock's remembered doc at the current width — buildWin is fresh each time so
// listeners never stack. Used by aimDock/loadDock and by the resize re-fit.
function mountDockDoc(){
  if (!dockDoc) return;
  const d = dockDoc;
  if (dockWin) dockWin.remove();
  dockWin = buildWin(d.key, d.rects.length ? `p.${d.page + 1}` : "full paper",
                     {onClose: closeDock, onDetach: detachDock});
  dockWin.classList.add("pw-side");                    // fixed right pane (CSS) — before mount
  mountDoc(dockWin, d.key, d.page, d.rects.slice(), {interactive: true});
}
function scheduleDockRefit(){ clearTimeout(dockRefitTimer);
  dockRefitTimer = setTimeout(() => { if (dockOpen && dockDoc) mountDockDoc(); }, 140); }
// Load a paper's whole PDF (page 1, no highlight) — the coarse "show me this paper" entry, used
// by openDock when no claim has aimed it yet. It does not open the dock itself: opening is the
// pill's job, and nothing here should put a PDF on screen that the human didn't ask for.
function loadDock(key){
  if (!LIVE || !(PDFS && PDFS.has(key))) return;   // nothing servable → skip
  const qid = `${key}:__paper__`;
  if (qid === dockShown) { if (pdfDetached && pdfWin && !pdfWin.closed) pdfWin.focus(); return; }
  clearTimeout(dockTimer); dockReq = qid;
  dockDoc = {key, page: 0, rects: []};
  renderCurrent();
  if (pdfDetached && pdfWin && !pdfWin.closed) pdfWin.focus();   // card click brings the detached window forward
  dockShown = qid;
}

// hover a quote-slice → aim the open dock at it (debounced so pass-through hovers don't thrash)
function aimDockFromHover(h){
  clearTimeout(dockTimer);
  if (!pdfActive() || !HOVER) return;
  const key = h && h.sid ? idKey(h.cardId) : null;
  const s = key ? (PAPERS[key] && PAPERS[key].slices || []).find(x => x.id === h.sid) : null;
  if (!LIVE || !s || !s.quote) return;             // non-quote row / card body: leave the pane put
  dockTimer = setTimeout(() => aimDock(key, h.sid), 180);
}
async function aimDock(key, sid){
  const qid = `${key}:${sid}`;
  if (qid === dockShown) return;                    // already parked on this claim
  dockReq = qid;
  const loc = await resolveLoc(key, sid) || {page: 0, rects: []};
  if (dockReq !== qid) return;                      // a newer aim (or closeDock) superseded this one
  // Recorded even with the PDF shut — renderCurrent is then a no-op, but the aim survives, so an
  // explicit 📄 afterwards opens ON the claim you clicked instead of on page 1.
  dockDoc = {key, page: loc.page || 0, rects: loc.rects.slice()};
  renderCurrent();
  dockShown = qid;
}
// Split resize (persisted per axis): the grip sits on the seam between graph and PDF — the dock's
// left edge in landscape, its top edge in portrait — and one handler drives both, reading the axis
// off the orientation at pointerdown. Pointer events, so a finger drags it as well as a mouse.
// Only a WIDTH change needs the re-fit: mountDoc bakes the page width into its layout, while the
// height is just how much of the scroll body you can see, so a portrait drag keeps its scroll spot.
const SPLIT_MIN = 0.2, SPLIT_MAX = 0.8;
if (LIVE) {
  const grip = document.getElementById("dockGrip");
  const KEY = {w: "lit.dock.w", h: "lit.dock.h"};
  const portrait = () => matchMedia("(orientation:portrait)").matches;
  for (const ax of ["w", "h"]) {
    try { const v = parseFloat(localStorage.getItem(KEY[ax]));
          if (v >= SPLIT_MIN && v <= SPLIT_MAX)
            document.body.style.setProperty(`--dock-${ax}`, (v * 100) + "%"); } catch {}
  }
  if (grip) grip.addEventListener("pointerdown", e => {
    e.preventDefault();
    const ax = portrait() ? "h" : "w";
    document.body.classList.add("dock-resizing");
    document.body.style.cursor = ax === "h" ? "ns-resize" : "ew-resize";
    let f = 0;
    const move = ev => {
      f = ax === "h" ? (innerHeight - ev.clientY) / innerHeight
                     : (innerWidth - ev.clientX) / innerWidth;
      f = Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, f));
      document.body.style.setProperty(`--dock-${ax}`, (f * 100) + "%");
    };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      document.body.classList.remove("dock-resizing");
      document.body.style.cursor = "";
      if (f) { try { localStorage.setItem(KEY[ax], f.toString()); } catch {} }
      if (ax === "w") scheduleDockRefit();          // baked page width changed; height is free
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  });
  // a rotate fires resize and swaps the axis, which does change the pane's width — re-fit
  addEventListener("resize", () => { if (dockOpen) scheduleDockRefit(); });
}

// ── the HUD gets out of the way ──────────────────────────────────────────────────────────
// The bar is ~46px of chrome, which on a phone is real estate the graph wants back. It slides
// away as you scroll down the board and returns the moment you scroll up or reach the top — what
// a mobile browser does with its own toolbar. It only ever moves ITSELF: the board is full-height
// and merely pads its top by the measured bar height, so nothing reflows and the scroll never
// jumps. The dock hangs from --hud-top, so the PDF grows into the space at the same time.
// `hudQuiet` is how a scroll the CODE performed says so. Zooming the board keeps the point under
// the cursor fixed, which means moving scrollTop — and the bar read that as the reader scrolling
// down and slid away, taking the zoom slider out from under the hand still dragging it. A scroll
// nobody asked for is not a signal about where the reader's attention is going.
let hudQuiet = 0;                       // performance.now() before which scrolls aren't the reader's
if (!DETACHED) (function(){
  const hud = document.getElementById("hud");
  if (!hud) return;
  const measure = () => document.body.style.setProperty("--hud-h", hud.offsetHeight + "px");
  measure();
  // Controls below are revealed after this module runs. On a narrow viewport that can wrap the
  // HUD onto another row without resizing the window, so a window-only listener leaves the new
  // row over the first card. Observe the bar itself: its rendered height is the inset's source of
  // truth, whether the change came from viewport size, late content, or font/layout settling.
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(measure).observe(hud);
  else addEventListener("resize", measure);
  const THRESH = 28;                    // px travelled one way before the bar commits to a move
  let last = 0, run = 0;
  board.addEventListener("scroll", () => {
    const y = Math.max(0, board.scrollTop), d = y - last;
    last = y;
    if (performance.now() < hudQuiet) { run = 0; return; }   // ours, not the reader's
    if (!d) return;                     // horizontal scroll (fanning out columns) leaves it alone
    run = (d > 0) === (run > 0) ? run + d : d;   // distance travelled since the last turnaround
    if (y < 24) { run = 0; document.body.classList.remove("hud-off"); return; }   // top: always shown
    if (run > THRESH && !document.body.classList.contains("hud-off")) {
      document.body.classList.add("hud-off");
      closeSearch();                    // the dropdown is pinned under a box that just left
    } else if (run < -THRESH) document.body.classList.remove("hud-off");
  }, {passive: true});
})();

// ── right-click a curated card → Validate it (serve, browse view) ─────────────────────────────
// The desk (SCHEMA §4): Validate records the paper's current pass as the one the owner has
// validated (POST /validate, validatePaper in 14-search.js); the levels below it are there for a
// paper read less deeply than curation ran. It settles in place — the card's status swaps, the
// desk pill recounts — with nothing to reload: validating adds or removes no card or arrow.
// Offline, the menu still opens, its entries disabled with the reason beside them.
const ctxmenu = document.getElementById("ctxmenu");
function hideCtxMenu(){ ctxmenu.style.display = "none"; ctxmenu.onclick = null; }
function showDeskMenu(e, key){
  e.preventDefault();
  const p = PAPERS[key], m = curPass(p), v = p.validated;
  const off = OFFLINE.on ? ` disabled title="${OFFLINE_WHY}"` : "";
  const item = (n, text) => `<button data-v="${n}"${off || (n === v ? " disabled" : "")}>${text}</button>`;
  let h = `<div class="ctx-hd">${v == null ? "new · never validated" : `validated ${v} · ${passLabel(v)}`}</div>`
    + item(m, v === m ? `Validated · ${m} ${passLabel(m)}` : `Validate · ${m} ${passLabel(m)}`);
  if (m > 0) h += `<div class="ctx-sub">or at a lower level</div>`
    + Array.from({length: m}, (_, i) => m - 1 - i).map(n => item(n, `${n} ${passLabel(n)}`)).join("");
  if (OFFLINE.on) h += `<div class="ctx-why">${OFFLINE_WHY}</div>`;
  ctxmenu.innerHTML = h;
  ctxmenu.style.display = "block";
  const w = ctxmenu.offsetWidth || 150, ht = ctxmenu.offsetHeight || 34;
  ctxmenu.style.left = Math.min(e.clientX, innerWidth - w - 8) + "px";
  ctxmenu.style.top = Math.min(e.clientY, innerHeight - ht - 8) + "px";
  ctxmenu.onclick = ev => {
    const b = ev.target.closest("button"); if (!b || b.disabled) return;
    hideCtxMenu();
    validatePaper(key, +b.dataset.v).catch(() => alert(`Could not validate ${key}. Please try again.`));
  };
}
addEventListener("click", hideCtxMenu);          // any left-click dismisses the menu
addEventListener("scroll", hideCtxMenu, true);   // scrolling the board dismisses it too

// A window shell: titlebar (key · page · pan/text tools · ×) + a scrollable body holding a sizer
// (owns the scroll extent) and a stage (image + highlights + text layer, under one scale). Both
// callers dock it via CSS (curate focus pane / browse viewer); `at` seeds a free-floating place
// for any future caller, but a docked pane's !important rules win over it.
function buildWin(key, sub, {onClose, at, onDetach} = {}){
  const win = document.createElement("div");
  win.className = "pw";
  win.dataset.tool = "pan";
  const detach = onDetach ? `<button class="pw-tool" data-t="detach" title="detach to its own window">⧉</button>` : "";
  // The find button and bar are chrome, so they're built here — but they stay hidden until a
  // mount claims them: only the whole-document view (mountDoc) can honestly search a PDF, and
  // the single-page fallback would otherwise offer a search over 1/20th of the paper.
  // Same rule for the zoom stepper: wireZoom reveals it, so the hover tooltip's soft preview —
  // which mounts non-interactively — doesn't advertise a control that does nothing there.
  win.innerHTML =
    `<div class="pw-bar"><b>${key}</b><span class="pw-sub">${sub}</span><span class="sp"></span>`
    + `<span class="pw-zoom" hidden title="zoom this PDF — drag, ctrl/⌘-wheel, or + / − / 0">`
    + `<input type="range" min="0" max="1000" step="1" value="0">`
    + `<span class="pz-val" title="back to fit-width (0)">100%</span></span>`
    + `<span class="pw-tools"><button class="pw-tool" data-t="find" title="find in this PDF (ctrl/⌘-F)" hidden>🔍</button>`
    + `<button class="pw-tool" data-t="pan" title="pan (drag)">✥</button>`
    + `<button class="pw-tool" data-t="text" title="select text">I</button>${detach}</span>`
    + `<span class="pw-x" title="close">×</span>`
    + `</div>`
    + `<div class="pw-find"><input type="search" placeholder="find in this PDF"`
    + ` autocomplete="off" spellcheck="false" enterkeyhint="search">`
    + `<span class="pw-fn"></span>`
    + `<button class="pw-fb" data-f="prev" title="previous (shift-enter)">‹</button>`
    + `<button class="pw-fb" data-f="next" title="next (enter)">›</button>`
    + `<button class="pw-fb" data-f="close" title="close (esc)">×</button></div>`
    + `<div class="pw-body"><div class="pw-loading">rendering page…</div>`
    + `<div class="pw-sizer"><div class="pw-stage"></div></div></div>`
    + `<div class="pw-grip"></div>`;
  document.body.appendChild(win);
  if (at) { win.style.left = at.left + "px"; win.style.top = at.top + "px"; }
  dragBy(win.querySelector(".pw-bar"), (dx, dy, l, t) => { win.style.left = l + dx + "px"; win.style.top = t + dy + "px"; },
         // the guard names every control ON the titlebar: the bar is a drag handle, and dragBy
         // eats the pointerdown, so anything left out of this list can never be clicked or dragged
         () => [win.offsetLeft, win.offsetTop], ".pw-x,.pw-tool,.pw-zoom");
  dragBy(win.querySelector(".pw-grip"), (dx, dy, w, h) => { win.style.width = Math.max(240, w + dx) + "px"; win.style.height = Math.max(160, h + dy) + "px"; },
         () => [win.offsetWidth, win.offsetHeight]);
  win.querySelector(".pw-x").addEventListener("click", onClose);
  if (onDetach) win.querySelector('.pw-tool[data-t=detach]').addEventListener("click", onDetach);
  return win;
}

// A zoom slider's track is LOG-spaced, and both zooms use this to map one. Zoom multiplies: half
// and double are the same move in opposite directions, so they have to sit the same distance
// either side of 100%. A linear track would crush the entire zoom-out half of the board's range
// into a fifth of the bar and give the last stretch of zoom-in most of it — the reader would be
// fighting the control at exactly the end they reach for when the board stops fitting.
// 0..1000 ticks is finer than any track is wide, so the slider is continuous in practice.
const zoomSlider = {
  toTrack: (z, min, max) => Math.round(1000 * Math.log(z / min) / Math.log(max / min)),
  toZoom(v, min, max){
    const z = min * Math.pow(max / min, v / 1000);
    return Math.abs(Math.log(z)) < 0.04 ? 1 : z;   // 100% is worth being able to land on by hand
  },
};

// ── zoom, shared by both PDF mounts ──────────────────────────────────────────────────────
// Both mounts lay a page out the same way — a sizer owning the scroll extent, a stage under one
// scale() — so the zoom is one function over that pair, and the only thing they differ on
// arrives as `sharpen`: what "fetch it sharper" means when the reader zooms past the rung the
// raster was cut at (one image, or every page currently on screen).
// This is NOT the board's zoom (BOARD_ZOOM). They sit side by side and are read from different
// distances — a page at 200% beside a board at 60% is the ordinary way to curate — so they
// share no state, no control and no key.
// Remembered across mounts, because aiming at the next quote is not a request to stand back up:
// without that, every hover reset the page to fit-width and the zoom read as not being there.
// Fit-width stays the floor: below it a page is a stamp in a field of grey, and the dock is
// already as narrow as the reading ever gets.
function wireZoom(win, view, {body, sizer, stage, sharpen, interactive = true}){
  const MIN = 1, MAX = 12, STEP = 1.35, KEY = "lit.pdf.zoom";
  const ctl = interactive ? win.querySelector(".pw-zoom") : null;
  const slider = ctl && ctl.querySelector("input");
  const clamp = z => Math.max(MIN, Math.min(MAX, z || 1));
  const paint = () => {
    if (!ctl) return;
    ctl.hidden = false;
    ctl.querySelector(".pz-val").textContent = Math.round(view.z * 100) + "%";
    slider.value = String(zoomSlider.toTrack(view.z, MIN, MAX));
  };
  // Lay the stage out at `z` and leave the scroll alone — what a fresh mount wants, since it is
  // about to scroll to its highlight itself.
  const layout = z => {
    view.z = clamp(z);
    sizer.style.width = view.W0 * view.z + "px";
    sizer.style.height = view.H0 * view.z + "px";
    stage.style.transform = `scale(${view.z})`;
    const r = rung(view.W0 || body.clientWidth, view.z);   // zoomed past this raster → sharpen
    if (r > view.rw) { view.rw = r; sharpen(); }
    paint();
  };
  // …and with the scroll: keep whatever is under (cx,cy) on the glass under (cx,cy).
  const to = (z1, cx, cy) => {
    const z0 = view.z, ax = body.scrollLeft + cx, ay = body.scrollTop + cy;
    layout(z1);
    body.scrollLeft = ax / z0 * view.z - cx; body.scrollTop = ay / z0 * view.z - cy;
    try { localStorage.setItem(KEY, String(view.z)); } catch {}
  };
  const mid = z => { const r = body.getBoundingClientRect(); to(z, r.width / 2, r.height / 2); };
  const api = {layout, to,
    // the distance the reader last chose — 1 for a non-interactive mount, which is a thumbnail
    // and has no business inheriting a reading zoom
    stored(){ if (!interactive) return 1;
              try { return clamp(parseFloat(localStorage.getItem(KEY))); } catch { return 1; } },
    in(){ mid(view.z * STEP); }, out(){ mid(view.z / STEP); }, reset(){ mid(1); }};
  if (!interactive) return api;
  win._zoom = api;                                 // the +/−/0 keys reach the PDF through this
  // Dragging the track zooms about the middle of the page you can see, which is the bit you are
  // reading — zooming about a corner would slide the text out from under you.
  slider.addEventListener("input", () => mid(zoomSlider.toZoom(+slider.value, MIN, MAX)));
  ctl.querySelector(".pz-val").addEventListener("click", () => api.reset());
  body.addEventListener("wheel", e => {            // ctrl/⌘-wheel (and trackpad pinch) zooms; plain wheel scrolls
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const r = body.getBoundingClientRect();
    to(view.z * Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  return api;
}
// Open on the quote. Both mounts hand this the highlight's boxes in ZOOMED px — the space the
// scroll offsets live in — as the whole quote (`box`) and its opening line (`head`).
// Centre the whole thing, which is what fit-width always did and still does. But a quote is
// several lines and, zoomed in, wider or taller than the port: the centre of a three-line quote
// that starts at 70% across the page puts its opening off the right edge, which is the one part
// the reader is actually looking for. So the centring is clamped to keep `head` in frame, and
// the clamp is ordered so that a head bigger than the port shows its START. At fit-width every
// clamp is inert and the behaviour is exactly what it was.
function showQuote(body, box, head){
  const M = 24;                                    // a little air, so the line isn't flush to the edge
  let sl = (box.x0 + box.x1) / 2 - body.clientWidth / 2;
  let st = (box.y0 + box.y1) / 2 - body.clientHeight / 2;
  if (head) {
    sl = Math.min(Math.max(sl, head.x1 - body.clientWidth + M), head.x0 - M);
    st = Math.min(Math.max(st, head.y1 - body.clientHeight + M), head.y0 - M);
  }
  body.scrollLeft = Math.max(0, Math.min(body.scrollWidth  - body.clientWidth,  sl));
  body.scrollTop  = Math.max(0, Math.min(body.scrollHeight - body.clientHeight, st));
}
function unionBox(bs){
  return {x0: Math.min(...bs.map(b => b.x0)), x1: Math.max(...bs.map(b => b.x1)),
          y0: Math.min(...bs.map(b => b.y0)), y1: Math.max(...bs.map(b => b.y1))};
}

// Render page `page` into `win`'s scroll body: the page image + highlight overlays (page
// fractions) live on a fixed-base-width stage; a sizer sibling owns the scroll extent and a
// single scale() transform does zoom, so highlights and the text layer never need per-element
// recompute. Opens at fit-width with the highlight scrolled into view. opts.interactive wires
// ctrl/⌘-wheel zoom + drag-pan + the pan/text tool toggle (skipped for the soft preview).
function mountPage(win, key, page, rects, opts){
  const body = win.querySelector(".pw-body");
  const sizer = win.querySelector(".pw-sizer"), stage = win.querySelector(".pw-stage");
  const img = new Image(); img.className = "pw-img"; stage.appendChild(img);
  for (const r of rects) {
    const hl = document.createElement("div"); hl.className = "pw-hl";
    hl.style.left = (r[0] * 100) + "%"; hl.style.top = (r[1] * 100) + "%";
    hl.style.width = ((r[2] - r[0]) * 100) + "%"; hl.style.height = ((r[3] - r[1]) * 100) + "%";
    stage.appendChild(hl);
  }
  const view = {z: 1, W0: 0, H0: 0};             // W0/H0 = base (fit-width) page size in px
  const interactive = opts.interactive !== false;
  view.rw = rung(body.clientWidth, 1);           // raster rung in force; grows as the user zooms
  let ready; win._ready = new Promise(r => ready = r);   // text layer waits on W0/H0 being known
  const zoom = wireZoom(win, view, {body, sizer, stage, interactive,
    sharpen: () => {                             // one page here — swap this raster for a sharper cut
      const next = new Image();                  // decode off-screen, then swap: no blink
      next.onload = () => { img.src = next.src; };
      next.src = pageSrc(key, page, view.rw);
    }});
  img.onload = () => {
    // Only the first raster lays the stage out. A sharper one swapped in by the zoom fires onload
    // again, and re-running this would snap the reader back to fit-width mid-zoom.
    if (view.laidOut) return;
    view.laidOut = true;
    const load = win.querySelector(".pw-loading"); if (load) load.remove();
    view.W0 = body.clientWidth;                  // fit-width (scrollbar-gutter keeps this stable)
    view.H0 = view.W0 * (img.naturalHeight / img.naturalWidth);
    stage.style.width = view.W0 + "px";
    zoom.layout(zoom.stored());                  // fit-width, or the distance last chosen
    if (rects.length) {                          // …and open on the quote, at that zoom
      const bs = rects.map(r => ({x0: r[0] * view.W0 * view.z, x1: r[2] * view.W0 * view.z,
                                  y0: r[1] * view.H0 * view.z, y1: r[3] * view.H0 * view.z}));
      showQuote(body, unionBox(bs), bs[0]);
    }
    ready();
  };
  img.onerror = () => { const l = win.querySelector(".pw-loading"); if (l) l.textContent = "page render failed"; };
  img.decoding = "async";
  img.src = pageSrc(key, page, view.rw);
  if (!interactive) return;

  body.addEventListener("pointerdown", e => {    // pan tool: drag scrolls (text tool: browser selects)
    if (e.pointerType === "touch") return;       // native scroll owns touch; drag-pan is mouse-only
    if (e.button !== 0 || win.dataset.tool !== "pan") return;
    body.classList.add("pan"); body.setPointerCapture(e.pointerId);
    const sx = e.clientX, sy = e.clientY, l0 = body.scrollLeft, t0 = body.scrollTop;
    const mv = ev => { body.scrollLeft = l0 - (ev.clientX - sx); body.scrollTop = t0 - (ev.clientY - sy); };
    const up = () => { body.classList.remove("pan"); body.removeEventListener("pointermove", mv); body.removeEventListener("pointerup", up); };
    body.addEventListener("pointermove", mv); body.addEventListener("pointerup", up);
  });
  win.querySelector(".pw-tools").addEventListener("click", e => {   // pan / text-select toggle
    const b = e.target.closest(".pw-tool"); if (!b) return;
    if (b.dataset.t !== "pan" && b.dataset.t !== "text") return;    // e.g. ⧉ detach — not a viewer tool
    win.dataset.tool = b.dataset.t;
    if (b.dataset.t === "text") ensureTextLayer(win, key, page, view);
  });
}
// A transparent selectable text layer (pdf.js trick): one absolutely-positioned span per word,
// placed in base-px coords on the stage so the scale transform keeps it registered on the raster.
// Each span's glyph run is scaleX-fit to its raster word box so drag-selection tracks the page.
// Built once, on first entry to text mode; native Ctrl+C copies the selection.
async function ensureTextLayer(win, key, page, view){
  if (win._textBuilt) return; win._textBuilt = true;
  let words = [];
  try { words = await fetch(`words/${key}/${page}.json`).then(r => r.ok ? r.json() : []); }
  catch { words = []; }
  await win._ready;                              // W0/H0 known
  if (!win.isConnected || !words.length) return;
  const stage = win.querySelector(".pw-stage"), layer = document.createElement("div");
  layer.className = "pw-text";
  const W0 = view.W0, H0 = view.H0, spans = [];
  for (const w of words) {
    const sp = document.createElement("span");
    sp.style.left = (w.x0 * W0) + "px"; sp.style.top = (w.y0 * H0) + "px";
    sp.style.fontSize = Math.max(4, (w.y1 - w.y0) * H0) + "px";
    sp.textContent = w.t;                        // measure the word alone; space appended after
    layer.appendChild(sp); spans.push([sp, (w.x1 - w.x0) * W0]);
  }
  stage.appendChild(layer);
  for (const [sp, targetW] of spans) {           // read widths in one batch (after all writes), then fit
    const natW = sp.offsetWidth;
    if (natW > 0) sp.style.transform = `scaleX(${targetW / natW})`;
    sp.appendChild(document.createTextNode(" "));   // word separation for copied text
  }
}

// Full-document viewer for a pinned window: the whole PDF as a lazily-rendered stack of page
// boxes (one per page, sized from the /pages manifest), opened scrolled to the quote's page with
// the highlight in view. A page renders — and, in text mode, grows its selectable overlay — only
// as it nears the viewport, so a long PDF stays cheap. Falls back to a single page if the manifest
// can't be read. Ctrl/⌘-wheel zooms, plain wheel scrolls, the titlebar tracks the current page.
async function mountDoc(win, key, page, rects, opts){
  const body = win.querySelector(".pw-body");
  const sizer = win.querySelector(".pw-sizer"), stage = win.querySelector(".pw-stage");
  const view = {z: 1, W0: 0, H0: 0};             // H0 = the whole stack's base height
  let ready; win._ready = new Promise(r => ready = r);
  const docP = openPdf(key);                      // the device's own copy, or null (→ server rasters)
  let sizes = [];
  if (OFFLINE.on) {
    // No server: the pages come from the copy or not at all. Sizes are read off the PDF; the
    // word boxes and find are server-side, so those two tools stay away.
    const doc = await docP;
    if (!win.isConnected) return;
    if (!doc) return mountCopy(win, key, page);   // pdf.js unavailable: the browser's own viewer
    try { sizes = await pdfSizes(doc); } catch { sizes = []; }
    if (!win.isConnected) return;
    if (!sizes.length) return mountCopy(win, key, page);
    const tb = win.querySelector('.pw-tool[data-t="text"]'); if (tb) tb.hidden = true;
  } else {
    try { sizes = await fetch(`pages/${key}.json`).then(r => r.ok ? r.json() : []); } catch { sizes = []; }
  }
  if (!win.isConnected) return;
  if (!sizes.length) return mountPage(win, key, page, rects, opts);   // manifest unreadable → one page
  const load = win.querySelector(".pw-loading"); if (load) load.remove();
  const GAP = 8, W0 = body.clientWidth; view.W0 = W0;
  const pages = []; let top = 0;                  // lay out one sized box per page, stacked
  for (let n = 0; n < sizes.length; n++) {
    const h = W0 * (sizes[n][1] / sizes[n][0]);
    const div = document.createElement("div"); div.className = "pw-page"; div.dataset.n = n;
    div.style.height = h + "px"; stage.appendChild(div);
    pages.push({div, n, top, h, imgLoaded: false, textBuilt: false});
    top += h + GAP;
  }
  view.H0 = top - GAP;
  stage.style.width = W0 + "px";
  const qp = pages[page] || pages[0];            // highlight rects live on the quote's page box
  for (const r of rects) {
    const hl = document.createElement("div"); hl.className = "pw-hl";
    hl.style.left = (r[0] * 100) + "%"; hl.style.top = (r[1] * 100) + "%";
    hl.style.width = ((r[2] - r[0]) * 100) + "%"; hl.style.height = ((r[3] - r[1]) * 100) + "%";
    qp.div.appendChild(hl);
  }
  ready();
  view.rw = rung(W0, 1);                          // raster rung in force; grows as the user zooms
  // One raster per page box, swapped in whole (loadRaster). `tok` voids a load that a newer one —
  // or an unload — has overtaken, so a late arrival never replaces a sharper image or revives a
  // page that was let go.
  const loadImg = (p, want = view.rw) => {
    const tok = p.tok = (p.tok || 0) + 1;
    p.imgLoaded = true; p.div.classList.remove("pw-failed");
    const live = () => p.tok === tok && win.isConnected;
    const server = () => loadRaster(pageSrc(key, p.n, want));
    docP.then(doc => !doc ? server()
        : drawPage(doc, p.n, want, live).catch(e => { if (!live()) throw e; return server(); }))
    .then(im => {
      if (!live()) return freeRaster(im);
      const old = p.img;
      if (old) old.replaceWith(im); else p.div.prepend(im);   // under the positioned overlays
      freeRaster(old);
      p.img = im; p.rw = want;
    }, () => {
      if (p.tok !== tok) return;
      if (!p.img) { p.imgLoaded = false; p.div.classList.add("pw-failed"); }   // tap retries
    });
  };
  // A decoded 1600px page is ~13 MB, and a 20-page paper held whole is more than an iPad gives a
  // web page before it starts dropping decodes. Pages well out of sight give their image back;
  // drawing one again from the copy (or the HTTP cache) is quick.
  const unloadImg = p => {
    p.tok = (p.tok || 0) + 1; p.imgLoaded = false; p.rw = 0;
    if (p.img) { p.img.remove(); freeRaster(p.img); p.img = null; }
  };
  // Zooming past the rung a page was rasterized at would just magnify its pixels, so re-fetch the
  // on-screen pages one rung up. Only pages actually in view are upgraded (the rest re-fetch
  // lazily when the observer reaches them); the old raster stays up until the new one is whole,
  // so a zoom never blinks the page out.
  const upgradeRasters = () => {
    const br = body.getBoundingClientRect();
    for (const p of pages) {
      if (!p.imgLoaded || p.rw >= view.rw) continue;
      const r = p.div.getBoundingClientRect();
      if (r.bottom < br.top - 400 || r.top > br.bottom + 400) { p.imgLoaded = false; continue; }
      loadImg(p);
    }
  };
  // Zoom before the opening scroll, so "centred on the highlight" is true at whatever distance
  // the reader last stood at — not true at 100% and then wrong the moment the stage grows.
  const zoom = wireZoom(win, view, {body, sizer, stage, sharpen: upgradeRasters});
  zoom.layout(zoom.stored());
  if (rects.length) {                            // open on the quote, else on its page's top
    const bs = rects.map(r => ({x0: r[0] * view.W0 * view.z, x1: r[2] * view.W0 * view.z,
                                y0: (qp.top + r[1] * qp.h) * view.z,
                                y1: (qp.top + r[3] * qp.h) * view.z}));
    showQuote(body, unionBox(bs), bs[0]);
  } else {                                       // unresolved quote: the page top, as before
    body.scrollTop = Math.max(0, Math.min(body.scrollHeight - body.clientHeight,
                                          qp.top * view.z - body.clientHeight / 2));
  }
  const buildText = async p => {                 // transparent selectable overlay for one page (pdf.js trick)
    if (p.textBuilt) return; p.textBuilt = true;
    let words = []; try { words = await fetch(`words/${key}/${p.n}.json`).then(r => r.ok ? r.json() : []); } catch { words = []; }
    if (!win.isConnected || !words.length) return;
    const layer = document.createElement("div"); layer.className = "pw-text"; const spans = [];
    for (const w of words) { const sp = document.createElement("span");
      sp.style.left = (w.x0 * W0) + "px"; sp.style.top = (w.y0 * p.h) + "px"; sp.style.fontSize = Math.max(4, (w.y1 - w.y0) * p.h) + "px"; sp.textContent = w.t;
      layer.appendChild(sp); spans.push([sp, (w.x1 - w.x0) * W0]); }
    p.div.appendChild(layer);
    for (const [sp, tw] of spans) { const nw = sp.offsetWidth; if (nw > 0) sp.style.transform = `scaleX(${tw / nw})`; sp.appendChild(document.createTextNode(" ")); }
  };
  // Prefetch reach: a screen and a bit on touch, where bandwidth is the scarce thing and a fast
  // flick would otherwise queue a dozen page fetches the reader scrolls straight past; the old
  // 1200px stays on desktop, where the pages are already local.
  const REACH = matchMedia("(hover:none) and (pointer:coarse)").matches ? "500px 0px" : "1200px 0px";
  const io = new IntersectionObserver(es => {    // render (+ text, in text mode) pages as they near view
    for (const e of es) { if (!e.isIntersecting) continue; const p = pages[+e.target.dataset.n];
      if (!p.imgLoaded) loadImg(p); if (win.dataset.tool === "text") buildText(p); }
  }, {root: body, rootMargin: REACH});
  const far = new IntersectionObserver(es => {   // …and let them go once they are screens away
    for (const e of es) if (!e.isIntersecting) unloadImg(pages[+e.target.dataset.n]);
  }, {root: body, rootMargin: "3000px 0px"});
  pages.forEach(p => { io.observe(p.div); far.observe(p.div);
    p.div.addEventListener("click", () => { if (p.div.classList.contains("pw-failed")) loadImg(p); }); });

  body.addEventListener("pointerdown", e => {    // pan tool: drag scrolls (text tool: browser selects)
    if (e.pointerType === "touch") return;       // native scroll owns touch; drag-pan is mouse-only
    if (e.button !== 0 || win.dataset.tool !== "pan") return;
    body.classList.add("pan"); body.setPointerCapture(e.pointerId);
    const sx = e.clientX, sy = e.clientY, l0 = body.scrollLeft, t0 = body.scrollTop;
    const mv = ev => { body.scrollLeft = l0 - (ev.clientX - sx); body.scrollTop = t0 - (ev.clientY - sy); };
    const up = () => { body.classList.remove("pan"); body.removeEventListener("pointermove", mv); body.removeEventListener("pointerup", up); };
    body.addEventListener("pointermove", mv); body.addEventListener("pointerup", up);
  });
  const sub = win.querySelector(".pw-sub");       // titlebar tracks the page under the viewport middle
  body.addEventListener("scroll", () => {
    const mid = body.scrollTop + body.clientHeight / 2; let cur = 0;
    for (const p of pages) { if (p.top * view.z <= mid) cur = p.n; else break; }
    if (sub) sub.textContent = `p.${cur + 1}`;
  }, {passive: true});
  win.querySelector(".pw-tools").addEventListener("click", e => {   // pan / text-select toggle
    const b = e.target.closest(".pw-tool"); if (!b) return;
    if (b.dataset.t !== "pan" && b.dataset.t !== "text") return;    // e.g. ⧉ detach — not a viewer tool
    win.dataset.tool = b.dataset.t;
    if (b.dataset.t === "text") {                 // build overlay for every page currently on screen
      const br = body.getBoundingClientRect();
      for (const p of pages) { const r = p.div.getBoundingClientRect(); if (r.bottom > br.top && r.top < br.bottom) buildText(p); }
    }
  });
  if (!OFFLINE.on) attachFind(win, key, {body, pages, view});
  else if (sub) sub.textContent += " · offline copy";
}

// Offline, nothing can rasterize a page, so the pane shows the cached PDF itself in the browser's
// own viewer (the service worker answers its range requests from the copy). The highlight, the
// find bar and the text layer are server-side features and stay off; `#page=` lands on the quote's
// page where the browser's viewer honours it.
function mountCopy(win, key, page){
  const body = win.querySelector(".pw-body"), sub = win.querySelector(".pw-sub");
  body.classList.add("pw-copy");
  body.innerHTML = `<iframe class="pw-pdf" title="${key}.pdf"`
    + ` src="pdf/${encodeURIComponent(key)}.pdf#page=${page + 1}"></iframe>`;
  if (sub) sub.textContent = `p.${page + 1} · offline copy`;
  win.querySelectorAll('.pw-tool[data-t="pan"],.pw-tool[data-t="text"]').forEach(b => { b.hidden = true; });
}
