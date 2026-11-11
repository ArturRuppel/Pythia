// ── THE WALK ─────────────────────────────────────────────────────────────────────────────
// A second view onto the same emitted graph (docs/2026-08-03-the-walk-design.md). The board
// draws five relations at once; this walks ONE at a time as an indented tree, so there is no
// edge layer and nothing can cross. Everything you are NOT walking is a count badge that
// pivots the walk when clicked.
//
// The detached PDF window has no graph, so it gets nothing. The roster (a paper's "contents" tab)
// is the walk's answer to "did I account for every slice I wrote" — every claim, question and
// method in one paper, including the unwired ones the board never draws an edge for.
const WALK = !DETACHED ? (function(){
  const rail = document.getElementById("walkRail");
  const stage = document.getElementById("walkStage");
  const btn = document.getElementById("walkBtn");
  if (!rail || !stage || !btn) return null;

  // ── the index ──────────────────────────────────────────────────────────────────────────
  // Papers, slices, stubs and broad nodes become one flat node table; the five relations
  // become adjacency lists. Nothing is authored here that isn't already in the JSON — this is
  // a re-shaping of `grounds` / `up` / `gen` / `cons` / `answers` / `lateral`, not new data.
  let N = {}, CH = {}, KEYS = [], BROAD_IDS = [];
  const REL_KINDS = ["grounds", "builds", "gen", "answers", "corr", "contra"];

  function add(rel, a, b){
    if (!a || !b || a === b) return;
    const l = (CH[rel][a] = CH[rel][a] || []);
    if (!l.includes(b)) l.push(b);
  }
  // A ref {key,tid} → the sharpest node that actually exists. An unsharpened ref (tid null)
  // rests on the container — the CONCEPT §2 wildcard — and that is a valid endpoint, not a miss.
  function resolveRef(r){
    if (!r) return null;
    if (r.slug) return BROAD[r.slug] ? "B:" + r.slug : null;
    const sharp = r.key && r.tid ? `${r.key}:${r.tid}` : null;
    if (sharp && N[sharp]) return sharp;
    return r.key && N[r.key] ? r.key : null;
  }

  function reindex(){
    N = {}; CH = {}; KEYS = []; BROAD_IDS = [];
    REL_KINDS.forEach(k => CH[k] = {});

    const topicsOf = {};
    for (const [slug, t] of Object.entries(TOPICS))
      for (const k of t.papers || []) (topicsOf[k] = topicsOf[k] || []).push(slug);

    for (const [key, p] of Object.entries(PAPERS)) {
      // `pass` here is the VALIDATED pass — the status the viewer shows (the desk, SCHEMA §4)
      N[key] = {id: key, t: "paper", key, year: p.year, pass: p.validated || 0, cpass: curPass(p),
                vnew: deskStatus(p) === "new",
                title: p.title || "", authors: p.authors || [], type: p.type || "original",
                cur: !!p.cur, topics: topicsOf[key] || [], slices: [], wall: []};
      KEYS.push(key);
      for (const s of p.slices || []) {
        const sid = `${key}:${s.id}`;
        N[sid] = {id: sid, t: s.kind, paper: key, sid: s.id, label: s.text || "",
                  quote: s.quote || null, color: s.color || null, floor: !!s.is_floor};
        N[key].slices.push(sid);
      }
    }
    for (const [key, s] of Object.entries(STUBS))
      if (!N[key]) N[key] = {id: key, t: "stub", key, year: s.year, title: s.title || ""};
    for (const [slug, b] of Object.entries(BROAD)) {
      const id = "B:" + slug, m = b.meter || {};
      N[id] = {id, t: "broad", slug, label: b.title || b.text || slug, text: b.text || "",
               s: m.s || 0, c: m.c || 0};
      BROAD_IDS.push(id);
    }
    // The broad band has its own internal ladder: a broad claim generalises into a broader one,
    // up to the apexes the library is capped at. Without these the apex claims — the ones with no
    // paper laddering straight into them — read as empty nodes, which is the opposite of the truth.
    for (const [slug, b] of Object.entries(BROAD))
      for (const up of b.leads_to || []) {
        const from = "B:" + slug, to = "B:" + up;
        if (N[to]) { add("gen", from, to); add("builds", to, from); }
      }

    for (const [key, p] of Object.entries(PAPERS)) {
      const me = N[key];
      for (const s of p.slices || []) {
        const sid = `${key}:${s.id}`;
        // Within-paper support (build.py `_up` = grounded_in, local refs). The inverse is not
        // emitted, but it is real and it is the reading a curator wants on a floor: "what in this
        // paper rests on this measurement?" Without it a floor's `built on by` reads empty, which
        // inverts the truth — and makes the most load-bearing slice in the paper look untouched.
        for (const u of s.up || []) {
          const t = N[`${key}:${u}`] ? `${key}:${u}` : null;
          if (t) { add("grounds", sid, t); add("builds", t, sid); }
        }
        for (const g of s.gen || []) {                     // the LOCAL ladder (same paper)
          const t = N[`${key}:${g}`] ? `${key}:${g}` : null;
          if (t) { add("gen", sid, t); add("builds", t, sid); }
        }
        for (const a of s.answers || []) {
          const t = typeof a === "string" ? (N[`${key}:${a}`] ? `${key}:${a}` : null) : resolveRef(a);
          if (t) { add("answers", sid, t); add("answers", t, sid); }
        }
      }
      // cross-paper grounding. A curated target is a real step of the walk; an uncurated one
      // folds into this paper's wall, which is the citation wall staying folded by construction.
      for (const r of p.grounds || []) {
        const src = r.via ? `${key}:${r.via}` : key, tgt = resolveRef(r);
        if (!tgt) continue;
        const base = tgt.split(":")[0];
        if (PAPERS[base]) {
          add("grounds", src, tgt); add("builds", tgt, src);
          add("grounds", key, base); add("builds", base, key);
        } else {
          if (!me.wall.includes(tgt)) me.wall.push(tgt);
          add("grounds", src, tgt);
        }
      }
      // The emitted inverse of cross-paper grounding (build.py _builds). Its fields are NOT
      // shaped like `grounds`: here `key` and `via` both name the BUILDING paper (its citekey
      // and its building slice), while `tid` names the slice of *this* paper being built on.
      // Reading `via` as ours mints a cross-product id that belongs to neither paper.
      for (const r of p.builds || []) {
        const mine = r.tid && N[`${key}:${r.tid}`] ? `${key}:${r.tid}` : key;
        const theirs = r.via && N[`${r.key}:${r.via}`] ? `${r.key}:${r.via}`
                     : (N[r.key] ? r.key : null);
        if (!theirs) continue;
        add("builds", mine, theirs); add("grounds", theirs, mine);
        if (PAPERS[r.key]) { add("builds", key, r.key); add("grounds", r.key, key); }
      }
      for (const c of p.cons || []) {                      // the ladder into the broad band
        const src = c.via ? `${key}:${c.via}` : key, id = "B:" + c.slug;
        if (N[id]) { add("gen", src, id); add("builds", id, src); }
      }
      for (const l of p.lateral || []) {                   // stance — signed, and never support
        const src = l.via ? `${key}:${l.via}` : key, tgt = resolveRef(l);
        if (!tgt) continue;
        const rel = l.sign === "contra" ? "contra" : "corr";
        add(rel, src, tgt); add(rel, tgt, src);
      }
      for (const a of p.ans || []) {
        const src = a.via ? `${key}:${a.via}` : key, tgt = resolveRef(a);
        if (tgt) { add("answers", src, tgt); add("answers", tgt, src); }
      }
    }
    KEYS.sort((a, b) => (N[b].pass - N[a].pass) || ((N[b].year || 0) - (N[a].year || 0)));
  }

  // ── the tabs: containment, then the five relations ─────────────────────────────────────
  // `contents` is first and is not a relation — it is what a paper *is* (CONCEPT: a container
  // of slices). It earns its place because every other tab is a relation, and a slice that
  // participates in none of them is unreachable from its own paper at any depth. That was 22%
  // of the library's slices, concentrated in exactly the papers under active curation.
  const RELS = [
    {id: "contents", lbl: "contains", gl: "▤", cls: "",
     note: "Everything in this paper, complete and uncapped: every claim, question and method you have sliced, each with its weld quote. A roster, not a walk — so the budget does not apply and nothing folds. Slices no edge touches yet are flagged `unwired`."},
    {id: "grounds", lbl: "grounded in", gl: "⊣", cls: "",
     note: "Downward, toward evidence and older work. A paper's grounds are its curated sources; a claim's are the slices it rests on, ending at a measurement floor or an axiom."},
    {id: "builds", lbl: "built on by", gl: "⊢", cls: "",
     note: "The inverse walk — newer work, and the broader statements that rest on this."},
    {id: "gen", lbl: "generalises to", gl: "⤴", cls: "b",
     note: "The ladder: granular, quote-bound claims rolling up into the broad statements you would write in an intro."},
    {id: "answers", lbl: "answers", gl: "?", cls: "q",
     note: "Question ⇄ the claims that answer it. Bipartite, so it reads as two levels and never more."},
    {id: "stance", lbl: "stance", gl: "⚖", cls: "x",
     note: "Corroboration and contradiction. Not support — it never belongs on the support walk, so it gets its own shape: a ledger, evidence for on the left, against on the right."},
  ];
  function stanceOf(id){
    const n = N[id]; if (!n) return [];
    const both = x => (CH.corr[x] || []).concat(CH.contra[x] || []);
    if (n.t === "paper") return n.slices.flatMap(both);
    if (n.t === "broad") return (CH.builds[id] || []).flatMap(both);
    return both(id);
  }
  function childrenOf(id, rel){
    const n = N[id]; if (!n || rel === "stance") return [];
    if (rel === "contents") return n.t === "paper" ? n.slices.slice() : [];
    if (rel === "grounds" && n.t === "paper")
      return (CH.grounds[id] || []).concat(n.wall.length ? [{wall: id}] : []);
    if (rel === "gen" && n.t === "paper")
      return n.slices.filter(s => (CH.gen[s] || []).length);
    if (rel === "answers" && n.t === "paper")
      return n.slices.filter(s => N[s].t === "question" || (CH.answers[s] || []).length);
    return CH[rel][id] || [];
  }
  function relCount(id, rel){
    if (rel === "stance") return stanceOf(id).length;
    return childrenOf(id, rel).reduce((a, x) => a + (x && x.wall ? N[x.wall].wall.length : 1), 0);
  }
  // What the BOARD would spawn for the same focus. Shown in the budget readout, because the
  // whole claim of this view is a comparison and it should be checkable, not asserted.
  function boardCost(id){
    const n = N[id]; if (!n) return {cards: 0, edges: 0};
    if (n.t !== "paper") {
      const k = relCount(id, "grounds") + relCount(id, "builds") + relCount(id, "stance");
      return {cards: k, edges: k};
    }
    const gr = (CH.grounds[id] || []).length + n.wall.length;
    const bu = (CH.builds[id] || []).length;
    const gen = n.slices.reduce((a, s) => a + (CH.gen[s] || []).length, 0);
    const st = n.slices.reduce((a, s) => a + (CH.corr[s] || []).length + (CH.contra[s] || []).length, 0);
    return {cards: gr + bu + gen + st + 1, edges: gr + bu + gen + st + n.slices.length};
  }

  // ── state ──────────────────────────────────────────────────────────────────────────────
  let FOCUS = null, REL = "contents", TOPIC = null, TRAIL = [], rows = 0, KF = null;
  let MAXD = 2, CAP = 7;
  const OPEN = new Set(), UNFOLD = new Set();

  // ── labels ─────────────────────────────────────────────────────────────────────────────
  // Colour is read off the graph, never off a field (CONCEPT §3) — the same SID_CLASS the
  // board's slice rows use, so a claim is the same colour in both views.
  function glyph(n){
    if (n.t === "paper") return ["pa", n.type === "review" ? "rev" : "pap"];
    if (n.t === "stub") return ["st", "src"];
    if (n.t === "broad") return ["br", "broad"];
    if (n.t === "question") return ["q", "?"];
    return [SID_CLASS[n.color] || "cl", n.t === "method" ? (n.color === "model" ? "model" : "meas") : "claim"];
  }
  function label(n){
    if (n.t === "paper") return `<span class="k">${esc(n.key)}</span> <span class="yr">${n.year || ""}</span> · ${esc(n.title)}`;
    if (n.t === "stub") return `<span class="k">${esc(n.key)}</span> <span class="yr">${n.year || ""}</span> · ${esc(n.title || "")}`;
    if (n.t === "broad") return `<span class="lad">⤴</span> ${esc(n.label)}`;
    return `${esc(n.label)} <span class="yr">${esc(N[n.paper].key)}:${esc(n.sid)}</span>`;
  }
  const shortOf = path => {
    const n = N[path.split("/").pop()];
    return !n ? "root" : n.t === "paper" || n.t === "stub" ? n.key
         : n.t === "broad" ? n.label : `${N[n.paper].key}:${n.sid}`;
  };
  const aimable = n => LIVE && n && n.quote && n.paper;   // a quote row can drive the PDF dock

  // ── render ─────────────────────────────────────────────────────────────────────────────
  function drawRail(){
    const list = KEYS.filter(k => !TOPIC || N[k].topics.includes(TOPIC));
    const tsorted = Object.entries(TOPICS).sort((a, b) => a[1].title.localeCompare(b[1].title));
    rail.innerHTML =
      `<div class="wr-hd">topics · ${tsorted.length}</div>` +
      tsorted.map(([slug, t]) => {
        const n = (t.papers || []).filter(k => PAPERS[k]).length;
        return `<div class="wr-t${TOPIC === slug ? " on" : ""}" data-topic="${esc(slug)}">${
          esc(t.title)}<span class="n">${n}</span></div>`;
      }).join("") +
      `<div class="wr-hd">library · ${list.length} curated${TOPIC ? " in topic" : ""}</div>` +
      list.map(k => {
        const c = boardCost(k).cards;
        return `<div class="wr-row${FOCUS === k ? " on" : ""}${c > 30 ? " hot" : ""}" data-key="${esc(k)}">
          ${PAPERS[k] && PAPERS[k].cur ? vstat(PAPERS[k]) : passCircle(0)}<span class="k">${esc(k)}</span><span class="n">${c}</span></div>`;
      }).join("") +
      `<div class="wr-hd">broad · ${BROAD_IDS.length}</div>` +
      BROAD_IDS.slice().sort((a, b) => N[a].label.localeCompare(N[b].label))
        .map(id => `<div class="wr-t" data-node="${esc(id)}">${esc(N[id].label)}</div>`).join("");
  }

  function headerHtml(n){
    if (n.t === "paper") {
      const au = n.authors.length ? shortAuthLine(n.authors) : "";
      return `<div class="wk-focus"><div class="fk">
        <span class="kind">${esc(n.type)}</span><span class="key">${esc(n.key)}</span>
        <span class="yr">${n.year || ""} · ${n.vnew ? "new" : `validated ${n.pass}/4`}${n.cpass > n.pass || n.vnew ? ` · curated ${n.cpass}` : ""} · ${n.slices.length} slices · ${n.wall.length} sources</span>
        </div><div class="ttl">${esc(n.title)}</div>${au ? `<div class="auth">${au}</div>` : ""}</div>`;
    }
    if (n.t === "broad")
      return `<div class="wk-focus b"><div class="fk"><span class="kind">broad</span>
        <span class="key">${esc(n.label)}</span>
        <span class="yr">${n.s} support · ${n.c} contra</span></div>
        <div class="txt">${esc(n.text)}</div></div>`;
    if (n.t === "stub")
      return `<div class="wk-focus"><div class="fk"><span class="kind">uncurated source</span>
        <span class="key">${esc(n.key)}</span><span class="yr">${n.year || ""}</span></div>
        <div class="ttl">${esc(n.title || "")}</div></div>`;
    const p = N[n.paper];
    return `<div class="wk-focus ${n.t === "question" ? "q" : ""}"><div class="fk">
      <span class="kind">${esc(n.t)}</span>
      <span class="key">${esc(p.key)}:${esc(n.sid)}</span><span class="yr">${p.year || ""}</span></div>
      <div class="txt">${esc(n.label)}</div>
      ${n.quote ? `<div class="quote${aimable(n) ? " wk-q aims" : ""}"${
        aimable(n) ? ` data-aim="${esc(n.paper)}" data-sid="${esc(n.sid)}"` : ""}>${esc(n.quote)}</div>` : ""}</div>`;
  }

  function tabsHtml(id){
    const r = RELS.find(x => x.id === REL);
    return `<div id="walkTabs">` + RELS.map(x => {
      const c = relCount(id, x.id);
      return `<div class="wk-tab ${x.cls}${REL === x.id ? " on" : ""}${c ? "" : " off"}" data-rel="${x.id}">
        <span>${x.gl}</span><span>${esc(x.lbl)}</span><span class="ct">${c}</span></div>`;
    }).join("") + `<span id="walkBudget">` +
      // the budget bounds a walk; the roster and the ledger are not walks, so it would lie
      (REL === "contents" || REL === "stance" ? "" :
        `<span>depth <input type="range" id="wkDepth" min="1" max="6" value="${MAXD}">${MAXD}</span>
         <span>siblings <input type="range" id="wkCap" min="3" max="30" value="${CAP}">${CAP}</span>`) +
      `<span class="cost"></span></span></div>
      <p class="wk-note">${esc(r.note)}</p>`;
  }

  const badges = (id, skip) => `<span class="wk-bg">` + RELS.filter(r => r.id !== skip).map(r => {
    const c = relCount(id, r.id);
    return `<span class="wk-b${c ? "" : " z"}" data-piv="${esc(id)}" data-pr="${r.id}"
      title="${esc(r.lbl)}: ${c} — click to pivot the walk here">${r.gl}${c}</span>`;
  }).join("") + `</span>`;

  const guides = (depth, flags) => {
    let g = "";
    for (let d = 0; d < depth; d++) g += `<span class="wk-g${flags[d] ? "" : " v"}"></span>`;
    return g;
  };
  function rowHtml(id, depth, flags, path, kids, isLast, extra){
    const n = N[id], [g, gl] = glyph(n);
    const lead = depth > 0 ? guides(depth - 1, flags) + `<span class="wk-g e${isLast ? "" : " mid"}"></span>` : "";
    return `<div class="wk-row ${extra || ""}" data-path="${esc(path)}" data-id="${esc(id)}">
      ${lead}<span class="wk-tw">${kids > 0 ? (OPEN.has(path) ? "▾" : "▸") : "·"}</span>
      <span class="sid ${g}">${gl}</span>
      <span class="wk-lb">${label(n)}</span>${badges(id, REL)}</div>`;
  }

  function treeHtml(root){
    const out = [], seen = new Map();
    rows = 0; seen.set(root, "·");
    (function rec(id, depth, flags, path){
      const kids = childrenOf(id, REL);
      if (!kids.length) return;
      const chipKey = path + "/…";
      let shown = kids, hidden = 0;
      if (kids.length > CAP && !UNFOLD.has(chipKey)) { shown = kids.slice(0, CAP); hidden = kids.length - CAP; }
      shown.forEach((k, i) => {
        const isLast = (i === shown.length - 1) && !hidden;
        if (k && k.wall) {                                   // the citation wall, folded
          const w = N[k.wall].wall, wk = path + "/wall", un = UNFOLD.has(wk);
          out.push(`<div class="wk-chiprow">${guides(depth, flags)}<span class="wk-g e${isLast ? "" : " mid"}"></span>
            <span class="wk-chip" data-unfold="${esc(wk)}">${un ? "▾" : "▸"} <b>${w.length}</b> uncurated sources</span></div>`);
          rows++;
          if (un) {
            const lim = Math.min(CAP, w.length);
            w.slice(0, lim).forEach((s, j) =>
              { out.push(rowHtml(s, depth + 2, flags.concat([isLast, false]), wk + "/" + s, 0, j === lim - 1, "dimmed")); rows++; });
            if (w.length > lim) {
              out.push(`<div class="wk-chiprow">${guides(depth + 1, flags.concat([isLast]))}
                <span class="wk-chip">… <b>${w.length - lim}</b> more, not shown</span></div>`);
              rows++;
            }
          }
          return;
        }
        const p2 = path + "/" + k;
        if (seen.has(k)) {                                   // the DAG becomes a tree by repetition
          out.push(rowHtml(k, depth + 1, flags, p2, 0, isLast, "rep").replace(/<\/div>$/,
            `<span class="wk-also" data-goto="${esc(seen.get(k))}">↩ also under ${esc(shortOf(seen.get(k)))}</span></div>`));
          rows++; return;
        }
        seen.set(k, p2);
        const kc = childrenOf(k, REL).length;
        if (depth + 1 < MAXD && kc && !OPEN.has(p2) && !OPEN.has("!" + p2)) OPEN.add(p2);
        out.push(rowHtml(k, depth + 1, flags, p2, kc, isLast)); rows++;
        const nq = N[k];
        if (nq.quote && OPEN.has(p2) && !kc) {
          out.push(`<div class="wk-chiprow">${guides(depth + 2, flags.concat([isLast, false]))}
            <span class="wk-q${aimable(nq) ? " aims" : ""}"${aimable(nq)
              ? ` data-aim="${esc(nq.paper)}" data-sid="${esc(nq.sid)}"` : ""}>${esc(nq.quote)}</span></div>`);
          rows++;
        }
        if (OPEN.has(p2)) rec(k, depth + 1, flags.concat([isLast]), p2);
      });
      if (hidden) {
        out.push(`<div class="wk-chiprow">${guides(depth, flags)}<span class="wk-g e"></span>
          <span class="wk-chip" data-unfold="${esc(chipKey)}">▸ <b>${hidden}</b> more</span></div>`);
        rows++;
      }
    })(root, 0, [], "·");
    return out.length ? out.join("") : `<p class="wk-empty">Nothing along this relation — try another tab.</p>`;
  }

  // ── the roster ─────────────────────────────────────────────────────────────────────────
  // The manifest of a paper. Deliberately uncapped and unfolded: the budget exists to stop a
  // walk exploding, and this is not a walk — you cannot sift thoroughly through something the
  // view is allowed to elide. Filters narrow it; nothing hides it.
  const KINDS = [["claim", "claims"], ["question", "questions"], ["method", "methods"]];
  const unwired = id => !RELS.some(r => r.id !== "contents" && relCount(id, r.id));
  function rosterHtml(id){
    const n = N[id], all = n.slices;
    rows = all.length;
    if (!all.length)
      return `<p class="wk-empty">Registered, but not sliced yet — nothing to sift through.</p>`;
    const un = all.filter(unwired);
    const bar = `<div class="rs-bar"><span class="rs-f${KF ? "" : " on"}" data-kf="">all<b>${all.length}</b></span>` +
      KINDS.map(([k, lbl]) => {
        const c = all.filter(s => N[s].t === k).length;
        return c ? `<span class="rs-f${KF === k ? " on" : ""}" data-kf="${k}">${lbl}<b>${c}</b></span>` : "";
      }).join("") +
      (un.length ? `<span class="rs-f w${KF === "!" ? " on" : ""}" data-kf="!"
        title="sliced, but no edge touches it yet — nothing else in this view can reach these">unwired<b>${un.length}</b></span>` : "") +
      `</div>`;
    const pick = KF === "!" ? un : KF ? all.filter(s => N[s].t === KF) : all;
    rows = pick.length;
    let out = "";
    for (const [k, lbl] of KINDS) {
      const g = pick.filter(s => N[s].t === k);
      if (!g.length) continue;
      out += `<div class="rs-sec">${lbl}<span>${g.length}</span></div>` + g.map(s => {
        const x = N[s], [cls, gl] = glyph(x), u = unwired(s);
        return `<div class="wk-ent rs${x.t === "question" ? " q" : ""}${u ? " un" : ""}" data-id="${esc(s)}">
          <span class="sid ${cls}">${gl}</span><div class="bd">
          <div class="src">${esc(n.key)}:${esc(x.sid)}${
            x.floor ? `<span class="rs-tag fl">measurement floor</span>` : ""}${
            u ? `<span class="rs-tag un">unwired</span>` : ""}</div>
          <div class="t">${esc(x.label)}</div>${
          x.quote ? `<div class="qt${aimable(x) ? " aims" : ""}"${aimable(x)
            ? ` data-aim="${esc(x.paper)}" data-sid="${esc(x.sid)}"` : ""}>${esc(x.quote)}</div>` : ""}
          </div>${badges(s, "contents")}</div>`;
      }).join("");
    }
    return bar + (out ? `<div id="walkRoster">${out}</div>`
                      : `<p class="rs-none">Nothing in this filter.</p>`);
  }

  function ledgerHtml(id){
    const side = (rel, cls, ttl) => {
      const n = N[id];
      const src = n.t === "paper" ? n.slices.flatMap(s => CH[rel][s] || [])
                : n.t === "broad" ? (CH.builds[id] || []).flatMap(s => CH[rel][s] || [])
                : (CH[rel][id] || []);
      return `<div><div class="lhd ${cls}">${ttl}<span>${src.length}</span></div>` +
        (src.length ? src.map(s => {
          const x = N[s]; if (!x) return "";
          // an endpoint may rest on the container — the unsharpened wildcard (CONCEPT §2)
          const sl = !!x.paper, p = sl ? N[x.paper] : x;
          const head = sl ? `${esc(p.key)}:${esc(x.sid)} <span class="yr">${p.year || ""}</span>`
            : `${esc(p.key || p.label || s)} <span class="yr">${p.year || ""}</span><span class="wild">▸ not yet sliced</span>`;
          return `<div class="wk-ent ${cls}" data-id="${esc(s)}">
            <div class="src">${head}</div><div class="t">${esc(sl ? x.label : (x.title || x.text || ""))}</div>
            ${x.quote ? `<div class="qt">${esc(x.quote)}</div>` : ""}</div>`;
        }).join("") : `<div class="wk-empty">none recorded</div>`) + `</div>`;
    };
    rows = stanceOf(id).length;
    return `<div id="walkLedger">${side("corr", "p", "corroborates")}${side("contra", "m", "contradicts")}</div>`;
  }

  const landing = () => `<div class="wk-land"><h2>One focus. One relation. No drawn edges.</h2>
    <p>The board draws five relations at once — grounds, within-paper support, the ladder,
    answers and stance — as strokes on one canvas. Each has a different natural shape, so
    superimposed none of them is readable. This walks <b>one</b> at a time as an indented tree,
    so there is nothing to cross.</p>
    <div class="pt"><b>Every relation you are not walking is a badge, not a line.</b>
    Clicking one doesn't draw anything — it pivots the walk, with that node as the new focus.</div>
    <div class="pt"><b>Stance gets a ledger, not an arrow.</b> "What contradicts this" is a
    different question from "what grounds this".</div>
    <div class="pt"><b>The mess is structurally impossible.</b> Depth and sibling budgets cap
    what can render; the citation wall folds by construction, never by clean-up.</div>
    <p style="margin-top:18px;color:var(--faint)">Pick a paper on the left — the number beside it
    is what the board would spawn for it. The <span style="color:var(--cross)">red</span> ones are
    the ones the board cannot survive.</p></div>`;

  function paint(){
    drawRail();
    if (!FOCUS || !N[FOCUS]) { stage.innerHTML = landing(); return; }
    const n = N[FOCUS];
    stage.innerHTML = crumbs() + headerHtml(n) + tabsHtml(FOCUS) +
      (REL === "stance" ? ledgerHtml(FOCUS)
       : REL === "contents" && n.t === "paper" ? rosterHtml(FOCUS)
       : `<div id="walkTree">${treeHtml(FOCUS)}</div>`);
    const c = boardCost(FOCUS), cost = stage.querySelector("#walkBudget .cost");
    if (cost) cost.innerHTML = `walk <b>${rows} rows · 0 edges</b> · board would draw
      <span class="${c.cards > 28 ? "bad" : ""}">${c.cards} cards · ${c.edges} edges</span>`;
  }
  const crumbs = () => `<div id="walkCrumbs">` +
    TRAIL.filter(Boolean).slice(-5).map(x => `<a data-back="${esc(x)}">${esc(shortOf("·/" + x))}</a><span class="sep">›</span>`).join("") +
    `<a data-back="">library</a></div>`;

  function setFocus(id, rel){
    if (!N[id]) return;
    if (FOCUS !== id) { if (FOCUS) TRAIL.push(FOCUS); OPEN.clear(); UNFOLD.clear(); KF = null; }
    FOCUS = id;
    if (rel) REL = rel;
    if (!relCount(FOCUS, REL)) {                    // never land on an empty tab
      const r = RELS.find(x => relCount(FOCUS, x.id));
      if (r) REL = r.id;
    }
    paint(); stage.scrollTop = 0;
  }

  // ── events ─────────────────────────────────────────────────────────────────────────────
  rail.addEventListener("click", e => {
    const t = e.target.closest("[data-topic]"), k = e.target.closest("[data-key]"),
          b = e.target.closest("[data-node]");
    if (t) { TOPIC = TOPIC === t.dataset.topic ? null : t.dataset.topic; drawRail(); return; }
    if (k) setFocus(k.dataset.key, "contents");     // a paper opens on its own contents — the
    if (b) setFocus(b.dataset.node, "builds");      // roster is where curation starts
  });
  stage.addEventListener("click", e => {
    const aim = e.target.closest("[data-aim]");
    if (aim) {
      // Same path a slice row on the board takes: aim the docked PDF pane at this quote.
      if (LIVE) { if (!pdfActive()) openDock(); aimDock(aim.dataset.aim, aim.dataset.sid); }
      return;
    }
    const tab = e.target.closest("[data-rel]");
    if (tab && !tab.classList.contains("off")) { REL = tab.dataset.rel; OPEN.clear(); UNFOLD.clear(); KF = null; paint(); return; }
    const kf = e.target.closest("[data-kf]");
    if (kf) { KF = kf.dataset.kf || null; paint(); return; }
    const piv = e.target.closest("[data-piv]");
    if (piv) { setFocus(piv.dataset.piv, piv.dataset.pr); return; }
    const back = e.target.closest("[data-back]");
    if (back) {
      const v = back.dataset.back;
      TRAIL = [];
      if (!v) { FOCUS = null; OPEN.clear(); UNFOLD.clear(); paint(); } else setFocus(v);
      return;
    }
    const un = e.target.closest("[data-unfold]");
    if (un) { const k = un.dataset.unfold; UNFOLD.has(k) ? UNFOLD.delete(k) : UNFOLD.add(k); paint(); return; }
    const go = e.target.closest("[data-goto]");
    if (go) {
      const el = stage.querySelector(`[data-path="${CSS.escape(go.dataset.goto)}"]`);
      if (el) { el.scrollIntoView({block: "center"}); el.classList.remove("wk-flash"); void el.offsetWidth; el.classList.add("wk-flash"); }
      return;
    }
    const ent = e.target.closest(".wk-ent");
    // a ledger entry is an argument about grounding; a roster entry is just a slice, so let
    // setFocus pick its first non-empty tab rather than dumping it on an empty `grounds`
    if (ent) { setFocus(ent.dataset.id, ent.classList.contains("rs") ? undefined : "grounds"); return; }
    const row = e.target.closest(".wk-row");
    if (row && !row.classList.contains("rep")) {
      if (e.detail === 2 || e.shiftKey) { setFocus(row.dataset.id); return; }
      const p = row.dataset.path;
      if (OPEN.has(p)) { OPEN.delete(p); OPEN.add("!" + p); } else { OPEN.add(p); OPEN.delete("!" + p); }
      paint();
    }
  });
  stage.addEventListener("input", e => {
    if (e.target.id === "wkDepth") { MAXD = +e.target.value; OPEN.clear(); }
    else if (e.target.id === "wkCap") CAP = +e.target.value;
    else return;
    paint();
  });

  // ── the toggle ─────────────────────────────────────────────────────────────────────────
  // One or the other, never both: the walk hides the board the same way the library does.
  const isOpen = () => document.body.classList.contains("walk");
  function show(on){
    if (on === isOpen()) return;
    document.body.classList.toggle("walk", on);
    btn.classList.toggle("on", on);
    btn.textContent = on ? "← board" : "walk";
    if (on) {
      if (!KEYS.length) reindex();
      // arriving from the board with a paper open lands on that paper, not on the splash
      if (!FOCUS && typeof focusedKey === "function") {
        const k = focusedKey();
        if (k && N[k]) { FOCUS = k; REL = relCount(k, "contents") ? "contents" : "gen"; KF = null; }
      }
      paint();
    } else redraw();     // the board was display:none; its edge overlay needs re-anchoring
  }
  btn.hidden = false;
  btn.addEventListener("click", () => show(!isOpen()));
  // One full-pane view at a time, in BOTH directions. The library owns its own button, so the
  // only way to be sure the walk yields to it is to step aside before its handler runs.
  const libBtnEl = document.getElementById("libBtn");
  if (libBtnEl) libBtnEl.addEventListener("click", () => { if (isOpen()) show(false); }, true);
  addEventListener("keydown", e => {
    if (e.key === "Escape" && isOpen()) { show(false); return; }
    if (e.key !== "w" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName || "") || e.target.isContentEditable) return;
    if (document.body.classList.contains("library")) return;
    show(!isOpen());
  });

  reindex();
  return {reindex, show, paint, isOpen,
          get focus(){return FOCUS}, get rel(){return REL}, get rows(){return rows},
          get nodes(){return N}, get ch(){return CH}, get rels(){return RELS},
          setFocus, boardCost, relCount, childrenOf, treeHtml, ledgerHtml, rosterHtml, unwired,
          headerHtml, tabsHtml,
          get keys(){return KEYS}, get broadIds(){return BROAD_IDS}};
})() : null;
window.litWalk = WALK;      // the seam gotoPaper reaches through (see its TDZ note)

