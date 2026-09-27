// generic pointer-drag: onMove(dx,dy,base0,base1); base() seeds the deltas; skip if target in `guard`
function dragBy(handle, onMove, base, guard){
  handle.addEventListener("pointerdown", e => {
    if (e.pointerType === "touch") return;   // touch scrolls the sheet natively; drag/resize is mouse-only
    if (guard && e.target.closest(guard)) return;
    e.preventDefault(); e.stopPropagation(); handle.setPointerCapture(e.pointerId);
    const sx = e.clientX, sy = e.clientY, [b0, b1] = base();
    const mv = ev => onMove(ev.clientX - sx, ev.clientY - sy, b0, b1);
    const up = () => { handle.removeEventListener("pointermove", mv); handle.removeEventListener("pointerup", up); };
    handle.addEventListener("pointermove", mv); handle.addEventListener("pointerup", up);
  });
}

// ── boot: the landing list (column 0), ranked by pass desc, then year desc ───────────────
// The landing column lists CURATED papers only. ORDER carries the whole bibliography (~3.7k
// entries against 54 curated ones), and rendering a card for each built a ~187k-px column whose
// mere existence taxed every forced relayout — one per click, one per hover. Measured at 4x CPU
// throttle, trimming it cut a click from 34.8 ms to 13.6 ms and rebuild() from 23.2 to 10.2 ms.
//
// Nothing becomes unreachable. Stubs stay indexed by the search box, which materializes a landing
// card on demand (gotoPaper), and the two ways a stub is drawn *into* the graph both still work:
// uncurated grounds fold into the per-card source stack (they never had a landing card of their
// own to anchor on), and a lateral/answers target that is only a stub is materialized up front by
// landingKeys so its arrow still lands.
function landingKeys(){
  const keep=new Set(ORDER.filter(k=>PAPERS[k]));
  for(const p of Object.values(PAPERS))
    for(const f of ["lateral","ans"])
      for(const l of p[f]||[])
        if(!l.slug && !PAPERS[l.key] && STUBS[l.key]) keep.add(l.key);
  return ORDER.filter(k=>keep.has(k));               // ORDER's ranking, filtered — never resorted
}

// ── the flat landing column ──────────────────────────────────────────────────────────────
// Every curated paper, always, in ORDER's pass ranking — the same decision as the synthesis band,
// for the same reason. This column was collapsed for a while: it landed empty and papers arrived
// only when something asked for them (a claim you showed, a jump by name), on the theory that a
// list of 54 you must scroll is a backlog rather than a view. It is a backlog only if scrolling is
// the sole way to reach anything in it. It isn't — showing a claim HOISTS its papers to the top of
// this column, so the reader's attention is placed by order, and the collapse was buying nothing
// the hoist did not already deliver while costing everything below:
//
//   · a card could be *put away*, so what the column held became session history rather than a
//     fact about the library, and three doors in needed a per-card × and a `clear` to undo;
//   · a paper's presence had to be EXPLAINED (the `.cprov` strip exists for this), because the
//     reader could not otherwise know why these 12 and not the other 42;
//   · the board could not answer "what have I curated?" at all without opening the library.
//
// What survives is one door and one set of state:
//   landedStuck — a paper named by the search box or a library row that the flat list does NOT
//                 carry, i.e. a STUB. Curated papers are always present, so naming one is a
//                 scroll-and-flash (gotoPaper) and adding it here is a no-op. Sticky, because
//                 naming something is a standing request; `clear` is the way back.
//   shownBroad  — the claims you have SHOWN (showBroad). No longer decides which papers EXIST in
//                 the column, only which ones are gathered at its top, and which arrows are lit.
// `landedDropped` and the per-card × went with the collapse: hiding a paper from a flat list is
// the very thing the flat list is for not doing.
const landedStuck=new Set();
const shownBroad=new Set();
// key -> {claims:[slug], stuck:bool}: WHY a card is here — no longer *whether*. Two consumers, the
// per-card provenance strip and the stub reconcile below, so they cannot disagree.
function landedWant(){
  const want=new Map();
  const note=(k,slug)=>{
    const e=want.get(k)||{claims:[],stuck:false};
    if(slug) e.claims.push(slug); else e.stuck=true;
    want.set(k,e);
  };
  for(const k of landedStuck) note(k,null);
  for(const slug of shownBroad)
    for(const k of new Set((BROAD_LINKS[slug]||[]).map(l=>l.key))) note(k,slug);
  return want;
}
const broadLabel=slug=>{
  const b=BROAD[slug]||{}, s=b.title||b.text||slug;
  return s.length>36?s.slice(0,35)+"…":s;
};
// ── the way out ──────────────────────────────────────────────────────────────────────────
// TWO DOORS, nested, sharing one implementation so they cannot disagree:
//
//   clear arrows (HUD, `c`)      every pinned row + every shown claim + the hover. The edge layer
//                                goes quiet and the board stands still — nothing closes, nothing
//                                re-sorts, no card moves.
//   clear (landing column head)  the above, plus the stubs you summoned by name. A summoned stub
//                                is a search result, not an arrow, which is the whole difference.
//
// The HUD door is new, and it is the fix for the report that opening and collapsing a run of
// claims leaves the board full of arrows with no way back. Before it, releasing depended on
// finding the thing you had pinned: click the same row again (impossible once its card is
// collapsed — and see pinLive for the stale-pin half of that bug), or click empty board space
// (there is none once four columns have fanned out, and it thawed row pins only, never a shown
// claim), or scroll to the top of the landing column for a `clear` that did the exact opposite —
// claims but not rows. Three partial exits, none reachable from the mess they made.
//
// It is deliberately NOT bound to Escape: Escape already closes the library, the walk, the views
// menu and the search box, and a fifth listener that fires unconditionally would clear the board
// behind whichever pane you were actually dismissing.
function releaseArrows(){
  if(!pin.length&&!shownBroad.size) return false;
  pin=[]; hover=null; unpinned=null; shownBroad.clear();
  return true;                                 // rebuild re-derives the claim pins from shownBroad
}
function clearArrows(){ if(releaseArrows()) rebuild(); }
// `clear` no longer empties the column — a flat list has nothing to empty. It RELEASES: every shown
// claim put away, its arrows dark, every stub summoned by name dismissed. Claim pins go with it,
// because rebuild derives them from shownBroad — one state, one clear. It deliberately leaves the
// ORDER the hoists built: releasing a claim is not a reason to re-sort the column under the reader.
function clearLanding(){
  releaseArrows(); landedStuck.clear();
  rebuild();
}
// The button reports HOW MUCH is being held, because "clear arrows" on a board with one pinned row
// and on a board with eleven is the same words and very different news. Written only when the
// count changes: redraw() calls this, and redraw() runs on every scroll event.
const clearBtn=document.getElementById("clearBtn");
let clearHeld=-1;
function syncClearBtn(){
  if(!clearBtn) return;
  const n=pin.length+shownBroad.size;
  if(n===clearHeld) return;
  clearHeld=n;
  clearBtn.hidden=!n;
  clearBtn.textContent=`clear arrows · ${n}`;
}
if(clearBtn) clearBtn.addEventListener("click",()=>clearArrows());
// ── quiet arrows: the resting board goes dark ────────────────────────────────────────────
// `clear arrows` releases what you are HOLDING; this puts away what you never asked for. They are
// the two halves of the same complaint and neither does the other's job: clearing a board with no
// pins on it changes nothing, and quieting one does not release the pins it is deliberately keeping.
//
// A standing mode, not an action, so it gets a toggle rather than a button that fires once — and
// one line in edgeVis rather than a second pass over the edge list, because "which arrows are on"
// is decided in exactly one place (see there). redraw() alone is enough: it re-asks edgeVis about
// every edge from current state, and nothing about the board's layout has moved.
const quietBtn=document.getElementById("quietBtn");
function setQuiet(on){
  quietEdges=!!on;
  if(quietBtn){
    quietBtn.classList.toggle("on",quietEdges);
    quietBtn.title=quietEdges
      ? "showing only the arrows you asked for — click to bring the resting board back (q)"
      : "draw only the arrows you asked for — everything resting goes dark (q)";
  }
  redraw();
}
if(quietBtn&&!DETACHED){ quietBtn.hidden=false; quietBtn.addEventListener("click",()=>setQuiet(!quietEdges)); }
// `q` for quiet, alongside `c` for clear and `w` for the walk — same guards: not while typing, and
// not while a pane that owns the keyboard is up.
addEventListener("keydown",e=>{
  if((e.key!=="c"&&e.key!=="q")||e.metaKey||e.ctrlKey||e.altKey) return;
  if(/^(INPUT|TEXTAREA)$/.test(e.target.tagName||"")||e.target.isContentEditable) return;
  if(document.body.classList.contains("library")||document.body.classList.contains("walk")) return;
  if(e.key==="c") clearArrows(); else setQuiet(!quietEdges);
});
// ── showing a claim: ONE gesture ─────────────────────────────────────────────────────────
// This used to be three. A ◂ chip landed the claim's papers in the column; a ▸ chip walked one rung
// down the ladder; a click on the card pinned its edges bright and hoisted the block. They read as
// alternatives and were not: since the landing column collapsed, a pin has nothing to light up
// until its evidence has landed, so the card click was only ever the chips' other half — and which
// of the three you reached for changed what you got.
//
// Now the card is the whole gesture, at every altitude. Click a claim: whatever sits one step below
// it joins it at the top of the board — its papers land in the column, the narrower claims that
// ladder into it are hoisted up beside it on the band, its arrows go bright and stay bright, and
// the whole block gathers into one screenful. Click again: it all comes undone. Which kind of
// evidence a claim has is a fact about the graph; making the reader express it as a different
// gesture pushed a detail of the schema into the hands. The chips are readouts of that state, not
// ways to enter part of it.
//
// The gesture PLACES; it no longer reveals. The rungs used to appear on this click (see broadTier for
// why they stopped hiding), so a claim's own subtree could vanish under it and `pruneShown` existed to
// keep that consistent. With the band flat, showing a claim can only ever move things.
function showBroad(slug){
  const hide=shownBroad.has(slug);
  if(hide) shownBroad.delete(slug); else shownBroad.add(slug);
  rebuild();                                   // hoists the papers, re-derives the pins, re-hoists
  // on hide the pointer is still resting on the card we just put away; without this the transient
  // hover re-lights the very edges the click turned off (see `unpinned`). On show, jump to the
  // hoisted block — instantly, because every scroll event redraws the edge overlay and animating
  // up from deep in a tall column would repaint every arrow the whole way.
  if(hide){ unpinned={cardId:`card-${SYNTH}:${slug}`,sid:null}; return; }
  // The hoist put this claim's FAMILY at the top of the column; scrolling home lands on the family
  // head, which is the right place only when the head is what you clicked. A rung deep inside a tall
  // box needs the board brought to the rung. Instantly, never smoothly: every scroll event redraws
  // the whole edge overlay, and animating down a long column repaints every arrow the whole way.
  const el=document.getElementById(`card-${SYNTH}:${slug}`);
  if(!broadHost[slug]||!el){ if(board.scrollTop) board.scrollTop=0; return; }
  el.scrollIntoView({block:"center"});
  flash(el);
}
// Reconcile cols[0]. The curated list is a FIXED population — every key landingKeys() names is
// present from boot and never leaves, so a later call only ever evicts stub cards nobody names
// any more. It never re-sorts: a card already in the column stays exactly where the hoists left it.
function syncLanding(){
  const c=cols[0]; if(!c) return;
  const want=landedWant();
  const perm=new Set(landingKeys());
  for(const k of [...c.keys]){                       // only summoned stubs are evictable
    if(perm.has(k)||landedStuck.has(k)||k.endsWith("::srcs")) continue;
    c.keys.delete(k);
    // stubOpen is deliberately NOT pruned here. It is keyed by citekey, not by card, and the same
    // uncited paper can also be standing as a row in some open paper's source wall — evicting the
    // summoned card would then fold a row on the other side of the board that nobody dismissed.
    const el=document.getElementById(`card-0:${k}`); if(el) el.remove();
  }
  for(const k of perm){                              // ORDER's ranking — never resorted
    if(ACTIVE.has(k)||c.keys.has(k)) continue;        // reading-list papers stay off the column
    addPaper(0,k);
  }
  for(const k of landedStuck){                       // a stub named by hand isn't in landingKeys()
    if(ACTIVE.has(k)||c.keys.has(k)||!(PAPERS[k]||STUBS[k])) continue;
    addPaper(0,k);
  }
  // Say what each card is doing here. Not "why is it on screen" any more — a curated paper needs no
  // excuse for being in the list of curated papers — but which of the shown claims it answers to,
  // which is what tells the reader whose block a hoisted card belongs to when two are gathered at
  // the top. Rewritten every sync: showing a second claim that rests on this paper adds a reason.
  for(const k of c.keys){
    const card=document.getElementById(`card-0:${k}`);   // id-with-a-colon: getElementById, not a selector
    const via=card&&card.querySelector(".cvia");
    if(!via) continue;
    const e=want.get(k)||{claims:[],stuck:false};
    const bits=[];
    if(e.stuck) bits.push("asked for by name");
    for(const slug of e.claims) bits.push("evidence for “"+broadLabel(slug)+"”");
    via.textContent=bits.join(" · ");
    via.title=bits.join("\n");
    card.classList.toggle("plain",!bits.length);         // no reason to state → no strip at all
  }
  const hd=c.el.querySelector(".colhd");
  // Count the CURATED cards, not c.keys.size: the column's tail carries a card per uncurated paper
  // that some lateral / answers edge points at (landingKeys), which exist so those arrows have an
  // anchor and are not part of the list this header names. 69 curated, 49 such stubs today.
  // `clear` appears only when there is state to release (a shown claim, a summoned stub). On the
  // resting column it would be a button that does nothing, which is worse than no button.
  let n=0; for(const k of c.keys) if(PAPERS[k]) n++;
  // On a PROPOSAL page this column is not a library at all — it is the proposal itself, the
  // introduction with its aims under it (preview.isolate_proposal). Naming it "curated papers"
  // there would be a third rendering of a fact the page contradicts on sight.
  if(hd) hd.innerHTML=(PROPOSAL?`the proposal`:`curated papers · ${n}`)
    +(shownBroad.size||landedStuck.size?`<span class="hd-clear">clear</span>`:"");
  c.el.classList.toggle("vacant",!c.keys.size);         // an empty repo, or a preview of one paper
  document.body.classList.toggle("landing-vacant",!c.keys.size);
}
function boot(){
  broadRefresh();                    // tiers + nesting ready before the very first ensureBroadBand()
  const c0=ensureCol(0,"curated papers");
  // delegated, because syncLanding rewrites the header every time the count changes
  c0.el.addEventListener("click",e=>{
    if(e.target.closest(".hd-clear")){ e.stopPropagation(); clearLanding(); }
  });
  syncLanding();                                     // the whole curated list, in ORDER's ranking
  ensureBroadBand();                                 // synthesis band present from the landing view
  redraw();
}
if (!DETACHED) boot();                                // the detached PDF window renders no graph

// ── the detached PDF window ──────────────────────────────────────────────────────────────
// Its own OS window holding nothing but a full-bleed PDF pane (?detached=1), mounted with the
// same buildWin/mountDoc the in-page dock uses so the two can't drift. It is the browse view's
// popped-out dock: the graph window broadcasts {t:"aim",…} on the same hover that would aim the
// in-page dock, over the "lit-pdf" BroadcastChannel. We announce {t:"ready"} on boot so a graph
// window that opened us first still hands over the current aim.
if (DETACHED) {
  document.title = "Pythia · PDF";
  const pane = document.getElementById("detachPane");
  let win = null, lastAim = null;
  function mount(m){
    lastAim = m;
    const empty = document.getElementById("detachEmpty"); if (empty) empty.remove();
    if (win) win.remove();
    win = buildWin(m.key, (m.rects && m.rects.length) ? `p.${m.page + 1}` : "full paper",
                   {onClose: () => window.close()});
    pane.appendChild(win);                           // re-parent out of <body> into the full-bleed host
    mountDoc(win, m.key, m.page || 0, (m.rects || []).slice(), {interactive: true});
  }
  const chan = ("BroadcastChannel" in window) ? new BroadcastChannel("lit-pdf") : null;
  if (chan) {
    chan.onmessage = e => { const m = e.data; if (m && m.t === "aim") mount(m); };
    chan.postMessage({t: "ready"});
    addEventListener("beforeunload", () => chan.postMessage({t: "closed"}));
  }
  let rt = null;                                      // re-fit the page to the new window width (mountDoc bakes W0)
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (lastAim) mount(lastAim); }, 140); });
}
// width slider: drive --col live; columns resize (edges re-anchor on redraw), centering
// padding follows via calc(50vw - var(--col)/2). Value readout kept in sync.
(function(){
  const slider=document.getElementById("colw"), val=slider.nextElementSibling;
  const apply=()=>{ document.documentElement.style.setProperty("--col","min("+slider.value+"px, 86vw)");
    val.textContent=slider.value+"px"; redraw(); };
  slider.addEventListener("input",apply); apply();
})();

