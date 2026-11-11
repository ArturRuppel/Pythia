// a pass (SCHEMA §4) as a pie-filled circle: n/4. Empty ring = stub or nothing validated (0),
// full disk = 4. Cards and rows draw the VALIDATED pass with it (vstat, below).
function passCircle(pass){
  const p = Math.max(0, Math.min(4, pass || 0)), frac = p / 4, r = 7;
  const ring = `<circle cx="8" cy="8" r="${r}" fill="none" style="stroke:var(--faint);stroke-width:1.3"/>`;
  let wedge = "";
  if (frac >= 1) wedge = `<circle cx="8" cy="8" r="${r}" style="fill:var(--grounded)"/>`;
  else if (frac > 0) {
    const a = frac * 2 * Math.PI, ex = 8 + r * Math.sin(a), ey = 8 - r * Math.cos(a);
    wedge = `<path d="M8,8 L8,${8 - r} A${r},${r} 0 ${frac > 0.5 ? 1 : 0} 1 ${ex.toFixed(2)},${ey.toFixed(2)} Z" style="fill:var(--grounded)"/>`;
  }
  return `<span class="circle" title="curation maturity ${p}/4">`
       + `<svg width="16" height="16" viewBox="0 0 16 16">${ring}${wedge}</svg></span>`;
}
// ── the desk (SCHEMA §4): what the owner has validated, against how far curation ran ─────────
// `pass` is how far curation ran; `validated` is the pass the OWNER has validated (absent: never
// validated, a new paper). A paper is on the desk iff `validated` is absent or differs from the
// pass (absent `pass` = 0). Derived here, never stored — so the static build lists it too, and
// only `lit serve` can change it (validatePaper, 14-search.js). Function declarations, because
// the landing column mints its cards while the bundle is still being parsed.
function passLabel(n){ return ["ingested", "abstract", "intro+disc", "results", "methods"][n] || ""; }
function curPass(p){ return p && p.pass != null ? p.pass : 0; }
function deskStatus(p){
  if (!p || !p.cur || p.aim || p.narr) return null;
  if (p.validated == null) return "new";
  return p.validated !== curPass(p) ? "changed" : null;
}
// The desk's two groups, newest curation record first (the only date a paper carries), then by
// citekey. `only` narrows it to a set of citekeys (a collection).
function deskKeys(only){
  const out = {new: [], changed: []};
  for (const k in PAPERS) {
    if (only && !only.has(k)) continue;
    const st = deskStatus(PAPERS[k]);
    if (st) out[st].push(k);
  }
  const newest = (a, b) => ((PAPERS[b].curation_updated || 0) - (PAPERS[a].curation_updated || 0))
    || (a < b ? -1 : a > b ? 1 : 0);
  out.new.sort(newest); out.changed.sort(newest);
  return out;
}
// A paper's status wherever the board shows one: the VALIDATED pass as the pie, and a quiet
// marker when the owner has not caught up — "new" if never validated, "curated M" if curation ran
// ahead. `.vstat` is the handle validatePaper swaps in place.
function vstat(p){
  const v = p.validated, m = curPass(p);
  const mark = v == null ? `<span class="vmark">new</span>`
    : m > v ? `<span class="vmark" title="curation ran to pass ${m} · ${passLabel(m)}">curated ${m}</span>` : "";
  const title = v == null ? `new · never validated · curated ${m} ${passLabel(m)}`
    : `validated ${v}/4 · ${passLabel(v)}`;
  return `<span class="vstat" title="${title}">${passCircle(v || 0).replace(/ title="[^"]*"/, "")}${mark}</span>`;
}
function authLine(a){return a.map(([n, pos, corr]) =>
  corr ? `<span class="star">${n}*</span>` : n).join(' · ');}
// An uncited stub is on screen as a reference, not as a bibliography entry to be read end to end,
// so a 25-name byline is 25 lines of noise. Compact to the ends of the byline — which is how the
// paper gets cited anyway — keeping the corresponding-author mark. Under six names it is already
// short enough to print in full. (Curated cards print the full byline, everywhere they stand.)
function shortAuthLine(a){
  if (a.length < 6) return authLine(a);
  const one = ([n, , corr]) => corr ? `<span class="star">${n}*</span>` : n;
  const corr = a.filter(x => x[2]).map(one);
  const ends = [one(a[0]), ...(corr.length ? corr : [one(a[a.length - 1])])];
  return `${ends[0]} · … · ${ends.slice(1).join(' · ')} <span class="anum">(${a.length} authors)</span>`;
}
// citekey = <Family><Year><Venue>; the venue token is the journal (ISO-4 abbrev / brand). Used as
// the journal until a real `journal` field is stored end-to-end (then p.journal wins).
const venueFromKey = k => { const m = String(k).match(/\d{4}([A-Za-z][A-Za-z0-9]*)$/); return m ? m[1] : ""; };

// An aim's `note` is written as thesis-then-consequence — "same mean, percolating pattern → solid;
// dispersed → fluid. If it holds it makes a number and closes the chain…". Split it there: the
// first sentence is the punchline (closed card), the remainder is the pitch (open card). No new
// schema field — the two layers were already in the YAML, the card just never printed them.
function splitNote(n){
  const t = (n || "").trim();
  const m = t.match(/^([\s\S]*?[.!?])\s+([\s\S]+)$/);
  return m ? [m[1], m[2].replace(/\s+/g, " ")] : [t, ""];
}
// The standing counts: what the aim rests on that nothing checks, what would settle it, what it
// cannot yet do. This is `lit programme`'s report compressed onto one line, and it deliberately
// leads with the weakest thing — that is what a reviewer finds first regardless.
function aimStat(p){
  const S = p.slices, n = (k, one, many) => `${k} ${k === 1 ? one : many}`;
  const lb = S.filter(s => s.lb), tests = S.filter(s => s.kind === "test");
  const risk = tests.filter(s => s.risk);
  const asp = S.filter(s => s.kind === "capability" && s.asp);
  const openq = S.filter(s => s.kind === "question" && !s.answered);
  const bits = [];
  if (lb.length) bits.push(`<span class="warn">${n(lb.length, "assumption", "assumptions")} `
    + `nothing checks</span> (${lb.map(s => s.br + "✕").join(" · ")})`);
  if (tests.length) bits.push(n(tests.length, "test", "tests") + (risk.length
    ? `, <span class="warn">${risk.length === tests.length ? "all" : risk.length} at risk</span>` : ""));
  if (asp.length) bits.push(`<span class="warn">`
    + n(asp.length, "capability that doesn't", "capabilities that don't") + ` exist yet</span>`);
  if (openq.length) bits.push(n(openq.length, "open question", "open questions"));
  return bits.join(" · ");
}

function paperCard(key, level){
  const p = PAPERS[key] || STUBS[key];
  const cur = !!(PAPERS[key] && PAPERS[key].cur);
  const aim = !!(PAPERS[key] && PAPERS[key].aim);
  const narr = !!(PAPERS[key] && PAPERS[key].narr);
  // the two programme containers share a header: no curation maturity (a reading protocol for a
  // document that already exists) and no year, and their title reads on the CLOSED card, since
  // `@fluid-solid-switch` / `~cnrs-v2` collapsed tells a reader nothing at all.
  const prog = aim || narr;
  const id = `${level}:${key}`;
  const el = document.createElement("div");
  el.className = `card ${cur ? 'curated' : 'stub'}${aim ? ' aim' : ''}${narr ? ' narr' : ''}`;
  el.id = "card-" + id; el.dataset.key = key; el.dataset.id = id;
  el.dataset.year = p.year || 0;
  // Collapsed by default: circle + citekey only. The rest is revealed on focus (.open).
  // An aim carries neither: curation maturity is a reading protocol for a document that already
  // exists (programme design §7), and an aim has no year — which the header used to print as
  // a literal "null".
  let body = `<div class="chd">${prog ? "" : cur ? vstat(p) : passCircle(0)}<span class="ckey">${key}</span>`;
  if (cur) {
    body += `<span class="ctype ${p.type}">${p.type}</span>`;
    // tags ride in the header (collapsed too) between the class pill and the right-pushed year
    if (p.tags && p.tags.length) body += `<div class="ctags">`
      + p.tags.map(t => `<span class="ctag" data-tag="${esc(t)}">${esc(t)}</span>`).join("") + `</div>`;
    // a narrative has no year; what stands in that slot is the one number a grant is actually
    // constrained by — the page budget the sections have to fit inside
    if (narr && p.budget != null) body += `<span class="cyr nbud">${esc(String(p.budget))} pages</span>`;
    else if (!aim) body += `<span class="cyr">${p.year}</span>`;
  } else if (p.year) {
    body += `<span class="cyr">${p.year}</span>`;      // right-pushed, revealed by .card.open
  }
  body += `</div>`;
  if (!cur) {
    // A stub expands to the bib record `stubs.yaml` actually stores — title, byline, venue, year
    // — reusing the curated card's own classes so the two kinds cannot drift apart visually and
    // the existing `.card.open` reveal rules cover both. The byline is the SHORT form for the
    // same reason a cited source uses it: an uncited stub is on screen as a reference, not as a
    // bibliography entry to be read end to end. `p.journal || venueFromKey` is the tip's rule
    // verbatim (showTip) — two renderings of one fact disagreeing is worse than the mild
    // redundancy of naming a venue the citekey above already spells.
    const venue = p.journal || venueFromKey(key);
    body += `<div class="ctitle">${p.title || ""}</div>`;
    if (p.authors && p.authors.length) body += `<div class="cauth">${shortAuthLine(p.authors)}</div>`;
    if (venue) body += `<div class="cbib">${esc(venue)}</div>`;
  }
  if (cur) {
    body += `<div class="ctitle">${p.title}</div>`;
    if (narr) {
      // nothing between the title and the prose: a narrative's body IS its sections, and it
      // carries no abstract, byline or note to stand in front of them.
    } else if (aim) {
      const [punch, pitch] = splitNote(p.note);
      if (punch) body += `<div class="cpunch">${punch}</div>`;
      const stat = aimStat(p);
      if (stat) body += `<div class="cstat">${stat}</div>`;
      if (pitch) body += `<div class="cnote">${pitch}</div>`;
    } else {
      if (p.authors) body += `<div class="cauth">${authLine(p.authors)}</div>`;
      // The abstract is 200 words of someone else's prose sitting between the byline and the
      // graph — the longest thing on the card and the one you reread least. So it gets its own
      // fold: an open card offers the WORD, and the paragraph arrives when it is asked for.
      // (Inline, desktop and touch alike — the hover tip carries the PDF thumbnail, not this.)
      if (p.abs) body += `<div class="cabsx"><span class="acar"></span>abstract</div>`
                       + `<div class="cabs">${p.abs}</div>`;
    }
    body += `<div class="slices"></div>`;   // filled by renderSlices from the drill state
  }
  // The provenance strip, landing column only: which shown claims this paper answers to. Born empty
  // (hence .plain) and filled by syncLanding, because what a card is doing here changes after it is
  // built — showing a second claim that also rests on this paper adds a reason.
  if (level === 0)
    body += `<div class="cprov"><span class="cvia"></span></div>`;
  el.innerHTML = body;
  if (level === 0) el.classList.add("plain");
  if (!cur && stubOpen.has(key)) el.classList.add("open");   // a card minted while its stub is expanded
  if (cur && absOpen.has(key)) el.classList.add("absopen");  // …and one minted while its abstract is
  // a tag chip runs a search for that tag (the whole filter-by-tag story — no separate panel);
  // stopPropagation keeps the click off cardClick's fold/drill routing
  if (cur) el.querySelectorAll(".ctag").forEach(chip =>
    chip.addEventListener("click", e => { e.stopPropagation(); runSearch(chip.dataset.tag); }));
  // the abstract + PDF-preview tip is bound to the citekey tag only (hovering the body drills
  // slices / isolates edges without popping the tip); edge-isolation still tracks any row.
  el.addEventListener("mousemove", e => {
    if (e.target.closest(".ckey")) showTip(e, key, el); else dropTip();
    hoverRow(el, e);
  });
  el.addEventListener("mouseleave", () => { dropTip(); hoverRow(null); });
  // right-click a curated card (browse view) → Validate, at its pass or a lower one (the desk)
  if (cur && !prog && LIVE) el.addEventListener("contextmenu", e => showDeskMenu(e, key));
  // Both kinds of card open on a click; what they open to differs. A curated card routes through
  // cardClick (fold / drill / isolate); a stub has none of that and simply reveals its bib record.
  // The citekey stays the tip's handle in both: on desktop the mousemove above pops it on hover,
  // and on touch — where there is no hover at all — a tap on the key is the only route to the
  // live-fetched abstract, which is the one thing the expanded card does NOT carry. Hence the
  // early return: tapping the key reads the abstract, tapping anywhere else expands.
  el.addEventListener("click", e => {
    if (cur) return cardClick(e, el, level, key);
    if (!HOVER && e.target.closest(".ckey")) { showTip(e, key, el, true); return; }
    toggleStub(key);
  });
  return el;
}

// Expand/collapse an uncited stub, every instance of it at once (see stubOpen). The redraw is not
// cosmetic: `.open` is exactly what endOpen tests, so expanding a stub promotes every edge landing
// on it from a ghost to scaffolding — which is the honest reading, since an arrow into a stub can
// only ever anchor on the card border, and the border now names the paper it lands on.
function toggleStub(key){
  if (!STUBS[key]) return;                          // curated papers open through cardClick
  if (stubOpen.has(key)) stubOpen.delete(key); else stubOpen.add(key);
  const on = stubOpen.has(key);
  const k = CSS.escape(key);
  document.querySelectorAll(`.card.stub[data-key="${k}"], .card.stack .src[data-sid="${k}"]`)
    .forEach(c => c.classList.toggle("open", on));
  redraw();
}
// The three facts a citekey and a year don't already carry, for a source-stack row. Same
// selection as the expanded stub card and the hover tip — one uncited paper reads the same
// wherever it stands, which is the whole point of keying the state by citekey.
function stubDetail(key, p){
  const venue = p.journal || venueFromKey(key);
  return `<div class="sdet">`
       + (p.title ? `<div class="st">${p.title}</div>` : "")
       + (p.authors && p.authors.length ? `<div class="sa">${shortAuthLine(p.authors)}</div>` : "")
       + (venue ? `<div class="sj">${esc(venue)}</div>` : "")
       + `</div>`;
}

const samePin=(a,b)=>!!a&&!!b&&a.cardId===b.cardId&&a.sid===b.sid;
// the level baked into a card id ("card-<level>:<key>") — SYNTH and up is a synthesis-band claim
const cardIdLevel=cardId=>+cardId.slice(5,cardId.indexOf(":"));
// A target a second click just RELEASED. Without this the release is invisible: the pointer is
// still resting on the row it released, so the transient `hover` immediately re-lights the very
// edges the click turned off. On desktop that lasts until the pointer wanders away; on touch,
// where a tap fires a synthetic mousemove and no mouseleave ever comes, it lasts until some other
// card is tapped — which is exactly the "second click does nothing" it was reported as. The
// suppression lifts the moment the hover genuinely moves somewhere else.
let unpinned=null;
