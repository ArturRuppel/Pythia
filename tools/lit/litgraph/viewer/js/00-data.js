const PAPERS = GRAPH.papers;
const BROAD = GRAPH.broad;
const STUBS = GRAPH.stubs;
const ORDER = GRAPH.order;
// The topic axis (SCHEMA §9) — a saved-search tree over the paper `tags` vocabulary, computed
// once in Python (build.py's _topics_json: closure + curated membership already reduced, so
// this viewer never re-walks `broader`). `|| {}` covers both an untopiced repo (to_json_dict
// still emits "topics": {}) and `lit preview`'s isolated payload, which carries no "topics" key
// at all (preview.isolate() reduces to one paper — see preview.py).
const TOPICS = GRAPH.topics || {};
// Collections (SCHEMA §10): papers gathered for a purpose — a review, a grant, a talk — found by
// typing the collection's title into search. `papers` is authored order, curated and stubs alike;
// PAPERS / STUBS say which is which. Never graph: nothing here draws an edge to one. `|| {}` for
// the same two cases as TOPICS (no collections/ tree; a `lit preview` payload).
const COLLECTIONS = GRAPH.collections || {};
// The narrative key (`~<grant>`) when this payload is a PROPOSAL page — the introduction plus
// the aims under it, isolated together (preview.isolate_proposal) — else null. Only the landing
// column's own header reads it: everything else on such a page is an ordinary card doing the
// ordinary thing, which is the entire point of building the narrative as a container.
const PROPOSAL = GRAPH.proposal || null;

// slug -> every curated paper that links into that broad node (generalize / stance / answer),
// independent of expansion state. Lets a broad-node hover reach papers still collapsed in the
// landing column, not just the expanded ones whose edges happen to already be drawn.
const BROAD_LINKS = {};
function buildBroadLinks(){
  for(const k in BROAD_LINKS) delete BROAD_LINKS[k];   // idempotent: a live refresh rebuilds it
  const push=(slug,key,via,kind)=>{ (BROAD_LINKS[slug]=BROAD_LINKS[slug]||[]).push({key,via,kind}); };
  for(const [key,p] of Object.entries(PAPERS)){
    if(!p.cur) continue;
    (p.cons||[]).forEach(c=>push(c.slug,key,c.via,"leads"));
    (p.lateral||[]).forEach(l=>{ if(l.slug) push(l.slug,key,l.via,l.sign); });
    (p.ans||[]).forEach(a=>{ if(a.slug) push(a.slug,key,a.via,"answers"); });
  }
}
buildBroadLinks();

