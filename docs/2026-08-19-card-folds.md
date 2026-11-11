# What an open card shows: three folds, one click each

**Status:** built · `viewer/js/03-card.js` (`.cabsx`), `05-slices.js` (`renderGraph`,
`sliceDefaultOpen`), `04-hover-pin.js` (`cardClick`), `07-expand.js` (`expandCard`) ·
**Date:** 2026-08-19
**Companions:** [2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) ·
[2026-08-05-edge-visibility.md](2026-08-05-edge-visibility.md) ·
[2026-08-03-topics-and-claim-altitudes.md](2026-08-03-topics-and-claim-altitudes.md)

Opening a card used to be one gesture that did four things at once: it printed the paper's head,
dumped its abstract, unfolded its entire local subgraph, and opened every cited card **already
unfolded onto the exact slice the edge points at**. Each of those was defensible on its own and
the four together were not.

Measured on the real library — one click on the first card in the landing column
(a review paper with 69 slices):

| | before | after |
|---|---|---|
| cards left open | **7** | 1 |
| slice rows on the board | **210** | 0 |
| arcs drawn | **224** | 7 |
| height of the card you clicked | **2726 px** | 188 px |

A 2726-px card is not a card. It is a document, and the bibliographic head you opened it to read
is 3% of it.

## The rule

**An open card is the paper's identity.** Circle, citekey, class, tags, year, title, byline — and
two folded rows underneath it, each saying what is behind it:

```
◕ Nakamura2024Surv   review   [tags]        2024
  Stream Processing Performance: From Operators to Pipelines
  Nakamura, Ren · Osei, Kofi · Lindqvist, Maja
  ▸ ABSTRACT
  ▸ 69 SLICES · 50 EDGES
```

Everything below the byline is now **asked for**, and nothing this expansion spawns arrives open.

### Fold 1 — the abstract (`.cabsx` → `.cabs`)

200 words of someone else's prose, standing between the byline and the graph. It is the longest
thing on the card and the one you reread least; it earns its place on the card and not its place
*in front of* the card.

Keyed by **citekey**, exactly as `stubOpen` is, and for the same reason: an abstract is a
bibliographic fact about a paper, so the two instances of one paper standing in two columns have
nothing to disagree about, and unfolding it once unfolds it wherever that paper stands. It
therefore survives a rebuild (`paperCard` re-mints the class) and survives a close — reopening a
card you were reading the abstract of lands back on the abstract.

The toggle flips a class on every instance and re-renders nothing, so the caret is CSS
(`.card.absopen .cabsx .acar::before`) rather than markup.

### Fold 2 — the slice graph (the `.sbar` header)

The bar the graph already carried — `69 slices · 50 edges` — becomes the section's own header.
Shut, it is a caret and a size; open, it grows back the axis label and the `fold to graph` toggle,
which describe columns that are not on screen until then.

Keyed by **card id** (`level:key`), like `sFold`, because this one *is* per instance: the same
paper opened in the grounds column and in the landing column are two readings. Seeded once
(`sliceSeeded`, the `grpSeeded` idiom) so unfolding sticks across the rebuilds a click causes,
and cleared by a close so a reopened card is a fresh read.

**No rows rendered means no arcs added.** The within-card links are not emitted at all while the
section is shut — `edgeVis` clause 1 would turn every one of them off anyway the moment either end
fell back to the card border, and an arc that collapses onto the container→container line is the
one shape no isolation can ever thin. A *cross*-paper edge into a shut card keeps anchoring on the
border and sharpens to the row when the graph is unfolded: the same continuum a collapsed card is
already on, one rung longer.

**One exception, and it is not the board.** A page that *is* one card — the curation card window
(`&drive=1`), `lit preview`'s isolated render, the mobile curation view — exists for the slices.
Making the curator click for them is a papercut on every step of the loop, so `sliceDefaultOpen()`
starts them open there (`DRIVE || MOBILE_CURATE || ORDER.length === 1`). The board is the only
surface that asks.

### Fold 3 — the cited cards stay shut (`expandCard`)

Expanding a paper still spawns its neighbours in the grounds/builds columns, drawn from the same
edges as before. They just arrive **collapsed**, as the landing column has always drawn a paper
that has not been focused ([2026-06-25 §the abstract view](2026-06-25-visualization-design.md)):
one line, circle and citekey.

This reverses "opening each source on the exact cited finding is the whole payoff — you see what
it took from them without a click." That reads well for one source. It does not survive twelve:
the grounds column came up as a wall of open cards, each with its own title, byline, abstract and
20-odd slice rows, and finding any one paper in it meant scrolling past the rest. The concession
had already been made once, for programme containers (a grant narrative's introduction can ground
dozens of sentences in dozens of papers), where it was written down as a special case for aims and narratives. It is
the general rule now, which deletes the special case rather than adding to it.

Nothing is lost by waiting, because the edge layer was already built for this: the arrow anchors
on the card border and stays a **ghost** — "there is a relation here if you open it" — until the
card is opened, then scaffolding, then a lit fan if you pin it
([2026-08-05 §clause 3](2026-08-05-edge-visibility.md)).

## What did not change

- **`?goto=Citekey:sid`.** Naming a claim must put that claim on screen, so the handoff still
  reveals: `reveal()` now unfolds the slice section on its way to forcing the drill path open. It
  is the only caller left.
- **Aim cards.** An aim already opened on its argument alone with every other group folded
  ([2026-08-02](2026-08-02-programme-graph-design.md) and the `groups` table in `renderSlices`);
  that is this same rule, arrived at earlier for a different container. A narrative's body *is*
  its sections and has no head to bury, so it keeps opening whole.
- **The hover tip, `fold to graph`, per-slice folding, pins, edge visibility.** Untouched. The
  folds are state the existing decisions read, not new decisions about arrows.
