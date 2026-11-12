// ── the paper's local subgraph ───────────────────────────────────────────────────────────
// A paper's slices form a small DAG — measured across the 53 curated papers it is never
// deeper than 5 nor wider than 12 — and this reduces it to a drawing order for that DAG.
//
// Direction: `a` stands ABOVE `b` when a rests on b (grounded_in), when a is the broader
// claim b ladders into (local leads_to), or when a is the question b answers. So the top of
// the list is what the paper concluded and the bottom is the floors it stands on, which is
// the order the outline used to nest in — minus the nesting.
//
//   * `rows`  — every slice exactly once, each below all of its parents (Kahn, depth-first
//     so a chain stays contiguous, ties broken by authored order).
//   * `depth` — longest path from a root, the indent. Reproduces the outline's shape for the
//     tree-like part without paying its duplication for the parts that aren't a tree.
//   * `links` — the real edges, drawn as arcs. This is the half an outline threw away: a
//     support with two parents, and a claim that grounds in something three generations down.
function localDag(p){
  const byId = {}; p.slices.forEach(s => byId[s.id] = s);
  const rank = {}; p.slices.forEach((s, i) => rank[s.id] = i);
  const kids = {}, par = {}, links = [];
  const link = (a, b, kind) => {
    if (a === b || !byId[a] || !byId[b]) return;
    if (links.some(l => l.a === a && l.b === b)) return;      // one arc per pair, whatever the refs
    links.push({a, b, kind});
    (kids[a] = kids[a] || []).push(b);
    (par[b] = par[b] || []).push(a);
  };
  p.slices.forEach(s => {
    (s.up || []).forEach(u => link(s.id, u, "leads"));        // s rests on u
    (s.gen || []).forEach(g => link(g, s.id, "gen"));         // g is the broader claim s ladders into
    (s.answers || []).forEach(q => link(q, s.id, "answers")); // the question stands over its answer
  });
  const rows = [], seen = new Set();
  const pend = {}; p.slices.forEach(s => pend[s.id] = (par[s.id] || []).length);
  // Among slices that are all equally free to be placed, order by the paper's own rhetoric —
  // the same order the entry groups used to impose as containers: the line of inquiry it
  // answered, then its novel claims, then the ones it merely restates, then the methods, and
  // last the questions it leaves OPEN. The groups were headings over that order; a topological
  // sort can carry it as a tie-break instead, which is how the reading survives the flattening.
  const bucket = s => s.kind === "question" ? (s.answered ? 0 : 4)
                    : s.kind === "method" ? 3
                    : s.color === "borrowed" ? 2 : 1;
  const ord = {}; p.slices.forEach(s => ord[s.id] = bucket(s) * 1e4 + rank[s.id]);
  const byRank = a => a.slice().sort((x, y) => ord[y] - ord[x]);     // stack pops the first wanted
  const ready = byRank(p.slices.filter(s => !pend[s.id]).map(s => s.id));
  while (ready.length) {
    const n = ready.pop();
    if (seen.has(n)) continue;
    seen.add(n); rows.push(n);
    const freed = (kids[n] || []).filter(c => --pend[c] === 0);
    ready.push(...byRank(freed));                             // depth-first: a chain stays together
  }
  // a cycle would strand its members; the schema forbids one, but a stranded slice must still
  // render — dropping a proposed claim silently is the one failure mode this card can't have
  p.slices.forEach(s => { if (!seen.has(s.id)) { seen.add(s.id); rows.push(s.id); } });

  // ── the columns ────────────────────────────────────────────────────────────────────────
  // A slice's column is its longest chain of local support: a slice resting on nothing local
  // is a floor and sits at 0, and everything stands one column right of the furthest thing it
  // leans on. So the axis reads ground → derived, left → right, the same direction `leads-to`
  // runs everywhere else in this viewer — the card is the board one scale down.
  //
  // A claim with no LOCAL grounding lands in column 0 beside the methods, which looks wrong for
  // about a second and is then exactly right: its grounding is a citation, and the paper it
  // cites is the card immediately to the left of this one.
  const lv = {};
  const level = (n, st) => {
    if (lv[n] != null) return lv[n];
    if (st.has(n)) return 0;                                  // defensive: a cycle stops here
    st.add(n);
    lv[n] = Math.max(0, ...(kids[n] || []).map(k => level(k, st) + 1));
    st.delete(n); return lv[n];
  };
  rows.forEach(n => level(n, new Set()));
  const width = Math.max(0, ...Object.values(lv)) + 1;
  const cols = Array.from({length: width}, () => []);
  rows.forEach(n => cols[lv[n]].push(n));                     // rows order = the rhetoric tie-break
  // Order each column by the barycentre of what it rests on, so an edge runs as near to
  // horizontal as the graph allows and two supports of one claim sit next to each other rather
  // than at opposite ends of a column. Column 0 has nothing to its left, so it keeps the
  // rhetoric order; every column after it is placed against the one already settled.
  for (let c = 1; c < width; c++) {
    const at = {}; cols[c - 1].forEach((n, i) => at[n] = i);
    const bary = {};
    cols[c].forEach((n, i) => {
      const ks = (kids[n] || []).filter(k => at[k] != null).map(k => at[k]);
      bary[n] = ks.length ? ks.reduce((a, b) => a + b, 0) / ks.length : i;
    });
    cols[c].sort((x, y) => bary[x] - bary[y] || rows.indexOf(x) - rows.indexOf(y));
  }
  return {rows, cols, lv, links, byId, par, kids};
}

// Render that DAG as columns of nodes: one node per slice, its column its support depth, with
// the edges handed to redraw(). The card body scrolls sideways when the ladder is longer than
// the window — and folding (a node by click, the card by the bar's toggle) is the way out of
// that: badges are a quarter the width, so a folded card puts the whole ladder on screen at
// once. Read the text one column at a time, fold to see the shape.
// Is a card's slice graph unfolded from the start? On the BOARD, no: a card is opened to read the
// paper, and its subgraph is a second question — three open cards used to put ~80 rows of prose and
// a hundred arcs on screen at once, burying the bibliographic heads they hang off. On a page that
// IS one card — `lit preview`'s isolated render, an aim or proposal page — the slices are the
// entire reason the page exists, so making you click for them is a papercut on every step of the
// loop. ORDER.length === 1 is exactly that case (isolate() emits a single-container payload).
const sliceDefaultOpen = () => ORDER.length === 1;

function renderGraph(id, key, p, box){
  const {rows, cols, links} = localDag(p);
  const cid = "card-" + id;
  const folded = sFold.get(id) || new Set();
  const all = rows.length && rows.every(n => folded.has(n));
  // Seeded once per card (like grpSeeded), so unfolding sticks across the rebuilds a click causes;
  // a close clears the seed and the card reopens on the default view.
  if (!sliceSeeded.has(id)) { sliceSeeded.add(id); if (sliceDefaultOpen()) sliceOpen.add(id); }
  const shown = sliceOpen.has(id);
  // Shut, the bar is the whole section: a caret and the size of what is behind it. The axis label
  // and the fold toggle describe columns that aren't on screen, so they wait for them.
  let html = `<div class="sbar${shown ? "" : " shut"}"><span class="gcar">${shown ? "▾" : "▸"}</span>`
           + `<span>${rows.length} slice${rows.length === 1 ? "" : "s"}`
           + ` · ${links.length} edge${links.length === 1 ? "" : "s"}</span>`
           + (shown ? `<span class="saxis">ground →&nbsp;derived</span>`
                    + `<span class="sfold">${all ? "show text" : "fold to graph"}</span>` : ``)
           + `</div>`;
  // Nothing rendered, nothing anchored: with no rows on screen the within-card arcs have no honest
  // place to be drawn (edgeVis clause 1 turns an intra edge off the moment either end falls back to
  // the card), so they are not added at all, and a cross-paper edge into this card anchors on the
  // border until the reader opens the graph — the same continuum a collapsed card is already on.
  if (!shown) { box.innerHTML = html; return; }
  html += `<div class="snodes${all ? " allfold" : ""}">`;
  cols.forEach((col, c) => {
    html += `<div class="scol"><div class="schd">${c === 0 ? "floors" : "· ".repeat(c)}`
          + `<span class="sct">${col.length}</span></div>`;
    // the slices a programme container on THIS page points at (preview.py `_cited_neighbour`);
    // empty on the main board. Marking them is what the old trim was really for — "what does the
    // proposal take from this paper" — minus throwing the rest of the paper away to say it.
    const cited = new Set(p.cited || []);
    for (const sid of col) {
      const s = p.slices.find(x => x.id === sid);
      const ans = s.kind === "question" && s.answered ? " ans" : "";
      const pdf = (LIVE && s.quote) ? " pdf-src" : "";   // quote-bearing → hover aims the docked viewer
      const cit = cited.has(sid) ? " cite" : "";
      html += `<div class="slice${pdf}${cit}${folded.has(sid) ? " fold" : ""}" data-sid="${s.id}"`
            + ` title="click to fold this slice to its badge">`
            + `<span class="sid ${SID_CLASS[s.color] || 'cl'}${ans}">${s.id}</span>`
            + `<span class="stx">${rich(s.text)}</span>`
            + `<span class="fkd">${s.kind}</span>`
            + `</div>`;
    }
    html += `</div>`;
  });
  box.innerHTML = html + `</div>`;
  // The columns scroll under a stationary overlay, so the arcs have to be re-laid on every
  // scroll tick or they detach from the nodes they belong to.
  box.querySelector(".snodes").addEventListener("scroll", redraw);
  // The within-paper edges go to the same overlay the cross-paper ones use, so they inherit the
  // whole isolation story for free: faint at rest, bright when the hover or a pin touches either
  // end. That dimming is what keeps 34 arcs legible in the space between five columns.
  //
  // Emitted ground → derived (`l.b` rests under `l.a`), so the arrowhead lands on the derived
  // slice and every arrow in this card points the same way as every arrow on the board.
  for (const l of links)
    addEdge({cardId: cid, sid: l.b}, {cardId: cid, sid: l.a}, l.kind, true);
}

// Drill-down rendering (AIM cards): entry rows are the top of the container's local support
// hierarchy. Expanding a row reveals its direct supports — for a question, the claims that
// answer it; for a broader claim, also the claims that ladder into it (⤴). An aim is read as
// an argument, not as a support DAG, so it keeps its rhetorical groups and its outline; the
// duplication an outline costs is bounded there because the groups already place every claim
// exactly once and the nesting only reaches methods.
function renderSlices(id){
  const key = id.slice(id.indexOf(":") + 1), p = PAPERS[key];
  const box = document.getElementById("card-" + id).querySelector(".slices");
  if (!box) return;
  if (p.narr) return renderNarrative(id, p, box);        // sections, not a DAG (18-programme.js)
  // A cited neighbour used to render its own way here — one "cited here" group holding the
  // trimmed slices a programme container points at. It is a whole paper card now (preview.py
  // `_cited_neighbour`), so it renders as one: the same slice DAG the main board draws, with
  // the cited rows marked inside it. One paper, one rendering, wherever it stands.
  if (!p.aim) return renderGraph(id, key, p, box);
  const byId = {}; p.slices.forEach(s => byId[s.id] = s);
  const answeredBy = {};
  p.slices.forEach(s => (s.answers || []).forEach(r => {
    if (!r.includes(":")) (answeredBy[r] = answeredBy[r] || []).push(s.id);
  }));
  const genBy = {};                    // broader slice -> the local slices laddering into it
  p.slices.forEach(s => (s.gen || []).forEach(g => (genBy[g] = genBy[g] || []).push(s.id)));
  const dependents = new Set();
  p.slices.forEach(s => (s.up || []).forEach(u => dependents.add(u)));
  // an aim additionally shows tests as entries in their own right — a test is not
  // sub-structure of a claim, it is what the aim proposes to *do*.
  const tests = p.aim ? p.slices.filter(s => s.kind === "test") : [];
  // a laddering claim (local leads_to) sits under its broader parent, not at the top
  const entries = p.slices.filter(s =>
    (s.kind === "claim" && !dependents.has(s.id) && !(s.gen || []).length)
    || s.kind === "question");
  const questions = entries.filter(s => s.kind === "question");
  // An aim's card answers a different question from a paper's, and it must not open on all of it.
  // A paper reports what it found; an aim makes an argument, and an argument is read top-down —
  // the hypothesis, its rivals, and the experiments that separate them, with everything else
  // folded until asked for. Three rules differ from the paper branch:
  //
  //   * **every claim is placed, exactly once.** The paper rule ("a claim something depends on is
  //     sub-structure — nest it") inverts here: an aim's hypothesis is grounded in its assumptions
  //     and its payoff is grounded in the hypothesis, so the load-bearing claims are precisely the
  //     ones that rule hid. It hid c5 (the hypothesis) behind c14, and made the assumptions group
  //     unreachable outright — `lb` requires a dependent, and having a dependent removed you.
  //   * **the argument leads.** Ordered by blast radius, so the hypothesis stands above the rivals
  //     it is being tested against rather than below whichever null sorts first.
  //   * **the rest is folded** (seeded below), so the card opens on ~one screenful.
  const argued = new Set();            // claims a test separates — the argument's live front
  tests.forEach(t => (t.disc || []).forEach(c => argued.add(c)));
  const testFor = {};                  // claim -> the test(s) aimed at it, shown as a row chip
  tests.forEach(t => (t.disc || []).forEach(c => (testFor[c] = testFor[c] || []).push(t.id)));
  const allClaims = p.aim ? p.slices.filter(s => s.kind === "claim") : [];
  const placed = new Set();            // first group wins, so nothing renders twice
  const take = f => {                  // …and nothing silently vanishes: see the "everything else"
    const out = allClaims.filter(s => !placed.has(s.id) && f(s));
    out.forEach(s => placed.add(s.id));
    return out;
  };
  const argument = [...take(s => argued.has(s.id)).sort((a, b) => (b.br || 0) - (a.br || 0)), ...tests];
  const assumptions = take(s => s.lb);
  const literature = take(s => s.mod === "established");
  const rest = take(() => true);       // controls the test verifies, and what follows if it works
  const caps = p.aim ? p.slices.filter(s => s.kind === "capability") : [];
  const other = p.aim ? p.slices.filter(s =>
    !["claim", "question", "test", "capability"].includes(s.kind)) : [];
  // [label, rows, folded-by-default]
  const groups = p.aim ? [
    ["the argument", argument, false],
    ["assumptions — nothing checks these", assumptions, true],
    ["rests on the literature", literature, true],
    ["controls & consequences", rest, true],
    ["open questions", questions.filter(s => !s.answered), true],
    ["answered questions", questions.filter(s => s.answered), true],
    ["capabilities", caps, true],
    ["everything else", other, true],
  ] : [];
  const paths = new Set([...(drill.get(id) || []), ...(ctxDrill.get(id) || [])]);
  // a question's direct answers are only the *un-subsumed* ones: an answer that grounds (up) or
  // ladders (gen) into another answer of the SAME question nests under that sibling when it's
  // drilled, so listing it flat here too would render it twice (the umbrella + its supports).
  // This mirrors the top-level `dependents`/`gen` entry filter, which the answer list bypassed.
  const qKids = qid => {
    const ans = answeredBy[qid] || [], set = new Set(ans), sub = new Set();
    ans.forEach(a => {
      (byId[a].up || []).forEach(u => { if (set.has(u)) sub.add(u); });
      (genBy[a] || []).forEach(u => { if (set.has(u)) sub.add(u); });
    });
    return ans.filter(a => !sub.has(a)).map(k => ({s: byId[k], lad: false}));
  };
  // A test drills to the methods it uses. What it *separates* and what it *needs* used to nest
  // here too, which is what made one aim's 23 slices render as 47 rows — the rivals sit in the
  // same group as the test and the capabilities have their own, so nesting them re-rendered
  // claims up to five times over. Both relations ride on the row instead, as cross-references.
  const kidsOf = s => s.kind === "question"
    ? qKids(s.id)
    : s.kind === "test"
    ? (s.up || []).map(u => ({s: byId[u], lad: false})).filter(k => k.s)
    : [...(s.up || []).map(u => ({s: byId[u], lad: false})),
       ...(genBy[s.id] || []).map(u => ({s: byId[u], lad: true}))].filter(k => k.s);
  // the cross-reference lines under a test's text: what it settles, and the kit it needs (an
  // unevidenced capability shown in the risk colour — it is the reason the test reads at-risk).
  const xref = s => {
    if (s.kind !== "test") return "";
    const bits = [];
    if ((s.disc || []).length)
      bits.push(`separates ${s.disc.map(c => `<b>${c}</b>`).join(" · ")}`);
    if ((s.en || []).length)
      bits.push(`needs ${s.en.map(k => byId[k] && byId[k].asp
        ? `<b style="color:var(--risk)" title="claimed but not evidenced">${k}</b>` : `<b>${k}</b>`).join(" · ")}`);
    return bits.length ? `<span class="sep">${bits.join(" &nbsp;·&nbsp; ")}</span>` : "";
  };
  let html = "";
  const row = (s, path, depth, lad) => {
    const kids = kidsOf(s);
    const can = kids.length;                        // drillable only if it has sub-structure now
    const isOpen = can && paths.has(path);
    const ans = s.kind === "question" && s.answered ? " ans" : "";
    // a slice whose weld is a quote: no inline quote text — its PDF pops on hover / pins on click
    const pdf = (LIVE && s.quote) ? " pdf-src" : "";   // quote-bearing → hover aims the docked viewer
    html += `<div class="slice${can ? ' drillable' : ''}${pdf}${lad ? ' gen' : ''}" data-sid="${s.id}" data-path="${path}"`
          + ` style="margin-left:${depth * 14}px"${lad ? ' title="generalizes into the claim above (leads_to)"' : ''}>`
          + `<span class="car">${can ? (isOpen ? "▾" : "▸") : "·"}</span>`
          + (lad ? `<span class="gmk">⤴</span>` : ``)
          + `<span class="sid ${SID_CLASS[s.color] || 'cl'}${ans}">${s.id}</span>`
          + `<span class="stx">${rich(s.text)}${xref(s)}</span>`
          // the one thing a jury finds first: what the aim rests on with nothing under it
          + (s.lb ? `<span class="lb" title="load-bearing: ${s.br} dependent${s.br === 1 ? '' : 's'}, no test aimed at it">${s.br}✕</span>` : ``)
          // …and its mirror: the test aimed at this claim, so a rival names its own referee
          + ((testFor[s.id] || []).length
             ? `<span class="tst" title="settled by ${testFor[s.id].join(", ")}">${testFor[s.id].join(" ")}</span>` : ``)
          + `</div>`;
    if (isOpen) {
      for (const k of kids) row(k.s, `${path}/${k.s.id}`, depth + 1, k.lad);
    }
  };
  // An aim opens on its argument alone. Seeded once per card (see grpSeeded) so unfolding a group
  // sticks; a close clears the seed, so reopening lands back on the default view.
  if (p.aim && !grpSeeded.has(id)) {
    grpSeeded.add(id);
    for (const [label, ss, fold] of groups)
      if (fold && ss.length) grpCollapsed.add(`${id}::${label}`);
  }
  for (const [label, ss] of groups) {
    if (!ss.length) continue;
    const col = grpCollapsed.has(`${id}::${label}`);
    html += `<div class="sgrp" data-grp="${label}"><span class="gcar">${col ? "▸" : "▾"}</span>`
          + `${label}<span class="gct">${ss.length}</span></div>`;
    if (col) continue;                     // header only — rows stay folded away
    html += `<div class="sgrpb">`;
    ss.forEach(s => row(s, s.id, 0, false));
    html += `</div>`;
  }
  box.innerHTML = html;
}
