// ── find a paper (build + serve) ─────────────────────────────────────────────────────────
// A paper-finding search: type fragments of what you remember (title, author, journal, year,
// tag) and jump to the matching card. NOT a knowledge search over claims/quotes. Purely
// client-side, so a static `lit build` keeps it working offline. It indexes the WHOLE
// bibliography, curated or not — since the landing column trimmed down to curated papers, this is
// the only path to a stub, and gotoPaper mints its card on demand. Curated papers rank above stubs
// (ORDER is already curated-first). Papers on the reading list (ACTIVE) are held off the landing
// column, but remain searchable: naming one is what asks gotoPaper to mint its card on demand.
const searchInput = document.getElementById("search");
const searchResults = document.getElementById("searchResults");
let searchIndex = null;
function buildSearchIndex(){
  const rows = [];
  for(const key of ORDER){
    const cur = !!(PAPERS[key] && PAPERS[key].cur);
    const p = PAPERS[key] || STUBS[key] || {};
    const authors = (p.authors || []).map(a => a[0]);
    const journal = p.journal || venueFromKey(key);       // curated: venue token from the citekey
    const tags = (cur && p.tags) ? p.tags : [];            // tags are curated-only
    const blob = [key, p.title || "", authors.join(" "), journal, p.year || "", tags.join(" ")]
      .join(" ").toLowerCase();
    // `pass` is curated-only and rides along for the library view's ranking badge; the search
    // dropdown ignores it.
    rows.push({key, cur, title: p.title || key, authors, journal, year: p.year, tags,
               pass: cur ? p.pass : null, blob});
  }
  return rows;
}
function openResults(){
  const r = searchInput.getBoundingClientRect();       // pin under the box (HUD is fixed)
  searchResults.style.left = Math.max(8, Math.min(r.left, innerWidth - 348)) + "px";
  searchResults.style.top = (r.bottom + 6) + "px";
  searchResults.classList.add("on");
}
function closeSearch(){ searchResults.classList.remove("on"); }
const SR_CAP = 12;
function _srRow(r){
  const who = r.authors.length
    ? esc(r.authors.slice(0, 3).join(" · ")) + (r.authors.length > 3 ? " · …" : "") : "";
  const bib = esc([r.journal, r.year].filter(Boolean).join(" · "));
  const meta = [who, bib].filter(Boolean).join("  ·  ");
  const badge = r.cur ? "" : `<span class="sr-badge">stub</span>`;
  return `<div class="sr-row ${r.cur ? "" : "stub"}" data-key="${esc(r.key)}">`
       + `<div class="sr-t">${esc(r.title)}${badge}</div>`
       + `<div class="sr-m">${esc(r.key)}${meta ? "  ·  " + meta : ""}</div></div>`;
}
// A topic (SCHEMA §9) is not a second filter mechanism — it is a saved search over its
// keyword closure, run through this SAME find-a-paper index. "topic:<slug>" is the box's own
// query syntax for it; typing past it falls straight back to ordinary free-text search, same as
// editing a tag-chip search. The library's facet rail is now the way you BROWSE the topic tree
// (it filters rows in place, which is strictly more useful than a dropdown of search results),
// so this syntax is what's left of the old topics panel: still exact, no longer the front door.
function renderTopicResults(slug){
  const topic = TOPICS[slug];
  const hits = topic.papers.map(k => searchIndex.find(r => r.key === k)).filter(Boolean);
  const hd = `<div class="sr-topic">topic · ${esc(topic.title)} · `
           + `${hits.length} paper${hits.length === 1 ? "" : "s"}</div>`;
  const body = hits.length
    ? hits.slice(0, SR_CAP).map(_srRow).join("")
      + (hits.length > SR_CAP ? `<div class="sr-more">+${hits.length - SR_CAP} more — refine the search</div>` : "")
    : `<div class="sr-none">no curated paper carries this topic's keywords</div>`;
  searchResults.innerHTML = hd + body;
  openResults();
}
function renderResults(q){
  if(!searchIndex) searchIndex = buildSearchIndex();
  const q0 = q.trim();
  const topicMatch = /^topic:([a-z0-9][a-z0-9-]*)$/i.exec(q0);
  if(topicMatch && TOPICS[topicMatch[1]]){ renderTopicResults(topicMatch[1]); return; }
  const terms = q0.toLowerCase().split(/\s+/).filter(Boolean);
  if(!terms.length){ closeSearch(); return; }
  const hits = searchIndex.filter(r => terms.every(t => r.blob.includes(t)));   // AND across terms
  if(!hits.length){
    searchResults.innerHTML = `<div class="sr-none">no paper matches “${esc(q)}”</div>`;
  } else {
    let html = hits.slice(0, SR_CAP).map(_srRow).join("");
    if(hits.length > SR_CAP) html += `<div class="sr-more">+${hits.length - SR_CAP} more — refine the search</div>`;
    searchResults.innerHTML = html;
  }
  openResults();
}
function gotoPaper(key){
  closeSearch();
  // A curated paper is already in the flat list, so this is a scroll-and-flash and landedStuck is a
  // no-op. It earns its keep for a STUB, which the list does not carry: naming one is a standing
  // request for it, so the card is minted and survives every rebuild's syncLanding until `clear`.
  if(!STUBS[key] && !PAPERS[key]) return;
  // …but in the walk, the board is not the view you are looking at: naming a paper there means
  // focus the WALK on it. Reached through window (not the `const WALK` below) so this stays safe
  // however early it is called — a bare `typeof` on a const in its temporal dead zone throws.
  if(document.body.classList.contains("walk") && window.litWalk){
    window.litWalk.setFocus(key);
    return;
  }
  landedStuck.add(key);
  // A card that was ALREADY standing keeps its place: the column does not re-sort itself under the
  // reader (syncLanding), and a curated paper you searched for is where the ranking put it. A card
  // minted FOR this request is different — it was summoned by name, the ranking has nothing to say
  // about it, and appending it left the one paper you asked for at the very bottom of a column of
  // thousands, which is also the one place scrollIntoView cannot centre. So it is hoisted to the
  // top instead. Both mint sites are covered: syncLanding below for a summoned stub, and the
  // addPaper for a reading-list paper, which is held off the column until named.
  const minted = !document.getElementById(`card-0:${key}`);
  syncLanding();                             // mints a summoned stub's card, and refreshes every
  let el = document.getElementById(`card-0:${key}`);     // card's provenance + the column header
  if(!el){                                   // a reading-list paper (ACTIVE) is held off the
    addPaper(0, key);                        // landing column — but naming it by hand outranks
    el = document.getElementById(`card-0:${key}`);       // that, so mint the card
    if(!el) return;
  }
  if(minted) hoistAll([el]);                             // summoned by name → top of the column
  redraw();                                              // the column may have grown; edges re-anchor
  el.scrollIntoView({behavior: "smooth", block: "center"});
  flash(el);
}
function runSearch(term){                                 // called by a tag chip → search that tag
  if(!searchInput) return;
  searchInput.value = term;
  searchInput.focus();
  renderResults(term);
}
if(searchInput){
  searchInput.addEventListener("input", () => renderResults(searchInput.value));
  searchInput.addEventListener("focus", () => { if(searchInput.value.trim()) renderResults(searchInput.value); });
  searchInput.addEventListener("keydown", e => {
    if(e.key === "Escape"){ searchInput.value = ""; closeSearch(); searchInput.blur(); }
    else if(e.key === "Enter"){
      const first = searchResults.querySelector(".sr-row");
      if(first) gotoPaper(first.dataset.key);
    }
  });
  searchResults.addEventListener("click", e => {
    const row = e.target.closest(".sr-row");
    if(row) gotoPaper(row.dataset.key);
  });
  addEventListener("click", e => {                       // click outside closes the dropdown
    if(!e.target.closest("#searchResults, #search")) closeSearch();
  }, true);
}

// ── the LIBRARY view ─────────────────────────────────────────────────────────────────────
// Reference-manager browsing: one vertical scroll over the WHOLE bibliography, narrowed by a
// facet rail. It reuses buildSearchIndex() wholesale — that index already carries every field
// a row needs for all 3.8k entries — so this view is a surface over the search machinery, not
// a second copy of it. A row click leaves for the board via gotoPaper(), which mints a card
// for an uncurated stub on demand.
//
// Why topic facets imply curated: `tags` are curated-only (a stub has no curation, so no tags)
// and a topic reaches papers through tags. Selecting a container therefore cannot match a stub,
// and pretending otherwise would show an empty list with no explanation. The scope pill flips
// itself and says so.
if(!DETACHED) (function(){
  const btn = document.getElementById("libBtn");
  const pane = document.getElementById("libraryPane");
  const facets = document.getElementById("libFacets");
  const scroll = document.getElementById("libScroll");
  const sizer = document.getElementById("libSizer");
  const rowsEl = document.getElementById("libRows");
  const filterEl = document.getElementById("libFilter");
  const countEl = document.getElementById("libCount");
  const clearEl = document.getElementById("libClear");
  if(!btn || !pane) return;

  const ROW_H = 76, OVERSCAN = 6;
  // pass ranking first because it is the board's own landing order — the curator's judgement
  // about the library, which a plain year sort would silently discard.
  const SORTS = {
    pass:  {label: "curation pass", cmp: null},        // null = keep index order (ORDER is pass-ranked)
    year:  {label: "year ↓", cmp: (a, b) => (b.year || 0) - (a.year || 0)},
    title: {label: "title", cmp: (a, b) => a.title.localeCompare(b.title)},
  };
  const SCOPES = {all: "everything", curated: "curated", stub: "uncited stubs"};
  const HEAD = 12, MORE = 60;                          // ranked-facet cap, and what "more" opens it to
  let scope = "all", sort = "pass", topic = null, author = null, journal = null,
      moreAuth = false, moreJrnl = false, rows = [], view = [];

  const leavesByHead = () => Object.entries(TOPICS).filter(([, t]) => t.root)
    .sort((a, b) => a[1].title.localeCompare(b[1].title))
    .map(([slug, t]) => [t, Object.entries(TOPICS).filter(([, x]) => x.broader.includes(slug))
      .sort((a, b) => a[1].title.localeCompare(b[1].title))]);

  // ── the two derived axes ──────────────────────────────────────────────────────────────
  // Neither authors nor journals are stored in a form you can group on directly, and both fail
  // the same way: the curated tier and the stub tier write the *same* fact differently, so a
  // naive tally files one journal (or one person) under two entries and the ranking lies.

  // Journals ride the CITEKEY's venue token, not the display string. A curated paper stores no
  // `journal` at all (SCHEMA §3: the venue only ever lived in the citekey), while a stub carries
  // OpenAlex's full name — so "Nature Physics" and "NatPhys" are the same journal seen from the
  // two tiers. The token is in every citekey on both tiers, which makes it the one key they
  // share; the stubs then donate a readable name for it (the most-cited spelling wins, since
  // OpenAlex serves catalogue variants like "Physical review. E" alongside the modern title).
  let venueName = null;
  function venueNames(){
    if(venueName) return venueName;
    const tally = {};
    for(const [k, s] of Object.entries(STUBS)){
      const t = venueFromKey(k);
      if(!t || !s.journal) continue;
      (tally[t] || (tally[t] = {}))[s.journal] = (tally[t][s.journal] || 0) + 1;
    }
    venueName = {};
    for(const [t, names] of Object.entries(tally))
      venueName[t] = Object.entries(names)
        .sort((a, b) => b[1] - a[1] || a[0].length - b[0].length)[0][0];
    return venueName;
  }
  const venueLabel = tok => venueNames()[tok] || tok;

  // Authors fold to `family|first-initial`. Curated YAML writes "Family, Given" (SCHEMA §4);
  // stubs carry OpenAlex's "Given M. Family" — one person, two strings, and the same person
  // also drifts between "Given Family" and "Given M. Family" across publishers. Family plus
  // first initial is the granularity a bibliography can actually support. The cost is that true
  // homonyms collide, which the rail says out loud rather than pretending precision it hasn't got.
  const PARTICLES = new Set(["van", "von", "de", "der", "den", "du", "del", "della", "di", "da",
                             "dos", "la", "le", "ter", "ten"]);
  const fold = s => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();  // strip accents
  function authorId(raw){
    // U+2010–2015 are the typographic dashes OpenAlex serves in place of ASCII "-"
    const s = String(raw || "").replace(/[\u2010-\u2015]/g, "-").replace(/\s+/g, " ").trim();
    if(!s) return null;
    let family, given;
    const c = s.indexOf(",");
    if(c > -1){ family = s.slice(0, c).trim(); given = s.slice(c + 1).trim(); }
    else {
      const w = s.split(" ");
      let i = w.length - 1;                          // absorb a nobiliary particle into the family
      while(i > 1 && PARTICLES.has(fold(w[i - 1]).replace(/\.$/, ""))) i--;
      family = w.slice(i).join(" "); given = w.slice(0, i).join(" ");
    }
    if(!family) return null;
    const ini = (given.match(/[A-Za-z\u00c0-\u024f]/) || [""])[0].toUpperCase();
    return {id: fold(family) + "|" + fold(ini), name: family + (ini ? ", " + ini + "." : "")};
  }

  // Fold once, onto the shared search index — recompute() runs on every keystroke and would
  // otherwise re-parse ~30k names each time.
  function prepare(r){
    if(r.auth) return r;
    const seen = new Set();
    r.auth = [];
    for(const a of r.authors){
      const id = authorId(a);
      if(id && !seen.has(id.id)){ seen.add(id.id); r.auth.push(id); }
    }
    r.venue = venueFromKey(r.key);
    return r;
  }

  // One ranked facet: rows already tallied, capped at HEAD unless opened, with the current
  // selection pinned in even when it falls outside the cap (counts are computed with this
  // facet's own filter lifted, so a narrow pick can rank low in its own list).
  function rankedFacet(kind, title, tally, sel, more, note){
    let list = Object.entries(tally)
      .sort((a, b) => b[1].n - a[1].n || a[1].name.localeCompare(b[1].name));
    if(!list.length) return "";
    const cap = more ? MORE : HEAD, total = list.length;
    let shown = list.slice(0, cap);
    if(sel && !shown.some(([k]) => k === sel) && tally[sel]) shown = shown.concat([[sel, tally[sel]]]);
    return `<div class="lf-hd">${esc(title)}</div><div class="lf-list">`
      + shown.map(([k, v]) =>
          `<span class="lf-row${sel === k ? " on" : ""}" data-${kind}="${esc(k)}" `
          + `title="${esc(v.name)}"><span class="nm">${esc(v.name)}</span>`
          + `<span class="n">${v.n}</span></span>`).join("")
      + `</div>`
      + (total > cap
          ? `<div class="lf-more" data-more="${kind}">${more ? "less" : `${total - cap} more…`}</div>`
          : "")
      + (note ? `<div class="lf-note">${note}</div>` : "");
  }

  function renderFacets(tallies){
    let html = `<div class="lf-hd">show</div><div class="lf-seg">`
      + Object.entries(SCOPES).map(([k, lbl]) =>
          `<span class="lf-opt${scope === k ? " on" : ""}" data-scope="${k}">${esc(lbl)}</span>`).join("")
      + `</div>`
      // sort rides up here with scope: both are controls over the whole list, whereas topic,
      // journal and author are the three filter axes and read better as one block.
      + `<div class="lf-hd">sort</div><div class="lf-seg">`
      + Object.entries(SORTS).map(([k, s]) =>
          `<span class="lf-opt${sort === k ? " on" : ""}" data-sort="${k}">${esc(s.label)}</span>`).join("")
      + `</div>`;
    const heads = leavesByHead().filter(([, leaves]) => leaves.length);
    if(heads.length){
      html += `<div class="lf-hd">topic</div>`
        + heads.map(([t, leaves]) =>
            `<div class="tp-head" title="${esc(t.note || "")}">${esc(t.title)}</div>`
            + `<div class="tp-leaves">` + leaves.map(([lslug, lt]) =>
                `<span class="tp-chip${topic === lslug ? " on" : ""}" data-slug="${esc(lslug)}" `
                + `title="${esc(lt.note || "")}">${esc(lt.title)}`
                + `<span class="n">${lt.papers.length}</span></span>`).join("")
            + `</div>`).join("")
        + `<div class="lf-note">headings group and can't be filtered; click a container to narrow. `
        + `Topics reach curated papers only — a stub carries no tags.</div>`;
    }
    html += rankedFacet("jrnl", "journal", tallies.jrnl, journal, moreJrnl,
                        "grouped by the citekey's venue token, so a curated paper and the stubs "
                        + "citing the same journal land on one row.")
          + rankedFacet("auth", "author", tallies.auth, author, moreAuth,
                        "ranked by how often the name appears across the whole bibliography. "
                        + "Folded to family name + first initial, so two people who share both "
                        + "share a row.");
    facets.innerHTML = html;
  }

  function recompute(){
    // `rows` is derived from the index, so it must die with it whenever the index is invalidated.
    if(!searchIndex){ searchIndex = buildSearchIndex(); rows = []; }
    if(!rows.length) rows = searchIndex.map(prepare);  // ORDER's ranking, curated-first
    const terms = filterEl.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const inTopic = topic ? new Set(TOPICS[topic].papers) : null;
    // `skip` lifts one facet's own filter, so its list keeps showing the alternatives you could
    // switch to instead of collapsing to the one row you already picked.
    const passes = (r, skip) => {
      if(scope === "curated" && !r.cur) return false;
      if(scope === "stub" && r.cur) return false;
      if(skip !== "topic" && inTopic && !inTopic.has(r.key)) return false;
      if(skip !== "jrnl" && journal && r.venue !== journal) return false;
      if(skip !== "auth" && author && !r.auth.some(a => a.id === author)) return false;
      return terms.every(t => r.blob.includes(t));
    };
    const tallies = {auth: {}, jrnl: {}};
    for(const r of rows){
      if(r.venue && passes(r, "jrnl")){
        const e = tallies.jrnl[r.venue] || (tallies.jrnl[r.venue] = {n: 0, name: venueLabel(r.venue)});
        e.n++;
      }
      if(passes(r, "auth")) for(const a of r.auth){
        const e = tallies.auth[a.id] || (tallies.auth[a.id] = {n: 0, name: a.name});
        e.n++;
      }
    }
    view = rows.filter(r => passes(r, null));
    const cmp = SORTS[sort].cmp;
    if(cmp) view = view.slice().sort(cmp);
    countEl.textContent = `${view.length} of ${rows.length}`;
    clearEl.hidden = !(topic || author || journal || terms.length
                       || scope !== "all" || sort !== "pass");
    const keepScroll = facets.scrollTop;               // the rail re-renders on every keystroke
    renderFacets(tallies);
    facets.scrollTop = keepScroll;
    sizer.style.height = (view.length * ROW_H) + "px";
    paint();
  }

  function rowHTML(r){
    const who = r.authors.length
      ? esc(r.authors.slice(0, 4).join(" · ")) + (r.authors.length > 4 ? " · …" : "") : "";
    // the venue token resolved back to a real journal name, same map the facet ranks by
    const bib = esc([r.venue ? venueLabel(r.venue) : r.journal, r.year].filter(Boolean).join(" · "));
    const badge = r.cur ? "" : `<span class="lr-badge">stub</span>`;
    const tags = (r.tags || []).slice(0, 8)
      .map(t => `<span class="lr-tag">${esc(t)}</span>`).join("");
    // the same pie the board's cards carry (pass/4), in a gutter the title can't clip
    return `<div class="lr ${r.cur ? "" : "stub"}" data-key="${esc(r.key)}">`
         + `<div class="lr-ind">${passCircle(r.cur ? r.pass : 0)}</div>`
         + `<div class="lr-body">`
         + `<div class="lr-t">${esc(r.title)}</div>`
         + `<div class="lr-m">${badge}${esc(r.key)}${who || bib ? "  ·  " + [who, bib].filter(Boolean).join("  ·  ") : ""}</div>`
         + `<div class="lr-tags">${tags}</div></div>`
         + `<button class="lr-go" title="show this paper on the board">board →</button></div>`;
  }

  // Windowed paint: only the rows the viewport can see are in the DOM, offset by a transform.
  function paint(){
    if(!view.length){
      rowsEl.style.transform = "translateY(0)";
      rowsEl.innerHTML = `<div class="lr-none">nothing in the library matches these filters.</div>`;
      return;
    }
    const first = Math.max(0, Math.floor(scroll.scrollTop / ROW_H) - OVERSCAN);
    const last = Math.min(view.length, first + Math.ceil(scroll.clientHeight / ROW_H) + OVERSCAN * 2);
    rowsEl.style.transform = `translateY(${first * ROW_H}px)`;
    rowsEl.innerHTML = view.slice(first, last).map(rowHTML).join("");
  }

  // named openLib/closeLib, not open/close: the outer scope has an `open` Set (focused cards)
  // and window.close is a real function — shadowing either from in here is a trap for later.
  function openLib(){
    document.body.classList.add("library");
    btn.classList.add("on");
    btn.textContent = "← board";
    recompute();                                // renders the rail too: the facet counts are of the view
    scroll.scrollTop = 0;
    paint();
  }
  function closeLib(){
    document.body.classList.remove("library");
    btn.classList.remove("on");
    btn.textContent = "library";
    redraw();                                   // the board was display:none; its edges need re-anchoring
  }
  const isOpen = () => document.body.classList.contains("library");

  btn.hidden = false;
  btn.addEventListener("click", () => isOpen() ? closeLib() : openLib());
  scroll.addEventListener("scroll", paint);
  addEventListener("resize", () => { if(isOpen()) paint(); });
  filterEl.addEventListener("input", () => { scroll.scrollTop = 0; recompute(); });
  clearEl.addEventListener("click", () => {
    scope = "all"; sort = "pass"; topic = null; author = null; journal = null;
    moreAuth = moreJrnl = false; filterEl.value = "";
    scroll.scrollTop = 0; recompute();
  });
  facets.addEventListener("click", e => {
    const sc = e.target.closest("[data-scope]"), so = e.target.closest("[data-sort]"),
          ch = e.target.closest(".tp-chip"), rw = e.target.closest("[data-auth],[data-jrnl]"),
          mo = e.target.closest("[data-more]");
    if(sc) scope = sc.dataset.scope;
    else if(so) sort = so.dataset.sort;
    else if(mo){                                         // open/close a ranked facet's tail
      if(mo.dataset.more === "auth") moreAuth = !moreAuth; else moreJrnl = !moreJrnl;
      recompute(); return;                               // not a filter change — hold the scroll spot
    }
    else if(rw){
      if(rw.dataset.auth !== undefined) author = author === rw.dataset.auth ? null : rw.dataset.auth;
      else journal = journal === rw.dataset.jrnl ? null : rw.dataset.jrnl;
    }
    else if(ch){
      topic = topic === ch.dataset.slug ? null : ch.dataset.slug;
      if(topic && scope === "stub") scope = "curated";   // a stub can't carry a topic; say so by moving
    } else return;
    scroll.scrollTop = 0; recompute();
  });
  // Two destinations, two gestures. The ROW means "read this": it opens the paper's PDF in the
  // dock beside the list and stays in the library, which is what browsing a bibliography is
  // actually for — you scan, you open one, you scan on. The BOARD button is the seam over to the
  // reasoning surface, and it is explicit because it costs you the list.
  //
  // Falling back matters: a stub has no PDF and a static `lit build` serves none at all, so
  // where there is nothing to open the row keeps its old meaning rather than doing nothing.
  // Leaving first means gotoPaper's scrollIntoView + flash land on a visible board.
  scroll.addEventListener("click", e => {
    const row = e.target.closest(".lr");
    if(!row) return;
    const key = row.dataset.key;
    if(e.target.closest(".lr-go") || !(LIVE && PDFS && PDFS.has(key))){
      closeLib();
      gotoPaper(key);
      return;
    }
    // closeDock() drops the mount but leaves dockShown parked, so clicking the SAME row after
    // shutting the dock would early-out of loadDock and then open on the wrong paper.
    if(!pdfActive()) dockShown = null;
    loadDock(key);
    if(!pdfActive()) openDock();                 // …which turns the 📄 PDF pill on
    paint();                                     // the pane just lost width (or height, in portrait)
  });
  addEventListener("keydown", e => { if(e.key === "Escape" && isOpen()) closeLib(); });
  // …but a ?goto= names a destination on the BOARD (17-handoff), and it wins: a handoff that
  // landed behind the library pane would look like a handoff that did nothing.
  const q = new URLSearchParams(location.search);
  if(q.get("view") === "library" && !q.get("goto")) openLib();
})();

board.addEventListener("scroll",redraw);
// The overlay is sized from the port (redraw's W/H floor) and edgeVis's legibility clause is
// measured against it, so a resized window leaves both stale until something else redraws.
addEventListener("resize",redraw);
addEventListener("resize",redraw);

// ── the reading list: `[curation] active`, surfaced as the WIP panel (serve only) ─────────
// Curation moved outside the browser — a conventional coding agent works the paper against
// `curated/<citekey>.yaml` directly, following CURATION.md, with the human reviewing the diff.
// `[curation] active` survives that move as a plain reading list: papers you asked to keep in
// view. The right-click "Curate this paper" on a card (10-pdf.js) and `lit curate` both add to
// it; the "reading list" pill below reads it back and opens a picker. There used to be a third
// door here — clicking a row opened three real OS windows (an isolated card, a PDF pane polling
// a focus wire, a terminal running that paper's agent session) and POSTed to `/term` to spawn
// it. All of that — the focus wire, the card/paper window split, `/term`, `lit focus` — was the
// curation cockpit, and it went with the cockpit: a row click now just finds the paper on the
// board, the same gesture a search result or a library row already makes (gotoPaper).
// The programme index: a HUD pill listing everything in the programme layer, each row a link to
// its own page at /preview.html?key=<slug> — the same isolated view `lit preview` writes, so the
// served page and the written one cannot drift. Server-only (/aims.json is a `lit serve` route),
// so a static `lit build` never sprouts it, and a repo with no programme/ tree never shows it.
//
// This pill is the ONLY door to the programme layer now. It used to be a shortcut past a lane
// that stood on the board whether you wanted it or not; that lane is gone (18-programme.js), so
// what was a convenience is now the way in. Proposals lead the list — a `~<grant>` row opens the
// narrative WITH the aims under it, which is how a proposal is read — and the aims follow, each
// still openable alone for the times you want one argument without its introduction.
if (LIVE && !DETACHED) (function(){
  const pill = document.getElementById("aims");
  const panel = document.getElementById("aimPanel");
  if (!pill || !panel) return;
  const cardUrl = slug => {                 // built off THIS document's URL, like the worklist's
    const u = new URL("preview.html", location.href); u.hash = "";
    u.searchParams.set("key", slug);
    return u.href;
  };
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  fetch("aims.json").then(r => r.ok ? r.json() : []).then(list => {
    if (!list.length) return;               // no programme tree → the pill stays hidden
    pill.innerHTML = `programme · <span class="n">${list.length}</span>`;
    pill.hidden = false;
    panel.innerHTML = `<div class="wp-hd">programme</div>` + list.map(a => {
      // what is worth seeing without opening the row. For an aim that is the two things a
      // reviewer finds first; for a proposal it is its size — its assumptions ARE the aims',
      // and they are already stated on the rows below it.
      const bits = [];
      let flag;
      if (a.kind === "proposal") {
        flag = `${plural(a.sections, "section")} · ${plural(a.bullets, "line")}`;
      } else {
        if (a.assumptions) bits.push(plural(a.assumptions, "assumption"));
        if (a.at_risk) bits.push(plural(a.at_risk, "test") + " at risk");
        flag = bits.length ? bits.join(" · ") : plural(a.slices, "slice");
      }
      return `<a class="ap-row${a.kind === "proposal" ? " prop" : ""}"`
           + ` href="${esc(cardUrl(a.slug))}" target="_blank" rel="noopener">`
           + `<span class="ckey">${esc(a.title || a.slug)}</span>`
           + `<span class="flag${bits.length ? " warn" : ""}">${esc(flag)}</span></a>`;
    }).join("") + `<div class="wp-note">a proposal is its introduction with the aims under it; `
                + `an aim on its own is its hypotheses, what they rest on, and the tests that `
                + `would settle them. Opens in a new tab.</div>`;
    pill.addEventListener("click", e => {
      e.stopPropagation();
      const wipPanel = document.getElementById("wipPanel");
      if (wipPanel) wipPanel.hidden = true;   // one panel open at a time
      panel.hidden = !panel.hidden;
    });
    document.addEventListener("click", e => {
      if (!panel.hidden && !panel.contains(e.target) && e.target !== pill) panel.hidden = true;
    });
  }).catch(() => {});                        // a server without the route: stay hidden
})();

// Both viewer faces remove through the same server acknowledgement and client state.
async function removeFromReadingList(k){
  const response = await fetch("active", {method: "POST",
    body: JSON.stringify({citekey: k, active: false})});
  if (!response.ok) throw new Error("Could not remove the paper from the reading list.");
  const result = await response.json();
  if (!result.ok) throw new Error("Could not remove the paper from the reading list.");
  GRAPH.active = (GRAPH.active || []).filter(key => key !== k);
  ACTIVE.delete(k);
  syncLanding();
  redraw();
  dispatchEvent(new CustomEvent("readinglistchange", {detail: {removed: k}}));
}

// LIVE-gated: a static `lit build` carries no active list, so the pill stays hidden.
if (LIVE && !DETACHED) (function(){
  const pill = document.getElementById("wip");
  const inProg = (GRAPH.active || []).filter(k => PAPERS[k] && PAPERS[k].cur);
  if (!inProg.length) return;
  pill.innerHTML = `reading list · <span class="n">${inProg.length}</span>`;
  pill.hidden = false;

  const panel = document.getElementById("wipPanel");
  const STAGE = ["stub","ingested","skeleton","contextualized","full"];
  const stage = k => { const p = PAPERS[k].pass == null ? 0 : PAPERS[k].pass;
                       return `maturity ${p}/4 · ${STAGE[p] || ""}`; };
  // A row IS a paper you asked to keep in view — same gesture a search result or a library row
  // already makes (gotoPaper): close the panel, find the paper on the board (minting its card if
  // it isn't already sitting there), scroll to it, flash it. Nothing here opens a window or spawns
  // anything; reading the paper from there is the same hover/click the board always offers.
  function enter(k){
    panel.hidden = true;
    gotoPaper(k);
  }
  // ── done: off the reading list, back onto the board ──────────────────────────────────
  // Settled IN PLACE, with no reload. This direction is purely additive — the paper's card joins
  // the curated column and nothing already drawn stops being true — so there is nothing for a
  // reload to settle. The other direction, `moveToCurate` in 10-pdf.js, SUBTRACTS a paper the
  // board may already hold arrows into, and still reloads; see the note there.
  //
  // It reloaded here too, once, and that alone read as a stuck button. `/` builds the graph
  // payload inline (serve.py's do_GET), writing config.toml invalidates the server's payload
  // cache, and a navigation is not committed until the first response byte — so the browser sat
  // on the OLD page, panel open, row still there, ✓ still live, for the whole rebuild. Sixteen
  // seconds of it on the real library, before ruamel.yaml.clib and graph.py's parse cache.
  // Clicking the ✓ again then POSTed again, which invalidated the rebuild already in flight and
  // started the wait over — so the one gesture that looked like it might help was the one that
  // hurt. `btn.disabled` shuts that door; not reloading removes the wait it was a door to.
  function dropRow(k){
    const row = panel.querySelector(`.wp-row[data-k="${k}"]`);    // citekeys are [A-Za-z0-9]+
    if (row) row.remove();
    const n = panel.querySelectorAll(".wp-row").length;
    if (!n) { panel.hidden = true; pill.hidden = true; return; }  // an empty list has no pill, as at boot
    pill.innerHTML = `reading list · <span class="n">${n}</span>`;
  }
  addEventListener("readinglistchange", e => dropRow(e.detail.removed));
  async function returnToGraph(k, btn){
    if (OFFLINE.on) return;                   // hidden offline (css/14-offline.css), see the note
    if (btn) btn.disabled = true;
    try {
      await removeFromReadingList(k);
    } catch { if (btn) btn.disabled = false; alert("server unreachable — is lit serve running?"); }
  }

  panel.innerHTML = `<div class="wp-hd">reading list</div>` + inProg.map(k =>
    `<div class="wp-row" data-k="${k}" title="show ${k} on the board">`
    + `${passCircle(PAPERS[k].pass || 0)}<span class="ckey">${k}</span>`
    + `<span class="stage">${stage(k)}</span>`
    + `<button class="wp-done" data-done="${k}" title="done: return ${k} to the graph">✓</button>`
    + `</div>`).join("")
    + `<div class="wp-note">click a row to find it on the board</div>`
    + `<div class="wp-note wp-offline">returning a paper to the graph ${OFFLINE_WHY}</div>`;

  pill.addEventListener("click", () => {
    const aimPanel = document.getElementById("aimPanel");
    if (aimPanel) aimPanel.hidden = true;     // one panel open at a time
    panel.hidden = !panel.hidden;
  });
  panel.addEventListener("click", e => {
    const done = e.target.closest(".wp-done");
    if (done) { e.stopPropagation(); return returnToGraph(done.dataset.done, done); }
    const r = e.target.closest(".wp-row"); if (r) enter(r.dataset.k);
  });
  addEventListener("keydown", e => { if (e.key === "Escape") panel.hidden = true; });
  // click outside an open panel dismisses it (capture so it runs before the board's own handler)
  addEventListener("click", e => {
    if (!panel.hidden && !e.target.closest("#wipPanel,#wip")) panel.hidden = true;
  }, true);
})();
// a click on empty board space (not a card or broad node) thaws any pinned isolation.
// isConnected guard: a drill/collapse rebuild detaches the clicked row mid-dispatch, so a
// pinning click bubbles here with a detached target — don't misread that as empty space.
// Click empty board space to thaw the SLICE-ROW pins. Claim pins are deliberately not thawed here:
// they are not really pins, they are the "this claim is shown" state (showBroad), and dropping the
// brightness while its papers stayed in the column would put back exactly the half-state the merge
// removed. A claim goes away by clicking it again, with `clear arrows` in the HUD (or `c`), or with
// `clear` in the papers-column header. This gesture SURVIVES those two doors rather than being
// replaced by them — it costs no travel and it is the quick one — but it is no longer the only way
// back, which it had no business being: on a fanned-out board there is no empty space left to click.
board.addEventListener("click",e=>{
  // .bfam counts as "not empty space": the box's own padding and its nest gutter are part of a
  // family, and thawing the board because the click landed on 7px of container chrome would be
  // indistinguishable from a misfire.
  if(!pin.length||!e.target.isConnected||e.target.closest(".card,.bn,.bfam")) return;
  const keep=pin.filter(p=>cardIdLevel(p.cardId)>=SYNTH);
  if(keep.length===pin.length) return;
  pin=keep; redraw();
});
