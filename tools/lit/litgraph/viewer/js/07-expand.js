// Where does `key` already sit? Prefer the instance nearest `near`; every paper the graph can
// point at is in the landing column (landingKeys keeps the referenced stubs), so level 0 is the
// guaranteed fallback. Callers that could still miss check for the element before using it.
function findCardLevel(key,near){
  let best=null;
  for(const lvl of Object.keys(cols).map(Number)){
    if(lvl>=SYNTH||!cols[lvl].keys.has(key)) continue;
    if(best===null||Math.abs(lvl-near)<Math.abs(best-near)) best=lvl;
  }
  return best===null?0:best;
}

// `grp` is which click this expansion belongs to; everything it spawns is stamped with it, so the
// cards land in one contiguous block per opened card rather than mixed in by year. See placeInCol.
function expandCard(level,key,p,grp){
  const cid=`card-${level}:${key}`;
  // NOTHING this expansion spawns lands open. A cited card used to arrive already unfolded onto the
  // exact slice the edge points at — "see what this paper took from them without a click" — which
  // reads well for one source and not at all for twelve: a paper's grounds column came up as a wall
  // of open cards, every one of them carrying its own title, byline, abstract and 20-odd slice rows,
  // and finding any single paper in it meant scrolling past the rest. That was already conceded for
  // programme containers (a grant narrative's introduction can ground dozens of sentences in dozens
  // of papers), where it was written down as a special case; it is the general rule now, and the same one the landing
  // column has always followed — collapsed body, depth earned by focusing
  // (docs/2026-06-25-visualization-design.md).
  //
  // Nothing is lost by waiting. The edge anchors on the card border and stays a GHOST until the card
  // is opened, then sharpens to the cited row once its graph is unfolded — one continuum driven by
  // how much you have opened up, which is exactly what `edgeVis` (08-edges.js) is built around.
  //
  // LEFT — grounds spawn the previous generation. Curated sources get their own (collapsed) card,
  // and a sharpened ref (tid) names the source slice on the edge, which anchors there the moment
  // that row is on screen. Uncurated sources fold into one collapsed "▸ N sources" stack
  // (citation-wall collapse) — their edges anchor on the stack until the human unfolds it.
  //
  // A narrative is a LINEARIZATION — the order its sentences run in is the whole of what it adds
  // over the graph — so the column it spawns runs in that order too: the paper the introduction
  // cites first sits at the top, and reading down the prose is reading down the cards beside it.
  // Every other container keeps chronology, which is what a support DAG's grounding walk gives.
  // `citeOrd` counts every ground, curated or not, so the citation wall lands where the prose
  // first reaches for an uncurated source rather than at the foot of the block.
  const citeOrd=new Map();
  if(p.narr) (p.grounds||[]).forEach(g=>{ if(!citeOrd.has(g.key)) citeOrd.set(g.key,citeOrd.size); });
  const wall=[];
  (p.grounds||[]).forEach(g=>{
    if(!PAPERS[g.key]){ wall.push(g); return; }
    addPaper(level-1,g.key,"grounds ←",grp,citeOrd.get(g.key));
    addEdge({cardId:`card-${level-1}:${g.key}`,sid:g.tid||null},{cardId:cid,sid:g.via},"leads");
  });
  if(wall.length){
    const wallOrd=p.narr?Math.min(...wall.map(g=>citeOrd.get(g.key))):undefined;
    const sid=addStack(level-1,key,wall,"grounds ←",grp,wallOrd);
    wall.forEach(g=>addEdge({cardId:sid,sid:g.key},{cardId:cid,sid:g.via},"leads"));
  }
  // LATERAL — never spawns a column: connect to the target wherever it already sits,
  // revealing the specific claim when the ref is sharpened (Kumar → Chen2021Sys:c1).
  (p.lateral||[]).forEach(l=>{
    const from={cardId:cid,sid:l.via};
    if(l.slug){                                      // stance toward a broad claim → synthesis band
      addBroad(SYNTH,l.slug,synthLabel(),grp);
      addEdge(from,{cardId:`card-${SYNTH}:${l.slug}`,sid:null},l.sign);
      return;
    }
    const tl=findCardLevel(l.key,level);
    addEdge(from,{cardId:`card-${tl}:${l.key}`,sid:l.tid||null},l.sign);
  });
  // ANSWERS — cross-paper claim→question: like lateral, never spawns a column. The target
  // question is context-revealed (an entry row, so opening its card suffices) and the
  // edge anchors on it; a broad-question target routes to the synthesis band.
  (p.ans||[]).forEach(a=>{
    const from={cardId:cid,sid:a.via};
    if(a.slug){
      addBroad(SYNTH,a.slug,synthLabel(),grp);
      addEdge(from,{cardId:`card-${SYNTH}:${a.slug}`,sid:null},"answers");
      return;
    }
    const tl=findCardLevel(a.key,level);
    addEdge(from,{cardId:`card-${tl}:${a.key}`,sid:a.tid||null},"answers");
  });
  // RIGHT — the papers that build on this one (inverted grounds) spawn the next
  // generation rightward; the edge runs ground→derived and sharpens as either side's
  // rows are drilled (b.tid = this paper's grounded slice, b.via = the building slice).
  (p.builds||[]).forEach(b=>{
    addPaper(level+1,b.key,"builds on →",grp);
    addEdge({cardId:cid,sid:b.tid||null},{cardId:`card-${level+1}:${b.key}`,sid:b.via},"leads");
  });
  // RIGHTMOST — synthesis band; the edge sharpens to the generalizing claim once it's drilled
  (p.cons||[]).forEach(c=>{
    addBroad(SYNTH,c.slug,synthLabel(),grp);
    addEdge({cardId:cid,sid:c.via},{cardId:`card-${SYNTH}:${c.slug}`,sid:null},"leads");
  });
}

// Context-reveal a sharpened target: open its card, unfold its slice graph, and force-expand the
// drill path from an entry row down to `sid` (climbing the local outline parents — the slice's
// dependents via `up`, or the broader claim it ladders into via `gen`), so the exact slice is on
// screen. If the target is itself an entry row, opening the card suffices.
//
// The board no longer reveals anything on its own (see expandCard): the one caller left is the
// `?goto=Citekey:sid` handoff (17-handoff.js), where naming a claim MUST put that claim on screen —
// a handoff that lands on a fold is not a handoff.
function reveal(id,sid){
  ctxOpen.add(id);
  const p=PAPERS[id.slice(id.indexOf(":")+1)];
  if(!p) return;
  sliceOpen.add(id); sliceSeeded.add(id);   // the row lives in the graph; unfold the section holding it
  // A paper's card renders every slice, so unfolding it IS the reveal — there is no path to
  // force. Only an aim's outline still hides a slice behind a fold.
  if(!p.aim) return;
  const dep={};
  p.slices.forEach(s=>{
    (s.up||[]).forEach(u=>{ (dep[u]=dep[u]||[]).push(s.id); });
    (s.gen||[]).forEach(g=>{ (dep[s.id]=dep[s.id]||[]).push(g); });
  });
  const chain=[sid];
  let cur=sid, guard=0;
  while(dep[cur]&&dep[cur].length&&guard++<64){ cur=dep[cur][0]; chain.push(cur); }
  chain.reverse();                                   // entry row … target
  let s=ctxDrill.get(id);
  if(!s){ s=new Set(); ctxDrill.set(id,s); }
  let path="";
  for(let i=0;i<chain.length-1;i++){                 // expand every row above the target
    path=path?`${path}/${chain[i]}`:chain[i];
    s.add(path);
  }
}

// ── edges ──────────────────────────────────────────────────────────────────────────────
// The slug of the isolated broad node (an active broad target carries sid===null), else null.
function broadIsoSlug(iso){
  if(!iso||iso.sid!==null) return null;
  const el=document.getElementById(iso.cardId);
  if(!el||!el.classList.contains("bn")) return null;
  const id=el.dataset.id||"";
  return id.slice(id.indexOf(":")+1)||null;
}
