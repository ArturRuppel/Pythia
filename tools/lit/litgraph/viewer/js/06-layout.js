// ── hoisting ─────────────────────────────────────────────────────────────────────────────
// Clicking a broad claim pulls it AND every container that feeds it to the top of their columns.
// While the library was small the isolation highlight was enough: dim everything, and the two or
// three lit cards were on screen anyway. It isn't any more — a broad node's papers sit anywhere
// down a column of thousands, so isolating it lit up arrows that pointed off the bottom of the
// screen. Hoisting gathers the claim and its containers into one screenful, which is what
// "show me this broad claim" meant all along.
function colInsertPoint(col){                        // the first slot below the column's header
  const hd=col.querySelector(":scope > .colhd");
  return hd?hd.nextSibling:col.firstChild;
}
// Move each element to the top of its own column, preserving the order given — elements sharing a
// column stack in list order, and one already on top stays put.
function hoistAll(els){
  const prev=new Map();                              // column -> the last element hoisted into it
  for(const el of els){
    const col=el&&el.parentNode;
    if(!col||!col.classList||!col.classList.contains("col")) continue;
    const p=prev.get(col);
    // chain off the previous hoist rather than tracking a "next sibling" cursor: that cursor goes
    // null on the column's last child, and insertBefore(el,null) APPENDS — the exact opposite
    if(p) p.after(el); else col.insertBefore(el,colInsertPoint(col));
    prev.set(col,el);
  }
}
function hoistEls(slug){
  // The FAMILY is what travels, not the rung. A rung's card lives inside its root's box, so moving
  // it to the top of the column would tear it out of the containment that makes the band readable —
  // and there is nothing left to gather anyway: the narrower claims a hoist used to fetch up beside
  // this one are already nested directly under it. So the hoist has one job now, placing the box
  // that holds the claim at the top of the synthesis column, and the papers in the curated list.
  const root=broadRoot[slug]||slug;
  const els=[document.getElementById("fam-"+root)
            ||document.getElementById(`card-${SYNTH}:${root}`)];
  const seen=new Set();
  for(const lk of (BROAD_LINKS[slug]||[])){          // once per paper, however many slices feed the node
    if(seen.has(lk.key)) continue;
    seen.add(lk.key);
    // every instance, not just the landing one: an expanded paper also has a card in the
    // grounds/builds column it spawned into, and that is where its real edge anchors
    for(const lvl of Object.keys(cols).map(Number))
      if(lvl<SYNTH&&cols[lvl].keys.has(lk.key))
        els.push(document.getElementById(`card-${lvl}:${lk.key}`));
  }
  // in the order they already stand, not the order BROAD_LINKS happens to list them: a hoist moves
  // a block, it does not get to re-sort inside it. Keeps the landing column's pass ranking intact,
  // and makes replaying the stack idempotent for the blocks already in place.
  return els.filter(e=>e&&e.isConnected)
            .sort((x,y)=>(x.compareDocumentPosition(y)&Node.DOCUMENT_POSITION_FOLLOWING)?-1:1);
}
// Hoisting ACCUMULATES: the first claim you show gathers itself and its papers at the top, the
// second lands directly BELOW that block instead of shoving it down. One hoist at a time was fine
// while a hoist was assumed to be the last thing you'd do, but two claims on screen at once is what
// a synthesis band is for, and a board that reorders itself under a comparison you are halfway
// through is unusable. A paper feeding two shown claims stays with the first that claimed it —
// pulling it down on the second click would tear a hole in the block you just built.
//
// The order comes straight from `shownBroad`, which is an insertion-ordered Set and therefore
// already the click order: no second list to keep in step, because two orderings of the same fact
// are two things that can drift apart.
function hoistShown(){
  const els=[],seen=new Set();
  for(const slug of shownBroad)
    for(const el of hoistEls(slug))
      if(!seen.has(el)){ seen.add(el); els.push(el); }
  hoistAll(els);
}
const broadPapers=slug=>[...new Set((BROAD_LINKS[slug]||[]).map(l=>l.key))];
const broadTitle=slug=>(BROAD[slug]&&(BROAD[slug].title||BROAD[slug].text))||slug;
// `rung` = this card stands INSIDE a family box rather than at the head of one. A rung is written
// compact (see the fold bar): its authored `title` is the at-a-glance name SCHEMA §4 says it is,
// and the full statement is one hover away and one bar-click from being on screen for the whole
// family at once. Nothing is removed — demoted, which is the same move `.bn.titled .btx` already
// makes on a titled card.
function broadCard(slug,level,rung){
  const b=BROAD[slug], id=`${level}:${slug}`;
  const el=document.createElement("div");
  el.className="bn"+(b.kind.includes("question")?" q":"")+(b.title?" titled":"")+(rung?" rung":"");
  el.id="card-"+id; el.dataset.id=id; el.dataset.slug=slug;
  let m = b.meter?`<div class="meter"><span class="s">▲ ${b.meter.s} support</span><span class="c">▼ ${b.meter.c} contradict</span></div>`:'';
  // optional `title` (SCHEMA §4): the at-a-glance name, with the full statement as its gloss
  let t = b.title?`<div class="btl">${rich(b.title)}</div>`:'';
  // TWO READOUTS, no controls — see showBroad. Both report what the card's own click did, split by
  // what lies one step below this claim: narrower claims (up the ladder) and papers (at the foot of
  // it). A claim can have either, both, or neither; a leaf carries no affordance it cannot honour.
  const on=shownBroad.has(slug);
  const kids=(broadKids[slug]||[]).length;
  // The rung pill reads differently now that the narrower claims are literally inside this card's
  // box: it names what you are already looking at rather than pointing off across the band. Kept
  // because the count is still the fact that matters — how much of the library this claim gathers.
  const dn=kids?`<div class="bdrill${on?" on":""}"`
          +` title="the narrower claims that ladder into this one — they are nested inside this`
          +` box; click the card to gather its papers in the curated list">`
          +`${kids} narrower</div>`:"";
  // the paper readout — same shape as the rung pill, and for the same reason. It used to read
  // "showing 3 of 4", because a × could dismiss one of the papers the claim had just landed; with
  // the column flat there is nothing to dismiss and nothing to land, so the count is again a
  // constant fact about the graph and the fill says whether the block is gathered.
  const keys=broadPapers(slug);
  const dp=keys.length?`<div class="blens"><span class="lens${on?" on":""}"`
          +` title="the papers that assert this — they stand in the curated list; click the card to`
          +` gather them at the top of it">`
          +`◂ ${keys.length} paper${keys.length===1?"":"s"}</span></div>`:"";
  // Multi-parenting, stated on the card that hosts it. Without this the reference rows elsewhere
  // are the only trace, and a reader who lands on the real card has no way to know the claim also
  // answers to a second, possibly quite distant, parent.
  const alt=(BROAD[slug].leads_to||[]).filter(r=>BROAD[r]&&r!==broadHost[slug]);
  const av=alt.length?`<div class="balso" title="this claim ladders into more than one broader`
          +` claim; it is nested under the first its leads_to names and referenced under the rest">`
          +`also under ${alt.map(r=>"“"+esc(broadTitle(r))+"”").join(" · ")}</div>`:"";
  el.innerHTML=`<div class="bkd">${esc(b.kind)}</div>${t}<div class="btx">${rich(b.text)}</div>${m}${av}`
              +(dn?`<div class="bdrills">${dn}</div>`:"")+dp;
  // the statement a folded rung trades away is one hover from coming back
  if(rung) el.title=b.text;
  // No per-chip handlers left: the card is the only thing on it that takes a click.
  // hovering a broad node isolates its edges and lights up the papers linked into it
  el.addEventListener("mousemove",e=>{ e.stopPropagation(); setHover({cardId:el.id,sid:null}); });
  el.addEventListener("mouseleave",()=>setHover(null));
  el.addEventListener("click",e=>{ e.stopPropagation(); showBroad(slug); });
  return el;
}

// ── the family container ─────────────────────────────────────────────────────────────────
// One box per ladder root, holding its whole descent. The root's own card is the box's header —
// exactly as a paper's citekey/title header names the container its slices sit in — and everything
// that ladders into it nests below, recursively. A root with nothing under it is not a container at
// all, just the card it always was; a box with one member in it would be chrome around a fact.
const famFolded=new Set();   // roots whose rungs are folded to their titles (default: all of them)
let famSeeded=false;         // …seeded once, so a fold the reader opened survives every rebuild
// "the thing you asked for is HERE": a brief ring, on every mark the board can be sent to (a card,
// a broad node, a slice row). One implementation because four places want the identical gesture —
// the search box, a library row, a shown claim and the ?goto= handoff — and a jump that flashed
// differently depending on which door you came through would read as four different events.
function flash(el){
  el.classList.remove("found"); void el.offsetWidth;      // restart a flash still running
  el.classList.add("found");
  setTimeout(()=>el.classList.remove("found"),1800);
}
function scrollToBroad(slug){
  const el=document.getElementById(`card-${SYNTH}:${slug}`);
  if(!el) return;
  el.scrollIntoView({behavior:"smooth",block:"center"});
  flash(el);
}
// `seen` is the cycle guard the rest of this file carries for the same reason (see computeBroadTiers):
// nothing here re-validates a `leads_to` cycle, which would otherwise recurse until the tab dies.
// Nesting stops at the repeat; the node keeps its card wherever it was first reached.
function famNest(slug,root,depth,seen){
  const box=document.createElement("div");
  box.className="bnest";
  for(const kid of broadNest[slug]) box.appendChild(famBranch(kid,root,depth+1,seen));
  // A claim hosted by another parent still has to be VISIBLE here, or this box quietly lies about
  // what ladders into it. It is a pointer, not a copy: one row, the real card's name, and a click
  // that goes and finds it. Copying the card is what an outline does and what the paper card's DAG
  // was written to stop.
  for(const kid of broadRefs[slug]){
    const r=document.createElement("div");
    r.className="bref";
    r.innerHTML=`<span class="brefa">↗</span><span class="breft">${esc(broadTitle(kid))}</span>`
      +`<span class="brefn">nested under “${esc(broadTitle(broadHost[kid]))}”</span>`;
    r.title="also ladders into this claim — the card lives under its first parent; click to go to it";
    r.addEventListener("click",e=>{ e.stopPropagation(); scrollToBroad(kid); });
    box.appendChild(r);
  }
  return box;
}
function famBranch(slug,root,depth,seen){
  const wrap=document.createElement("div");
  wrap.className="bbranch";
  wrap.appendChild(broadCard(slug,SYNTH,true));
  if(seen.has(slug)) return wrap;                          // cycle: card yes, descent no
  seen.add(slug);
  if(broadNest[slug].length||broadRefs[slug].length) wrap.appendChild(famNest(slug,root,depth,seen));
  return wrap;
}
// The whole family, as it stands in the synthesis column. `fam-<root>` is what hoisting moves: the
// family is the unit that travels, because pulling one rung out of its box to the column top would
// undo the containment that is the entire point.
function familyEl(root){
  const has=broadNest[root].length||broadRefs[root].length;
  const head=broadCard(root,SYNTH,false);
  if(!has){ head.id="card-"+SYNTH+":"+root; head.dataset.fam=root; return head; }
  const el=document.createElement("div");
  el.className="bfam"; el.id="fam-"+root; el.dataset.fam=root;
  const n=(function size(s,seen){
    if(seen.has(s)) return 0;
    seen.add(s);
    return broadNest[s].reduce((a,c)=>a+size(c,seen),0)+1;
  })(root,new Set())-1;
  const folded=famFolded.has(root);
  const bar=document.createElement("div");
  bar.className="bfbar";
  // "in this ladder", not "narrower": the head card's own pill already says how many claims are ONE
  // rung down, and two adjacent counts both labelled "narrower" would be read as a contradiction.
  // This one is the whole descent — every claim inside the box, at any depth.
  bar.innerHTML=`<span class="bfn">${n} in this ladder</span>`
    +`<span class="bffold">${folded?"show statements":"fold to titles"}</span>`;
  bar.addEventListener("click",e=>{
    e.stopPropagation();
    if(famFolded.has(root)) famFolded.delete(root); else famFolded.add(root);
    rebuild();
  });
  el.appendChild(head);
  el.appendChild(bar);
  el.appendChild(famNest(root,root,0,new Set([root])));
  el.classList.toggle("folded",folded);
  return el;
}

function ensureCol(level,label){
  if(cols[level]) return cols[level];
  const el=document.createElement("div"); el.className="col";
  if(label) el.innerHTML=`<div class="colhd">${label}</div>`;
  cols[level]={el,keys:new Set(),label};
  // insert in DOM ordered by level (left→right)
  const levels=Object.keys(cols).map(Number).sort((a,b)=>a-b);
  const idx=levels.indexOf(level);
  if(idx===levels.length-1) stage.appendChild(el);
  else stage.insertBefore(el, cols[levels[idx+1]].el);
  return cols[level];
}
// ── where a spawned card goes vertically ─────────────────────────────────────────────────
// Every card in a spawned column carries the GROUP that pulled it in: the index of the card you
// opened, in the order you opened it (see rebuild's sweep). A column sorts by group first and by
// its own rule second. That ordering is the whole point — a column sorted only by year lets the
// second thing you click interleave into the first thing's block, so the board silently rearranges
// itself around a click that was meant to ADD something. Group-first means each click's material
// lands below the last one's, and what is already on screen stays where you left it.
//
// Cards nobody opened for — the synthesis band's standing backfill — carry BACKFILL and sit under
// everything, so the band still reads as the complete ladder once the opened claims are past.
const BACKFILL=1e9;
const cardGrp=el=>{ const g=+el.dataset.grp; return Number.isFinite(g)?g:BACKFILL; };
// A card's rank in the walk that spawned it. It is stamped only when the container doing the
// spawning has a reading order of its own, so it is NaN on a card placed by chronology.
const cardOrd=el=>{ const o=+el.dataset.ord; return Number.isFinite(o)?o:NaN; };
// The tie-break inside one group, as a `within` predicate for placeInCol: does the incoming card
// belong above the one being compared. Chronology (year desc) is the rule, unless `ord` names the
// incoming card's place in its spawner's own order, which then wins and is stamped on the card so
// the cards after it have something to compare against. One walk spawns a whole group, so a group
// is never half ordered by one rule and half by the other.
function withinRule(el,ord){
  if(ord==null){ const yr=+el.dataset.year||0; return ch=>(+ch.dataset.year||0)<yr; }
  el.dataset.ord=ord;
  return ch=>cardOrd(ch)>ord;                        // NaN compares false: a chronological card stays put
}
// `within` breaks the tie inside one group: withinRule for papers, arrival order for broad nodes.
function placeInCol(c,el,grp,within){
  el.dataset.grp=grp;
  let before=null;
  for(const ch of c.el.querySelectorAll(":scope > .card, :scope > .bn, :scope > .bfam")){
    const g=cardGrp(ch);
    if(g>grp||(g===grp&&within(ch))){ before=ch; break; }
  }
  c.el.insertBefore(el,before);
}
// `ord` is where this card stands in the order its spawner reads in, when the spawner has one
// (expandCard passes it for a narrative and for nothing else); without it, chronology falls out of
// the grounding walk within a group, which is the older and still the general rule.
function addPaper(level,key,label,grp,ord){
  const c=ensureCol(level,label);
  if(c.keys.has(key)) return;          // de-dup by citekey (accumulate) — and the FIRST group to
  c.keys.add(key);                     // ask for a card keeps it; a later one only adds an edge
  const card=paperCard(key,level);
  if(level===0){ c.el.appendChild(card); return; }   // landing keeps its pass ranking
  placeInCol(c,card,grp==null?BACKFILL:grp,withinRule(card,ord));
}
// A broad node is never placed alone: naming any rung places its whole FAMILY, because a rung's
// card only exists inside its root's box. So the column's key — and the dedup — is the root, and
// every member is registered under it so a second call naming a sibling is a no-op.
function addBroad(level,slug,label,grp){
  const c=ensureCol(level,label);
  if(c.keys.has(slug)) return;
  const root=broadRoot[slug]||slug;
  if(c.keys.has(root)) { c.keys.add(slug); return; }
  for(const s in BROAD) if((broadRoot[s]||s)===root) c.keys.add(s);
  // no second key inside a group: claims arrive in the order the open paper cites them, and the
  // backfill in the ladder's own standing order, both of which are already the order to show them in
  placeInCol(c,familyEl(root),grp==null?BACKFILL:grp,()=>false);
}
// The synthesis band always shows every broad claim / question, expanded state or not —
// they're the standing right-hand column. expandCard still adds the ones linked from an
// open paper (with real edges); this backfills the rest (deduped), so the band is complete
// on the landing view and survives every rebuild. Unlinked-yet nodes stay hover-active
// (broadExtraEdges lights their papers) like any other broad node.
function ensureBroadBand(){
  // Every family, every rebuild, in the standing order broadFamilies settled. addBroad de-dups on
  // the root, so a family expandCard already materialized for an open paper's real edges is left
  // where that click put it.
  for(const root of broadOrder) addBroad(SYNTH,root,synthLabel());
  // The broad-to-broad half of `leads-to` (SCHEMA §4) is now drawn as CONTAINMENT — a rung inside
  // its parent's box — so the arrows that used to carry it are gone. They were suppressed at rest
  // anyway (redraw hides every broad edge until the node is hovered or clicked), which is exactly
  // why the ladder read as invisible: the relation was only ever drawn on demand.
  //
  // What containment cannot draw is the SECOND parent of a multi-parented claim. That one keeps its
  // arrow, and it is worth an arrow precisely because it is the edge the boxes do not express —
  // together with the reference row famNest leaves in the other parent, it is how a claim that
  // ladders into two places stays honest without being duplicated.
  for(const [slug,b] of Object.entries(BROAD))
    for(const r of (b.leads_to||[]))
      if(BROAD[r]&&r!==broadHost[slug])
        addEdge({cardId:`card-${SYNTH}:${slug}`,sid:null},
                {cardId:`card-${SYNTH}:${r}`,sid:null},"gen");
}
// Citation-wall collapse: a focused paper's UNCURATED sources never spawn cards — they fold
// into one "▸ N sources" stack per focused card, expandable on demand and ONLY on demand
// (reveal()/rebuild() never unfold it, so it stays collapsed under any programmatic
// expansion). Rows carry data-sid=<citekey>, so a wall edge sharpens from the stack card to
// its source row the moment the stack is unfolded. Returns the stack element id.
function addStack(level,owner,wall,label,grp,ord){
  const c=ensureCol(level,label);
  const key=owner+"::srcs", id=`${level}:${key}`, eid="card-"+id;
  if(c.keys.has(key)) return eid;
  c.keys.add(key);
  const srcs=[...new Set(wall.map(g=>g.key))]
    .map(k=>({k,p:STUBS[k]||{}}))
    .sort((a,b)=>(b.p.year||0)-(a.p.year||0));
  const el=document.createElement("div");
  el.className="card stack"+(stacks.has(id)?" open":"");
  el.id=eid; el.dataset.id=id;
  el.dataset.year=srcs.length?(srcs[0].p.year||0):0;   // sorts by its newest source
  el.innerHTML=`<div class="chd"><span class="car">${stacks.has(id)?"▾":"▸"}</span>`
    +`<span class="ckey">${srcs.length} source${srcs.length===1?"":"s"}</span></div>`
    +`<div class="srcs">`+srcs.map(s=>
      `<div class="src${stubOpen.has(s.k)?" open":""}" data-sid="${s.k}">`
      +`<span class="skey">${s.k}</span>`
      +`<span class="sy">${s.p.year||""}</span>`+stubDetail(s.k,s.p)+`</div>`).join("")+`</div>`;
  el.addEventListener("click",()=>{
    if(stacks.has(id)) stacks.delete(id); else stacks.add(id);
    el.classList.toggle("open",stacks.has(id));
    el.querySelector(".car").textContent=stacks.has(id)?"▾":"▸";
    redraw();                                          // anchors move; edges re-route
  });
  for(const row of el.querySelectorAll(".src")){
    row.addEventListener("mousemove",e=>showTip(e,row.dataset.sid,row));
    row.addEventListener("mouseleave",dropTip);
    // stopPropagation or the stack's own handler folds the whole wall shut under the reader:
    // reading one source is the opposite of putting all of them away.
    row.addEventListener("click",e=>{ e.stopPropagation(); dropTip(); toggleStub(row.dataset.sid); });
  }
  placeInCol(c,el,grp==null?BACKFILL:grp,withinRule(el,ord));   // grouped, then the same rule as cards
  return eid;
}

const edgeSeen=new Set();
// each endpoint is {cardId, sid}: it anchors at sid's row when visible, else at the card.
// `intra` marks an edge whose two ends are rows in the SAME card — the paper's own subgraph.
// It only changes the geometry (redraw bows it into the card's left gutter instead of reaching
// for a facing edge that isn't there); everything else about an edge is the same either way.
function addEdge(from,to,kind,intra){      // de-dup: rebuilds must not stack duplicate paths
  const k=`${from.cardId}:${from.sid}|${to.cardId}:${to.sid}|${kind}`;
  if(edgeSeen.has(k)) return;
  edgeSeen.add(k); edges.push({from,to,kind,intra:!!intra});
}

// Recompute every spawned column + edge from the open set (non-exclusive: opening one
// paper never tears down another). An open card at level L pours its grounds into L-1 and
// the papers that build on it into L+1; if a spawned card is opened too, the sweep drills
// it in turn — cross-paper expansion is iterative, one generation per click. Expansion
// runs both directions, so the sweep iterates to a fixpoint instead of walking one way.
// `hold` is the card the human just acted on ("level:key"), if any. The landing column pins the
// horizontal axis for everyone; the held card pins the vertical one for the click that caused
// the rebuild, because hoisting reorders whole blocks and a card halfway down a long column
// would otherwise vanish upward the moment you opened it.
function rebuild(hold){
  // The landing column is a fixed anchor: content expands out from it (grounds ←, builds →)
  // without it sliding sideways. Capture its screen-x before the DOM churns, restore it after
  // by compensating scrollLeft for whatever columns were inserted/removed to its left.
  const anchorEl=cols[0]&&cols[0].el;
  const beforeLeft=anchorEl?anchorEl.getBoundingClientRect().left:0;
  const holdEl=hold&&document.getElementById("card-"+hold);
  const beforeTop=holdEl?holdEl.getBoundingClientRect().top:null;
  Object.keys(cols).map(Number).forEach(lvl=>{
    if(lvl!==0){ cols[lvl].el.remove(); delete cols[lvl]; return; }
    for(const k of [...cols[0].keys]){          // stacks are rebuild-scoped; the landing
      if(!k.endsWith("::srcs")) continue;       // column persists, so evict its stacks
      cols[0].keys.delete(k);
      const el=document.getElementById(`card-0:${k}`); if(el) el.remove();
    }
  });
  edges=[]; edgeSeen.clear(); hover=null; unpinned=null;   // rows re-render; next mousemove re-isolates (docked viewer rests)
  broadRefresh();                    // tiers + nesting, fresh before anything places a broad card
  syncLanding();                     // before the expansion sweep below reads cols[0].keys
  document.querySelectorAll(".card.open,.card.focus").forEach(c=>c.classList.remove("open","focus"));
  ctxOpen=new Set(); ctxDrill=new Map();
  // The sweep walks `open` in the order you OPENED things, not in column order, because that index
  // is the group every spawned card inherits (placeInCol): open a second paper and its grounds
  // stack below the first paper's instead of interleaving by year. `open` is a Set, so it is
  // already insertion-ordered, and a card closed and reopened rightly counts as a fresh arrival.
  // Still a fixpoint loop rather than a straight walk — a card at level 2 has no column to live in
  // until the level-1 card that spawns it has expanded — but the group comes from the index, so a
  // late unlock still lands in the block belonging to its own click.
  const seq=[...open], done=new Set();
  let changed=true;
  while(changed){
    changed=false;
    seq.forEach((id,grp)=>{
      if(done.has(id)) return;
      const i=id.indexOf(":"), lvl=+id.slice(0,i), key=id.slice(i+1);
      if(lvl>=SYNTH||!PAPERS[key]||!cols[lvl]||!cols[lvl].keys.has(key)) return;
      done.add(id); expandCard(lvl,key,PAPERS[key],grp); changed=true;
    });
  }
  ensureBroadBand();                                 // keep the full synthesis band standing
  // apply visual state + drill regions for focused and context-opened cards
  for(const id of new Set([...open,...ctxOpen])){
    const el=document.getElementById("card-"+id);
    if(!el||!PAPERS[id.slice(id.indexOf(":")+1)]) continue;
    el.classList.add("open");
    if(open.has(id)) el.classList.add("focus");      // ctx-only cards: revealed, not focused
    renderSlices(id);
  }
  // Stubs re-open from their own state: the blanket strip above takes `.open` off every card, and
  // a stub carries none of the open/ctxOpen machinery that puts it back. Run after every minting
  // site (syncLanding, the expansion sweep, ensureBroadBand), so a stub materialized by this very
  // rebuild lands expanded rather than snapping shut under the reader. Wall rows are re-minted
  // with the class already on (addStack reads stubOpen); they are swept here too so the two
  // renderings of one citekey cannot come out of a rebuild disagreeing.
  if(stubOpen.size) document.querySelectorAll(".card.stub,.card.stack .src").forEach(c=>{
    const k=c.dataset.key||c.dataset.sid;
    if(stubOpen.has(k)) c.classList.add("open");
  });
  // A claim's brightness is DERIVED from whether it is shown, never pinned independently: that is
  // the merge (see showBroad). Deriving rather than toggling is what makes it impossible for the
  // arrows and the papers column to disagree about which claims you are looking at.
  pin=pin.filter(p=>cardIdLevel(p.cardId)<SYNTH);
  for(const slug of shownBroad){
    const cardId=`card-${SYNTH}:${slug}`;
    if(document.getElementById(cardId)) pin.push({cardId,sid:null});
  }
  hoistShown();                                       // blocks in the order they were shown
  if(anchorEl){                                       // hold the anchor column visually still
    board.scrollLeft+=anchorEl.getBoundingClientRect().left-beforeLeft;
  }
  if(beforeTop!=null){                                // …and the clicked card at its own height
    const el=document.getElementById("card-"+hold);
    if(el) board.scrollTop+=el.getBoundingClientRect().top-beforeTop;
  }
  redraw();
}

