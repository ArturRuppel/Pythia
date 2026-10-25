// ── the handoff in: ?goto= ───────────────────────────────────────────────────────────────
// 16-renderings is the way OUT to the alternative renderings; this is the way back in. A view
// names a node in the URL and the board goes and stands on it — which is the seam the additive
// views were designed around (docs/2026-08-05-additive-graph-views.md §2: "a paper's citekey is
// the handoff seam back to the board").
//
// Nothing is invented for it. The two gestures the board already has ARE the handoff — gotoPaper
// for a paper, showBroad for a broad node — so arriving from a view and finding the same thing by
// name leave the board in exactly the same state, and there is no second notion of "go there" to
// drift from the first.
//
// Three shapes, resolved by asking the payload which kind owns the name rather than by spelling:
//
//   ?goto=Park2015NatMater        a paper — open its card, minting a stub's card if needed, flash it
//   ?goto=Park2015NatMater:c3     a slice — …and drill to that row, flash it
//   ?goto=tissue-behaviour-…      a broad node — hoist its papers, scroll, flash
//
// `Citekey:sid` is the schema's own spelling for a sharpened ref (SCHEMA §3), so the URL says what
// the YAML says. Telling the two apart by shape (CamelCase vs kebab-case) would work today and
// break on the first citekey or slug that isn't shaped like its neighbours; membership cannot.
//
// Naming a CLAIM opens the card that holds it — a claim you cannot see is not a handoff — and
// naming a PAPER opens its card too: an arrival by link is a request to read, which is where it
// parts from the same name typed into the search box (that gesture only scrolls and flashes).
function gotoTarget(spec){
  const s = String(spec || "").trim();
  if(!s) return null;
  const i = s.indexOf(":");
  const key = i < 0 ? s : s.slice(0, i), sid = i < 0 ? null : s.slice(i + 1);
  // A programme container (an aim, a narrative) rides in PAPERS on the main board but NOT in
  // ORDER, and gotoPaper below assumes any key it is handed belongs in the landing column —
  // minting one there would plant a programme card among the papers, which is exactly what
  // keeping the programme off the board is for. So the test is membership in ORDER, not kind:
  // on the board `?goto=@slug` names nothing this handoff can reach, and on a proposal page,
  // where the aim IS in the landing column, the very same link lands on it.
  const prog = PAPERS[key] && (PAPERS[key].aim || PAPERS[key].narr);
  if(prog && !ORDER.includes(key)) return null;
  if(PAPERS[key] || STUBS[key]){
    if(!sid) return {kind: "paper", key};
    const p = PAPERS[key];
    if(p && (p.slices || []).some(x => x.id === sid)) return {kind: "slice", key, sid};
    // The paper is real and the row is not — a slice renamed or dropped since the link was made.
    // Landing on the paper is strictly better than refusing: the destination still exists.
    return {kind: "paper", key, missing: sid};
  }
  if(BROAD[s]) return {kind: "broad", slug: s};
  return null;
}
// A name nothing answers to is reported where the reader is already looking for names. Silence
// would be indistinguishable from a handoff that worked and landed off-screen.
function gotoLost(spec){
  console.warn(`litgraph: ?goto=${spec} names nothing in this build`);
  if(!searchInput || !searchInput.isConnected) return;      // defensive: nothing to report into
  searchResults.innerHTML = `<div class="sr-none">nothing in this build answers to `
    + `“${esc(spec)}” — the link may name a paper or claim this graph does not carry</div>`;
  openResults();
}
function applyGoto(spec){
  const t = gotoTarget(spec);
  if(!t){ gotoLost(spec); return false; }
  if(t.kind === "broad"){ showBroad(t.slug); return true; }
  if(t.missing) console.warn(`litgraph: ${t.key} carries no slice ${t.missing} — landing on the paper`);
  gotoPaper(t.key);                          // mints a stub's card, flashes it, owns the walk case
  // In the walk the board is not the view you are looking at: gotoPaper has already re-focused the
  // walk on the paper, and there is no card to open or row to drill.
  if(document.body.classList.contains("walk")) return true;
  const id = `0:${t.key}`;
  // A handoff is an arrival from elsewhere (Athena, a rendering, a pasted link), and the reader
  // came to READ the paper, not to find its card on the board: so unlike the same name typed in
  // the search box, the card opens — on its bibliographic head for a paper, drilled to the row
  // for a slice. The card is focused first so that the slices are on it at all.
  open.add(id); rebuild(id);
  if(t.kind !== "slice"){
    redraw();
    const card = document.getElementById("card-" + id);
    if(card){ card.scrollIntoView({behavior: "smooth", block: "center"}); flash(card); }
    return true;
  }
  // A focused card opens on its bibliographic head, with the slice graph folded (and an aim's
  // outline hiding rows inside its own groups); rebuild() clears the ctx state on its way through
  // — so the folds are forced open after the sweep, and the card re-rendered.
  reveal(id, t.sid); renderSlices(id); redraw();
  const el = document.getElementById("card-" + id);
  const row = el && el.querySelector(`.slice[data-sid="${CSS.escape(t.sid)}"]`);
  if(!row) return true;                      // the card is on screen either way
  // inline as well as block: a paper's slices are a horizontally scrolling graph, so a deep
  // column's rows sit off the side of the card rather than below it.
  row.scrollIntoView({behavior: "smooth", block: "center", inline: "center"});
  flash(row);
  return true;
}
const GOTO = new URLSearchParams(location.search).get("goto");
if(GOTO) applyGoto(GOTO);
window.litGoto = applyGoto;                  // the same seam from the console, and for headless checks
