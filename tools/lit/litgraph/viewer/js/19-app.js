// ── the Pythia app: the touch reading view (iPhone + iPad) ──────────────────────────────────
// A second face on the same GRAPH (Claude Design "Logo mark refinement round 2", the tab-bar
// variant). Read-only, and nothing on the board is shared with it but the data: four tabs
// (Library · Topics · Reading · Search), each tab its own push stack of screens (a paper, a
// slice, a broad node, a stub, a stance ledger). The board stays one tap away — the Board
// button here, the "app" button on the HUD — and the choice sticks (localStorage).
//
// When it shows: `?view=app` / `?view=board` force it; otherwise the last choice made on this
// device; otherwise a touch screen (iPhone, iPad) or a phone-width window gets the app and
// everything else the board. Styles: css/12-app.css. Everything lives in this one closure,
// because the board's scope already owns short names (`open`, `route`, …).
(function(){
  if (DETACHED) return;                      // a popped-out PDF window is never the app
  const TOUCH = matchMedia("(hover:none) and (pointer:coarse)").matches
             || matchMedia("(max-width:640px)").matches;
  const store = {
    get(k){ try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v){ try { localStorage.setItem(k, v); } catch {} },
  };

  // ── text ──
  // Slice text is prose that quotes maths (`<Du>`, `<sigma_xx>`) and titles that carry a few
  // real tags (`<i>RAS</i>`) or entities (`&amp;`). Escape everything, then let the handful of
  // inline formatting tags back through, and leave an entity that is already an entity alone.
  const tx = s => String(s == null ? "" : s)
    .replace(/&(?!#?\w+;)/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/&lt;(\/?)(i|b|em|strong|sub|sup)&gt;/g, "<$1$2>");
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const person = n => { const i = n.indexOf(", "); return i < 0 ? n : `${n.slice(i + 2)} ${n.slice(0, i)}`; };
  function authors(a, max = 8){
    if (!a || !a.length) return "";
    const names = a.map(x => person(x[0]));
    return names.length > max ? names.slice(0, max - 1).join(", ") + ", … " + names[names.length - 1]
                              : names.join(", ");
  }
  const PASS = ["Uncurated", "Bibliography", "Skeleton", "Contextualized", "Curated"];
  const pm = (p, lg) => `<span class="pa-pm${lg ? " lg" : ""}">`
    + [1, 2, 3, 4].map(i => `<i class="${i <= (p || 0) ? "on" : ""}"></i>`).join("") + `</span>`;
  const CHEV = `<svg class="pa-chev" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>`;
  const MARK = `<svg viewBox="0 0 48 48"><g fill="#f3f3f4"><rect x="11" y="29" width="26" height="3"/>`
    + `<rect x="8" y="10" width="32" height="7"/><path d="M12 17h5l-6 23H6zM31 17h5l6 23h-5z"/>`
    + `<rect x="22" y="17" width="4" height="23"/></g></svg>`;
  const KIND = { claim: "Claim", question: "Question", method: "Method" };

  // ── the graph, as nodes and edges ──
  // A node is {t:'slice',pk,id} | {t:'paper',key} | {t:'stub',key} | {t:'broad',slug}. The
  // payload spreads a slice's edges over several shapes (up/gen/answers on the slice, grounds/
  // cons/lateral on the paper); they are folded here into one list with the prototype's five
  // relations: g grounded_in · l leads_to · co corroborates · ct contradicts · a answers.
  const PK = Object.keys(PAPERS).filter(k => !PAPERS[k].aim && !PAPERS[k].narr);
  const SK = Object.keys(STUBS);
  const SL = {};                              // pk -> id -> slice
  for (const k of PK) { SL[k] = {}; for (const s of PAPERS[k].slices) SL[k][s.id] = s; }
  const sl = n => SL[n.pk][n.id];
  const nk = n => n.t === "slice" ? `${n.pk}:${n.id}` : n.t === "broad" ? `@${n.slug}` : n.key;
  const bkind = slug => BROAD[slug].kind.replace(/^broad /, "");
  function ref(key, tid){
    if (SL[key]) return tid && SL[key][tid] ? { t: "slice", pk: key, id: tid } : { t: "paper", key };
    return { t: "stub", key };
  }
  function raw(pk, r){
    if (BROAD[r]) return { t: "broad", slug: r };
    if (r.includes(":")) { const [k, id] = r.split(":"); return ref(k, id); }
    if (SL[pk][r]) return { t: "slice", pk, id: r };
    return ref(r, null);
  }
  const OUT = new Map(), IN = new Map();      // nk -> rel -> Map(nk -> node)
  function edge(from, rel, to){
    for (const [idx, a, b] of [[OUT, from, to], [IN, to, from]]) {
      let m = idx.get(nk(a)); if (!m) idx.set(nk(a), m = {});
      (m[rel] = m[rel] || new Map()).set(nk(b), b);
    }
  }
  for (const pk of PK) {
    const p = PAPERS[pk], at = id => ({ t: "slice", pk, id });
    for (const s of p.slices) {
      (s.up || []).forEach(r => SL[pk][r] && edge(at(s.id), "g", at(r)));
      (s.gen || []).forEach(r => SL[pk][r] && edge(at(s.id), "l", at(r)));
      (s.answers || []).forEach(r => edge(at(s.id), "a", raw(pk, r)));
    }
    (p.grounds || []).forEach(e => edge(at(e.via), "g", ref(e.key, e.tid)));
    (p.cons || []).forEach(e => BROAD[e.slug] && edge(at(e.via), "l", { t: "broad", slug: e.slug }));
    (p.lateral || []).forEach(e => edge(at(e.via), e.sign === "contra" ? "ct" : "co",
      e.slug ? (BROAD[e.slug] ? { t: "broad", slug: e.slug } : raw(pk, e.slug)) : ref(e.key, e.tid)));
  }
  for (const slug in BROAD) (BROAD[slug].leads_to || [])
    .forEach(r => BROAD[r] && edge({ t: "broad", slug }, "l", { t: "broad", slug: r }));
  const outs = (n, rel) => [...((OUT.get(nk(n)) || {})[rel] || new Map()).values()];
  const ins = (n, rel) => [...((IN.get(nk(n)) || {})[rel] || new Map()).values()];
  const insAll = n => { const m = IN.get(nk(n)) || {}; return Object.entries(m).flatMap(([rel, v]) => [...v.values()].map(from => ({ from, rel }))); };
  const cont = n => n.t === "slice" ? n.pk : n.key;
  const cites = {};                           // stub key -> incoming edges (the frontier's rank)
  for (const k of SK) cites[k] = insAll({ t: "stub", key: k }).length;
  const answered = n => ins(n, "a").length > 0 || (n.t === "slice" && !!sl(n).answered);

  function lab(n){
    if (n.t === "slice") { const s = sl(n); return { kicker: `${n.pk} · ${n.id}`, text: s.text, quote: s.qd || s.quote }; }
    if (n.t === "paper") { const p = PAPERS[n.key]; return { kicker: `${n.key}${p.year ? " · " + p.year : ""}`, text: p.title || n.key }; }
    if (n.t === "stub") { const s = STUBS[n.key] || {}; return { kicker: [n.key, s.year, "stub"].filter(Boolean).join(" · "), text: s.title || n.key, wild: true }; }
    const b = BROAD[n.slug]; return { kicker: `Broad ${bkind(n.slug)}`, text: b.text || b.title || n.slug };
  }
  // A claim's stance: what corroborates it or it corroborates (support is symmetric here), what
  // contradicts it — and for a broad claim, every slice that generalizes into it. That is the
  // same count build.broad_meter makes, so a bar here agrees with the board's meter.
  function stance(n){
    const sup = [], con = [];
    if (n.t === "broad") ins(n, "l").filter(x => x.t === "slice").forEach(x => sup.push({ n: x, rel: "leads here" }));
    outs(n, "co").concat(ins(n, "co")).forEach(x => sup.push({ n: x, rel: "corroborates" }));
    outs(n, "ct").concat(ins(n, "ct")).forEach(x => con.push({ n: x, rel: "contradicts" }));
    return { sup, con };
  }

  // ── topics ──
  const TK = Object.keys(TOPICS);
  const tRoots = TK.filter(k => TOPICS[k].root);
  const tLeaves = TK.filter(k => !TOPICS[k].root);
  const tKids = k => TK.filter(c => (TOPICS[c].broader || []).includes(k));
  const tIn = {}; for (const k of TK) tIn[k] = new Set(TOPICS[k].papers || []);

  // ── state ──
  const TABS = ["library", "topics", "reading", "search"];
  const S = {
    tab: "library", stacks: { library: [], topics: [], reading: [], search: [] },
    scope: "curated", sort: "new", kind: "all", absOpen: false, sheet: false,
    q: "", more: {}, pos: {},
  };
  const cur = () => { const st = S.stacks[S.tab]; return st[st.length - 1] || null; };
  let recent = []; try { recent = JSON.parse(store.get("pythia.recent") || "[]"); } catch {}

  const app = document.createElement("div");
  app.id = "app";
  document.body.appendChild(app);
  let acts = {}, aid = 0;                    // tap handlers by id; a full render starts afresh
  const act = fn => { acts[++aid] = fn; return `data-a="${aid}"`; };
  app.addEventListener("click", e => {
    const b = e.target.closest("[data-a]");
    if (!b || !app.contains(b)) return;
    const fn = acts[b.dataset.a];
    if (fn) { if (b.tagName !== "A") e.preventDefault(); fn(e); }
  });

  // ── navigation ──
  // Every push is a history entry, so iOS's edge swipe and the browser's back button walk the
  // stack like the on-screen back does. A tab switch is not an entry (tab bars never are).
  const posKey = () => `${S.tab}/${S.stacks[S.tab].length}`;
  const scroller = () => app.querySelector(".pa-scroll");
  const keepPos = () => { const sc = scroller(); if (sc) S.pos[posKey()] = sc.scrollTop; };
  function push(r){
    keepPos();
    if (S.q.trim()) remember(S.q.trim());
    S.stacks[S.tab].push(r); S.kind = "all"; S.absOpen = false;
    history.pushState({ pythia: true }, "");
    render(0);
  }
  function pop(){
    if (!S.stacks[S.tab].length) return;
    S.stacks[S.tab].pop(); S.kind = "all";
    render(S.pos[posKey()] || 0);
  }
  addEventListener("popstate", () => { if (document.body.classList.contains("app")) pop(); });
  function tabTo(t){
    keepPos();
    if (S.tab === t) { S.stacks[t] = []; render(0); return; }   // re-tap: back to the tab's root
    S.tab = t; render(S.pos[posKey()] || 0);
    if (t === "search" && !cur()) { const i = app.querySelector(".pa-search input"); if (i) i.focus(); }
  }
  function remember(q){
    recent = [q, ...recent.filter(x => x !== q)].slice(0, 6);
    store.set("pythia.recent", JSON.stringify(recent));
  }
  const route = n => n.t === "slice" ? { t: "slice", pk: n.pk, id: n.id } : n.t === "paper" ? { t: "paper", key: n.key }
    : n.t === "stub" ? { t: "stub", key: n.key } : { t: "broad", slug: n.slug };
  function titleOf(r){
    if (!r) return { library: "Library", topics: "Topics", reading: "Reading", search: "Search" }[S.tab];
    if (r.t === "paper" || r.t === "stub") return r.key;
    if (r.t === "slice") return `${r.pk} · ${r.id}`;
    if (r.t === "ledger") return "Stance";
    return "Broad " + bkind(r.slug);
  }
  function kickOf(r){
    return r.t === "paper" ? "Paper" : r.t === "stub" ? "Stub" : r.t === "ledger" ? "Stance"
      : r.t === "broad" ? "Broad" : KIND[sl(r).kind] || sl(r).kind;
  }

  // ── pieces ──
  const item = (n, extra) => { const L = lab(n);
    return `<button class="pa-item" ${act(() => push(route(n)))}><span><span class="pa-ik">${tx(extra ? `${L.kicker} · ${extra}` : L.kicker)}</span>`
         + `<span class="pa-it">${tx(L.text)}</span></span>${CHEV}</button>`; };
  const sec = (title, n, cls) => `<div class="pa-sec${cls ? " " + cls : ""}"><b>${tx(title)}</b>${n != null && n !== "" ? `<span>${tx(n)}</span>` : ""}</div>`;
  // a long list shows `step` at a time; "more" is keyed so it survives a re-render
  function paged(id, list, step, fn){
    const n = S.more[id] || step;
    let h = list.slice(0, n).map(fn).join("");
    if (list.length > n) h += `<button class="pa-more" ${act(() => { S.more[id] = n + step; render(scroller().scrollTop); })}>`
      + `Show ${Math.min(step, list.length - n)} more · ${list.length - n} left</button>`;
    return h;
  }
  function paperRow(k, meta){
    const p = PAPERS[k];
    const c = kd => p.slices.filter(s => s.kind === kd).length;
    return `<button class="pa-row" ${act(() => push({ t: "paper", key: k }))}><span class="pa-rtop">`
      + `<span class="pa-key">${tx(k)}</span><span class="pa-yr">${p.year || ""}</span>${pm(p.pass)}</span>`
      + `<span class="pa-rtitle">${tx(p.title || k)}</span>`
      + `<span class="pa-meta">${tx(meta || `${plural(c("claim"), "claim")} · ${plural(c("question"), "question")} · ${plural(c("method"), "method")}`)}</span></button>`;
  }
  function stubRow(k){
    const s = STUBS[k] || {}, n = cites[k] || 0;
    return `<button class="pa-row" ${act(() => push({ t: "stub", key: k }))}><span class="pa-rtop">`
      + `<span class="pa-key">${tx(k)}</span><span class="pa-yr">${s.year || ""}</span><span class="pa-stub">Stub</span>${pm(0)}</span>`
      + `<span class="pa-rtitle dim">${tx(s.title || k)}</span>`
      + `<span class="pa-meta">${n ? `Cited by ${plural(n, "slice")}` : "Not referenced yet"}</span></button>`;
  }
  const bar = (s, c, lg) => `<span class="pa-bar${lg ? " lg" : ""}"><span class="s" style="flex:${s}"></span><span class="c" style="flex:${c}"></span></span>`
    + `<span class="pa-bartx${lg ? " lg" : ""}"><span class="s">${s} supporting</span><span class="c">${c} contradicting</span></span>`;

  // ── the library ──
  // One index row per paper, curated or stub, with the two axes a bibliography can't group on
  // as stored: authors fold to `family|first-initial` (curated YAML writes "Family, Given",
  // OpenAlex "Given M. Family"), and journals ride the citekey's venue token (a curated paper
  // stores no journal; a stub's full name is only a label for its token). Same rules as the
  // board's library rail (14-search.js), so the two agree on who and where.
  const PARTICLES = new Set(["van", "von", "de", "der", "den", "du", "del", "della", "di", "da", "dos", "la", "le", "ter", "ten"]);
  const fold = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  function authorId(raw){
    const s = String(raw || "").replace(/[‐-―]/g, "-").replace(/\s+/g, " ").trim();
    if (!s) return null;
    let family, given;
    const c = s.indexOf(",");
    if (c > -1) { family = s.slice(0, c).trim(); given = s.slice(c + 1).trim(); }
    else {
      const w = s.split(" "); let i = w.length - 1;
      while (i > 1 && PARTICLES.has(fold(w[i - 1]).replace(/\.$/, ""))) i--;
      family = w.slice(i).join(" "); given = w.slice(0, i).join(" ");
    }
    if (!family) return null;
    const ini = (given.match(/[A-Za-zÀ-ɏ]/) || [""])[0].toUpperCase();
    return { id: fold(family) + "|" + fold(ini), name: family + (ini ? ", " + ini + "." : "") };
  }
  let IDX = null;
  const AUTH = {}, VENUE = {};                 // id → display name
  function index(){
    if (IDX) return IDX;
    const vt = {};
    const row = (k, stub) => {
      const p = (stub ? STUBS : PAPERS)[k] || {}, seen = new Set(), auth = [];
      for (const a of p.authors || []) {
        const id = authorId(a[0]);
        if (id && !seen.has(id.id)) { seen.add(id.id); auth.push(id.id); AUTH[id.id] = AUTH[id.id] || id.name; }
      }
      const venue = venueFromKey(k);
      if (venue && p.journal) { const t = vt[venue] || (vt[venue] = {}); t[p.journal] = (t[p.journal] || 0) + 1; }
      return { k, stub, year: p.year || 0, pass: stub ? 0 : p.pass || 0, type: p.type || "", auth, venue };
    };
    IDX = PK.map(k => row(k, false)).concat(SK.map(k => row(k, true)));
    for (const r of IDX) if (r.venue && !VENUE[r.venue])      // the most-used spelling names the token
      VENUE[r.venue] = vt[r.venue] ? Object.entries(vt[r.venue]).sort((a, b) => b[1] - a[1] || a[0].length - b[0].length)[0][0] : r.venue;
    return IDX;
  }
  // The filter: several fields, several picks in each. A paper passes when it matches ANY pick
  // within a field and EVERY field that has picks. `skip` lifts one field, which is how a
  // field's own counts are taken (so ticking a second author doesn't zero out the first's list).
  const F0 = () => ({ type: new Set(), topic: new Set(), author: new Set(), journal: new Set(), y0: 0, y1: 0 });
  S.f = F0(); S.fq = { author: "", journal: "" }; S.fmore = {};
  const nFilters = () => { const f = S.f; return f.type.size + f.topic.size + f.author.size + f.journal.size + (f.y0 || f.y1 ? 1 : 0); };
  function passes(r, skip){
    const f = S.f;
    if (S.scope === "curated" ? r.stub : S.scope === "stub" && !r.stub) return false;
    if (skip !== "type" && f.type.size && !f.type.has(r.type)) return false;
    if (skip !== "topic" && f.topic.size && (r.stub || ![...f.topic].some(t => tIn[t].has(r.k)))) return false;
    if (skip !== "year" && (f.y0 && !(r.year >= f.y0) || f.y1 && !(r.year && r.year <= f.y1))) return false;
    if (skip !== "journal" && f.journal.size && !f.journal.has(r.venue)) return false;
    if (skip !== "author" && f.author.size && !r.auth.some(a => f.author.has(a))) return false;
    return true;
  }
  function libRows(){
    const rows = index().filter(r => passes(r));
    rows.sort((a, b) => S.sort === "new" ? b.year - a.year : S.sort === "old" ? (a.year || 9999) - (b.year || 9999) : b.pass - a.pass || b.year - a.year);
    return rows;
  }
  const SORTS = { new: ["Newest", "Newest first"], old: ["Oldest", "Oldest first"], pass: ["Curated", "Most curated"] };
  const TYPES = { original: "Original", review: "Review", perspective: "Perspective", methods: "Methods" };
  const typeName = t => TYPES[t] || t[0].toUpperCase() + t.slice(1);
  const toggle = (set, v) => { set.has(v) ? set.delete(v) : set.add(v); S.more.lib = 0; };
  const yearsLabel = f => f.y0 && f.y1 ? (f.y0 === f.y1 ? `${f.y0}` : `${f.y0}–${f.y1}`) : f.y0 ? `${f.y0} on` : `to ${f.y1}`;
  // every pick as a removable chip, for the list's head
  function picked(){
    const f = S.f, out = [];
    const add = (label, drop) => out.push(`<button class="pa-chip on" ${act(() => { drop(); S.more.lib = 0; render(0); })}>${tx(label)}`
      + `<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg></button>`);
    f.type.forEach(t => add(typeName(t), () => f.type.delete(t)));
    if (f.y0 || f.y1) add(yearsLabel(f), () => { f.y0 = f.y1 = 0; });
    f.journal.forEach(j => add(VENUE[j] || j, () => f.journal.delete(j)));
    f.author.forEach(a => add(AUTH[a] || a, () => f.author.delete(a)));
    return out.join("");
  }
  function library(){
    const rows = libRows(), f = S.f;
    const scopes = [["all", "All", PK.length + SK.length], ["curated", "Curated", PK.length], ["stub", "Stubs", SK.length]];
    let h = `<div class="pa-col"><div style="padding:12px 16px 0;display:flex;flex-direction:column;gap:10px">`
      + `<div class="pa-seg" style="grid-template-columns:repeat(3,minmax(0,1fr))">`
      + scopes.map(([k, l, n]) => `<button class="${S.scope === k ? "on" : ""}" ${act(() => { S.scope = k; S.more.lib = 0; render(0); })}>${l}<i>${n}</i></button>`).join("")
      + `</div>`;
    if (tLeaves.length) h += `<div class="pa-chips">` + tLeaves.map(k => `<button class="pa-chip${f.topic.has(k) ? " on" : ""}" `
      + `${act(() => { toggle(f.topic, k); render(0); })}>${tx(TOPICS[k].title)}<i>${tIn[k].size}</i></button>`).join("") + `</div>`;
    const more = picked();
    if (more) h += `<div class="pa-chips">${more}<button class="pa-chip" ${act(() => { S.f = F0(); S.more.lib = 0; render(0); })}>Clear all</button></div>`;
    h += `</div><div class="pa-listhd pa-cap"><span>${plural(rows.length, "paper")}${nFilters() ? " · filtered" : ""}</span>`
      + `<span>${SORTS[S.sort][1]}</span></div><div class="pa-list">`
      + (rows.length ? paged("lib", rows, 60, x => x.stub ? stubRow(x.k) : paperRow(x.k))
                     : `<div class="pa-note">${f.topic.size && S.scope === "stub" ? "Topics hold curated papers only — a stub has no tags yet." : "Nothing matches every filter."}</div>`)
      + `</div><div class="pa-pad"></div></div>`;
    return h;
  }

  // ── the filter sheet ──
  const check = (on, label, cnt, fn, cls) => `<button class="pa-radio pa-check${cls ? " " + cls : ""}" ${act(fn)}><i class="${on ? "on" : ""}"></i>`
    + `<span>${tx(label)}</span><em>${cnt}</em></button>`;
  // Authors and journals run to thousands, so each is a ranked list with its own find box:
  // the picks first, then the most frequent names under the other filters, more on request.
  function facetList(field){
    const set = S.f[field], names = field === "author" ? AUTH : VENUE, q = fold(S.fq[field].trim());
    const n = {};
    for (const r of index()) if (passes(r, field)) {
      if (field === "author") for (const a of r.auth) n[a] = (n[a] || 0) + 1;
      else if (r.venue) n[r.venue] = (n[r.venue] || 0) + 1;
    }
    const hit = k => !q || fold(names[k] || k).includes(q) || (field === "journal" && fold(k).includes(q));
    const rest = Object.keys(n).filter(k => !set.has(k) && hit(k)).sort((a, b) => n[b] - n[a] || (names[a] || a).localeCompare(names[b] || b));
    const cap = S.fmore[field] || 8;
    const flip = k => () => { toggle(set, k); render(); };
    let h = [...set].map(k => check(true, names[k] || k, n[k] || 0, flip(k))).join("")
      + rest.slice(0, cap).map(k => check(false, names[k] || k, n[k], flip(k))).join("");
    if (rest.length > cap) h += `<button class="pa-more" ${act(() => { S.fmore[field] = cap + 20; render(); })}>Show ${Math.min(20, rest.length - cap)} more · ${rest.length - cap} left</button>`;
    else if (!rest.length && q) h += `<div class="pa-note">No ${field} matches “${tx(S.fq[field].trim())}”.</div>`;
    return h;
  }
  function sheet(){
    const f = S.f, n = libRows().length;
    const cap = (t, sub) => `<span class="pa-cap pa-fcap">${t}${sub ? `<em>${sub}</em>` : ""}</span>`;
    // counts beside each pick are what the list would gain with that field lifted
    const typeN = {}, topicN = {};
    let yMin = 9999, yMax = 0;
    for (const r of index()) {
      if (r.year) { yMin = Math.min(yMin, r.year); yMax = Math.max(yMax, r.year); }
      if (passes(r, "type")) typeN[r.type] = (typeN[r.type] || 0) + 1;
      if (!r.stub && passes(r, "topic")) for (const t of TK) if (tIn[t].has(r.k)) topicN[t] = (topicN[t] || 0) + 1;
    }
    const types = Object.keys(TYPES).filter(t => typeN[t] || f.type.has(t))
      .concat(Object.keys(typeN).filter(t => t && !TYPES[t] && t !== "aim"));
    let topics = "";
    const seen = new Set(), tflip = k => () => { toggle(f.topic, k); render(); };
    for (const r of tRoots) {
      topics += check(f.topic.has(r), TOPICS[r].title, topicN[r] || 0, tflip(r));
      for (const c of tKids(r)) { if (seen.has(c)) continue; seen.add(c);
        topics += check(f.topic.has(c), TOPICS[c].title, topicN[c] || 0, tflip(c), "sub"); }
    }
    for (const k of tLeaves) if (!seen.has(k)) topics += check(f.topic.has(k), TOPICS[k].title, topicN[k] || 0, tflip(k), "sub");
    const yopt = (sel, any) => `<option value="0">${any}</option>`
      + Array.from({ length: yMax - yMin + 1 }, (_, i) => yMax - i).map(y => `<option${y === sel ? " selected" : ""}>${y}</option>`).join("");
    const clear = (label, fn) => `<button class="pa-fclear" ${act(fn)}>${label}</button>`;
    const find = field => `<label class="pa-ffind"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>`
      + `<input type="search" data-facet="${field}" enterkeyhint="done" autocomplete="off" autocorrect="off" spellcheck="false" `
      + `placeholder="Find ${field === "author" ? "an author" : "a journal"}" value="${tx(S.fq[field])}"></label>`;
    return `<div class="pa-sheet"><div ${act(() => { S.sheet = false; render(); })}></div><div class="pa-sheetb"><div class="pa-col">`
      + `<div class="pa-sheethd"><b>Filter &amp; sort</b>`
      + (nFilters() ? clear("Clear all", () => { S.f = F0(); S.fq = { author: "", journal: "" }; render(); }) : "")
      + `<button aria-label="Close" ${act(() => { S.sheet = false; render(); })}>`
      + `<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>`
      + cap("Sort") + `<div class="pa-seg" style="grid-template-columns:repeat(3,minmax(0,1fr))">`
      + Object.keys(SORTS).map(k => `<button class="${S.sort === k ? "on" : ""}" ${act(() => { S.sort = k; render(); })}>${SORTS[k][0]}</button>`).join("")
      + `</div>`
      + (types.length ? cap("Type", "any of") + `<div class="pa-fwrap">` + types.map(t => `<button class="pa-chip${f.type.has(t) ? " on" : ""}" `
          + `${act(() => { toggle(f.type, t); render(); })}>${tx(typeName(t))}<i>${typeN[t] || 0}</i></button>`).join("") + `</div>` : "")
      + (yMax ? cap("Year", f.y0 || f.y1 ? yearsLabel(f) : "") + `<div class="pa-years">`
          + `<label><span>From</span><select data-year="y0">${yopt(f.y0, "Any")}</select></label>`
          + `<label><span>To</span><select data-year="y1">${yopt(f.y1, "Any")}</select></label></div>` : "")
      + (TK.length ? cap("Topic", "any of · curated papers only") + `<div class="pa-flist">${topics}</div>` : "")
      + cap("Journal", "any of") + find("journal") + `<div class="pa-flist" data-list="journal">${facetList("journal")}</div>`
      + cap("Author", "any of · family name + first initial") + find("author") + `<div class="pa-flist" data-list="author">${facetList("author")}</div>`
      + `<button class="pa-go" ${act(() => { S.sheet = false; S.more.lib = 0; render(0); })}>Show ${plural(n, "paper")}</button>`
      + `</div></div></div>`;
  }
  // the sheet's live parts: a find box re-lists its field only (so it keeps focus), a year
  // picker sets its end of the range (and pushes the other end along if they cross)
  function wireSheet(){
    for (const inp of app.querySelectorAll(".pa-ffind input")) {
      const field = inp.dataset.facet;
      inp.addEventListener("input", () => {
        S.fq[field] = inp.value; S.fmore[field] = 0;
        app.querySelector(`[data-list="${field}"]`).innerHTML = facetList(field);
      });
      inp.addEventListener("keydown", e => { if (e.key === "Enter") inp.blur(); });
    }
    for (const sel of app.querySelectorAll(".pa-years select")) sel.addEventListener("change", () => {
      const f = S.f, v = +sel.value;
      f[sel.dataset.year] = v;
      if (f.y0 && f.y1 && f.y0 > f.y1) f[sel.dataset.year === "y0" ? "y1" : "y0"] = v;
      S.more.lib = 0; render();
    });
  }
  // a topic from elsewhere (Topics tab, a search hit) opens the library on that topic alone
  const showTopic = k => { keepPos(); S.tab = "library"; S.f = F0(); S.f.topic.add(k); S.scope = "curated"; S.more.lib = 0; S.stacks.library = []; render(0); };
  // ── topics: the broad ladder ──
  function topics(){
    const toLib = k => () => showTopic(k);
    const trow = k => `<button class="pa-item" ${act(toLib(k))}><span><span class="pa-it b">${tx(TOPICS[k].title)}</span>`
      + (TOPICS[k].note ? `<span class="pa-in">${tx(TOPICS[k].note)}</span>` : "") + `</span>`
      + `<span class="pa-n">${plural(tIn[k].size, "paper")}</span>${CHEV}</button>`;
    let h = `<div class="pa-col">`;
    for (const r of tRoots) {
      h += `<button class="pa-item" style="border-top:2px solid var(--pa-text);padding:18px 16px 12px" ${act(toLib(r))}><span>`
         + `<span class="pa-cap">${tx(TOPICS[r].title)} · ${plural(tIn[r].size, "paper")}</span>`
         + (TOPICS[r].note ? `<span class="pa-in">${tx(TOPICS[r].note)}</span>` : "") + `</span>${CHEV}</button>`;
      h += tKids(r).map(trow).join("");
    }
    if (!tRoots.length) h += tLeaves.map(trow).join("");
    const bs = Object.keys(BROAD);
    const claims = bs.filter(k => bkind(k) === "claim").map(k => ({ k, st: stance({ t: "broad", slug: k }) }))
      .sort((a, b) => (b.st.sup.length + b.st.con.length) - (a.st.sup.length + a.st.con.length));
    if (claims.length) h += sec("Broad claims", "where the evidence stands") + paged("bclaims", claims, 25, ({ k, st }) =>
      `<button class="pa-row" ${act(() => push({ t: "broad", slug: k }))} style="gap:8px"><span class="pa-rtitle">${tx(BROAD[k].text)}</span>`
      + bar(st.sup.length, st.con.length) + `</button>`);
    const qs = bs.filter(k => bkind(k) === "question");
    if (qs.length) h += sec("Open questions") + qs.map(k => { const n = { t: "broad", slug: k }, a = answered(n);
      const raised = new Set(ins(n, "l").map(cont)).size;
      return `<button class="pa-row" ${act(() => push({ t: "broad", slug: k }))}><span class="pa-rtitle">${tx(BROAD[k].text)}</span>`
        + `<span style="display:flex;gap:8px;align-items:center"><span class="pa-tag ${a ? "ans" : "open"}">${a ? "Answered" : "Open"}</span>`
        + `<span class="pa-meta">Raised by ${plural(raised, "paper")}</span></span></button>`; }).join("");
    // methods: the leads_to ladder, drawn as an indented tree from its tops
    const ms = bs.filter(k => bkind(k) === "method");
    if (ms.length) {
      const up = k => (BROAD[k].leads_to || []).filter(r => BROAD[r] && bkind(r) === "method");
      const kids = k => ms.filter(c => up(c).includes(k));
      const out = [], seen = new Set();
      const walk = (k, d) => { if (seen.has(k)) return; seen.add(k); out.push({ k, d }); kids(k).forEach(c => walk(c, d + 1)); };
      ms.filter(k => !up(k).length).forEach(k => walk(k, 0));
      ms.forEach(k => walk(k, 0));
      h += sec("Methods") + out.map(({ k, d }) => { const n = { t: "broad", slug: k };
        const used = new Set(ins(n, "l").filter(x => x.t === "slice").map(cont)).size;
        const meta = used ? `Used by ${plural(used, "paper")}` : kids(k).length ? "Top of the method ladder" : "Not used yet";
        return `<button class="pa-item" style="gap:10px" ${act(() => push({ t: "broad", slug: k }))}>`
          + `<span class="pa-rule${d ? " on" : ""}" style="width:${d * 14}px;flex:none"></span>`
          + `<span style="flex:1;min-width:0;display:flex;flex-direction:column;gap:3px"><span class="pa-it b">${tx(BROAD[k].text)}</span>`
          + `<span class="pa-meta">${meta}</span></span></button>`; }).join("");
    }
    return h + `<div class="pa-pad"></div></div>`;
  }

  // ── reading: the worklist, what is in progress, and the frontier ──
  function reading(){
    const active = (GRAPH.active || []).filter(k => SL[k]);
    const prog = PK.filter(k => (PAPERS[k].pass || 0) < 4 && !active.includes(k))
      .sort((a, b) => (PAPERS[b].pass || 0) - (PAPERS[a].pass || 0) || (PAPERS[b].year || 0) - (PAPERS[a].year || 0));
    const done = PK.filter(k => PAPERS[k].pass === 4);
    const front = SK.filter(k => cites[k]).sort((a, b) => cites[b] - cites[a]);
    const passMeta = k => { const p = PAPERS[k].pass || 0;
      return p < 4 ? `Pass ${p} of 4 · ${PASS[p]} · next: ${PASS[p + 1].toLowerCase()}` : `${plural(PAPERS[k].slices.length, "slice")} · finished`; };
    let h = `<div class="pa-col">`;
    if (active.length) h += sec("On the desk", "the worklist") + active.map(k => paperRow(k, passMeta(k))).join("");
    h += sec("In progress", "being curated") + paged("prog", prog, 30, k => paperRow(k, passMeta(k)));
    if (done.length) h += sec("Curated", "all four passes") + paged("done", done, 30, k => paperRow(k, passMeta(k)));
    if (front.length) h += sec("Frontier", "stubs, most cited first") + paged("front", front, 30, stubRow);
    return h + `<div class="pa-pad"></div></div>`;
  }

  // ── search ──
  function search(){
    const q = S.q.trim().toLowerCase();
    if (q.length < 2) {
      if (!recent.length) return `<div class="pa-col"><div class="pa-note">Search papers, stubs, claims, broad slices and topics.</div></div>`;
      return `<div class="pa-col"><div class="pa-cap" style="padding:20px 16px 10px">Recent</div>` + recent.map(r =>
        `<button class="pa-item" style="height:48px;padding:0 16px;gap:10px" ${act(() => { S.q = r; render(0); })}>`
        + `<svg class="pa-chev" viewBox="0 0 24 24"><path d="M12 7v5l3 2"/><circle cx="12" cy="12" r="9"/></svg>`
        + `<span class="pa-it" style="font-size:16px">${tx(r)}</span></button>`).join("") + `</div>`;
    }
    const m = s => !!s && String(s).toLowerCase().includes(q);
    const mp = k => { const p = PAPERS[k]; return m(k) || m(p.title) || (p.tags || []).some(m) || (p.authors || []).some(a => m(a[0])); };
    const ms = k => { const s = STUBS[k]; return m(k) || m(s.title) || m(s.journal) || (s.authors || []).some(a => m(a[0])); };
    const papers = PK.filter(mp).map(k => ({ t: "paper", key: k })).concat(SK.filter(ms).map(k => ({ t: "stub", key: k })));
    const slices = []; for (const pk of PK) for (const s of PAPERS[pk].slices)
      if (m(s.text) || m(s.quote)) slices.push({ t: "slice", pk, id: s.id });
    const broad = Object.keys(BROAD).filter(k => m(BROAD[k].text) || m(BROAD[k].title) || m(k)).map(slug => ({ t: "broad", slug }));
    const tps = TK.filter(k => m(TOPICS[k].title) || (TOPICS[k].keywords || []).some(m));
    const groups = [["Papers", papers, n => item(n)],
      ["Claims, questions, methods", slices, n => item(n, (KIND[sl(n).kind] || sl(n).kind).toLowerCase())],
      ["Broad slices", broad, n => item(n)],
      ["Topics", tps, k => `<button class="pa-item" ${act(() => { remember(S.q.trim()); showTopic(k); })}>`
        + `<span><span class="pa-ik">Topic · ${plural(tIn[k].size, "paper")}</span><span class="pa-it">${tx(TOPICS[k].title)}</span></span>${CHEV}</button>`]]
      .filter(g => g[1].length);
    if (!groups.length) return `<div class="pa-col"><div class="pa-note">Nothing matches “${tx(S.q)}”.</div></div>`;
    return `<div class="pa-col">` + groups.map(([t, l, fn]) => sec(t, l.length, "sm") + paged("s:" + t, l, 20, fn)).join("")
      + `<div class="pa-pad"></div></div>`;
  }

  // ── a paper: its own contents ──
  const pdfOK = k => LIVE && PDFS && PDFS.has(k);
  function paper(key){
    const p = PAPERS[key];
    const count = k => p.slices.filter(s => s.kind === k).length;
    const kinds = [["all", "All", p.slices.length], ["claim", "Claims", count("claim")], ["question", "Questions", count("question")], ["method", "Methods", count("method")]];
    const tags = p.tags || [];
    let h = `<div class="pa-col"><div class="pa-head"><span class="pa-cap">${tx([key, p.type, p.year].filter(Boolean).join(" · "))}</span>`
      + `<h1>${tx(p.title || key)}</h1>` + (p.authors && p.authors.length ? `<span class="pa-auth">${tx(authors(p.authors))}</span>` : "")
      + `<span class="pa-pass">${pm(p.pass, true)}${p.pass == null ? "No pass recorded" : `Pass ${p.pass} of 4 · ${PASS[p.pass]}`}</span>`
      + (tags.length ? `<span class="pa-tags">` + tags.map(t => `<button ${act(() => { remember(t); keepPos(); S.tab = "search"; S.q = t; S.stacks.search = []; render(0); })}>${tx(t)}</button>`).join("") + `</span>` : "")
      + (pdfOK(key) ? `<span class="pa-links"><a href="pdf/${encodeURIComponent(key)}.pdf" target="_blank" rel="noopener">Open the PDF</a></span>` : "")
      + (p.note ? `<span class="pa-sub">${tx(p.note)}</span>` : "") + `</div>`;
    if (p.abs) h += `<button class="pa-abs" ${act(() => { S.absOpen = !S.absOpen; render(scroller().scrollTop); })}>Abstract<span>${S.absOpen ? "−" : "+"}</span></button>`
      + (S.absOpen ? `<p class="pa-abstx">${tx(p.abs)}</p>` : "");
    h += `<div class="pa-sticky"><div class="pa-seg kinds" style="grid-template-columns:repeat(4,minmax(0,1fr))">`
      + kinds.map(([k, l, n]) => `<button class="${S.kind === k ? "on" : ""}" ${act(() => { S.kind = k; render(scroller().scrollTop); })}>${l}<i>${n}</i></button>`).join("")
      + `</div></div>`;
    for (const [k, label] of [["claim", "Claims"], ["question", "Questions"], ["method", "Methods"]]) {
      if (S.kind !== "all" && S.kind !== k) continue;
      const rows = p.slices.filter(s => s.kind === k);
      if (!rows.length) continue;
      h += sec(label, rows.length);
      for (const s of rows) {
        const n = { t: "slice", pk: key, id: s.id }, b = [];
        if (k === "claim") {
          const g = outs(n, "g").length, st = stance(n), an = outs(n, "a");
          if (g) b.push(["", plural(g, "ground")]);
          if (st.sup.length) b.push(["s", `+${st.sup.length} corroborate`]);
          if (st.con.length) b.push(["c", `−${st.con.length} contradict`]);
          if (an.length) b.push(["p", "answers " + an.map(x => x.id || x.slug || x.key).join(", ")]);
        } else if (k === "question") b.push(answered(n) ? ["s", "Answered"] : ["p", "Open"]);
        else { const u = ins(n, "g").length; if (u) b.push(["", `used by ${u}`]); }
        const q = s.qd || s.quote;
        h += `<button class="pa-srow" ${act(() => push({ t: "slice", pk: key, id: s.id }))}><span class="pa-sid ${k}">${tx(s.id)}</span>`
          + `<span class="pa-sbody"><span class="pa-it">${tx(s.text)}</span>`
          + (q ? `<span class="pa-q">“${tx(q)}”</span>` : "")
          + (b.length ? `<span class="pa-badges">${b.map(([c, t]) => `<i class="${c}">${tx(t)}</i>`).join("")}</span>` : "")
          + `</span>${CHEV}</button>`;
      }
    }
    // what this paper stands on, and what stands on it — whole papers, from the g edges
    const on = new Map(), by = new Map();
    for (const s of p.slices) for (const t of outs({ t: "slice", pk: key, id: s.id }, "g")) {
      const c = cont(t); if (c !== key) on.set(c, SL[c] ? { t: "paper", key: c } : { t: "stub", key: c }); }
    for (const pk of PK) if (pk !== key) for (const s of PAPERS[pk].slices)
      if (outs({ t: "slice", pk, id: s.id }, "g").some(t => cont(t) === key)) { by.set(pk, { t: "paper", key: pk }); break; }
    if (on.size) h += sec("Built on", on.size) + [...on.values()].map(n => item(n)).join("");
    if (by.size) h += sec("Built on by", by.size) + [...by.values()].map(n => item(n)).join("");
    return h + `<div class="pa-pad"></div></div>`;
  }

  // ── a slice, a broad node, or a stub: one screen each ──
  function detail(r){
    const secs = [];
    const add = (title, list, extra) => { if (list.length) secs.push(sec(title, list.length) + list.map(x => item(x.n || x, x.rel || extra)).join("")); };
    let h = `<div class="pa-col"><div class="pa-det">`, n, quote = "";
    if (r.t === "slice") {
      n = { t: "slice", pk: r.pk, id: r.id }; const s = sl(n);
      h += `<div class="pa-dtop"><span class="pa-kind ${s.kind}">${KIND[s.kind] || tx(s.kind)}</span>`
        + `<button class="pa-src" ${act(() => push({ t: "paper", key: r.pk }))}>${tx(r.pk)} · ${tx(r.id)}</button>`
        + (s.kind === "question" ? (answered(n) ? `<span class="pa-tag ans">Answered</span>` : `<span class="pa-tag open">Open</span>`) : "")
        + `</div><h1>${tx(s.text)}</h1><span class="pa-sub">${tx(PAPERS[r.pk].title)}</span>`;
      const q = s.qd || s.quote;
      if (q) {
        const pg = s.loc && s.loc.page != null && pdfOK(r.pk)
          ? `<a href="pdf/${encodeURIComponent(r.pk)}.pdf#page=${s.loc.page + 1}" target="_blank" rel="noopener">Page ${s.loc.page + 1} ↗</a>` : "";
        quote = `<div class="pa-quote"><span class="pa-cap">Quote · verbatim from the paper${pg}</span><span>“${tx(q)}”</span></div>`;
      }
      add("Grounded in", outs(n, "g")); add("Built on by", ins(n, "g"));
      add("Leads to", outs(n, "l")); add("Laddered from", ins(n, "l"));
      add("Answers", outs(n, "a")); add("Answered by", ins(n, "a"));
    } else if (r.t === "broad") {
      n = { t: "broad", slug: r.slug }; const b = BROAD[r.slug], k = bkind(r.slug);
      h += `<div class="pa-dtop"><span class="pa-kind broad">Broad ${k}</span>`
        + (k === "question" ? (answered(n) ? `<span class="pa-tag ans">Answered</span>` : `<span class="pa-tag open">Open</span>`) : "")
        + `</div><h1>${tx(b.text || b.title)}</h1>` + (b.title && b.text && b.title !== b.text ? `<span class="pa-sub">${tx(b.title)}</span>` : "");
      const fromBroad = ins(n, "l").filter(x => x.t === "broad"), fromSl = ins(n, "l").filter(x => x.t !== "broad");
      if (k === "question") { add("Raised by", fromSl); add("Answered by", ins(n, "a")); }
      else if (k === "method") add("Used by", fromSl);
      add("Specialized by", fromBroad); add("Generalizes to", outs(n, "l"));
    } else {
      const s = STUBS[r.key] || {}; n = { t: "stub", key: r.key };
      const REL = { g: "grounded in it", l: "leads to it", co: "corroborates it", ct: "contradicts it", a: "answers it" };
      h += `<div class="pa-dtop"><span class="pa-kind stub">Stub</span></div><h1>${tx(s.title || r.key)}</h1>`
        + (s.authors && s.authors.length ? `<span class="pa-auth">${tx(authors(s.authors))}</span>` : "")
        + `<span class="pa-sub">${tx([r.key, s.journal, s.year].filter(Boolean).join(" · "))} · not yet sliced. Links to it point at the whole paper until it is curated.</span>`
        + (s.doi ? `<span class="pa-sub">DOI ${tx(s.doi)}</span>` : "");   // text, not a link: the page links out nowhere
      // the abstract is not in the payload; `lit serve` fetches it on demand (09-live.js)
      if (LIVE && s.doi) {
        const a = stubAbsCache.get(r.key);
        if (typeof a === "string") quote = `<div class="pa-abs">Abstract</div><p class="pa-abstx">${tx(a)}</p>`;
        else if (a !== null && !stubAbsCache.has(r.key)) fetchStubAbstract(r.key).then(() => {
          const c = cur(); if (c && c.t === "stub" && c.key === r.key) render(scroller().scrollTop); });
      }
      const refs = insAll(n);
      if (refs.length) secs.push(sec("Referenced by", refs.length) + refs.map(e => item(e.from, REL[e.rel])).join(""));
    }
    h += `</div>` + quote;
    const isClaim = (r.t === "slice" && sl(n).kind === "claim") || (r.t === "broad" && bkind(r.slug) === "claim");
    const st = stance(n);
    if (isClaim && (st.sup.length || st.con.length))
      h += `<button class="pa-stance" ${act(() => push({ t: "ledger", node: n }))}><span><b>Stance</b>`
        + `<em>Ledger<svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg></em></span>` + bar(st.sup.length, st.con.length, true) + `</button>`;
    return h + secs.join("") + `<div class="pa-pad"></div></div>`;
  }

  // ── the stance ledger: support and contradiction, entry by entry ──
  function ledger(n){
    const st = stance(n), L = lab(n);
    const ent = x => { const l = lab(x.n);
      return `<button class="pa-row pa-lgrow" ${act(() => push(route(x.n)))}><span class="pa-rtop"><span class="pa-key">${tx(l.kicker.replace(" · stub", ""))}</span>`
        + `<span class="pa-yr">${tx(x.rel)}</span>${l.wild ? `<span class="pa-wild">Not yet sliced</span>` : ""}</span>`
        + `<span class="pa-it">${tx(l.text)}</span>` + (l.quote ? `<span class="pa-q">“${tx(l.quote)}”</span>` : "") + `</button>`; };
    const col = (title, c, list, empty) => `<div class="pa-lghd"><i class="${c}"></i><b>${title}</b></div>`
      + (list.length ? list.map(ent).join("") : `<div class="pa-lgempty">${empty}</div>`) + `<div class="pa-lgend"></div>`;
    return `<div class="pa-col"><div class="pa-det"><div class="pa-dtop"><span class="pa-kind">Stance ledger</span>`
      + `<span class="pa-n">${tx(n.t === "broad" ? "Broad claim" : L.kicker)}</span></div><h1 class="sm">${tx(L.text)}</h1></div>`
      + `<div class="pa-lgn"><div class="s"><b>${st.sup.length}</b><span>Supporting</span></div><div class="c"><b>${st.con.length}</b><span>Contradicting</span></div></div>`
      + col("Supporting", "s", st.sup, "Nothing in the library supports this yet.")
      + col("Contradicting", "c", st.con, "Nothing in the library contradicts this yet.")
      + `<div class="pa-pad"></div></div>`;
  }

  // ── render ──
  const ICON = {
    library: `<path d="m16 6 4 14M12 6v14M8 8v12M4 4v16"/>`,
    topics: `<path d="M21 12h-8M21 6H8M21 18h-8M3 6v4c0 1.1.9 2 2 2h3M3 10v6c0 1.1.9 2 2 2h3"/>`,
    reading: `<path d="M12 7v14M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>`,
    search: `<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>`,
  };
  const BOARD = `<svg viewBox="0 0 24 24"><rect x="3" y="4" width="7" height="16"/><rect x="14" y="4" width="7" height="9"/><path d="M10 9h4"/></svg>`;
  const FILTER = `<svg viewBox="0 0 24 24"><path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/></svg>`;
  function header(){
    const r = cur();
    if (r) {
      const st = S.stacks[S.tab];
      return `<div class="pa-push"><div class="pa-col"><button class="pa-back" ${act(() => history.back())}>`
        + `<svg viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>${tx(titleOf(st[st.length - 2] || null))}</button>`
        + `<span class="pa-kick">${tx(kickOf(r))}</span></div></div>`;
    }
    const sub = S.tab === "library" ? plural(PK.length + SK.length, "paper")
      : S.tab === "topics" ? `${tLeaves.length} topics · ${Object.keys(BROAD).length} broad slices`
      : S.tab === "reading" ? `${PK.filter(k => (PAPERS[k].pass || 0) < 4).length} in progress` : "";
    return `<div class="pa-root"><div class="pa-col"><div class="pa-brand">${MARK}<span class="pa-word">Pythia</span><span class="pa-hbtns">`
      + (S.tab === "library" ? `<button class="pa-hbtn" aria-label="Filter and sort" ${act(() => { S.sheet = true; render(); })}>${FILTER}${nFilters() ? `Filters · ${nFilters()}` : "Filter"}</button>` : "")
      + `<button class="pa-hbtn" aria-label="Open the graph board" ${act(() => setMode("board"))}>${BOARD}Board</button></span></div>`
      + `<div class="pa-title"><b>${titleOf(null)}</b><span>${tx(sub)}</span></div>`
      + (S.tab === "search" ? `<div class="pa-search"><label><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>`
        + `<input type="search" enterkeyhint="search" autocomplete="off" autocorrect="off" spellcheck="false" placeholder="Papers, claims, topics"></label></div>` : "")
      + `</div></div>`;
  }
  function body(){
    const r = cur();
    if (!r) return { library, topics, reading, search }[S.tab]();
    if (r.t === "paper") return paper(r.key);
    if (r.t === "ledger") return ledger(r.node);
    return detail(r);
  }
  function tabs(){
    return `<div class="pa-tabs"><div class="pa-col">` + TABS.map(t =>
      `<button class="${S.tab === t ? "on" : ""}" ${act(() => tabTo(t))}><svg viewBox="0 0 24 24">${ICON[t]}</svg>${t[0].toUpperCase() + t.slice(1)}</button>`).join("")
      + `</div></div>`;
  }
  // `top`: where to leave the scroll (undefined keeps it). The search box survives a keystroke
  // because typing re-renders the results only (renderResults), never the header it sits in.
  function render(top){
    const sc = scroller(), keep = sc ? sc.scrollTop : 0;
    const sb = app.querySelector(".pa-sheetb"), sheetKeep = sb ? sb.scrollTop : 0;   // a tick in the sheet keeps its place
    acts = {};
    app.innerHTML = header() + `<div class="pa-scroll">${body()}</div>` + tabs() + (S.sheet && S.tab === "library" && !cur() ? sheet() : "");
    const inp = app.querySelector(".pa-search input");
    if (inp) {
      inp.value = S.q;
      inp.addEventListener("input", () => { S.q = inp.value; S.more = {}; renderResults(); });
      inp.addEventListener("focus", () => app.classList.add("kbd"));
      inp.addEventListener("blur", () => setTimeout(() => app.classList.remove("kbd"), 120));
      inp.addEventListener("keydown", e => { if (e.key === "Enter") { if (S.q.trim()) remember(S.q.trim()); inp.blur(); } });
    }
    const sb2 = app.querySelector(".pa-sheetb");
    if (sb2) { sb2.scrollTop = sheetKeep; wireSheet(); }
    scroller().scrollTop = top === undefined ? keep : top;
  }
  // a keystroke's render: the results region only. Its handlers join `acts` beside the header's
  // and the tab bar's (the stale ones left behind are unreachable, and go at the next render).
  function renderResults(){
    const sc = scroller(); if (!sc) return;
    sc.innerHTML = body();
    sc.scrollTop = 0;
  }

  // ── app ⇄ board ──
  function setMode(m){
    const on = m === "app";
    document.body.classList.toggle("app", on);
    store.set("pythia.view", m);
    if (on) render();
    // the board was laid out while hidden; a resize makes it re-measure and redraw its edges
    else requestAnimationFrame(() => dispatchEvent(new Event("resize")));
  }
  const hudBtn = document.createElement("button");
  hudBtn.id = "appBtn"; hudBtn.className = "libbtn"; hudBtn.textContent = "app";
  hudBtn.title = "the reading app — library, topics, reading, search";
  hudBtn.addEventListener("click", () => setMode("app"));
  const hud = document.getElementById("hud");
  if (hud) hud.insertBefore(hudBtn, hud.children[1] || null);

  const want = QUERY.get("view");
  const mode = want === "app" || want === "board" ? want : (store.get("pythia.view") || (TOUCH ? "app" : "board"));
  if (mode === "app") setMode("app");
})();
