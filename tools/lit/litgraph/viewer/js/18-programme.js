// ── the narrative card: a proposal's prose, wired into the graph ─────────────────────────
// A narrative (programme design §7, extended) is one linearization of the programme into a
// grant's sections. It used to render as a static panel in a standing "programme lane" on the
// main board, with each bullet's citations as inert chips. Two things were wrong with that:
//
//   * **the lane.** A grant's argument stood in the leftmost column of every reader's board,
//     whether they had come to read the proposal or to browse the library. The programme is
//     something you ASK for now — the HUD's programme pill opens one aim, or a whole proposal
//     (narrative + the aims under it), on its own page. Nothing programme-shaped is on the
//     board at rest; `order` is paper-only, so nothing puts one there.
//   * **the chips.** A bullet's refs are the one thing a reader wants to follow, and a chip is
//     a dead end exactly where the rest of this viewer draws an arrow. The old comment here
//     defended that as protecting the schema — but the schema is protected by the narrative
//     carrying no edges *into the graph*, which is a fact about build.py, not about what the
//     viewer is allowed to draw. So a bullet is now a slice and its refs are ordinary `grounds`
//     / `cons` edges (build._narrative_card_json), and this card gets the whole machinery for
//     free: open it, and every sentence has arrows running to the cards it rests on; hover one
//     and just its sources light up.
//
// Deleting programme/narrative/ still changes nothing the graph computes — that invariant is
// held where it always was, in the Python (tests/test_narrative.py), not by refusing to draw.

// The narrative's own rendering of its slices, in place of the paper DAG (renderGraph) and the
// aim outline. Neither fits: a bullet has no local support and no sub-structure — the ONLY
// structure a narrative has is which section a sentence stands in, and that is an ordering, not
// a graph. So the sections are the groups, in the order the file writes them, and a bullet is a
// leaf row whose whole content is the sentence that will appear in the grant.
function renderNarrative(id, p, box){
  const byId = {}; p.slices.forEach(s => byId[s.id] = s);
  const secs = p.sections || [];
  const nb = p.slices.length;
  let html = `<div class="sbar"><span>${nb} bullet${nb === 1 ? "" : "s"}`
           + ` · ${secs.length} section${secs.length === 1 ? "" : "s"}</span>`
           + `<span class="saxis">◂ what each line rests on</span></div>`;
  for (const sec of secs) {
    const col = grpCollapsed.has(`${id}::${sec.title}`);
    html += `<div class="sgrp nsec" data-grp="${esc(sec.title)}">`
          + `<span class="gcar">${col ? "▸" : "▾"}</span>${rich(sec.title)}`
          + `<span class="gct">${sec.bullets.length}</span></div>`;
    if (col) continue;                       // header only — the section's prose folds away
    html += `<div class="sgrpb">`;
    for (const sid of sec.bullets) {
      const s = byId[sid];
      if (!s) continue;
      // the ref COUNT still rides on the row, and is the one thing the chips did honestly: it
      // says how much is standing behind this sentence while the card is shut and no arrow is
      // drawn. A bullet with nothing under it says so — an unbacked line in a grant is exactly
      // what a reader of this card is looking for.
      const n = s.nref || 0;
      html += `<div class="slice nbul" data-sid="${s.id}">`
            + `<span class="sid nb">${s.id}</span>`
            + `<span class="stx">${rich(s.text)}</span>`
            + (n ? `<span class="nrf" title="${n} source${n === 1 ? "" : "s"} — open the card to`
                 + ` draw them, hover this line to light just these">${n}</span>`
                 : `<span class="nrf none" title="nothing cited yet">—</span>`)
            + `</div>`;
    }
    html += `</div>`;
  }
  box.innerHTML = html;
}
