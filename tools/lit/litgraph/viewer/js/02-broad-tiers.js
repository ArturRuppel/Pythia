                         // computeBroadTiers since it walks exactly that relation already
// The band is FLAT: every rung of every ladder has a card, always. It was not always — the band
// used to land on its ROOTS only, and a rung appeared when the human showed the node above it, on
// the theory that 42 nodes at once is a backlog and 14 is a view. Hiding was the wrong tool for
// that job. Once ORDER does the organizing, hiding only subtracts: you cannot see that a claim you
// have not clicked exists, cannot read the shape of the ladder without walking it, and a claim
// reachable through two parents flickers in and out depending on which one you have open.
//
// So `shownBroad` means one thing only: whose block is gathered at the top (and whose papers are in
// the column). Nothing about it decides what exists on screen. That still holds — the band is now
// CONTAINERIZED rather than flat (see broadFamilies), and containment reveals nothing and hides
// nothing; it only puts a family in one box instead of spraying it across four columns.
function computeBroadTiers(){
  const kids={};                                    // slug -> broad nodes that ladder INTO it
  for(const s in BROAD) kids[s]=[];
  for(const [s,b] of Object.entries(BROAD))
    for(const r of (b.leads_to||[])) if(kids[r]) kids[r].push(s);
  const tier={}, visiting=new Set();
  function tierOf(slug){
    if(slug in tier) return tier[slug];
    if(visiting.has(slug)) return 0;                // a cycle here means the build already
    visiting.add(slug);                             // rejected it; just don't hang on stale data
    let t=0;
    for(const c of kids[slug]) t=Math.max(t,tierOf(c)+1);
    visiting.delete(slug);
    return tier[slug]=t;
  }
  for(const slug in BROAD) tierOf(slug);
  broadKids=kids;
  return tier;
}
// ── the band as containers ───────────────────────────────────────────────────────────────
// The band used to be four COLUMNS keyed by altitude — `broadLevel` returned SYNTH+tier and each
// rung stood in the column its tier put it in. Altitude is a derived scalar; `leads_to` between two
// broad nodes is the relation actually authored, and rendering the scalar instead of the relation
// sprayed every family across the board: tier 0 alone held 34 of 45 cards, and the only thing
// tying a parent to its children was an arrow `redraw` deliberately suppresses until the node is
// hovered or clicked. At rest the ladder was not drawn at all.
//
// So a family is a CONTAINER, the same way a paper is a container of its slices (CONCEPT: the model
// is recursively containerized). Containment is drawn as containment — a box inside a box — which
// is why the rung arrows are gone rather than merely dimmed: geometry says what the arrow said, and
// says it without being hovered. One synthesis column now, one card per ladder root, everything
// under that root nested inside it.
//
// There is therefore no `broadLevel` any more: every broad card's id is `card-<SYNTH>:<slug>`
// whatever its altitude, so every id-building call site (expandCard, hoistEls, showBroad, the pin
// derivation) is unchanged — the card moved in the DOM, not in the addressing scheme.
const synthLabel=()=>"synthesis →";

// A node with two parents cannot nest under both without being duplicated, and duplication is
// precisely what `localDag` was written to stop doing to the paper card. So: a node NESTS under the
// first parent its authored `leads_to` names, and every other parent gets a REFERENCE row pointing
// at the real card. Authored order means the curator decides which parent hosts, with no magic to
// reverse-engineer. A node whose parents sit under different roots is the case this exists for.
let broadHost={};      // slug -> the parent that nests it ("" for a root)
let broadNest={};      // slug -> children nested inside it, in ladder order
let broadRefs={};      // slug -> children that live elsewhere and are only referenced here
let broadRoot={};      // slug -> the root of its hosting chain (its family)
let broadOrder=[];     // roots, in the standing order the band lays them out
function broadFamilies(){
  broadHost={}; broadNest={}; broadRefs={}; broadRoot={};
  for(const s in BROAD){ broadNest[s]=[]; broadRefs[s]=[]; }
  for(const s in BROAD){
    const par=(BROAD[s].leads_to||[]).filter(r=>BROAD[r]);
    broadHost[s]=par[0]||"";
    if(par[0]) broadNest[par[0]].push(s);
    for(const r of par.slice(1)) broadRefs[r].push(s);
  }
  // the root of the hosting chain; the guard is for a cycle the build should already have rejected
  const rootOf=(s,seen)=>{
    const h=broadHost[s];
    if(!h||seen.has(s)) return s;
    seen.add(s); return rootOf(h,seen);
  };
  for(const s in BROAD) broadRoot[s]=rootOf(s,new Set());
  // Standing order: families before leaves, biggest family first, then kind, then slug. Structure
  // ahead of orphans is the useful reading — and note this deliberately does NOT sort by kind
  // first. Separating the broad methods from the broad claims is still the open question of
  // 2026-08-03 §7; containers make it far less pressing (the two method ladders become their own
  // boxes and self-segregate) without deciding it here.
  const size=(s,seen)=>seen.has(s)?0:(seen.add(s),broadNest[s].reduce((n,c)=>n+size(c,seen),1));
  broadOrder=Object.keys(BROAD).filter(s=>!broadHost[s])
    .sort((a,b)=>size(b,new Set())-size(a,new Set())
                ||BROAD[a].kind.localeCompare(BROAD[b].kind)||a.localeCompare(b));
}
// Everything the band derives from BROAD, in one call — because there are two entry points that
// need it (boot, which never calls rebuild, and rebuild itself) and two of them computing half of
// it each is exactly how the band's altitudes and its nesting would drift out of step.
function broadRefresh(){
  broadTier=computeBroadTiers();
  broadFamilies();
  // A family lands folded to its rungs' titles: the band is the standing MAP of what the library
  // claims, and a map shows names. Seeded once, so a box the reader opened stays open across every
  // rebuild — the fold is a reading position, and a click elsewhere must not reset it.
  if(!famSeeded){ famSeeded=true; for(const r of broadOrder) famFolded.add(r); }
}

