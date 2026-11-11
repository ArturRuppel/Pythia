# Two additive views — the paper graph and the claim graph

**Status:** design · prototypes not yet built · **Date:** 2026-08-05
**Companions:** [CONCEPT.md](../CONCEPT.md) · [SCHEMA.md](../SCHEMA.md) ·
[2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) ·
[2026-08-03-topics-and-claim-altitudes.md](2026-08-03-topics-and-claim-altitudes.md)

Two new lenses over the *same* authored data, built as standalone prototypes and served
separately before anything is welded into the viewer. **Purely additive**: the board, the walk
and the library are untouched, and neither view writes anything or introduces a field.

The motivating observation is one sentence:

> **The support skeleton — the thing the whole model is built around — has no standing view.**

The band draws containment between broad nodes. `redraw` suppresses edges touching a broad node
unless it is isolated. The walk shows one focus and one relation. So `leads_to` from a
quote-welded claim, through derivation, across papers, down to a measurement floor exists in the
data, is *used* (every emergent colour is read off it), and is never drawn as a landscape.

---

## 0. What both views are not

An earlier version of this idea was an embedding point cloud — claims as points, proximity as
semantic similarity, clustering as generalization. It was rejected for the core, and the reason
is worth recording because it governs both views below:

> **Every relation Litgraph draws is authored, contestable and quote-welded. A cosine similarity
> is none of those.** A proximity you cannot disagree with is not a claim (2026-08-03 §1), and
> rendered in the same visual language as `leads-to` it will be read as one.

Both views below are **projections of authored edges**. Nothing is inferred, everything is
auditable, and no model is in the loop. An embedding layer remains possible later as a *third*,
clearly-distinct thing — most plausibly as a proposer (`lit propose`: merge candidates, missing
`leads_to`, incoherent families) rather than a renderer. Out of scope here.

## 1. The substrate — one file, no coupling

Both prototypes consume **`dist/graph.json`**, the payload `build.emit()` already writes
(3.2 MB against the current library). Nothing else. No Python import, no SQLite, no rebuild
hook, no shared module with the viewer. This is what makes the two buildable in parallel and
throwaway-able independently.

What is in it, and the shapes that matter:

| Key | Count today | Notes |
|---|---|---|
| `papers` | 77 | curated only; carries `pass`, `year`, `type`, `tags`, `slices`, and the four edge lists |
| `stubs` | 5047 | bib metadata only — title/year/type/doi/journal/authors |
| `broad` | 45 | `kind`, `title`, `text`, `meter {s,c}`, `leads_to` |
| `order` | 5124 | the global pass/year ranking |
| `topics` | 18 | keyword closures + curated paper lists |

Per-paper edge lists (each entry names the mediating slice in `via` — **there is no bare
paper→paper edge in the model**, CONCEPT §10.4):

| List | Entry | Total |
|---|---|---|
| `grounds` | `{key, tid, via}` — a `grounded_in` ref at a container; `tid` set iff sharpened | 634 |
| `cons` | `{slug, via}` — a slice's `leads_to` into a broad node | 297 |
| `lateral` | `{key,tid,sign,via}` or `{slug,sign,via}` — `corr` / `contra` | 92 |
| `ans` | `{key,tid,via}` or `{slug,via}` — cross-paper `answers` | — |

Per-slice: `{id, kind, text, color, is_floor, grounded, borrowed, answered, up, gen, quote}`.
822 slices total. **The emergent colours are already computed** (`color`, `grounded`,
`borrowed`, `is_floor`) — a view reads them, it does not re-derive them.

> **Rule for both prototypes: the graph.json path is a required CLI argument with no committed
> default.** The file lives in the private data repo; this repo is public. No absolute path,
> no fallback, no `config.toml` read.

---

## 2. View A — the paper graph (`prototypes/paper-graph/`, port 8001)

ResearchRabbit-shaped: papers as circles, sized and filled, in a force layout. Because the model
has no paper→paper edge, **every edge here is a projection**, and there are two worth drawing.
They answer different questions and should be togglable, not merged.

### A1 · Grounding projection — "what does my library rest on"

Collapse each `grounds` entry to `paper → target`, de-duped per pair. Directed.

Measured on the current library: **424 distinct targets, 357 of them with in-degree 1.** Drawn
naively that is a hairball of leaves around a small core. So:

> **Default to in-degree ≥ 2 (67 targets today), with the threshold on a slider.** The
> singletons are real data, not noise, but they are the frontier's tail and belong behind a
> control rather than in the landing view.

The curated core is thin, and it is worth stating the number at the right level of dedup —
three readings of "how much of my grounding lands on something I have read" that differ by a
factor of four:

| Counting | Value |
|---|---|
| raw `grounds` refs landing on a curated paper (a ref per mediating slice) | 117 of 634 |
| **distinct (source, target) pairs landing on a curated paper** — what the graph draws | **90 of 559** |
| distinct curated papers ever grounded in | 27 of 77 |

**The middle row is the one a graph view means**, since an edge is a pair. The rest points into
the 5047 stubs, and that asymmetry is the view's whole point, not a defect.

### A2 · Co-support projection — "who is working on the same claim"

Two papers are linked when slices in each `leads_to` the same broad node. Undirected, weighted
by the number of broad nodes shared. Derived entirely from `cons`.

Measured: **380 pairs over 53 papers** — mean degree ~14, a hairball at weight 1. **Default to
weight ≥ 2 (144 pairs); weight ≥ 3 is 41.** Same slider idiom as A1.

24 of the 77 curated papers touch no broad node at all and therefore do not appear in A2. They
should be shown as an explicit off-graph tray, not silently dropped — a paper with no rung is a
curation signal (2026-08-03: *order organizes; absence doesn't*).

On top of A2, the **signed layer**: `lateral` is already slice↔slice, so `corr` / `contra`
project to signed paper edges for free. This is the one question no existing surface asks —
the board lists a claim's evidence, it never shows *who is arguing with whom*. Distinct style,
own toggle, drawn over either projection.

### The mark — size and fill are two different variables

Degree is confounded with `pass`: a pass-4 paper has ~11 slices and a pass-1 paper has two, so
degree partly measures *how hard the paper was curated*. Don't hide that — put both in one mark,
reusing the idiom the landing card already has:

> **Size = degree. Fill = the `pass` pie (`○ ◔ ◑ ◕ ●`), empty ring = stub.**

The readout that falls out is the reason to build this view at all:

> **A big empty ring is the next paper to curate** — many curated papers ground in it, nobody
> has read it.

It works today. The top grounding targets are three curated papers at in-degree 9, 9 and 8 — all full disks,
the field's canon correctly identified as load-bearing. The top *uncurated* target is a stub at
in-degree 5. That is
the view's first answer, and it is a real one. **Ship-test: the prototype must surface it
without being asked.**

Hover gives title/authors/year/journal; click pins a paper and dims to its neighbourhood; a
paper's citekey is the handoff seam back to the board (`gotoPaper()` equivalent — for now, just
print the citekey where it can be copied). *(Built 2026-08-06: the citekey field stayed, for
copying into a terminal, and the pin panel grew a real door beside it — §4.2.)*

## 3. View B — the claim graph (`prototypes/claim-graph/`, port 8002)

Slice-centric. **Papers demote to an attribute** — a hull, a badge, a hover — and the nodes are
the 822 slices plus the 45 broad nodes. This is the view that draws the support skeleton.

Edges, all authored, no projection:

- slice `up` → local `grounded_in` (within-paper support);
- slice `gen` → local `leads_to` (within-paper generalization ladder);
- `cons` → slice → broad node;
- `broad.leads_to` → the broad ladder (the 4-tier, 45-node structure the band draws as boxes);
- `grounds` with `tid` set → the **sharpened** cross-paper slice→slice edges;
- `lateral` → signed, drawn distinctly, **never part of the walk** (CONCEPT §9).

Colour is not a design decision — CONCEPT §3 already specifies it and `graph.json` already
carries it: grounded vs plausible, original vs borrowed, floor vs not, question open vs
answered. **Read the fields; invent nothing.**

### Layout: layered, not force

`leads_to` is a DAG with a real depth axis — that is the entire point of the altitude work — and
a spring layout throws it away. Rank nodes by distance-to-floor and lay out left→right, keeping
the board's established orientation:

> **left = evidence/past, right = synthesis/now** (2026-06-27 rotation, still binding).

Floors (`is_floor`) pin to the left edge; broad nodes to the right. A claim whose chain never
reaches a floor has no rank from below — **those are the interesting ones**, and they should be
visibly stranded rather than quietly assigned rank 0.

### What this view is for (flat version)

Not navigation — the board and the walk do that better. It is a **diagnostic of what the library
actually establishes versus what it merely asserts.** The expected first reading is
uncomfortable: a large mass of plausible-but-unfloored claims, clustered somewhere specific. If
the picture is *not* uncomfortable, be suspicious of the rendering before believing the library.

## 3.1 The claim graph goes spherical — generality as radius

**Date:** 2026-08-05, after looking at the flat build. The layered 2D version renders and its
diagnostic holds (48% of claims never reach a floor), **and it is kept** — but it is the wrong
primary. Flat layering spends one axis on altitude and packs the rest arbitrarily; the structure
has two independent authored dimensions and deserves both.

> **A sphere: generality is radius, family is direction, and the apex is the centre.**

| Coordinate | Read from | Note |
|---|---|---|
| **radius** | distance-to-floor (slices) / ladder tier (broad) | apex at r≈0, floors at the surface; small inner radius so the innermost nodes don't collide at a point |
| **direction** | the top-level ancestor of the broad node a slice `leads_to` — one of the band's **16** | Fibonacci-distributed over the sphere, not wedges: family is a solid angle, 2 DOF |
| **within a shell** | force-packed to avoid overlap | **meaningless by construction, and labelled so** |

Shell area grows as r², which matches the data: 3 nodes at the top tier, 112 floors at the
bottom. The one broad node with two top-level ancestors (`caching-effect-is-workload-dependent`)
sits at the normalized midpoint of its parents' directions.

The **16 top-level entries** are 9 broad methods, 4 broad claims and 3 broad questions. The 4
claims are `pipeline-behaviour-is-collective-dynamics` and
`performance-and-control-share-one-substrate` (the two apexes of 2026-08-03 §2), plus
`tuning-effect-is-workload-dependent` and the deliberate orphan `scale-up-or-scale-out-dichotomy`.
*(An earlier draft of this section said "2 apexes + 4 roots", which reads as six nodes; it is
four, two of which are the apexes.)*

### The inheritance rule is underdetermined — and the finding survives it anyway

"Inherit a family through the local `gen`/`up` ladder" does not pin down a single rule, and the
candidates disagree badly: **291** slices (follow `gen` only), **415** (forward-only along the
`leads_to` direction), **419** (`gen` then `up`), **509** (undirected transitive closure). That
spread is wider than most of the numbers in this document, so no conclusion may rest on it.

The halo conclusion does not, because **the radius constraint binds first**: only 421–429 slices
have a distance-to-floor at all, so the ball is capped near 49% of the 867 nodes before family
direction is even consulted. **The halo is a majority under every inheritance rule.**

### The coordinates are sparse, and that is the finding

| Coverage | Count |
|---|---|
| slices with an **authored** family direction (via `cons`) | 284 of 822 |
| …plus inheritance through the local `gen`/`up` ladder (also authored) | 419 of 822 |
| …plus a paper-level majority vote | 784 — **rejected** |
| slices with a distance-to-floor rank | 429 of 822 (393 unfloored) |

The paper-level fallback is rejected because it would place ~365 slices in a direction nobody
wrote — a guess wearing structure's clothes, which is §0's whole prohibition arriving from a new
angle. So:

> **A slice with no authored coordinate does not get a fabricated one.** It goes in a diffuse
> halo outside the shell, never into a sector it was never assigned to.

The resulting picture is a **structured ball** — claims that ladder into a family and reach a
floor — wrapped in a **haze** of claims that do neither. That is the view's payload: the
unfloored fraction stops being a statistic and becomes the first thing you see. If the haze is
thicker than the ball, that is the honest state of the library.

### Two motions, deliberately different controls

- **Camera distance drives level of detail.** Nodes merge into their nearest *ladder ancestor*
  as they stop resolving: 16 families → 45 broad → 867 nodes → quote text. This is the
  "zoom out and they merge" of the original sketch, with the merge target **authored** rather
  than clustered.
- **Radial position is navigation.** Flying to the centre is flying toward the apexes; "move
  inside" is a real gesture, not a camera trick.

**Occlusion is the cost of a filled ball**, and it is solved rather than apologized for: a
shell-window control showing `r ∈ [a, b]` peels radially. It is the altitude slider and the
see-the-middle fix in one control.

Quantitative readouts (meters, counts) stay in a 2D side panel — perspective and occlusion make
distance and density unreadable in 3D, so the sphere is for structure and navigation only.

Built standalone at `prototypes/claim-sphere/`, port **8003**. Flat version stays on 8002 for
comparison.

### 3.2 Three readings, one renderer — and three.js is gone

**Date:** 2026-08-05, from the design handoff. The sphere holds, and the WebGL build under it
does not: `prototypes/claim-sphere/` is now **2D canvas** with a hand-rolled perspective
projection and a painter's-algorithm depth sort. ~1000 nodes and ~1000 edges never needed a GPU,
and canvas buys exact control of hairline weight, dash patterns and label placement — which is
what makes the ink-and-red treatment legible at all. The vendored `three.module.js`,
`OrbitControls`, `FlyControls`, `scene.js` and `model.js` are deleted; `derive-model.js` (pure,
the five coordinate rules) and `sphere-view.js` (the renderer) replace them.

**One renderer, three layouts** — `layout="sphere" | "sectors" | "shells"` over one node table,
so the three readings cannot drift apart:

- **1a · the ball and the haze** — the reading above, unchanged: radial shell-window peel,
  per-kind edge toggles, the unplaceable claims as a red haze outside the sphere.
- **1b · the sixteen, pulled apart** — same coordinates, each family exploded along its own axis
  so a solid angle reads as a limb. The ranked branch list doubles as the isolate control, and it
  stays in the **ladder's own order**, never sorted by size, so the claim/method asymmetry
  survives the sort.
- **1c · the stack and the slab** — radius unrolled: distance-to-floor becomes height, the ladder
  read edge-on as stacked plates, with the rank-less claims standing beside it as a slab at no
  height at all.

1c splits on **rank alone** while 1a/1b split on **both coordinates**, so their haze counts
differ by design; each view says which in its standfirst.

**No number in the chrome is hardcoded.** Every count in a heading, standfirst, checkbox label
or plate table is read off the derived model at load. The design bundle's own figures were three
hours stale by the time it was implemented (911 slices → 938), which is the argument.

The fly camera is gone with three.js; orbit + dolly is the whole gesture set, and flying to the
centre is still flying to the apexes.

### 3.3 One panel — the rendering is a setting, and colour comes in

**Date:** 2026-08-05. §3.2 shipped the three readings as three stacked screens, each with its own
control column. That was the wrong shape and the page said so: **three menus for three settings
of one view.** The prototype is now a **single panel**, and `layout` is a control in it beside the
others.

The merge is not just tidying. Because there is one view and one state, a selected claim, an
isolated branch and a radial peel all **survive switching reading** — so "where does this thing
sit in the stack" is now a click, not a scroll to another screen and a hunt for the same mark.
The one place state is deliberately *not* per-reading is the haze checkbox: it means "the haze" in
the ball and the sectors, "the slab" in the stack, and it keeps one value across all three. The
sectors help line says out loud that the haze belongs to no limb, rather than the panel quietly
switching it off.

**Colour is a second channel, chosen in the settings** (`colour.js`, pure). Four readings:

| Mode | What the hue is | Where it comes from |
|---|---|---|
| `status` *(default)* | grounded · borrowed · plausible · question · floor · model | **the board's own emergent colours** — `graph._slice_color` (SCHEMA §7), hexes mirrored from `viewer/template.html`'s `:root` |
| `family` | one hue per top-level entry | golden-angle over the hue circle, at constant OKLCH lightness and chroma — the same trick that distributes the family *axes*, so ladder-neighbours are far apart in colour too |
| `generality` | distance to a measurement floor | an ordered ochre→indigo ramp; the quantity the radius already draws, as a second channel |
| `ink` | nothing | the monochrome the view was first drawn in |

Two rules hold across all four. **The status palette is not ours** — a claim that is green on its
card is green in the sphere, and the sphere invents no hue the board does not already use; that
also means it inherits the board's near-collisions (`floor`/`question` are both brown, `model`/
`broad` both violet), which shape disambiguates here. And **red still means exactly one thing**: a
node with no authored coordinate is drawn in the accent in *every* mode, because that is the
finding the view exists to show. Colour never reaches the haze. The selection bracket moved from
red to ink for the same reason — with colour on, an accent bracket around a red haze node points
at itself.

The branch strip under the viewport carries each family's hue on its magnitude bar, so it is the
`family` legend and the isolate control at once, and `colour.js` is imported by both the renderer
and the chrome — a swatch and the dot it explains cannot disagree.

**OKLCH → sRGB is hand-rolled** rather than handed to the browser's `oklch()`. The same hex has to
reach a canvas fill, a CSS background and Node under the headless check; a colour string that
fails to parse in one of the three leaves the previous `fillStyle` standing, which presents as a
drawing bug.

### 3.4 Three things missing from a view you can actually work in

**Date:** 2026-08-05. Orbit and dolly turned out not to be the whole gesture set after all (§3.2),
and two of the three additions here are not gestures at all.

**Pan moves the pivot, not the image.** The camera grew a target `tx/ty/tz` that `project()`
subtracts before it rotates, so an orbit *after* a pan turns about what you panned to rather than
about the origin — panning to a limb and then walking around it is one continuous act. The
alternative, a screen-space offset added after projection, is three lines shorter and wrong: the
figure would swing away the moment you dragged. The screen→world basis is read off the same
yaw/pitch the projection uses (`right = (cos y, 0, −sin y)`, `up = (−sin p sin y, cos p,
−sin p cos y)`), so a point at the pivot depth tracks the cursor exactly; nearer and further marks
lag and lead by parallax, which is the depth cue doing its job. Right-drag, middle-drag and
shift-drag all pan, so no existing mouse gesture changed meaning; on touch the two-finger gesture
now dollies on the spread *and* pans on the centroid at once, that being the only pan a
touchscreen has to spare.

**One expansion knob, on whichever axis the layout gives the radius.** `spread` scales the radial
coordinate: every shell gap is multiplied, marks keep their pixel size, and the knot of broad
nodes at the centre opens far enough to count. It is deliberately *not* a dolly — flying in scales
the marks too, which is why the middle stays unreadable however close you get. In the stack the
radial axis is height, so the same attribute scales plate spacing instead; the slab stretches with
it. The dolly ceiling now follows the knob (`11 × spread`), because a figure you can expand past
the far plane is a figure you cannot get back.

**Focus: the neighbourhood, hiding everything else.** Clicking a mark names it; ticking *focus*
makes that click hide every node the selection does not reach within `n` hops. Three decisions
worth keeping:

- **Adjacency is built from the edge kinds currently ticked**, so "connected" means what the
  reader has chosen to draw — ask the question of `up` alone and you get the grounding chain, not
  the citation web. It is undirected: *what is this claim attached to* is not a question about
  which way an arrow points.
- **Focus overrides every other filter**, in both directions. Inside the neighbourhood the shell
  window, the branch isolate and the haze switch all step aside; outside it nothing is drawn. A
  peel that could still swallow a neighbour would make "everything connected to this claim" a lie,
  and the one thing this view must not do is quietly drop a node.
- **The text is a target too.** Every label the renderer draws — the family names on the
  perimeter, the broad titles at close range, and the per-node labels the focus mode adds — is
  recorded as a hit box resolving to its node, so clicking a family's name and clicking its apex
  are the same act. Marks are tested first, since a label is a far larger target than the 5px dot
  it names. A family label resolves to its own top-level broad node, which is what the strip's
  isolate button has always meant.

The count under the control is emitted by the renderer (`sv-shown`), not recomputed by the chrome:
it is the only place that knows what survived, and a focus that legitimately shows three nodes
should not be indistinguishable from a bug.

## 4. How they get built and looked at

Standalone, side by side, nothing welded:

- `prototypes/paper-graph/` and `prototypes/claim-graph/` — disjoint trees, no shared files.
- Each: one static page (vanilla JS + SVG/canvas, no CDN, no build step) plus a ~40-line
  `stdlib`-only static server taking `--graph <path>` and `--port`.
- Ports **8001** and **8002** (`lit serve` holds 8000; 8477–8479, 8766, 5001–5002 are taken by
  other desk services — see `~/agents/desk.md`). Bind `127.0.0.1`.
- No dependency on `litgraph`, no import from it, no change to any file outside the prototype
  tree. Nothing is committed by the implementing agents.

**Welding is a separate decision, deliberately deferred.** If a view earns its place, it becomes
a HUD toggle beside `walk` and its projection moves into the emit layer. If it doesn't, the
directory is deleted and nothing else has to be untangled. That property is the reason for the
separate servers, and it is worth more than the convenience of building in place.

**Reachable, not yet welded (2026-08-05).** The halfway step is in: `lit serve` publishes the
`prototypes/` tree at `/views/<slug>/` and lists what is actually on disk in a HUD dropdown, and
each view links back to the board. Nothing moved into the emit layer — a view still fetches a
*relative* `graph.json`, which lands at `/views/<slug>/graph.json` and is answered with the
server's live payload, so the views read the same rebuilt-from-YAML graph as the board rather than
a stale `dist/` artifact. It stays **serve-only**: a static `lit build` is one self-contained file
and gets no `views` key, hence no dropdown whose links nothing would answer. Because `_VIEWS` is a
module constant, *a running server predates any change here* — the dropdown appears only after a
restart, which is exactly how the first version of this went missing for two days.

### 4.1 Navigation on a phone

Three changes, one principle each.

**A view opened in a new tab is a room with no door.** The HUD dropdown opened each view with
`target="_blank"`, which on a mouse is right — the board keeps its scroll position and whatever
the reader had open. On a touchscreen it is not: the back gesture is the only navigation a phone
reliably has, and a new tab severs it. The links now drop the target under
`(hover:none) and (pointer:coarse)`, so back returns to the board. Both halves are belt and
braces: every view also carries a visible `← board` link, because a remembered gesture is worse
than a door you can see. `paper-graph` and `claim-graph` had neither and now have both;
`claim-graph` was additionally missing a doctype and a viewport meta, so a phone was laying it out
at 980px and scaling the result down — quirks mode is not a place to debug an SVG's coordinates.

**A pinch is the only zoom a phone has.** `sphere-view` listened for `wheel` and nothing else, so
on a touchscreen the camera was nailed to its home distance — in a figure whose entire point is
flying in toward the apexes. It now tracks every live pointer rather than the first: one finger
orbits, two pinch. The details that matter are the seams. A second finger landing mid-drag
converts the gesture in place instead of rewinding the orbit; lifting one finger out of a pinch
re-seats the orbit on the survivor at *its* current position, so the view does not jump, and marks
it moved so the release is not read as a tap; a tap on touch clears the tooltip behind it, because
a finger leaves no cursor to move away and the readout under the figure has the full text anyway.
Path length for the tap/drag test is measured from the tracked point, not `e.movementX`, which is
routinely 0 for touch pointers.

**The rendering switch is navigation, not adjustment.** The merged panel puts a 296px settings
column beside the canvas, which fits no phone at any input device. Below 860px `.ctl-col` becomes
`display:contents`, dissolving the column so its groups can be ordered individually against the
view; the page then reads *rendering · the figure · what you selected · everything else*. The
rendering control keeps `position:sticky; top:0` and sheds its explanatory notes to a three-across
row. That is the one control worth pinning: the merge is only an improvement on a phone if
switching reading costs no scroll to find it. `reset view` is pulled up beside the thing it
resets. Layout keys off width; tap-target sizing keys off `(pointer:coarse)` separately, since a
narrow desktop window still has a mouse and does not need 20px checkboxes.

### 4.2 The handoff — `?goto=`

**Date:** 2026-08-06. §2 left the seam back to the board as a placeholder ("for now, just print the
citekey where it can be copied"), and a view you can only leave by the front door is half a door.
The other half is one query parameter:

```
?goto=Park2015NatMater        a paper       → scroll-and-flash, minting a stub's card if needed
?goto=Park2015NatMater:c3     a slice       → …and open the card, drill to that row, flash it
?goto=tissue-behaviour-…      a broad node  → hoist its papers, scroll, flash
```

Three decisions hold it together.

**The board's existing gestures ARE the handoff.** `gotoPaper()` and `showBroad()` are called
unchanged, so arriving from a view and finding the same thing by name leave the board in the same
state, and there is no second notion of *go there* to drift from the first. What the handoff adds
is the slice case, because the views are slice-centric and the board's own surfaces are not: no
existing door names a claim.

**Kind is resolved by asking the payload, never by spelling.** A citekey and a broad slug are told
apart by which table owns the name. Pattern-matching `Author2020Venue` against `a-kebab-slug` works
today and breaks on the first name that isn't shaped like its neighbours — and the failure would be
a silent jump to the wrong kind of thing. `Citekey:sid` is the schema's own spelling for a
sharpened ref (SCHEMA §3), so the URL says what the YAML says.

**Naming a claim opens the card; naming a paper does not.** A claim you cannot see is not a
handoff, so the slice case focuses the card and forces the drill path down to the row (an aim's
outline otherwise keeps it folded). A paper keeps the meaning that gesture has always had in the
search box and the library. Where the paper is real and the row is not — a slice renamed since the
link was made — the board lands on the paper rather than refusing; where the whole name is unknown
it says so in the search dropdown, because silence is indistinguishable from a jump that landed
off-screen.

Gated exactly like the `← board` door: the link appears only under `/views/`, since standalone
(ports 8001–8003) there is no board above the page to hand off to. Same tab, for the reason §4.1
gives. `?goto=` also outranks `?view=library` — a handoff that landed behind the library pane would
look like a handoff that did nothing.

## 5. Deliberately not decided

- **Whether the two paper projections should ever be shown at once.** They are different
  relations over the same nodes and superimposing them makes a node's degree meaningless.
  Toggle for now; revisit only if a real reading wants both.
- **Whether stubs belong in view B.** A stub has no slices, so it can only appear as a wildcard
  terminal. Left out of the first cut; it is the same container-wildcard question the board
  already handles with `landingKeys()`.
- **Whether view B should carry the topic axis.** It is the facet rail's job and 2026-08-03 §7
  already declined to put topics on claims. Not revisited here.
- **The embedding layer.** §0. A proposer, if ever, not a renderer.
