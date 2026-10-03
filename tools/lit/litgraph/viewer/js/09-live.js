// ── tooltip ────────────────────────────────────────────────────────────────────────────
// Served over HTTP (`lit serve`), the tooltip upgrades: pdfs.json says which curated
// papers have a servable PDF, hovering embeds its first page, clicking the preview opens
// the full PDF in a new tab. Opened from file:// (`lit build` output) it stays inert.
const LIVE = location.protocol.startsWith("http");
// touch/no-hover devices synthesize mouseenter/move on tap (iOS), which would pin a sticky
// tooltip and latch soft previews. Hover-only affordances are gated on a real hover pointer;
// the load-bearing actions (tap to open/pin) are click/pointer-based and unaffected.
const HOVER = matchMedia("(hover: hover)").matches;
const QUERY = new URLSearchParams(location.search);
// DETACHED: this document is the browse view's popped-out PDF pane — /index.html?detached=1,
// opened in its own OS window (window.open of index.html?detached=1) so the PDF can live on a
// second monitor. It renders no graph, just a full-bleed PDF pane, mirrored from the graph
// window over the "lit-pdf" BroadcastChannel — see 10-pdf.js's detachDock/reattachDock and the
// mount loop in 12-landing.js.
const DETACHED = LIVE && QUERY.has("detached");
if (DETACHED) document.body.classList.add("detached");    // hide graph chrome before it paints
// OFFLINE: this page is the installed app's offline copy — the service worker (viewer/sw.js)
// marks a page it answers from the cache with data-offline="<ms it was copied>" — or the server
// has stopped answering since it loaded (20-offline.js calls goOffline). Reading still works from
// the copy; everything that writes is disabled and says why, rather than failing on the tap.
const OFFLINE = {on: LIVE && document.documentElement.hasAttribute("data-offline"),
                 since: +document.documentElement.dataset.offline || null};
const OFFLINE_WHY = "needs the server: this is the read-only offline copy";
if (OFFLINE.on) document.body.classList.add("offline");
function goOffline(){
  if (OFFLINE.on) return;
  OFFLINE.on = true;
  document.body.classList.add("offline");
  dispatchEvent(new Event("offlinechange"));
}
// The move (delta §3): papers on the in-progress worklist (the reading list) are pulled OUT of
// the browse view's landing column — they live off-board until named by the search box, a
// library row, or a click in the WIP panel (14-search.js), which is where the reading list is
// actually browsed.
const ACTIVE = new Set(GRAPH.active || []);
// The collapsible PDF viewer lives in the browse view only — a detached window has its own
// full-bleed pane instead.
const pdfToggle = document.getElementById("pdfToggle");
if (pdfToggle && LIVE) {
  pdfToggle.hidden = false;
  pdfToggle.addEventListener("click", toggleDock);
}
let PDFS = null;                       // Set of citekeys with a PDF (null until fetched)
if (LIVE) fetch("pdfs.json").then(r => r.ok ? r.json() : [])
  .then(l => { PDFS = new Set(l); }).catch(() => { PDFS = new Set(); })
  .then(() => dispatchEvent(new Event("pdfsready")));   // 20-offline.js trims it to the copy
// The tip must survive the hop from card to tip (to click the preview): hiding is
// deferred a beat (dropTip) and cancelled when the pointer arrives (keepTip).
let tipHide = null;
function keepTip(){ if (tipHide) { clearTimeout(tipHide); tipHide = null; } }
function dropTip(){
  keepTip();
  tipHide = setTimeout(() => { tip.style.display = "none"; tip.dataset.key = ""; }, 140);
}
tip.addEventListener("mouseenter", keepTip);
tip.addEventListener("mouseleave", () => { tip.style.display = "none"; tip.dataset.key = ""; });
// touch: a tap-pinned tip (from a stub) has no mouseleave — dismiss it on the next tap that
// isn't inside the tip or on another stub (capture, so it beats the stub's own re-show handler).
addEventListener("click", e => {
  if (!HOVER && tip.style.display === "block"
      && !e.target.closest("#tip") && !e.target.closest(".card.stub")) {
    tip.style.display = "none"; tip.dataset.key = "";
  }
}, true);

// ── stub abstracts (live-fetched on hover, serve-only) ───────────────────────────────────
// A stub carries title/authors/journal/year in stubs.yaml but NOT its abstract — persisting
// 50–100 reference abstracts per curated paper would balloon the diffable YAML. Instead the
// abstract is fetched on demand from OpenAlex (by DOI) the first time a stub card is hovered
// under `lit serve`, cached for the session, and never written to disk. Static `lit build`
// (no server, no LIVE) just shows the bib-only note.
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const stubAbsCache = new Map();          // citekey -> string | null (none/failed) | undefined (in-flight)
function stubAbstract(key, p){
  if (!LIVE || !p.doi) return `<div class="nopdf">uncurated stub — bib metadata only</div>`;
  const cached = stubAbsCache.get(key);
  if (typeof cached === "string") return `<div class="tabs">${esc(cached)}</div>`;
  if (cached === null) return `<div class="nopdf">uncurated stub — no abstract available</div>`;
  fetchStubAbstract(key);                // unfetched: kick it off, show a pending note this render
  return `<div class="nopdf" id="tabsPending">fetching abstract…</div>`;
}
async function fetchStubAbstract(key){
  if (stubAbsCache.has(key)) return;     // in-flight or done — don't refetch
  stubAbsCache.set(key, undefined);      // mark in-flight (has() true, so the guard above holds)
  let text = null;
  try {
    const r = await fetch(`stub-abstract?key=${encodeURIComponent(key)}`);
    if (r.ok) { const j = await r.json(); text = j && j.abstract ? j.abstract : null; }
  } catch { text = null; }
  stubAbsCache.set(key, text);
  // patch the live tip in place if it's still showing this stub (dataset.key guards re-render)
  if (tip.dataset.key === key && tip.style.display === "block") {
    const slot = tip.querySelector("#tabsPending");
    if (slot) slot.outerHTML = (typeof text === "string")
      ? `<div class="tabs">${esc(text)}</div>`
      : `<div class="nopdf">uncurated stub — no abstract available</div>`;
  }
}

// The hover preview is a pure metadata card now — title · all authors · journal · year · a
// (non-clickable) first-page thumbnail. Opening the PDF is the docked viewer's job (a card click
// loads it), so the tip no longer opens anything; it's a bib peek that holds still under the pointer.
function showTip(e, key, el, force){
  if (!HOVER && !force) return;        // touch: only the explicit tap-to-pin path (force) shows the tip
  keepTip();
  tip.style.display = "block";
  if (tip.dataset.key === key) return; // pinned: hold still while the same target is hovered
  tip.dataset.key = key;
  const cur = !!(PAPERS[key] && PAPERS[key].cur);
  const p = PAPERS[key] || STUBS[key];
  let thumb;
  if (cur && !LIVE) thumb = `<div class="nopdf">PDF preview needs <code>lit serve</code></div>`;
  else if (cur && OFFLINE.on) thumb = `<div class="nopdf">first-page preview ${OFFLINE_WHY}</div>`;
  else if (cur && (!PDFS || !PDFS.has(key))) thumb = `<div class="nopdf">no PDF served (${key}.pdf)</div>`;
  else if (cur) thumb = `<div class="pdf live"><img src="preview/${key}.png" alt="first page of ${key}.pdf"></div>`;
  else thumb = stubAbstract(key, p);   // uncurated: no PDF — show the abstract (live-fetched) instead
  const auth = (p.authors && p.authors.length) ? `<div class="tauth">${authLine(p.authors)}</div>` : "";
  const bib = [p.journal || venueFromKey(key), p.year].filter(Boolean).join(" · ");
  tip.innerHTML = `<div class="ttitle">${p.title || key}</div>${auth}`
                + `<div class="meta">${bib}</div>${thumb}`;
  // pin beside the hovered card — right of it, flipping left when there's no room — NOT
  // at the cursor, so the pointer can travel into the tip to read a long author list
  const r = ((el && el.closest(".card")) || el || e.target).getBoundingClientRect();
  const pad = 10, w = 300, h = tip.offsetHeight;
  let x = r.right + pad;
  if (x + w > innerWidth) x = r.left - w - pad;
  x = Math.max(8, Math.min(x, innerWidth - w - 8));
  const y = Math.max(54, Math.min(e.clientY - 24, innerHeight - h - 8));
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
